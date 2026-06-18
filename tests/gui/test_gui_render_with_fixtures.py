"""GUI render test WITH minimal artifacts — exercises data-dependent paths.

This is the test class that catches bugs like the aero sweep "Polar curves"
KeyError (BUG-1: the code referenced df["Elevon [°]"] but the column is "δe [°]").
The empty-state smoke test cannot catch these because the buggy branch only runs
when real sweep data with successful cases is present.

Strategy: fabricate the minimal directory + JSON structure the GUI reads for an
aero sweep, point the GUI at it, navigate to Aero → Inspect → select the sweep →
"Polar curves", and assert no exception.

Requires streamlit; skipped if the AppTest harness is unavailable.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = st_testing.AppTest

import aeris.gui.app as gui_app


def _seed_aero_sweep(root: Path) -> Path:
    """Create a minimal but realistic aero sweep run the GUI can inspect.

    Mirrors the structure read in pg_aero inspect:
      <run>/aero_sweep_manifest.json
        -> {"aero_sweep_result": {"cases": [ {case fields...}, ... ]}}
    The run folder name must contain '_sweep_' to be picked up by _aero_run_rows.
    Includes >1 distinct elevon (δe) value so the polar 'one curve per elevon'
    branch executes.
    """
    runs = root / "data" / "runs"
    sweep = runs / "20260101_000000_aero_sweep_fixture"
    sweep.mkdir(parents=True, exist_ok=True)

    cases = []
    idx = 0
    for de in (-5.0, 0.0, 5.0):           # >1 elevon → exercises per-elevon polar
        for alpha in (-2.0, 0.0, 2.0, 4.0):
            cl = 0.45 + 0.08 * alpha + 0.01 * de
            cd = max(1e-4, 0.02 + 0.0015 * alpha * alpha)
            cases.append({
                "case_index": idx,
                "case_label": f"case_{idx:04d}",
                "status": "success",
                "control_input_deg": de,
                "diff_input_deg": 0.0,
                "flight_condition": {
                    "alpha_deg": alpha,
                    "velocity_mps": 28.0,
                    "altitude_m": 1500.0,
                    "beta_deg": 0.0,
                },
                "aero_result": {
                    "scalars": {
                        "cl": cl, "cd": cd, "cm": -0.08 - 0.002 * de,
                        "l_over_d": cl / cd, "x_np": 0.56,
                    },
                },
            })
            idx += 1

    manifest = {"aero_sweep_result": {"cases": cases}}
    (sweep / "aero_sweep_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return sweep


def _app(root: Path) -> "AppTest":
    at = AppTest.from_file(gui_app.__file__, default_timeout=90)
    at.session_state["sb_root"] = str(root)
    at.session_state["sb_dry"] = True
    at.session_state["active_page"] = "aero"
    return at


def test_aero_sweep_inspect_renders(tmp_path):
    """Selecting a sweep run on the Aero inspect tab must not raise."""
    _seed_aero_sweep(tmp_path)
    at = _app(tmp_path)
    at.run()
    assert not at.exception, f"Aero page raised with a sweep fixture:\n{at.exception}"


def test_aero_sweep_polar_curves_view(tmp_path):
    """The 'Polar curves' radio option on a sweep must render without KeyError.

    This is the exact path of BUG-1. We set the inspect view radio to
    'Polar curves' via session_state, which the GUI keys as 'ai_type'.
    """
    _seed_aero_sweep(tmp_path)
    at = _app(tmp_path)
    at.run()
    assert not at.exception, f"initial render raised:\n{at.exception}"

    # Drive the inspect 'View' radio to Polar curves.
    # The radio is created with key='ai_type' (see pg_aero inspect).
    at.session_state["ai_type"] = "Polar curves"
    at.run()
    assert not at.exception, (
        "Aero sweep 'Polar curves' view raised — this is the BUG-1 class "
        f"(column-name mismatch):\n{at.exception}"
    )

    # And the data-table view, which also references the elevon column.
    at.session_state["ai_type"] = "Data table"
    at.run()
    assert not at.exception, (
        f"Aero sweep 'Data table' view raised:\n{at.exception}"
    )
