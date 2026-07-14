"""End-to-end CLI behavior: exit codes, formats, filters, and error paths.

Tests call ``colshift.cli.main`` directly with argv lists — the same code
path as the console script, without subprocess overhead.
"""

import json

from colshift import __version__
from colshift.cli import main
from tests.conftest import write_csv


def _drifted_pair(tmp_path):
    baseline = write_csv(
        tmp_path / "baseline.csv",
        ["amount", "region"],
        [[str(v), r] for v, r in zip(range(100), ["north", "south"] * 50)],
    )
    current = write_csv(
        tmp_path / "current.csv",
        ["amount", "region"],
        [[str(v + 60), r] for v, r in zip(range(100), ["north"] * 90 + ["atlantis"] * 10)],
    )
    return baseline, current


def test_version_flag_and_bare_invocation(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"colshift {__version__}"
    assert main([]) == 2  # a subcommand is required


def test_compare_identical_exits_zero(baseline_csv, identical_current_csv, capsys):
    rc = main(["compare", str(baseline_csv), str(identical_current_csv)])
    assert rc == 0
    assert "**Verdict: OK**" in capsys.readouterr().out


def test_compare_drift_exits_one_unless_fail_on_never(tmp_path, capsys):
    baseline, current = _drifted_pair(tmp_path)
    assert main(["compare", str(baseline), str(current)]) == 1
    assert "**Verdict: ALERT**" in capsys.readouterr().out
    assert main(["compare", str(baseline), str(current), "--fail-on", "never"]) == 0
    assert "ALERT" in capsys.readouterr().out  # still reported, just not fatal


def test_fail_on_warn_triggers_on_warn_only_drift(tmp_path, capsys):
    baseline = write_csv(tmp_path / "b.csv", ["n"], [[str(v)] for v in range(100)])
    current = write_csv(tmp_path / "c.csv", ["n"], [[str(v + 8)] for v in range(100)])
    assert main(["compare", str(baseline), str(current)]) == 0  # warn < alert gate
    assert main(["compare", str(baseline), str(current), "--fail-on", "warn"]) == 1
    capsys.readouterr()


def test_format_json_emits_parseable_report(tmp_path, capsys):
    baseline, current = _drifted_pair(tmp_path)
    main(["compare", str(baseline), str(current), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert data["schema_version"] == "colshift-report/1"
    assert data["verdict"] == "alert"


def test_out_writes_file_and_keeps_stdout_quiet(tmp_path, capsys):
    baseline, current = _drifted_pair(tmp_path)
    target = tmp_path / "report.md"
    main(["compare", str(baseline), str(current), "--out", str(target)])
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "report written to" in captured.err
    assert "# colshift drift report" in target.read_text(encoding="utf-8")


def test_json_out_writes_json_alongside_markdown_stdout(tmp_path, capsys):
    baseline, current = _drifted_pair(tmp_path)
    target = tmp_path / "report.json"
    main(["compare", str(baseline), str(current), "--json-out", str(target)])
    assert "# colshift drift report" in capsys.readouterr().out
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["verdict"] == "alert"


def test_profile_then_compare_matches_direct_compare(tmp_path, capsys):
    baseline, current = _drifted_pair(tmp_path)
    profile_path = tmp_path / "profile.json"
    assert main(["profile", str(baseline), "-o", str(profile_path)]) == 0
    capsys.readouterr()

    main(["compare", str(baseline), str(current), "--format", "json"])
    direct = json.loads(capsys.readouterr().out)
    rc = main(["compare", str(profile_path), str(current), "--format", "json"])
    via_profile = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert via_profile["verdict"] == direct["verdict"]
    assert via_profile["columns"] == direct["columns"]


def test_profile_to_stdout_without_out_flag(baseline_csv, capsys):
    assert main(["profile", str(baseline_csv)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["schema_version"] == "colshift-profile/1"
    assert data["rows"] == 100


def test_columns_and_exclude_filters(tmp_path, capsys):
    baseline, current = _drifted_pair(tmp_path)
    rc = main(["compare", str(baseline), str(current), "--columns", "region", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert [c["name"] for c in data["columns"]] == ["region"]
    assert rc == 1  # region alone still alerts (new category + share shift)
    main(["compare", str(baseline), str(current), "--exclude", "amount", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert [c["name"] for c in data["columns"]] == ["region"]


def test_unknown_column_in_columns_flag_is_an_error(tmp_path, capsys):
    baseline, current = _drifted_pair(tmp_path)
    rc = main(["compare", str(baseline), str(current), "--columns", "nope"])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


def test_bad_inputs_exit_two_with_a_message(tmp_path, baseline_csv, capsys):
    # Missing snapshot file.
    assert main(["compare", str(tmp_path / "ghost.csv"), str(baseline_csv)]) == 2
    assert "colshift: error:" in capsys.readouterr().err
    # A JSON baseline that is not a colshift profile.
    bogus = tmp_path / "not-a-profile.json"
    bogus.write_text('{"hello": "world"}', encoding="utf-8")
    assert main(["compare", str(bogus), str(baseline_csv)]) == 2
    assert "not a colshift profile" in capsys.readouterr().err
    # A profile passed as the *current* snapshot.
    profile_path = tmp_path / "profile.json"
    main(["profile", str(baseline_csv), "-o", str(profile_path)])
    capsys.readouterr()
    assert main(["compare", str(baseline_csv), str(profile_path)]) == 2
    assert "current snapshot must be raw data" in capsys.readouterr().err


def test_option_validation_exits_two(tmp_path, baseline_csv, capsys):
    baseline, current = _drifted_pair(tmp_path)
    rc = main(["compare", str(baseline), str(current), "--psi-warn", "0.5", "--psi-alert", "0.1"])
    assert rc == 2
    assert "alert thresholds" in capsys.readouterr().err
    assert main(["profile", str(baseline_csv), "--bins", "1"]) == 2
    assert "--bins" in capsys.readouterr().err


def test_negative_warn_threshold_is_rejected(tmp_path, capsys):
    # A negative warn threshold would classify every column as drifted
    # (PSI and |null delta| are always >= 0), so it is surely a typo.
    baseline, current = _drifted_pair(tmp_path)
    rc = main(["compare", str(baseline), str(current), "--psi-warn", "-0.1"])
    assert rc == 2
    assert "must be >= 0" in capsys.readouterr().err


def test_custom_null_tokens_flow_through(tmp_path, capsys):
    baseline = write_csv(tmp_path / "b.csv", ["n"], [["1"], ["2"], ["3"], ["4"]])
    current = write_csv(tmp_path / "c.csv", ["n"], [["1"], ["2"], ["-"], ["-"]])
    main(["compare", str(baseline), str(current), "--null-tokens", ",-", "--format", "json",
          "--fail-on", "never"])
    data = json.loads(capsys.readouterr().out)
    assert data["columns"][0]["null_rate_current"] == 0.5


def test_delimiter_option_reaches_the_loader(tmp_path, capsys):
    baseline = tmp_path / "b.csv"
    baseline.write_text("a;b\n1;x\n2;y\n", encoding="utf-8")
    current = tmp_path / "c.csv"
    current.write_text("a;b\n1;x\n2;y\n", encoding="utf-8")
    rc = main(["compare", str(baseline), str(current), "--delimiter", ";"])
    assert rc == 0
    assert "**Verdict: OK**" in capsys.readouterr().out
