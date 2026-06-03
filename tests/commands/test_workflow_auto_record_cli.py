from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def _build_promoted_dataset(tmp_path: Path) -> Path:
    dataset_root = tmp_path / "promoted_ds"
    dataset_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3", "g4"]):
        for alpha in [-2.0, 0.0, 4.0]:
            rows.append(
                {
                    "geometry_id": geom_id,
                    "c1_m": 1.5 + 0.01 * geom_idx,
                    "b_total_m": 1.6 + 0.01 * geom_idx,
                    "sw1_deg": 40.0,
                    "alpha_deg": alpha,
                    "velocity_mps": 28.0,
                    "altitude_m": 1500.0,
                    "control_input_deg": 0.0,
                    "cl": 0.1 * alpha + 0.01 * geom_idx,
                    "cd": 0.02 + 0.001 * (alpha ** 2),
                    "cm": -0.05 * alpha,
                }
            )

    pd.DataFrame(rows).to_csv(dataset_root / "curated_aero_dataset.csv", index=False)
    pd.DataFrame([], columns=["geometry_id", "reason"]).to_csv(
        dataset_root / "rejected_aero_rows.csv", index=False
    )

    promotion_manifest = {
        "dataset_root": str(dataset_root),
        "promotion_forced": False,
        "promotion_ready_at_time_of_promotion": True,
        "promotion_blockers": [],
        "qc_context": {
            "qc_preset_used": "production",
            "geometry_qc_passed": True,
            "aero_qc_passed": True,
        },
        "artifacts": {
            "curated_aero_dataset_csv": str(dataset_root / "curated_aero_dataset.csv"),
            "rejected_aero_rows_csv": str(dataset_root / "rejected_aero_rows.csv"),
        },
    }
    (dataset_root / "promotion_manifest.json").write_text(
        json.dumps(promotion_manifest, indent=2),
        encoding="utf-8",
    )
    return dataset_root


def test_supported_commands_expose_workflow_option() -> None:
    commands = [
        ["dataset", "generate"],
        ["dataset", "aero-generate"],
        ["dataset", "aero-qc"],
        ["dataset", "curate-aero"],
        ["dataset", "promote-aero"],
        ["ml", "eda"],
        ["ml", "train"],
        ["ml", "compare"],
        ["ml", "compare-seeds"],
        ["ml", "promote-model"],
        ["ml", "check-inference-inputs"],
    ]

    for command in commands:
        result = runner.invoke(app, [*command, "--help"])
        assert result.exit_code == 0, result.output
        assert "--workflow" in result.output


def test_ml_eda_auto_records_workflow_stage(tmp_path: Path) -> None:
    dataset_root = _build_promoted_dataset(tmp_path)
    workflow_dir = tmp_path / "workflow"
    eda_dir = tmp_path / "eda"

    init_result = runner.invoke(
        app,
        [
            "--no-check-writable",
            "workflow",
            "init",
            "--name",
            "auto_record_demo",
            "--output-dir",
            str(workflow_dir),
        ],
    )
    assert init_result.exit_code == 0, init_result.output

    eda_result = runner.invoke(
        app,
        [
            "--no-check-writable",
            "ml",
            "eda",
            "--dataset",
            str(dataset_root),
            "--feature-preset",
            "bwb_control",
            "--targets",
            "cl,cd,cm",
            "--output-dir",
            str(eda_dir),
            "--no-plots",
            "--workflow",
            str(workflow_dir),
        ],
    )
    assert eda_result.exit_code == 0, eda_result.output
    assert "Workflow stage auto-recorded" in eda_result.output

    status = json.loads((workflow_dir / "workflow_status.json").read_text(encoding="utf-8"))
    stage = status["stages"]["ml_eda"]
    assert stage["status"] == "complete"
    assert stage["metadata"]["command"] == "aeris ml eda"
    assert str(eda_dir.resolve()) in stage["artifacts"]

    stage_file = workflow_dir / "stages" / "ml_eda" / "stage_status.json"
    assert stage_file.exists()
