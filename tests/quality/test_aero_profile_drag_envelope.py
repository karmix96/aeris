"""Unit tests for the profile-drag envelope QC validator (polar bridge)."""
from __future__ import annotations

import pandas as pd

from aeris.quality.aero_validators import _check_profile_drag_envelope


def _fresh_report() -> dict:
    return {"passed": True, "errors": [], "warnings": [], "metrics": {}}


def test_envelope_column_absent_is_skipped():
    df = pd.DataFrame({"cl": [0.1, 0.2], "cd": [0.01, 0.02]})
    report = _fresh_report()
    _check_profile_drag_envelope(df, {}, report)
    assert report["passed"] is True
    assert report["warnings"] == []
    assert report["metrics"].get("profile_drag_envelope") == "column_absent_skipped"


def test_envelope_all_zero_no_warning():
    df = pd.DataFrame({"profile_drag_n_extrapolated_strips": [0, 0, 0]})
    report = _fresh_report()
    _check_profile_drag_envelope(df, {}, report)
    assert report["passed"] is True
    assert report["warnings"] == []
    assert report["metrics"]["profile_drag_rows_with_extrapolation"] == 0
    assert report["metrics"]["profile_drag_total_extrapolated_strips"] == 0


def test_envelope_some_extrapolated_warns_but_passes():
    df = pd.DataFrame({"profile_drag_n_extrapolated_strips": [0, 2, 5, 0]})
    report = _fresh_report()
    _check_profile_drag_envelope(df, {}, report)
    assert report["passed"] is True  # warning-only, must not fail QC
    assert len(report["warnings"]) == 1
    assert report["metrics"]["profile_drag_rows_with_extrapolation"] == 2
    assert report["metrics"]["profile_drag_total_extrapolated_strips"] == 7


def test_envelope_registered_and_runs_in_strict():
    from aeris.quality.profiles import resolve_aero_profile

    _, validator_ids = resolve_aero_profile("strict")
    assert "aero_profile_drag_envelope_v1" in validator_ids
