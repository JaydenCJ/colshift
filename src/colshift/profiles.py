"""Column profiles: the compact, committable summary of one snapshot.

A profile stores everything :func:`colshift.drift.compare` needs from the
baseline side — quantile bin edges and counts for numeric columns, top-K
category counts for categorical ones — so a baseline can be a small JSON
file in git instead of the raw data.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Tuple

from . import __version__
from .errors import ProfileError
from .inference import (
    DEFAULT_NULL_TOKENS,
    KIND_CATEGORICAL,
    KIND_EMPTY,
    KIND_NUMERIC,
    infer_kind,
    parse_number,
    split_nulls,
)
from .loaders import Dataset
from .stats import bin_values, percentiles, quantile_edges, sample_stdev

#: Schema marker written into every profile JSON document.
PROFILE_SCHEMA = "colshift-profile/1"

DEFAULT_BINS = 10
DEFAULT_TOP_K = 20


@dataclass
class ColumnProfile:
    """Summary of one column of one snapshot."""

    name: str
    kind: str  # numeric | categorical | empty
    total: int
    nulls: int
    distinct: int
    # Numeric columns only:
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    mean: Optional[float] = None
    stdev: Optional[float] = None
    p25: Optional[float] = None
    p50: Optional[float] = None
    p75: Optional[float] = None
    edges: List[float] = field(default_factory=list)
    bin_counts: List[int] = field(default_factory=list)
    # Categorical columns only:
    categories: List[Tuple[str, int]] = field(default_factory=list)
    other_count: int = 0

    @property
    def null_rate(self) -> float:
        return self.nulls / self.total if self.total else 0.0


@dataclass
class DatasetProfile:
    """All column profiles of one snapshot plus the options used to build it."""

    source: str
    rows: int
    bins: int
    top_k: int
    columns: List[ColumnProfile] = field(default_factory=list)

    def column(self, name: str) -> Optional[ColumnProfile]:
        for col in self.columns:
            if col.name == name:
                return col
        return None


def profile_column(
    name: str,
    raws: List[Optional[str]],
    bins: int = DEFAULT_BINS,
    top_k: int = DEFAULT_TOP_K,
    null_tokens: FrozenSet[str] = DEFAULT_NULL_TOKENS,
) -> ColumnProfile:
    """Build the profile of a single column from raw cells."""
    values, nulls = split_nulls(raws, null_tokens)
    kind = infer_kind(values)
    profile = ColumnProfile(
        name=name, kind=kind, total=len(raws), nulls=nulls, distinct=len(set(values))
    )
    if kind == KIND_NUMERIC:
        numbers = sorted(parse_number(v) for v in values)  # type: ignore[type-var]
        profile.minimum = float(numbers[0])
        profile.maximum = float(numbers[-1])
        profile.mean = float(sum(numbers) / len(numbers))
        profile.stdev = sample_stdev(numbers)
        profile.p25, profile.p50, profile.p75 = percentiles(numbers)
        profile.edges = quantile_edges(numbers, bins)
        profile.bin_counts = bin_values(profile.edges, numbers)
    elif kind == KIND_CATEGORICAL:
        counter = Counter(values)
        # Deterministic top-K: count descending, then value ascending.
        ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        profile.categories = ranked[:top_k]
        profile.other_count = sum(count for _, count in ranked[top_k:])
    return profile


def profile_dataset(
    dataset: Dataset,
    bins: int = DEFAULT_BINS,
    top_k: int = DEFAULT_TOP_K,
    null_tokens: FrozenSet[str] = DEFAULT_NULL_TOKENS,
) -> DatasetProfile:
    """Profile every column of a loaded snapshot."""
    columns = [
        profile_column(name, dataset.values[name], bins=bins, top_k=top_k, null_tokens=null_tokens)
        for name in dataset.columns
    ]
    return DatasetProfile(
        source=dataset.source, rows=dataset.rows, bins=bins, top_k=top_k, columns=columns
    )


def profile_to_dict(profile: DatasetProfile) -> Dict[str, object]:
    """Serialize a profile to the ``colshift-profile/1`` JSON structure."""
    columns: List[Dict[str, object]] = []
    for col in profile.columns:
        entry: Dict[str, object] = {
            "name": col.name,
            "kind": col.kind,
            "total": col.total,
            "nulls": col.nulls,
            "distinct": col.distinct,
        }
        if col.kind == KIND_NUMERIC:
            entry["stats"] = {
                "min": col.minimum,
                "max": col.maximum,
                "mean": col.mean,
                "stdev": col.stdev,
                "p25": col.p25,
                "p50": col.p50,
                "p75": col.p75,
            }
            entry["edges"] = list(col.edges)
            entry["bin_counts"] = list(col.bin_counts)
        elif col.kind == KIND_CATEGORICAL:
            entry["categories"] = [[value, count] for value, count in col.categories]
            entry["other_count"] = col.other_count
        columns.append(entry)
    return {
        "schema_version": PROFILE_SCHEMA,
        "generated_by": f"colshift {__version__}",
        "source": profile.source,
        "rows": profile.rows,
        "options": {"bins": profile.bins, "top_k": profile.top_k},
        "columns": columns,
    }


def profile_from_dict(data: object) -> DatasetProfile:
    """Parse and validate a ``colshift-profile/1`` document."""
    if not isinstance(data, dict):
        raise ProfileError("profile document must be a JSON object")
    if data.get("schema_version") != PROFILE_SCHEMA:
        raise ProfileError(
            f"not a colshift profile (expected schema_version '{PROFILE_SCHEMA}', "
            f"got {data.get('schema_version')!r})"
        )
    rows = data.get("rows")
    if not isinstance(rows, int) or rows < 0:
        raise ProfileError("profile field 'rows' must be a non-negative integer")
    options = data.get("options")
    if not isinstance(options, dict):
        raise ProfileError("profile field 'options' must be an object")
    bins = options.get("bins")
    top_k = options.get("top_k")
    if not isinstance(bins, int) or bins < 2:
        raise ProfileError("profile option 'bins' must be an integer >= 2")
    if not isinstance(top_k, int) or top_k < 1:
        raise ProfileError("profile option 'top_k' must be an integer >= 1")
    raw_columns = data.get("columns")
    if not isinstance(raw_columns, list):
        raise ProfileError("profile field 'columns' must be a list")
    columns = [_column_from_dict(entry, index) for index, entry in enumerate(raw_columns)]
    source = data.get("source")
    return DatasetProfile(
        source=source if isinstance(source, str) else "<unknown>",
        rows=rows,
        bins=bins,
        top_k=top_k,
        columns=columns,
    )


def _column_from_dict(entry: object, index: int) -> ColumnProfile:
    if not isinstance(entry, dict):
        raise ProfileError(f"profile column #{index} must be an object")
    name = entry.get("name")
    kind = entry.get("kind")
    if not isinstance(name, str) or not name:
        raise ProfileError(f"profile column #{index} is missing a name")
    if kind not in (KIND_NUMERIC, KIND_CATEGORICAL, KIND_EMPTY):
        raise ProfileError(f"profile column '{name}' has unknown kind {kind!r}")
    total = entry.get("total")
    nulls = entry.get("nulls")
    distinct = entry.get("distinct")
    for label, value in (("total", total), ("nulls", nulls), ("distinct", distinct)):
        if not isinstance(value, int) or value < 0:
            raise ProfileError(f"profile column '{name}': '{label}' must be a non-negative integer")
    col = ColumnProfile(name=name, kind=kind, total=total, nulls=nulls, distinct=distinct)
    if kind == KIND_NUMERIC:
        stats = entry.get("stats")
        if not isinstance(stats, dict):
            raise ProfileError(f"profile column '{name}': numeric column needs a 'stats' object")
        col.minimum = _opt_float(stats.get("min"), name, "min")
        col.maximum = _opt_float(stats.get("max"), name, "max")
        col.mean = _opt_float(stats.get("mean"), name, "mean")
        col.stdev = _opt_float(stats.get("stdev"), name, "stdev")
        col.p25 = _opt_float(stats.get("p25"), name, "p25")
        col.p50 = _opt_float(stats.get("p50"), name, "p50")
        col.p75 = _opt_float(stats.get("p75"), name, "p75")
        edges = entry.get("edges")
        bin_counts = entry.get("bin_counts")
        if not isinstance(edges, list) or not all(isinstance(e, (int, float)) for e in edges):
            raise ProfileError(f"profile column '{name}': 'edges' must be a list of numbers")
        if not isinstance(bin_counts, list) or not all(
            isinstance(c, int) and c >= 0 for c in bin_counts
        ):
            raise ProfileError(f"profile column '{name}': 'bin_counts' must be a list of counts")
        if len(bin_counts) != len(edges) + 1:
            raise ProfileError(
                f"profile column '{name}': expected {len(edges) + 1} bin counts, got {len(bin_counts)}"
            )
        col.edges = [float(e) for e in edges]
        col.bin_counts = list(bin_counts)
    elif kind == KIND_CATEGORICAL:
        categories = entry.get("categories")
        other_count = entry.get("other_count")
        if not isinstance(categories, list):
            raise ProfileError(f"profile column '{name}': 'categories' must be a list")
        parsed: List[Tuple[str, int]] = []
        for item in categories:
            if (
                not isinstance(item, (list, tuple))
                or len(item) != 2
                or not isinstance(item[0], str)
                or not isinstance(item[1], int)
            ):
                raise ProfileError(
                    f"profile column '{name}': each category must be a [value, count] pair"
                )
            parsed.append((item[0], item[1]))
        if not isinstance(other_count, int) or other_count < 0:
            raise ProfileError(f"profile column '{name}': 'other_count' must be a non-negative integer")
        col.categories = parsed
        col.other_count = other_count
    return col


def _opt_float(value: object, column: str, label: str) -> Optional[float]:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ProfileError(f"profile column '{column}': stat '{label}' must be a number or null")
    return float(value)
