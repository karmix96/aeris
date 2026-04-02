"""
Validation utilities for aerodynamic inputs and outputs.

This module contains generic aero-contract validation and, for the current AVL
integration, parser consistency checks that compare normalized AERIS results
against raw parsed solver data. Generic validation should remain solver-agnostic;
solver-specific trust checks may later move closer to their adapter layer.
"""

from __future__ import annotations

import math

from aeris.aero.models import AeroInput, AeroResult


def validate_aero_input(aero_input: AeroInput) -> list[str]:
    errors: list[str] = []

    fc = aero_input.flight_condition

    numeric_checks = {
        "alpha_deg": fc.alpha_deg,
        "beta_deg": fc.beta_deg,
        "velocity_mps": fc.velocity_mps,
        "altitude_m": fc.altitude_m,
        "p_rad_s": fc.p_rad_s,
        "q_rad_s": fc.q_rad_s,
        "r_rad_s": fc.r_rad_s,
    }

    if fc.mach is not None:
        numeric_checks["mach"] = fc.mach

    for name, value in numeric_checks.items():
        try:
            fval = float(value)
        except Exception:
            errors.append(f"{name} is not numeric: {value!r}")
            continue

        if not math.isfinite(fval):
            errors.append(f"{name} is not finite: {value!r}")

    if float(fc.velocity_mps) <= 0.0:
        errors.append(f"velocity_mps must be > 0, got {fc.velocity_mps}")

    if aero_input.geometry is None:
        errors.append("geometry is missing")
    else:
        if aero_input.geometry.airplane is None:
            errors.append("geometry.airplane is missing")
        if not aero_input.geometry.view_id:
            errors.append("geometry.view_id is missing")

    return errors


def validate_aero_result(result: AeroResult) -> list[str]:
    errors: list[str] = []

    # ---- primary force/moment scalars ----
    primary_scalars = {
        "cl": result.cl,
        "cd": result.cd,
        "cm": result.cm,
        "cy": result.cy,
        "cl_roll": result.cl_roll,
        "cn": result.cn,
    }

    for name, value in primary_scalars.items():
        if value is None:
            errors.append(f"Required result scalar '{name}' is missing.")
            continue
        try:
            fval = float(value)
        except Exception:
            errors.append(f"Required result scalar '{name}' is not numeric: {value!r}")
            continue
        if not math.isfinite(fval):
            errors.append(f"Required result scalar '{name}' is not finite: {value!r}")

    # ---- drag-specific pathology logic ----
    if result.cd is None:
        errors.append("Aerodynamic result has missing CD.")
    else:
        try:
            cd = float(result.cd)
            if not math.isfinite(cd):
                errors.append(f"Aerodynamic result has non-finite CD: {result.cd!r}")
            elif cd <= 0.0:
                errors.append(f"Aerodynamic result has non-positive CD: CD={cd}")
        except Exception:
            pass

    # ---- l/d should only be required if drag is healthy ----
    if result.cd is not None:
        try:
            cd = float(result.cd)
            if math.isfinite(cd) and cd > 0.0:
                if result.l_over_d is None:
                    errors.append(
                        "Cannot compute l_over_d despite positive CD."
                    )
                else:
                    ld = float(result.l_over_d)
                    if not math.isfinite(ld):
                        errors.append(
                            f"l_over_d is not finite: {result.l_over_d!r}"
                        )
        except Exception:
            pass

    optional_scalar_groups = [
        ("stability_axis_derivatives", result.stability_axis_derivatives),
        ("body_axis_derivatives", result.body_axis_derivatives),
        ("derived_metrics", result.derived_metrics),
    ]

    for group_name, group in optional_scalar_groups:
        for key, value in group.items():
            if value is None:
                continue
            try:
                fval = float(value)
            except Exception:
                errors.append(f"{group_name}.{key} is not numeric: {value!r}")
                continue
            if not math.isfinite(fval):
                errors.append(f"{group_name}.{key} is not finite: {value!r}")

    if result.runtime_sec is not None:
        try:
            runtime = float(result.runtime_sec)
            if not math.isfinite(runtime) or runtime < 0.0:
                errors.append(f"runtime_sec is invalid: {result.runtime_sec!r}")
        except Exception:
            errors.append(f"runtime_sec is not numeric: {result.runtime_sec!r}")

    return errors