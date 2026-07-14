"""PSI math: hand-checkable values, smoothing, and category alignment."""

import math
from collections import Counter

import pytest

from colshift.psi import EPSILON, OTHER_LABEL, align_categories, psi_from_counts


def test_identical_shape_has_zero_psi_even_when_scaled():
    psi, buckets = psi_from_counts(["a", "b"], [50, 50], [50, 50])
    assert psi == 0.0
    assert all(b.contribution == 0.0 for b in buckets)
    # PSI compares shares, not counts: 3x the rows, same shape, zero drift.
    psi_scaled, _ = psi_from_counts(["a", "b"], [10, 30], [30, 90])
    assert psi_scaled == pytest.approx(0.0, abs=1e-12)


def test_known_two_bucket_shift():
    # p = (0.5, 0.5), q = (0.8, 0.2):
    # (0.8-0.5)ln(0.8/0.5) + (0.2-0.5)ln(0.2/0.5) = 0.141001 + 0.274887
    psi, _ = psi_from_counts(["a", "b"], [50, 50], [80, 20])
    assert psi == pytest.approx(0.415888, abs=1e-6)


def test_contributions_are_non_negative_and_sum_to_psi():
    psi, buckets = psi_from_counts(["a", "b", "c"], [10, 60, 30], [30, 30, 40])
    assert all(b.contribution >= 0.0 for b in buckets)
    assert psi == pytest.approx(sum(b.contribution for b in buckets))


def test_psi_is_symmetric_in_direction():
    # (q-p)ln(q/p) == (p-q)ln(p/q), so swapping snapshots keeps the PSI.
    forward, _ = psi_from_counts(["a", "b"], [70, 30], [40, 60])
    backward, _ = psi_from_counts(["a", "b"], [40, 60], [70, 30])
    assert forward == pytest.approx(backward)


def test_empty_bucket_is_smoothed_but_shares_stay_honest():
    # A category that vanishes entirely would make ln(q/p) blow up;
    # EPSILON flooring keeps the contribution large but finite. The floor
    # applies to the log ratio only — reported shares stay exact.
    psi, buckets = psi_from_counts(["a", "b"], [50, 50], [100, 0])
    assert math.isfinite(psi)
    vanished = buckets[1]
    expected = (EPSILON - 0.5) * math.log(EPSILON / 0.5)
    assert vanished.contribution == pytest.approx(expected)
    assert vanished.current_share == 0.0


def test_an_all_empty_side_yields_none():
    assert psi_from_counts(["a"], [0], [10]) == (None, [])
    assert psi_from_counts(["a"], [10], [0]) == (None, [])


def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        psi_from_counts(["a", "b"], [1], [1, 2])


def test_align_without_other_tail_and_with_baseline_tail():
    labels, base, cur = align_categories([("x", 6), ("y", 4)], 0, Counter({"x": 5, "y": 5}))
    assert labels == ["x", "y"]
    assert base == [6, 4]
    assert cur == [5, 5]
    labels, base, cur = align_categories([("x", 6)], 4, Counter({"x": 10}))
    assert labels == ["x", OTHER_LABEL]
    assert base == [6, 4]
    assert cur == [10, 0]


def test_align_adds_other_bucket_for_unseen_current_values():
    labels, base, cur = align_categories([("x", 6), ("y", 4)], 0, Counter({"x": 5, "z": 5}))
    assert labels == ["x", "y", OTHER_LABEL]
    assert base == [6, 4, 0]
    assert cur == [5, 0, 5]
