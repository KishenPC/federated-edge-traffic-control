# Federated Edge-AI Workflow

## 1. System Roles

### Edge Node A

- ESP32 `esp`
- reads `ir1` to `ir4`
- controls `led1` to `led12`
- trains a tiny local model from its own traffic state

### Edge Node B

- ESP32 `esp1`
- reads `ir5` to `ir8`
- controls `led13` to `led24`
- trains a tiny local model from its own traffic state

### Federated Server

- laptop running Flask
- receives local model updates from both nodes
- runs federated averaging
- publishes the latest global model

## 2. Local Edge Workflow

Each ESP32 repeats this loop:

1. Read the four lane sensors.
2. Convert sensor activity into a local demand estimate for each lane.
3. Compute a lane priority score using local model weights.
4. Select the next lane to serve.
5. Apply hard traffic rules:
   - minimum green
   - maximum green
   - yellow transition
   - all-red clearance
   - anti-starvation boost
6. Drive the LEDs for the selected phase.
7. Measure the post-phase residual demand.
8. Update local weights based on how well the phase reduced congestion.

This means every node performs local inference and local learning on-device.

## 3. Federated Workflow

After the node completes a learning window:

1. The ESP32 serializes its local model weights to JSON.
2. The ESP32 sends the update to the laptop using HTTP `POST /update`.
3. The laptop stores one update per node for the current round.
4. When updates from both nodes arrive, the laptop runs `FedAvg`.
5. The laptop increments the global round number.
6. Each ESP32 fetches the latest model using `GET /get_weights`.
7. The ESP32 replaces its local weights with the global model.
8. The node continues running locally using the updated model.

## 4. Why This Is Federated Edge AI

This workflow satisfies the original federated edge-AI requirement because:

- raw local sensing stays at the intersection
- local learning happens on the ESP32
- only model weights and summary metrics are shared
- the laptop acts as an aggregator, not the live controller

## 5. Local Model Used In This Prototype

The local model is intentionally lightweight:

```text
priority[i] = weight[i] * demand[i] + starvationBoost[i]
greenTime[i] = clamp(baseGreen + gain * priority[i], minGreen, maxGreen)
```

Local update rule:

- if a served lane still has high residual demand after green, its weight increases
- all weights are re-normalized so the model stays bounded and stable

This is simple enough for ESP32-class hardware while still being a real local learning loop.

## 6. Safety Boundary

The AI model never directly bypasses safety constraints.

Hardcoded safety on each ESP32:

- `MIN_GREEN_MS`
- `MAX_GREEN_MS`
- `YELLOW_MS`
- `ALL_RED_MS`
- fallback standalone timing if Wi-Fi/server fails

That makes the prototype both more credible and easier to defend in a technical report.

