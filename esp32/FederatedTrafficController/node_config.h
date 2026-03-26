#pragma once

// Update these credentials before uploading to hardware.
#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define SERVER_BASE_URL "http://192.168.1.10:5000"

// Compile with 0 for the first ESP32 and 1 for the second ESP32.
#define NODE_PROFILE_INDEX 0

// Most IR obstacle sensors are active LOW.
#define SENSOR_ACTIVE_LOW true

// Serial logs are useful during bring-up.
#define SERIAL_BAUD 115200

