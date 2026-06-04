"""
AERIS Dynamics — Data Models
=============================
All dataclasses for dynamics foundation, stability analysis, trim, and
control effectiveness. Single source of truth for the dynamics layer schema.

Design rules:
- All fields with physical units are documented inline.
- frozen=True everywhere — mutation is never in-place; create new instances.
- to_dict() on compound results for JSON serialisation.
- No business logic in models — that lives in analysis.py and trim.py.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Mass & inertia
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InertiaPlaceholders:
    """Principal moments of inertia in body axes. All [kg·m²]."""
    ixx_kg_m2: float | None = None   # roll inertia
    iyy_kg_m2: float | None = None   # pitch inertia
    izz_kg_m2: float | None = None   # yaw inertia
    ixy_kg_m2: float | None = None   # product of inertia (usually 0 for symmetric)
    ixz_kg_m2: float | None = None   # product of inertia (xz — can be nonzero)
    iyz_kg_m2: float | None = None   # product of inertia (usually 0 for symmetric)
    reference_axes: str = "body"


@dataclass(frozen=True)
class MassProperties:
    """Aircraft mass and CG in geometry/body axes."""
    mass_kg: float                              # total mass [kg]
    x_cg_m: float                              # longitudinal CG from nose ref [m]
    y_cg_m: float = 0.0                        # lateral CG (0 for symmetric) [m]
    z_cg_m: float = 0.0                        # vertical CG [m]
    reference_frame: str = "geometry_body_axes"
    source: str = "manual"
    notes: str | None = None
    inertia: InertiaPlaceholders = field(default_factory=InertiaPlaceholders)

    def inertia_complete(self) -> bool:
        """True if all three principal moments of inertia are provided."""
        i = self.inertia
        return all(v is not None for v in (i.ixx_kg_m2, i.iyy_kg_m2, i.izz_kg_m2))


# ---------------------------------------------------------------------------
# Trim
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TrimDefinition:
    """Trim problem specification. Currently schema-only — solver not yet implemented."""
    enabled: bool = False
    objective: str = "force_moment_balance"
    fixed_variables: dict[str, float] = field(default_factory=dict)
    solve_variables: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass(frozen=True)
class LongitudinalTrimEstimate:
    """
    First-order linearised longitudinal trim estimate.

    Two modes are computed when data is available:
      alpha_trim: control-fixed trim (solve for Δα such that Cm=0, δe fixed)
      delta_e_trim: alpha-fixed trim (solve for Δδe such that Cm=0, α fixed)

    Both are linear extrapolations from the current operating point.
    They are diagnostic estimates, not solutions from a nonlinear solver.
    """
    # Operating point inputs
    alpha_current_deg: float | None          # α at which aero was evaluated [deg]
    control_input_deg: float | None          # δe at evaluation point [deg]
    cm_current: float | None                 # Cm at operating point [-]
    cma_per_rad: float | None                # ∂Cm/∂α [/rad]
    cmde_per_rad: float | None               # ∂Cm/∂δe [/rad]  — None if not available

    # Control-fixed trim: solve Δα for Cm=0 at fixed δe
    delta_alpha_rad: float | None            # required Δα [rad]
    delta_alpha_deg: float | None            # required Δα [deg]
    alpha_trim_deg: float | None             # estimated trim α [deg]
    alpha_trim_in_bounds: bool | None        # True if trim α ∈ [-5°, +15°]

    # Elevon-fixed trim: solve Δδe for Cm=0 at fixed α
    delta_de_rad: float | None               # required Δδe [rad]
    delta_de_deg: float | None               # required Δδe [deg]
    de_trim_deg: float | None                # estimated trim δe [deg]
    de_trim_in_bounds: bool | None           # True if trim δe ∈ [-25°, +25°]

    valid: bool
    reason: str | None = None
    mode: str = "linearised_first_order"

    @property
    def has_elevon_trim(self) -> bool:
        return self.de_trim_deg is not None


@dataclass(frozen=True)
class TrimResult:
    """Complete trim analysis result — written to trim_result.json."""
    schema_version: str
    run_dir: str
    mode: str
    longitudinal: LongitudinalTrimEstimate
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Control effectiveness
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ControlEffectiveness:
    """
    Control surface effectiveness derivatives extracted from AVL stability output.
    These are constant w.r.t. CG position.
    """
    # Longitudinal
    cl_per_de_rad: float | None = None      # ∂CL/∂δe [/rad]
    cm_per_de_rad: float | None = None      # ∂Cm/∂δe [/rad]  — Cmδe

    # Lateral-directional
    cy_per_da_rad: float | None = None      # ∂CY/∂δa [/rad]  — aileron
    cl_roll_per_da_rad: float | None = None # ∂Cl/∂δa [/rad]
    cn_per_da_rad: float | None = None      # ∂Cn/∂δa [/rad]

    # Rudder (if present)
    cy_per_dr_rad: float | None = None      # ∂CY/∂δr [/rad]
    cl_roll_per_dr_rad: float | None = None # ∂Cl/∂δr [/rad]
    cn_per_dr_rad: float | None = None      # ∂Cn/∂δr [/rad]

    # Assessment
    pitch_authority_adequate: bool | None = None  # |Cmδe| > 0.1 /rad threshold
    notes: str | None = None


# ---------------------------------------------------------------------------
# Stability metrics
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LongitudinalStabilityDerivatives:
    """
    Stability-axis longitudinal derivatives from AVL.
    Per-radian unless noted.
    """
    cla: float | None = None    # ∂CL/∂α  — lift slope [/rad]
    cda: float | None = None    # ∂CD/∂α  [/rad]
    cma: float | None = None    # ∂Cm/∂α  — pitch stability [/rad], must be < 0 for stability
    clq: float | None = None    # ∂CL/∂(qc/2V) — pitch rate lift [/rad]
    cmq: float | None = None    # ∂Cm/∂(qc/2V) — pitch damping [/rad], must be < 0
    clad: float | None = None   # ∂CL/∂(α_dot·c/2V) — alpha-rate lift (approx)
    cmad: float | None = None   # ∂Cm/∂(α_dot·c/2V) — alpha-rate damping (approx)


@dataclass(frozen=True)
class LateralDirectionalStabilityDerivatives:
    """
    Stability-axis lateral-directional derivatives from AVL.
    Per-radian unless noted.
    """
    clb: float | None = None    # ∂Cl/∂β  — dihedral effect [/rad], must be < 0 for stability
    cnb: float | None = None    # ∂Cn/∂β  — weathercock stability [/rad], must be > 0
    cyb: float | None = None    # ∂CY/∂β  [/rad]
    clp: float | None = None    # ∂Cl/∂(pb/2V) — roll damping [/rad], must be < 0
    cnp: float | None = None    # ∂Cn/∂(pb/2V) — adverse yaw [/rad]
    clr: float | None = None    # ∂Cl/∂(rb/2V) — roll due to yaw rate [/rad]
    cnr: float | None = None    # ∂Cn/∂(rb/2V) — yaw damping [/rad], must be < 0


@dataclass(frozen=True)
class StabilityDerivativeSummary:
    """Complete set of stability derivatives with sign assessments."""
    longitudinal: LongitudinalStabilityDerivatives = field(
        default_factory=LongitudinalStabilityDerivatives
    )
    lateral_directional: LateralDirectionalStabilityDerivatives = field(
        default_factory=LateralDirectionalStabilityDerivatives
    )

    # Sign checks — True = correct sign for stability
    cma_sign_ok: bool | None = None           # Cma < 0
    cmq_sign_ok: bool | None = None           # Cmq < 0 (pitch damping)
    clb_sign_ok: bool | None = None           # Clβ < 0 (dihedral effect)
    cnb_sign_ok: bool | None = None           # Cnβ > 0 (directional stability)
    clp_sign_ok: bool | None = None           # Clp < 0 (roll damping)
    cnr_sign_ok: bool | None = None           # Cnr < 0 (yaw damping)
    spiral_metric: float | None = None        # Clβ·Cnr / (Clr·Cnβ) — < 1 = spiral stable
    spiral_stable: bool | None = None         # True if spiral_metric < 1


@dataclass(frozen=True)
class StabilityMetrics:
    """
    Core static stability metrics derived from aero result + mass properties.
    """
    # Geometry
    x_np_m: float | None            # neutral point x position [m]
    x_cg_m: float                   # CG x position [m]
    mac_m: float | None             # mean aerodynamic chord [m]

    # Static margin
    static_margin: float | None     # (Xnp - Xcg) / MAC [-]  positive = stable
    static_margin_percent_mac: float | None  # static_margin × 100 [%MAC]

    # Key derivatives
    cma: float | None = None        # ∂Cm/∂α [/rad]
    cma_consistent_with_static_margin: bool | None = None
    spiral_metric: float | None = None
    longitudinal_interpretation: str | None = None   # 'positive_static_margin' | 'negative_static_margin' | 'neutral_static_margin'

    # Flight condition context
    alpha_deg: float | None = None           # operating α [deg]
    velocity_mps: float | None = None        # operating velocity [m/s]
    altitude_m: float | None = None          # operating altitude [m]
    dynamic_pressure_pa: float | None = None # q∞ = ½ρV² [Pa]
    lift_n: float | None = None              # L = CL · q∞ · Sref [N]
    drag_n: float | None = None              # D = CD · q∞ · Sref [N]
    load_factor: float | None = None         # n = L / (m·g) [-]
    weight_n: float | None = None            # W = m·g [N]


# ---------------------------------------------------------------------------
# Dynamic stability modes (approximations)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ShortPeriodApproximation:
    """
    Short-period mode approximation from longitudinal derivatives.
    Valid when decoupled from phugoid (high frequency assumption).
    Reference: Etkin & Reid, 'Dynamics of Flight', 3rd ed.
    """
    omega_n_rad_s: float | None = None  # natural frequency [rad/s]
    zeta: float | None = None           # damping ratio [-]
    omega_d_rad_s: float | None = None  # damped natural frequency [rad/s]
    period_s: float | None = None       # oscillation period [s]
    time_to_half_s: float | None = None # time to half amplitude [s]  — positive = stable
    valid: bool = False
    reason: str | None = None

    # MIL-SPEC / Cooper-Harper quality level (approximate)
    # Level 1: ζ ∈ [0.35, 1.30], ωn > threshold
    # Level 2: ζ ∈ [0.25, 2.00]
    # Level 3: ζ > 0.15
    handling_quality_level: int | None = None   # 1, 2, or 3
    handling_quality_note: str | None = None


@dataclass(frozen=True)
class PhugoidApproximation:
    """
    Phugoid mode approximation (Lanchester approximation).
    omega_n ≈ g√2 / V,  zeta ≈ CD / (CL√2)
    """
    omega_n_rad_s: float | None = None
    zeta: float | None = None
    period_s: float | None = None
    time_to_double_or_half_s: float | None = None
    stable: bool | None = None   # zeta > 0
    valid: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class DutchRollApproximation:
    """
    Dutch roll mode approximation from lateral-directional derivatives.
    omega_n ≈ sqrt(Cnβ · q∞ · S · b / Izz)
    """
    omega_n_rad_s: float | None = None
    zeta: float | None = None
    period_s: float | None = None
    valid: bool = False
    reason: str | None = None
    handling_quality_level: int | None = None
    handling_quality_note: str | None = None


@dataclass(frozen=True)
class DynamicModesSummary:
    """All dynamic mode approximations in one place."""
    short_period: ShortPeriodApproximation = field(
        default_factory=ShortPeriodApproximation
    )
    phugoid: PhugoidApproximation = field(
        default_factory=PhugoidApproximation
    )
    dutch_roll: DutchRollApproximation = field(
        default_factory=DutchRollApproximation
    )
    modes_computed: bool = False
    missing_inputs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# State-space readiness
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StateSpacePreparation:
    """
    Assesses what level of dynamics analysis is currently possible.
    All flags are derived from the available data — never hardcoded.
    """
    mass_available: bool
    cg_available: bool
    inertia_available: bool
    xnp_available: bool
    mac_available: bool
    longitudinal_derivatives_available: bool
    lateral_derivatives_available: bool
    control_derivatives_available: bool = False  # Cmδe known

    # Computed readiness — evaluated by build_state_space_preparation()
    ready_for_trim_solver: bool = False       # True when Cma + Cmδe + mass + CG known
    ready_for_eigenanalysis: bool = False     # True when full inertia tensor available
    ready_for_short_period: bool = False      # True when Cma, Cmq, Cmαdot, mass, Iyy known
    ready_for_phugoid: bool = False           # True when CL, CD, velocity known
    ready_for_dutch_roll: bool = False        # True when Cnβ, Cnr, Izz known

    missing_items: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level foundation result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DynamicsFoundationResult:
    """
    Complete dynamics foundation artifact.
    Written to <run_dir>/dynamics/dynamics_foundation.json.
    """
    schema_version: str
    source_run_dir: str
    source_solver_id: str | None
    operating_point_snapshot: dict[str, Any]
    mass_properties: MassProperties
    trim_definition: TrimDefinition
    stability_metrics: StabilityMetrics
    stability_derivatives: StabilityDerivativeSummary = field(
        default_factory=StabilityDerivativeSummary
    )
    control_effectiveness: ControlEffectiveness = field(
        default_factory=ControlEffectiveness
    )
    dynamic_modes: DynamicModesSummary = field(
        default_factory=DynamicModesSummary
    )
    state_space_preparation: StateSpacePreparation = field(
        default_factory=lambda: StateSpacePreparation(
            mass_available=False,
            cg_available=False,
            inertia_available=False,
            xnp_available=False,
            mac_available=False,
            longitudinal_derivatives_available=False,
            lateral_derivatives_available=False,
        )
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)