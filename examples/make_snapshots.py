#!/usr/bin/env python3
"""Generate a deterministic pair of dataset snapshots with injected drift.

Writes ``baseline.csv`` (400 rows) and ``current.csv`` (450 rows) into the
output directory (default: ``demo``). The current snapshot drifts on
purpose, so ``colshift compare`` has something interesting to say:

  * ``amount``         shifted up ~35%              -> PSI alert
  * ``interest_rate``  shifted up ~0.5 points       -> PSI warn
  * ``credit_score``   lower mean + a new low tail  -> PSI drift, range widened
  * ``income``         null rate 2% -> ~18%         -> null-rate alert
  * ``region``         gains a new "offshore" value -> new-category warn
  * ``promo_code``     dropped in current           -> schema alert
  * ``device``         added in current             -> schema warn
  * ``term_months``, ``channel``                    -> stable, verdict ok

``loan_id`` is a unique identifier, so its PSI is meaningless noise —
compare with ``--exclude loan_id`` (this is exactly what the flag is for).

Everything is seeded; two runs produce byte-identical files.
"""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

SEED = 20260712


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def baseline_rows(rng: random.Random):
    for i in range(400):
        income = ""
        if rng.random() >= 0.02:  # ~2% nulls
            income = str(int(round(clamp(rng.gauss(52000, 15000), 12000, 250000), -2)))
        yield {
            "loan_id": f"L{10000 + i}",
            "amount": f"{rng.lognormvariate(9.2, 0.5):.2f}",
            "interest_rate": f"{clamp(rng.gauss(7.1, 1.3), 1.0, 20.0):.2f}",
            "term_months": str(rng.choices([12, 24, 36, 48, 60], [10, 20, 35, 20, 15])[0]),
            "region": rng.choices(["north", "south", "east", "west"], [35, 30, 20, 15])[0],
            "channel": rng.choices(["web", "branch", "partner"], [55, 30, 15])[0],
            "income": income,
            "credit_score": str(int(clamp(rng.gauss(690, 55), 300, 850))),
            "promo_code": rng.choices(["spring24", "welcome", "renewal"], [40, 35, 25])[0],
        }


def current_rows(rng: random.Random):
    for i in range(450):
        income = ""
        if rng.random() >= 0.18:  # nulls jump to ~18%
            income = str(int(round(clamp(rng.gauss(53000, 15500), 12000, 250000), -2)))
        if rng.random() < 0.06:  # new low tail below the baseline range
            score = int(rng.uniform(360, 520))
        else:
            score = int(clamp(rng.gauss(668, 62), 300, 850))
        yield {
            "loan_id": f"L{20000 + i}",
            "amount": f"{rng.lognormvariate(9.2, 0.5) * 1.35:.2f}",
            "interest_rate": f"{clamp(rng.gauss(7.65, 1.35), 1.0, 20.0):.2f}",
            "term_months": str(rng.choices([12, 24, 36, 48, 60], [10, 20, 35, 20, 15])[0]),
            "region": rng.choices(
                ["north", "south", "east", "west", "offshore"], [31, 29, 20, 16, 4]
            )[0],
            "channel": rng.choices(["web", "branch", "partner"], [55, 30, 15])[0],
            "income": income,
            "credit_score": str(score),
            "device": rng.choices(["ios", "android", "desktop"], [40, 35, 25])[0],
        }


def write_csv(path: Path, rows) -> int:
    rows = list(rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> int:
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("demo")
    outdir.mkdir(parents=True, exist_ok=True)
    n_base = write_csv(outdir / "baseline.csv", baseline_rows(random.Random(SEED)))
    n_cur = write_csv(outdir / "current.csv", current_rows(random.Random(SEED + 1)))
    print(f"wrote {outdir / 'baseline.csv'} ({n_base} rows)")
    print(f"wrote {outdir / 'current.csv'} ({n_cur} rows)")
    print("next: colshift compare "
          f"{outdir / 'baseline.csv'} {outdir / 'current.csv'} --exclude loan_id")
    return 0


if __name__ == "__main__":
    sys.exit(main())
