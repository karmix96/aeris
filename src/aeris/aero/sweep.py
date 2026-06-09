"""
Aero sweep expansion.

Generates a full Cartesian product of flight condition parameters and optional
control-surface input values based on a base condition and sweep definitions.
"""

from __future__ import annotations

from itertools import product

from .models import AeroSweepCaseInput, FlightCondition, FlightConditionSweep

DEFAULT_MAX_SWEEP_CASES = 256


def _resolved_control_values(
    sweep: FlightConditionSweep,
    *,
    base_control_input_deg: float | None,
) -> list[float | None]:
    if sweep.control_input_deg_values:
        return [float(v) for v in sweep.control_input_deg_values]
    return [None if base_control_input_deg is None else float(base_control_input_deg)]


def _resolved_diff_values(sweep: FlightConditionSweep) -> list[float]:
    """Return diff sweep values, or empty list if none configured."""
    return [float(v) for v in sweep.diff_input_deg_values]


def count_flight_condition_sweep_cases(
    base: FlightCondition,
    sweep: FlightConditionSweep,
    *,
    base_control_input_deg: float | None = None,
) -> int:
    alpha_values = sweep.alpha_deg_values or [base.alpha_deg]
    beta_values = sweep.beta_deg_values or [base.beta_deg]
    velocity_values = sweep.velocity_mps_values or [base.velocity_mps]
    altitude_values = sweep.altitude_m_values or [base.altitude_m]
    p_values = sweep.p_rad_s_values or [base.p_rad_s]
    q_values = sweep.q_rad_s_values or [base.q_rad_s]
    r_values = sweep.r_rad_s_values or [base.r_rad_s]
    control_values = _resolved_control_values(
        sweep,
        base_control_input_deg=base_control_input_deg,
    )

    return (
        len(alpha_values)
        * len(beta_values)
        * len(velocity_values)
        * len(altitude_values)
        * len(p_values)
        * len(q_values)
        * len(r_values)
        * len(control_values)
    )


def expand_aero_sweep(
    base: FlightCondition,
    sweep: FlightConditionSweep,
    *,
    base_control_input_deg: float | None = None,
    max_cases: int | None = DEFAULT_MAX_SWEEP_CASES,
) -> list[AeroSweepCaseInput]:
    alpha_values = sweep.alpha_deg_values or [base.alpha_deg]
    beta_values = sweep.beta_deg_values or [base.beta_deg]
    velocity_values = sweep.velocity_mps_values or [base.velocity_mps]
    altitude_values = sweep.altitude_m_values or [base.altitude_m]
    p_values = sweep.p_rad_s_values or [base.p_rad_s]
    q_values = sweep.q_rad_s_values or [base.q_rad_s]
    r_values = sweep.r_rad_s_values or [base.r_rad_s]
    control_values = _resolved_control_values(
        sweep,
        base_control_input_deg=base_control_input_deg,
    )

    n_cases = (
        len(alpha_values)
        * len(beta_values)
        * len(velocity_values)
        * len(altitude_values)
        * len(p_values)
        * len(q_values)
        * len(r_values)
        * len(control_values)
    )
    if max_cases is not None and n_cases > max_cases:
        raise ValueError(
            f"Sweep expands to {n_cases} cases, exceeding max_cases={max_cases}. "
            "This is how laptops go to die."
        )

    cases: list[AeroSweepCaseInput] = []

    # ── Symmetric sweep (delta_e_sym, diff=0) ────────────────────────────────
    for (
        alpha_deg,
        beta_deg,
        velocity_mps,
        altitude_m,
        p_rad_s,
        q_rad_s,
        r_rad_s,
        control_input_deg,
    ) in product(
        alpha_values,
        beta_values,
        velocity_values,
        altitude_values,
        p_values,
        q_values,
        r_values,
        control_values,
    ):
        cases.append(
            AeroSweepCaseInput(
                flight_condition=FlightCondition(
                    alpha_deg=float(alpha_deg),
                    beta_deg=float(beta_deg),
                    mach=base.mach,
                    velocity_mps=float(velocity_mps),
                    altitude_m=float(altitude_m),
                    p_rad_s=float(p_rad_s),
                    q_rad_s=float(q_rad_s),
                    r_rad_s=float(r_rad_s),
                ),
                control_input_deg=None if control_input_deg is None else float(control_input_deg),
                diff_input_deg=None,
                sweep_type="sym",
            )
        )

    # ── Differential sweep (delta_a_diff, sym=0) — independent, not product ──
    diff_values = _resolved_diff_values(sweep)
    for (
        alpha_deg,
        beta_deg,
        velocity_mps,
        altitude_m,
        p_rad_s,
        q_rad_s,
        r_rad_s,
        diff_deg,
    ) in product(
        alpha_values,
        beta_values,
        velocity_values,
        altitude_values,
        p_values,
        q_values,
        r_values,
        diff_values,
    ):
        cases.append(
            AeroSweepCaseInput(
                flight_condition=FlightCondition(
                    alpha_deg=float(alpha_deg),
                    beta_deg=float(beta_deg),
                    mach=base.mach,
                    velocity_mps=float(velocity_mps),
                    altitude_m=float(altitude_m),
                    p_rad_s=float(p_rad_s),
                    q_rad_s=float(q_rad_s),
                    r_rad_s=float(r_rad_s),
                ),
                control_input_deg=0.0,   # symmetric locked at 0 during diff sweep
                diff_input_deg=float(diff_deg),
                sweep_type="diff",
            )
        )

    return cases