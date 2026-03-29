from __future__ import annotations

from aeris.quality.presets import resolve_qc_preset


def test_resolve_qc_preset_production() -> None:
    preset = resolve_qc_preset("production")
    assert preset is not None
    assert preset.name == "production"

    assert preset.run_geometry_qc is True
    assert preset.geometry_qc_profile == "basic"
    assert preset.fail_on_geometry_qc_error is True

    assert preset.run_aero_qc is True
    assert preset.aero_qc_profile == "basic"
    assert preset.fail_on_aero_qc_error is True


def test_resolve_qc_preset_promotion_strict() -> None:
    preset = resolve_qc_preset("promotion_strict")
    assert preset is not None
    assert preset.name == "promotion_strict"

    assert preset.run_geometry_qc is True
    assert preset.geometry_qc_profile == "strict"
    assert preset.fail_on_geometry_qc_error is True

    assert preset.run_aero_qc is True
    assert preset.aero_qc_profile == "strict"
    assert preset.fail_on_aero_qc_error is True


def test_resolve_qc_preset_debug() -> None:
    preset = resolve_qc_preset("debug")
    assert preset is not None
    assert preset.name == "debug"

    assert preset.run_geometry_qc is True
    assert preset.geometry_qc_profile == "basic"
    assert preset.fail_on_geometry_qc_error is False

    assert preset.run_aero_qc is True
    assert preset.aero_qc_profile == "basic"
    assert preset.fail_on_aero_qc_error is False


def test_resolve_qc_preset_off() -> None:
    preset = resolve_qc_preset("off")
    assert preset is not None
    assert preset.name == "off"

    assert preset.run_geometry_qc is False
    assert preset.run_aero_qc is False


def test_resolve_qc_preset_invalid_raises() -> None:
    try:
        resolve_qc_preset("banana_mode")
    except ValueError as exc:
        assert "Unknown QC preset" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid QC preset")