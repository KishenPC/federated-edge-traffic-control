"""
simulate.py
Runs a single (scenario, mode) experiment and appends results to results/raw.csv.

Modes:
  fixed      — fixed green times, no learning (baseline)
  local      — local weight adaptation only, no federated averaging
  federated  — local adaptation + FedAvg weight sync every FEDAVG_INTERVAL ticks

Usage:
    python simulate.py --scenario light   --mode fixed
    python simulate.py --scenario light   --mode local
    python simulate.py --scenario light   --mode federated
    # Or run all combinations at once:
    python simulate.py --all
"""

import argparse
import csv
import json
import os
import copy
import time
from pathlib import Path

# ── Timing constants (match your ESP32 prototype exactly) ────────────────────
MIN_GREEN_MS  = 5_000
MAX_GREEN_MS  = 20_000
YELLOW_MS     = 2_000
ALL_RED_MS    = 1_000
BASE_GREEN_MS = 10_000

# ── Learning constants ───────────────────────────────────────────────────────
ALPHA          = 0.3    # demand smoothing (EMA)
GAIN           = 2.0    # priority → green time gain
STARVATION_MAX = 5      # ticks before starvation boost kicks in
STARVATION_W   = 1.5    # starvation boost weight
LEARN_RATE     = 0.05   # weight update step per cycle
FEDAVG_INTERVAL= 20     # ticks between federated averaging rounds

LANES = 4
SCENARIOS_DIR = Path("scenarios")
RESULTS_DIR   = Path("results")


# ── Controller classes ───────────────────────────────────────────────────────

class TrafficController:
    """Base controller — shared sensor/demand logic."""

    def __init__(self, mode: str, weights=None):
        self.mode = mode
        self.weights = weights if weights else [1.0] * LANES
        self.demand  = [0.0] * LANES
        self.starvation = [0] * LANES      # ticks since last green
        self.current_green_lane = 0
        self.metrics = []

    def update_demand(self, sensor: list):
        for i in range(LANES):
            self.demand[i] = ALPHA * self.demand[i] + (1 - ALPHA) * sensor[i]

    def compute_priority(self):
        priorities = []
        for i in range(LANES):
            boost = STARVATION_W * max(0, self.starvation[i] - STARVATION_MAX)
            p = self.weights[i] * self.demand[i] + boost
            priorities.append(p)
        return priorities

    def select_lane(self, priorities):
        return priorities.index(max(priorities))

    def compute_green_time(self, priority):
        gt = BASE_GREEN_MS + GAIN * 1000 * priority
        return max(MIN_GREEN_MS, min(MAX_GREEN_MS, gt))

    def step(self, tick: int, sensor: list) -> dict:
        self.update_demand(sensor)

        if self.mode == "fixed":
            selected = tick % LANES       # round-robin fixed
            green_ms  = BASE_GREEN_MS
        else:
            priorities = self.compute_priority()
            selected   = self.select_lane(priorities)
            green_ms   = self.compute_green_time(priorities[selected])
            self._update_weights(selected)

        # Update starvation counters
        for i in range(LANES):
            if i == selected:
                self.starvation[i] = 0
            else:
                self.starvation[i] += 1

        # Effective wait = sum of green+yellow+all-red for non-selected lanes
        # (simplified: each non-selected lane waits the full phase length)
        phase_ms  = green_ms + YELLOW_MS + ALL_RED_MS
        wait_ms   = {i: phase_ms if i != selected else 0 for i in range(LANES)}
        starvation_event = any(s > STARVATION_MAX for s in self.starvation)
        util_pct  = (green_ms / MAX_GREEN_MS) * 100

        m = {
            "tick": tick,
            "selected_lane": selected,
            "green_ms": green_ms,
            "avg_wait_ms": sum(wait_ms.values()) / LANES,
            "starvation_event": int(starvation_event),
            "utilisation_pct": round(util_pct, 2),
            "weights": copy.copy(self.weights),
        }
        self.metrics.append(m)
        self.current_green_lane = selected
        return m

    def _update_weights(self, selected: int):
        # Reward selected lane weight, decay others slightly
        for i in range(LANES):
            if i == selected:
                self.weights[i] = min(2.0, self.weights[i] + LEARN_RATE * self.demand[i])
            else:
                self.weights[i] = max(0.1, self.weights[i] - LEARN_RATE * 0.1)


class FederatedController(TrafficController):
    """Two-node federated controller: simulates Node A and Node B sharing weights."""

    def __init__(self):
        super().__init__("federated")
        # Simulate a second node (Node B) with slightly different init
        self.node_b = TrafficController("local", weights=[1.0, 1.1, 0.9, 1.0])
        self.round  = 0

    def step(self, tick: int, sensor: list) -> dict:
        # Node A steps normally
        m = super().step(tick, sensor)

        # Node B sees a slightly perturbed version (simulates different intersection)
        sensor_b = [max(0, min(1, s + (0.1 if i % 2 == 0 else -0.1)))
                    for i, s in enumerate(sensor)]
        self.node_b.step(tick, sensor_b)

        # FedAvg every FEDAVG_INTERVAL ticks
        if tick > 0 and tick % FEDAVG_INTERVAL == 0:
            self._fedavg()
            self.round += 1
            m["fedavg_round"] = self.round
        else:
            m["fedavg_round"] = self.round

        return m

    def _fedavg(self):
        # Weighted average (equal sample count → simple mean)
        global_weights = [
            (a + b) / 2
            for a, b in zip(self.weights, self.node_b.weights)
        ]
        self.weights      = global_weights
        self.node_b.weights = copy.copy(global_weights)


# ── Experiment runner ────────────────────────────────────────────────────────

def run_experiment(scenario_name: str, mode: str, run_id: int = 1) -> dict:
    path = SCENARIOS_DIR / f"{scenario_name}.json"
    with open(path) as f:
        scenario = json.load(f)

    ticks = scenario["ticks"]

    if mode == "fixed":
        ctrl = TrafficController("fixed")
    elif mode == "local":
        ctrl = TrafficController("local")
    elif mode == "federated":
        ctrl = FederatedController()
    else:
        raise ValueError(f"Unknown mode: {mode}")

    for tick_idx, sensor in enumerate(ticks):
        ctrl.step(tick_idx, sensor)

    # Aggregate metrics
    all_waits  = [m["avg_wait_ms"]        for m in ctrl.metrics]
    all_starv  = [m["starvation_event"]   for m in ctrl.metrics]
    all_util   = [m["utilisation_pct"]    for m in ctrl.metrics]

    n = len(ctrl.metrics)
    summary = {
        "scenario":            scenario_name,
        "mode":                mode,
        "run_id":              run_id,
        "ticks":               n,
        "avg_wait_ms":         round(sum(all_waits) / n, 1),
        "starvation_events":   sum(all_starv),
        "starvation_rate_pct": round(sum(all_starv) / n * 100, 2),
        "avg_utilisation_pct": round(sum(all_util)  / n, 2),
        "min_wait_ms":         round(min(all_waits), 1),
        "max_wait_ms":         round(max(all_waits), 1),
    }
    return summary


def write_result(summary: dict):
    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / "raw.csv"
    fieldnames = list(summary.keys())
    write_header = not out_path.exists()
    with open(out_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(summary)
    print(f"  → logged: {summary}")


SCENARIO_NAMES = ["light", "medium", "skewed_heavy"]
MODES          = ["fixed", "local", "federated"]
REPEAT_RUNS    = 3   # must match done-criteria (comparable metric tables ×3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=SCENARIO_NAMES)
    parser.add_argument("--mode",     choices=MODES)
    parser.add_argument("--run",      type=int, default=1)
    parser.add_argument("--all",      action="store_true",
                        help="Run all scenario×mode×run combinations")
    args = parser.parse_args()

    if args.all:
        total = len(SCENARIO_NAMES) * len(MODES) * REPEAT_RUNS
        done  = 0
        for scenario in SCENARIO_NAMES:
            for mode in MODES:
                for run_id in range(1, REPEAT_RUNS + 1):
                    done += 1
                    print(f"[{done}/{total}] scenario={scenario} mode={mode} run={run_id}")
                    summary = run_experiment(scenario, mode, run_id)
                    write_result(summary)
        print(f"\nAll {total} runs complete. Results in results/raw.csv")
    else:
        if not args.scenario or not args.mode:
            parser.error("Provide --scenario and --mode, or use --all")
        summary = run_experiment(args.scenario, args.mode, args.run)
        write_result(summary)


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nDone in {time.time()-t0:.2f}s")
