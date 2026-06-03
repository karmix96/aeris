"""
Tests: commands.dataset

Purpose:
    Validate basic CLI behavior for dataset commands.

What is tested:
    - Dataset command help renders
    - Dataset generate help renders
    - Dataset inspect help renders

Why it matters:
    Confirms dataset command registration and operator entrypoints work.
"""

from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_dataset_help_runs() -> None:
    result = runner.invoke(app, ["dataset", "--help"])
    assert result.exit_code == 0


def test_dataset_generate_help_runs() -> None:
    result = runner.invoke(app, ["dataset", "generate", "--help"])
    assert result.exit_code == 0


def test_dataset_inspect_help_runs() -> None:
    result = runner.invoke(app, ["dataset", "inspect", "--help"])
    assert result.exit_code == 0


def test_dataset_inspect_cli_reports_aero_dataset(tmp_path):
    import json
    import pandas as pd

    root = tmp_path / "aero_ds_cli"
    root.mkdir()

    (root / "aero_dataset_manifest.json").write_text(
        json.dumps(
            {
                "status": "success",
                "dataset_name": "aero_ds_cli",
                "requested_geometry_n": 1,
                "attempted_geometry_sweeps": 1,
                "completed_geometry_sweeps": 1,
                "successful_aero_rows": 2,
                "failed_aero_rows": 0,
                "generator_id": "bwb_segmented_v1",
                "solver": "aerosandbox_avl",
            }
        ),
        encoding="utf-8",
    )
    (root / "final_run_summary.json").write_text(
        json.dumps({"final_status": "success", "successful_aero_rows": 2, "failed_aero_rows": 0}),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {"geometry_id": "geom_00001", "alpha_deg": 0, "cl": 0.1, "cd": 0.02, "cm": -0.1},
            {"geometry_id": "geom_00001", "alpha_deg": 4, "cl": 0.2, "cd": 0.03, "cm": -0.2},
        ]
    ).to_csv(root / "aero_dataset.csv", index=False)
    pd.DataFrame([], columns=["geometry_id", "failure_reason"]).to_csv(
        root / "aero_failures.csv", index=False
    )

    result = runner.invoke(app, ["dataset", "inspect", "--dataset", str(root)])

    assert result.exit_code == 0
    summary = json.loads(result.stdout)
    assert summary["dataset_type"] == "aero"
    assert summary["aero_dataset_rows"] == 2
    assert summary["aero_failure_rows"] == 0
    assert summary["all_count_checks_pass"] is True
