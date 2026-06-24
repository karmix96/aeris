from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.ml.target_specific import _recommended_next_step, _target_family, train_target_specific_models


FEATURE_COLUMNS = [
    "c1_m",
    "b_total_m",
    "sw1_deg",
    "alpha_deg",
    "velocity_mps",
    "altitude_m",
    "control_input_deg",
]


def _build_dataset(tmp_path: Path) -> Path:
    dataset_root = tmp_path / "ml_dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3", "g4", "g5", "g6"]):
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
                    "cd": 0.02 + 0.001 * (alpha ** 2) + 0.0001 * geom_idx,
                    "cm": -0.05 * alpha + 0.005 * geom_idx,
                }
            )

    pd.DataFrame(rows).to_csv(dataset_root / "curated_aero_dataset.csv", index=False)
    (dataset_root / "rejected_aero_rows.csv").write_text("", encoding="utf-8")

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


def test_train_target_specific_models_writes_one_run_per_target(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "target_specific"

    result = train_target_specific_models(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=["cl", "cd"],
        model_type="linear_regression",
        split_method="grouped",
        random_seed=123,
        output_dir=output_dir,
    )

    assert result["failed_targets"] == []
    assert set(result["successful_targets"]) == {"cl", "cd"}
    assert (output_dir / "target_specific_training_report.json").exists()
    assert (output_dir / "target_specific_training_summary.csv").exists()
    assert (output_dir / "target_model_index.json").exists()

    for target in ["cl", "cd"]:
        run_dir = output_dir / "targets" / target
        assert (run_dir / "models" / "model.pkl").exists()
        assert (run_dir / "metrics.json").exists()
        assert (run_dir / "train_config.json").exists()
        assert (run_dir / "ml_run_manifest.json").exists()

        train_config = json.loads((run_dir / "train_config.json").read_text(encoding="utf-8"))
        assert train_config["target_columns"] == [target]
        assert train_config["feature_columns"] == FEATURE_COLUMNS

    report = json.loads((output_dir / "target_specific_training_report.json").read_text(encoding="utf-8"))
    assert report["schema_version"] == "aeris.target_specific_training.v1"
    assert report["status"] == "success"
    assert report["successful_target_count"] == 2
    assert report["failed_target_count"] == 0
    assert report["target_family_counts"] == {"aero": 2}
    assert report["weak_targets"] == []
    assert report["split_identity"]["consistent_across_successful_targets"] is True
    assert all(row["target_family"] == "aero" for row in report["targets"])
    assert all(row["recommended_next_step"] for row in report["targets"])

    summary = pd.read_csv(output_dir / "target_specific_training_summary.csv")
    assert set(summary["target"]) == {"cl", "cd"}
    assert set(summary["status"]) == {"success"}
    assert summary["test_r2"].notna().all()


def test_train_target_specific_models_reports_failed_target(tmp_path: Path) -> None:
    dataset_root = _build_dataset(tmp_path)
    output_dir = tmp_path / "target_specific_failure"

    result = train_target_specific_models(
        dataset_path=dataset_root,
        feature_columns=FEATURE_COLUMNS,
        target_columns=["cl", "missing_target"],
        model_type="linear_regression",
        split_method="grouped",
        random_seed=123,
        output_dir=output_dir,
    )

    assert result["successful_targets"] == ["cl"]
    assert result["failed_targets"] == ["missing_target"]

    report = json.loads((output_dir / "target_specific_training_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "partial_failure"
    failed_row = next(row for row in report["targets"] if row["target"] == "missing_target")
    assert failed_row["status"] == "failed"
    assert failed_row["error_type"]
    assert failed_row["error_message"]


def test_target_family_and_recommendation_helpers() -> None:
    assert _target_family("cl") == "aero"
    assert _target_family("cd") == "aero"
    assert _target_family("cm") == "aero"
    assert _target_family("Cm_delta_e_per_rad") == "control_derivative"
    assert _target_family("trim_delta_e_required_deg") == "flyability"
    assert _target_family("longitudinal_basic_flyable_int") == "flyability"

    recommendation = _recommended_next_step("Cm_delta_e_per_rad", "weak_target_low_r2")
    assert "do_not_promote_yet" in recommendation
    assert "control_sweep" in recommendation

