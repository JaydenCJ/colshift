#!/usr/bin/env bash
# Smoke test for colshift: generate the demo snapshot pair, compare it in
# markdown and JSON, store a baseline profile and compare against it, and
# exercise the exit-code gates and failure paths.
# Self-contained: pure stdlib, no network, idempotent (works from a clean tree).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

# The package has zero runtime dependencies, so running from src/ needs no install.
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/colshift-smoke.XXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

echo "[smoke] python: $("$PYTHON" --version 2>&1)"

# 1. Build the deterministic demo snapshot pair.
"$PYTHON" "$ROOT/examples/make_snapshots.py" "$WORKDIR" >/dev/null \
  || fail "make_snapshots.py exited non-zero"
[ -f "$WORKDIR/baseline.csv" ] || fail "baseline snapshot missing"
[ -f "$WORKDIR/current.csv" ] || fail "current snapshot missing"

# 2. Comparing a snapshot against itself exits 0 and says OK.
same_out="$("$PYTHON" -m colshift compare "$WORKDIR/baseline.csv" "$WORKDIR/baseline.csv" --exclude loan_id)" \
  || fail "self-compare should exit 0"
echo "$same_out" | grep -q '\*\*Verdict: OK\*\*' || fail "self-compare verdict should be OK"
echo "$same_out" | grep -q "No column crossed the warn threshold." \
  || fail "self-compare should report no drifted columns"

# 3. Comparing the drifted pair exits 1 and flags the injected drift.
set +e
drift_out="$("$PYTHON" -m colshift compare "$WORKDIR/baseline.csv" "$WORKDIR/current.csv" --exclude loan_id)"
drift_rc=$?
set -e
[ "$drift_rc" -eq 1 ] || fail "drifted compare should exit 1, got $drift_rc"
echo "$drift_out" | head -30 | sed 's/^/[compare] /'
echo "$drift_out" | grep -q '\*\*Verdict: ALERT\*\*' || fail "drifted compare verdict should be ALERT"
echo "$drift_out" | grep -Eq '\| amount \| numeric \| [0-9]+\.[0-9]{3} .* ALERT' \
  || fail "amount column should alert on PSI"
echo "$drift_out" | grep -q "new categories: offshore" || fail "region should report the new category"
echo "$drift_out" | grep -q "range widened low" || fail "credit_score should report a widened range"
echo "$drift_out" | grep -q 'removed from baseline: `promo_code`' || fail "promo_code removal not reported"
echo "$drift_out" | grep -q 'added in current: `device`' || fail "device addition not reported"

# 4. --fail-on never keeps the report but returns 0 (report-only mode).
"$PYTHON" -m colshift compare "$WORKDIR/baseline.csv" "$WORKDIR/current.csv" \
  --exclude loan_id --fail-on never >/dev/null \
  || fail "--fail-on never should exit 0"

# 5. JSON report parses and carries the schema marker and verdict.
set +e
"$PYTHON" -m colshift compare "$WORKDIR/baseline.csv" "$WORKDIR/current.csv" \
  --exclude loan_id --format json >"$WORKDIR/report.json"
json_rc=$?
set -e
[ "$json_rc" -eq 1 ] || fail "JSON compare on drift should exit 1, got $json_rc"
"$PYTHON" - "$WORKDIR/report.json" <<'PYEOF' || fail "JSON report failed validation"
import json, sys
data = json.load(open(sys.argv[1]))
assert data["schema_version"] == "colshift-report/1", "schema marker missing"
assert data["verdict"] == "alert", "verdict should be alert"
assert any(c["name"] == "income" and c["verdict"] == "alert" for c in data["columns"]), \
    "income null-rate alert missing"
PYEOF

# 6. Store a baseline profile, then compare against it: same verdict, exit 1.
"$PYTHON" -m colshift profile "$WORKDIR/baseline.csv" -o "$WORKDIR/baseline-profile.json" 2>/dev/null \
  || fail "profile command exited non-zero"
grep -q "colshift-profile/1" "$WORKDIR/baseline-profile.json" || fail "profile schema marker missing"
set +e
profile_out="$("$PYTHON" -m colshift compare "$WORKDIR/baseline-profile.json" "$WORKDIR/current.csv" --exclude loan_id)"
profile_rc=$?
set -e
[ "$profile_rc" -eq 1 ] || fail "profile-baseline compare should exit 1, got $profile_rc"
echo "$profile_out" | grep -q '\*\*Verdict: ALERT\*\*' || fail "profile-baseline verdict should be ALERT"

# 7. --json-out writes the machine artifact next to the human report.
"$PYTHON" -m colshift compare "$WORKDIR/baseline.csv" "$WORKDIR/current.csv" \
  --exclude loan_id --fail-on never --json-out "$WORKDIR/artifact.json" >/dev/null 2>&1 \
  || fail "--json-out run exited non-zero"
grep -q '"colshift-report/1"' "$WORKDIR/artifact.json" || fail "--json-out artifact missing schema"

# 8. Failure path: a missing snapshot exits 2 with a clear error.
set +e
"$PYTHON" -m colshift compare "$WORKDIR/ghost.csv" "$WORKDIR/current.csv" 2>"$WORKDIR/err.txt"
missing_rc=$?
set -e
[ "$missing_rc" -eq 2 ] || fail "missing snapshot should exit 2, got $missing_rc"
grep -q "colshift: error:" "$WORKDIR/err.txt" || fail "missing snapshot error message wrong"

# 9. --version agrees with the package version; --help lists both commands.
version_out="$("$PYTHON" -m colshift --version)"
pkg_version="$("$PYTHON" -c 'import colshift; print(colshift.__version__)')"
[ "$version_out" = "colshift $pkg_version" ] \
  || fail "--version mismatch: '$version_out' vs package '$pkg_version'"
"$PYTHON" -m colshift --help | grep -q "compare" || fail "--help missing compare command"
"$PYTHON" -m colshift --help | grep -q "profile" || fail "--help missing profile command"

echo "SMOKE OK"
