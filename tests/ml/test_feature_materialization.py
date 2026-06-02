from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aeris.ml.feature_materialization import (
    FeatureMaterializationError,
    materialize_feature_set_dataset,
)


def _build_dataset(tmp_path: Path, *, drop_column: str | None = None) -> Path:
    dataset_root = tmp_path / "feature_materialization_dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)

    rows = []
    control_by_alpha = {-2.0: -5.0, 0.0: 0.0, 4.0: 5.0}
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3", "g4"]):
        for alpha in [-2.0, 0.0, 4.0]:
            rows.append(
                {
                    "geometry_id": geom_id,
                    "case_id": f"{geom_id}_a{alpha:g}",
                    "c1_m": 1.5 + 0.01 * geom_idx,
                    "b_total_m": 1.6 + 0.02 * geom_idx,
                    "sw1_deg": 40.0 + geom_idx,
                    "alpha_deg": alpha,
                    "velocity_mps": 24.0 + geom_idx,
                    "altitude_m": 1000.0 + 100.0 * geom_idx,
                    "control_input_deg": control_by_alpha[alpha],
                    "cl": 0.1 * alpha + 0.01 * geom_idx,
                    "cd": 0.02 + 0.001 * (alpha**2) + 0.0001 * geom_idx,
                    "cm": -0.05 * alpha + 0.005 * geom_idx,
                }
            )

    df = pd.DataFrame(rows)
    if drop_column is not None:
        df = df.drop(columns=[drop_column])

    curated_csv = dataset_root / "curated_aero_dataset.csv"
    rejected_csv = dataset_root / "rejected_aero_rows.csv"
    df.to_csv(curated_csv, index=False)
    rejected_csv.write_text("", encoding="utf-8")

    promotion_manifest = {
        "dataset_root": str(dataset_root),
        "promotion_forced": False,
        "promotion_ready_at_time_of_promotion": True,
        "promotion_blockers": [],
        "artifacts": {
            "curated_aero_dataset_csv": str(curated_csv),
            "rejected_aero_rows_csv": str(rejected_csv),
        },
    }
    (dataset_root / "promotion_manifest.json").write_text(
        json.dumps(promotion_manifest, indent=2),
        encoding="utf-8",
    )
    return dataset_root


def test_materialize_physics_feature_set_writes_expected_artifacts(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path)
    output_dir = tmp_path / "features" / "physics"

    result = materialize_feature_set_dataset(
        dataset_path=dataset,
        feature_set_name="bwb_control_physics_v1",
        target_columns=["cl", "cd", "cm"],
        group_column="geometry_id",
        output_dir=output_dir,
        include_all_columns=False,
    )

    assert result.engineered_dataset_csv.exists()
    assert result.feature_engineering_manifest_json.exists()
    assert result.feature_schema_json.exists()
    assert result.feature_materialization_report_json.exists()
    assert result.validation.passed

    out_df = pd.read_csv(result.engineered_dataset_csv)
    assert "geometry_id" in out_df.columns
    assert "alpha_deg_sq" in out_df.columns
    assert "alpha_x_control" in out_df.columns
    assert "re_number" in out_df.columns
    assert "cl" in out_df.columns
    assert "case_id" not in out_df.columns
    assert len(out_df) == 12

    schema = json.loads(result.feature_schema_json.read_text(encoding="utf-8"))
    assert schema["feature_set"]["name"] == "bwb_control_physics_v1"
    assert "alpha_deg_sq" in schema["final_features"]
    assert schema["target_columns"] == ["cl", "cd", "cm"]

    report = json.loads(result.feature_materialization_report_json.read_text(encoding="utf-8"))
    assert report["status"] == "completed"
    assert report["n_materialized_rows"] == 12
    assert report["hashes"]["engineered_dataset_csv_sha256"]


def test_materialize_raw_feature_set_does_not_add_engineered_columns(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path)

    result = materialize_feature_set_dataset(
        dataset_path=dataset,
        feature_set_name="bwb_control_raw",
        target_columns=["cl", "cd", "cm"],
        output_dir=tmp_path / "raw_features",
        include_all_columns=False,
    )

    out_df = pd.read_csv(result.engineered_dataset_csv)
    assert "control_input_deg" in out_df.columns
    assert "alpha_deg_sq" not in out_df.columns
    assert "re_number" not in out_df.columns
    assert result.n_rows == 12


def test_materialize_feature_set_fails_when_validation_fails(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path, drop_column="control_input_deg")

    with pytest.raises(FeatureMaterializationError, match="missing_feature_set_source_columns"):
        materialize_feature_set_dataset(
            dataset_path=dataset,
            feature_set_name="bwb_control_physics_v1",
            target_columns=["cl", "cd", "cm"],
            output_dir=tmp_path / "bad",
        )


def test_materialize_feature_set_refuses_overwrite_by_default(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path)
    output_dir = tmp_path / "features"

    materialize_feature_set_dataset(
        dataset_path=dataset,
        feature_set_name="bwb_control_raw",
        target_columns=["cl", "cd", "cm"],
        output_dir=output_dir,
    )

    with pytest.raises(FeatureMaterializationError, match="already exist"):
        materialize_feature_set_dataset(
            dataset_path=dataset,
            feature_set_name="bwb_control_raw",
            target_columns=["cl", "cd", "cm"],
            output_dir=output_dir,
        )

    result = materialize_feature_set_dataset(
        dataset_path=dataset,
        feature_set_name="bwb_control_raw",
        target_columns=["cl", "cd", "cm"],
        output_dir=output_dir,
        overwrite=True,
    )
    assert result.engineered_dataset_csv.exists()
