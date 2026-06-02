from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.ml.feature_sets import (
    BWB_CONTROL_RAW_COLUMNS,
    describe_feature_set,
    get_feature_set,
    list_feature_set_names,
    validate_promoted_dataset_feature_set,
)


def _build_dataset(tmp_path: Path, *, drop_column: str | None = None) -> Path:
    dataset_root = tmp_path / "ml_feature_set_dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3", "g4"]):
        for alpha in [-2.0, 0.0, 4.0]:
            rows.append(
                {
                    "geometry_id": geom_id,
                    "c1_m": 1.5 + 0.01 * geom_idx,
                    "b_total_m": 1.6 + 0.01 * geom_idx,
                    "sw1_deg": 40.0 + geom_idx,
                    "alpha_deg": alpha,
                    "velocity_mps": 24.0 + geom_idx,
                    "altitude_m": 1000.0 + 100.0 * geom_idx,
                    "control_input_deg": {-2.0: -5.0, 0.0: 0.0, 4.0: 5.0}[alpha],
                    "cl": 0.1 * alpha + 0.01 * geom_idx,
                    "cd": 0.02 + 0.001 * (alpha ** 2) + 0.0001 * geom_idx,
                    "cm": -0.05 * alpha + 0.005 * geom_idx,
                }
            )

    df = pd.DataFrame(rows)
    if drop_column is not None:
        df = df.drop(columns=[drop_column])
    curated_csv = dataset_root / "curated_aero_dataset.csv"
    df.to_csv(curated_csv, index=False)
    rejected_csv = dataset_root / "rejected_aero_rows.csv"
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


def test_feature_set_registry_lists_initial_sets() -> None:
    names = list_feature_set_names()
    assert "bwb_control_raw" in names
    assert "bwb_control_physics_v1" in names


def test_bwb_control_raw_is_exact_current_raw_columns() -> None:
    feature_set = get_feature_set("bwb_control_raw")
    assert feature_set.raw_columns == BWB_CONTROL_RAW_COLUMNS
    assert feature_set.engineered_columns == ()
    assert feature_set.transforms == ()
    assert "re_number" not in feature_set.columns


def test_physics_feature_set_declares_engineered_columns_and_transforms() -> None:
    feature_set = get_feature_set("bwb_control_physics_v1")
    assert feature_set.raw_columns == BWB_CONTROL_RAW_COLUMNS
    assert "alpha_deg_sq" in feature_set.engineered_columns
    assert "velocity_sq" in feature_set.engineered_columns
    assert "re_number" in feature_set.engineered_columns
    assert "alpha_sq" in feature_set.transforms
    assert "re_number" in feature_set.transforms


def test_describe_feature_set_is_json_safe() -> None:
    payload = describe_feature_set("bwb_control_physics_v1")
    dumped = json.dumps(payload)
    assert "bwb_control_physics_v1" in dumped
    assert payload["schema_version"] == "aeris.ml.feature_set.v1"


def test_validate_raw_feature_set_against_promoted_dataset(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path)
    result = validate_promoted_dataset_feature_set(
        dataset_path=dataset,
        feature_set_name="bwb_control_raw",
        target_columns=["cl", "cd", "cm"],
        group_column="geometry_id",
    )
    assert result.passed, [issue.message for issue in result.errors]
    assert result.metadata["feature_set_id"] == "bwb_control_raw"
    assert result.metadata["engineered_features"] == []
    assert result.metadata["target_columns"] == ["cl", "cd", "cm"]


def test_validate_physics_feature_set_applies_transforms_in_memory(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path)
    result = validate_promoted_dataset_feature_set(
        dataset_path=dataset,
        feature_set_name="bwb_control_physics_v1",
        target_columns=["cl", "cd", "cm"],
        group_column="geometry_id",
    )
    assert result.passed, [issue.message for issue in result.errors]
    assert "alpha_deg_sq" in result.metadata["feature_columns"]
    assert "re_number" in result.metadata["feature_columns"]
    assert result.metadata["transform_manifest"]["n_engineered_columns"] > 0


def test_validate_feature_set_fails_on_missing_raw_source_column(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path, drop_column="control_input_deg")
    result = validate_promoted_dataset_feature_set(
        dataset_path=dataset,
        feature_set_name="bwb_control_raw",
        target_columns=["cl", "cd", "cm"],
        group_column="geometry_id",
    )
    assert not result.passed
    assert any(issue.code == "missing_feature_set_source_columns" for issue in result.errors)
