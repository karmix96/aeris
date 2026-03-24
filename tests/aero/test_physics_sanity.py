from __future__ import annotations

import math
from pathlib import Path

import pytest

from aeris.aero.models import (
    AeroGeometryView,
    AeroInput,
    AeroSolverSettings,
    AeroStatus,
    FlightCondition,
)
from aeris.aero.solvers.aerosandbox_avl import AeroSandboxAVLSolver
from aeris.aero.views import build_asb_airplane_from_paths


BASELINE_CASE_DIR = Path("data/debug/aero_validation_campaign/baseline_geometry_case")
CSV_PATH = BASELINE_CASE_DIR / "airfoils" / "openvsp_sections.csv"
AIRFOIL_DIR = BASELINE_CASE_DIR / "airfoils" / "xfoil"

pytestmark = [pytest.mark.integration, pytest.mark.avl]

if not CSV_PATH.exists():
    pytest.skip(f"Missing reconstruction CSV: {CSV_PATH}", allow_module_level=True)
if not AIRFOIL_DIR.exists():
    pytest.skip(f"Missing reconstructed airfoil dir: {AIRFOIL_DIR}", allow_module_level=True)


def _build_airplane():
    return build_asb_airplane_from_paths(
        csv_path=CSV_PATH,
        airfoil_dir=AIRFOIL_DIR,
    )


def _run(alpha_deg: float, output_dir: Path):
    airplane = _build_airplane()

    geometry = AeroGeometryView(
        view_id="physics_sanity_baseline",
        airplane=airplane,
        source_generator="reconstructed_test_case",
    )

    aero_input = AeroInput(
        geometry=geometry,
        flight_condition=FlightCondition(
            alpha_deg=alpha_deg,
            beta_deg=0.0,
            mach=None,
            velocity_mps=28.0,
            altitude_m=1500.0,
            p_rad_s=0.0,
            q_rad_s=0.0,
            r_rad_s=0.0,
        ),
        settings=AeroSolverSettings(
            timeout_sec=30,
            verbose=False,
            solver_options={"avl_command": "avl"},
        ),
    )

    solver = AeroSandboxAVLSolver()
    return solver.run_case(aero_input=aero_input, output_dir=output_dir)


def test_baseline_outputs_are_finite(tmp_path: Path) -> None:
    result = _run(alpha_deg=2.0, output_dir=tmp_path / "case_alpha_2")

    assert result.status == AeroStatus.SUCCESS

    for value in [result.cl, result.cd, result.cm]:
        assert value is not None
        assert math.isfinite(value)

    if result.l_over_d is not None:
        assert math.isfinite(result.l_over_d)


def test_drag_is_positive(tmp_path: Path) -> None:
    result = _run(alpha_deg=2.0, output_dir=tmp_path / "case_drag")

    assert result.status == AeroStatus.SUCCESS
    assert result.cd > 0.0

    if result.cd_ind is not None:
        assert result.cd_ind >= 0.0

    if result.span_efficiency is not None:
        assert result.span_efficiency > 0.0
        assert result.span_efficiency <= 1.5


def test_cl_increases_with_alpha_in_small_angle_range(tmp_path: Path) -> None:
    result_0 = _run(alpha_deg=0.0, output_dir=tmp_path / "case_alpha_0")
    result_4 = _run(alpha_deg=4.0, output_dir=tmp_path / "case_alpha_4")

    assert result_0.status == AeroStatus.SUCCESS
    assert result_4.status == AeroStatus.SUCCESS

    assert result_4.cl > result_0.cl


def test_symmetric_condition_has_small_lateral_coefficients(tmp_path: Path) -> None:
    result = _run(alpha_deg=2.0, output_dir=tmp_path / "case_symmetry")

    assert result.status == AeroStatus.SUCCESS

    if result.cy is not None:
        assert abs(result.cy) < 0.05
    if result.cl_roll is not None:
        assert abs(result.cl_roll) < 0.05
    if result.cn is not None:
        assert abs(result.cn) < 0.05


def test_repeat_run_is_reproducible(tmp_path: Path) -> None:
    result_a = _run(alpha_deg=2.0, output_dir=tmp_path / "case_repeat_a")
    result_b = _run(alpha_deg=2.0, output_dir=tmp_path / "case_repeat_b")

    assert result_a.status == AeroStatus.SUCCESS
    assert result_b.status == AeroStatus.SUCCESS

    assert result_a.cl == pytest.approx(result_b.cl, rel=1e-8, abs=1e-10)
    assert result_a.cd == pytest.approx(result_b.cd, rel=1e-8, abs=1e-10)
    assert result_a.cm == pytest.approx(result_b.cm, rel=1e-8, abs=1e-10)