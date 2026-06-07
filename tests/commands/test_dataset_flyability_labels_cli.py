from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app
from aeris.dataset.control_derivatives import compute_control_derivatives

runner = CliRunner()


def _make_dataset(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for delta in [-5.0, 0.0, 5.0]:
        rows.append(
            {
                "geometry_id": "geom_00001",
                "alpha_deg": 0.0,
                "beta_deg": 0.0,
                "velocity_mps": 28.0,
                "altitude_m": 1500.0,
                "p_rad_s": 0.0,
                "q_rad_s": 0.0,
                "r_rad_s": 0.0,
                "control_input_deg": delta,
                "delta_e_sym_deg": delta,
                "delta_a_diff_deg": 0.0,
                "cl": 0.5,
                "cd": 0.02,
                "cm": -0.05 - 0.003 * delta,
            }
        )
    pd.DataFrame(rows).to_csv(root / "aero_dataset.csv", index=False)
    (root / "aero_dataset_manifest.json").write_text(json.dumps({}), encoding="utf-8")
    compute_control_derivatives(dataset_root=root, source="raw")


def test_dataset_compute_flyability_labels_help_runs() -> None:
    result = runner.invoke(app, ["dataset", "compute-flyability-labels", "--help"])
    assert result.exit_code == 0
    assert "--dataset" in result.stdout
    assert "--max-abs-trim-delta-e-deg" in result.stdout
    assert "flyability" in result.stdout.lower()


def test_dataset_compute_flyability_labels_cli_writes_outputs(tmp_path: Path) -> None:
    root = tmp_path / "aero_dataset"
    _make_dataset(root)

    result = runner.invoke(
        app,
        [
            "dataset",
            "compute-flyability-labels",
            "--dataset",
            str(root),
            "--source",
            "raw",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "Flyability label generation completed" in result.stdout
    assert (root / "flyability_labels.csv").exists()
    assert (root / "flyability_labels_report.json").exists()

    out = pd.read_csv(root / "flyability_labels.csv")
    assert len(out) == 1
    assert out["status"].iloc[0] == "computed"


def test_dataset_compute_flyability_labels_cli_json(tmp_path: Path) -> None:
    root = tmp_path / "aero_dataset"
    _make_dataset(root)

    result = runner.invoke(
        app,
        [
            "dataset",
            "compute-flyability-labels",
            "--dataset",
            str(root),
            "--source",
            "raw",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["computed_label_count"] == 1
    assert payload["control_column"] == "delta_e_sym_deg"
