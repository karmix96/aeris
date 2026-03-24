from __future__ import annotations

import math
from typing import Any

from aeris.aero.models import AeroResult


def _is_close(a: float | None, b: float | None, *, atol: float = 1e-6, rtol: float = 1e-4) -> bool:
    if a is None or b is None:
        return False
    if not math.isfinite(a) or not math.isfinite(b):
        return False
    return abs(a - b) <= atol + rtol * max(abs(a), abs(b))


def validate_avl_parser_consistency(result: AeroResult) -> list[str]:
    """
    Validate consistency between normalized AERIS result fields and raw AVL-parsed data.

    This is AVL-specific trust/QC logic and should not live in generic aero validation.
    """
    errors: list[str] = []

    raw = result.raw_outputs or {}
    stability_raw = raw.get("_stability_file_parsed", {}) or {}
    body_raw = raw.get("_body_file_parsed", {}) or {}

    scalar_checks = [
        ("CL", result.cl),
        ("CD", result.cd),
        ("Cm", result.cm),
        ("CY", result.cy),
        ("Cl", result.cl_roll),
        ("Cn", result.cn),
    ]

    for raw_key, normalized_val in scalar_checks:
        raw_val = _to_float_or_none(raw.get(raw_key))
        if raw_val is None and normalized_val is None:
            continue
        if raw_val is None and normalized_val is not None:
            errors.append(f"Missing raw AVL scalar '{raw_key}' for normalized value.")
            continue
        if raw_val is not None and normalized_val is None:
            errors.append(f"Normalized scalar missing for raw AVL scalar '{raw_key}'.")
            continue
        if not _is_close(raw_val, normalized_val):
            errors.append(
                f"Scalar mismatch for {raw_key}: raw={raw_val}, normalized={normalized_val}"
            )

    stab_checks = [
        "CLa", "CYb", "Clb", "Cma", "Cnb",
        "Clp", "Cmq", "Cnr", "Clr", "Cnp",
        "Xnp",
    ]
    for key in stab_checks:
        raw_val = _to_float_or_none(stability_raw.get(key))
        norm_val = _to_float_or_none(result.stability_axis_derivatives.get(key))
        if raw_val is None and norm_val is None:
            continue
        if raw_val is None or norm_val is None:
            errors.append(f"Stability derivative presence mismatch for {key}.")
            continue
        if not _is_close(raw_val, norm_val):
            errors.append(
                f"Stability derivative mismatch for {key}: raw={raw_val}, normalized={norm_val}"
            )

    body_checks = [
        "CXu", "CXv", "CXw",
        "CYu", "CYv", "CYw",
        "CZu", "CZv", "CZw",
        "Clu", "Clv", "Clw",
        "Cmu", "Cmv", "Cmw",
        "Cnu", "Cnv", "Cnw",
    ]
    for key in body_checks:
        raw_val = _to_float_or_none(body_raw.get(key))
        norm_val = _to_float_or_none(result.body_axis_derivatives.get(key))
        if raw_val is None and norm_val is None:
            continue
        if raw_val is None or norm_val is None:
            errors.append(f"Body derivative presence mismatch for {key}.")
            continue
        if not _is_close(raw_val, norm_val):
            errors.append(
                f"Body derivative mismatch for {key}: raw={raw_val}, normalized={norm_val}"
            )

    raw_xnp = _to_float_or_none(stability_raw.get("Xnp"))
    if raw_xnp is not None or result.x_np is not None:
        if raw_xnp is None or result.x_np is None or not _is_close(raw_xnp, result.x_np):
            errors.append(f"Neutral point mismatch: raw={raw_xnp}, normalized={result.x_np}")

    clb = _to_float_or_none(result.stability_axis_derivatives.get("Clb"))
    cnr = _to_float_or_none(result.stability_axis_derivatives.get("Cnr"))
    clr = _to_float_or_none(result.stability_axis_derivatives.get("Clr"))
    cnb = _to_float_or_none(result.stability_axis_derivatives.get("Cnb"))
    stored_spiral = _to_float_or_none(result.derived_metrics.get("spiral_metric"))

    recomputed_spiral = None
    try:
        if None not in (clb, cnr, clr, cnb) and clr != 0.0 and cnb != 0.0:
            recomputed_spiral = float((clb * cnr) / (clr * cnb))
    except Exception:
        recomputed_spiral = None

    if recomputed_spiral is None and stored_spiral is None:
        return errors

    if recomputed_spiral is None or stored_spiral is None:
        errors.append(
            f"Spiral metric presence mismatch: recomputed={recomputed_spiral}, stored={stored_spiral}"
        )
        return errors

    if not _is_close(recomputed_spiral, stored_spiral, atol=1e-6, rtol=1e-4):
        errors.append(
            f"Spiral metric mismatch: recomputed={recomputed_spiral}, stored={stored_spiral}"
        )

    return errors


def _to_float_or_none(value: Any) -> float | None:
    try:
        val = float(value)
        if not math.isfinite(val):
            return None
        return val
    except Exception:
        return None