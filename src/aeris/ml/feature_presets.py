from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


class FeaturePresetError(ValueError):
    """Raised when an ML feature preset cannot be resolved safely."""


@dataclass(frozen=True)
class FeaturePreset:
    """Named, reusable feature-column set for ML experiments.

    Presets are deliberately lightweight: they are only column-name bundles plus
    human-readable metadata. They do not know how a dataset was generated and
    they do not bypass schema validation. This keeps ML experiment configs short
    without coupling the ML layer to a specific generator, solver, or CFD tool.
    """

    name: str
    columns: tuple[str, ...]
    domain: str
    description: str
    status: str = "active"

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "columns": list(self.columns),
            "domain": self.domain,
            "description": self.description,
            "status": self.status,
        }


# Active presets must describe columns that already exist in current promoted
# aero datasets. Do not add airfoil/CFD/GNN presets here until those dataset
# schemas are produced by real AERIS pipelines.
#
# Important:
# - bwb_control is the raw/current BWB control preset.
# - It intentionally does NOT include re_number. Reynolds/Mach/dynamic-pressure
#   style columns belong in the feature-engineering layer, where they will
#   be created explicitly and recorded in a feature manifest.
_FEATURE_PRESETS: dict[str, FeaturePreset] = {
    "bwb_basic": FeaturePreset(
        name="bwb_basic",
        domain="bwb_scalar_aero",
        columns=(
            "c1_m",
            "b_total_m",
            "sw1_deg",
            "alpha_deg",
            "velocity_mps",
            "altitude_m",
        ),
        description=(
            "Minimal current BWB scalar-aero feature set: core geometry scale, "
            "sweep, and flight condition. Excludes control deflection."
        ),
    ),
    "bwb_control": FeaturePreset(
        name="bwb_control",
        domain="bwb_scalar_aero",
        columns=(
            "c1_m",
            "b_total_m",
            "sw1_deg",
            "alpha_deg",
            "velocity_mps",
            "altitude_m",
            "control_input_deg",
        ),
        description=(
            "Current default BWB scalar-aero feature set including control input. "
            "Use for CL/CD/Cm surrogate smoke and baseline experiments. "
            "This is a raw-data preset; engineered Reynolds/Mach/qbar features "
            "belong in explicit feature-engineering feature sets."
        ),
    ),
}


def list_feature_presets(*, include_inactive: bool = False) -> list[FeaturePreset]:
    """Return registered feature presets in stable name order."""
    presets = sorted(_FEATURE_PRESETS.values(), key=lambda preset: preset.name)
    if include_inactive:
        return presets
    return [preset for preset in presets if preset.status == "active"]


def list_feature_preset_names(*, include_inactive: bool = False) -> list[str]:
    """Return registered feature-preset names."""
    return [preset.name for preset in list_feature_presets(include_inactive=include_inactive)]


def get_feature_preset(name: str) -> FeaturePreset:
    """Resolve a feature preset by name."""
    key = str(name).strip()
    if not key:
        raise FeaturePresetError("Feature preset name must not be empty.")
    try:
        return _FEATURE_PRESETS[key]
    except KeyError as exc:
        supported = ", ".join(list_feature_preset_names(include_inactive=True))
        raise FeaturePresetError(
            f"Unknown feature preset '{name}'. Supported presets: {supported}"
        ) from exc


def normalize_feature_columns(columns: Iterable[str]) -> list[str]:
    """Normalize and de-duplicate feature columns while preserving order."""
    normalized: list[str] = []
    seen: set[str] = set()
    for column in columns:
        clean = str(column).strip()
        if not clean:
            continue
        if clean not in seen:
            seen.add(clean)
            normalized.append(clean)
    if not normalized:
        raise FeaturePresetError("Feature column list must not be empty.")
    return normalized


def resolve_feature_columns(
    *,
    explicit_features: Iterable[str] | None = None,
    preset_name: str | None = None,
) -> list[str]:
    """Resolve features from either explicit columns or a named preset.

    Exactly one source is allowed. This avoids silent mistakes where the user
    thinks a preset is active but explicit CLI columns override it, or vice versa.
    """
    has_explicit = explicit_features is not None and bool(list(explicit_features))
    has_preset = preset_name is not None and bool(str(preset_name).strip())

    if has_explicit and has_preset:
        raise FeaturePresetError("Use either explicit --features or --feature-preset, not both.")
    if not has_explicit and not has_preset:
        raise FeaturePresetError("Provide either explicit features or a feature preset.")
    if has_preset:
        return list(get_feature_preset(str(preset_name)).columns)
    return normalize_feature_columns(explicit_features or [])
