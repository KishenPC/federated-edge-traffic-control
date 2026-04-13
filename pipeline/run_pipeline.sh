#!/usr/bin/env bash
# run_pipeline.sh
# Runs the complete reproducible experiment pipeline end-to-end.
# Usage: bash run_pipeline.sh

set -e

echo "========================================"
echo " Federated Traffic Control — Experiment"
echo "========================================"

echo ""
echo "[1/3] Generating scenario files..."
python scenarios.py

echo ""
echo "[2/3] Running all scenario × mode × repeat combinations..."
# This runs: 3 scenarios × 3 modes × 3 repeats = 27 total experiments
python simulate.py --all

echo ""
echo "[3/3] Analysing results..."
python analyse.py

echo ""
echo "Pipeline complete. Check results/raw.csv for full data."
