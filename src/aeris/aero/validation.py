from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .models import AeroInput, AeroResult


def validate_aero_input(aero_input: AeroInput) -> list[str]:
    errors: list[str] = []

    if aero_input.geometry is None:
        errors.append("Missing geometry.")
        return errors

    if aero_input.geometry.airplane is None:
        errors.append("Missing geometry airplane object.")

    fc = aero_input.flight_condition
    if not math.isfinite(fc.alpha_deg):
        errors.append("Flight condition alpha_deg must be finite.")
    if not math.isfinite(fc.beta_deg):
        errors.append("Flight condition beta_deg must be finite.")
    if not math.isfinite(fc.velocity_mps) or fc.velocity_mps <= 0.0:
        errors.append("Flight condition velocity_mps must be finite and > 0.")
    if not math.isfinite(fc.altitude_m):
        errors.append("Flight condition altitude_m must be finite.")
    if not math.isfinite(fc.p_rad_s):
        errors.append("Flight condition p_rad_s must be finite.")
    if not math.isfinite(fc.q_rad_s):
        errors.append("Flight condition q_rad_s must be finite.")
    if not math.isfinite(fc.r_rad_s):
        errors.append("Flight condition r_rad_s must be finite.")

    settings = aero_input.settings
    if settings.timeout_sec <= 0:
        errors.append("Solver timeout_sec must be > 0.")

    return errors


def validate_aero_result(result: AeroResult) -> list[str]:
    errors: list[str] = []

    required_scalars = {
        "cl": result.cl,
        "cd": result.cd,
        "cm": result.cm,
        "l_over_d": result.l_over_d,
        "cy": result.cy,
        "cl_roll": result.cl_roll,
        "cn": result.cn,
    }

    for name, value in required_scalars.items():
        if value is None:
            errors.append(f"Missing required output '{name}'.")
        elif not math.isfinite(value):
            errors.append(f"Non-finite required output '{name}'.")

    return errors


def validate_avl_parser_consistency(result: AeroResult, atol: float = 1e-6) -> list[str]:
    """
    Cross-check parsed AERIS fields against raw AVL-parsed file dictionaries already
    stored in result.raw_outputs.

    This is a trust check on our parser layer, not a solver convergence check.
    """
    errors: list[str] = []

    raw_outputs = result.raw_outputs or {}
    stability_raw = raw_outputs.get("_stability_file_parsed", {}) or {}
    body_raw = raw_outputs.get("_body_file_parsed", {}) or {}

    # --------------------------
    # Totals consistency checks
    # --------------------------
    scalar_pairs = [
        ("cl", result.cl, "CL"),
        ("cd", result.cd, "CD"),
        ("cm", result.cm, "Cm"),
        ("cy", result.cy, "CY"),
        ("cl_roll", result.cl_roll, "Cl"),
        ("cn", result.cn, "Cn"),
        ("cd_ind", result.cd_ind, "CDind"),
        ("cd_ff", result.cd_ff, "CDff"),
        ("span_efficiency", result.span_efficiency, "e"),
    ]

    for result_name, parsed_value, raw_key in scalar_pairs:
        raw_value = _safe_float(raw_outputs.get(raw_key))
        if parsed_value is None or raw_value is None:
            errors.append(f"Missing scalar comparison for {result_name}/{raw_key}.")
            continue
        if not _close(parsed_value, raw_value, atol=atol):
            errors.append(
                f"Scalar mismatch for {result_name}/{raw_key}: "
                f"result={parsed_value} raw={raw_value}"
            )

    # --------------------------
    # Stability derivative checks
    # --------------------------
    for key, parsed_value in (result.stability_axis_derivatives or {}).items():
        if parsed_value is None:
            continue
        raw_value = _safe_float(stability_raw.get(key))
        if raw_value is None:
            errors.append(f"Missing stability raw key '{key}'.")
            continue
        if not _close(parsed_value, raw_value, atol=atol):
            errors.append(
                f"Stability derivative mismatch for {key}: "
                f"result={parsed_value} raw={raw_value}"
            )

    # --------------------------
    # Body derivative checks
    # --------------------------
    for key, parsed_value in (result.body_axis_derivatives or {}).items():
        if parsed_value is None:
            continue
        raw_value = _safe_float(body_raw.get(key))
        if raw_value is None:
            errors.append(f"Missing body raw key '{key}'.")
            continue
        if not _close(parsed_value, raw_value, atol=atol):
            errors.append(
                f"Body derivative mismatch for {key}: "
                f"result={parsed_value} raw={raw_value}"
            )

    # --------------------------
    # Derived metric checks
    # --------------------------
    spiral_metric = (result.derived_metrics or {}).get("spiral_metric")
    stab = result.stability_axis_derivatives or {}
    clb = _safe_float(stab.get("Clb"))
    cnr = _safe_float(stab.get("Cnr"))
    clr = _safe_float(stab.get("Clr"))
    cnb = _safe_float(stab.get("Cnb"))

    xnp_from_group = _safe_float(stab.get("Xnp"))
    xnp_top_level = _safe_float(result.x_np)
    if xnp_from_group is not None:
        if xnp_top_level is None:
            errors.append("Missing top-level scalar 'x_np'.")
        elif not _close(xnp_top_level, xnp_from_group, atol=atol):
            errors.append(
                f"Scalar mismatch for x_np/Xnp: "
                f"result={xnp_top_level} raw_group={xnp_from_group}"
            )

    expected_spiral = None
    try:
        if None not in (clb, cnr, clr, cnb) and clr != 0.0 and cnb != 0.0:
            expected_spiral = (clb * cnr) / (clr * cnb)
    except Exception:
        expected_spiral = None

    if expected_spiral is not None:
        if spiral_metric is None:
            errors.append("Missing derived metric 'spiral_metric'.")
        elif not _close(spiral_metric, expected_spiral, atol=atol):
            errors.append(
                f"Derived metric mismatch for spiral_metric: "
                f"result={spiral_metric} expected={expected_spiral}"
            )

    return errors


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
        if not math.isfinite(out):
            return None
        return out
    except Exception:
        return None


def _close(a: float, b: float, atol: float = 1e-6) -> bool:
    return abs(a - b) <= atol