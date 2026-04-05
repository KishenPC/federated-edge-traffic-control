# Experiment Pipeline

Generates reproducible results for fixed-time, local-adaptive, and federated modes.

## Prerequisites
Python 3.x — no external libraries needed (uses only stdlib).

## How to run
```bash
bash run_pipeline.sh
```
This will:
1. Generate scenario files in `scenarios/`
2. Run all 27 experiments (3 scenarios × 3 modes × 3 repeats)
3. Print the comparison table and consistency check

Results are written to `results/raw.csv`.

scenarios and results file has been added to `.gitignore` because:
Each person should generate their own results locally. If you commit generated CSVs, merge conflicts become a headache fast.
