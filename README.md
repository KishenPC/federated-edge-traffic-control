# Federated Edge-AI Traffic Signal Control

This project is an ESP32 + Flask prototype for traffic signal coordination with a lightweight shared model workflow.

## Completed So Far

- set up the overall project structure for firmware, server, shared protocol notes, and workflow documentation
- built a Flask server with `GET /health`, `GET /status`, `GET /get_weights`, and `POST /update`
- added a browser dashboard that shows the current server state
- created ESP32 firmware that:
  - reads four lane sensor inputs
  - drives four traffic lanes with green, yellow, and red outputs
  - connects to Wi-Fi
  - fetches shared weights from the server
  - posts node updates back to the server
- defined a basic JSON payload shape for node-to-server communication

## Current Layout

- [`server/app.py`](/c:/Users/Kishen/Desktop/Stuff/MPMC%20Project/server/app.py): Flask server and API endpoints
- [`server/templates/dashboard.html`](/c:/Users/Kishen/Desktop/Stuff/MPMC%20Project/server/templates/dashboard.html): browser dashboard
- [`server/static/dashboard.js`](/c:/Users/Kishen/Desktop/Stuff/MPMC%20Project/server/static/dashboard.js): dashboard client logic
- [`server/static/style.css`](/c:/Users/Kishen/Desktop/Stuff/MPMC%20Project/server/static/style.css): dashboard styling
- [`esp32/FederatedTrafficController/FederatedTrafficController.ino`](/c:/Users/Kishen/Desktop/Stuff/MPMC%20Project/esp32/FederatedTrafficController/FederatedTrafficController.ino): ESP32 traffic controller firmware
- [`esp32/FederatedTrafficController/node_config.h`](/c:/Users/Kishen/Desktop/Stuff/MPMC%20Project/esp32/FederatedTrafficController/node_config.h): Wi-Fi and node configuration
- [`shared/protocol.md`](/c:/Users/Kishen/Desktop/Stuff/MPMC%20Project/shared/protocol.md): API payload notes
- [`docs/workflow.md`](/c:/Users/Kishen/Desktop/Stuff/MPMC%20Project/docs/workflow.md): workflow summary

## Current Behavior

- the server stores a shared four-value weight vector
- the dashboard loads and displays live status from `/status`
- the ESP32 cycles through lane phases and can exchange weight data with the server over Wi-Fi

## Next Development Steps

- improve the lane-selection logic
- strengthen request validation and testing
- expand the dashboard with more system insights
- refine the node update and aggregation flow
