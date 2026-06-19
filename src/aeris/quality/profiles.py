from __future__ import annotations


GEOMETRY_QC_PROFILES: dict[str, list[str]] = {
    "basic": [
        "geometry_manifest_consistency_v1",
        "geometry_required_columns_v1",
        "geometry_no_duplicate_ids_v1",
        "geometry_metadata_no_nan_v1",
        "geometry_basic_ranges_v1",
        "geometry_required_files_v1",
    ],
    "production": [
        "geometry_manifest_consistency_v1",
        "geometry_required_columns_v1",
        "geometry_no_duplicate_ids_v1",
        "geometry_metadata_no_nan_v1",
        "geometry_basic_ranges_v1",
        "geometry_required_files_v1",
        "geometry_scalar_consistency_v1",
        "geometry_chord_ratio_sanity_v1",
        "geometry_planform_parameter_sanity_v1",
        "geometry_twist_dihedral_ranges_v1",
    ],
    "strict": [
        "geometry_manifest_consistency_v1",
        "geometry_required_columns_v1",
        "geometry_no_duplicate_ids_v1",
        "geometry_metadata_no_nan_v1",
        "geometry_basic_ranges_v1",
        "geometry_required_files_v1",
        "geometry_scalar_consistency_v1",
        "geometry_chord_ratio_sanity_v1",
        "geometry_planform_parameter_sanity_v1",
        "geometry_twist_dihedral_ranges_v1",   # new: twist/dihedral physical bounds
    ],
}

AERO_QC_PROFILES: dict[str, list[str]] = {
    "basic": [
        "aero_manifest_consistency_v1",
        "aero_targets_finite_v1",
        "aero_grid_complete_v1",
        "aero_zero_control_once_v1",
        "aero_control_diagnostics_v1",
        "aero_control_effectiveness_v1",
        "aero_basic_ranges_v1",
    ],
    "production": [
        "aero_manifest_consistency_v1",
        "aero_targets_finite_v1",
        "aero_grid_complete_v1",
        "aero_zero_control_once_v1",
        "aero_control_diagnostics_v1",
        "aero_control_effectiveness_v1",
        "aero_basic_ranges_v1",
        "aero_cl_alpha_trend_v1",
        "aero_cm_control_trend_v1",
    ],
    "strict": [
        "aero_manifest_consistency_v1",
        "aero_targets_finite_v1",
        "aero_grid_complete_v1",
        "aero_zero_control_once_v1",
        "aero_control_diagnostics_v1",
        "aero_control_effectiveness_v1",
        "aero_basic_ranges_v1",
        "aero_cl_alpha_trend_v1",
        "aero_cm_control_trend_v1",
        "aero_outlier_scan_v1",
        "aero_ld_sanity_v1",
        "aero_profile_drag_envelope_v1",
        "aero_beta_zero_lateral_sanity_v1",
        "aero_target_variation_v1",         # data integrity: no collapsed outputs
        # NOTE: Cmde sign check is part of aero_cm_control_trend_v1 (strict only)
        # It fires when dCm/d(ctrl) > 0, indicating inverted elevon convention.
    ],
}


def _resolve_profile(name: str | None, mapping: dict[str, list[str]], default: str = "basic") -> str:
    if name is None:
        return default

    key = name.strip().lower()
    if key not in mapping:
        return default
    return key


def resolve_geometry_profile(name: str | None) -> tuple[str, list[str]]:
    key = _resolve_profile(name, GEOMETRY_QC_PROFILES, default="basic")
    return key, GEOMETRY_QC_PROFILES[key]


def resolve_aero_profile(name: str | None) -> tuple[str, list[str]]:
    key = _resolve_profile(name, AERO_QC_PROFILES, default="basic")
    return key, AERO_QC_PROFILES[key]