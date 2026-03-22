from __future__ import annotations

from itertools import product

from .models import FlightCondition, FlightConditionSweep


def expand_flight_condition_sweep(
    base: FlightCondition,
    sweep: FlightConditionSweep,
) -> list[FlightCondition]:
    alpha_values = sweep.alpha_deg_values or [base.alpha_deg]
    beta_values = sweep.beta_deg_values or [base.beta_deg]
    velocity_values = sweep.velocity_mps_values or [base.velocity_mps]
    altitude_values = sweep.altitude_m_values or [base.altitude_m]
    p_values = sweep.p_rad_s_values or [base.p_rad_s]
    q_values = sweep.q_rad_s_values or [base.q_rad_s]
    r_values = sweep.r_rad_s_values or [base.r_rad_s]

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