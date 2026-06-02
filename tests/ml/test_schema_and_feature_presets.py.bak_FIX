from __future__ import annotations

import pandas as pd

from aeris.ml.feature_presets import get_feature_preset, list_feature_preset_names, resolve_feature_columns
from aeris.ml.schema import validate_tabular_ml_schema


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "geometry_id": ["g1", "g2", "g3"],
            "c1_m": [1.4, 1.5, 1.6],
            "b_total_m": [1.7, 1.8, 1.9],
            "sw1_deg": [30.0, 35.0, 40.0],
            "alpha_deg": [0.0, 2.0, 4.0],
            "velocity_mps": [28.0, 28.0, 28.0],
            "altitude_m": [1500.0, 1500.0, 1500.0],
            "control_input_deg": [-5.0, 0.0, 5.0],
            "cl": [0.1, 0.2, 0.3],
            "cd": [0.01, 0.02, 0.03],
            "cm": [-0.1, -0.2, -0.3],
        }
    )


def test_feature_presets_resolve_bwb_control() -> None:
    names = list_feature_preset_names()
    assert "bwb_control" in names

    preset = get_feature_preset("bwb_control")
    assert "control_input_deg" in preset.columns

    resolved = resolve_feature_columns(preset_name="bwb_control")
    assert resolved == list(preset.columns)


def test_schema_validation_passes_for_bwb_control() -> None:
    result = validate_tabular_ml_schema(
        _df(),
        feature_columns=resolve_feature_columns(preset_name="bwb_control"),
        target_columns=["cl", "cd", "cm"],
        group_column="geometry_id",
    )

    assert result.passed is True
    assert result.metadata["n_rows"] == 3
    assert result.metadata["n_groups"] == 3


def test_schema_validation_reports_missing_column() -> None:
    result = validate_tabular_ml_schema(
        _df().drop(columns=["cl"]),
        feature_columns=resolve_feature_columns(preset_name="bwb_control"),
        target_columns=["cl", "cd", "cm"],
        group_column="geometry_id",
    )

    assert result.passed is False
    assert any(issue.code == "missing_columns" for issue in result.errors)


def test_schema_validation_reports_non_numeric_feature() -> None:
    df = _df()
    df["alpha_deg"] = df["alpha_deg"].astype(object)
    df.loc[0, "alpha_deg"] = "bad"

    result = validate_tabular_ml_schema(
        df,
        feature_columns=resolve_feature_columns(preset_name="bwb_control"),
        target_columns=["cl", "cd", "cm"],
        group_column="geometry_id",
    )

    assert result.passed is False
    assert any(issue.code == "non_numeric_feature_columns" for issue in result.errors)
