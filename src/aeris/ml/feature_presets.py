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
# - bwb_control is the backward-compatible raw/current BWB control preset
#   using the legacy control_input_deg column.
# - bwb_control_sym_elevon is the explicit symmetric-elevon preset using
#   delta_e_sym_deg. Prefer it for new datasets generated after D1b.2.
# - These presets intentionally do NOT include re_number. Reynolds/Mach/
#   dynamic-pressure style columns belong in the feature-engineering layer,
#   where they will be created explicitly and recorded in a feature manifest.
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
            "Backward-compatible BWB scalar-aero feature preset including the "
            "legacy control_input_deg column. Keep this for old datasets, old "
            "model runs, and smoke/regression tests. Prefer "
            "bwb_control_sym_elevon for new D1b.2+ datasets."
        ),
    ),
    "bwb_control_sym_elevon": FeaturePreset(
        name="bwb_control_sym_elevon",
        domain="bwb_scalar_aero",
        columns=(
            "c1_m",
            "b_total_m",
            "sw1_deg",
            "alpha_deg",
            "velocity_mps",
            "altitude_m",
            "delta_e_sym_deg",
        ),
        description=(
            "Explicit symmetric-elevon BWB scalar-aero feature preset. This is "
            "the preferred raw control naming for new datasets: "
            "delta_e_sym_deg means symmetric elevon deflection; "
            "delta_a_diff_deg remains reserved until differential-elevon solver "
            "wiring exists."
        ),
    ),
    "bwb_control_sym_elevon_v3": FeaturePreset(
        name="bwb_control_sym_elevon_v3",
        domain="bwb_scalar_aero",
        columns=(
            "c1_m", "b_total_m", "sw1_deg",
            "elevon_start_frac", "elevon_end_frac", "elevon_hinge_frac",
            "alpha_deg", "velocity_mps", "altitude_m",
            "delta_e_sym_deg",
        ),
        description="BWB v3 pitch preset with variable elevon geometry DVs.",
    ),
    "bwb_diff_elevon_v3": FeaturePreset(
        name="bwb_diff_elevon_v3",
        domain="bwb_scalar_aero",
        columns=(
            "c1_m", "b_total_m", "sw1_deg",
            "elevon_start_frac", "elevon_end_frac", "elevon_hinge_frac",
            "alpha_deg", "velocity_mps", "altitude_m",
            "delta_a_diff_deg",
        ),
        description="BWB v3 roll preset with variable elevon geometry DVs.",
    ),
    "airfoil_xfoil_v1": FeaturePreset(
        name="airfoil_xfoil_v1",
        domain="airfoil_2d_scalar_aero",
        columns=(
            # Operating condition inputs (always present)
            "alpha_deg",
            "log10_reynolds",
            "mach",
            "ncrit",
            # Derived operating features (physics-informed)
            "alpha_sq",           # quadratic alpha term
            # Airfoil geometry statistics (computed at ingest, pre-split)
            "t_c",                # max thickness / chord
            "camber_max",         # max camber / chord
            "le_radius",          # approximate leading-edge radius
            "te_angle_deg",       # trailing-edge included angle
        ),
        description=(
            "Airfoil 2D scalar aero feature set for XFOIL-generated datasets. "
            "Features: operating condition (alpha, log10Re, Mach, Ncrit) + "
            "physics-derived (alpha^2) + geometry stats (t/c, camber, LE radius, "
            "TE angle). CST coefficients can be appended when available. "
            "Group key: airfoil_id. "
            "Targets: cl, cd, cm."
        ),
    ),
    # AERIS_PATCH_CST_AIRFOIL_V1_FEATURE_PRESET
    "airfoil_cst_xfoil_v1": FeaturePreset(
        name="airfoil_cst_xfoil_v1",
        domain="airfoil_2d_scalar_aero",
        columns=(
            "alpha_deg", "log10_reynolds", "mach", "ncrit", "alpha_sq",
            "cst_u0", "cst_u1", "cst_u2", "cst_u3", "cst_u4", "cst_u5", "cst_u6", "cst_u7", "cst_u8",
            "cst_l0", "cst_l1", "cst_l2", "cst_l3", "cst_l4", "cst_l5", "cst_l6", "cst_l7", "cst_l8",
            "cst_dz_te",
        ),
        description=(
            "CST/Kulfan 8th-order airfoil feature preset for XFOIL scalar datasets. "
            "Uses generated CST coefficients plus operating-condition features. "
            "Group key: airfoil_id. Targets: cl, cd, cm."
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
