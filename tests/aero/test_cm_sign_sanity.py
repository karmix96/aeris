from __future__ import annotations

import pandas as pd

from aeris.aero.cm_sanity import run_cm_sign_sanity


def test_cm_sign_sanity_passes_when_cm_decreases_with_alpha(tmp_path):
    csv_path = tmp_path / "aero.csv"
    pd.DataFrame({
        "geometry_id": ["g1", "g1", "g1"],
        "control_input_deg": [0, 0, 0],
        "velocity_mps": [28, 28, 28],
        "altitude_m": [1500, 1500, 1500],
        "alpha_deg": [0.0, 4.0, 8.0],
        "cm": [-0.1, -0.2, -0.3],
    }).to_csv(csv_path, index=False)

    report = run_cm_sign_sanity(csv_path=csv_path)

    assert report.passed is True
    assert report.n_groups_evaluable == 1
    assert report.n_groups_failed == 0
    assert report.groups[0].cma_per_rad < 0


def test_cm_sign_sanity_fails_when_cm_increases_with_alpha(tmp_path):
    csv_path = tmp_path / "aero.csv"
    pd.DataFrame({
        "geometry_id": ["g1", "g1", "g1"],
        "control_input_deg": [0, 0, 0],
        "velocity_mps": [28, 28, 28],
        "altitude_m": [1500, 1500, 1500],
        "alpha_deg": [0.0, 4.0, 8.0],
        "cm": [-0.3, -0.2, -0.1],
    }).to_csv(csv_path, index=False)

    report = run_cm_sign_sanity(csv_path=csv_path)

    assert report.passed is False
    assert report.n_groups_failed == 1
    assert report.groups[0].reason == "unexpected_cma_sign"
