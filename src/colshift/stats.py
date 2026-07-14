"""Numeric helpers: summary statistics, quantile bin edges, binning, formatting.

Everything here is pure and deterministic; PSI lives in :mod:`colshift.psi`.
"""

from __future__ import annotations

import math
import statistics
from bisect import bisect_left
from typing import List, Optional, Sequence, Tuple


def sample_stdev(values: Sequence[float]) -> Optional[float]:
    """Sample standard deviation, or None when fewer than two values."""
    if len(values) < 2:
        return None
    return float(statistics.stdev(values))


def percentiles(values: Sequence[float]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """(p25, p50, p75) using the inclusive (type-7) method."""
    if not values:
        return (None, None, None)
    if len(values) == 1:
        v = float(values[0])
        return (v, v, v)
    q = statistics.quantiles(values, n=4, method="inclusive")
    return (float(q[0]), float(q[1]), float(q[2]))


def quantile_edges(values: Sequence[float], bins: int) -> List[float]:
    """Interior bin edges cut at baseline quantiles.

    Duplicate cut points (heavily repeated values) are collapsed so edges
    are strictly increasing; a constant column yields the single edge
    ``[c]``, giving the two buckets "<= c" and "> c" so that drift *above*
    a constant baseline still registers.
    """
    if not values or bins < 2:
        return []
    distinct = sorted(set(values))
    if len(distinct) == 1:
        return [float(distinct[0])]
    cuts = statistics.quantiles(values, n=bins, method="inclusive")
    edges: List[float] = []
    for cut in cuts:
        cut = float(cut)
        if not edges or cut > edges[-1]:
            edges.append(cut)
    return edges


def bin_values(edges: Sequence[float], values: Sequence[float]) -> List[int]:
    """Count values into len(edges)+1 buckets.

    Bucket i covers ``(edges[i-1], edges[i]]``; the outer buckets are
    open-ended, so every value lands somewhere. A value equal to an edge
    belongs to the lower bucket (upper bounds are inclusive).
    """
    counts = [0] * (len(edges) + 1)
    for value in values:
        counts[bisect_left(edges, value)] += 1
    return counts


def bucket_labels(edges: Sequence[float]) -> List[str]:
    """Human-readable labels matching :func:`bin_values` buckets."""
    if not edges:
        return ["all values"]
    labels = [f"<= {fmt_num(edges[0])}"]
    for low, high in zip(edges, edges[1:]):
        labels.append(f"{fmt_num(low)} - {fmt_num(high)}")
    labels.append(f"> {fmt_num(edges[-1])}")
    return labels


def fmt_num(value: Optional[float]) -> str:
    """Compact, deterministic number formatting for reports and labels."""
    if value is None:
        return "n/a"
    v = float(value)
    if math.isnan(v) or math.isinf(v):
        return "n/a"
    if v.is_integer() and abs(v) < 1e15:
        return format(int(v), ",")
    if 0.001 <= abs(v) < 1e6:
        text = format(v, ",.3f").rstrip("0").rstrip(".")
        return text if text and text != "-0" else "0"
    return format(v, ".3g")


def fmt_pct(rate: Optional[float]) -> str:
    """Format a 0..1 rate as a percentage with one decimal."""
    if rate is None:
        return "n/a"
    return f"{rate * 100:.1f}%"
