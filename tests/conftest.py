"""Shared fixtures and factories for the colshift test suite.

Everything is offline and deterministic: snapshots are tiny literal CSV /
JSONL files written into tmp_path, never generated from randomness.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

import pytest

from colshift.loaders import Dataset


def write_csv(path: Path, header: Sequence[str], rows: Sequence[Sequence[str]]) -> Path:
    """Write a small CSV file and return its path."""
    lines = [",".join(header)]
    lines.extend(",".join(row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def make_dataset(columns: dict, source: str = "test.csv") -> Dataset:
    """Build an in-memory Dataset from {column: [cells]} without touching disk."""
    names: List[str] = list(columns)
    rows = len(next(iter(columns.values()))) if columns else 0
    for name, cells in columns.items():
        assert len(cells) == rows, f"ragged test data in column {name}"
    return Dataset(source=source, format="csv", columns=names, rows=rows, values=dict(columns))


@pytest.fixture
def baseline_csv(tmp_path: Path) -> Path:
    """A small baseline snapshot with a numeric and a categorical column."""
    return write_csv(
        tmp_path / "baseline.csv",
        ["amount", "region"],
        [[str(v), r] for v, r in zip(range(10, 110), ["north", "south"] * 50)],
    )


@pytest.fixture
def identical_current_csv(tmp_path: Path, baseline_csv: Path) -> Path:
    """A current snapshot byte-identical in content to the baseline."""
    target = tmp_path / "current.csv"
    target.write_text(baseline_csv.read_text(encoding="utf-8"), encoding="utf-8")
    return target
