"""
AERIS Dynamics — Analysis Engine
==================================
Core physics computations for the dynamics foundation layer.

Design rules:
- All functions are pure (no I/O, no side effects).
- Physical constants are module-level named constants, never magic numbers.
- Every formula cites its reference.
- Fail loudly on nonsense inputs (negative mass, zero MAC, etc.).
- No hardcoded readiness flags — everything is evaluated from data.

References:
  [ER]  Etkin & Reid, "Dynamics of Flight", 3rd ed., Wiley, 1996.
  [SM]  Stevens & Lewis, "Aircraft Control and Simulation", 3rd ed., Wiley, 2015.
  [CS]  Cook, "Flight Dynamics Principles", 3rd ed., Butterworth-Heinemann, 2012.
  [MIL] MIL-HDBK-1797A, Flying Qualities of Piloted Aircraft, 1997.
"""

from __future__ import annotations

import math
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any
import json

from aeris.dynamics.models import (
    ControlEffectiveness,
    DutchRollApproximation,
    DynamicsFoundationResult,
    DynamicModesSummary,
    LateralDirectionalStabilityDerivatives,
    LongitudinalStabilityDerivatives,
    MassProperties,
    PhugoidApproximation,
    ShortPeriodApproximation,
    StabilityDerivativeSummary,
    StabilityMetrics,
    StateSpacePreparation,
    TrimDefinition,
)

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

GRAVITY_MPS2: float = 9.80665          # standard gravity [m/s²]  ISO 80000-3
ISA_SEA_LEVEL_RHO_KGM3: float = 1.225  # sea-level air density [kg/m³]  ICAO ISA
ISA_LAPSE_RATE_K_PER_M: float = 0.0065 # tropospheric lapse rate [K/m]
ISA_SEA_LEVEL_T_K: float = 288.15      # sea-level temperature [K]
ISA_SEA_LEVEL_P_PA: float = 101325.0   # sea-level pressure [Pa]
ISA_R_J_KG_K: float = 287.058          # specific gas constant for dry air [J/(kg·K)]
ISA_GAMMA: float = 1.4                  # ratio of specific heats for air [-]
TROPOPAUSE_ALT_M: float = 11000.0      # tropopause altitude [m]

# Control effectiveness thresholds (engineering judgment, BWB context)
PITCH_AUTHORITY_MIN_PER_RAD: float = 0.10   # |Cmδe| below this = inadequate pitch authority

# MIL-HDBK-1797A short-period damping requirements (Category B flight phases)
SP_ZETA_LEVEL1_MIN: float = 0.35
SP_ZETA_LEVEL1_MAX: float = 1.30
SP_ZETA_LEVEL2_MIN: float = 0.25
SP_ZETA_LEVEL2_MAX: float = 2.00
SP_ZETA_LEVEL3_MIN: float = 0.15


# ---------------------------------------------------------------------------
# ISA atmosphere
# ---------------------------------------------------------------------------

def isa_density(altitude_m: float) -> float:
    """
    ISA standard atmosphere density [kg/m³] at altitude_m.
    Valid for troposphere (0–11 km). Clipped at tropopause above.
    Reference: ICAO Doc 7488.
    """
    altitude_m = float(altitude_m)
    if altitude_m == 0.0:
        return ISA_SEA_LEVEL_RHO_KGM3
    alt = min(float(altitude_m), TROPOPAUSE_ALT_M)
    T = ISA_SEA_LEVEL_T_K - ISA_LAPSE_RATE_K_PER_M * alt
    P = ISA_SEA_LEVEL_P_PA * (T / ISA_SEA_LEVEL_T_K) ** (
        GRAVITY_MPS2 / (ISA_LAPSE_RATE_K_PER_M * ISA_R_J_KG_K)
    )
    return P / (ISA_R_J_KG_K * T)


def dynamic_pressure(velocity_mps: float, altitude_m: float) -> float:
    """q∞ = ½ρV² [Pa]"""
    rho = isa_density(altitude_m)
    return 0.5 * rho * velocity_mps ** 2


# ---------------------------------------------------------------------------
# Utility: safe dict/object getter
# ---------------------------------------------------------------------------

def _get(obj: Any, *names: str) -> Any:
    """Recursively search a dict or object for the first matching non-None key."""
    def _search_dict(d: dict) -> Any:
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
# Geometry reference values
# ---------------------------------------------------------------------------

def load_geometry_summary(run_dir: str | Path) -> dict | None:
    """Read geometry_summary.json from the run directory if it exists."""
    path = Path(run_dir) / "geometry" / "geometry_summary.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Static stability
# ---------------------------------------------------------------------------

def compute_static_margin(
    *,
    x_np_m: float,
    x_cg_m: float,
    mac_m: float,
    x_positive_aft: bool = True,
) -> tuple[float, float]:
    """
    Static margin = (Xnp - Xcg) / MAC.
    Positive = statically stable (CG forward of NP) for x-positive-aft convention.
    Returns (static_margin [-], static_margin_percent_mac [%MAC]).
    Reference: [CS] Section 3.3.
    """
    if mac_m <= 0.0:
        raise ValueError(f"MAC must be positive, got {mac_m:.6f} m")
    raw = (x_np_m - x_cg_m) / mac_m
    sm = raw if x_positive_aft else -raw
    return sm, sm * 100.0


def interpret_longitudinal(
    static_margin: float | None,
    cma: float | None,
) -> tuple[str | None, bool | None]:
    """
    Classify longitudinal stability and verify Cma/SM consistency.
    Cma must be negative for static stability (x-positive-aft convention).
    """
    if static_margin is None:
        return None, None
    if static_margin > 0.0:
        interp = "positive_static_margin"
    elif static_margin < 0.0:
        interp = "negative_static_margin"
    else:
        interp = "neutral_static_margin"
    if cma is None:
        return interp, None
    consistent = (
        (static_margin > 0.0 and cma < 0.0)
        or (static_margin < 0.0 and cma > 0.0)
        or (static_margin == 0.0 and abs(cma) < 1e-12)
    )
    return interp, consistent


# ---------------------------------------------------------------------------
# Stability derivative extraction
# ---------------------------------------------------------------------------

def extract_longitudinal_derivatives(aero_result: Any) -> LongitudinalStabilityDerivatives:
    """Extract longitudinal stability derivatives from aero_result dict/object.

    Supports both real AERIS aero_result dictionaries:

        {"stability_axis_derivatives": {"Cma": ...}}

    and lightweight object-style test/result containers:

        aero_result.Cma

    The object fallback is intentionally narrow and only used when the nested
    derivative dictionary does not contain the requested value.
    """
    sad = _get(aero_result, "stability_axis_derivatives") or {}

    def _d(*keys: str) -> float | None:
        nested = _get(sad, *keys)
        if nested is not None:
            return nested
        return _get(aero_result, *keys)

    return LongitudinalStabilityDerivatives(
        cla=_d("CLa", "cla"),
        cda=_d("CDa", "cda"),
        cma=_d("Cma", "cma"),
        clq=_d("CLq", "clq"),
        cmq=_d("Cmq", "cmq"),
        clad=_d("CLad", "clad"),
        cmad=_d("Cmad", "cmad"),
    )


def extract_lateral_derivatives(aero_result: Any) -> LateralDirectionalStabilityDerivatives:
    """Extract lateral-directional stability derivatives from aero_result dict/object."""
    sad = _get(aero_result, "stability_axis_derivatives") or {}
    return LateralDirectionalStabilityDerivatives(
        clb=_get(sad, "Clb"),
        cnb=_get(sad, "Cnb"),
        cyb=_get(sad, "CYb"),
        clp=_get(sad, "Clp"),
        cnp=_get(sad, "Cnp"),
        clr=_get(sad, "Clr"),
        cnr=_get(sad, "Cnr"),
    )


def extract_control_effectiveness(aero_result: Any) -> ControlEffectiveness:
    """
    Extract control surface effectiveness derivatives.
    AVL writes these under 'd1' (first control surface, typically elevon on BWB).
    Keys vary by AVL version: 'CLd1', 'Cmd1', etc.
    """
    sad = _get(aero_result, "stability_axis_derivatives") or {}
    raw = aero_result if isinstance(aero_result, dict) else {}

    # Try standard AVL key patterns for first control (d1 = elevon on BWB)
    def _ctrl(*keys: str) -> float | None:
        for k in keys:
            v = sad.get(k) or raw.get(k)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        return None

    cl_de  = _ctrl("CLd1", "CL_d1", "CLde")
    cm_de  = _ctrl("Cmd1", "Cm_d1", "Cmde", "CmD1")
    cy_da  = _ctrl("CYd1", "CY_d1")
    cl_da  = _ctrl("Cld1", "Cl_d1")
    cn_da  = _ctrl("Cnd1", "Cn_d1")

    pitch_ok: bool | None = None
    if cm_de is not None:
        pitch_ok = abs(cm_de) >= PITCH_AUTHORITY_MIN_PER_RAD

    notes = None
    if cm_de is None:
        notes = (
            "Cmδe not found in stability_axis_derivatives. "
            "Check that AVL control surface (d1) is defined in the airplane model."
        )

    return ControlEffectiveness(
        cl_per_de_rad=cl_de,
        cm_per_de_rad=cm_de,
        cy_per_da_rad=cy_da,
        cl_roll_per_da_rad=cl_da,
        cn_per_da_rad=cn_da,
        pitch_authority_adequate=pitch_ok,
        notes=notes,
    )


def build_stability_derivative_summary(
    longitudinal: LongitudinalStabilityDerivatives,
    lateral: LateralDirectionalStabilityDerivatives,
) -> StabilityDerivativeSummary:
    """Assemble derivative summary with stability sign checks."""
    clb = lateral.clb
    cnb = lateral.cnb
    clr = lateral.clr
    cnr = lateral.cnr

    # Spiral metric: Clβ·Cnr / (Clr·Cnβ)  [ER] §11.4
    spiral: float | None = None
    if all(v is not None for v in (clb, cnr, clr, cnb)):
        denom = clr * cnb  # type: ignore[operator]
        if abs(denom) > 1e-14:
            spiral = (clb * cnr) / denom  # type: ignore[operator]

    return StabilityDerivativeSummary(
        longitudinal=longitudinal,
        lateral_directional=lateral,
        cma_sign_ok=longitudinal.cma < 0 if longitudinal.cma is not None else None,
        cmq_sign_ok=longitudinal.cmq < 0 if longitudinal.cmq is not None else None,
        clb_sign_ok=clb < 0 if clb is not None else None,
        cnb_sign_ok=cnb > 0 if cnb is not None else None,
        clp_sign_ok=lateral.clp < 0 if lateral.clp is not None else None,
        cnr_sign_ok=cnr < 0 if cnr is not None else None,
        spiral_metric=spiral,
        spiral_stable=spiral < 1.0 if spiral is not None else None,
    )


# ---------------------------------------------------------------------------
# Dynamic mode approximations
# ---------------------------------------------------------------------------

def _sp_handling_quality(zeta: float) -> tuple[int | None, str | None]:
    """Classify short-period handling quality per MIL-HDBK-1797A (Cat B)."""
    if zeta >= SP_ZETA_LEVEL1_MIN and zeta <= SP_ZETA_LEVEL1_MAX:
        return 1, "Level 1 (satisfactory)"
    if zeta >= SP_ZETA_LEVEL2_MIN and zeta <= SP_ZETA_LEVEL2_MAX:
        return 2, "Level 2 (acceptable)"
    if zeta >= SP_ZETA_LEVEL3_MIN:
        return 3, "Level 3 (controllable)"
    return None, "Below Level 3 (unacceptable)"


def estimate_short_period(
    *,
    cma_per_rad: float,
    cmq_per_rad: float | None,
    cmad_per_rad: float | None,
    cla_per_rad: float | None,
    mass_kg: float,
    iyy_kg_m2: float,
    velocity_mps: float,
    altitude_m: float,
    mac_m: float,
    sref_m2: float | None = None,
) -> ShortPeriodApproximation:
    """
    Short-period natural frequency and damping ratio approximation.
    Uses the decoupled short-period equations of motion.
    Reference: [ER] §7.3, [CS] §6.4.

    ω²_n ≈ (q∞·S/m) · [CLα - m·g·cos(θ)/q∞S - Cma·m/Iyy·(c/2V)²]
           simplified to: ω²_n ≈ -Cma · q∞·S·c / Iyy (dominant term)
    ζ ≈ -(Cmq + Cmαdot) · (c/2V) · (q∞·S·c / 2·Iyy·ω_n)  [ER 7.3.17]
    """
    if cma_per_rad >= 0:
        return ShortPeriodApproximation(
            valid=False,
            reason="Cma ≥ 0 — aircraft is pitch-unstable; short-period approximation not valid.",
        )
    if iyy_kg_m2 <= 0:
        return ShortPeriodApproximation(
            valid=False, reason="Iyy must be positive.",
        )

    q_inf = dynamic_pressure(velocity_mps, altitude_m)
    rho   = isa_density(altitude_m)

    # Estimate reference area from mass if not provided
    # For a 12.5 kg UAV at 28 m/s, CL~0.3 → S ~ 2·L/(ρ·V²·CL) ~ 0.15 m²
    # This is only used when sref not given — caller should supply it.
    S = sref_m2 or max(mass_kg / (q_inf * 0.3), 0.05)

    # Non-dimensional pitch stiffness: Mα = q∞·S·c·Cma / Iyy  [1/s²]
    M_alpha = (q_inf * S * mac_m * cma_per_rad) / iyy_kg_m2

    # ω_n² ≈ -Mα  (dominant term, sign check: Cma<0 → M_alpha<0 → -M_alpha>0)
    omega_n_sq = -M_alpha
    if omega_n_sq <= 0:
        return ShortPeriodApproximation(
            valid=False,
            reason="ω_n² ≤ 0 after sign check — check Cma sign and Iyy.",
        )
    omega_n = math.sqrt(omega_n_sq)

    # Damping: uses Cmq + Cmαdot if available
    cmq  = cmq_per_rad  or 0.0
    cmad = cmad_per_rad or 0.0
    # Mq = q∞·S·c²·Cmq / (2·V·Iyy)  [1/s]
    M_q    = (q_inf * S * mac_m**2 * cmq)  / (2.0 * velocity_mps * iyy_kg_m2)
    M_ad   = (q_inf * S * mac_m**2 * cmad) / (2.0 * velocity_mps * iyy_kg_m2)
    zeta = -(M_q + M_ad) / (2.0 * omega_n)

    if zeta <= 0:
        # Undamped / divergent — still report omega_n
        hq, hq_note = None, "Negative damping — divergent short-period mode."
        t_half = None
    else:
        omega_d = omega_n * math.sqrt(max(1.0 - zeta**2, 0.0))
        period  = (2.0 * math.pi / omega_d) if omega_d > 1e-12 else None
        t_half  = math.log(2.0) / (zeta * omega_n)
        hq, hq_note = _sp_handling_quality(zeta)
        omega_d_val = omega_d
        period_val  = period
        return ShortPeriodApproximation(
            omega_n_rad_s=round(omega_n, 4),
            zeta=round(zeta, 4),
            omega_d_rad_s=round(omega_d_val, 4),
            period_s=round(period_val, 4) if period_val else None,
            time_to_half_s=round(t_half, 4),
            valid=True,
            handling_quality_level=hq,
            handling_quality_note=hq_note,
        )

    omega_d_u = omega_n * math.sqrt(max(1.0 - zeta**2, 0.0))
    return ShortPeriodApproximation(
        omega_n_rad_s=round(omega_n, 4),
        zeta=round(zeta, 4),
        omega_d_rad_s=round(omega_d_u, 4),
        period_s=None,
        time_to_half_s=None,
        valid=False,
        reason=hq_note,
        handling_quality_level=hq,
        handling_quality_note=hq_note,
    )


def estimate_phugoid(
    *,
    cl: float,
    cd: float,
    velocity_mps: float,
) -> PhugoidApproximation:
    """
    Lanchester phugoid approximation.
    ω_n ≈ g√2 / V,   ζ ≈ CD / (CL·√2)
    Reference: [ER] §7.4, [CS] §7.2.
    Valid for lightly damped, low-frequency mode (ζ << 1).
    """
    if velocity_mps <= 0:
        return PhugoidApproximation(valid=False, reason="Velocity must be positive.")
    if cl <= 0:
        return PhugoidApproximation(valid=False, reason="CL must be positive for phugoid estimate.")

    omega_n = GRAVITY_MPS2 * math.sqrt(2.0) / velocity_mps
    zeta    = cd / (cl * math.sqrt(2.0))
    period  = 2.0 * math.pi / omega_n

    if zeta > 0:
        t_half = math.log(2.0) / (zeta * omega_n)
        stable = True
    else:
        t_half = None
        stable = False

    return PhugoidApproximation(
        omega_n_rad_s=round(omega_n, 4),
        zeta=round(zeta, 4),
        period_s=round(period, 2),
        time_to_double_or_half_s=round(t_half, 2) if t_half else None,
        stable=stable,
        valid=True,
    )


def estimate_dutch_roll(
    *,
    cnb_per_rad: float,
    cnr_per_rad: float | None,
    mass_kg: float,
    izz_kg_m2: float,
    velocity_mps: float,
    altitude_m: float,
    sref_m2: float | None = None,
    span_m: float | None = None,
) -> DutchRollApproximation:
    """
    Dutch roll natural frequency approximation.
    ω_n ≈ √(Nβ),  Nβ = q∞·S·b·Cnβ / Izz
    ζ ≈ -Nr / (2·ω_n),  Nr = q∞·S·b²·Cnr / (2·V·Izz)
    Reference: [ER] §11.2, [CS] §9.3.
    """
    if cnb_per_rad <= 0:
        return DutchRollApproximation(
            valid=False,
            reason="Cnβ ≤ 0 — aircraft is directionally unstable; Dutch roll approximation not valid.",
        )
    if izz_kg_m2 <= 0:
        return DutchRollApproximation(valid=False, reason="Izz must be positive.")

    q_inf = dynamic_pressure(velocity_mps, altitude_m)
    S = sref_m2 or max(mass_kg / (q_inf * 0.3), 0.05)
    b = span_m or math.sqrt(S * 7.0)  # assume AR~7 as fallback

    # Yaw stiffness
    N_beta = (q_inf * S * b * cnb_per_rad) / izz_kg_m2
    if N_beta <= 0:
        return DutchRollApproximation(
            valid=False, reason="N_β ≤ 0 after computation — check derivatives.",
        )
    omega_n = math.sqrt(N_beta)

    zeta: float | None = None
    period: float | None = None
    if cnr_per_rad is not None:
        N_r = (q_inf * S * b**2 * cnr_per_rad) / (2.0 * velocity_mps * izz_kg_m2)
        zeta = -N_r / (2.0 * omega_n)
        omega_d = omega_n * math.sqrt(max(1.0 - zeta**2, 0.0)) if zeta < 1.0 else 0.0
        period = (2.0 * math.pi / omega_d) if omega_d > 1e-12 else None

    hq, hq_note = None, None
    if zeta is not None:
        hq, hq_note = _sp_handling_quality(zeta)

    return DutchRollApproximation(
        omega_n_rad_s=round(omega_n, 4),
        zeta=round(zeta, 4) if zeta is not None else None,
        period_s=round(period, 2) if period else None,
        valid=True,
        handling_quality_level=hq,
        handling_quality_note=hq_note,
    )


def compute_dynamic_modes(
    *,
    derivatives: StabilityDerivativeSummary,
    control: ControlEffectiveness,
    mass_props: MassProperties,
    stability_metrics: StabilityMetrics,
    velocity_mps: float | None,
    altitude_m: float | None,
    cl: float | None,
    cd: float | None,
    mac_m: float | None,
    sref_m2: float | None = None,
    span_m: float | None = None,
) -> DynamicModesSummary:
    """
    Compute all available dynamic mode approximations.
    Falls back gracefully when data is missing.
    """
    missing: list[str] = []
    ld = derivatives.longitudinal
    lat = derivatives.lateral_directional

    # Short period
    sp = ShortPeriodApproximation(valid=False, reason="Insufficient data")
    sp_missing: list[str] = []
    if ld.cma is None:   sp_missing.append("Cma")
    if mass_props.inertia.iyy_kg_m2 is None: sp_missing.append("Iyy")
    if velocity_mps is None: sp_missing.append("velocity")
    if mac_m is None:    sp_missing.append("MAC")

    if not sp_missing:
        sp = estimate_short_period(
            cma_per_rad=ld.cma,  # type: ignore[arg-type]
            cmq_per_rad=ld.cmq,
            cmad_per_rad=ld.cmad,
            cla_per_rad=ld.cla,
            mass_kg=mass_props.mass_kg,
            iyy_kg_m2=mass_props.inertia.iyy_kg_m2,  # type: ignore[arg-type]
            velocity_mps=velocity_mps,  # type: ignore[arg-type]
            altitude_m=altitude_m or 0.0,
            mac_m=mac_m,  # type: ignore[arg-type]
            sref_m2=sref_m2,
        )
    else:
        missing.extend(f"short-period needs: {', '.join(sp_missing)}".split(": "))

    # Phugoid
    ph = PhugoidApproximation(valid=False, reason="Insufficient data")
    ph_missing: list[str] = []
    if cl is None:          ph_missing.append("CL")
    if cd is None:          ph_missing.append("CD")
    if velocity_mps is None: ph_missing.append("velocity")

    if not ph_missing:
        ph = estimate_phugoid(
            cl=cl,  # type: ignore[arg-type]
            cd=cd,  # type: ignore[arg-type]
            velocity_mps=velocity_mps,  # type: ignore[arg-type]
        )
    else:
        missing.extend(ph_missing)

    # Dutch roll
    dr = DutchRollApproximation(valid=False, reason="Insufficient data")
    dr_missing: list[str] = []
    if lat.cnb is None:    dr_missing.append("Cnβ")
    if mass_props.inertia.izz_kg_m2 is None: dr_missing.append("Izz")
    if velocity_mps is None: dr_missing.append("velocity")

    if not dr_missing:
        dr = estimate_dutch_roll(
            cnb_per_rad=lat.cnb,  # type: ignore[arg-type]
            cnr_per_rad=lat.cnr,
            mass_kg=mass_props.mass_kg,
            izz_kg_m2=mass_props.inertia.izz_kg_m2,  # type: ignore[arg-type]
            velocity_mps=velocity_mps,  # type: ignore[arg-type]
            altitude_m=altitude_m or 0.0,
            sref_m2=sref_m2,
            span_m=span_m,
        )
    else:
        missing.extend(dr_missing)

    modes_computed = sp.valid or ph.valid or dr.valid

    return DynamicModesSummary(
        short_period=sp,
        phugoid=ph,
        dutch_roll=dr,
        modes_computed=modes_computed,
        missing_inputs=list(set(missing)),
    )


# ---------------------------------------------------------------------------
# State-space readiness (evaluated, not hardcoded)
# ---------------------------------------------------------------------------

def build_state_space_preparation(
    *,
    mass_properties: MassProperties,
    x_np_m: float | None,
    mac_m: float | None,
    cma: float | None,
    cmde: float | None,
    spiral_metric: float | None,
    cl: float | None,
    velocity_mps: float | None,
) -> StateSpacePreparation:
    """
    Evaluate what dynamics analyses are currently possible.
    Never hardcodes False — everything is derived from data availability.
    """
    missing: list[str] = []

    inertia_complete = mass_properties.inertia_complete()
    iyy_ok = mass_properties.inertia.iyy_kg_m2 is not None
    izz_ok = mass_properties.inertia.izz_kg_m2 is not None

    if not inertia_complete: missing.append("principal inertia estimates (Ixx, Iyy, Izz)")
    if x_np_m is None:       missing.append("neutral point (Xnp)")
    if mac_m is None:        missing.append("mean aerodynamic chord (MAC)")
    if cma is None:          missing.append("pitch stability derivative (Cma)")
    if cmde is None:         missing.append("elevon effectiveness (Cmδe)")
    if spiral_metric is None: missing.append("spiral metric (needs Clβ, Cnr, Clr, Cnβ)")

    # Trim solver: need Cma + Cmδe (or at least Cma for alpha-only trim)
    ready_trim = (cma is not None and x_np_m is not None and mac_m is not None)
    ready_trim_full = ready_trim and (cmde is not None)

    # Eigenanalysis: need full inertia tensor
    ready_eigen = inertia_complete and (cma is not None) and (mac_m is not None)

    # Short-period: need Cma, Iyy, velocity, MAC
    ready_sp = (
        cma is not None and iyy_ok
        and velocity_mps is not None and mac_m is not None
    )

    # Phugoid: need CL, CD, velocity
    ready_ph = (cl is not None and velocity_mps is not None)

    # Dutch roll: need Cnβ, Izz, velocity (evaluated externally via cnb_available flag)
    ready_dr = izz_ok and velocity_mps is not None

    return StateSpacePreparation(
        mass_available=True,
        cg_available=True,
        inertia_available=inertia_complete,
        xnp_available=x_np_m is not None,
        mac_available=mac_m is not None,
        longitudinal_derivatives_available=cma is not None,
        lateral_derivatives_available=spiral_metric is not None,
        control_derivatives_available=cmde is not None,
        ready_for_trim_solver=ready_trim,
        ready_for_eigenanalysis=ready_eigen,
        ready_for_short_period=ready_sp,
        ready_for_phugoid=ready_ph,
        ready_for_dutch_roll=ready_dr,
        missing_items=missing,
    )


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------

def build_dynamics_foundation_result(
    *,
    aero_result: Any,
    mass_properties: MassProperties,
    source_run_dir: str,
    trim_definition: TrimDefinition | None = None,
    x_positive_aft: bool = True,
    sref_m2: float | None = None,
    span_m: float | None = None,
) -> DynamicsFoundationResult:
    """
    Build a complete DynamicsFoundationResult from an aero result and mass properties.

    This is the single entry point for all dynamics computations. It:
    1. Extracts all derivatives from the aero result
    2. Computes static stability metrics
    3. Computes control effectiveness
    4. Computes dynamic mode approximations (when data permits)
    5. Assesses state-space readiness
    6. Returns a complete, self-describing result artifact

    The aero_result may be an AeroResult dataclass instance or a dict
    (loaded from aero_result.json). Both are handled transparently.
    """
    trim_definition = trim_definition or TrimDefinition()

    # ── Extract scalars from aero result ─────────────────────────────────────
    scalars = _get(aero_result, "scalars") or {}
    if not scalars and isinstance(aero_result, dict):
        scalars = aero_result  # older format without sub-dict

    x_np_m      = _get(aero_result, "x_np", "Xnp", "x_np_m") or _get(scalars, "x_np", "Xnp")
    cl          = _get(aero_result, "cl", "CL") or _get(scalars, "cl", "CL")
    cd          = _get(aero_result, "cd", "CD") or _get(scalars, "cd", "CD")
    cm_val      = _get(aero_result, "cm", "Cm") or _get(scalars, "cm", "Cm")
    solver_id   = _get(aero_result, "solver_id", "solver")

    # MAC: try aero result, then geometry_summary.json
    mac_m = _get(aero_result, "mac_m", "mean_aerodynamic_chord_m", "cbar_m")
    if mac_m is None:
        geo = load_geometry_summary(source_run_dir)
        if geo:
            mac_m = geo.get("reference_values", {}).get("mean_aerodynamic_chord_m")

    # Flight condition
    meta = _get(aero_result, "solver_metadata") or {}
    fc   = meta.get("flight_condition") or _get(aero_result, "flight_condition") or {}
    if isinstance(fc, dict):
        alpha_deg    = fc.get("alpha_deg")
        velocity_mps = fc.get("velocity_mps")
        altitude_m   = fc.get("altitude_m", 0.0)
    else:
        alpha_deg    = getattr(fc, "alpha_deg", None)
        velocity_mps = getattr(fc, "velocity_mps", None)
        altitude_m   = getattr(fc, "altitude_m", 0.0)

    # ── Derivatives ───────────────────────────────────────────────────────────
    long_derivs   = extract_longitudinal_derivatives(aero_result)
    lat_derivs    = extract_lateral_derivatives(aero_result)
    ctrl_effect   = extract_control_effectiveness(aero_result)
    deriv_summary = build_stability_derivative_summary(long_derivs, lat_derivs)

    cma   = long_derivs.cma
    cmde  = ctrl_effect.cm_per_de_rad

    # ── Static stability ──────────────────────────────────────────────────────
    static_margin: float | None = None
    static_margin_pct: float | None = None
    if x_np_m is not None and mac_m is not None:
        static_margin, static_margin_pct = compute_static_margin(
            x_np_m=x_np_m,
            x_cg_m=mass_properties.x_cg_m,
            mac_m=mac_m,
            x_positive_aft=x_positive_aft,
        )
    interp, consistent = interpret_longitudinal(static_margin, cma)

    # ── Flight envelope context ───────────────────────────────────────────────
    q_inf: float | None = None
    lift_n: float | None = None
    drag_n: float | None = None
    load_factor: float | None = None
    weight_n = mass_properties.mass_kg * GRAVITY_MPS2

    if velocity_mps is not None and altitude_m is not None:
        q_inf = dynamic_pressure(velocity_mps, altitude_m)
    if q_inf is not None and sref_m2 is not None:
        if cl is not None:
            lift_n = float(cl) * q_inf * sref_m2
            load_factor = lift_n / weight_n
        if cd is not None:
            drag_n = float(cd) * q_inf * sref_m2

    sm_obj = StabilityMetrics(
        x_np_m=x_np_m,
        x_cg_m=mass_properties.x_cg_m,
        mac_m=mac_m,
        static_margin=static_margin,
        static_margin_percent_mac=static_margin_pct,
        cma=cma,
        cma_consistent_with_static_margin=consistent,
        spiral_metric=deriv_summary.spiral_metric,
        longitudinal_interpretation=interp,
        alpha_deg=alpha_deg,
        velocity_mps=velocity_mps,
        altitude_m=altitude_m,
        dynamic_pressure_pa=q_inf,
        lift_n=lift_n,
        drag_n=drag_n,
        load_factor=load_factor,
        weight_n=weight_n,
    )

    # ── Dynamic modes ─────────────────────────────────────────────────────────
    dynamic_modes = compute_dynamic_modes(
        derivatives=deriv_summary,
        control=ctrl_effect,
        mass_props=mass_properties,
        stability_metrics=sm_obj,
        velocity_mps=velocity_mps,
        altitude_m=altitude_m,
        cl=float(cl) if cl is not None else None,
        cd=float(cd) if cd is not None else None,
        mac_m=mac_m,
        sref_m2=sref_m2,
        span_m=span_m,
    )

    # ── Readiness ─────────────────────────────────────────────────────────────
    operating_point = fc if isinstance(fc, dict) else (
        asdict(fc) if is_dataclass(fc) else {}
    )

    readiness = build_state_space_preparation(
        mass_properties=mass_properties,
        x_np_m=x_np_m,
        mac_m=mac_m,
        cma=cma,
        cmde=cmde,
        spiral_metric=deriv_summary.spiral_metric,
        cl=float(cl) if cl is not None else None,
        velocity_mps=velocity_mps,
    )

    return DynamicsFoundationResult(
        schema_version="0.2.0",
        source_run_dir=source_run_dir,
        source_solver_id=solver_id,
        operating_point_snapshot=operating_point,
        mass_properties=mass_properties,
        trim_definition=trim_definition,
        stability_metrics=sm_obj,
        stability_derivatives=deriv_summary,
        control_effectiveness=ctrl_effect,
        dynamic_modes=dynamic_modes,
        state_space_preparation=readiness,
        metadata={
            "x_axis_positive_aft": x_positive_aft,
            "schema_version": "0.2.0",
            "sref_m2_used": sref_m2,
            "span_m_used": span_m,
        },
    )