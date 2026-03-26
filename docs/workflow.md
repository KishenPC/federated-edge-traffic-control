# Federated Edge-AI Workflow

## System Pieces

- 2 ESP32-based intersection nodes
- 1 Flask server running on a laptop
- shared status and weight exchange over local Wi-Fi

## Completed Workflow

1. Each ESP32 reads four lane sensors.
2. The ESP32 drives signal outputs for the active lane.
3. The ESP32 can connect to the local Wi-Fi network.
4. The node fetches the latest shared weights from the server.
5. The node sends its current weight payload back to the server.
6. The Flask server stores the latest known node updates and shared weights.
7. The dashboard reads the server status and shows the current state in the browser.

## Current Focus

- maintain stable ESP32 signal sequencing
- keep node-to-server JSON communication working
- prepare the codebase for richer coordination and analytics logic
