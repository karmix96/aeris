"""
AERIS Dynamics — DATCOM Semi-Empirical Derivative Estimators
=============================================================
Provides semi-empirical (USAF DATCOM-inspired) estimates for stability
derivatives that AVL does not directly output, or where AVL output is
unreliable (e.g., Cmq, Clp, Cnr for tailless BWB configurations).

These are used as:
  1. Fallback when AVL derivative is missing (None in aero_result).
  2. Cross-check sanity estimate (DATCOM vs. AVL comparison table).
  3. Fill missing derivatives for eigenvalue analysis (clearly flagged).

All estimators clearly document their assumptions, applicable range,
and uncertainty level. No estimator returns a value without noting
its source and expected accuracy.

References:
  [DATCOM] USAF Stability and Control DATCOM, 1978 (AFWAL-TR-83-3048).
  [ESDU]   ESDU 85010, Longitudinal stability derivatives.
  [ER]     Etkin & Reid, "Dynamics of Flight", 3rd ed.
  [CS]     Cook, "Flight Dynamics Principles", 3rd ed.
  [MK]     McLean, "Automatic Flight Control Systems".
  [LB]     Lan & Roskam, "Airplane Aerodynamics and Performance".

Accuracy ratings (engineering judgment for BWB/tailless):
  ★★★★★  Excellent  — < 10% error typical
  ★★★★   Good       — 10-25% error typical
  ★★★    Moderate   — 25-50% error typical (use with caution)
  ★★     Poor       — order-of-magnitude only
  ★      Reference  — directional guidance only
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class DATCOMEstimate:
    """Result of a DATCOM semi-empirical estimate."""
    derivative_name: str         # e.g. "Cmq"
    value: float                 # estimated value [per rad]
    method: str                  # method name
    accuracy: str                # accuracy rating (★ to ★★★★★)
    formula: str                 # human-readable formula used
    assumptions: list[str]       # key assumptions made
    note: str | None = None


# ---------------------------------------------------------------------------
# Geometry helper
# ---------------------------------------------------------------------------

def _aspect_ratio(span_m: float, sref_m2: float) -> float:
    """Wing aspect ratio AR = b² / S."""
    if sref_m2 <= 0:
        raise ValueError("sref_m2 must be positive.")
    return span_m**2 / sref_m2


# ---------------------------------------------------------------------------
# Longitudinal derivatives
# ---------------------------------------------------------------------------

def estimate_cmq(
    *,
    cla_per_rad: float,
    mac_m: float,
    sref_m2: float,
    span_m: float,
    x_ac_m: float,
    x_cg_m: float,
    x_positive_aft: bool = True,
) -> DATCOMEstimate:
    """
    Pitch rate damping derivative Cmq [/rad].

    DATCOM method for tailless flying wing / BWB:
    Cmq ≈ -2·CLα·(x_ac - x_cg)²/c²
          contribution from wing lift shift due to pitch rate.
    For tailless (no tail), the dominant contribution is the wing alone.

    More precisely (from strip theory):
    Cmq_wing ≈ -CLα·AR·(1 + 3·λ)/(12·(1 + λ))   [for unswept wing]
    For swept tailless: multiply by (c_bar/c_r)² correction.

    Sign convention: x positive aft. Cmq should be negative (damping).

    Reference: [DATCOM] Section 7.3.1.2, [ER] §4.7.
    Accuracy: ★★★ (25-50% error for swept tailless BWB)
    """
    # Lever arm: Mq arises from wing lift shifting ahead/behind pitch centre
    # For tailless wing, dominant term is ∫ y²·cl_y dy type integral
    # Simplified Etkin: Cmq_wing ≈ -CLα·(x_ac-x_cg)²/c²   [/rad, body-axis]
    AR = _aspect_ratio(span_m, sref_m2)
    lam = 1.0  # assume taper ratio λ ~ 0.5 for simple estimate; affect coefficient ~5%
    
    # Wing-alone Cmq (strip theory, from [LB] Section 4.6)
    # For BWB, the "body" contributes ~ 10-30% additional damping
    # Using simplified sweep-corrected Etkin formula:
    lever_c = (x_ac_m - x_cg_m) / mac_m
    cmq_lever = -2.0 * cla_per_rad * lever_c**2

    # AR correction (DATCOM Eq 7.3.1.2-a)
    # For high-AR wings Cmq is larger; for low-AR BWB it's reduced
    ar_correction = max(0.5, min(1.5, AR / 6.0))  # clamp to [0.5, 1.5]
    cmq_est = cmq_lever * ar_correction

    # Ensure negative (physically must be damping for any reasonable config)
    if cmq_est > 0:
        cmq_est = -abs(cmq_lever) * 0.5

    return DATCOMEstimate(
        derivative_name="Cmq",
        value=round(cmq_est, 4),
        method="DATCOM_lever_arm_strip_theory",
        accuracy="★★★",
        formula="Cmq ≈ -2·CLα·(Xac-Xcg)²/c² × AR_correction",
        assumptions=[
            "Tailless configuration (no stabiliser contribution)",
            "Subsonic, low Mach (M < 0.3)",
            "Linear lift distribution approximation",
            "AR correction factor is approximate for BWB planforms",
        ],
        note=f"Lever arm = {lever_c:.3f}c, AR correction = {ar_correction:.2f}. "
             "Use AVL Cmq if available; this estimate is a fallback.",
    )


def estimate_clq(
    *,
    cla_per_rad: float,
    mac_m: float,
    sref_m2: float,
    span_m: float,
) -> DATCOMEstimate:
    """
    Lift due to pitch rate CLq [/rad].
    DATCOM: CLq ≈ 2·CLα·(c_bar/2)/(c_bar) = CLα  (approximate for tailless)
    More precisely: CLq_wing ≈ 0.5·CLα·AR/(AR+2) from lifting line theory.
    Accuracy: ★★★★
    """
    AR = _aspect_ratio(span_m, sref_m2)
    clq_est = 0.5 * cla_per_rad * AR / (AR + 2.0)

    return DATCOMEstimate(
        derivative_name="CLq",
        value=round(clq_est, 4),
        method="lifting_line_CLq",
        accuracy="★★★★",
        formula="CLq ≈ 0.5·CLα·AR/(AR+2)",
        assumptions=[
            "Unswept or moderately swept wing",
            "Subsonic, linear aerodynamics",
        ],
        note="For swept BWB, reduce by factor cos²(Λ_LE/2).",
    )


def estimate_cmad(
    *,
    cla_per_rad: float,
    mac_m: float,
    x_ac_m: float,
    x_cg_m: float,
) -> DATCOMEstimate:
    """
    Alpha-dot pitch damping Cmαdot [/rad] — alpha-rate contribution.
    For tailless (no tail): Cmαdot ≈ -2·CLα·(x_ac-x_cg)/c  (wing downwash lag)
    This is typically small for tailless configs (no significant downwash source).
    Accuracy: ★★ (BWB has negligible downwash lag)
    """
    lever_c = (x_ac_m - x_cg_m) / mac_m
    cmad_est = -0.5 * cla_per_rad * lever_c  # reduced from conventional tail estimate

    return DATCOMEstimate(
        derivative_name="Cmad",
        value=round(cmad_est, 4),
        method="DATCOM_tailless_downwash_lag",
        accuracy="★★",
        formula="Cmαdot ≈ -0.5·CLα·(Xac-Xcg)/c [tailless reduction]",
        assumptions=[
            "Tailless — no stabiliser downwash lag contribution",
            "BWB body provides minor alpha-rate contribution only",
        ],
        note="Cmαdot is small for BWB. Setting to zero is conservative.",
    )


# ---------------------------------------------------------------------------
# Lateral-directional derivatives
# ---------------------------------------------------------------------------

def estimate_clp(
    *,
    cla_per_rad: float,
    span_m: float,
    sref_m2: float,
) -> DATCOMEstimate:
    """
    Roll damping derivative Clp [/rad].
    DATCOM wing-alone, trapezoidal planform:
    Clp ≈ -(CLα/8)·(1 + 3·λ)/(1 + λ)  [per rad]
    For λ = 0 (delta tip): Clp ≈ -CLα/8
    For λ = 1 (rectangular): Clp ≈ -CLα/2
    For typical BWB λ ~ 0.2-0.5: Clp ≈ -CLα·(0.2 to 0.35)

    Reference: [DATCOM] Section 7.1.3.2, [CS] Section 5.4.
    Sign: must be negative (roll damping).
    Accuracy: ★★★★ (good for subsonic, moderate sweep)
    """
    AR = _aspect_ratio(span_m, sref_m2)
    lam = 0.3  # typical BWB tip chord ratio estimate
    clp_est = -(cla_per_rad / 8.0) * (1.0 + 3.0 * lam) / (1.0 + lam)

    return DATCOMEstimate(
        derivative_name="Clp",
        value=round(clp_est, 4),
        method="DATCOM_wing_alone_taper",
        accuracy="★★★★",
        formula="Clp ≈ -(CLα/8)·(1+3λ)/(1+λ), λ = 0.3 (BWB estimate)",
        assumptions=[
            "Subsonic, M < 0.3",
            "Taper ratio λ ≈ 0.3 (typical BWB; update with actual geometry)",
            "Wing-alone (body contribution neglected — ~10% underestimate)",
        ],
        note="Update λ from geometry_summary.json for better accuracy.",
    )


def estimate_cnr(
    *,
    cd0: float,
    cla_per_rad: float,
    cl0: float,
    span_m: float,
    sref_m2: float,
) -> DATCOMEstimate:
    """
    Yaw damping derivative Cnr [/rad].
    DATCOM simplified (wing-alone, no tail):
    Cnr ≈ -(CL²·AR/(π·AR²·e) + CD0·0.25·AR/(AR+4))·(1/AR)
    Simplified for tailless: Cnr ≈ -(CD0·b²/(2·S) + CL²/(π·e·AR))

    Alternative Etkin simplified: Cnr ≈ -(CD0 + (2/π)·(CL²/AR))·k
    where k ≈ 0.5 for tailless.

    Reference: [ER] §5.3, [DATCOM] 7.2.3.2.
    Sign: must be negative (yaw damping).
    Accuracy: ★★★ (tailless BWB has weak Cnr — within factor 2)
    """
    AR = _aspect_ratio(span_m, sref_m2)
    e = 0.85  # Oswald efficiency estimate for BWB
    # Induced drag contribution to Cnr
    cnr_induced = -(cl0**2) / (math.pi * e * AR**2)
    # Profile drag contribution
    cnr_profile = -cd0 * AR / (AR + 4.0) * 0.5

    cnr_est = (cnr_induced + cnr_profile)
    if cnr_est > -0.01:
        cnr_est = -0.05  # floor for tailless BWB — cannot be near zero

    return DATCOMEstimate(
        derivative_name="Cnr",
        value=round(cnr_est, 4),
        method="DATCOM_wing_yaw_damping",
        accuracy="★★★",
        formula="Cnr ≈ -(CL²/(π·e·AR²) + CD0·AR/(AR+4)·0.5)",
        assumptions=[
            "Tailless — no vertical tail or rudder contribution",
            "Oswald e = 0.85 (typical BWB estimate)",
            "Subsonic, linear aerodynamics",
            "BWB typically has weak Cnr — this is an underestimate",
        ],
        note="Tailless BWB Cnr is typically weak (~0.05-0.15). "
             "AVL value from sideslip sweep is preferred.",
    )


def estimate_cnb(
    *,
    cla_per_rad: float,
    span_m: float,
    sref_m2: float,
    sweep_le_deg: float = 35.0,
) -> DATCOMEstimate:
    """
    Weathercock stability derivative Cnβ [/rad] — directional stability.
    For tailless/no-rudder BWB, Cnβ is weak and primarily from swept-wing geometry.
    DATCOM swept-wing estimate:
    Cnβ_wing ≈ (CLα/6·π) · (AR·tan²Λ_LE)/(AR + 4·cos(Λ_LE))
               - CL²·(AR·tan(Λ_LE)/4 + 1/(π·AR))·(small positive term)

    Simplified: Cnβ_wing ≈ CLα/(π·AR) · sin(Λ_LE) · (positive)

    For BWB without vertical surfaces: Cnβ is the critical concern.
    Typical tailless BWB Cnβ ≈ 0.02 – 0.08 /rad (very low).
    Reference: [DATCOM] 7.2.1.2, [ER] §5.3.
    Accuracy: ★★ (directional stability of tailless is geometry-dependent)
    """
    AR = _aspect_ratio(span_m, sref_m2)
    sweep_le_rad = math.radians(sweep_le_deg)

    # Wing sweep contribution to Cnβ (positive for aft-swept)
    cos_lam = math.cos(sweep_le_rad)
    tan_lam = math.tan(sweep_le_rad)
    cnb_est = (cla_per_rad / (6.0 * math.pi)) * (AR * tan_lam**2) / (AR + 4.0 * cos_lam)

    # Ensure small positive (directionally stable)
    if cnb_est < 0.005:
        cnb_est = 0.005  # absolute floor for any swept wing

    return DATCOMEstimate(
        derivative_name="Cnb",
        value=round(cnb_est, 4),
        method="DATCOM_swept_wing_Cnb",
        accuracy="★★",
        formula="Cnβ ≈ (CLα/6π)·(AR·tan²Λ)/(AR+4·cosΛ), Λ_LE = " + f"{sweep_le_deg:.0f}°",
        assumptions=[
            f"LE sweep = {sweep_le_deg:.0f}° (update with actual geometry)",
            "Tailless — no vertical tail/winglet contribution",
            "Low CL (cruise condition)",
            "BWB Cnβ is typically weak — this may underestimate",
        ],
        note="CRITICAL for BWB: Cnβ is the weakest derivative in tailless designs. "
             "Dutch roll stability depends strongly on it. Verify with AVL.",
    )


def estimate_clb_dihedral(
    *,
    dihedral_deg: float,
    cla_per_rad: float,
    span_m: float,
    sref_m2: float,
) -> DATCOMEstimate:
    """
    Dihedral effect Clβ [/rad] from geometric dihedral angle.
    DATCOM: Clβ_Γ ≈ -(π/180)·Γ·CLα/6  [Γ in degrees for clarity]
    For swept wing add sweep contribution:
    Clβ_Λ ≈ -CLα·tan(Λ_LE)/(4·π·AR)

    Reference: [DATCOM] 7.1.1.2, [CS] Section 5.3.
    Sign: must be negative (stable dihedral effect).
    Accuracy: ★★★★ for geometric dihedral contribution.
    """
    dihedral_rad = math.radians(dihedral_deg)
    AR = _aspect_ratio(span_m, sref_m2)

    # Geometric dihedral contribution (dominant for low sweep)
    clb_dihedral = -(math.pi / 180.0) * dihedral_deg * cla_per_rad / 6.0

    return DATCOMEstimate(
        derivative_name="Clb",
        value=round(clb_dihedral, 5),
        method="DATCOM_geometric_dihedral",
        accuracy="★★★★",
        formula=f"Clβ ≈ -(π/180)·Γ·CLα/6, Γ = {dihedral_deg:.1f}°",
        assumptions=[
            f"Geometric dihedral Γ = {dihedral_deg:.1f}°",
            "Low speed, incompressible",
            "Sweep contribution not included (see combined estimate)",
        ],
        note="For BWB with winglets or out-of-plane surfaces, "
             "this underestimates Clβ. AVL value preferred.",
    )


# ---------------------------------------------------------------------------
# Combined fallback fill
# ---------------------------------------------------------------------------

def fill_missing_derivatives(
    derivs: dict[str, float | None],
    *,
    cla_per_rad: float,
    cl0: float = 0.3,
    cd0: float = 0.03,
    mac_m: float,
    span_m: float,
    sref_m2: float,
    x_ac_m: float,
    x_cg_m: float,
    sweep_le_deg: float = 35.0,
    dihedral_deg: float = 5.0,
) -> tuple[dict[str, float], dict[str, DATCOMEstimate]]:
    """
    Fill None-valued derivatives with DATCOM estimates.
    Returns (filled_derivs, datcom_estimates_used).
    Filled derivs dict only contains values that were estimated.
    """
    filled: dict[str, float] = {}
    estimates: dict[str, DATCOMEstimate] = {}

    def _fill(key: str, estimator_fn, **kwargs):
        if derivs.get(key) is None:
            est = estimator_fn(**kwargs)
            filled[key] = est.value
            estimates[key] = est

    _fill("Cmq", estimate_cmq,
          cla_per_rad=cla_per_rad, mac_m=mac_m, sref_m2=sref_m2,
          span_m=span_m, x_ac_m=x_ac_m, x_cg_m=x_cg_m)

    _fill("CLq", estimate_clq,
          cla_per_rad=cla_per_rad, mac_m=mac_m, sref_m2=sref_m2, span_m=span_m)

    _fill("Clp", estimate_clp,
          cla_per_rad=cla_per_rad, span_m=span_m, sref_m2=sref_m2)

    _fill("Cnr", estimate_cnr,
          cd0=cd0, cla_per_rad=cla_per_rad, cl0=cl0, span_m=span_m, sref_m2=sref_m2)

    if derivs.get("Cnb") is None:
        est = estimate_cnb(cla_per_rad=cla_per_rad, span_m=span_m,
                           sref_m2=sref_m2, sweep_le_deg=sweep_le_deg)
        filled["Cnb"] = est.value
        estimates["Cnb"] = est

    return filled, estimates


# ---------------------------------------------------------------------------
# Inertia estimation from geometry
# ---------------------------------------------------------------------------

@dataclass
class InertiaEstimate:
    """
    Semi-empirical inertia tensor estimate from planform geometry and mass.
    All values in kg·m².
    """
    ixx_kg_m2: float | None          # roll inertia
    iyy_kg_m2: float | None          # pitch inertia
    izz_kg_m2: float | None          # yaw inertia
    ixz_kg_m2: float                 # product of inertia (usually small for symmetric)

    # Radius of gyration coefficients used (non-dimensional)
    k_x: float | None                # Ixx = m·(k_x·b/2)²
    k_y: float | None                # Iyy = m·(k_y·c)²
    k_z: float | None                # Izz ≈ Ixx + Iyy (thin plate approximation)

    method: str
    accuracy: str
    assumptions: list[str]
    note: str | None = None


def estimate_inertia_from_geometry(
    *,
    mass_kg: float,
    span_m: float,
    mac_m: float,
    area_m2: float,
    sweep_le_deg: float = 35.0,
    dihedral_deg: float = 3.0,
    aspect_ratio: float | None = None,
    thickness_to_chord: float = 0.12,
    fuel_fraction: float = 0.0,
    payload_x_fraction: float = 0.5,
) -> InertiaEstimate:
    """
    Estimate mass moments of inertia for a BWB flying wing from planform data.

    Uses the radius-of-gyration method from DATCOM Volume VI, Table 10.1,
    adapted for BWB/flying-wing planforms.

    Physical basis:
    - Ixx (roll): dominated by mass distributed along the span.
      For a uniform elliptic-load wing: Ixx ≈ m·(b/2)²/8 = m·(b/4)²
      Corrected for actual planform taper: k_x ≈ 0.32 (typical BWB)
      Formula: Ixx = m·(k_x · b/2)²

    - Iyy (pitch): dominated by mass distributed in the chord direction.
      For a swept flying wing: Iyy is larger than for a conventional aircraft
      because the wing extends forward (leading-edge sweep pushes mass forward).
      Corrected: k_y ≈ 0.38 for a 35° LE-swept BWB
      Formula: Iyy = m·(k_y · MAC)²

    - Izz (yaw): thin-body approximation — Izz ≈ Ixx + Iyy (perpendicular axis theorem)
      Valid for a flat wing (thin plate in xy-plane, z-extent negligible).

    - Ixz (cross product): typically small for a symmetric aircraft.
      Estimated as Ixz ≈ m·k_xz·b/2·MAC where k_xz ≈ 0.02 for low dihedral.

    Accuracy:
    ★★★ for Iyy (±25% expected for BWB vs. measured)
    ★★★ for Ixx (±20% expected)
    ★★★ for Izz (inherits errors from both)

    For eigenvalue screening this is sufficient: dynamic modes scale as
    √(I/qSc) so a 25% error in I produces ~12% error in ω_n.

    References:
    [DATCOM] USAF DATCOM Vol VI, Table 10.1 — radius of gyration coefficients.
    [MK]     McLean, "Automatic Flight Control Systems", Table B.1.
    [HJ]     Hoak & Jantscher, AFFDL-TR-72-43, 1972.
    """
    if mass_kg <= 0:
        raise ValueError(f"mass_kg must be positive, got {mass_kg}")
    if span_m <= 0 or mac_m <= 0 or area_m2 <= 0:
        raise ValueError("Geometry parameters must be positive.")

    AR = aspect_ratio or (span_m**2 / area_m2)
    sweep_rad = math.radians(sweep_le_deg)
    semi_span = span_m / 2.0

    # ── Radius of gyration coefficients ──────────────────────────────────
    # k_x: roll — DATCOM Table 10.1 for flying wing, low-AR planform
    # Increases with dihedral (out-of-plane mass moment)
    # Decreases with high AR (mass closer to root)
    k_x_base = 0.32
    dihedral_correction = max(0.0, dihedral_deg / 90.0) * 0.05
    ar_correction = max(-0.05, min(0.05, (AR - 5.0) / 20.0))
    k_x = k_x_base + dihedral_correction + ar_correction

    # k_y: pitch — DATCOM Table 10.1 for swept flying wing
    # Larger k_y for more sweep (mass further from pitch axis)
    # Reference: k_y = 0.35 for 30° sweep, 0.42 for 50° sweep (linear interp)
    k_y_base = 0.35 + (sweep_le_deg - 30.0) * (0.42 - 0.35) / (50.0 - 30.0)
    k_y = max(0.25, min(0.55, k_y_base))

    # ── Compute inertias ─────────────────────────────────────────────────
    # Ixx = m · (k_x · b/2)²
    ixx = mass_kg * (k_x * semi_span) ** 2

    # Iyy = m · (k_y · c_bar)²
    iyy = mass_kg * (k_y * mac_m) ** 2

    # Izz = Ixx + Iyy (thin-plate perpendicular axis theorem — exact for flat wing)
    izz = ixx + iyy

    # Ixz: cross product — small for low dihedral, grows with sweep
    # DATCOM: Ixz/Izz ≈ sin(2Λ)/4 where Λ is LE sweep (for swept mass distribution)
    k_xz = math.sin(2.0 * sweep_rad) / 4.0 * 0.1  # conservative damped estimate
    ixz = mass_kg * k_xz * semi_span * mac_m

    # ── Payload and fuel correction ───────────────────────────────────────
    # If payload fraction is known, shift CG and adjust Iyy accordingly
    # (payload at payload_x_fraction of MAC shifts Iyy)
    # This is a simple first-order correction — not required if payload mass
    # is already included in mass_kg at a known CG.
    # Skip for now — caller should pass the total mass at actual CG.

    assumptions = [
        f"Radius of gyration k_x = {k_x:.3f} (DATCOM Table 10.1, flying wing)",
        f"Radius of gyration k_y = {k_y:.3f} (DATCOM, LE sweep = {sweep_le_deg:.0f}°)",
        "Izz = Ixx + Iyy (thin-plate perpendicular axis theorem)",
        "Ixz small — symmetric aircraft, low dihedral",
        "Mass uniformly distributed along span (no concentrated fuselage mass)",
        "Valid for subsonic, no aeroelastic deformation",
    ]

    note = (
        f"Estimated for m={mass_kg:.1f} kg, b={span_m:.2f} m, "
        f"c_bar={mac_m:.3f} m, AR={AR:.2f}, Λ_LE={sweep_le_deg:.0f}°. "
        "Expected accuracy: Iyy ±25%, Ixx ±20%. "
        "For eigenvalue screening this gives ω_n accurate to ~12%. "
        "Replace with measured values when available (weigh the aircraft, "
        "or use OpenAeroStruct structural model for Paper 2 anchor cases)."
    )

    return InertiaEstimate(
        ixx_kg_m2=ixx,
        iyy_kg_m2=iyy,
        izz_kg_m2=izz,
        ixz_kg_m2=ixz,
        k_x=round(k_x, 4),
        k_y=round(k_y, 4),
        k_z=None,  # derived from Ixx + Iyy, not independent
        method="DATCOM_radius_of_gyration_flying_wing",
        accuracy="★★★",
        assumptions=assumptions,
        note=note,
    )


def inertia_from_geometry_summary(
    geometry_summary: dict,
    mass_kg: float,
) -> InertiaEstimate:
    """
    Convenience wrapper: extract geometry from a geometry_summary.json dict
    and return inertia estimates.

    geometry_summary: loaded from <run_dir>/artifacts/geometry/geometry_summary.json
    """
    rv = geometry_summary.get("reference_values") or {}
    ma = geometry_summary.get("mean_angles_deg") or {}

    span_m       = rv.get("span_m")
    area_m2      = rv.get("area_m2")
    mac_m        = rv.get("mean_aerodynamic_chord_m")
    ar           = rv.get("aspect_ratio")
    sweep_le_deg = ma.get("sweep_le_deg", 35.0)
    dihedral_deg = abs(ma.get("dihedral_c4_deg", 3.0))

    if span_m is None or area_m2 is None or mac_m is None:
        raise ValueError(
            "geometry_summary missing required fields: "
            "reference_values.span_m, area_m2, mean_aerodynamic_chord_m"
        )

    return estimate_inertia_from_geometry(
        mass_kg=mass_kg,
        span_m=float(span_m),
        mac_m=float(mac_m),
        area_m2=float(area_m2),
        sweep_le_deg=float(sweep_le_deg),
        dihedral_deg=float(dihedral_deg),
        aspect_ratio=float(ar) if ar else None,
    )


def inertia_to_mass_properties(
    inertia: InertiaEstimate,
    mass_kg: float,
    x_cg_m: float,
    y_cg_m: float = 0.0,
    z_cg_m: float = 0.0,
) -> "aeris.dynamics.models.MassProperties":  # type: ignore[name-defined]
    """
    Convert InertiaEstimate to a MassProperties object for the dynamics pipeline.
    """
    from aeris.dynamics.models import InertiaPlaceholders, MassProperties
    return MassProperties(
        mass_kg=mass_kg,
        x_cg_m=x_cg_m,
        y_cg_m=y_cg_m,
        z_cg_m=z_cg_m,
        source="DATCOM_geometry_estimate",
        notes=f"Inertia estimated from planform geometry. Accuracy: {inertia.accuracy}.",
        inertia=InertiaPlaceholders(
            ixx_kg_m2=inertia.ixx_kg_m2,
            iyy_kg_m2=inertia.iyy_kg_m2,
            izz_kg_m2=inertia.izz_kg_m2,
            ixz_kg_m2=inertia.ixz_kg_m2,
        ),
    )
