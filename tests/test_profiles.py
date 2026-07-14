"""Profiles: building, top-K category ranking, and JSON round-trips."""

import pytest

from colshift.errors import ProfileError
from colshift.profiles import (
    PROFILE_SCHEMA,
    profile_column,
    profile_dataset,
    profile_from_dict,
    profile_to_dict,
)
from tests.conftest import make_dataset


def test_numeric_column_stats():
    col = profile_column("n", [str(v) for v in range(1, 11)])
    assert col.kind == "numeric"
    assert col.total == 10
    assert col.nulls == 0
    assert col.distinct == 10
    assert col.minimum == 1.0
    assert col.maximum == 10.0
    assert col.mean == pytest.approx(5.5)
    assert col.p50 == pytest.approx(5.5)


def test_numeric_bin_counts_sum_to_non_null_count():
    col = profile_column("n", [str(v) for v in range(100)] + ["", "NULL"])
    assert col.nulls == 2
    assert sum(col.bin_counts) == 100
    assert len(col.bin_counts) == len(col.edges) + 1


def test_null_tokens_are_respected():
    col = profile_column("n", ["1", "2", "-"], null_tokens=frozenset({"", "-"}))
    assert col.kind == "numeric"
    assert col.nulls == 1


def test_categorical_top_k_ranking_and_other_tail():
    # b and c tie at 2; alphabetical order breaks the tie deterministically.
    raws = ["a"] * 3 + ["c"] * 2 + ["b"] * 2 + ["d"]
    col = profile_column("c", raws, top_k=3)
    assert col.categories == [("a", 3), ("b", 2), ("c", 2)]
    assert col.other_count == 1
    wide = profile_column("c", [f"v{i}" for i in range(30)], top_k=20)
    assert len(wide.categories) == 20
    assert wide.other_count == 10


def test_empty_column_and_zero_row_null_rates():
    col = profile_column("e", ["", None, "NULL"])
    assert col.kind == "empty"
    assert col.null_rate == 1.0
    assert profile_column("e", []).null_rate == 0.0


def test_profile_dataset_preserves_column_order():
    ds = make_dataset({"b": ["1"], "a": ["x"]})
    profile = profile_dataset(ds)
    assert [c.name for c in profile.columns] == ["b", "a"]


def test_roundtrip_through_json_dict():
    ds = make_dataset(
        {
            "n": [str(v) for v in range(50)],
            "c": ["red", "blue", "red", "green"] * 12 + ["red", ""],
            "e": [""] * 50,
        }
    )
    original = profile_dataset(ds, bins=5, top_k=2)
    data = profile_to_dict(original)
    assert data["schema_version"] == PROFILE_SCHEMA
    assert data["options"] == {"bins": 5, "top_k": 2}
    restored = profile_from_dict(data)
    assert restored.rows == original.rows
    assert restored.bins == 5 and restored.top_k == 2
    for a, b in zip(original.columns, restored.columns):
        assert a == b


def test_from_dict_rejects_wrong_schema_or_non_object():
    with pytest.raises(ProfileError, match="schema_version"):
        profile_from_dict({"schema_version": "something-else/9"})
    with pytest.raises(ProfileError, match="JSON object"):
        profile_from_dict([1, 2, 3])


def test_from_dict_rejects_bad_bin_counts_length():
    ds = make_dataset({"n": [str(v) for v in range(50)]})
    data = profile_to_dict(profile_dataset(ds))
    data["columns"][0]["bin_counts"] = [1, 2]  # wrong: must be len(edges)+1
    with pytest.raises(ProfileError, match="bin counts"):
        profile_from_dict(data)


def test_from_dict_rejects_malformed_categories_and_rows():
    ds = make_dataset({"c": ["x", "y"]})
    data = profile_to_dict(profile_dataset(ds))
    data["columns"][0]["categories"] = [["x"]]  # missing the count
    with pytest.raises(ProfileError, match="category"):
        profile_from_dict(data)
    with pytest.raises(ProfileError, match="rows"):
        profile_from_dict({"schema_version": PROFILE_SCHEMA, "rows": -1})
