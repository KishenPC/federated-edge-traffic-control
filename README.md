# Federated Edge-AI Traffic Signal Control

This project implements a two-node federated edge-AI traffic controller using:

- `2x ESP32` intersections
- `4x sensors` per intersection
- `4x signal heads` per intersection
- `1x Flask` aggregation server on a laptop

Each ESP32:

- reads local lane sensors
- computes lane demand locally
- runs a tiny local traffic model
- updates its own weights on-device
- controls LEDs with hard safety limits
- sends only model weights and summary metrics to the laptop

The laptop:

- receives local model updates
- performs federated averaging (`FedAvg`)
- returns a shared global model to both intersections

## Project Layout

- [`docs/workflow.md`](/c:/Users/Kishen/Desktop/Stuff/MPMC%20Project/docs/workflow.md): report-ready workflow and architecture
- [`shared/protocol.md`](/c:/Users/Kishen/Desktop/Stuff/MPMC%20Project/shared/protocol.md): JSON contract and model definition
- [`server/app.py`](/c:/Users/Kishen/Desktop/Stuff/MPMC%20Project/server/app.py): Flask federated aggregation server
- [`server/requirements.txt`](/c:/Users/Kishen/Desktop/Stuff/MPMC%20Project/server/requirements.txt): Python dependencies
- [`esp32/FederatedTrafficController/FederatedTrafficController.ino`](/c:/Users/Kishen/Desktop/Stuff/MPMC%20Project/esp32/FederatedTrafficController/FederatedTrafficController.ino): ESP32 firmware
- [`esp32/FederatedTrafficController/node_config.h`](/c:/Users/Kishen/Desktop/Stuff/MPMC%20Project/esp32/FederatedTrafficController/node_config.h): per-node Wi-Fi and upload configuration

## Your Current Wiring Map

Both ESP32 boards use the same pin scheme:

- Sensors:
  - `GPIO34`
  - `GPIO35`
  - `GPIO32`
  - `GPIO33`
- Signal heads:
  - Lane 1: `G=21`, `Y=22`, `R=23`
  - Lane 2: `G=5`, `Y=18`, `R=19`
  - Lane 3: `G=4`, `Y=16`, `R=17`
  - Lane 4: `G=27`, `Y=26`, `R=25`

## How To Run

### 1. Start the federated server

```powershell
cd server
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

By default the server listens on `0.0.0.0:5000`.

### 2. Configure local environment values

Edit [`.env`](/c:/Users/Kishen/Desktop/Stuff/MPMC%20Project/.env) with:

- your Wi-Fi SSID/password
- your laptop IP in `SERVER_BASE_URL`
- any Flask overrides such as `FLASK_PORT` or `FED_MIN_CLIENTS`

Generate the ESP32 local secrets header from the same `.env` file:

```powershell
powershell -ExecutionPolicy Bypass -File tools\generate_esp32_secrets.ps1
```

### 3. Configure and upload each ESP32

Edit [`esp32/FederatedTrafficController/node_config.h`](/c:/Users/Kishen/Desktop/Stuff/MPMC%20Project/esp32/FederatedTrafficController/node_config.h):

- compile once with `NODE_PROFILE_INDEX 0` for ESP32 A
- compile again with `NODE_PROFILE_INDEX 1` for ESP32 B

### 4. Observe the federated loop

- ESP32 nodes boot and fetch the current global model
- each node controls its own intersection locally
- nodes update weights after each phase cycle
- nodes post updates to the laptop
- the server aggregates weights after updates from both nodes
- both nodes pull the new shared model

## Design Notes

- The local model is intentionally tiny so it can run fully on the ESP32.
- Safety rules remain local and hardcoded on the edge node.
- The system still functions if the server is temporarily unavailable.
- This is a valid federated edge-AI prototype because learning happens on the ESP32s, not only on the laptop.
