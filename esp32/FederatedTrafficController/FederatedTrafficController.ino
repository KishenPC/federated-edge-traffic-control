#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

#include "node_config.h"

namespace {

constexpr size_t kLaneCount = 4;

struct LanePins {
  uint8_t green;
  uint8_t yellow;
  uint8_t red;
};

struct NodeProfile {
  const char* nodeId;
  const char* label;
};

constexpr uint8_t SENSOR_PINS[kLaneCount] = {34, 35, 32, 33};
constexpr LanePins SIGNAL_PINS[kLaneCount] = {
  {21, 22, 23},
  {5, 18, 19},
  {4, 16, 17},
  {27, 26, 25},
};

constexpr NodeProfile NODE_PROFILES[] = {
  {"esp-a", "Intersection-A"},
  {"esp-b", "Intersection-B"},
};

static_assert(NODE_PROFILE_INDEX >= 0 && NODE_PROFILE_INDEX < 2, "NODE_PROFILE_INDEX must be 0 or 1");

const NodeProfile& ACTIVE_NODE = NODE_PROFILES[NODE_PROFILE_INDEX];

constexpr uint32_t SENSOR_SAMPLE_MS = 100;
constexpr uint32_t MIN_GREEN_MS = 5000;
constexpr uint32_t MAX_GREEN_MS = 20000;
constexpr uint32_t BASE_GREEN_MS = 5000;
constexpr uint32_t EXTRA_GREEN_MS = 9000;
constexpr uint32_t YELLOW_MS = 2000;
constexpr uint32_t ALL_RED_MS = 1000;
constexpr uint32_t SERVER_SYNC_INTERVAL_MS = 15000;
constexpr float DEMAND_ALPHA = 0.85f;
constexpr float STARVATION_STEP = 0.02f;
constexpr float MAX_STARVATION = 1.0f;
constexpr float LEARNING_RATE = 0.30f;
constexpr float MIN_WEIGHT = 0.50f;
constexpr float MAX_WEIGHT = 2.50f;
constexpr float RESIDUAL_TARGET = 0.20f;
constexpr float UPDATE_TRIGGER = 0.05f;

float laneDemand[kLaneCount] = {0.0f, 0.0f, 0.0f, 0.0f};
float starvationBoost[kLaneCount] = {0.0f, 0.0f, 0.0f, 0.0f};
float localWeights[kLaneCount] = {1.0f, 1.0f, 1.0f, 1.0f};
float lastPublishedWeights[kLaneCount] = {1.0f, 1.0f, 1.0f, 1.0f};

uint32_t globalRound = 0;
uint32_t phaseCount = 0;
uint32_t activeSampleCount = 1;
uint32_t lastSyncAttemptMs = 0;
bool wifiReady = false;

float clampFloat(float value, float low, float high) {
  return value < low ? low : (value > high ? high : value);
}

bool readSensorActive(size_t lane) {
  const int level = digitalRead(SENSOR_PINS[lane]);
  return SENSOR_ACTIVE_LOW ? level == LOW : level == HIGH;
}

void normalizeWeights() {
  float sum = 0.0f;
  for (float weight : localWeights) {
    sum += weight;
  }

  const float average = sum / static_cast<float>(kLaneCount);
  if (average <= 0.0f) {
    for (size_t lane = 0; lane < kLaneCount; ++lane) {
      localWeights[lane] = 1.0f;
    }
    return;
  }

  for (size_t lane = 0; lane < kLaneCount; ++lane) {
    localWeights[lane] = clampFloat(localWeights[lane] / average, MIN_WEIGHT, MAX_WEIGHT);
  }
}

void applyGlobalWeights(const float incoming[kLaneCount]) {
  for (size_t lane = 0; lane < kLaneCount; ++lane) {
    localWeights[lane] = clampFloat(incoming[lane], MIN_WEIGHT, MAX_WEIGHT);
  }
  normalizeWeights();
}

void setAllRed() {
  for (const auto& pins : SIGNAL_PINS) {
    digitalWrite(pins.green, LOW);
    digitalWrite(pins.yellow, LOW);
    digitalWrite(pins.red, HIGH);
  }
}

void setPhaseGreen(size_t lane) {
  for (size_t i = 0; i < kLaneCount; ++i) {
    const bool active = i == lane;
    digitalWrite(SIGNAL_PINS[i].green, active ? HIGH : LOW);
    digitalWrite(SIGNAL_PINS[i].yellow, LOW);
    digitalWrite(SIGNAL_PINS[i].red, active ? LOW : HIGH);
  }
}

void setPhaseYellow(size_t lane) {
  for (size_t i = 0; i < kLaneCount; ++i) {
    const bool active = i == lane;
    digitalWrite(SIGNAL_PINS[i].green, LOW);
    digitalWrite(SIGNAL_PINS[i].yellow, active ? HIGH : LOW);
    digitalWrite(SIGNAL_PINS[i].red, active ? LOW : HIGH);
  }
}

void sampleDemand(int activeLane) {
  for (size_t lane = 0; lane < kLaneCount; ++lane) {
    const bool active = readSensorActive(lane);
    const float instant = active ? 1.0f : 0.0f;
    laneDemand[lane] = DEMAND_ALPHA * laneDemand[lane] + (1.0f - DEMAND_ALPHA) * instant;

    if (static_cast<int>(lane) == activeLane) {
      starvationBoost[lane] = 0.0f;
    } else {
      starvationBoost[lane] = clampFloat(starvationBoost[lane] + STARVATION_STEP, 0.0f, MAX_STARVATION);
    }

    if (active) {
      ++activeSampleCount;
    }
  }
}

void waitWithSampling(uint32_t durationMs, int activeLane) {
  const uint32_t started = millis();
  while (millis() - started < durationMs) {
    sampleDemand(activeLane);
    delay(SENSOR_SAMPLE_MS);
  }
}

size_t chooseNextLane() {
  size_t bestLane = 0;
  float bestScore = -1.0f;

  for (size_t lane = 0; lane < kLaneCount; ++lane) {
    const float score = localWeights[lane] * laneDemand[lane] + starvationBoost[lane];
    if (score > bestScore) {
      bestScore = score;
      bestLane = lane;
    }
  }

  return bestLane;
}

uint32_t computeGreenTimeMs(size_t lane) {
  const float score = localWeights[lane] * laneDemand[lane] + starvationBoost[lane];
  const uint32_t proposed = BASE_GREEN_MS + static_cast<uint32_t>(score * EXTRA_GREEN_MS);
  return min(MAX_GREEN_MS, max(MIN_GREEN_MS, proposed));
}

float averageDemandExcluding(size_t excludedLane) {
  float total = 0.0f;
  for (size_t lane = 0; lane < kLaneCount; ++lane) {
    if (lane != excludedLane) {
      total += laneDemand[lane];
    }
  }
  return total / static_cast<float>(kLaneCount - 1);
}

void updateLocalModel(size_t servedLane, float preDemand, float postDemand) {
  const float residualError = postDemand - RESIDUAL_TARGET;
  const float scaling = max(preDemand, 0.20f);
  localWeights[servedLane] += LEARNING_RATE * residualError * scaling;

  for (size_t lane = 0; lane < kLaneCount; ++lane) {
    if (lane == servedLane) {
      continue;
    }
    localWeights[lane] += 0.05f * LEARNING_RATE * laneDemand[lane];
  }

  normalizeWeights();
}

float currentCycleLoss() {
  float total = 0.0f;
  for (size_t lane = 0; lane < kLaneCount; ++lane) {
    total += laneDemand[lane] + 0.25f * starvationBoost[lane];
  }
  return total / static_cast<float>(kLaneCount);
}

bool shouldPublishModel() {
  float maxRelativeDelta = 0.0f;
  for (size_t lane = 0; lane < kLaneCount; ++lane) {
    const float baseline = max(0.01f, fabs(lastPublishedWeights[lane]));
    const float relative = fabs(localWeights[lane] - lastPublishedWeights[lane]) / baseline;
    if (relative > maxRelativeDelta) {
      maxRelativeDelta = relative;
    }
  }
  return maxRelativeDelta >= UPDATE_TRIGGER || millis() - lastSyncAttemptMs >= SERVER_SYNC_INTERVAL_MS;
}

void printStatus(const char* stage, size_t lane = 255, uint32_t durationMs = 0) {
  Serial.printf("[%s] node=%s round=%lu", stage, ACTIVE_NODE.nodeId, static_cast<unsigned long>(globalRound));
  if (lane < kLaneCount) {
    Serial.printf(" lane=%u greenMs=%lu", static_cast<unsigned>(lane + 1), static_cast<unsigned long>(durationMs));
  }
  Serial.print(" demand=[");
  for (size_t i = 0; i < kLaneCount; ++i) {
    Serial.printf("%.2f%s", laneDemand[i], i + 1 == kLaneCount ? "" : ", ");
  }
  Serial.print("] weights=[");
  for (size_t i = 0; i < kLaneCount; ++i) {
    Serial.printf("%.2f%s", localWeights[i], i + 1 == kLaneCount ? "" : ", ");
  }
  Serial.println("]");
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.printf("Connecting %s to Wi-Fi", ACTIVE_NODE.nodeId);
  const uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 15000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  wifiReady = WiFi.status() == WL_CONNECTED;
  if (wifiReady) {
    Serial.printf("Wi-Fi connected. IP=%s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("Wi-Fi unavailable. Node will continue in standalone mode.");
  }
}

bool pullGlobalModel() {
  if (WiFi.status() != WL_CONNECTED) {
    wifiReady = false;
    return false;
  }

  HTTPClient http;
  const String url = String(SERVER_BASE_URL) + "/get_weights";
  http.begin(url);
  http.setTimeout(3000);

  const int responseCode = http.GET();
  if (responseCode != HTTP_CODE_OK) {
    http.end();
    return false;
  }

  DynamicJsonDocument doc(512);
  const DeserializationError error = deserializeJson(doc, http.getString());
  http.end();
  if (error) {
    return false;
  }

  const JsonArray weights = doc["weights"].as<JsonArray>();
  if (weights.size() != kLaneCount) {
    return false;
  }

  float incoming[kLaneCount];
  for (size_t lane = 0; lane < kLaneCount; ++lane) {
    incoming[lane] = weights[lane].as<float>();
  }

  globalRound = doc["round"] | globalRound;
  applyGlobalWeights(incoming);
  wifiReady = true;
  Serial.printf("Pulled global model round %lu\n", static_cast<unsigned long>(globalRound));
  return true;
}

bool pushLocalModel() {
  if (WiFi.status() != WL_CONNECTED) {
    wifiReady = false;
    return false;
  }

  HTTPClient http;
  const String url = String(SERVER_BASE_URL) + "/update";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(4000);

  DynamicJsonDocument payload(768);
  payload["node_id"] = ACTIVE_NODE.nodeId;
  payload["round"] = globalRound;

  JsonArray weights = payload.createNestedArray("weights");
  for (float weight : localWeights) {
    weights.add(weight);
  }

  payload["sample_count"] = activeSampleCount;
  JsonObject metrics = payload.createNestedObject("metrics");
  metrics["cycle_loss"] = currentCycleLoss();
  metrics["phase_count"] = phaseCount;
  JsonArray demand = metrics.createNestedArray("demand");
  for (float value : laneDemand) {
    demand.add(value);
  }
  metrics["average_other_demand"] = averageDemandExcluding(chooseNextLane());

  String body;
  serializeJson(payload, body);

  const int responseCode = http.POST(body);
  const String response = http.getString();
  http.end();

  lastSyncAttemptMs = millis();
  if (responseCode <= 0) {
    return false;
  }

  DynamicJsonDocument doc(512);
  const DeserializationError error = deserializeJson(doc, response);
  if (error) {
    return false;
  }

  const char* status = doc["status"] | "unknown";
  globalRound = doc["current_round"] | globalRound;

  if (doc["global_weights"].is<JsonArray>()) {
    const JsonArray incoming = doc["global_weights"].as<JsonArray>();
    if (incoming.size() == kLaneCount) {
      float newWeights[kLaneCount];
      for (size_t lane = 0; lane < kLaneCount; ++lane) {
        newWeights[lane] = incoming[lane].as<float>();
      }
      applyGlobalWeights(newWeights);
    }
  }

  for (size_t lane = 0; lane < kLaneCount; ++lane) {
    lastPublishedWeights[lane] = localWeights[lane];
  }
  activeSampleCount = 1;

  Serial.printf("Published local update. Server status=%s round=%lu\n", status, static_cast<unsigned long>(globalRound));
  wifiReady = true;
  return true;
}

void initializeHardware() {
  for (size_t lane = 0; lane < kLaneCount; ++lane) {
    pinMode(SENSOR_PINS[lane], INPUT);
    pinMode(SIGNAL_PINS[lane].green, OUTPUT);
    pinMode(SIGNAL_PINS[lane].yellow, OUTPUT);
    pinMode(SIGNAL_PINS[lane].red, OUTPUT);
  }
  setAllRed();
}

}  // namespace

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(1000);
  Serial.printf("Booting %s (%s)\n", ACTIVE_NODE.nodeId, ACTIVE_NODE.label);

  initializeHardware();
  connectWiFi();
  if (wifiReady) {
    pullGlobalModel();
  }
}

void loop() {
  const size_t lane = chooseNextLane();
  const uint32_t greenMs = computeGreenTimeMs(lane);
  const float preDemand = laneDemand[lane];

  printStatus("before_phase", lane, greenMs);
  setPhaseGreen(lane);
  waitWithSampling(greenMs, static_cast<int>(lane));

  setPhaseYellow(lane);
  waitWithSampling(YELLOW_MS, -1);

  setAllRed();
  waitWithSampling(ALL_RED_MS, -1);

  const float postDemand = laneDemand[lane];
  updateLocalModel(lane, preDemand, postDemand);
  ++phaseCount;
  printStatus("after_phase", lane, greenMs);

  if (shouldPublishModel()) {
    if (!pushLocalModel()) {
      Serial.println("Model publish failed. Retrying global pull when possible.");
      pullGlobalModel();
    } else {
      pullGlobalModel();
    }
  }

  if (WiFi.status() != WL_CONNECTED && millis() - lastSyncAttemptMs >= SERVER_SYNC_INTERVAL_MS) {
    connectWiFi();
    if (wifiReady) {
      pullGlobalModel();
    }
  }
}

