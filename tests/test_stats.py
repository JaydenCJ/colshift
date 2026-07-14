"""Quantile edges, binning, and number formatting.

Binning conventions (inclusive upper bounds, open outer buckets) must never
change silently: stored profiles depend on them.
"""

from colshift.stats import (
    bin_values,
    bucket_labels,
    fmt_num,
    fmt_pct,
    percentiles,
    quantile_edges,
    sample_stdev,
)


def test_decile_edges_of_uniform_range():
    values = [float(v) for v in range(1, 101)]
    edges = quantile_edges(values, 10)
    assert len(edges) == 9
    assert edges[0] == 10.9  # p10 of 1..100, inclusive method
    assert edges[-1] == 90.1


def test_edges_are_strictly_increasing_with_repeated_values():
    # 90% of the mass on one value collapses most cut points; duplicates
    # must be removed or bins would be zero-width.
    values = [5.0] * 90 + [float(v) for v in range(1, 11)]
    edges = quantile_edges(values, 10)
    assert edges == sorted(set(edges))


def test_degenerate_edge_cases():
    # A constant baseline still gets the two buckets "<= c" and "> c" so
    # values drifting above the constant register in PSI.
    assert quantile_edges([7.0, 7.0, 7.0], 10) == [7.0]
    assert quantile_edges([3.0], 10) == [3.0]
    assert quantile_edges([], 10) == []
    assert quantile_edges([1.0, 2.0], 1) == []


def test_binning_conventions():
    edges = [10.0, 20.0]
    # A value equal to an edge belongs to the lower bucket (inclusive upper
    # bounds); the outer buckets are open-ended so nothing is ever dropped.
    assert bin_values(edges, [10.0]) == [1, 0, 0]
    assert bin_values(edges, [20.0]) == [0, 1, 0]
    assert bin_values(edges, [-1e9]) == [1, 0, 0]
    assert bin_values(edges, [1e9]) == [0, 0, 1]


def test_bin_counts_sum_to_value_count():
    edges = [10.0, 20.0, 30.0]
    values = [float(v) for v in range(0, 45)]
    assert sum(bin_values(edges, values)) == len(values)


def test_bucket_labels_match_bucket_count():
    edges = [10.0, 20.0]
    labels = bucket_labels(edges)
    assert labels == ["<= 10", "10 - 20", "> 20"]
    assert len(labels) == len(bin_values(edges, [])) == 3
    assert bucket_labels([]) == ["all values"]


def test_fmt_num_integers_and_decimals():
    assert fmt_num(1234567.0) == "1,234,567"
    assert fmt_num(42.0) == "42"
    assert fmt_num(3.5) == "3.5"  # trailing zeros trimmed
    assert fmt_num(0.25) == "0.25"


def test_fmt_num_extremes_none_and_fmt_pct():
    assert "e" in fmt_num(12345678.9)
    assert "e" in fmt_num(0.00001)
    assert fmt_num(None) == "n/a"
    assert fmt_pct(0.178) == "17.8%"
    assert fmt_pct(0.0) == "0.0%"
    assert fmt_pct(None) == "n/a"


def test_percentiles_and_sample_stdev():
    p25, p50, p75 = percentiles([float(v) for v in range(1, 101)])
    assert (p25, p50, p75) == (25.75, 50.5, 75.25)
    assert percentiles([9.0]) == (9.0, 9.0, 9.0)
    assert sample_stdev([5.0]) is None
    assert abs(sample_stdev([2.0, 4.0]) - 1.4142135) < 1e-6
