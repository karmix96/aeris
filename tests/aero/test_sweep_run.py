import json
from pathlib import Path

from aeris.aero.models import (
    AeroFailure,
    AeroGeometryView,
    AeroResult,
    AeroSolverSettings,
    AeroStatus,
    FlightCondition,
    FlightConditionSweep,
)
from aeris.aero.sweep_run import run_aero_sweep


class DummySolver:
    def __init__(self, statuses):
        self._statuses = list(statuses)

    def run_case(self, aero_input, output_dir):
        status = self._statuses.pop(0)
        result = AeroResult(
            status=status,
            solver_id="dummy",
            runtime_sec=0.5,
        )
        if status != AeroStatus.SUCCESS:
            result.failure = AeroFailure(
                status=status,
                reason="dummy_failure",
                message="broken on purpose",
            )
        payload = {
            "status": status.value,
            "solver_id": "dummy",
            "scalars": {"cl": 0.1, "cd": 0.01, "cm": 0.0, "l_over_d": 10.0, "cy": 0.0, "cl_roll": 0.0, "cn": 0.0,
                        "cd_ind": None, "cd_ff": None, "span_efficiency": None, "x_np": None},
            "stability_axis_derivatives": {},
            "body_axis_derivatives": {},
            "derived_metrics": {},
            "runtime_sec": 0.5,
            "warnings": [],
            "artifact_paths": {},
            "solver_metadata": {},
            "failure": None if result.failure is None else {
                "status": result.failure.status.value,
                "reason": result.failure.reason,
                "message": result.failure.message,
                "exception_type": result.failure.exception_type,
            },
        }
        (output_dir / "aero_result.json").write_text(json.dumps(payload), encoding="utf-8")
        return result


def test_run_aero_sweep_summary_counts(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "aeris.aero.sweep_run.create_solver",
        lambda solver_id: DummySolver(
            [AeroStatus.SUCCESS, AeroStatus.INVALID_OUTPUT, AeroStatus.SOLVER_FAILED]
        ),
    )

    geometry = AeroGeometryView(view_id="g", airplane=object(), source_generator="unit")
    result = run_aero_sweep(
        geometry=geometry,
        base_flight_condition=FlightCondition(
            alpha_deg=0.0,
            beta_deg=0.0,
            mach=None,
            velocity_mps=30.0,
            altitude_m=0.0,
            p_rad_s=0.0,
            q_rad_s=0.0,
            r_rad_s=0.0,
        ),
        sweep=FlightConditionSweep(alpha_deg_values=[0.0, 2.0, 4.0]),
        solver_id="dummy",
        settings=AeroSolverSettings(timeout_sec=10, verbose=False, solver_options={}),
        output_dir=tmp_path,
        max_cases=10,
        print_progress=False,
    )

    assert result.summary["requested_n_cases"] == 3
    assert result.summary["n_success"] == 1
    assert result.summary["n_invalid_output"] == 1
    assert result.summary["n_solver_failed"] == 1
    assert result.summary["n_failed_total"] == 2
    assert result.summary["total_runtime_sec"] == 1.5