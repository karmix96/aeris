"""
AERIS Dynamics — CG Sweep
==========================
Sweeps CG x-position and computes static margin, neutral point, and trim
elevon requirement at each point. Produces:
  - cg_sweep.json  (machine-readable, full detail)
  - cg_sweep.csv   (tabular, for plotting/export)

Engineering use:
  - Find the stable CG envelope (SM > 0)
  - Find the neutral point (SM = 0 crossing)
  - Find minimum trim elevon as a function of CG
"""

from __future__ import annotations

import csv
import math
from dataclasses import asdict
from pathlib import Path
import json

from aeris.aero.io import read_aero_result
from aeris.dynamics.analysis import (
    GRAVITY_MPS2,
    build_dynamics_foundation_result,
    dynamic_pressure,
)
from aeris.dynamics.models import (
    InertiaPlaceholders,
    MassProperties,
    TrimDefinition,
)
from aeris.dynamics.trim import (
    DE_MAX_DEG,
    DE_MIN_DEG,
    estimate_longitudinal_trim,
)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def linspace(start: float, stop: float, n: int) -> list[float]:
    """Pure-Python linspace without numpy dependency."""
    if n < 2:
        return [float(start)]
    step = (stop - start) / (n - 1)
    return [float(start + i * step) for i in range(n)]


def estimate_zero_crossing(cases: list[dict]) -> float | None:
    """
    Linear interpolation estimate of CG where static_margin crosses zero.
    Returns None if no sign change is found in the sweep.
    """
    for a, b in zip(cases[:-1], cases[1:]):
        sm_a = a.get("static_margin")
        sm_b = b.get("static_margin")
        if sm_a is None or sm_b is None:
            continue
        if sm_a == 0.0:
            return float(a["x_cg_m"])
        if sm_b == 0.0:
            return float(b["x_cg_m"])
        if sm_a * sm_b < 0.0:
            x_a = float(a["x_cg_m"])
            x_b = float(b["x_cg_m"])
            return x_a + (0.0 - sm_a) * (x_b - x_a) / (sm_b - sm_a)
    return None


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# AERIS_PATCH_D3_APPLIED: CG-corrected trim estimate for cg_sweep
# ---------------------------------------------------------------------------
def _cg_corrected_trim(
    aero_dict: dict,
    x_cg_m: float,
    x_cg_ref_m: float,
    *,
    run_dir,
) -> "TrimResult":
    """
    Estimate trim elevon at a new CG position by correcting Cm₀.

    Physics: Cm(xcg_new) = Cm(xcg_ref) + CLα·(xcg_ref - xcg_new)/c · α₀
    Reference: [ER] §3.3, moment transfer theorem.

    xcg_ref_m is the CG position at which the AVL aero_result was computed.
    """
    import copy, math
    aero_corrected = copy.deepcopy(aero_dict)
    scalars = aero_corrected.get("scalars") or aero_corrected
    sad = aero_corrected.get("stability_axis_derivatives") or {}
    meta = aero_corrected.get("solver_metadata") or {}
    fc = meta.get("flight_condition") or {}

    cla = sad.get("CLa") or sad.get("cla")
    cm0 = scalars.get("cm") or scalars.get("Cm") or aero_corrected.get("cm")
    alpha_deg = (fc.get("alpha_deg") if isinstance(fc, dict) else None) or 0.0

    # Extract MAC from geometry summary (best effort)
    from aeris.dynamics.analysis import load_geometry_summary
    geo = load_geometry_summary(str(run_dir)) or {}
    mac_m = (geo.get("reference_values") or {}).get("mean_aerodynamic_chord_m")

    if cla is not None and cm0 is not None and mac_m is not None and mac_m > 0:
        alpha_rad = math.radians(float(alpha_deg))
        delta_cm = float(cla) * (x_cg_ref_m - x_cg_m) / float(mac_m) * alpha_rad
        # Inject corrected Cm into the copy
        if "scalars" in aero_corrected:
            aero_corrected["scalars"]["cm"] = float(cm0) + delta_cm
        else:
            aero_corrected["cm"] = float(cm0) + delta_cm

    return estimate_longitudinal_trim(aero_corrected, run_dir)



def run_cg_sweep(
    *,
    run_dir: str | Path,
    mass_kg: float,
    cg_min_m: float,
    cg_max_m: float,
    n: int,
    y_cg_m: float = 0.0,
    z_cg_m: float = 0.0,
    ixx_kg_m2: float | None = None,
    iyy_kg_m2: float | None = None,
    izz_kg_m2: float | None = None,
    x_positive_aft: bool = True,
    sref_m2: float | None = None,
    span_m: float | None = None,
) -> dict:
    """
    Sweep CG x-position from cg_min_m to cg_max_m in n steps.

    For each CG position, computes:
      - Static margin and neutral point
      - Key stability derivatives
      - Trim elevon requirement (Δδe to achieve Cm=0 at current α)

    Returns a summary dict suitable for JSON serialisation.
    """
    run_dir    = Path(run_dir)
    aero_result = read_aero_result(run_dir)

    # Load aero_result as dict for trim analysis
    from aeris.aero.io import find_aero_result_json
    aero_json_path = find_aero_result_json(run_dir)
    import json as _json
    aero_dict = _json.loads(aero_json_path.read_text(encoding="utf-8"))

    cg_values = linspace(cg_min_m, cg_max_m, n)
    cases: list[dict] = []

    for x_cg_m in cg_values:
        mass = MassProperties(
            mass_kg=mass_kg,
            x_cg_m=x_cg_m,
            y_cg_m=y_cg_m,
            z_cg_m=z_cg_m,
            inertia=InertiaPlaceholders(
                ixx_kg_m2=ixx_kg_m2,
                iyy_kg_m2=iyy_kg_m2,
                izz_kg_m2=izz_kg_m2,
            ),
        )

        result = build_dynamics_foundation_result(
            aero_result=aero_result,
            mass_properties=mass,
            source_run_dir=str(run_dir),
            trim_definition=TrimDefinition(enabled=False, notes="CG sweep — schema only."),
            x_positive_aft=x_positive_aft,
            sref_m2=sref_m2,
            span_m=span_m,
        )

        sm   = result.stability_metrics
        ctrl = result.control_effectiveness
        deriv = result.stability_derivatives

        # Trim elevon estimate at this CG: what δe brings Cm to 0?
        # AERIS_PATCH_D3_APPLIED: correct Cm₀ for CG position before trim.
        # The AVL result was computed at x_cg_ref_m; we transfer the moment.
        x_cg_ref_m = float(aero_dict.get("solver_metadata", {}).get(
            "flight_condition", {}
        ).get("x_cg_m") or cg_values[0])  # fallback: use first CG as ref
        trim_res = _cg_corrected_trim(
            aero_dict, x_cg_m=x_cg_m, x_cg_ref_m=x_cg_ref_m, run_dir=run_dir
        )
        de_trim  = trim_res.longitudinal.de_trim_deg
        de_ok    = trim_res.longitudinal.de_trim_in_bounds

        cases.append({
            "x_cg_m":                       round(x_cg_m, 6),
            "static_margin":                 sm.static_margin,
            "static_margin_percent_mac":     sm.static_margin_percent_mac,
            "x_np_m":                        sm.x_np_m,
            "mac_m":                         sm.mac_m,
            "cma":                           deriv.longitudinal.cma,
            "cmde":                          ctrl.cm_per_de_rad,
            "de_trim_deg":                   round(de_trim, 4) if de_trim is not None else None,
            "de_trim_in_bounds":             de_ok,
            "cma_consistent_with_static_margin": sm.cma_consistent_with_static_margin,
            "longitudinal_interpretation":   sm.longitudinal_interpretation,
            "pitch_authority_adequate":      ctrl.pitch_authority_adequate,
        })

    # ── Summary ───────────────────────────────────────────────────────────────
    positive_cases = [c for c in cases if c["static_margin"] is not None
                      and c["static_margin"] > 0.0]
    trimmable_cases = [c for c in cases if c.get("de_trim_in_bounds") is True]

    zero_crossing_m = estimate_zero_crossing(cases)

    min_sm     = min((c["static_margin_percent_mac"] for c in cases
                      if c["static_margin_percent_mac"] is not None), default=None)
    max_sm     = max((c["static_margin_percent_mac"] for c in cases
                      if c["static_margin_percent_mac"] is not None), default=None)

    summary = {
        "schema_version": "0.2.0",
        "run_dir": str(run_dir),
        "mass_kg": mass_kg,
        "cg_min_m": cg_min_m,
        "cg_max_m": cg_max_m,
        "n": n,
        "x_positive_aft": x_positive_aft,
        # Stability envelope
        "stable_cg_min_m": min(c["x_cg_m"] for c in positive_cases) if positive_cases else None,
        "stable_cg_max_m": max(c["x_cg_m"] for c in positive_cases) if positive_cases else None,
        "static_margin_zero_crossing_estimate_m": zero_crossing_m,
        "min_static_margin_percent_mac": round(min_sm, 4) if min_sm is not None else None,
        "max_static_margin_percent_mac": round(max_sm, 4) if max_sm is not None else None,
        # Trim envelope
        "trimmable_cg_min_m": min(c["x_cg_m"] for c in trimmable_cases) if trimmable_cases else None,
        "trimmable_cg_max_m": max(c["x_cg_m"] for c in trimmable_cases) if trimmable_cases else None,
        "cmde_available": any(c.get("cmde") is not None for c in cases),
        # Per-CG cases
        "cases": cases,
    }

    return summary


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def write_cg_sweep(summary: dict, output_dir: str | Path) -> Path:
    """Write cg_sweep.json to output_dir."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "cg_sweep.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return path


def write_cg_sweep_csv(summary: dict, output_dir: str | Path) -> Path:
    """Write cg_sweep.csv to output_dir."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "cg_sweep.csv"

    cases = summary.get("cases", [])
    if not cases:
        path.write_text("", encoding="utf-8")
        return path

    fieldnames = [
        "x_cg_m",
        "static_margin",
        "static_margin_percent_mac",
        "x_np_m",
        "mac_m",
        "cma",
        "cmde",
        "de_trim_deg",
        "de_trim_in_bounds",
        "cma_consistent_with_static_margin",
        "longitudinal_interpretation",
        "pitch_authority_adequate",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for case in cases:
            writer.writerow({k: case.get(k) for k in fieldnames})

    return path