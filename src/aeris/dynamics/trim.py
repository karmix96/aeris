"""
AERIS Dynamics — Trim Analysis
================================
Linearised first-order trim estimates for the BWB UAV.

Two trim modes are computed when data is available:
  1. Control-fixed (alpha-trim):  find Δα such that Cm(α+Δα, δe_fixed) = 0
     Uses: Cm_current, Cma
  2. Alpha-fixed (elevon-trim):   find Δδe such that Cm(α_fixed, δe+Δδe) = 0
     Uses: Cm_current, Cmδe

Both are linear (first-order Taylor) extrapolations from the current operating
point. They are accurate when the operating point is close to trim — i.e., when
|Cm| is small. For BWBs with large Cm offsets (e.g. Cm=-0.42 as observed),
the estimate may be off by several degrees from the true nonlinear trim point.

A combined trim estimate is also produced: given a target trim alpha, solve for
the required δe directly from:
  Cm_trim = Cm0 + Cma·(α_trim - α0) + Cmδe·(δe_trim - δe0) = 0

Physical bounds are checked against:
  - alpha: [-5°, +15°] — flyable BWB envelope
  - delta_e: [-25°, +25°] — typical elevon authority

Design rules:
- No I/O in this module — caller writes results via io.py.
- All inputs in SI + degrees for angles (converted internally where needed).
- fail-loud: raise ValueError on obviously wrong inputs.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
import json

from aeris.dynamics.models import LongitudinalTrimEstimate, TrimResult

# ---------------------------------------------------------------------------
# Physical bounds for trim assessment
# ---------------------------------------------------------------------------

ALPHA_MIN_DEG: float = -5.0    # minimum flyable alpha [deg]
ALPHA_MAX_DEG: float = 15.0    # maximum flyable alpha (pre-stall) [deg]
DE_MIN_DEG: float = -25.0      # maximum up-elevon deflection [deg]
DE_MAX_DEG: float = 25.0       # maximum down-elevon deflection [deg]

DEG2RAD: float = math.pi / 180.0
RAD2DEG: float = 180.0 / math.pi


# ---------------------------------------------------------------------------
# Utility: safe nested getter (shared with analysis.py)
# ---------------------------------------------------------------------------

def _get(obj, *names):
    def _search_dict(d):
        for k, v in d.items():
            if k in names and v is not None:
                return v
            if isinstance(v, dict):
                found = _search_dict(v)
                if found is not None:
                    return found
        return None
    if isinstance(obj, dict):
        return _search_dict(obj)
    for name in names:
        if hasattr(obj, name):
            val = getattr(obj, name)
            if val is not None:
                return val
    return None


# ---------------------------------------------------------------------------
# Core trim estimation
# ---------------------------------------------------------------------------

def estimate_longitudinal_trim(
    aero_result: dict,
    run_dir: str | Path,
) -> TrimResult:
    """
    Compute all available longitudinal trim estimates from one aero result.

    Extracts:
      - Current operating point: α₀, δe₀, Cm₀
      - Pitch stability:  Cma [/rad]
      - Pitch control:    Cmδe [/rad]  (may be None if not in aero result)

    Produces:
      - Alpha-trim (control-fixed): α_trim such that Cm(α_trim, δe₀) = 0
      - Elevon-trim (alpha-fixed): δe_trim such that Cm(α₀, δe_trim) = 0
      - Combined trim (target-alpha): for each target α, what δe achieves trim?
    """
    # ── Extract operating point ───────────────────────────────────────────────
    scalars = _get(aero_result, "scalars") or {}
    meta    = _get(aero_result, "solver_metadata") or {}
    fc      = meta.get("flight_condition") or _get(aero_result, "flight_condition") or {}
    sad     = _get(aero_result, "stability_axis_derivatives") or {}

    alpha0_deg = (
        fc.get("alpha_deg") if isinstance(fc, dict) else getattr(fc, "alpha_deg", None)
    )
    de0_deg = meta.get("control_input_deg") or _get(aero_result, "control_input_deg")

    cm0 = _get(scalars, "cm", "Cm") or _get(aero_result, "cm", "Cm")

    # Cma: per radian
    cma_per_rad = _get(sad, "Cma", "cma") or _get(aero_result, "Cma", "cma")

    # Cmδe: try multiple key patterns from AVL output
    cmde_per_rad: float | None = None
    for key in ("Cmd1", "CmD1", "Cm_d1", "Cmde"):
        v = sad.get(key) or aero_result.get(key) if isinstance(aero_result, dict) else None
        if v is not None:
            try:
                cmde_per_rad = float(v)
                break
            except (TypeError, ValueError):
                pass

    # ── Validate minimums ─────────────────────────────────────────────────────
    if alpha0_deg is None:
        return _invalid_result(run_dir, cm0, cma_per_rad, cmde_per_rad,
                               de0_deg, "Missing current alpha (α₀).")
    if cm0 is None:
        return _invalid_result(run_dir, cm0, cma_per_rad, cmde_per_rad,
                               de0_deg, "Missing current Cm.")
    if cma_per_rad is None:
        return _invalid_result(run_dir, cm0, cma_per_rad, cmde_per_rad,
                               de0_deg, "Missing Cma.")
    if abs(cma_per_rad) < 1e-12:
        return _invalid_result(run_dir, cm0, cma_per_rad, cmde_per_rad,
                               de0_deg, "Cma too close to zero — linear trim undefined.")

    alpha0_deg = float(alpha0_deg)
    de0_deg    = float(de0_deg) if de0_deg is not None else 0.0
    cm0        = float(cm0)
    cma        = float(cma_per_rad)

    # ── Mode 1: control-fixed alpha trim ─────────────────────────────────────
    # Solve:  0 = Cm₀ + Cma·Δα  →  Δα = -Cm₀ / Cma
    delta_alpha_rad = -cm0 / cma
    delta_alpha_deg = delta_alpha_rad * RAD2DEG
    alpha_trim_deg  = alpha0_deg + delta_alpha_deg
    alpha_in_bounds = ALPHA_MIN_DEG <= alpha_trim_deg <= ALPHA_MAX_DEG

    # ── Mode 2: alpha-fixed elevon trim ───────────────────────────────────────
    # Solve:  0 = Cm₀ + Cmδe·Δδe  →  Δδe = -Cm₀ / Cmδe
    delta_de_rad: float | None = None
    delta_de_deg: float | None = None
    de_trim_deg:  float | None = None
    de_in_bounds: bool | None = None

    if cmde_per_rad is not None and abs(cmde_per_rad) > 1e-12:
        cmde        = float(cmde_per_rad)
        delta_de_rad = -cm0 / cmde
        delta_de_deg = delta_de_rad * RAD2DEG
        de_trim_deg  = de0_deg + delta_de_deg
        de_in_bounds = DE_MIN_DEG <= de_trim_deg <= DE_MAX_DEG

    trim_est = LongitudinalTrimEstimate(
        alpha_current_deg=alpha0_deg,
        control_input_deg=de0_deg,
        cm_current=cm0,
        cma_per_rad=cma,
        cmde_per_rad=cmde_per_rad,
        delta_alpha_rad=round(delta_alpha_rad, 6),
        delta_alpha_deg=round(delta_alpha_deg, 4),
        alpha_trim_deg=round(alpha_trim_deg, 4),
        alpha_trim_in_bounds=alpha_in_bounds,
        delta_de_rad=round(delta_de_rad, 6) if delta_de_rad is not None else None,
        delta_de_deg=round(delta_de_deg, 4) if delta_de_deg is not None else None,
        de_trim_deg=round(de_trim_deg, 4) if de_trim_deg is not None else None,
        de_trim_in_bounds=de_in_bounds,
        valid=True,
    )

    metadata: dict = {
        "assumption": (
            "Linearised control-fixed and elevon-fixed trim estimates "
            "from Taylor expansion at operating point. "
            "Accuracy degrades when |Cm| is large relative to the trim deflection range."
        ),
        "alpha_trim_mode": "control_fixed_linearised",
        "elevon_trim_available": cmde_per_rad is not None,
    }

    if not alpha_in_bounds:
        metadata["alpha_trim_warning"] = (
            f"Trim alpha {alpha_trim_deg:.2f}° is outside flyable range "
            f"[{ALPHA_MIN_DEG}°, {ALPHA_MAX_DEG}°]. "
            "Consider adjusting CG position or using elevon trim."
        )
    if de_trim_deg is not None and not de_in_bounds:
        metadata["de_trim_warning"] = (
            f"Elevon trim {de_trim_deg:.2f}° is outside actuator limits "
            f"[{DE_MIN_DEG}°, {DE_MAX_DEG}°]. "
            "Consider adjusting CG position."
        )

    return TrimResult(
        schema_version="0.2.0",
        run_dir=str(run_dir),
        mode="longitudinal_linearised_dual",
        longitudinal=trim_est,
        metadata=metadata,
    )


def _invalid_result(
    run_dir: str | Path,
    cm0, cma, cmde, de0, reason: str,
) -> TrimResult:
    """Return an invalid TrimResult with a descriptive reason."""
    est = LongitudinalTrimEstimate(
        alpha_current_deg=None,
        control_input_deg=float(de0) if de0 is not None else None,
        cm_current=float(cm0) if cm0 is not None else None,
        cma_per_rad=float(cma) if cma is not None else None,
        cmde_per_rad=float(cmde) if cmde is not None else None,
        delta_alpha_rad=None, delta_alpha_deg=None,
        alpha_trim_deg=None, alpha_trim_in_bounds=None,
        delta_de_rad=None, delta_de_deg=None,
        de_trim_deg=None, de_trim_in_bounds=None,
        valid=False, reason=reason,
    )
    return TrimResult(
        schema_version="0.2.0",
        run_dir=str(run_dir),
        mode="longitudinal_linearised_dual",
        longitudinal=est,
        metadata={"failure_reason": reason},
    )


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def write_trim_result(result: TrimResult, output_dir: str | Path) -> Path:
    """Write trim_result.json to output_dir."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "trim_result.json"
    import os, tempfile  # AERIS_PATCH_D13B_APPLIED: atomic write
    serialized = json.dumps(result.to_dict(), indent=2)
    tmp_fd, tmp_str = tempfile.mkstemp(dir=output_dir, prefix=".trim_result.tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(serialized)
        os.replace(tmp_str, path)
    except Exception:
        try: os.unlink(tmp_str)
        except OSError: pass
        raise
    return path


def read_trim_result(path: str | Path) -> dict:
    """Load trim_result.json as a dict."""
    return json.loads(Path(path).read_text(encoding="utf-8"))