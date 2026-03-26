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
        self.received_control_inputs = []

    def run_case(self, aero_input, output_dir):
        self.received_control_inputs.append(
            aero_input.settings.solver_options.get("control_input_deg")
        )

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
            "scalars": {
                "cl": 0.1,
                "cd": 0.01,
                "cm": 0.0,
                "l_over_d": 10.0,
                "cy": 0.0,
                "cl_roll": 0.0,
                "cn": 0.0,
                "cd_ind": None,
                "cd_ff": None,
                "span_efficiency": None,
                "x_np": None,
            },
            "stability_axis_derivatives": {},
            "body_axis_derivatives": {},
            "derived_metrics": {},
            "runtime_sec": 0.5,
            "warnings": [],
            "artifact_paths": {},
            "solver_metadata": {
                "control_input_deg": aero_input.settings.solver_options.get("control_input_deg")
            },
            "failure": None
            if result.failure is None
            else {
                "status": result.failure.status.value,
                "reason": result.failure.reason,
                "message": result.failure.message,
                "exception_type": result.failure.exception_type,
            },
        }

        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "aero_result.json").write_text(json.dumps(payload), encoding="utf-8")
        return result


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


def test_run_aero_sweep_propagates_case_specific_control_input(monkeypatch, tmp_path: Path):
    dummy_solver = DummySolver(
        statuses=[AeroStatus.SUCCESS, AeroStatus.SUCCESS, AeroStatus.SUCCESS]
    )
    monkeypatch.setattr(
        "aeris.aero.sweep_run.create_solver",
        lambda solver_id: dummy_solver,
    )

    geometry = AeroGeometryView(
        view_id="geom",
        airplane=object(),
        source_generator="dummy",
        has_control_surfaces=True,
        control_surface_names=("elevon",),
    )

    settings = AeroSolverSettings(
        solver_options={"control_input_deg": None},
    )

    sweep = FlightConditionSweep(
        control_input_deg_values=[-5.0, 0.0, 5.0],
    )

    result = run_aero_sweep(
        geometry=geometry,
        base_flight_condition=_base_fc(),
        sweep=sweep,
        solver_id="dummy",
        settings=settings,
        output_dir=tmp_path,
        provenance={},
        print_progress=False,
    )

    assert len(result.cases) == 3
    assert dummy_solver.received_control_inputs == [-5.0, 0.0, 5.0]
    assert [case["control_input_deg"] for case in result.cases] == [-5.0, 0.0, 5.0]
    assert result.summary["control_input_deg_values"] == [-5.0, 0.0, 5.0]