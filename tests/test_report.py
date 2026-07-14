"""Report rendering: markdown structure, JSON schema, and determinism."""

import json

from colshift.drift import compare
from colshift.profiles import profile_dataset
from colshift.report import REPORT_SCHEMA, render_json, render_markdown, report_to_dict
from tests.conftest import make_dataset


def _drifted_report():
    base = make_dataset(
        {
            "amount": [str(v) for v in range(100)],
            "region": ["north", "south"] * 50,
            "steady": ["1", "2"] * 50,
        },
        source="base.csv",
    )
    cur = make_dataset(
        {
            "amount": [str(v + 60) for v in range(100)],
            "region": ["north"] * 90 + ["atlantis"] * 10,
            "steady": ["1", "2"] * 50,
        },
        source="cur.csv",
    )
    return compare(profile_dataset(base), cur)


def _clean_report():
    cols = {"n": [str(v) for v in range(50)]}
    base = make_dataset(cols, source="base.csv")
    cur = make_dataset(dict(cols), source="cur.csv")
    return compare(profile_dataset(base), cur)


def test_markdown_has_title_sources_and_verdict():
    text = render_markdown(_drifted_report())
    assert text.startswith("# colshift drift report\n")
    assert "`base.csv`" in text and "`cur.csv`" in text
    assert "**Verdict: ALERT**" in text
    assert "**Verdict: OK**" in render_markdown(_clean_report())


def test_markdown_summary_has_a_row_per_compared_column():
    report = _drifted_report()
    text = render_markdown(report)
    for column in report.columns:
        assert f"| {column.name} |" in text


def test_markdown_details_only_for_drifted_columns():
    text = render_markdown(_drifted_report())
    assert "### amount — ALERT" in text
    assert "### steady" not in text
    assert "| Bucket | Baseline | Current | PSI part |" in text


def test_markdown_clean_report_says_so():
    text = render_markdown(_clean_report())
    assert "No column crossed the warn threshold." in text
    assert "No columns were added or removed." in text


def test_markdown_pluralizes_the_compared_column_count():
    # One compared column must not read "1 columns" (and vice versa).
    assert "across 1 compared column." in render_markdown(_clean_report())
    assert "across 3 compared columns." in render_markdown(_drifted_report())


def test_markdown_escapes_pipes_in_names():
    base = make_dataset({"a|b": ["x", "y"]}, source="base.csv")
    cur = make_dataset({"a|b": ["x", "x"]}, source="cur.csv")
    text = render_markdown(compare(profile_dataset(base), cur))
    assert "a\\|b" in text


def test_markdown_ends_with_thresholds_footer():
    text = render_markdown(_drifted_report())
    assert text.rstrip().endswith("alert >= 15pp.")


def test_json_is_valid_and_schema_tagged():
    data = json.loads(render_json(_drifted_report()))
    assert data["schema_version"] == REPORT_SCHEMA
    assert data["verdict"] == "alert"
    assert data["baseline"]["rows"] == 100
    assert data["current"]["source"] == "cur.csv"


def test_json_column_entries_carry_the_essentials():
    data = json.loads(render_json(_drifted_report()))
    amount = next(c for c in data["columns"] if c["name"] == "amount")
    assert amount["verdict"] == "alert"
    assert amount["psi"] > 0.25
    assert amount["range"]["expanded_high"] is True
    region = next(c for c in data["columns"] if c["name"] == "region")
    assert region["new_categories"] == [{"value": "atlantis", "count": 10}]
    assert "missing_categories" in region  # "south" vanished entirely


def test_json_counts_match_column_verdicts():
    data = json.loads(render_json(_drifted_report()))
    tally = {"ok": 0, "warn": 0, "alert": 0}
    for column in data["columns"]:
        tally[column["verdict"]] += 1
    assert data["counts"] == tally


def test_json_rendering_is_deterministic_and_ordered():
    a = render_json(_drifted_report())
    b = render_json(_drifted_report())
    assert a == b
    data = json.loads(a)
    assert [c["name"] for c in data["columns"]] == ["amount", "region", "steady"]
    # Determinism is a feature: the same inputs must produce byte-identical
    # reports, so nothing time- or environment-dependent may leak in.
    assert "time" not in a and "date" not in a


def test_report_to_dict_thresholds_roundtrip():
    data = report_to_dict(_drifted_report())
    assert data["thresholds"] == {
        "psi_warn": 0.10,
        "psi_alert": 0.25,
        "null_warn": 0.05,
        "null_alert": 0.15,
    }
