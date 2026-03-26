#pragma once

// Local secrets can be generated from the repo .env file into node_secrets.h.
#if __has_include("node_secrets.h")
#include "node_secrets.h"
#endif

#ifndef WIFI_SSID
#define WIFI_SSID "YOUR_WIFI_SSID"
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#endif

#ifndef SERVER_BASE_URL
#define SERVER_BASE_URL "http://192.168.1.10:5000"
#endif

// Compile with 0 for the first ESP32 and 1 for the second ESP32.
#define NODE_PROFILE_INDEX 0

// Most IR obstacle sensors are active LOW.
#ifndef SENSOR_ACTIVE_LOW
#define SENSOR_ACTIVE_LOW true
#endif

// Serial logs are useful during bring-up.
#ifndef SERIAL_BAUD
#define SERIAL_BAUD 115200
#endif
