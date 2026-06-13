"""
AERIS Dynamics — Dataset Label Extractor
=========================================
Converts a DynamicsFoundationResult + MIL-STD-1797B report into a flat
dict of scalar labels for direct insertion into the Paper 1 flyability-aware
dataset.

This module is the bridge between standalone dynamics analysis and the
ML/MDAO pipeline. Every label produced here becomes:
  - A column in the aero dataset CSV (Paper 1 dataset)
  - A training target for the GNN surrogate (Paper 1 model)
  - A constraint input for the MDAO optimizer (Paper 4)

Label schema is versioned. Breaking changes increment schema_version.

Usage:
    labels = extract_dataset_labels(
        foundation_result=result_dict,
        hq_report=report,
        mission=MissionClass.ISR,
    )
    # labels is a flat dict suitable for pd.DataFrame row insertion
"""

from __future__ import annotations

from typing import Any

from aeris.dynamics.mil_std import (
    HandlingQualityReport,
    HQLevel,
    MissionClass,
)

LABEL_SCHEMA_VERSION = "0.2.0"


def _safe(d: dict | None, *keys, default=None):
    """Safely navigate nested dicts."""
    if d is None:
        return default
    obj = d
    for k in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(k, default)
        if obj is None:
            return default
    return obj


def extract_dataset_labels(
    *,
    foundation_result: dict,
    hq_report: HandlingQualityReport | None = None,
    mission: MissionClass = MissionClass.ISR,
    include_derivatives: bool = True,
    include_modes: bool = True,
    include_hq: bool = True,
) -> dict[str, Any]:
    """
    Extract a flat, ML-ready label dict from the dynamics foundation result.

    This is the single function called by the dataset pipeline to extract
    all dynamics labels for one geometry × one flight condition.

    Returns a dict with keys suitable for a CSV column header.
    All values are float, bool, int, or str (no nested dicts).
    Missing values are None (the dataset pipeline decides how to handle them).
    """
    labels: dict[str, Any] = {
        "dyn_label_schema_version": LABEL_SCHEMA_VERSION,
        "dyn_mission_class": mission.value,
    }

    # ── Static stability ──────────────────────────────────────────────────
    sm = _safe(foundation_result, "stability_metrics")
    labels.update({
        "dyn_x_np_m":                   _safe(sm, "x_np_m"),
        "dyn_x_cg_m":                   _safe(sm, "x_cg_m"),
        "dyn_mac_m":                     _safe(sm, "mac_m"),
        "dyn_static_margin":             _safe(sm, "static_margin"),
        "dyn_static_margin_pct_mac":     _safe(sm, "static_margin_percent_mac"),
        "dyn_cma":                       _safe(sm, "cma"),
        "dyn_spiral_metric":             _safe(sm, "spiral_metric"),
        "dyn_longitudinal_interpretation": _safe(sm, "longitudinal_interpretation"),
        "dyn_cma_consistent":            _safe(sm, "cma_consistent_with_static_margin"),
        # Flight condition context
        "dyn_alpha_deg":                 _safe(sm, "alpha_deg"),
        "dyn_velocity_mps":              _safe(sm, "velocity_mps"),
        "dyn_altitude_m":                _safe(sm, "altitude_m"),
        "dyn_dynamic_pressure_pa":       _safe(sm, "dynamic_pressure_pa"),
        "dyn_lift_n":                    _safe(sm, "lift_n"),
        "dyn_drag_n":                    _safe(sm, "drag_n"),
        "dyn_load_factor":               _safe(sm, "load_factor"),
        "dyn_weight_n":                  _safe(sm, "weight_n"),
    })

    # ── Control effectiveness ─────────────────────────────────────────────
    ctrl = _safe(foundation_result, "control_effectiveness")
    labels.update({
        "dyn_cm_per_de_rad":             _safe(ctrl, "cm_per_de_rad"),   # Cmδe
        "dyn_cl_per_de_rad":             _safe(ctrl, "cl_per_de_rad"),   # CLδe
        "dyn_pitch_authority_adequate":  _safe(ctrl, "pitch_authority_adequate"),
    })

    # ── Trim labels ───────────────────────────────────────────────────────
    # These come from the trim result if present; extracted from metadata here
    # The trim command writes trim_result.json separately.
    # Include as None if not available.
    labels.update({
        "dyn_alpha_trim_deg":            None,  # filled by trim pipeline
        "dyn_de_trim_deg":               None,  # filled by trim pipeline
        "dyn_trim_feasible":             None,  # bool: trim solution in bounds
        "dyn_trim_feasible_alpha":       None,  # bool: alpha trim in [-5°,15°]
        "dyn_trim_feasible_de":          None,  # bool: elevon trim in [-25°,25°]
    })

    # ── Stability derivatives (all key ones for Paper 2) ──────────────────
    if include_derivatives:
        long_d = _safe(foundation_result, "stability_derivatives", "longitudinal")
        lat_d  = _safe(foundation_result, "stability_derivatives", "lateral_directional")
        deriv_s = _safe(foundation_result, "stability_derivatives")

        labels.update({
            # Longitudinal
            "dyn_cla":   _safe(long_d, "cla"),
            "dyn_cda":   _safe(long_d, "cda"),
            "dyn_cmq":   _safe(long_d, "cmq"),
            "dyn_clq":   _safe(long_d, "clq"),
            "dyn_cmad":  _safe(long_d, "cmad"),
            # Lateral-directional
            "dyn_clb":   _safe(lat_d, "clb"),
            "dyn_cnb":   _safe(lat_d, "cnb"),
            "dyn_cyb":   _safe(lat_d, "cyb"),
            "dyn_clp":   _safe(lat_d, "clp"),
            "dyn_cnp":   _safe(lat_d, "cnp"),
            "dyn_clr":   _safe(lat_d, "clr"),
            "dyn_cnr":   _safe(lat_d, "cnr"),
            # Sign checks
            "dyn_cma_sign_ok":  _safe(deriv_s, "cma_sign_ok"),
            "dyn_cmq_sign_ok":  _safe(deriv_s, "cmq_sign_ok"),
            "dyn_clb_sign_ok":  _safe(deriv_s, "clb_sign_ok"),
            "dyn_cnb_sign_ok":  _safe(deriv_s, "cnb_sign_ok"),
            "dyn_clp_sign_ok":  _safe(deriv_s, "clp_sign_ok"),
            "dyn_cnr_sign_ok":  _safe(deriv_s, "cnr_sign_ok"),
            "dyn_spiral_stable": _safe(deriv_s, "spiral_stable"),
        })

    # ── Dynamic modes (from state-space analysis if run) ─────────────────
    if include_modes:
        # These are populated by the full state-space analysis module
        # They may be None until Iyy/Izz are provided
        labels.update({
            # Short-period
            "dyn_sp_omega_n_rad_s":   None,
            "dyn_sp_zeta":            None,
            "dyn_sp_period_s":        None,
            "dyn_sp_time_half_s":     None,
            "dyn_sp_stable":          None,
            # Phugoid
            "dyn_ph_omega_n_rad_s":   None,
            "dyn_ph_zeta":            None,
            "dyn_ph_period_s":        None,
            "dyn_ph_stable":          None,
            # Roll subsidence
            "dyn_roll_tau_s":         None,
            "dyn_roll_stable":        None,
            # Spiral
            "dyn_spiral_t2_s":        None,
            "dyn_spiral_mode_stable": None,
            # Dutch roll
            "dyn_dr_omega_n_rad_s":   None,
            "dyn_dr_zeta":            None,
            "dyn_dr_zeta_omega":      None,  # ζ·ω product
            "dyn_dr_stable":          None,
        })

    # ── MIL-STD-1797B classification labels ───────────────────────────────
    if include_hq and hq_report is not None:
        def _level_int(c) -> int | None:
            return c.level.value if c is not None else None

        labels.update({
            "dyn_hq_mission":           hq_report.mission.value,
            "dyn_hq_overall_level":     hq_report.overall_level.value,
            "dyn_hq_flyable":           hq_report.flyable,
            "dyn_hq_mission_compliant": hq_report.mission_compliant,
            "dyn_hq_escalate":          hq_report.overall_escalate,
            # Per-mode levels
            "dyn_hq_sm_level":          _level_int(hq_report.static_margin),
            "dyn_hq_sp_damp_level":     _level_int(hq_report.short_period_damping),
            "dyn_hq_sp_freq_level":     _level_int(hq_report.short_period_frequency),
            "dyn_hq_ph_level":          _level_int(hq_report.phugoid),
            "dyn_hq_roll_level":        _level_int(hq_report.roll_subsidence),
            "dyn_hq_dr_level":          _level_int(hq_report.dutch_roll),
            "dyn_hq_spiral_level":      _level_int(hq_report.spiral),
            # Probabilistic flags (P = 1.0 for deterministic; filled by UQ in Paper 2)
            "dyn_p_level1_sp_damp":     _safe(hq_report.short_period_damping.__dict__ if hq_report.short_period_damping else None, "p_level1"),
            "dyn_p_level1_sm":          _safe(hq_report.static_margin.__dict__ if hq_report.static_margin else None, "p_level1"),
            "dyn_p_level1_ph":          _safe(hq_report.phugoid.__dict__ if hq_report.phugoid else None, "p_level1"),
            "dyn_p_level1_spiral":      _safe(hq_report.spiral.__dict__ if hq_report.spiral else None, "p_level1"),
            # Binary flyability labels (Paper 1 dataset)
            "dyn_label_statically_stable":   (
                _safe(sm, "static_margin") is not None and
                _safe(sm, "static_margin") > 0.0
            ),
            "dyn_label_trimmable":           None,   # filled by trim pipeline
            "dyn_label_control_authority_ok": _safe(ctrl, "pitch_authority_adequate"),
            "dyn_label_mil_level1":          hq_report.overall_level == HQLevel.LEVEL_1,
            "dyn_label_mil_level2_or_better": hq_report.overall_level.value <= 2,
            "dyn_label_mission_flyable":     hq_report.flyable,
        })

    return labels


def fill_trim_labels(
    labels: dict[str, Any],
    *,
    trim_result_dict: dict,
) -> dict[str, Any]:
    """
    Fill trim-related label fields from a trim_result.json dict.
    Call after extract_dataset_labels() with the trim result.
    """
    long = _safe(trim_result_dict, "longitudinal") or {}
    labels["dyn_alpha_trim_deg"]     = _safe(long, "alpha_trim_deg")
    labels["dyn_de_trim_deg"]        = _safe(long, "de_trim_deg")
    labels["dyn_trim_feasible_alpha"] = _safe(long, "alpha_trim_in_bounds")
    labels["dyn_trim_feasible_de"]   = _safe(long, "de_trim_in_bounds")
    # AERIS_PATCH_D12_APPLIED: separate OR-feasibility from strict elevon feasibility.
    # dyn_trim_feasible: legacy OR label — True if any trim mode is in-bounds.
    # dyn_de_trim_feasible: strict label — True only when elevon trim is in-bounds.
    #   This is the operational label for a flight-controlled BWB.
    # dyn_label_trimmable now uses the strict elevon-trim definition.
    labels["dyn_trim_feasible"] = (
        bool(_safe(long, "alpha_trim_in_bounds") or _safe(long, "de_trim_in_bounds"))
    )
    labels["dyn_de_trim_feasible"] = bool(_safe(long, "de_trim_in_bounds"))
    labels["dyn_label_trimmable"] = labels["dyn_de_trim_feasible"]
    return labels


def fill_mode_labels(
    labels: dict[str, Any],
    *,
    longitudinal_modes,   # LongitudinalModes object
    lateral_modes,        # LateralDirectionalModes object
) -> dict[str, Any]:
    """
    Fill dynamic mode label fields from state-space analysis results.
    Call after extract_dataset_labels() when full eigenvalue analysis is available.
    """
    from aeris.dynamics.state_space import LongitudinalModes, LateralDirectionalModes

    if longitudinal_modes and longitudinal_modes.valid:
        sp = longitudinal_modes.short_period
        ph = longitudinal_modes.phugoid
        if sp:
            labels["dyn_sp_omega_n_rad_s"] = sp.omega_n
            labels["dyn_sp_zeta"]          = sp.zeta
            labels["dyn_sp_period_s"]      = sp.period_s
            labels["dyn_sp_time_half_s"]   = sp.time_to_half_s
            labels["dyn_sp_stable"]        = sp.stable
        if ph:
            labels["dyn_ph_omega_n_rad_s"] = ph.omega_n
            labels["dyn_ph_zeta"]          = ph.zeta
            labels["dyn_ph_period_s"]      = ph.period_s
            labels["dyn_ph_stable"]        = ph.stable

    if lateral_modes and lateral_modes.valid:
        roll   = lateral_modes.roll_subsidence
        spiral = lateral_modes.spiral
        dr     = lateral_modes.dutch_roll
        if roll:
            labels["dyn_roll_tau_s"]    = roll.time_constant_s
            labels["dyn_roll_stable"]   = roll.stable
        if spiral:
            labels["dyn_spiral_t2_s"]        = spiral.time_to_double_s
            labels["dyn_spiral_mode_stable"]  = spiral.stable
        if dr:
            labels["dyn_dr_omega_n_rad_s"] = dr.omega_n
            labels["dyn_dr_zeta"]          = dr.zeta
            labels["dyn_dr_zeta_omega"]    = (
                dr.zeta * dr.omega_n
                if dr.zeta is not None and dr.omega_n is not None
                else None
            )
            labels["dyn_dr_stable"] = dr.stable

    return labels


def get_label_schema() -> dict[str, str]:
    """Return a dict of label_key → description for documentation."""
    return {
        "dyn_static_margin_pct_mac":   "Static margin [%MAC]. Positive = stable.",
        "dyn_cma":                     "Pitch stability derivative Cma [/rad]. Must be < 0.",
        "dyn_cm_per_de_rad":           "Pitch control effectiveness Cmδe [/rad].",
        "dyn_sp_zeta":                 "Short-period damping ratio ζ_sp [-].",
        "dyn_sp_omega_n_rad_s":        "Short-period natural frequency ω_sp [rad/s].",
        "dyn_ph_zeta":                 "Phugoid damping ratio ζ_ph [-].",
        "dyn_roll_tau_s":              "Roll subsidence time constant τ_r [s].",
        "dyn_spiral_t2_s":             "Spiral mode doubling time T₂ [s]. None if stable.",
        "dyn_dr_zeta":                 "Dutch roll damping ratio ζ_DR [-].",
        "dyn_dr_zeta_omega":           "Dutch roll ζ_DR·ω_DR product [rad/s].",
        "dyn_hq_overall_level":        "MIL-STD-1797B overall level (1=L1, 2=L2, 3=L3, 4=unacceptable).",
        "dyn_label_statically_stable": "Binary: static margin > 0.",
        "dyn_label_trimmable":         "Binary: trim solution exists within actuator limits.",
        "dyn_label_mil_level1":        "Binary: all classified modes meet Level 1.",
        "dyn_label_mission_flyable":   "Binary: overall Level 1 or Level 2.",
        "dyn_p_level1_sp_damp":        "P(Level 1 short-period damping). 1.0 for deterministic; <1.0 with conformal UQ.",
    }
