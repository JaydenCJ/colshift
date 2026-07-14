# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-12

### Added

- Snapshot loaders for CSV, TSV, and JSON Lines with a uniform in-memory
  table: BOM handling, delimiter override, short-row padding, long-row
  errors with line numbers, JSONL scalar normalization and canonical
  encoding of nested values.
- Null detection with a documented default token set (`NULL`, `NaN`, `NA`,
  `#N/A`, …), always-null empty/whitespace cells, and a `--null-tokens`
  replacement flag; strict numeric parsing that rejects `inf`, `nan`, and
  underscore literals so one stray token cannot flip a column's type.
- Column profiling: numeric summary stats (min/max/mean/stdev/quartiles),
  quantile bin edges with duplicate collapsing and a constant-column
  special case, top-K category counts with a deterministic tie-break and an
  `(other)` tail.
- Committable `colshift-profile/1` JSON documents (aggregates only, never
  raw rows) with strict validation on load; comparing against a profile is
  guaranteed identical to comparing against the raw baseline.
- PSI over aligned buckets with per-bucket contributions, epsilon-smoothed
  log ratios, and exact (unsmoothed) reported shares; categorical alignment
  onto the baseline's stored categories plus an `(other)` bucket.
- Drift engine with `ok`/`warn`/`alert` verdicts: PSI thresholds (0.10 /
  0.25 by default), absolute null-rate-delta thresholds, numeric range
  expansion, type changes, new/missing category detection that never claims
  novelty the stored top-K cannot prove, and schema add/remove tracking.
- Deterministic report renderers: a markdown report with summary table,
  schema changes, per-column details and top contributing buckets; a
  versioned `colshift-report/1` JSON document with sorted keys and no
  timestamps.
- `colshift` CLI: `compare` (formats, `--out`/`--json-out`, column
  include/exclude filters, threshold flags, `--fail-on never|warn|alert`
  exit-code gate) and `profile`; exit codes 0/1/2.
- Deterministic demo snapshot generator and walkthrough script under
  `examples/`, format documentation in `docs/formats.md`.
- 92 pytest tests and `scripts/smoke.sh`, all offline and deterministic.

### Notes

- The repository ships no CI workflow; verification is local — `pip install -e '.[dev]' && pytest && bash scripts/smoke.sh`.

[0.1.0]: https://github.com/JaydenCJ/colshift/releases/tag/v0.1.0
