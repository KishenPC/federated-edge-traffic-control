# Shared Protocol

Current API notes for communication between the ESP32 nodes and the Flask server.

## `GET /health`

Returns a small server health payload.

Example response:

```json
{
  "status": "ok",
  "time": "2026-03-26T12:00:00+00:00"
}
```

## `GET /status`

Returns the current shared weights, last update time, and latest node payloads known to the server.

## `GET /get_weights`

Example response:

```json
{
  "weights": [1.0, 1.0, 1.0, 1.0],
  "updated_at": "2026-03-26T12:00:00+00:00"
}
```

## `POST /update`

Example request body:

```json
{
  "node_id": "esp-a",
  "weights": [1.0, 1.0, 1.0, 1.0]
}
```

Example response:

```json
{
  "status": "accepted",
  "message": "Server accepted the latest node payload.",
  "weights": [1.0, 1.0, 1.0, 1.0]
}
```
