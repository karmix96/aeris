from __future__ import annotations

import pandas as pd

from aeris.ml.feature_sets import (
    BWB_CONTROL_RAW_COLUMNS,
    BWB_CONTROL_SYM_ELEVON_RAW_COLUMNS,
    get_feature_set,
    list_feature_set_names,
    validate_feature_set_dataframe,
)


def _df_explicit_control() -> pd.DataFrame:
    rows = []
    for geom_idx, geom_id in enumerate(["g1", "g2", "g3"]):
        for alpha, delta_e in [(-2.0, -5.0), (0.0, 0.0), (4.0, 5.0)]:
            rows.append(
                {
                    "geometry_id": geom_id,
                    "c1_m": 1.5 + 0.01 * geom_idx,
                    "b_total_m": 1.6 + 0.01 * geom_idx,
                    "sw1_deg": 40.0 + geom_idx,
                    "alpha_deg": alpha,
                    "velocity_mps": 24.0 + geom_idx,
                    "altitude_m": 1000.0 + 100.0 * geom_idx,
                    "delta_e_sym_deg": delta_e,
                    "delta_a_diff_deg": 0.0,
                    "cl": 0.1 * alpha + 0.01 * geom_idx,
                    "cd": 0.02 + 0.001 * (alpha ** 2) + 0.0001 * geom_idx,
                    "cm": -0.05 * alpha + 0.005 * geom_idx,
                }
            )
    return pd.DataFrame(rows)


def test_feature_set_registry_keeps_legacy_and_adds_explicit_control_sets() -> None:
    names = list_feature_set_names()

    assert "bwb_control_raw" in names
    assert "bwb_control_physics_v1" in names
    assert "bwb_control_sym_elevon_raw" in names
    assert "bwb_control_sym_elevon_physics_v1" in names


def test_legacy_raw_columns_are_not_renamed() -> None:
    assert BWB_CONTROL_RAW_COLUMNS[-1] == "control_input_deg"
    feature_set = get_feature_set("bwb_control_raw")

    assert feature_set.raw_columns == BWB_CONTROL_RAW_COLUMNS
    assert "delta_e_sym_deg" not in feature_set.raw_columns


def test_explicit_symmetric_elevon_raw_feature_set_uses_delta_e_sym() -> None:
    assert BWB_CONTROL_SYM_ELEVON_RAW_COLUMNS[-1] == "delta_e_sym_deg"
    feature_set = get_feature_set("bwb_control_sym_elevon_raw")

    assert feature_set.raw_columns == BWB_CONTROL_SYM_ELEVON_RAW_COLUMNS
    assert "control_input_deg" not in feature_set.raw_columns
    assert feature_set.engineered_columns == ()
    assert feature_set.transforms == ()


def test_explicit_symmetric_elevon_physics_feature_set_uses_explicit_transforms() -> None:
    feature_set = get_feature_set("bwb_control_sym_elevon_physics_v1")

    assert feature_set.raw_columns == BWB_CONTROL_SYM_ELEVON_RAW_COLUMNS
    assert "delta_e_sym_sq" in feature_set.transforms
    assert "alpha_x_delta_e_sym" in feature_set.transforms
    assert "control_sq" not in feature_set.transforms
    assert "alpha_x_control" not in feature_set.transforms
    assert "delta_e_sym_deg_sq" in feature_set.engineered_columns
    assert "alpha_x_delta_e_sym" in feature_set.engineered_columns
    assert "control_input_deg_sq" not in feature_set.engineered_columns


def test_validate_explicit_symmetric_elevon_raw_dataframe() -> None:
    result = validate_feature_set_dataframe(
        _df_explicit_control(),
        feature_set="bwb_control_sym_elevon_raw",
        target_columns=["cl", "cd", "cm"],
        group_column="geometry_id",
    )

    assert result.passed, [issue.message for issue in result.errors]
    assert result.metadata["feature_set_id"] == "bwb_control_sym_elevon_raw"
    assert result.metadata["feature_columns"][-1] == "delta_e_sym_deg"


def test_validate_explicit_symmetric_elevon_physics_dataframe_applies_transforms() -> None:
    result = validate_feature_set_dataframe(
        _df_explicit_control(),
        feature_set="bwb_control_sym_elevon_physics_v1",
        target_columns=["cl", "cd", "cm"],
        group_column="geometry_id",
    )

    assert result.passed, [issue.message for issue in result.errors]
    assert "delta_e_sym_deg_sq" in result.metadata["feature_columns"]
    assert "alpha_x_delta_e_sym" in result.metadata["feature_columns"]
    assert result.metadata["transform_manifest"]["n_engineered_columns"] > 0


def test_legacy_feature_set_still_requires_legacy_control_column() -> None:
    result = validate_feature_set_dataframe(
        _df_explicit_control(),
        feature_set="bwb_control_raw",
        target_columns=["cl", "cd", "cm"],
        group_column="geometry_id",
    )

    assert not result.passed
    assert any(issue.code == "missing_feature_set_source_columns" for issue in result.errors)
