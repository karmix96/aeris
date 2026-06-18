from __future__ import annotations

import json
from pathlib import Path

from aeris.quality.presets import resolve_qc_preset


def _write_final_run_summary(summary_path: Path, *, qc_preset_name: str) -> dict:
    """
    Minimal test helper that mirrors the intended final summary QC fields.

    This is a workflow-facing contract test:
    - preset is resolved
    - resolved profiles are written
    - fail-on-qc flags are written
    """
    preset = resolve_qc_preset(qc_preset_name)
    assert preset is not None

    summary = {
        "qc": {
            "qc_preset": preset.name,
            "geometry_qc": {
                "enabled": preset.run_geometry_qc,
                "profile": preset.geometry_qc_profile,
                "fail_on_error": preset.fail_on_geometry_qc_error,
            },
            "aero_qc": {
                "enabled": preset.run_aero_qc,
                "profile": preset.aero_qc_profile,
                "fail_on_error": preset.fail_on_aero_qc_error,
            },
        }
    }

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def test_final_run_summary_records_production_profiles(tmp_path: Path) -> None:
    summary_path = tmp_path / "final_run_summary.json"
    written = _write_final_run_summary(summary_path, qc_preset_name="production")

    loaded = json.loads(summary_path.read_text(encoding="utf-8"))

    assert loaded == written
    assert loaded["qc"]["qc_preset"] == "production"

    assert loaded["qc"]["geometry_qc"]["enabled"] is True
    assert loaded["qc"]["geometry_qc"]["profile"] == "production"
    assert loaded["qc"]["geometry_qc"]["fail_on_error"] is True

    assert loaded["qc"]["aero_qc"]["enabled"] is True
    assert loaded["qc"]["aero_qc"]["profile"] == "production"
    assert loaded["qc"]["aero_qc"]["fail_on_error"] is True


def test_final_run_summary_records_promotion_strict_profiles(tmp_path: Path) -> None:
    summary_path = tmp_path / "final_run_summary.json"
    written = _write_final_run_summary(summary_path, qc_preset_name="promotion_strict")

    loaded = json.loads(summary_path.read_text(encoding="utf-8"))

    assert loaded == written
    assert loaded["qc"]["qc_preset"] == "promotion_strict"

    assert loaded["qc"]["geometry_qc"]["enabled"] is True
    assert loaded["qc"]["geometry_qc"]["profile"] == "strict"
    assert loaded["qc"]["geometry_qc"]["fail_on_error"] is True

    assert loaded["qc"]["aero_qc"]["enabled"] is True
    assert loaded["qc"]["aero_qc"]["profile"] == "strict"
    assert loaded["qc"]["aero_qc"]["fail_on_error"] is True


def test_final_run_summary_records_debug_profiles(tmp_path: Path) -> None:
    summary_path = tmp_path / "final_run_summary.json"
    written = _write_final_run_summary(summary_path, qc_preset_name="debug")

    loaded = json.loads(summary_path.read_text(encoding="utf-8"))

    assert loaded == written
    assert loaded["qc"]["qc_preset"] == "debug"

    assert loaded["qc"]["geometry_qc"]["enabled"] is True
    assert loaded["qc"]["geometry_qc"]["profile"] == "basic"
    assert loaded["qc"]["geometry_qc"]["fail_on_error"] is False

    assert loaded["qc"]["aero_qc"]["enabled"] is True
    assert loaded["qc"]["aero_qc"]["profile"] == "basic"
    assert loaded["qc"]["aero_qc"]["fail_on_error"] is False


def test_final_run_summary_records_off_profiles(tmp_path: Path) -> None:
    summary_path = tmp_path / "final_run_summary.json"
    written = _write_final_run_summary(summary_path, qc_preset_name="off")

    loaded = json.loads(summary_path.read_text(encoding="utf-8"))

    assert loaded == written
    assert loaded["qc"]["qc_preset"] == "off"

    assert loaded["qc"]["geometry_qc"]["enabled"] is False
    assert loaded["qc"]["geometry_qc"]["profile"] == "basic"
    assert loaded["qc"]["geometry_qc"]["fail_on_error"] is False

    assert loaded["qc"]["aero_qc"]["enabled"] is False
    assert loaded["qc"]["aero_qc"]["profile"] == "basic"
    assert loaded["qc"]["aero_qc"]["fail_on_error"] is False