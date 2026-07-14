"""Report renderers: markdown for humans, JSON for pipelines.

Both renderers are pure functions of a :class:`~colshift.drift.DriftReport`
and fully deterministic — no timestamps, no environment lookups — so the
same pair of snapshots always produces byte-identical reports.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from . import __version__
from .drift import OK, ColumnDrift, DriftReport
from .stats import fmt_num, fmt_pct

#: Schema marker written into every report JSON document.
REPORT_SCHEMA = "colshift-report/1"

#: How many buckets each drifted column shows in the markdown details.
MAX_DETAIL_BUCKETS = 6


def _md_escape(text: str) -> str:
    """Escape characters that would break a markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ")


def _fmt_psi(psi: Optional[float]) -> str:
    return "n/a" if psi is None else f"{psi:.3f}"


def _type_cell(column: ColumnDrift) -> str:
    if column.kind_baseline == column.kind_current:
        return column.kind_baseline
    return f"{column.kind_baseline} -> {column.kind_current}"


def render_markdown(report: DriftReport) -> str:
    """Render the full markdown drift report."""
    lines: List[str] = []
    lines.append("# colshift drift report")
    lines.append("")
    lines.append("| Snapshot | Source | Rows | Columns |")
    lines.append("|---|---|---:|---:|")
    lines.append(
        f"| baseline | `{_md_escape(report.baseline_source)}` | {report.baseline_rows:,} | {report.baseline_columns} |"
    )
    lines.append(
        f"| current | `{_md_escape(report.current_source)}` | {report.current_rows:,} | {report.current_columns} |"
    )
    lines.append("")
    counts = report.counts
    compared = len(report.columns)
    noun = "column" if compared == 1 else "columns"
    lines.append(
        f"**Verdict: {report.verdict.upper()}** — {counts['alert']} alert, {counts['warn']} warn, "
        f"{counts['ok']} ok across {compared} compared {noun}."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Column | Type | PSI | Nulls (base -> cur) | Verdict | Notes |")
    lines.append("|---|---|---:|---|---|---|")
    for column in report.columns:
        notes = "; ".join(_md_escape(note) for note in column.notes) or "—"
        lines.append(
            f"| {_md_escape(column.name)} | {_type_cell(column)} | {_fmt_psi(column.psi)} "
            f"| {fmt_pct(column.null_rate_baseline)} -> {fmt_pct(column.null_rate_current)} "
            f"| {column.verdict.upper()} | {notes} |"
        )
    lines.append("")
    lines.append("## Schema changes")
    lines.append("")
    if not report.added and not report.removed:
        lines.append("No columns were added or removed.")
    else:
        for name, kind in report.added:
            lines.append(f"- added in current: `{_md_escape(name)}` ({kind})")
        for name, kind in report.removed:
            lines.append(f"- removed from baseline: `{_md_escape(name)}` ({kind})")
    lines.append("")
    lines.append("## Column details")
    lines.append("")
    drifted = [column for column in report.columns if column.verdict != OK]
    if not drifted:
        lines.append("No column crossed the warn threshold.")
        lines.append("")
    for column in drifted:
        lines.extend(_column_details(column))
    th = report.thresholds
    lines.append(
        f"Thresholds: PSI warn >= {th.psi_warn:g}, alert >= {th.psi_alert:g} · "
        f"null-rate delta warn >= {th.null_warn * 100:g}pp, alert >= {th.null_alert * 100:g}pp."
    )
    return "\n".join(lines) + "\n"


def _column_details(column: ColumnDrift) -> List[str]:
    lines: List[str] = []
    lines.append(f"### {_md_escape(column.name)} — {column.verdict.upper()}")
    lines.append("")
    facts = [f"PSI {_fmt_psi(column.psi)}"]
    facts.append(
        f"nulls {fmt_pct(column.null_rate_baseline)} -> {fmt_pct(column.null_rate_current)}"
    )
    if column.range_baseline and column.range_current:
        facts.append(
            f"range {fmt_num(column.range_baseline[0])} – {fmt_num(column.range_baseline[1])} "
            f"-> {fmt_num(column.range_current[0])} – {fmt_num(column.range_current[1])}"
        )
    lines.append("- " + " · ".join(facts))
    for note in column.notes:
        lines.append(f"- {note}")
    if column.buckets:
        top = sorted(column.buckets, key=lambda b: -abs(b.contribution))[:MAX_DETAIL_BUCKETS]
        lines.append("")
        lines.append("| Bucket | Baseline | Current | PSI part |")
        lines.append("|---|---:|---:|---:|")
        for bucket in top:
            lines.append(
                f"| {_md_escape(bucket.label)} "
                f"| {bucket.baseline_count:,} ({fmt_pct(bucket.baseline_share)}) "
                f"| {bucket.current_count:,} ({fmt_pct(bucket.current_share)}) "
                f"| {bucket.contribution:.3f} |"
            )
    lines.append("")
    return lines


def report_to_dict(report: DriftReport) -> Dict[str, object]:
    """Serialize a report to the ``colshift-report/1`` JSON structure."""
    th = report.thresholds
    return {
        "schema_version": REPORT_SCHEMA,
        "generated_by": f"colshift {__version__}",
        "baseline": {
            "source": report.baseline_source,
            "rows": report.baseline_rows,
            "columns": report.baseline_columns,
        },
        "current": {
            "source": report.current_source,
            "rows": report.current_rows,
            "columns": report.current_columns,
        },
        "thresholds": {
            "psi_warn": th.psi_warn,
            "psi_alert": th.psi_alert,
            "null_warn": th.null_warn,
            "null_alert": th.null_alert,
        },
        "verdict": report.verdict,
        "counts": report.counts,
        "schema_changes": {
            "added": [{"name": name, "kind": kind} for name, kind in report.added],
            "removed": [{"name": name, "kind": kind} for name, kind in report.removed],
        },
        "columns": [_column_to_dict(column) for column in report.columns],
    }


def _column_to_dict(column: ColumnDrift) -> Dict[str, object]:
    entry: Dict[str, object] = {
        "name": column.name,
        "kind_baseline": column.kind_baseline,
        "kind_current": column.kind_current,
        "verdict": column.verdict,
        "psi": _round(column.psi),
        "null_rate_baseline": _round(column.null_rate_baseline),
        "null_rate_current": _round(column.null_rate_current),
        "null_delta": _round(column.null_delta),
        "notes": list(column.notes),
        "buckets": [
            {
                "label": bucket.label,
                "baseline_count": bucket.baseline_count,
                "current_count": bucket.current_count,
                "baseline_share": _round(bucket.baseline_share),
                "current_share": _round(bucket.current_share),
                "contribution": _round(bucket.contribution),
            }
            for bucket in column.buckets
        ],
    }
    if column.range_baseline or column.range_current:
        entry["range"] = {
            "baseline": list(column.range_baseline) if column.range_baseline else None,
            "current": list(column.range_current) if column.range_current else None,
            "expanded_low": column.expanded_low,
            "expanded_high": column.expanded_high,
        }
    if column.new_categories:
        entry["new_categories"] = [
            {"value": value, "count": count} for value, count in column.new_categories
        ]
    if column.missing_categories:
        entry["missing_categories"] = list(column.missing_categories)
    if column.unlisted_current:
        entry["unlisted_current"] = column.unlisted_current
    return entry


def render_json(report: DriftReport) -> str:
    """Render the JSON drift report (sorted keys, stable across runs)."""
    return json.dumps(report_to_dict(report), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _round(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 6)
