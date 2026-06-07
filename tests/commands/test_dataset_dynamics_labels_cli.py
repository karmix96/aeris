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


def test_dataset_compute_dynamics_labels_help_runs() -> None:
    result = runner.invoke(app, ["dataset", "compute-dynamics-labels", "--help"])
    assert result.exit_code == 0
    assert "--dataset" in result.stdout
    # Rich/Typer may visually truncate long option names in help output,
    # so assert the option's help text instead of the exact rendered flag.
    assert "Recompute D2" in result.stdout
    assert "control derivatives" in result.stdout
    assert "dynamics" in result.stdout.lower()


def test_dataset_compute_dynamics_labels_cli_writes_outputs(tmp_path: Path) -> None:
    root = tmp_path / "aero_dataset"
    _make_dataset(root)

    result = runner.invoke(
        app,
        [
            "dataset",
            "compute-dynamics-labels",
            "--dataset",
            str(root),
            "--source",
            "raw",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "Dynamics label batch completed" in result.stdout
    assert (root / "control_derivatives.csv").exists()
    assert (root / "flyability_labels.csv").exists()
    assert (root / "dynamics_label_run_report.json").exists()

    payload = json.loads((root / "dynamics_label_run_report.json").read_text())
    assert payload["stages"]["control_derivatives"]["mode"] == "computed"
    assert payload["label_summary"]["computed_label_count"] == 1


def test_dataset_compute_dynamics_labels_cli_json_and_reuse(tmp_path: Path) -> None:
    root = tmp_path / "aero_dataset"
    _make_dataset(root)
    compute_control_derivatives(dataset_root=root, source="raw")

    result = runner.invoke(
        app,
        [
            "dataset",
            "compute-dynamics-labels",
            "--dataset",
            str(root),
            "--source",
            "raw",
            "--no-recompute-control-derivatives",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["stages"]["control_derivatives"]["mode"] == "reused_existing"
    assert payload["label_summary"]["computed_label_count"] == 1
