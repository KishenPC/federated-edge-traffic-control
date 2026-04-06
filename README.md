# Federated Edge-AI Traffic Signal Control

This project implements a two-node federated edge-AI traffic controller with:

- 2 ESP32 intersections
- 4 lane sensors per intersection
- 4 signal lanes per intersection (R/Y/G each)
- 1 Flask aggregation server on a laptop

Each ESP32 performs local sensing, demand estimation, lane selection, and local model updates. Only model weights and summary metrics are sent to the server. The Flask server performs weighted federated averaging (FedAvg) and shares a global model back to both nodes.

## Repository Layout

- [README.md](README.md): setup and operation guide
- [docs/workflow.md](docs/workflow.md): architecture and workflow narrative
- [shared/protocol.md](shared/protocol.md): API payload contract and model format
- [server/app.py](server/app.py): Flask aggregation backend and dashboard APIs
- [server/requirements.txt](server/requirements.txt): Python dependencies
- [server/templates/dashboard.html](server/templates/dashboard.html): dashboard markup
- [server/static/style.css](server/static/style.css): dashboard styling
- [server/static/dashboard.js](server/static/dashboard.js): dashboard polling/render logic
- [esp32/FederatedTrafficController/FederatedTrafficController.ino](esp32/FederatedTrafficController/FederatedTrafficController.ino): ESP32 firmware
- [esp32/FederatedTrafficController/node_config.h](esp32/FederatedTrafficController/node_config.h): compile-time node profile and defaults
- [esp32/FederatedTrafficController/node_secrets.h](esp32/FederatedTrafficController/node_secrets.h): generated local secrets header
- [tools/generate_esp32_secrets.ps1](tools/generate_esp32_secrets.ps1): .env to node_secrets.h generator

## Prerequisites

- Python 3.10+ on the machine running the Flask server
- Arduino IDE (or PlatformIO) with ESP32 board support installed
- ArduinoJson library available for ESP32 build
- Two ESP32 boards on the same Wi-Fi network as the server
- 4 digital vehicle sensors per node and lane LEDs/signals wired to GPIO

## Pin Mapping

Both ESP32 boards use the same pins:

- Sensors:
  - GPIO34
  - GPIO35
  - GPIO32
  - GPIO33
- Signals:
  - Lane 1: G=21, Y=22, R=23
  - Lane 2: G=5, Y=18, R=19
  - Lane 3: G=4, Y=16, R=17
  - Lane 4: G=27, Y=26, R=25

## Getting Started

### First-Time Setup Procedure

Follow this once from a fresh machine/workspace.

1. Open this project in a terminal at repository root.
2. Create your local environment file.

```powershell
Copy-Item .env.example .env
```

3. Edit [.env](.env) and set:
  - WIFI_SSID
  - WIFI_PASSWORD
  - SERVER_BASE_URL (must be reachable by ESP32 over Wi-Fi)
  - optional: FLASK_HOST, FLASK_PORT, FLASK_DEBUG, FED_MIN_CLIENTS
4. Install backend dependencies and start the server.

```powershell
cd server
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

5. Confirm the server is live by opening http://localhost:5000/health in your browser.
6. In a second terminal at repository root, generate ESP32 secrets from your .env values.

```powershell
powershell -ExecutionPolicy Bypass -File tools\generate_esp32_secrets.ps1
```

7. Edit [esp32/FederatedTrafficController/node_config.h](esp32/FederatedTrafficController/node_config.h):
  - set NODE_PROFILE_INDEX to 0 and upload firmware to node esp-a
  - set NODE_PROFILE_INDEX to 1 and upload firmware to node esp-b
8. Open the dashboard and verify both nodes become online and rounds increase:
  - http://localhost:5000
  - or http://<server-ip>:5000

Default server binding is 0.0.0.0:5000 unless overridden in [.env](.env).
Generated secrets are written to [esp32/FederatedTrafficController/node_secrets.h](esp32/FederatedTrafficController/node_secrets.h).

If nodes do not appear online, go to the Troubleshooting section below.

### Quick Start (Returning Users)

If your environment is already set up:

1. Start the backend server.

```powershell
cd server
.venv\Scripts\activate
python app.py
```

2. Regenerate [esp32/FederatedTrafficController/node_secrets.h](esp32/FederatedTrafficController/node_secrets.h) only when [.env](.env) changes.
3. Rebuild/reupload ESP32 firmware only when firmware or node config changes.
4. Open http://localhost:5000 and verify node status.

## Configuration Reference

Values are read from [.env](.env) by [server/app.py](server/app.py), and secrets can be propagated to firmware via [tools/generate_esp32_secrets.ps1](tools/generate_esp32_secrets.ps1).

| Key | Purpose | Default |
| --- | --- | --- |
| FLASK_HOST | Flask bind host | 0.0.0.0 |
| FLASK_PORT | Flask port | 5000 |
| FLASK_DEBUG | Flask debug mode (1/0) | 0 |
| FED_MIN_CLIENTS | Required updates before aggregation | 2 |
| WIFI_SSID | Node Wi-Fi SSID | YOUR_WIFI_SSID |
| WIFI_PASSWORD | Node Wi-Fi password | YOUR_WIFI_PASSWORD |
| SERVER_BASE_URL | Base URL used by ESP32 HTTP client | http://192.168.1.10:5000 |
| SENSOR_ACTIVE_LOW | Sensor polarity (true/false) | true |
| SERIAL_BAUD | ESP32 serial monitor baud rate | 115200 |

## Runtime Behavior

Local edge loop on each ESP32:

1. Read lane sensors and smooth demand values.
2. Compute lane priority from local weights + starvation boost.
3. Select next lane and compute bounded green time.
4. Enforce safety timings: min/max green, yellow, all-red.
5. Update local model weights.
6. Periodically push local model to server.

Federated loop on Flask server:

1. Accept local updates for current round.
2. Wait for minimum client count.
3. Aggregate with weighted FedAvg using sample_count.
4. Increment round and publish new global weights.

## API Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /health | Liveness check |
| GET | /get_weights | Fetch current global model and round |
| GET | /status | Full runtime snapshot for dashboard |
| POST | /update | Submit node update for current round |
| POST | /reset | Reset server state to defaults |
| GET | /api/errors | Fetch in-memory event log |
| GET | /api/history | Fetch aggregation history |
| GET | /api/test | Run backend self-checks and return pass/fail results |

Update response status values:

- accepted: update stored, waiting for more clients
- aggregated: update triggered federated aggregation
- stale: update round is behind current server round (HTTP 409)

Detailed payloads are documented in [shared/protocol.md](shared/protocol.md).

## Dashboard Features

- Global model card (round, last update, pending clients, global weights)
- Per-node status cards (online/stale/offline, demand bars, metrics)
- Aggregation history table
- Event log with level filters
- System test panel (depends on /api/test endpoint)

## Safety and Failover Notes

- Safety timing is enforced on ESP32 and does not depend on the server.
- If Wi-Fi/server is unavailable, nodes continue standalone local control.
- Raw sensor streams are kept local; only model weights + summary metrics are transmitted.

## Troubleshooting

- Dashboard shows server Offline:
  - confirm Flask is running on expected host/port
  - verify firewall allows incoming connections on FLASK_PORT
- Node never updates:
  - verify SERVER_BASE_URL points to reachable server IP from ESP32 network
  - verify Wi-Fi credentials in .env and regenerated node_secrets.h
- Frequent stale responses from /update:
  - node is sending an older round; force node to pull global weights
- Wrong vehicle detection behavior:
  - check SENSOR_ACTIVE_LOW setting and sensor wiring
- ESP32 compile cannot find secrets:
  - ensure node_secrets.h exists and is generated by tools/generate_esp32_secrets.ps1

## Project Notes

- [.env](.env) and [esp32/FederatedTrafficController/node_secrets.h](esp32/FederatedTrafficController/node_secrets.h) are git-ignored for safety.
