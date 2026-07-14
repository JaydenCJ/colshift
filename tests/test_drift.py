"""The drift engine: verdict classification, notes, and schema changes."""

import pytest

from colshift.drift import Thresholds, compare
from colshift.profiles import profile_dataset, profile_from_dict, profile_to_dict
from tests.conftest import make_dataset


def _compare(base_cols, cur_cols, thresholds=None, **profile_kwargs):
    baseline = profile_dataset(make_dataset(base_cols, source="base.csv"), **profile_kwargs)
    current = make_dataset(cur_cols, source="cur.csv")
    return compare(baseline, current, thresholds=thresholds)


def _column(report, name):
    return next(c for c in report.columns if c.name == name)


def test_identical_snapshots_are_ok():
    cols = {"n": [str(v) for v in range(100)], "c": ["a", "b"] * 50}
    report = _compare(cols, dict(cols))
    assert report.verdict == "ok"
    assert all(c.verdict == "ok" for c in report.columns)
    assert report.counts == {"ok": 2, "warn": 0, "alert": 0}


def test_numeric_shift_crosses_warn_then_alert():
    base = {"n": [str(v) for v in range(100)]}
    nudged = {"n": [str(v + 8) for v in range(100)]}
    shoved = {"n": [str(v + 60) for v in range(100)]}
    warn = _column(_compare(base, nudged), "n")
    alert = _column(_compare(base, shoved), "n")
    assert warn.verdict == "warn"
    assert alert.verdict == "alert"
    assert alert.psi > warn.psi >= 0.1


def test_custom_psi_thresholds_are_honored():
    base = {"n": [str(v) for v in range(100)]}
    nudged = {"n": [str(v + 8) for v in range(100)]}
    strict = Thresholds(psi_warn=0.001, psi_alert=0.01)
    assert _column(_compare(base, nudged, thresholds=strict), "n").verdict == "alert"


def test_null_rate_delta_warn_and_alert():
    base = {"n": [str(v) for v in range(90)] + [""] * 10}  # 10% null
    warn_cur = {"n": [str(v) for v in range(82)] + [""] * 18}  # +8pp
    alert_cur = {"n": [str(v) for v in range(70)] + [""] * 30}  # +20pp
    assert _column(_compare(base, warn_cur), "n").verdict == "warn"
    assert _column(_compare(base, alert_cur), "n").verdict == "alert"


def test_null_rate_drop_also_counts_as_drift():
    # Nulls disappearing is a pipeline change too (e.g. a default got filled in).
    base = {"n": [str(v) for v in range(70)] + [""] * 30}
    cur = {"n": [str(v) for v in range(100)]}
    col = _column(_compare(base, cur), "n")
    assert col.null_delta == pytest.approx(-0.30)
    assert col.verdict == "alert"


def test_type_change_is_an_alert():
    base = {"n": [str(v) for v in range(10)]}
    cur = {"n": ["1", "2", "oops"] + [str(v) for v in range(7)]}
    col = _column(_compare(base, cur), "n")
    assert col.verdict == "alert"
    assert col.psi is None
    assert any("type changed: numeric -> categorical" in note for note in col.notes)


def test_range_expansion_is_warned_but_containment_is_not():
    base = {"n": [str(v) for v in range(10, 20)]}
    wider = {"n": ["5"] + [str(v) for v in range(11, 19)] + ["25"]}
    col = _column(_compare(base, wider), "n")
    assert col.expanded_low and col.expanded_high
    assert col.verdict != "ok"
    assert any("widened low" in note for note in col.notes)
    assert any("widened high" in note for note in col.notes)
    inside = {"n": [str(v) for v in range(12, 18)] + ["13", "15", "16", "14"]}
    contained = _column(_compare(base, inside), "n")
    assert not contained.expanded_low and not contained.expanded_high


def test_new_category_reported_when_baseline_was_exhaustive():
    base = {"c": ["a", "b"] * 50}
    cur = {"c": ["a", "b"] * 48 + ["zz"] * 4}
    col = _column(_compare(base, cur), "c")
    assert col.new_categories == [("zz", 4)]
    assert col.verdict in ("warn", "alert")


def test_values_beyond_stored_top_k_are_not_claimed_as_new():
    # With an (other) tail in the baseline we cannot prove novelty, so the
    # report must not say "new categories" — only an honest unlisted count.
    base = {"c": ["a"] * 6 + ["b"] * 5 + [f"tail{i}" for i in range(4)]}
    cur = {"c": ["a"] * 8 + ["b"] * 4 + ["mystery"] * 3}
    report = _compare(base, cur, top_k=2)
    col = _column(report, "c")
    assert col.new_categories == []
    assert col.unlisted_current == 3
    assert any("outside the stored top-2" in note for note in col.notes)


def test_missing_category_is_warned():
    base = {"c": ["a"] * 50 + ["b"] * 40 + ["fax"] * 10}
    cur = {"c": ["a"] * 55 + ["b"] * 45}
    col = _column(_compare(base, cur), "c")
    assert col.missing_categories == ["fax"]
    assert col.verdict in ("warn", "alert")


def test_added_column_raises_overall_to_warn():
    base = {"n": [str(v) for v in range(10)]}
    cur = {"n": [str(v) for v in range(10)], "extra": ["x"] * 10}
    report = _compare(base, cur)
    assert report.added == [("extra", "categorical")]
    assert report.verdict == "warn"


def test_removed_column_raises_overall_to_alert():
    base = {"n": [str(v) for v in range(10)], "gone": ["x"] * 10}
    cur = {"n": [str(v) for v in range(10)]}
    report = _compare(base, cur)
    assert report.removed == [("gone", "categorical")]
    assert report.verdict == "alert"


def test_all_null_transitions():
    # Both sides empty: nothing changed, nothing to flag.
    assert _column(_compare({"e": [""] * 10}, {"e": [""] * 10}), "e").verdict == "ok"
    # A column going entirely null is an alert (null delta 1.0).
    died = _column(_compare({"n": [str(v) for v in range(10)]}, {"n": [""] * 10}), "n")
    assert died.verdict == "alert"
    assert any("entirely null in current" in note for note in died.notes)
    # And so is a column coming back from the dead (delta -1.0).
    revived = _column(_compare({"e": [""] * 10}, {"e": [str(v) for v in range(10)]}), "e")
    assert revived.verdict == "alert"
    assert any("entirely null in baseline" in note for note in revived.notes)
    # A zero-row current snapshot must not claim the column is "entirely
    # null" — there are no rows to be null; the note says so instead.
    vanished = _column(_compare({"n": [str(v) for v in range(10)]}, {"n": []}), "n")
    assert any("no rows" in note for note in vanished.notes)
    assert not any("entirely null" in note for note in vanished.notes)


def test_constant_baseline_still_sees_upward_drift():
    base = {"n": ["7"] * 100}
    cur = {"n": ["7"] * 40 + ["9"] * 60}
    col = _column(_compare(base, cur), "n")
    assert col.psi > 0.25
    assert col.verdict == "alert"


def test_profile_baseline_matches_raw_baseline_exactly():
    # The flagship consistency guarantee: committing a profile and comparing
    # against it must give the same answer as keeping the raw baseline.
    base = {
        "n": [str(v) for v in range(200)],
        "c": ["red", "blue", "green", "red"] * 50,
    }
    cur = {
        "n": [str(v + 40) for v in range(200)],
        "c": ["red", "blue"] * 90 + ["violet"] * 20,
    }
    baseline_profile = profile_dataset(make_dataset(base, source="base.csv"))
    rehydrated = profile_from_dict(profile_to_dict(baseline_profile))
    direct = compare(baseline_profile, make_dataset(cur, source="cur.csv"))
    via_profile = compare(rehydrated, make_dataset(cur, source="cur.csv"))
    assert direct.verdict == via_profile.verdict
    for a, b in zip(direct.columns, via_profile.columns):
        assert a.psi == b.psi
        assert a.verdict == b.verdict
        assert a.notes == b.notes


def test_report_column_order_follows_baseline():
    base = {"b": ["1"] * 5, "a": ["x"] * 5}
    cur = {"a": ["x"] * 5, "b": ["1"] * 5}
    report = _compare(base, cur)
    assert [c.name for c in report.columns] == ["b", "a"]
