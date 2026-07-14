"""Null detection and column type inference.

These rules decide everything downstream (which PSI variant runs, what the
null-rate deltas are), so the edge cases here are load-bearing.
"""

from colshift.inference import (
    DEFAULT_NULL_TOKENS,
    infer_kind,
    is_null,
    numeric_values,
    parse_number,
    split_nulls,
)


def test_none_empty_and_whitespace_are_null():
    assert is_null(None)
    assert is_null("")
    assert is_null("   ")
    assert is_null("\t")


def test_default_null_tokens_cover_common_spellings_even_padded():
    # Spreadsheet exports pad cells; " NA " must still read as null.
    for token in ("null", "NULL", "None", "NaN", "nan", "NA", "N/A", "#N/A", "  NA  "):
        assert is_null(token), token


def test_regular_values_are_not_null():
    for value in ("0", "false", "north", "NAND", "n/available"):
        assert not is_null(value), value


def test_custom_null_tokens_replace_defaults():
    tokens = frozenset({"", "-"})
    assert is_null("-", tokens)
    # "NA" is a real value under the custom set (e.g. the North America region).
    assert not is_null("NA", tokens)


def test_parse_number_accepts_int_float_scientific_signed():
    assert parse_number("42") == 42.0
    assert parse_number("-3.5") == -3.5
    assert parse_number("+0.25") == 0.25
    assert parse_number("1e3") == 1000.0
    assert parse_number(" 7 ") == 7.0


def test_parse_number_rejects_text_and_specials():
    # float() would happily accept "1_000", "inf" and "nan" — we must not,
    # or one stray token flips a whole column's kind.
    for bad in ("abc", "", "1_000", "inf", "-inf", "nan", "12px", "1,000"):
        assert parse_number(bad) is None, bad


def test_infer_kind_covers_all_three_kinds():
    assert infer_kind(["1", "2.5", "-3", "1e2"]) == "numeric"
    # One stray string makes the whole column categorical.
    assert infer_kind(["1", "2", "oops"]) == "categorical"
    assert infer_kind([]) == "empty"


def test_split_nulls_and_numeric_values():
    values, nulls = split_nulls(["a", None, "", "NULL", "b"], DEFAULT_NULL_TOKENS)
    assert values == ["a", "b"]
    assert nulls == 3
    assert numeric_values(["1", None, "2.5", "NaN"]) == [1.0, 2.5]
