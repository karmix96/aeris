import pytest

from aeris.aero.models import FlightCondition, FlightConditionSweep
from aeris.aero.sweep import count_flight_condition_sweep_cases, expand_aero_sweep


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


def test_count_flight_condition_sweep_cases_without_control_dimension():
    sweep = FlightConditionSweep(
        alpha_deg_values=[0.0, 5.0],
        beta_deg_values=[0.0, 2.0, 4.0],
    )
    assert count_flight_condition_sweep_cases(_base_fc(), sweep) == 6


def test_count_flight_condition_sweep_cases_with_control_dimension():
    sweep = FlightConditionSweep(
        alpha_deg_values=[0.0, 5.0],
        control_input_deg_values=[-5.0, 0.0, 5.0],
    )
    assert count_flight_condition_sweep_cases(
        _base_fc(),
        sweep,
        base_control_input_deg=None,
    ) == 6


def test_expand_aero_sweep_respects_max_cases():
    sweep = FlightConditionSweep(
        alpha_deg_values=[0.0, 5.0],
        beta_deg_values=[0.0, 2.0, 4.0],
        control_input_deg_values=[-5.0, 0.0],
    )
    with pytest.raises(ValueError, match="exceeding max_cases"):
        expand_aero_sweep(_base_fc(), sweep, max_cases=10)


def test_expand_aero_sweep_includes_control_input_values():
    sweep = FlightConditionSweep(
        alpha_deg_values=[0.0, 5.0],
        control_input_deg_values=[-5.0, 0.0, 5.0],
    )

    cases = expand_aero_sweep(_base_fc(), sweep)

    assert len(cases) == 6
    assert sorted({case.control_input_deg for case in cases}) == [-5.0, 0.0, 5.0]
    assert sorted({case.flight_condition.alpha_deg for case in cases}) == [0.0, 5.0]


def test_expand_aero_sweep_uses_base_control_input_when_no_control_values_provided():
    sweep = FlightConditionSweep(
        alpha_deg_values=[0.0, 5.0],
    )

    cases = expand_aero_sweep(
        _base_fc(),
        sweep,
        base_control_input_deg=2.5,
    )

    assert len(cases) == 2
    assert all(case.control_input_deg == pytest.approx(2.5) for case in cases)