"""Snapshot loading: CSV/TSV/JSONL parsing, normalization, and error paths."""

import pytest

from colshift.errors import InputError
from colshift.loaders import load_table


def test_csv_basic(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("a,b\n1,x\n2,y\n", encoding="utf-8")
    ds = load_table(path)
    assert ds.columns == ["a", "b"]
    assert ds.rows == 2
    assert ds.values["a"] == ["1", "2"]
    assert ds.values["b"] == ["x", "y"]
    # Spreadsheet exports prepend a BOM; the first column name must not
    # silently become "﻿a".
    bom = tmp_path / "bom.csv"
    bom.write_bytes(b"\xef\xbb\xbfa,b\n1,x\n")
    assert load_table(bom).columns == ["a", "b"]


def test_tsv_extension_and_delimiter_override(tmp_path):
    tsv = tmp_path / "data.tsv"
    tsv.write_text("a\tb\n1\tx\n", encoding="utf-8")
    assert load_table(tsv).values["b"] == ["x"]
    semi = tmp_path / "data.csv"
    semi.write_text("a;b\n1;x\n", encoding="utf-8")
    assert load_table(semi, delimiter=";").columns == ["a", "b"]


def test_short_rows_padded_with_null(tmp_path):
    # Exporters routinely drop trailing empty cells; that is not an error.
    path = tmp_path / "data.csv"
    path.write_text("a,b,c\n1,x\n", encoding="utf-8")
    assert load_table(path).values["c"] == [None]


def test_long_row_is_an_error_with_row_number(tmp_path):
    # Extra fields always mean a quoting/delimiter problem worth surfacing.
    path = tmp_path / "data.csv"
    path.write_text("a,b\n1,x,EXTRA\n", encoding="utf-8")
    with pytest.raises(InputError, match="row 2"):
        load_table(path)


def test_duplicate_header_is_an_error(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("a,a\n1,2\n", encoding="utf-8")
    with pytest.raises(InputError, match="duplicate column name 'a'"):
        load_table(path)


def test_header_only_and_blank_lines(tmp_path):
    header_only = tmp_path / "empty.csv"
    header_only.write_text("a,b\n", encoding="utf-8")
    assert load_table(header_only).rows == 0
    sparse = tmp_path / "sparse.csv"
    sparse.write_text("a,b\n1,x\n\n2,y\n", encoding="utf-8")
    assert load_table(sparse).rows == 2  # blank lines skipped, not rows of nulls


def test_completely_empty_csv_is_an_error(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(InputError, match="header row is required"):
        load_table(path)


def test_jsonl_scalars_are_normalized(tmp_path):
    path = tmp_path / "data.jsonl"
    path.write_text(
        '{"n": 1, "f": 2.5, "b": true, "s": "hi", "z": null}\n', encoding="utf-8"
    )
    ds = load_table(path)
    assert ds.values["n"] == ["1"]
    assert ds.values["f"] == ["2.5"]
    assert ds.values["b"] == ["true"]
    assert ds.values["s"] == ["hi"]
    assert ds.values["z"] == [None]


def test_jsonl_missing_keys_become_null_and_order_is_first_seen(tmp_path):
    path = tmp_path / "data.jsonl"
    path.write_text('{"a": 1}\n{"b": 2, "a": 3}\n', encoding="utf-8")
    ds = load_table(path)
    assert ds.columns == ["a", "b"]
    assert ds.values["b"] == [None, "2"]


def test_jsonl_nested_values_become_canonical_tokens(tmp_path):
    # Key order must not matter: both spellings are the same category.
    path = tmp_path / "data.jsonl"
    path.write_text('{"m": {"y": 2, "x": 1}}\n{"m": {"x": 1, "y": 2}}\n', encoding="utf-8")
    ds = load_table(path)
    assert ds.values["m"][0] == ds.values["m"][1] == '{"x":1,"y":2}'


def test_jsonl_error_paths_report_line_numbers(tmp_path):
    non_object = tmp_path / "a.jsonl"
    non_object.write_text("[1, 2]\n", encoding="utf-8")
    with pytest.raises(InputError, match="expected an object"):
        load_table(non_object)
    invalid = tmp_path / "b.jsonl"
    invalid.write_text('{"a": 1}\n{oops}\n', encoding="utf-8")
    with pytest.raises(InputError, match="line 2"):
        load_table(invalid)


def test_unsupported_extension_and_missing_file_are_errors(tmp_path):
    unknown = tmp_path / "data.parquet"
    unknown.write_text("x", encoding="utf-8")
    with pytest.raises(InputError, match="unsupported snapshot extension"):
        load_table(unknown)
    with pytest.raises(InputError, match="not found"):
        load_table(tmp_path / "nope.csv")
