from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QCPreset:
    name: str
    run_geometry_qc: bool
    geometry_qc_profile: str
    fail_on_geometry_qc_error: bool
    run_aero_qc: bool
    aero_qc_profile: str
    fail_on_aero_qc_error: bool


QC_PRESETS: dict[str, QCPreset] = {
    "off": QCPreset(
        name="off",
        run_geometry_qc=False,
        geometry_qc_profile="basic",
        fail_on_geometry_qc_error=False,
        run_aero_qc=False,
        aero_qc_profile="basic",
        fail_on_aero_qc_error=False,
    ),
    "debug": QCPreset(
        name="debug",
        run_geometry_qc=True,
        geometry_qc_profile="basic",
        fail_on_geometry_qc_error=False,
        run_aero_qc=True,
        aero_qc_profile="basic",
        fail_on_aero_qc_error=False,
    ),
    "production": QCPreset(
        name="production",
        run_geometry_qc=True,
        geometry_qc_profile="basic",
        fail_on_geometry_qc_error=True,
        run_aero_qc=True,
        aero_qc_profile="basic",
        fail_on_aero_qc_error=True,
    ),
    "promotion_strict": QCPreset(
        name="promotion_strict",
        run_geometry_qc=True,
        geometry_qc_profile="strict",
        fail_on_geometry_qc_error=True,
        run_aero_qc=True,
        aero_qc_profile="strict",
        fail_on_aero_qc_error=True,
    ),
}


def list_qc_presets() -> list[str]:
    return list(QC_PRESETS.keys())


def resolve_qc_preset(name: str | None) -> QCPreset | None:
    if name is None:
        return None

    key = name.strip().lower()
    if key == "":
        return None

    if key not in QC_PRESETS:
        valid = ", ".join(list_qc_presets())
        raise ValueError(f"Unknown QC preset '{name}'. Valid presets: {valid}")

    return QC_PRESETS[key]