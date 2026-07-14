"""Population Stability Index over aligned buckets.

PSI = sum over buckets of ``(q - p) * ln(q / p)`` where ``p`` is the
baseline share and ``q`` the current share of the bucket. Every term is
non-negative, so per-bucket contributions localize the drift. Empty
shares are floored at EPSILON so a bucket that appears or vanishes
contributes a large-but-finite amount instead of infinity.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

#: Floor applied to bucket shares before taking the log ratio.
EPSILON = 1e-6

#: Label of the aggregate bucket for categories beyond the stored top-K.
OTHER_LABEL = "(other)"


@dataclass
class Bucket:
    """One aligned bucket with its counts, shares, and PSI contribution."""

    label: str
    baseline_count: int
    current_count: int
    baseline_share: float
    current_share: float
    contribution: float


def psi_from_counts(
    labels: Sequence[str],
    baseline_counts: Sequence[int],
    current_counts: Sequence[int],
) -> Tuple[Optional[float], List[Bucket]]:
    """PSI plus per-bucket breakdown; None when either side has no values."""
    if len(labels) != len(baseline_counts) or len(labels) != len(current_counts):
        raise ValueError("labels and count sequences must have equal length")
    baseline_total = sum(baseline_counts)
    current_total = sum(current_counts)
    if baseline_total == 0 or current_total == 0:
        return None, []
    buckets: List[Bucket] = []
    total = 0.0
    for label, b_count, c_count in zip(labels, baseline_counts, current_counts):
        p = b_count / baseline_total
        q = c_count / current_total
        p_safe = max(p, EPSILON)
        q_safe = max(q, EPSILON)
        contribution = (q_safe - p_safe) * math.log(q_safe / p_safe)
        total += contribution
        buckets.append(
            Bucket(
                label=label,
                baseline_count=b_count,
                current_count=c_count,
                baseline_share=p,
                current_share=q,
                contribution=contribution,
            )
        )
    return total, buckets


def align_categories(
    baseline_categories: Sequence[Tuple[str, int]],
    baseline_other: int,
    current_counter: "Counter[str]",
) -> Tuple[List[str], List[int], List[int]]:
    """Align a current value counter onto the baseline's stored categories.

    Buckets are the baseline's top-K categories in stored order, plus one
    ``(other)`` bucket whenever either side has values beyond them — the
    same shape on both sides, which PSI requires.
    """
    labels = [value for value, _ in baseline_categories]
    baseline_counts = [count for _, count in baseline_categories]
    current_counts = [current_counter.get(value, 0) for value in labels]
    current_other = sum(current_counter.values()) - sum(current_counts)
    if baseline_other > 0 or current_other > 0:
        labels.append(OTHER_LABEL)
        baseline_counts.append(baseline_other)
        current_counts.append(current_other)
    return labels, baseline_counts, current_counts
