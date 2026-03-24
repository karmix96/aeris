import pytest

from aeris.aero.models import FlightCondition, FlightConditionSweep
from aeris.aero.sweep import count_flight_condition_sweep_cases, expand_flight_condition_sweep


def _base_fc() -> FlightCondition:
    return FlightCondition(
        alpha_deg=0.0,
        beta_deg=0.0,
        mach=None,
        velocity_mps=30.0,
        altitude_m=0.0,
        p_rad_s=0.0,
        q_rad_s=0.0,
        r_rad_s=0.0,
    )


def test_count_flight_condition_sweep_cases():
    sweep = FlightConditionSweep(
        alpha_deg_values=[0.0, 5.0],
        beta_deg_values=[0.0, 2.0, 4.0],
    )
    assert count_flight_condition_sweep_cases(_base_fc(), sweep) == 6


def test_expand_flight_condition_sweep_respects_max_cases():
    sweep = FlightConditionSweep(
        alpha_deg_values=[0.0, 5.0],
        beta_deg_values=[0.0, 2.0, 4.0],
    )
    with pytest.raises(ValueError, match="exceeding max_cases"):
        expand_flight_condition_sweep(_base_fc(), sweep, max_cases=5)