from aeris.dynamics.trim import estimate_longitudinal_trim


def test_estimate_longitudinal_trim_basic():
    aero_result = {
        "scalars": {"cm": -0.47811},
        "stability_axis_derivatives": {"Cma": -2.517702},
        "solver_metadata": {
            "flight_condition": {
                "alpha_deg": 4.0
            }
        },
    }

    result = estimate_longitudinal_trim(aero_result=aero_result, run_dir="test_run")

    assert result.longitudinal.valid is True
    assert result.longitudinal.alpha_trim_deg is not None