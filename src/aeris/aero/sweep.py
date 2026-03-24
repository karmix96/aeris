"""
Flight condition sweep expansion.

Generates a full Cartesian product of flight condition parameters based on
a base condition and sweep definitions.
"""

from __future__ import annotations

from itertools import product

from .models import FlightCondition, FlightConditionSweep

DEFAULT_MAX_SWEEP_CASES = 256


def count_flight_condition_sweep_cases(
    base: FlightCondition,
    sweep: FlightConditionSweep,
) -> int:
    alpha_values = sweep.alpha_deg_values or [base.alpha_deg]
    beta_values = sweep.beta_deg_values or [base.beta_deg]
    velocity_values = sweep.velocity_mps_values or [base.velocity_mps]
    altitude_values = sweep.altitude_m_values or [base.altitude_m]
    p_values = sweep.p_rad_s_values or [base.p_rad_s]
    q_values = sweep.q_rad_s_values or [base.q_rad_s]
    r_values = sweep.r_rad_s_values or [base.r_rad_s]

    return (
        len(alpha_values)
        * len(beta_values)
        * len(velocity_values)
        * len(altitude_values)
        * len(p_values)
        * len(q_values)
        * len(r_values)
    )


def expand_flight_condition_sweep(
    base: FlightCondition,
    sweep: FlightConditionSweep,
    *,
    max_cases: int | None = DEFAULT_MAX_SWEEP_CASES,
) -> list[FlightCondition]:
    alpha_values = sweep.alpha_deg_values or [base.alpha_deg]
    beta_values = sweep.beta_deg_values or [base.beta_deg]
    velocity_values = sweep.velocity_mps_values or [base.velocity_mps]
    altitude_values = sweep.altitude_m_values or [base.altitude_m]
    p_values = sweep.p_rad_s_values or [base.p_rad_s]
    q_values = sweep.q_rad_s_values or [base.q_rad_s]
    r_values = sweep.r_rad_s_values or [base.r_rad_s]

    n_cases = (
        len(alpha_values)
        * len(beta_values)
        * len(velocity_values)
        * len(altitude_values)
        * len(p_values)
        * len(q_values)
        * len(r_values)
    )
    if max_cases is not None and n_cases > max_cases:
        raise ValueError(
            f"Sweep expands to {n_cases} cases, exceeding max_cases={max_cases}. "
            "This is how laptops go to die."
        )

    cases: list[FlightCondition] = []

    for alpha_deg, beta_deg, velocity_mps, altitude_m, p_rad_s, q_rad_s, r_rad_s in product(
        alpha_values,
        beta_values,
        velocity_values,
        altitude_values,
        p_values,
        q_values,
        r_values,
    ):
        cases.append(
            FlightCondition(
                alpha_deg=float(alpha_deg),
                beta_deg=float(beta_deg),
                mach=base.mach,
                velocity_mps=float(velocity_mps),
                altitude_m=float(altitude_m),
                p_rad_s=float(p_rad_s),
                q_rad_s=float(q_rad_s),
                r_rad_s=float(r_rad_s),
            )
        )

    return cases