# Contributing to colshift

Thanks for your interest in contributing. Issues, discussions, and pull
requests are all welcome.

## Getting started

You need Python 3.9 or newer; nothing else.

```bash
git clone https://github.com/JaydenCJ/colshift
cd colshift
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
bash scripts/smoke.sh
```

`scripts/smoke.sh` generates the demo snapshot pair and drives the real CLI
end-to-end — compare, profile, JSON output, exit-code gates, failure paths —
and must print `SMOKE OK`.

## Before you open a pull request

1. Format with `python3 -m black src tests` if you have it (PEP 8 / 100-column
   style is enforced by review either way).
2. Lint with `python3 -m ruff check src tests` if you have it; new warnings
   are treated as failures.
3. `pytest` — all tests must pass, offline, with no new flakiness.
4. `bash scripts/smoke.sh` — must print `SMOKE OK`.
5. Add tests for behavior changes; keep logic in pure, unit-testable modules
   (`psi.py`, `stats.py`, `drift.py` know nothing about files or argv).

## Ground rules

- **No new runtime dependencies.** The package is standard-library only; that
  is the headline feature. Test-only tooling belongs in the `dev` extra.
- **Format changes need a version bump and docs.** Anything that changes the
  meaning of a field in `colshift-profile/1` or `colshift-report/1` must bump
  the schema version and update `docs/formats.md` in the same pull request.
- **Determinism is a contract.** Reports and profiles must stay byte-identical
  for identical inputs: no timestamps, no unsorted iteration, no locale
  dependence.
- **No network calls, no telemetry.** colshift reads local files and writes
  local files; nothing else.
- Code comments and doc comments are written in English.
- **Keep the three READMEs aligned.** `README.md`, `README.zh.md`, and
  `README.ja.md` are line-for-line translations; update all three when you
  change one (English is the authoritative version).

## Reporting bugs

Please include `colshift --version`, the exact command line, the report (or
the error printed to stderr), and if possible a minimal snapshot pair or a
`colshift profile` output that reproduces the issue — profiles contain only
aggregates, so they are safe to share.

## Security

Please do not open public issues for suspected vulnerabilities; use GitHub's
private vulnerability reporting on this repository instead.
