# colshift examples

Two runnable pieces, both offline and fully deterministic:

- **`make_snapshots.py`** — generates `baseline.csv` (400 rows) and
  `current.csv` (450 rows) with drift injected on purpose: a shifted
  `amount`, a nudged `interest_rate`, a `credit_score` low tail below the
  baseline range, an `income` null-rate jump from 2% to ~18%, a new
  `region` value, one removed column, and one added column. Seeded, so two
  runs produce byte-identical files.
- **`drift_demo.sh`** — the full walkthrough: generate, compare in
  markdown and JSON, then the commit-a-profile workflow
  (`colshift profile` -> compare against the stored profile).

From the repository root:

```bash
bash examples/drift_demo.sh          # writes into ./demo (gitignored)
```

or step by step:

```bash
python3 examples/make_snapshots.py demo
colshift compare demo/baseline.csv demo/current.csv --exclude loan_id
```

`--exclude loan_id` matters: `loan_id` is a unique identifier, so its
distribution "drifts" on every snapshot by construction — excluding id-like
columns is exactly what the flag is for.
