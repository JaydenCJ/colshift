#!/usr/bin/env bash
# Full colshift walkthrough on the generated demo pair:
#   1. generate two drifted snapshots
#   2. human-readable markdown compare (exit 1 because drift alerts)
#   3. machine-readable JSON compare
#   4. commit-a-profile workflow: profile the baseline, compare against it
# Run from the repository root: bash examples/drift_demo.sh [outdir]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
OUT="${1:-demo}"

echo "== 1. generate snapshots =="
"$PYTHON" "$ROOT/examples/make_snapshots.py" "$OUT"

echo
echo "== 2. markdown report (loan_id excluded: unique ids make PSI meaningless) =="
"$PYTHON" -m colshift compare "$OUT/baseline.csv" "$OUT/current.csv" --exclude loan_id \
  || echo "(exit code $? — drift at alert level, ready for CI gating)"

echo
echo "== 3. JSON report, first lines =="
"$PYTHON" -m colshift compare "$OUT/baseline.csv" "$OUT/current.csv" --exclude loan_id \
  --format json --fail-on never | head -20

echo
echo "== 4. profile workflow: commit the profile, not the data =="
"$PYTHON" -m colshift profile "$OUT/baseline.csv" -o "$OUT/baseline-profile.json"
"$PYTHON" -m colshift compare "$OUT/baseline-profile.json" "$OUT/current.csv" \
  --exclude loan_id --fail-on never | head -12

echo
echo "DEMO OK"
