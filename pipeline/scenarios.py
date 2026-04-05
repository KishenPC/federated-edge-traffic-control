"""
scenarios.py
Generates deterministic traffic scenario files for the experiment pipeline.
Each scenario is a JSON file: list of ticks, each tick = [lane0, lane1, lane2, lane3]
where each value is 0 (idle) or 1 (vehicle present), replayed at TICK_RATE_HZ.

Usage:
    python scenarios.py          # generates all three scenario files
"""

import json
import random
import os

TICK_RATE_HZ = 2          # sensor readings per second
DURATION_SECONDS = 300    # 5-minute run (change to match your demo duration)
TICKS = DURATION_SECONDS * TICK_RATE_HZ
LANES = 4

SCENARIOS = {
    "light": {
        "description": "Low demand — ~25% lane occupancy across all lanes",
        "seed": 42,
        # Per-lane probability that sensor reads 1 (vehicle present) at any tick
        "lane_probs": [0.25, 0.22, 0.28, 0.20],
    },
    "medium": {
        "description": "Moderate demand — ~55% occupancy, roughly uniform",
        "seed": 43,
        "lane_probs": [0.55, 0.50, 0.60, 0.52],
    },
    "skewed_heavy": {
        "description": "Heavy + skewed — lanes 0 and 1 saturated, lanes 2 and 3 light",
        "seed": 44,
        "lane_probs": [0.90, 0.85, 0.20, 0.15],
    },
}

def generate_scenario(name: str, cfg: dict) -> list:
    rng = random.Random(cfg["seed"])
    ticks = []
    for _ in range(TICKS):
        tick = [1 if rng.random() < p else 0 for p in cfg["lane_probs"]]
        ticks.append(tick)
    return ticks

def main():
    os.makedirs("scenarios", exist_ok=True)
    for name, cfg in SCENARIOS.items():
        ticks = generate_scenario(name, cfg)
        out = {
            "name": name,
            "description": cfg["description"],
            "seed": cfg["seed"],
            "tick_rate_hz": TICK_RATE_HZ,
            "duration_seconds": DURATION_SECONDS,
            "ticks": ticks,
        }
        path = f"scenarios/{name}.json"
        with open(path, "w") as f:
            json.dump(out, f)
        actual_occ = [
            round(sum(t[i] for t in ticks) / len(ticks) * 100, 1)
            for i in range(LANES)
        ]
        print(f"[{name}] written to {path} | actual occupancy per lane: {actual_occ}%")

if __name__ == "__main__":
    main()
