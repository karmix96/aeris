"""Tests for aeris.ml.feature_engineering."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aeris.ml.feature_engineering import (
    FEATURE_ENGINEERING_SCHEMA_VERSION,
    FEATURE_TRANSFORMS,
    apply_feature_engineering,
    list_transforms,
)


def _base_df() -> pd.DataFrame:
    return pd.DataFrame({
        "geometry_id": ["g1", "g2"],
        "c1_m": [1.5, 1.6],
        "b_total_m": [1.6, 1.7],
        "sw1_deg": [-35.0, -40.0],
        "alpha_deg": [2.0, 4.0],
        "velocity_mps": [28.0, 28.0],
        "altitude_m": [1500.0, 1500.0],
        "control_input_deg": [5.0, -5.0],
        "cl": [0.3, 0.5],
        "cd": [0.03, 0.04],
        "cm": [-0.05, -0.04],
    })


def test_list_transforms_returns_sorted():
    keys = list_transforms()
    assert keys == sorted(keys)
    assert len(keys) > 0


def test_all_transforms_registered_have_functions():
    for key, transform in FEATURE_TRANSFORMS.items():
        assert callable(transform.fn)
        assert transform.key == key
        assert len(transform.output_columns) > 0


def test_apply_all_transforms_adds_columns():
    df = _base_df()
    result, manifest = apply_feature_engineering(df)
    assert len(result.columns) > len(df.columns)
    assert manifest["schema_version"] == FEATURE_ENGINEERING_SCHEMA_VERSION
    assert manifest["n_engineered_columns"] > 0
    assert len(manifest["transforms_applied"]) > 0


def test_apply_specific_transforms():
    df = _base_df()
    result, manifest = apply_feature_engineering(df, transforms=["alpha_sq", "control_sq"])
    assert "alpha_deg_sq" in result.columns
    assert "control_input_deg_sq" in result.columns
    assert "abs_alpha_deg" not in result.columns
    assert manifest["transforms_requested"] == ["alpha_sq", "control_sq"]


def test_alpha_sq_values():
    df = _base_df()
    result, _ = apply_feature_engineering(df, transforms=["alpha_sq"])
    assert result["alpha_deg_sq"].tolist() == [4.0, 16.0]


def test_abs_alpha_values():
    df = _base_df()
    df["alpha_deg"] = [-2.0, 4.0]
    result, _ = apply_feature_engineering(df, transforms=["abs_alpha"])
    assert result["abs_alpha_deg"].tolist() == [2.0, 4.0]


def test_control_sq_values():
    df = _base_df()
    result, _ = apply_feature_engineering(df, transforms=["control_sq"])
    assert result["control_input_deg_sq"].tolist() == [25.0, 25.0]


def test_alpha_x_control_values():
    df = _base_df()
    result, _ = apply_feature_engineering(df, transforms=["alpha_x_control"])
    expected = [2.0 * 5.0, 4.0 * (-5.0)]
    assert result["alpha_x_control"].tolist() == expected


def test_dynamic_pressure_proxy():
    df = _base_df()
    result, _ = apply_feature_engineering(df, transforms=["dynamic_pressure_proxy"])
    assert "velocity_sq" in result.columns
    assert result["velocity_sq"].tolist() == [28.0 ** 2, 28.0 ** 2]


def test_aspect_ratio_proxy():
    df = _base_df()
    result, _ = apply_feature_engineering(df, transforms=["aspect_ratio_proxy"])
    assert "ar_proxy" in result.columns
    # 2 * 1.6 / 1.5 = 2.1333...
    assert abs(result["ar_proxy"].iloc[0] - 2 * 1.6 / 1.5) < 1e-9


def test_skips_transform_when_column_missing():
    df = pd.DataFrame({"c1_m": [1.0, 1.1], "cl": [0.1, 0.2]})
    result, manifest = apply_feature_engineering(df, transforms=["alpha_sq"])
    assert "alpha_deg_sq" not in result.columns
    assert len(manifest["transforms_skipped"]) == 1
    assert manifest["transforms_applied"] == []


def test_raises_on_unknown_transform():
    df = _base_df()
    with pytest.raises(ValueError, match="Unknown feature transforms"):
        apply_feature_engineering(df, transforms=["does_not_exist"])


def test_does_not_modify_input():
    df = _base_df()
    original_cols = list(df.columns)
    apply_feature_engineering(df)
    assert list(df.columns) == original_cols


def test_writes_manifest_json(tmp_path: Path):
    df = _base_df()
    path = tmp_path / "fe_manifest.json"
    _, manifest = apply_feature_engineering(df, transforms=["alpha_sq"], manifest_path=path)
    assert path.exists()
    loaded = json.loads(path.read_text())
    assert loaded["schema_version"] == FEATURE_ENGINEERING_SCHEMA_VERSION


def test_apply_empty_transforms_list():
    df = _base_df()
    result, manifest = apply_feature_engineering(df, transforms=[])
    assert list(result.columns) == list(df.columns)
    assert manifest["n_engineered_columns"] == 0