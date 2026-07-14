# colshift JSON formats

colshift writes two versioned JSON documents: the **profile**
(`colshift-profile/1`, from `colshift profile`) and the **report**
(`colshift-report/1`, from `colshift compare --format json` / `--json-out`).
Both are deterministic: sorted keys, no timestamps, floats rounded to six
decimals in reports — the same inputs always produce byte-identical output.
Any field-meaning change bumps the schema version.

## `colshift-profile/1`

A compact summary of one snapshot, safe to commit: it contains aggregates
only, never raw rows.

```json
{
  "schema_version": "colshift-profile/1",
  "generated_by": "colshift 0.1.0",
  "source": "demo/baseline.csv",
  "rows": 400,
  "options": { "bins": 10, "top_k": 20 },
  "columns": [
    {
      "name": "amount",
      "kind": "numeric",
      "total": 400,
      "nulls": 0,
      "distinct": 400,
      "stats": { "min": 1541.54, "max": 41454.92, "mean": 11082.38,
                 "stdev": 5939.21, "p25": 6915.12, "p50": 9849.54, "p75": 13648.95 },
      "edges": [5197.352, 6330.336, 7378.979, 8357.686, 9849.54,
                11194.168, 13041.778, 15055.834, 18459.924],
      "bin_counts": [40, 40, 40, 40, 40, 40, 40, 40, 40, 40]
    },
    {
      "name": "region",
      "kind": "categorical",
      "total": 400,
      "nulls": 0,
      "distinct": 4,
      "categories": [["north", 131], ["south", 126], ["east", 89], ["west", 54]],
      "other_count": 0
    }
  ]
}
```

Field notes (example abridged from the real demo-pair profile; floats are
shortened here for readability — real profiles store full precision):

| Field | Meaning |
|---|---|
| `kind` | `numeric` (every non-null cell parses as a finite number), `categorical`, or `empty` (all cells null) |
| `options.bins` | quantile buckets used for numeric columns; comparisons against this profile reuse them |
| `options.top_k` | categories stored per categorical column; the rest is aggregated into `other_count` |
| `edges` | interior bin edges cut at baseline quantiles, strictly increasing; bucket *i* covers `(edges[i-1], edges[i]]`, outer buckets are open-ended |
| `bin_counts` | baseline counts per bucket, `len(edges) + 1` entries |
| `categories` | `[value, count]` pairs, count-descending, value-ascending on ties |
| `other_count` | total non-null values beyond the stored top-K |

A constant numeric column stores the single edge `[c]`, giving the buckets
`<= c` and `> c`, so drift above the constant still registers in PSI.

## `colshift-report/1`

```json
{
  "schema_version": "colshift-report/1",
  "generated_by": "colshift 0.1.0",
  "baseline": { "source": "demo/baseline.csv", "rows": 400, "columns": 8 },
  "current": { "source": "demo/current.csv", "rows": 450, "columns": 8 },
  "thresholds": { "psi_warn": 0.1, "psi_alert": 0.25,
                  "null_warn": 0.05, "null_alert": 0.15 },
  "verdict": "alert",
  "counts": { "ok": 2, "warn": 2, "alert": 3 },
  "schema_changes": {
    "added": [{ "name": "device", "kind": "categorical" }],
    "removed": [{ "name": "promo_code", "kind": "categorical" }]
  },
  "columns": [
    {
      "name": "region",
      "kind_baseline": "categorical",
      "kind_current": "categorical",
      "verdict": "alert",
      "psi": 0.356845,
      "null_rate_baseline": 0.0,
      "null_rate_current": 0.0,
      "null_delta": 0.0,
      "notes": ["new categories: offshore (15)"],
      "new_categories": [{ "value": "offshore", "count": 15 }],
      "buckets": [
        { "label": "north", "baseline_count": 131, "current_count": 157,
          "baseline_share": 0.3275, "current_share": 0.348889,
          "contribution": 0.001353 }
      ]
    }
  ]
}
```

Field notes:

| Field | Meaning |
|---|---|
| `verdict` | `ok` / `warn` / `alert` — the maximum over all columns, plus `warn` for added and `alert` for removed columns |
| `psi` | Population Stability Index over the aligned buckets; `null` when either side has no non-null values or the column changed type |
| `buckets[].contribution` | this bucket's PSI term `(q - p) * ln(q / p)`; contributions sum to `psi` |
| `range` | numeric columns only: `baseline`/`current` `[min, max]` plus `expanded_low`/`expanded_high` flags |
| `new_categories` | present only when the baseline's stored categories were exhaustive (`other_count == 0`), so novelty is provable |
| `unlisted_current` | count of current values beyond the baseline's stored top-K when the baseline *had* an `(other)` tail — reported instead of claiming them as new |
| `missing_categories` | stored baseline categories with zero occurrences in current |

PSI details: shares are exact in the output; only the log ratio is smoothed
with a floor of `1e-6`, so a bucket that appears or vanishes contributes a
large-but-finite term instead of infinity. Nulls are excluded from PSI and
tracked separately as `null_delta` with its own thresholds.
