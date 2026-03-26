from pathlib import Path

import pytest
from aerosandbox.aerodynamics.aero_3D.avl import AVL as AVLBase
from aerosandbox.geometry import Wing, WingXSec

from aeris.aero.models import AeroGeometryView, AeroInput, AeroSolverSettings, FlightCondition, AeroStatus
from aeris.aero.solvers.aerosandbox_avl import (
    _airplane_has_any_control_surface,
    _compute_derived_metrics,
    _mach_consistency_warning,
    _resolve_avl_command,
    _resolve_control_input_deg,
    _validate_solver_airplane,
    avl_paneling_context,
    AVLStrips,
    AeroSandboxAVLSolver,
)

class DummyXSec:
    def __init__(self, control_surfaces=None):
        self.control_surfaces = control_surfaces or []


class DummyWing:
    def __init__(self, xsecs):
        self.xsecs = xsecs


class DummyControlAirplane:
    def __init__(self, has_control: bool):
        self.s_ref = 10.0
        self.b_ref = 5.0
        self.c_ref = 2.0
        xsec = DummyXSec(control_surfaces=[object()] if has_control else [])
        self.wings = [DummyWing([xsec])]


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

def test_airplane_has_any_control_surface_false():
    airplane = DummyControlAirplane(has_control=False)
    assert _airplane_has_any_control_surface(airplane) is False


def test_airplane_has_any_control_surface_true():
    airplane = DummyControlAirplane(has_control=True)
    assert _airplane_has_any_control_surface(airplane) is True

def test_resolve_control_input_deg_none():
    settings = AeroSolverSettings(
        avl_command="avl",
        timeout_sec=10,
        verbose=False,
        solver_options={},
    )
    assert _resolve_control_input_deg(settings) is None


def test_resolve_control_input_deg_float():
    settings = AeroSolverSettings(
        avl_command="avl",
        timeout_sec=10,
        verbose=False,
        solver_options={"control_input_deg": 5},
    )
    assert _resolve_control_input_deg(settings) == pytest.approx(5.0)

def test_default_keystrokes_no_controls_has_no_d1():
    avl = object.__new__(AVLStrips)
    avl.airplane = DummyControlAirplane(has_control=False)

    class DummyAtmosphere:
        def density(self):
            return 1.225

    class DummyOpPoint:
        velocity = 30.0
        alpha = 2.0
        beta = 0.0
        p = 0.0
        q = 0.0
        r = 0.0
        atmosphere = DummyAtmosphere()

        def mach(self):
            return 0.1

    avl.op_point = DummyOpPoint()

    lines = avl._default_keystroke_file_contents(control_input_deg=None)
    joined = "\n".join(lines)
    assert "d1" not in joined

def test_default_keystrokes_controls_default_to_zero():
    avl = object.__new__(AVLStrips)
    avl.airplane = DummyControlAirplane(has_control=True)

    class DummyAtmosphere:
        def density(self):
            return 1.225

    class DummyOpPoint:
        velocity = 30.0
        alpha = 2.0
        beta = 0.0
        p = 0.0
        q = 0.0
        r = 0.0
        atmosphere = DummyAtmosphere()

        def mach(self):
            return 0.1

    avl.op_point = DummyOpPoint()

    lines = avl._default_keystroke_file_contents(control_input_deg=None)
    assert lines[-3:] == ["d1", "d1", "0.0"]

def test_default_keystrokes_controls_use_explicit_value():
    avl = object.__new__(AVLStrips)
    avl.airplane = DummyControlAirplane(has_control=True)

    class DummyAtmosphere:
        def density(self):
            return 1.225

    class DummyOpPoint:
        velocity = 30.0
        alpha = 2.0
        beta = 0.0
        p = 0.0
        q = 0.0
        r = 0.0
        atmosphere = DummyAtmosphere()

        def mach(self):
            return 0.1

    avl.op_point = DummyOpPoint()

    lines = avl._default_keystroke_file_contents(control_input_deg=5.0)
    assert lines[-3:] == ["d1", "d1", "5.0"]

def test_solver_passes_control_input_deg_into_avl_run(monkeypatch, tmp_path):
    class DummyGeometryAirplane(DummyControlAirplane):
        pass

    airplane = DummyGeometryAirplane(has_control=True)
    geometry = AeroGeometryView(
        view_id="geom_00001",
        airplane=airplane,
        source_generator="dummy",
    )

    flight_condition = FlightCondition(
        alpha_deg=2.0,
        beta_deg=0.0,
        mach=None,
        velocity_mps=30.0,
        altitude_m=0.0,
        p_rad_s=0.0,
        q_rad_s=0.0,
        r_rad_s=0.0,
    )

    settings = AeroSolverSettings(
        avl_command="avl",
        timeout_sec=10,
        verbose=False,
        solver_options={
            "paneling": {"spanwise_resolution": 4, "chordwise_resolution": 8},
            "save_surface_forces": False,
            "save_element_forces": False,
            "control_input_deg": 5.0,
        },
    )

    aero_input = AeroInput(
        geometry=geometry,
        flight_condition=flight_condition,
        settings=settings,
        case_id="case_001",
        provenance={},
    )

    monkeypatch.setattr(
        "aeris.aero.solvers.aerosandbox_avl.validate_aero_input",
        lambda _: [],
    )
    monkeypatch.setattr(
        "aeris.aero.solvers.aerosandbox_avl._validate_solver_airplane",
        lambda _: [],
    )
    monkeypatch.setattr(
        "aeris.aero.solvers.aerosandbox_avl._resolve_avl_command",
        lambda _: "avl",
    )

    captured = {}

    class DummyAVL:
        def __init__(self, **kwargs):
            captured["init_kwargs"] = kwargs

        def run(self, **kwargs):
            captured["run_kwargs"] = kwargs
            return {
                "CL": 0.5,
                "CD": 0.02,
                "Cm": -0.1,
                "CY": 0.0,
                "Cl": 0.0,
                "Cn": 0.0,
                "e": 0.9,
                "_files": {},
            }

    monkeypatch.setattr("aeris.aero.solvers.aerosandbox_avl.AVLStrips", DummyAVL)

    solver = AeroSandboxAVLSolver()
    result = solver.run_case(aero_input=aero_input, output_dir=tmp_path)

    assert result.status == AeroStatus.SUCCESS
    assert captured["run_kwargs"]["control_input_deg"] == pytest.approx(5.0)
    assert result.solver_metadata["control_input_deg"] == pytest.approx(5.0)