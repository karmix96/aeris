from __future__ import annotations

from aeris.quality.presets import resolve_qc_preset


def build_qc_summary_payload(qc_preset_name: str | None) -> dict:
    """
    Small contract helper that mirrors the workflow summary payload.

    This isolates the exact shape we expect in final_run_summary.json and makes it easy
    to reuse in pipeline code later if desired.
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


def test_build_qc_summary_payload_for_production() -> None:
    payload = build_qc_summary_payload("production")

    assert payload["qc_preset"] == "production"
    assert payload["geometry_qc"] == {
        "enabled": True,
        "profile": "production",
        "fail_on_error": True,
    }
    assert payload["aero_qc"] == {
        "enabled": True,
        "profile": "production",
        "fail_on_error": True,
    }


def test_build_qc_summary_payload_for_promotion_strict() -> None:
    payload = build_qc_summary_payload("promotion_strict")

    assert payload["qc_preset"] == "promotion_strict"
    assert payload["geometry_qc"] == {
        "enabled": True,
        "profile": "strict",
        "fail_on_error": True,
    }
    assert payload["aero_qc"] == {
        "enabled": True,
        "profile": "strict",
        "fail_on_error": True,
    }


def test_build_qc_summary_payload_for_none() -> None:
    payload = build_qc_summary_payload(None)

    assert payload["qc_preset"] is None
    assert payload["geometry_qc"] == {
        "enabled": False,
        "profile": None,
        "fail_on_error": False,
    }
    assert payload["aero_qc"] == {
        "enabled": False,
        "profile": None,
        "fail_on_error": False,
    }