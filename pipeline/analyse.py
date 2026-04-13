"""
analyse.py
Loads results/raw.csv and produces:
  1. A mean comparison table (scenario × mode) for each metric
  2. A variance consistency check (flags any metric with CV > 5%)
  3. Prints a summary that can be copy-pasted into a project report

Usage:
    python analyse.py
"""

import csv
import statistics
from pathlib import Path
from collections import defaultdict

RAW_CSV = Path("results/raw.csv")

METRICS = {
    "avg_wait_ms":         "Avg wait (ms)",
    "starvation_rate_pct": "Starvation rate (%)",
    "avg_utilisation_pct": "Green utilisation (%)",
}

SCENARIOS = ["light", "medium", "skewed_heavy"]
MODES     = ["fixed", "local", "federated"]
MODE_LABELS = {
    "fixed":     "Fixed-time baseline",
    "local":     "Local-only adaptive",
    "federated": "Federated adaptive",
}

CV_THRESHOLD_PCT = 5.0   # coefficient of variation threshold for "consistent"


def load_results() -> dict:
    """Returns nested dict: data[scenario][mode] = list of row dicts."""
    data = defaultdict(lambda: defaultdict(list))
    with open(RAW_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            data[row["scenario"]][row["mode"]].append(row)
    return data


def mean(vals):
    return statistics.mean(float(v) for v in vals)

def cv(vals):
    """Coefficient of variation as a percentage."""
    floats = [float(v) for v in vals]
    if len(floats) < 2 or statistics.mean(floats) == 0:
        return 0.0
    return statistics.stdev(floats) / statistics.mean(floats) * 100


def print_separator(width=72):
    print("─" * width)


def print_comparison_table(data: dict, metric_key: str, metric_label: str):
    print(f"\n  Metric: {metric_label}")
    print_separator(60)
    header = f"  {'Scenario':<18}" + "".join(f"{MODE_LABELS[m]:>16}" for m in MODES)
    print(header)
    print_separator(60)

    for scenario in SCENARIOS:
        row = f"  {scenario:<18}"
        for mode in MODES:
            rows = data[scenario][mode]
            if rows:
                vals = [r[metric_key] for r in rows]
                row += f"{mean(vals):>15.1f}"
            else:
                row += f"{'N/A':>15}"
        print(row)

    print_separator(60)


def print_consistency_check(data: dict):
    print("\n  Variance consistency check (CV < 5% = pass)")
    print_separator(60)
    header = f"  {'Scenario':<14} {'Mode':<12} {'Metric':<24} {'CV %':>6}  {'Status':>6}"
    print(header)
    print_separator(60)

    all_pass = True
    for scenario in SCENARIOS:
        for mode in MODES:
            rows = data[scenario][mode]
            if not rows:
                continue
            for metric_key, metric_label in METRICS.items():
                vals   = [r[metric_key] for r in rows]
                cv_val = cv(vals)
                status = "PASS" if cv_val < CV_THRESHOLD_PCT else "FAIL"
                if status == "FAIL":
                    all_pass = False
                print(f"  {scenario:<14} {mode:<12} {metric_label:<24} {cv_val:>5.1f}%  {status:>6}")

    print_separator(60)
    if all_pass:
        print("  All runs within 5% CV — results are reproducible.")
    else:
        print("  WARNING: Some runs exceed 5% CV. Check for non-determinism.")


def print_improvement_summary(data: dict):
    print("\n  Improvement of federated vs fixed-time baseline")
    print_separator(60)
    for scenario in SCENARIOS:
        print(f"\n  Scenario: {scenario}")
        for metric_key, metric_label in METRICS.items():
            fixed_rows = data[scenario]["fixed"]
            fed_rows   = data[scenario]["federated"]
            if not fixed_rows or not fed_rows:
                continue
            fixed_mean = mean([r[metric_key] for r in fixed_rows])
            fed_mean   = mean([r[metric_key] for r in fed_rows])
            if fixed_mean == 0:
                continue
            delta_pct = (fed_mean - fixed_mean) / fixed_mean * 100
            direction = "improvement" if delta_pct < 0 else "increase"
            print(f"    {metric_label}: {fixed_mean:.1f} → {fed_mean:.1f}  "
                  f"({abs(delta_pct):.1f}% {direction})")


def main():
    if not RAW_CSV.exists():
        print(f"No results found at {RAW_CSV}. Run simulate.py first.")
        return

    data = load_results()

    print("\n" + "=" * 72)
    print("  EXPERIMENT RESULTS — FEDERATED EDGE-AI TRAFFIC CONTROL")
    print("=" * 72)

    for metric_key, metric_label in METRICS.items():
        print_comparison_table(data, metric_key, metric_label)

    print_consistency_check(data)
    print_improvement_summary(data)

    print("\n" + "=" * 72)
    print("  Done. Copy the tables above into your project report.")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()
