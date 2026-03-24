from pathlib import Path

import pytest
from aerosandbox.aerodynamics.aero_3D.avl import AVL as AVLBase
from aerosandbox.geometry import Wing, WingXSec

from aeris.aero.models import AeroGeometryView, AeroInput, AeroSolverSettings, FlightCondition, AeroStatus
from aeris.aero.solvers.aerosandbox_avl import (
    _mach_consistency_warning,
    _resolve_avl_command,
    _validate_solver_airplane,
    avl_paneling_context,
    _compute_derived_metrics,
    AeroSandboxAVLSolver,
)


class DummyAirplane:
    def __init__(self, s_ref=10.0, b_ref=5.0, c_ref=2.0):
        self.s_ref = s_ref
        self.b_ref = b_ref
        self.c_ref = c_ref
        self.wings = [object()]


def test_validate_solver_airplane_catches_bad_refs():
    airplane = DummyAirplane(s_ref=0.0, b_ref=-1.0, c_ref=0.0)
    errors = _validate_solver_airplane(airplane)
    assert any("s_ref" in e for e in errors)
    assert any("b_ref" in e for e in errors)
    assert any("c_ref" in e for e in errors)


def test_resolve_avl_command_raises_when_missing(monkeypatch):
    monkeypatch.setattr("aeris.aero.solvers.aerosandbox_avl.shutil.which", lambda _: None)
    with pytest.raises(FileNotFoundError):
        _resolve_avl_command(None)


def test_mach_consistency_warning_flags_mismatch():
    fc = FlightCondition(
        alpha_deg=0.0,
        beta_deg=0.0,
        mach=0.9,
        velocity_mps=50.0,
        altitude_m=0.0,
        p_rad_s=0.0,
        q_rad_s=0.0,
        r_rad_s=0.0,
    )
    warning = _mach_consistency_warning(fc)
    assert warning is not None
    assert "Mach/velocity inconsistency" in warning


def test_compute_derived_metrics_handles_zero_division():
    metrics = _compute_derived_metrics(
        {"Clb": 1.0, "Cnr": 1.0, "Clr": 0.0, "Cnb": 1.0}
    )
    assert metrics["spiral_metric"] is None


import copy

def test_avl_paneling_context_restores_global_defaults():
    original = copy.deepcopy(AVLBase.default_analysis_specific_options)
    airplane = DummyAirplane()

    with avl_paneling_context(airplane, {"spanwise_resolution": 7, "chordwise_resolution": 9}):
        assert AVLBase.default_analysis_specific_options[WingXSec]["spanwise_resolution"] == 7
        assert AVLBase.default_analysis_specific_options[Wing]["chordwise_resolution"] == 9

    assert AVLBase.default_analysis_specific_options == original


def test_solver_returns_invalid_input_for_bad_geometry(tmp_path: Path):
    solver = AeroSandboxAVLSolver()
    geometry = AeroGeometryView(
        view_id="test",
        airplane=DummyAirplane(s_ref=0.0),
        source_generator="unit",
    )
    aero_input = AeroInput(
        geometry=geometry,
        flight_condition=FlightCondition(
            alpha_deg=0.0,
            beta_deg=0.0,
            mach=None,
            velocity_mps=30.0,
            altitude_m=0.0,
            p_rad_s=0.0,
            q_rad_s=0.0,
            r_rad_s=0.0,
        ),
        settings=AeroSolverSettings(timeout_sec=10, verbose=False, solver_options={}),
    )
    result = solver.run_case(aero_input=aero_input, output_dir=tmp_path)
    assert result.status == AeroStatus.INVALID_INPUT
    assert result.failure is not None