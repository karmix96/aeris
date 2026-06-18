from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.quality.pipeline_api import run_aero_dataset_qc
from aeris.quality.presets import resolve_qc_preset
from aeris.quality.profiles import resolve_aero_profile, resolve_geometry_profile


def test_resolve_qc_preset_production() -> None:
    preset = resolve_qc_preset("production")
    assert preset is not None
    assert preset.name == "production"

    assert preset.run_geometry_qc is True
    assert preset.geometry_qc_profile == "production"
    assert preset.fail_on_geometry_qc_error is True

    assert preset.run_aero_qc is True
    assert preset.aero_qc_profile == "production"
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

def test_production_profiles_include_physical_validators() -> None:
    _, geometry_ids = resolve_geometry_profile("production")
    _, aero_ids = resolve_aero_profile("production")

    assert "geometry_scalar_consistency_v1" in geometry_ids
    assert "aero_cl_alpha_trend_v1" in aero_ids
    assert "aero_cm_control_trend_v1" in aero_ids
    assert "aero_outlier_scan_v1" not in aero_ids
    assert "aero_ld_sanity_v1" not in aero_ids
    assert "aero_beta_zero_lateral_sanity_v1" not in aero_ids
    assert "aero_target_variation_v1" not in aero_ids


def test_production_aero_qc_fails_inverted_cmde_sign(tmp_path: Path) -> None:
    dataset_root = tmp_path / "aero_dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for alpha in [0.0, 2.0, 4.0]:
        for ctrl, cm in [(-5.0, -0.11), (0.0, -0.08), (5.0, -0.05)]:
            rows.append(
                {
                    "geometry_id": "g1",
                    "alpha_deg": alpha,
                    "velocity_mps": 28.0,
                    "altitude_m": 1500.0,
                    "control_input_deg": ctrl,
                    "cl": 0.2 + 0.1 * alpha + 0.01 * ctrl,
                    "cd": 0.03,
                    "cm": cm,
                    "geometry_declares_controls": True,
                    "airplane_has_controls": True,
                    "diag_airplane_has_control_surfaces": True,
                    "diag_airplane_avl_has_control_blocks": True,
                    "diag_keystrokes_has_d1_command": True,
                    "diag_stdout_control_variables": 1,
                }
            )

    pd.DataFrame(rows).to_csv(dataset_root / "aero_dataset.csv", index=False)
    (dataset_root / "aero_dataset_manifest.json").write_text(
        json.dumps(
            {
                "status": "success",
                "successful_aero_rows": len(rows),
                "alpha_values": [0.0, 2.0, 4.0],
                "velocity_values": [28.0],
                "altitude_values": [1500.0],
                "control_input_values": [-5.0, 0.0, 5.0],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    report = run_aero_dataset_qc(dataset_root, profile="production")

    assert report["passed"] is False
    assert any("Cmde sign is POSITIVE" in msg for msg in report["errors"])
    assert not any("Cmde sign is POSITIVE" in msg for msg in report["warnings"])
