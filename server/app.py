from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any

import numpy as np
from flask import Flask, jsonify, render_template, request


# ── Constants ────────────────────────────────────────────────────────────────

LANE_COUNT = 4
DEFAULT_MODEL = np.ones(LANE_COUNT, dtype=float)
MAX_LOG_ENTRIES = 200
MAX_HISTORY_ENTRIES = 100


# ── Utilities ────────────────────────────────────────────────────────────────

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Event Logger ─────────────────────────────────────────────────────────────

class EventLog:
    """Thread-safe in-memory ring buffer for structured events."""

    def __init__(self, maxlen: int = MAX_LOG_ENTRIES) -> None:
        self._entries: deque[dict[str, str]] = deque(maxlen=maxlen)
        self._lock = Lock()

    def _add(self, level: str, message: str) -> None:
        with self._lock:
            self._entries.append({
                "level": level,
                "message": message,
                "time": utc_now_iso(),
            })

    def info(self, msg: str) -> None:
        self._add("info", msg)

    def warning(self, msg: str) -> None:
        self._add("warning", msg)

    def error(self, msg: str) -> None:
        self._add("error", msg)

    def snapshot(self) -> list[dict[str, str]]:
        with self._lock:
            return list(self._entries)


log = EventLog()


# ── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class NodeUpdate:
    node_id: str
    round_id: int
    weights: np.ndarray
    sample_count: int
    metrics: dict[str, Any]
    received_at: str


@dataclass
class HistoryEntry:
    round_id: int
    weights: list[float]
    contributors: list[str]
    time: str


@dataclass
class FederatedState:
    min_clients: int
    global_weights: np.ndarray = field(default_factory=lambda: DEFAULT_MODEL.copy())
    current_round: int = 0
    updated_at: str = field(default_factory=utc_now_iso)
    pending_updates: dict[str, NodeUpdate] = field(default_factory=dict)
    latest_node_metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    history: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=MAX_HISTORY_ENTRIES)
    )
    lock: Lock = field(default_factory=Lock)

    def snapshot(self) -> dict[str, Any]:
        return {
            "round": self.current_round,
            "weights": self.global_weights.tolist(),
            "updated_at": self.updated_at,
            "pending_nodes": list(self.pending_updates.keys()),
            "latest_node_metrics": self.latest_node_metrics,
            "min_clients": self.min_clients,
        }

    def reset(self) -> None:
        self.global_weights = DEFAULT_MODEL.copy()
        self.current_round = 0
        self.updated_at = utc_now_iso()
        self.pending_updates.clear()
        self.latest_node_metrics.clear()
        log.info("Server state reset to defaults.")

    def aggregate(self) -> None:
        updates = list(self.pending_updates.values())
        contributors = [u.node_id for u in updates]
        weights = np.array([u.weights for u in updates], dtype=float)
        sample_counts = np.array(
            [max(1, u.sample_count) for u in updates], dtype=float
        )
        aggregated = np.average(weights, axis=0, weights=sample_counts)
        self.global_weights = aggregated.astype(float)
        self.current_round += 1
        self.updated_at = utc_now_iso()

        # Record history
        self.history.append({
            "round": self.current_round,
            "weights": self.global_weights.tolist(),
            "contributors": contributors,
            "time": self.updated_at,
        })

        self.pending_updates.clear()
        log.info(
            f"FedAvg aggregation completed → round {self.current_round} "
            f"(contributors: {', '.join(contributors)})"
        )


# ── Flask App ────────────────────────────────────────────────────────────────

app = Flask(__name__)
state = FederatedState(min_clients=int(os.getenv("FED_MIN_CLIENTS", "2")))

_boot_time = time.time()

log.info("Federated traffic server started.")


def error_response(message: str, status_code: int):
    log.error(f"[{status_code}] {message}")
    return jsonify({"error": message}), status_code


# ── Dashboard ────────────────────────────────────────────────────────────────

@app.get("/")
def dashboard():
    return render_template("dashboard.html")


# ── API Endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return jsonify({"status": "ok", "time": utc_now_iso()})


@app.get("/get_weights")
def get_weights():
    try:
        with state.lock:
            return jsonify({
                "round": state.current_round,
                "weights": state.global_weights.tolist(),
                "updated_at": state.updated_at,
            })
    except Exception as exc:
        return error_response(f"get_weights failed: {exc}", 500)


@app.get("/status")
def status():
    try:
        with state.lock:
            return jsonify(state.snapshot())
    except Exception as exc:
        return error_response(f"status failed: {exc}", 500)


@app.post("/reset")
def reset():
    try:
        with state.lock:
            state.reset()
            return jsonify({"status": "reset", **state.snapshot()})
    except Exception as exc:
        return error_response(f"reset failed: {exc}", 500)


@app.post("/update")
def update():
    try:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return error_response("Expected a JSON object body.", 400)

        node_id = str(payload.get("node_id", "")).strip()
        if not node_id:
            return error_response("Missing node_id.", 400)

        try:
            round_id = int(payload.get("round"))
        except (TypeError, ValueError):
            return error_response("round must be an integer.", 400)

        raw_weights = payload.get("weights")
        if not isinstance(raw_weights, list) or len(raw_weights) != LANE_COUNT:
            return error_response(
                f"weights must be a list of {LANE_COUNT} numeric values.", 400
            )

        try:
            weights = np.array(
                [float(value) for value in raw_weights], dtype=float
            )
        except (TypeError, ValueError):
            return error_response("weights contains a non-numeric value.", 400)

        try:
            sample_count = int(payload.get("sample_count", 1))
        except (TypeError, ValueError):
            return error_response("sample_count must be an integer.", 400)

        metrics = payload.get("metrics", {})
        if not isinstance(metrics, dict):
            return error_response("metrics must be a JSON object.", 400)

        with state.lock:
            state.latest_node_metrics[node_id] = {
                **metrics,
                "round": round_id,
                "received_at": utc_now_iso(),
            }

            if round_id != state.current_round:
                log.warning(
                    f"Stale update from {node_id}: sent round {round_id}, "
                    f"current is {state.current_round}."
                )
                return (
                    jsonify({
                        "status": "stale",
                        "message": "Node model is behind the current federated round.",
                        "current_round": state.current_round,
                        "global_weights": state.global_weights.tolist(),
                    }),
                    409,
                )

            state.pending_updates[node_id] = NodeUpdate(
                node_id=node_id,
                round_id=round_id,
                weights=weights,
                sample_count=max(1, sample_count),
                metrics=metrics,
                received_at=utc_now_iso(),
            )

            log.info(
                f"Accepted update from {node_id} "
                f"(round={round_id}, samples={sample_count})."
            )

            if len(state.pending_updates) >= state.min_clients:
                state.aggregate()
                return jsonify({
                    "status": "aggregated",
                    "current_round": state.current_round,
                    "global_weights": state.global_weights.tolist(),
                })

            return jsonify({
                "status": "accepted",
                "current_round": state.current_round,
                "global_weights": state.global_weights.tolist(),
            })

    except Exception as exc:
        return error_response(f"update failed: {exc}", 500)


# ── New Dashboard API Endpoints ──────────────────────────────────────────────

@app.get("/api/errors")
def api_errors():
    return jsonify(log.snapshot())


@app.get("/api/history")
def api_history():
    with state.lock:
        return jsonify(list(state.history))


@app.get("/api/test")
def api_test():
    """Run automated self-tests and return structured results."""
    checks: list[dict[str, Any]] = []

    # 1. Server health
    try:
        with app.test_client() as client:
            r = client.get("/health")
            data = r.get_json()
            ok = r.status_code == 200 and data.get("status") == "ok"
            checks.append({
                "name": "Server Health",
                "passed": ok,
                "detail": f"status={data.get('status')}" if ok else f"HTTP {r.status_code}",
            })
    except Exception as exc:
        checks.append({"name": "Server Health", "passed": False, "detail": str(exc)})

    # 2. Model integrity
    try:
        w = state.global_weights
        finite = bool(np.all(np.isfinite(w)))
        positive = bool(np.all(w > 0))
        correct_len = len(w) == LANE_COUNT
        ok = finite and positive and correct_len
        detail_parts = []
        if not finite:
            detail_parts.append("non-finite values")
        if not positive:
            detail_parts.append("non-positive values")
        if not correct_len:
            detail_parts.append(f"length={len(w)} expected {LANE_COUNT}")
        checks.append({
            "name": "Model Integrity",
            "passed": ok,
            "detail": "weights OK" if ok else "; ".join(detail_parts),
        })
    except Exception as exc:
        checks.append({"name": "Model Integrity", "passed": False, "detail": str(exc)})

    # 3. FedAvg correctness
    try:
        w_a = np.array([1.2, 0.8, 1.1, 0.9])
        w_b = np.array([0.9, 1.1, 0.95, 1.05])
        s_a, s_b = 30, 20
        expected = np.average([w_a, w_b], axis=0, weights=[s_a, s_b])
        # Simulate via temp state
        from copy import deepcopy
        tmp = FederatedState(min_clients=2)
        tmp.pending_updates["test-a"] = NodeUpdate("test-a", 0, w_a, s_a, {}, utc_now_iso())
        tmp.pending_updates["test-b"] = NodeUpdate("test-b", 0, w_b, s_b, {}, utc_now_iso())
        tmp.aggregate()
        diff = float(np.max(np.abs(tmp.global_weights - expected)))
        ok = diff < 1e-6
        checks.append({
            "name": "FedAvg Correctness",
            "passed": ok,
            "detail": f"max_diff={diff:.2e}" if ok else f"max_diff={diff:.4f} — MISMATCH",
        })
    except Exception as exc:
        checks.append({"name": "FedAvg Correctness", "passed": False, "detail": str(exc)})

    # 4. Round counter consistency
    try:
        with state.lock:
            r = state.current_round
            ok = isinstance(r, int) and r >= 0
            checks.append({
                "name": "Round Counter",
                "passed": ok,
                "detail": f"current_round={r}",
            })
    except Exception as exc:
        checks.append({"name": "Round Counter", "passed": False, "detail": str(exc)})

    # 5. GET /get_weights endpoint validation
    try:
        with app.test_client() as client:
            r = client.get("/get_weights")
            data = r.get_json()
            ok = (
                r.status_code == 200
                and isinstance(data.get("weights"), list)
                and len(data["weights"]) == LANE_COUNT
            )
            checks.append({
                "name": "GET /get_weights",
                "passed": ok,
                "detail": f"returned {len(data.get('weights', []))} weights" if ok else f"HTTP {r.status_code}",
            })
    except Exception as exc:
        checks.append({"name": "GET /get_weights", "passed": False, "detail": str(exc)})

    # 6. GET /status endpoint validation
    try:
        with app.test_client() as client:
            r = client.get("/status")
            data = r.get_json()
            ok = r.status_code == 200 and "round" in data and "weights" in data
            checks.append({
                "name": "GET /status",
                "passed": ok,
                "detail": "all fields present" if ok else f"HTTP {r.status_code}",
            })
    except Exception as exc:
        checks.append({"name": "GET /status", "passed": False, "detail": str(exc)})

    # 7. POST /update validation — bad payload
    try:
        with app.test_client() as client:
            r = client.post("/update", json={"bad": "payload"})
            ok = r.status_code == 400
            checks.append({
                "name": "Error Handling (bad payload)",
                "passed": ok,
                "detail": "correctly rejected" if ok else f"HTTP {r.status_code} (expected 400)",
            })
    except Exception as exc:
        checks.append({"name": "Error Handling (bad payload)", "passed": False, "detail": str(exc)})

    # 8. Uptime
    try:
        uptime_s = time.time() - _boot_time
        ok = uptime_s > 0
        if uptime_s < 60:
            detail = f"{uptime_s:.0f}s"
        elif uptime_s < 3600:
            detail = f"{uptime_s / 60:.1f}m"
        else:
            detail = f"{uptime_s / 3600:.1f}h"
        checks.append({
            "name": "Server Uptime",
            "passed": ok,
            "detail": detail,
        })
    except Exception as exc:
        checks.append({"name": "Server Uptime", "passed": False, "detail": str(exc)})

    return jsonify({
        "passed": passed,
        "total": total,
        "checks": checks,
        "run_at": utc_now_iso(),
    })


# ── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)
