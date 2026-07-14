"""The drift engine: compare a baseline profile against a current snapshot.

The baseline side is always a :class:`~colshift.profiles.DatasetProfile`
(built in-process from raw data, or loaded from a committed profile JSON),
so raw-vs-raw and profile-vs-raw comparisons take the identical code path
and produce identical results.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Tuple

from .inference import (
    DEFAULT_NULL_TOKENS,
    KIND_CATEGORICAL,
    KIND_EMPTY,
    KIND_NUMERIC,
    numeric_values,
    split_nulls,
)
from .loaders import Dataset
from .profiles import ColumnProfile, DatasetProfile, profile_dataset
from .psi import Bucket, align_categories, psi_from_counts
from .stats import bin_values, bucket_labels, fmt_num, fmt_pct

#: Verdict levels in ascending severity.
OK, WARN, ALERT = "ok", "warn", "alert"
_SEVERITY_RANK = {OK: 0, WARN: 1, ALERT: 2}

#: How many new/missing categories are kept in the report.
MAX_LISTED_CATEGORIES = 10


@dataclass
class Thresholds:
    """Classification thresholds; defaults are the industry PSI convention."""

    psi_warn: float = 0.10
    psi_alert: float = 0.25
    null_warn: float = 0.05  # absolute change in null rate
    null_alert: float = 0.15


@dataclass
class ColumnDrift:
    """Everything the report needs to say about one shared column."""

    name: str
    kind_baseline: str
    kind_current: str
    psi: Optional[float]
    buckets: List[Bucket]
    null_rate_baseline: float
    null_rate_current: float
    null_delta: float
    range_baseline: Optional[Tuple[float, float]] = None
    range_current: Optional[Tuple[float, float]] = None
    expanded_low: bool = False
    expanded_high: bool = False
    new_categories: List[Tuple[str, int]] = field(default_factory=list)
    missing_categories: List[str] = field(default_factory=list)
    unlisted_current: int = 0
    notes: List[str] = field(default_factory=list)
    verdict: str = OK


@dataclass
class DriftReport:
    """The full comparison result."""

    baseline_source: str
    current_source: str
    baseline_rows: int
    current_rows: int
    baseline_columns: int
    current_columns: int
    thresholds: Thresholds
    columns: List[ColumnDrift]
    added: List[Tuple[str, str]]  # (name, kind) present only in current
    removed: List[Tuple[str, str]]  # (name, kind) present only in baseline
    verdict: str

    @property
    def counts(self) -> Dict[str, int]:
        counts = {OK: 0, WARN: 0, ALERT: 0}
        for column in self.columns:
            counts[column.verdict] += 1
        return counts


def max_severity(a: str, b: str) -> str:
    return a if _SEVERITY_RANK[a] >= _SEVERITY_RANK[b] else b


def classify(value: float, warn: float, alert: float) -> str:
    if value >= alert:
        return ALERT
    if value >= warn:
        return WARN
    return OK


def compare(
    baseline: DatasetProfile,
    current: Dataset,
    thresholds: Optional[Thresholds] = None,
    null_tokens: FrozenSet[str] = DEFAULT_NULL_TOKENS,
    baseline_source: Optional[str] = None,
) -> DriftReport:
    """Compare a current snapshot against a baseline profile."""
    th = thresholds or Thresholds()
    current_profile = profile_dataset(
        current, bins=baseline.bins, top_k=baseline.top_k, null_tokens=null_tokens
    )
    current_by_name = {col.name: col for col in current_profile.columns}
    baseline_names = {col.name for col in baseline.columns}

    columns: List[ColumnDrift] = []
    for base_col in baseline.columns:
        cur_col = current_by_name.get(base_col.name)
        if cur_col is None:
            continue
        columns.append(
            _column_drift(base_col, cur_col, current.values[base_col.name], th, baseline.top_k, null_tokens)
        )
    removed = [(col.name, col.kind) for col in baseline.columns if col.name not in current_by_name]
    added = [(col.name, col.kind) for col in current_profile.columns if col.name not in baseline_names]

    verdict = OK
    for column in columns:
        verdict = max_severity(verdict, column.verdict)
    if added:
        verdict = max_severity(verdict, WARN)
    if removed:
        verdict = max_severity(verdict, ALERT)

    return DriftReport(
        baseline_source=baseline_source or baseline.source,
        current_source=current.source,
        baseline_rows=baseline.rows,
        current_rows=current.rows,
        baseline_columns=len(baseline.columns),
        current_columns=len(current_profile.columns),
        thresholds=th,
        columns=columns,
        added=added,
        removed=removed,
        verdict=verdict,
    )


def _column_drift(
    base: ColumnProfile,
    cur: ColumnProfile,
    current_raws: List[Optional[str]],
    th: Thresholds,
    top_k: int,
    null_tokens: FrozenSet[str],
) -> ColumnDrift:
    drift = ColumnDrift(
        name=base.name,
        kind_baseline=base.kind,
        kind_current=cur.kind,
        psi=None,
        buckets=[],
        null_rate_baseline=base.null_rate,
        null_rate_current=cur.null_rate,
        null_delta=cur.null_rate - base.null_rate,
    )
    severity = OK

    null_severity = classify(abs(drift.null_delta), th.null_warn, th.null_alert)
    if null_severity != OK:
        drift.notes.append(
            f"null rate {fmt_pct(base.null_rate)} -> {fmt_pct(cur.null_rate)}"
        )
    severity = max_severity(severity, null_severity)

    if base.kind == KIND_EMPTY or cur.kind == KIND_EMPTY:
        # An all-null side has no distribution to compare; the null-rate
        # delta above already carries the severity (1.0 delta -> alert).
        if base.kind == KIND_EMPTY and cur.kind != KIND_EMPTY:
            # A zero-row snapshot is "empty" too, but saying "entirely null"
            # about a column with no rows at all would be misleading.
            if base.total:
                drift.notes.append("column was entirely null in baseline")
            else:
                drift.notes.append("baseline snapshot has no rows")
        elif cur.kind == KIND_EMPTY and base.kind != KIND_EMPTY:
            if cur.total:
                drift.notes.append("column is entirely null in current")
            else:
                drift.notes.append("current snapshot has no rows")
        if base.kind == KIND_NUMERIC and base.minimum is not None and base.maximum is not None:
            drift.range_baseline = (base.minimum, base.maximum)
    elif base.kind != cur.kind:
        drift.notes.append(f"type changed: {base.kind} -> {cur.kind}")
        severity = max_severity(severity, ALERT)
    elif base.kind == KIND_NUMERIC:
        severity = max_severity(severity, _numeric_drift(base, cur, current_raws, drift, th, null_tokens))
    else:
        severity = max_severity(severity, _categorical_drift(base, cur, current_raws, drift, th, top_k, null_tokens))

    drift.verdict = severity
    return drift


def _numeric_drift(
    base: ColumnProfile,
    cur: ColumnProfile,
    current_raws: List[Optional[str]],
    drift: ColumnDrift,
    th: Thresholds,
    null_tokens: FrozenSet[str],
) -> str:
    severity = OK
    values = numeric_values(current_raws, null_tokens)
    current_counts = bin_values(base.edges, values)
    labels = bucket_labels(base.edges)
    drift.psi, drift.buckets = psi_from_counts(labels, base.bin_counts, current_counts)
    if drift.psi is not None:
        severity = max_severity(severity, classify(drift.psi, th.psi_warn, th.psi_alert))

    if base.minimum is not None and base.maximum is not None:
        drift.range_baseline = (base.minimum, base.maximum)
    if cur.minimum is not None and cur.maximum is not None:
        drift.range_current = (cur.minimum, cur.maximum)
    if drift.range_baseline and drift.range_current:
        if drift.range_current[0] < drift.range_baseline[0]:
            drift.expanded_low = True
            drift.notes.append(
                f"range widened low: min {fmt_num(drift.range_baseline[0])} -> {fmt_num(drift.range_current[0])}"
            )
        if drift.range_current[1] > drift.range_baseline[1]:
            drift.expanded_high = True
            drift.notes.append(
                f"range widened high: max {fmt_num(drift.range_baseline[1])} -> {fmt_num(drift.range_current[1])}"
            )
        if drift.expanded_low or drift.expanded_high:
            severity = max_severity(severity, WARN)
    return severity


def _categorical_drift(
    base: ColumnProfile,
    cur: ColumnProfile,
    current_raws: List[Optional[str]],
    drift: ColumnDrift,
    th: Thresholds,
    top_k: int,
    null_tokens: FrozenSet[str],
) -> str:
    severity = OK
    values, _ = split_nulls(current_raws, null_tokens)
    counter: "Counter[str]" = Counter(values)
    labels, baseline_counts, current_counts = align_categories(
        base.categories, base.other_count, counter
    )
    drift.psi, drift.buckets = psi_from_counts(labels, baseline_counts, current_counts)
    if drift.psi is not None:
        severity = max_severity(severity, classify(drift.psi, th.psi_warn, th.psi_alert))

    stored = {value for value, _ in base.categories}
    outside = {value: count for value, count in counter.items() if value not in stored}
    if outside:
        if base.other_count == 0:
            # The baseline's stored categories were exhaustive, so these
            # values are definitively new — a schema-of-values change.
            ranked = sorted(outside.items(), key=lambda item: (-item[1], item[0]))
            drift.new_categories = ranked[:MAX_LISTED_CATEGORIES]
            listed = ", ".join(f"{value} ({count})" for value, count in drift.new_categories)
            drift.notes.append(f"new categories: {listed}")
            severity = max_severity(severity, WARN)
        else:
            # The baseline had an (other) tail we did not store, so values
            # outside the top-K are not provably new; report them honestly.
            drift.unlisted_current = sum(outside.values())
            noun = "value" if drift.unlisted_current == 1 else "values"
            drift.notes.append(
                f"{drift.unlisted_current} current {noun} outside the stored top-{top_k}; counted in (other)"
            )
    missing = [value for value, _ in base.categories if counter.get(value, 0) == 0]
    if missing:
        drift.missing_categories = missing[:MAX_LISTED_CATEGORIES]
        drift.notes.append("missing categories: " + ", ".join(drift.missing_categories))
        severity = max_severity(severity, WARN)
    return severity
