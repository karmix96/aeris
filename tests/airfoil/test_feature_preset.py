"""Verify the airfoil_xfoil_v1 feature preset is registered correctly."""
from __future__ import annotations

import pytest
from aeris.ml.feature_presets import get_feature_preset, list_feature_preset_names


def test_airfoil_preset_registered():
    names = list_feature_preset_names()
    assert "airfoil_xfoil_v1" in names


def test_airfoil_preset_columns():
    preset = get_feature_preset("airfoil_xfoil_v1")
    assert "alpha_deg" in preset.columns
    assert "log10_reynolds" in preset.columns
    assert "t_c" in preset.columns
    assert "camber_max" in preset.columns
    assert preset.domain == "airfoil_2d_scalar_aero"


def test_airfoil_preset_has_description():
    preset = get_feature_preset("airfoil_xfoil_v1")
    assert len(preset.description) > 10
