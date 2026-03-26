from __future__ import annotations

from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request


LANE_COUNT = 4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


app = Flask(__name__)

state: dict[str, object] = {
    "weights": [1.0] * LANE_COUNT,
    "updated_at": utc_now_iso(),
    "latest_nodes": {},
}


@app.get("/")
def dashboard():
    return render_template("dashboard.html")


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "time": utc_now_iso(),
    })


@app.get("/status")
def status():
    return jsonify(state)


@app.get("/get_weights")
def get_weights():
    return jsonify({
        "weights": state["weights"],
        "updated_at": state["updated_at"],
    })


@app.post("/update")
def update():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Expected a JSON object body."}), 400

    node_id = str(payload.get("node_id", "")).strip()
    raw_weights = payload.get("weights")

    if not node_id:
        return jsonify({"error": "Missing node_id."}), 400

    if not isinstance(raw_weights, list) or len(raw_weights) != LANE_COUNT:
        return jsonify({"error": f"weights must contain {LANE_COUNT} values."}), 400

    try:
        weights = [float(value) for value in raw_weights]
    except (TypeError, ValueError):
        return jsonify({"error": "weights contains a non-numeric value."}), 400

    latest_nodes = state["latest_nodes"]
    assert isinstance(latest_nodes, dict)
    latest_nodes[node_id] = {
        "weights": weights,
        "received_at": utc_now_iso(),
    }

    state["weights"] = weights
    state["updated_at"] = utc_now_iso()

    return jsonify({
        "status": "accepted",
        "message": "Server accepted the latest node payload.",
        "weights": state["weights"],
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
