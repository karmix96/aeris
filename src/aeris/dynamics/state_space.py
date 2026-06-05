"""
AERIS Dynamics — Full State-Space Assembly and Eigenvalue Analysis
===================================================================
Assembles the complete 4×4 longitudinal and 4×4 lateral-directional
state-space A matrices from dimensional stability derivatives, extracts
exact eigenvalues via numpy, and decomposes them into named flight
mechanics modes.

Architecture:
  1. Non-dimensional stability derivatives (from AVL) → dimensional derivatives
     via ISA atmosphere + reference geometry.
  2. Dimensional derivatives → A matrices (Etkin & Reid sign convention).
  3. A matrices → eigenvalues (numpy.linalg.eigvals).
  4. Eigenvalues → LongitudinalModes, LateralDirectionalModes dataclasses.
  5. Root locus: sweep a parameter (CG, speed, mass) and collect eigenvalue
     trajectories for the root locus plot.

References:
  [ER]  Etkin & Reid, "Dynamics of Flight", 3rd ed., Wiley 1996.
  [SL]  Stevens & Lewis, "Aircraft Control and Simulation", 3rd ed., Wiley 2015.
  [CS]  Cook, "Flight Dynamics Principles", 3rd ed., Butterworth-Heinemann 2012.
  [MK]  McLean, "Automatic Flight Control Systems", Prentice Hall, 1990.

Sign convention: x positive aft (standard aviation / AVL / AERIS).
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, field
from typing import Any

from aeris.dynamics.analysis import (
    GRAVITY_MPS2,
    dynamic_pressure,
    isa_density,
)

# ---------------------------------------------------------------------------
# Dimensional derivative conversion: non-dim → dimensional [1/s], [m/s²], etc.
# ---------------------------------------------------------------------------
# Etkin & Reid notation. All rates are body-axis angular rates.
# Velocity u₀ = trim speed [m/s].
# q∞ = ½ρV² [Pa], S = reference area [m²], c = MAC [m], b = span [m].
# Dimensional derivatives:
#   X_u = (q∞·S/m) · (2·CX_u/V  + CX_u·V) ... use Etkin notation.
#   Standard definitions per [ER] Table 5.1.
#
# We use the following dimensional derivative definitions (body-axis, trimmed
# level flight, small perturbation):
#
# Longitudinal (state vector [u, w, q, θ]):
#   X_u = q∞·S/(m·V₀) · (2·CD0 − CLu*α₀ + CX_u)   ≈  -(q∞·S/m)·2·CD/(V₀²)
#   X_w = (q∞·S/m)·(CX_a/V₀)                        ≈  (q∞·S·CL/(m·V₀))
#   Z_u = -(q∞·S·(2·CL + CLu))/(m·V₀)
#   Z_w = -(q∞·S·CLa)/(m·V₀)                         [/s]
#   M_u = (q∞·S·c·Cmu)/(Iyy·V₀)
#   M_w = (q∞·S·c·Cma)/(Iyy·V₀)
#   M_q = (q∞·S·c²·Cmq)/(2·Iyy·V₀)
#   M_w_dot = (q∞·S·c²·Cmad)/(2·Iyy·V₀²)           (alpha-dot term)
#
# Lateral-directional (state vector [β, p, r, φ]):
#   Y_v = (q∞·S·CYb)/(m·V₀)
#   L_v = (q∞·S·b·Clb)/(Ixx)
#   L_p = (q∞·S·b²·Clp)/(2·Ixx·V₀)
#   L_r = (q∞·S·b²·Clr)/(2·Ixx·V₀)
#   N_v = (q∞·S·b·Cnb)/(Izz)
#   N_p = (q∞·S·b²·Cnp)/(2·Izz·V₀)
#   N_r = (q∞·S·b²·Cnr)/(2·Izz·V₀)
#   Y_p = (q∞·S·b·CYp)/(2·m·V₀)
#   Y_r = (q∞·S·b·CYr)/(2·m·V₀)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class LongitudinalMode:
    """One longitudinal dynamic mode (short-period or phugoid)."""
    name: str                        # "short_period" or "phugoid"
    eigenvalue_real: float           # σ [1/s]  — negative = stable
    eigenvalue_imag: float           # ωd [rad/s]
    omega_n: float | None            # natural frequency [rad/s]
    zeta: float | None               # damping ratio [-]
    period_s: float | None           # oscillation period [s]
    time_to_half_s: float | None     # time to half amplitude (stable) [s]
    time_to_double_s: float | None   # time to double amplitude (unstable) [s]
    stable: bool                     # sigma < 0
    oscillatory: bool                # |imag| > 1e-6


@dataclass
class LateralDirectionalMode:
    """One lateral-directional dynamic mode."""
    name: str                        # "roll_subsidence", "spiral", "dutch_roll"
    eigenvalue_real: float
    eigenvalue_imag: float
    # Mode-specific outputs
    time_constant_s: float | None    # τ = -1/σ  for real modes (roll, spiral)
    omega_n: float | None            # [rad/s]  for Dutch roll
    zeta: float | None               # [-]      for Dutch roll
    period_s: float | None           # [s]      for Dutch roll
    time_to_double_s: float | None   # T₂ [s]   for spiral (divergent)
    stable: bool
    oscillatory: bool


@dataclass
class LongitudinalModes:
    """Complete longitudinal mode decomposition from eigenvalue analysis."""
    short_period: LongitudinalMode | None = None
    phugoid: LongitudinalMode | None = None
    all_eigenvalues: list[complex] = field(default_factory=list)
    a_matrix: list[list[float]] | None = None   # 4×4 for traceability
    valid: bool = False
    reason: str | None = None
    method: str = "full_state_space_4x4"


@dataclass
class LateralDirectionalModes:
    """Complete lateral-directional mode decomposition."""
    roll_subsidence: LateralDirectionalMode | None = None
    spiral: LateralDirectionalMode | None = None
    dutch_roll: LateralDirectionalMode | None = None
    all_eigenvalues: list[complex] = field(default_factory=list)
    a_matrix: list[list[float]] | None = None
    valid: bool = False
    reason: str | None = None
    method: str = "full_state_space_4x4"


@dataclass
class RootLocusPoint:
    """One point on the root locus (one parameter value → eigenvalues)."""
    parameter_value: float
    parameter_name: str
    longitudinal_eigenvalues: list[complex]
    lateral_eigenvalues: list[complex]


@dataclass
class RootLocusResult:
    """Complete root locus sweep."""
    parameter_name: str
    parameter_label: str
    parameter_unit: str
    points: list[RootLocusPoint]
    n_points: int


# ---------------------------------------------------------------------------
# Numpy availability guard
# ---------------------------------------------------------------------------

def _numpy_available() -> bool:
    try:
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Dimensional derivative conversion
# ---------------------------------------------------------------------------

class DimDerivatives:
    """
    Converts AVL non-dimensional stability derivatives to dimensional form.
    All in body axes, trimmed level flight, small perturbations.
    Reference: [ER] Chapter 4-5, [CS] Chapter 4-5.
    """

    def __init__(
        self,
        *,
        # Non-dimensional derivatives (all per radian unless noted)
        CLa: float, Cma: float,
        CYb: float, Clb: float, Cnb: float,
        Clp: float, Cmq: float, Cnr: float,
        Clr: float, Cnp: float,
        CLu: float = 0.0, Cmu: float = 0.0,
        CLq: float = 0.0, CLp: float = 0.0, CLr: float = 0.0,
        CYp: float = 0.0, CYr: float = 0.0,
        CDa: float = 0.0, CD0: float = 0.03,
        Cmad: float = 0.0,
        # Trim state
        CL0: float, CD0_trim: float,
        alpha0_rad: float,
        velocity_mps: float,
        altitude_m: float,
        # Reference geometry
        sref_m2: float,
        mac_m: float,
        span_m: float,
        # Mass properties
        mass_kg: float,
        ixx_kg_m2: float,
        iyy_kg_m2: float,
        izz_kg_m2: float,
        ixz_kg_m2: float = 0.0,
        gravity_mps2: float = GRAVITY_MPS2,
    ):
        self.V0  = velocity_mps
        self.alt = altitude_m
        self.S   = sref_m2
        self.c   = mac_m
        self.b   = span_m
        self.m   = mass_kg
        self.Ixx = ixx_kg_m2
        self.Iyy = iyy_kg_m2
        self.Izz = izz_kg_m2
        self.Ixz = ixz_kg_m2
        self.g   = gravity_mps2

        self.rho = isa_density(altitude_m)
        self.q   = 0.5 * self.rho * velocity_mps**2
        self.mu  = mass_kg / (self.rho * sref_m2 * mac_m)  # mass ratio

        # Trim state
        self.CL0     = CL0
        self.CD0t    = CD0_trim
        self.alpha0  = alpha0_rad

        # Non-dim derivatives
        self.CLa = CLa;  self.Cma  = Cma
        self.CYb = CYb;  self.Clb  = Clb;  self.Cnb = Cnb
        self.Clp = Clp;  self.Cmq  = Cmq;  self.Cnr = Cnr
        self.Clr = Clr;  self.Cnp  = Cnp
        self.CLu = CLu;  self.Cmu  = Cmu
        self.CLq = CLq;  self.CLp  = CLp;  self.CLr = CLr
        self.CYp = CYp;  self.CYr  = CYr
        self.CDa = CDa;  self.Cmad = Cmad

        # Scaling shortcuts
        self.qS   = self.q * sref_m2
        self.qSc  = self.q * sref_m2 * mac_m
        self.qSb  = self.q * sref_m2 * span_m
        self.qSb2 = self.q * sref_m2 * span_m**2
        self.qSc2 = self.q * sref_m2 * mac_m**2

    # ── Longitudinal dimensional derivatives ──────────────────────────────

    @property
    def X_u(self) -> float:
        """∂X/∂u  [1/s]   — drag-related speed stability  [ER 4.7.9]"""
        return -(self.qS / (self.m * self.V0)) * (2 * self.CD0t + self.CLu * self.alpha0)

    @property
    def X_w(self) -> float:
        """∂X/∂w  [1/s]   — lift contribution to X  [ER 4.7.10]"""
        return (self.qS / (self.m * self.V0)) * (self.CL0 - self.CDa)

    @property
    def Z_u(self) -> float:
        """∂Z/∂u  [1/s]   — speed-dependent lift change  [ER 4.7.11]"""
        return -(self.qS / (self.m * self.V0)) * (2 * self.CL0 + self.CLu)

    @property
    def Z_w(self) -> float:
        """∂Z/∂w  [1/s]   — lift curve slope in w-equation  [ER 4.7.12]"""
        return -(self.qS * self.CLa) / (self.m * self.V0)

    @property
    def Z_q(self) -> float:
        """∂Z/∂q  [m/s]   — lift due to pitch rate  [ER 4.7.13]"""
        return -(self.qSc * self.CLq) / (2 * self.m * self.V0)

    @property
    def M_u(self) -> float:
        """∂M/∂u  [1/(m·s)]  — Mach / speed effect on pitching moment"""
        return (self.qSc * self.Cmu) / (self.Iyy * self.V0)

    @property
    def M_w(self) -> float:
        """∂M/∂w  [1/(m·s)]  — pitch stiffness in w-form  [ER 4.7.16]"""
        return (self.qSc * self.Cma) / (self.Iyy * self.V0)

    @property
    def M_q(self) -> float:
        """∂M/∂q  [1/s]   — pitch rate damping  [ER 4.7.17]"""
        return (self.qSc2 * self.Cmq) / (2 * self.Iyy * self.V0)

    @property
    def M_w_dot(self) -> float:
        """∂M/∂ẇ  [1/(m·s)]  — alpha-dot pitch damping  [ER 4.7.18]"""
        return (self.qSc2 * self.Cmad) / (2 * self.Iyy * self.V0**2)

    # ── Lateral-directional dimensional derivatives ────────────────────────

    @property
    def Y_v(self) -> float:
        """∂Y/∂v  [1/s]"""
        return (self.qS * self.CYb) / (self.m * self.V0)

    @property
    def Y_p(self) -> float:
        """∂Y/∂p  [m/s]"""
        return (self.qSb * self.CYp) / (2 * self.m * self.V0)

    @property
    def Y_r(self) -> float:
        """∂Y/∂r  [m/s]"""
        return (self.qSb * self.CYr) / (2 * self.m * self.V0)

    @property
    def L_v(self) -> float:
        """∂L/∂v  [1/(m·s)]  — dihedral effect"""
        return (self.qSb * self.Clb) / (self.Ixx * self.V0)

    @property
    def L_p(self) -> float:
        """∂L/∂p  [1/s]  — roll damping"""
        return (self.qSb2 * self.Clp) / (2 * self.Ixx * self.V0)

    @property
    def L_r(self) -> float:
        """∂L/∂r  [1/s]  — roll due to yaw rate"""
        return (self.qSb2 * self.Clr) / (2 * self.Ixx * self.V0)

    @property
    def N_v(self) -> float:
        """∂N/∂v  [1/(m·s)]  — weathercock stability"""
        return (self.qSb * self.Cnb) / (self.Izz * self.V0)

    @property
    def N_p(self) -> float:
        """∂N/∂p  [1/s]  — adverse yaw"""
        return (self.qSb2 * self.Cnp) / (2 * self.Izz * self.V0)

    @property
    def N_r(self) -> float:
        """∂N/∂r  [1/s]  — yaw damping"""
        return (self.qSb2 * self.Cnr) / (2 * self.Izz * self.V0)


# ---------------------------------------------------------------------------
# A-matrix assembly
# ---------------------------------------------------------------------------

def build_longitudinal_a_matrix(dd: DimDerivatives) -> list[list[float]]:
    """
    4×4 longitudinal A matrix. State vector: x = [u, w, q, θ].
    Reference: [ER] Eq 5.2.1, [CS] Eq 4.36.

    A = | X_u    X_w    0       -g·cos(θ₀) |
        | Z_u    Z_w    Z_q+V₀  -g·sin(θ₀) |
        | M_u+M_wd·Z_u  M_w+M_wd·Z_w  M_q+M_wd·(Z_q+V₀)  -M_wd·g·sin(θ₀) |
        | 0      0      1       0          |

    For trimmed level flight: θ₀ = α₀ (small), sin(θ₀) ≈ sin(α₀), cos(θ₀) ≈ 1.
    The M_w_dot term modifies the pitch equation via quasi-steady approximation.
    """
    g   = dd.g
    V0  = dd.V0
    a0  = dd.alpha0
    Mwd = dd.M_w_dot  # alpha-dot effect

    Xu = dd.X_u;  Xw = dd.X_w
    Zu = dd.Z_u;  Zw = dd.Z_w;  Zq = dd.Z_q
    Mu = dd.M_u;  Mw = dd.M_w;  Mq = dd.M_q

    cos_t = math.cos(a0)
    sin_t = math.sin(a0)

    # Modified pitch derivatives with alpha-dot augmentation
    Mu_ = Mu + Mwd * Zu
    Mw_ = Mw + Mwd * Zw
    Mq_ = Mq + Mwd * (Zq + V0)

    return [
        [Xu,   Xw,   0.0,       -g * cos_t],
        [Zu,   Zw,   Zq + V0,   -g * sin_t],
        [Mu_,  Mw_,  Mq_,       -Mwd * g * sin_t],
        [0.0,  0.0,  1.0,        0.0],
    ]


def build_lateral_a_matrix(dd: DimDerivatives) -> list[list[float]]:
    """
    4×4 lateral-directional A matrix. State vector: x = [v, p, r, φ].
    Reference: [ER] Eq 5.3.1, [CS] Eq 4.55.

    For Ixz ≠ 0, the rolling/yawing equations are coupled via Ixz.
    Defines Γ = Ixx·Izz - Ixz²,  lv = Izz·Lv + Ixz·Nv, etc.

    A = | Y_v    Y_p    Y_r - V₀   g·cos(θ₀)  |
        | lv     lp     lr          0           |
        | nv     np     nr          0           |
        | 0      1      tan(θ₀)     0           |
    """
    g   = dd.g
    V0  = dd.V0
    a0  = dd.alpha0

    Gamma = dd.Ixx * dd.Izz - dd.Ixz**2
    if abs(Gamma) < 1e-20:
        Gamma = 1e-20  # avoid division by zero

    Yv = dd.Y_v;  Yp = dd.Y_p;  Yr = dd.Y_r
    Lv = dd.L_v;  Lp = dd.L_p;  Lr = dd.L_r
    Nv = dd.N_v;  Np = dd.N_p;  Nr = dd.N_r
    Ixz = dd.Ixz
    Ixx = dd.Ixx
    Izz = dd.Izz

    # Cross-coupling via Ixz [ER Eq 5.3.8]
    lv = (Izz * Lv + Ixz * Nv) / Gamma
    lp = (Izz * Lp + Ixz * Np) / Gamma
    lr = (Izz * Lr + Ixz * Nr) / Gamma
    nv = (Ixx * Nv + Ixz * Lv) / Gamma
    np = (Ixx * Np + Ixz * Lp) / Gamma
    nr = (Ixx * Nr + Ixz * Lr) / Gamma

    cos_t = math.cos(a0)
    tan_t = math.tan(a0)

    return [
        [Yv,  Yp,  Yr - V0,   g * cos_t],
        [lv,  lp,  lr,         0.0],
        [nv,  np,  nr,         0.0],
        [0.0, 1.0, tan_t,      0.0],
    ]


# ---------------------------------------------------------------------------
# Eigenvalue analysis and mode decomposition
# ---------------------------------------------------------------------------

def _eigenvalues(a_matrix: list[list[float]]) -> list[complex]:
    """Compute eigenvalues via numpy. Returns sorted by real part (most stable first)."""
    import numpy as np
    A = np.array(a_matrix, dtype=float)
    eigs = np.linalg.eigvals(A)
    return sorted(list(eigs), key=lambda e: e.real)


def _mode_from_complex_pair(
    eig: complex, name: str
) -> LongitudinalMode:
    """Convert a complex conjugate eigenvalue to a longitudinal mode."""
    sigma  = eig.real
    omega_d = abs(eig.imag)
    oscillatory = omega_d > 1e-4

    omega_n: float | None = None
    zeta:    float | None = None
    period:  float | None = None
    t_half:  float | None = None
    t_double: float | None = None

    if oscillatory:
        omega_n = abs(eig)  # |σ + jωd| = sqrt(σ²+ωd²)
        zeta    = -sigma / omega_n if omega_n > 1e-12 else None
        period  = 2.0 * math.pi / omega_d

    if sigma < 0:
        t_half   = -math.log(2.0) / sigma  # positive [s]
    elif sigma > 1e-8:
        t_double = math.log(2.0) / sigma   # positive [s]

    return LongitudinalMode(
        name=name,
        eigenvalue_real=sigma,
        eigenvalue_imag=eig.imag,
        omega_n=round(omega_n, 4) if omega_n else None,
        zeta=round(zeta, 4) if zeta else None,
        period_s=round(period, 3) if period else None,
        time_to_half_s=round(t_half, 3) if t_half else None,
        time_to_double_s=round(t_double, 3) if t_double else None,
        stable=sigma < 0,
        oscillatory=oscillatory,
    )


def decompose_longitudinal_modes(
    eigenvalues: list[complex],
) -> tuple[LongitudinalMode | None, LongitudinalMode | None]:
    """
    Decompose 4 longitudinal eigenvalues into short-period and phugoid.
    Short-period: higher frequency, faster pair.
    Phugoid: lower frequency, slower pair.
    """
    # Pair complex conjugates
    pairs: list[complex] = []
    used = [False] * len(eigenvalues)
    for i, ei in enumerate(eigenvalues):
        if used[i]:
            continue
        # Find conjugate
        for j, ej in enumerate(eigenvalues):
            if j == i or used[j]:
                continue
            if abs(ei.real - ej.real) < 1e-6 and abs(ei.imag + ej.imag) < 1e-6:
                pairs.append(ei)
                used[i] = used[j] = True
                break
        else:
            # Real eigenvalue — treat as overdamped mode
            pairs.append(complex(ei.real, 0.0))
            used[i] = True

    # Sort by |eigenvalue| descending — short-period has larger magnitude
    pairs_sorted = sorted(pairs, key=lambda e: abs(e), reverse=True)

    sp = _mode_from_complex_pair(pairs_sorted[0], "short_period") if len(pairs_sorted) > 0 else None
    ph = _mode_from_complex_pair(pairs_sorted[1], "phugoid")      if len(pairs_sorted) > 1 else None
    return sp, ph


def decompose_lateral_modes(
    eigenvalues: list[complex],
) -> tuple[LateralDirectionalMode | None, LateralDirectionalMode | None, LateralDirectionalMode | None]:
    """
    Decompose 4 lateral eigenvalues into:
    - Roll subsidence: large negative real, nearly real eigenvalue
    - Spiral: small real eigenvalue (positive = divergent)
    - Dutch roll: complex conjugate pair
    """
    real_eigs    = [e for e in eigenvalues if abs(e.imag) < 1e-4]
    complex_eigs = [e for e in eigenvalues if abs(e.imag) >= 1e-4]

    # Dutch roll: complex pair
    dutch: LateralDirectionalMode | None = None
    if complex_eigs:
        dr_eig = max(complex_eigs, key=lambda e: abs(e.imag))
        sigma   = dr_eig.real
        omega_d = abs(dr_eig.imag)
        omega_n = abs(dr_eig)
        zeta    = -sigma / omega_n if omega_n > 1e-12 else None
        period  = 2.0 * math.pi / omega_d if omega_d > 1e-8 else None
        dutch = LateralDirectionalMode(
            name="dutch_roll",
            eigenvalue_real=sigma,
            eigenvalue_imag=dr_eig.imag,
            time_constant_s=None,
            omega_n=round(omega_n, 4),
            zeta=round(zeta, 4) if zeta is not None else None,
            period_s=round(period, 3) if period else None,
            time_to_double_s=None,
            stable=sigma < 0,
            oscillatory=True,
        )

    # Real modes: roll subsidence (most negative) and spiral (smallest |real|)
    roll: LateralDirectionalMode | None = None
    spiral: LateralDirectionalMode | None = None

    if real_eigs:
        real_sorted = sorted(real_eigs, key=lambda e: e.real)
        # Roll subsidence: most negative
        rs = real_sorted[0]
        tau_r = -1.0 / rs.real if rs.real < -1e-8 else None
        roll = LateralDirectionalMode(
            name="roll_subsidence",
            eigenvalue_real=rs.real,
            eigenvalue_imag=0.0,
            time_constant_s=round(tau_r, 4) if tau_r else None,
            omega_n=None, zeta=None, period_s=None,
            time_to_double_s=None,
            stable=rs.real < 0,
            oscillatory=False,
        )
        # Spiral: smallest |real|
        if len(real_sorted) > 1:
            sp_e = real_sorted[-1]  # closest to zero (may be positive = divergent)
            t2 = math.log(2.0) / sp_e.real if sp_e.real > 1e-8 else None
            tc = -1.0 / sp_e.real if sp_e.real < -1e-8 else None
            spiral = LateralDirectionalMode(
                name="spiral",
                eigenvalue_real=sp_e.real,
                eigenvalue_imag=0.0,
                time_constant_s=round(tc, 2) if tc else None,
                omega_n=None, zeta=None, period_s=None,
                time_to_double_s=round(t2, 1) if t2 else None,
                stable=sp_e.real <= 0,
                oscillatory=False,
            )

    return roll, spiral, dutch


# ---------------------------------------------------------------------------
# Top-level assembly
# ---------------------------------------------------------------------------

def compute_full_longitudinal(
    dd: DimDerivatives,
) -> LongitudinalModes:
    """Assemble 4×4 longitudinal A matrix and compute all modes."""
    if not _numpy_available():
        return LongitudinalModes(
            valid=False,
            reason="numpy is not installed. Run `pip install numpy`.",
        )
    try:
        A = build_longitudinal_a_matrix(dd)
        eigs = _eigenvalues(A)
        sp, ph = decompose_longitudinal_modes(eigs)
        return LongitudinalModes(
            short_period=sp,
            phugoid=ph,
            all_eigenvalues=eigs,
            a_matrix=A,
            valid=True,
            method="full_state_space_4x4",
        )
    except Exception as e:
        return LongitudinalModes(valid=False, reason=str(e))


def compute_full_lateral(
    dd: DimDerivatives,
) -> LateralDirectionalModes:
    """Assemble 4×4 lateral A matrix and compute all modes."""
    if not _numpy_available():
        return LateralDirectionalModes(
            valid=False,
            reason="numpy is not installed. Run `pip install numpy`.",
        )
    try:
        A = build_lateral_a_matrix(dd)
        eigs = _eigenvalues(A)
        roll, spiral, dutch = decompose_lateral_modes(eigs)
        return LateralDirectionalModes(
            roll_subsidence=roll,
            spiral=spiral,
            dutch_roll=dutch,
            all_eigenvalues=eigs,
            a_matrix=A,
            valid=True,
            method="full_state_space_4x4",
        )
    except Exception as e:
        return LateralDirectionalModes(valid=False, reason=str(e))


# ---------------------------------------------------------------------------
# Root locus sweep
# ---------------------------------------------------------------------------

def compute_root_locus_vs_cg(
    *,
    base_dd: DimDerivatives,
    cg_values_m: list[float],
    x_np_m: float,
    mac_m: float,
    x_positive_aft: bool = True,
) -> RootLocusResult:
    """
    Sweep CG position and collect eigenvalue trajectories.
    Modifies Cma at each CG position: Cma(xcg) = -CLa·(Xnp-xcg)/c
    (standard result: Cma = -CLa·static_margin, SM = (Xnp-xcg)/c).
    """
    import numpy as np
    points: list[RootLocusPoint] = []

    for xcg in cg_values_m:
        # Re-compute Cma for this CG
        sm = (x_np_m - xcg) / mac_m
        if not x_positive_aft:
            sm = -sm
        new_cma = -base_dd.CLa * sm  # Cma = -CLα·SM [ER §3.3.6]

        # Rebuild DimDerivatives with new Cma
        import copy, types
        # We directly construct with updated Cma
        try:
            dd_new = DimDerivatives(
                CLa=base_dd.CLa, Cma=new_cma,
                CYb=base_dd.CYb, Clb=base_dd.Clb, Cnb=base_dd.Cnb,
                Clp=base_dd.Clp, Cmq=base_dd.Cmq, Cnr=base_dd.Cnr,
                Clr=base_dd.Clr, Cnp=base_dd.Cnp,
                CLu=base_dd.CLu, Cmu=base_dd.Cmu,
                CLq=base_dd.CLq, CLp=base_dd.CLp, CLr=base_dd.CLr,
                CYp=base_dd.CYp, CYr=base_dd.CYr,
                CDa=base_dd.CDa, CD0=base_dd.CD0t,
                Cmad=base_dd.Cmad,
                CL0=base_dd.CL0, CD0_trim=base_dd.CD0t,
                alpha0_rad=base_dd.alpha0,
                velocity_mps=base_dd.V0, altitude_m=base_dd.alt,
                sref_m2=base_dd.S, mac_m=base_dd.c, span_m=base_dd.b,
                mass_kg=base_dd.m,
                ixx_kg_m2=base_dd.Ixx, iyy_kg_m2=base_dd.Iyy,
                izz_kg_m2=base_dd.Izz, ixz_kg_m2=base_dd.Ixz,
            )
            long_eigs = _eigenvalues(build_longitudinal_a_matrix(dd_new))
            lat_eigs  = _eigenvalues(build_lateral_a_matrix(dd_new))
        except Exception:
            long_eigs, lat_eigs = [], []

        points.append(RootLocusPoint(
            parameter_value=xcg,
            parameter_name="x_cg_m",
            longitudinal_eigenvalues=long_eigs,
            lateral_eigenvalues=lat_eigs,
        ))

    return RootLocusResult(
        parameter_name="x_cg_m",
        parameter_label="CG x position",
        parameter_unit="m",
        points=points,
        n_points=len(points),
    )
