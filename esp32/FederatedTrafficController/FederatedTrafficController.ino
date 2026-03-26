#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

#include "node_config.h"

namespace {

constexpr size_t kLaneCount = 4;
constexpr uint8_t SENSOR_PINS[kLaneCount] = {34, 35, 32, 33};

struct LanePins {
  uint8_t green;
  uint8_t yellow;
  uint8_t red;
};

constexpr LanePins SIGNAL_PINS[kLaneCount] = {
  {21, 22, 23},
  {5, 18, 19},
  {4, 16, 17},
  {27, 26, 25},
};

const char* NODE_IDS[] = {"esp-a", "esp-b"};

constexpr uint32_t GREEN_MS = 5000;
constexpr uint32_t YELLOW_MS = 1500;
constexpr uint32_t ALL_RED_MS = 1000;

size_t activeLane = 0;
float sharedWeights[kLaneCount] = {1.0f, 1.0f, 1.0f, 1.0f};

bool readSensorActive(size_t lane) {
  const int level = digitalRead(SENSOR_PINS[lane]);
  return SENSOR_ACTIVE_LOW ? level == LOW : level == HIGH;
}

void setAllRed() {
  for (const auto& pins : SIGNAL_PINS) {
    digitalWrite(pins.green, LOW);
    digitalWrite(pins.yellow, LOW);
    digitalWrite(pins.red, HIGH);
  }
}

void setLaneGreen(size_t lane) {
  for (size_t i = 0; i < kLaneCount; ++i) {
    const bool isActive = i == lane;
    digitalWrite(SIGNAL_PINS[i].green, isActive ? HIGH : LOW);
    digitalWrite(SIGNAL_PINS[i].yellow, LOW);
    digitalWrite(SIGNAL_PINS[i].red, isActive ? LOW : HIGH);
  }
}

void setLaneYellow(size_t lane) {
  for (size_t i = 0; i < kLaneCount; ++i) {
    const bool isActive = i == lane;
    digitalWrite(SIGNAL_PINS[i].green, LOW);
    digitalWrite(SIGNAL_PINS[i].yellow, isActive ? HIGH : LOW);
    digitalWrite(SIGNAL_PINS[i].red, isActive ? LOW : HIGH);
  }
}

void initializePins() {
  for (size_t lane = 0; lane < kLaneCount; ++lane) {
    pinMode(SENSOR_PINS[lane], INPUT);
    pinMode(SIGNAL_PINS[lane].green, OUTPUT);
    pinMode(SIGNAL_PINS[lane].yellow, OUTPUT);
    pinMode(SIGNAL_PINS[lane].red, OUTPUT);
  }
  setAllRed();
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting to Wi-Fi");
  for (int i = 0; i < 20 && WiFi.status() != WL_CONNECTED; ++i) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("Wi-Fi ready. IP=%s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("Wi-Fi not ready. Continuing with offline placeholder behavior.");
  }
}

void fetchWeightsIfAvailable() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  HTTPClient http;
  http.begin(String(SERVER_BASE_URL) + "/get_weights");
  const int responseCode = http.GET();
  if (responseCode != HTTP_CODE_OK) {
    http.end();
    return;
  }

  DynamicJsonDocument doc(256);
  const auto error = deserializeJson(doc, http.getString());
  http.end();
  if (error || !doc["weights"].is<JsonArray>()) {
    return;
  }

  const JsonArray weights = doc["weights"].as<JsonArray>();
  if (weights.size() != kLaneCount) {
    return;
  }

  for (size_t lane = 0; lane < kLaneCount; ++lane) {
    sharedWeights[lane] = weights[lane].as<float>();
  }
}

void postPlaceholderUpdate() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  DynamicJsonDocument payload(256);
  payload["node_id"] = NODE_IDS[NODE_PROFILE_INDEX];
  JsonArray weights = payload.createNestedArray("weights");
  for (float weight : sharedWeights) {
    weights.add(weight);
  }

  String body;
  serializeJson(payload, body);

  HTTPClient http;
  http.begin(String(SERVER_BASE_URL) + "/update");
  http.addHeader("Content-Type", "application/json");
  http.POST(body);
  http.end();
}

void runSimpleCycle() {
  const bool sensorTriggered = readSensorActive(activeLane);
  Serial.printf(
    "lane=%u sensor=%s weight=%.2f\n",
    static_cast<unsigned>(activeLane + 1),
    sensorTriggered ? "active" : "idle",
    sharedWeights[activeLane]
  );

  setLaneGreen(activeLane);
  delay(GREEN_MS);

  setLaneYellow(activeLane);
  delay(YELLOW_MS);

  setAllRed();
  delay(ALL_RED_MS);

  activeLane = (activeLane + 1) % kLaneCount;
}

}  // namespace

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(1000);
  Serial.println("Booting federated traffic controller firmware.");

  initializePins();
  connectWiFi();
  fetchWeightsIfAvailable();
}

void loop() {
  runSimpleCycle();

  // Current behavior: refresh the latest shared weights and publish node state.
  fetchWeightsIfAvailable();
  postPlaceholderUpdate();
}
