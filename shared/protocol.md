# Shared Protocol

## Model

The federated model is a compact four-weight vector:

```json
{
  "weights": [1.0, 1.0, 1.0, 1.0]
}
```

Each weight corresponds to one lane of a four-way intersection.

## `POST /update`

Request body:

```json
{
  "node_id": "esp-a",
  "round": 0,
  "weights": [1.12, 0.96, 1.08, 0.84],
  "sample_count": 40,
  "metrics": {
    "cycle_loss": 0.42,
    "phase_count": 8,
    "demand": [0.60, 0.25, 0.50, 0.10]
  }
}
```

Response:

```json
{
  "status": "accepted",
  "current_round": 0,
  "global_weights": [1.0, 1.0, 1.0, 1.0]
}
```

Possible `status` values:

- `accepted`
- `aggregated`
- `stale`

## `GET /get_weights`

Response:

```json
{
  "round": 1,
  "weights": [1.05, 0.98, 1.04, 0.93],
  "updated_at": "2026-03-22T18:05:00Z"
}
```

## Aggregation Rule

The server performs weighted federated averaging:

```text
global = sum(local_weights * sample_count) / sum(sample_count)
```

The sample count acts as the relative contribution of each node.

