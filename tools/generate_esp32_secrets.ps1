param(
    [string]$EnvPath = ".env",
    [string]$OutputPath = "esp32/FederatedTrafficController/node_secrets.h"
)

$resolvedEnvPath = Join-Path $PSScriptRoot "..\$EnvPath"
$resolvedOutputPath = Join-Path $PSScriptRoot "..\$OutputPath"

if (-not (Test-Path -LiteralPath $resolvedEnvPath)) {
    throw "Could not find env file at $resolvedEnvPath"
}

$pairs = @{}
Get-Content -LiteralPath $resolvedEnvPath | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) {
        return
    }

    $index = $line.IndexOf("=")
    if ($index -lt 1) {
        return
    }

    $key = $line.Substring(0, $index).Trim()
    $value = $line.Substring($index + 1).Trim().Trim('"').Trim("'")
    $pairs[$key] = $value
}

$header = @(
    "#pragma once",
    "",
    "// Generated from the repo .env file. Do not commit local secrets.",
    "#define WIFI_SSID `"$($pairs['WIFI_SSID'])`"",
    "#define WIFI_PASSWORD `"$($pairs['WIFI_PASSWORD'])`"",
    "#define SERVER_BASE_URL `"$($pairs['SERVER_BASE_URL'])`"",
    "#define SENSOR_ACTIVE_LOW $($pairs['SENSOR_ACTIVE_LOW'])",
    "#define SERIAL_BAUD $($pairs['SERIAL_BAUD'])",
    ""
)

$header | Set-Content -LiteralPath $resolvedOutputPath -Encoding ASCII
