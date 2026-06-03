from __future__ import annotations

import json

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_aero_cm_sanity_cli_writes_report(tmp_path):
    csv_path = tmp_path / "aero.csv"
    out = tmp_path / "out"
    pd.DataFrame({
        "geometry_id": ["g1", "g1"],
        "control_input_deg": [0, 0],
        "velocity_mps": [28, 28],
        "altitude_m": [1500, 1500],
        "alpha_deg": [0.0, 4.0],
        "cm": [-0.1, -0.2],
    }).to_csv(csv_path, index=False)

    result = runner.invoke(app, [
        "aero", "cm-sanity",
        "--csv", str(csv_path),
        "--output-dir", str(out),
    ])

    assert result.exit_code == 0, result.output
    assert "passed: True" in result.output
    report = json.loads((out / "cm_sign_sanity_report.json").read_text())
    assert report["passed"] is True
    assert report["n_groups_passed"] == 1


def test_aero_cm_sanity_cli_fail_on_violation(tmp_path):
    csv_path = tmp_path / "aero.csv"
    pd.DataFrame({
        "geometry_id": ["g1", "g1"],
        "control_input_deg": [0, 0],
        "velocity_mps": [28, 28],
        "altitude_m": [1500, 1500],
        "alpha_deg": [0.0, 4.0],
        "cm": [-0.2, -0.1],
    }).to_csv(csv_path, index=False)

    result = runner.invoke(app, [
        "aero", "cm-sanity",
        "--csv", str(csv_path),
        "--fail-on-violation",
    ])

    assert result.exit_code != 0
    assert "passed: False" in result.output
