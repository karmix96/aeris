from __future__ import annotations

from aeris.ml.feature_presets import (
    get_feature_preset,
    list_feature_preset_names,
    resolve_feature_columns,
)


def test_legacy_bwb_control_preset_is_still_available() -> None:
    preset = get_feature_preset("bwb_control")

    assert "bwb_control" in list_feature_preset_names()
    assert "control_input_deg" in preset.columns
    assert "delta_e_sym_deg" not in preset.columns


def test_explicit_symmetric_elevon_preset_is_available() -> None:
    preset = get_feature_preset("bwb_control_sym_elevon")

    assert "bwb_control_sym_elevon" in list_feature_preset_names()
    assert "delta_e_sym_deg" in preset.columns
    assert "control_input_deg" not in preset.columns


def test_resolve_feature_columns_supports_explicit_symmetric_elevon_preset() -> None:
    columns = resolve_feature_columns(preset_name="bwb_control_sym_elevon")

    assert columns[-1] == "delta_e_sym_deg"
    assert "control_input_deg" not in columns
