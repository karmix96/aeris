from __future__ import annotations

from aeris.quality.presets import resolve_qc_preset


def build_qc_summary_payload(qc_preset_name: str | None) -> dict:
    """
    Build the QC portion of final_run_summary.json from the preset name.

    This keeps final summary writing consistent and testable.
    """
    preset = resolve_qc_preset(qc_preset_name)

    if preset is None:
        return {
            "qc_preset": None,
            "geometry_qc": {
                "enabled": False,
                "profile": None,
                "fail_on_error": False,
            },
            "aero_qc": {
                "enabled": False,
                "profile": None,
                "fail_on_error": False,
            },
        }

    return {
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