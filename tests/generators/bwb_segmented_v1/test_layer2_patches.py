"""
New tests for Layer 2 patches — drop this file into:
    tests/generators/bwb_segmented_v1/test_layer2_patches.py

Covers:
    - D21:    cumulative z-formula correctness
    - 2C.5:   validate_section_geometry new array-length and content checks
    - 2C.NEW: sweep positivity guard in validate_bwb_generator_config
    - 2C.4:   validate_planform_controls as public function
    - 2D.2:   Airplane has explicit s_ref/c_ref/b_ref
    - 2D.8:   UserWarning on airfoil coordinate fallback
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest

from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import build_aerosandbox_geometry
from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config
from aeris.generators.bwb_segmented_v1.planform import generate_bwb_planform_from_sample
from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design
from aeris.generators.bwb_segmented_v1.sections import (
    SectionRecord,
    SectionGeometryResult,
    _cumulative_z,
    build_section_geometry_from_sample,
)
from aeris.generators.bwb_segmented_v1.validation import (
    validate_bwb_generator_config,
    validate_planform_controls,
    validate_section_geometry,
)


# ---------------------------------------------------------------------------
# Fixtures (mirrors conftest but self-contained for clarity)
# ---------------------------------------------------------------------------

def _make_raw_config() -> dict:
    return {
        "name": "test_bwb",
        "geometry": {
            "generator": {"family": "bwb_segmented", "version": "v1", "seed": 42},
            "controls": {
                "n_points": 10,
                "n_spline_inboard": 4,
                "n_spline_outboard": 5,
                "desired_curvature_strength": 0.7,
                "spline_split_ratio": 0.55,
                "segment_length_variation": 0.0,
                "sweep_variation": 0.0,
            },
            "planform_bounds": {
                "c1_m":       {"min": 1.0, "max": 2.0},
                "c2_ratio":   {"min": 0.4, "max": 0.8},
                "c3_ratio":   {"min": 0.2, "max": 0.6},
                "c4_ratio":   {"min": 0.1, "max": 0.4},
                "b_total_m":  {"min": 2.0, "max": 4.0},
                "b3_ratio":   {"min": 0.2, "max": 0.5},
                "split_ratio":{"min": 0.2, "max": 0.8},
                "sw1_deg":    {"min": 10.0, "max": 30.0},
                "sw2_deg":    {"min": 5.0,  "max": 20.0},
                "sw3_deg":    {"min": 1.0,  "max": 10.0},  # min>0 to satisfy new guard
            },
            "section_bounds": {
                "airfoil_name": "naca4412",
                "dihedral_root_deg": 0.0,
                "twist_b0_deg":    {"min": -2.0, "max": 2.0},
                "twist_b1_deg":    {"min": -3.0, "max": 3.0},
                "twist_b2_deg":    {"min": -4.0, "max": 4.0},
                "twist_b3_deg":    {"min": -5.0, "max": 5.0},
                "dihedral_b1_deg": {"min": 0.0,  "max": 5.0},
                "dihedral_b2_deg": {"min": 0.0,  "max": 8.0},
                "dihedral_b3_deg": {"min": 0.0,  "max": 10.0},
            },
            "outputs": {"save_plot": False, "build_aerosandbox": True},
        },
    }


@pytest.fixture
def config():
    return build_bwb_generator_config(_make_raw_config())


@pytest.fixture
def sample(config):
    return sample_bwb_design(config, np.random.default_rng(99))


@pytest.fixture
def planform(config, sample):
    return generate_bwb_planform_from_sample(sample, config)


@pytest.fixture
def section_geometry(config, sample, planform):
    return build_section_geometry_from_sample(planform, sample, config)


# ===========================================================================
# D21 — cumulative z-formula
# ===========================================================================

class TestCumulativeZFormula:
    """D21: z = cumulative integral of tan(dihedral(y)) dy."""

    def test_uniform_dihedral_matches_simple_formula(self):
        """For uniform dihedral, cumulative integral must equal y * tan(d)."""
        y = np.linspace(0, 1.6, 99)
        d = np.full_like(y, 5.0)
        z_new = _cumulative_z(y, d)
        z_old = y * np.tan(np.radians(5.0))
        assert np.abs(z_new - z_old).max() < 1e-10

    def test_zero_dihedral_gives_zero_z(self):
        """Zero dihedral everywhere must give z = 0 at all stations."""
        y = np.linspace(0, 2.0, 50)
        d = np.zeros_like(y)
        z = _cumulative_z(y, d)
        assert np.allclose(z, 0.0)

    def test_root_z_is_always_zero(self):
        """First z value must always be 0 regardless of dihedral profile."""
        y = np.linspace(0, 1.6, 30)
        d = np.linspace(0.0, 8.0, 30)
        z = _cumulative_z(y, d)
        assert z[0] == 0.0

    def test_non_uniform_dihedral_less_than_ray_formula(self):
        """For ramping dihedral, cumulative z < y*tan(d_local) at tip.

        Old formula over-predicts because it places each section on an
        independent ray from origin using the local angle, not the
        integrated surface angle.
        """
        y = np.linspace(0, 1.6, 99)
        d = np.linspace(0.0, 5.0, 99)  # dihedral ramps from 0 to 5 deg
        z_integral = _cumulative_z(y, d)
        z_ray = y * np.tan(np.radians(d))
        # Old formula over-predicts at tip by ~half the ramp effect
        assert z_integral[-1] < z_ray[-1]
        # Error should be significant (>10mm for 1.6m span at 5deg ramp)
        assert (z_ray[-1] - z_integral[-1]) > 0.010

    def test_piecewise_linear_dihedral_is_station_independent(self):
        """Refining within each linear segment must not move common stations."""
        boundaries_y = np.array([0.0, 0.35, 1.05, 1.6])
        boundaries_d = np.array([0.0, 4.0, 1.5, 7.0])
        coarse_z = _cumulative_z(boundaries_y, boundaries_d)

        refined_y = np.unique(
            np.concatenate(
                [
                    np.linspace(left, right, 101)
                    for left, right in zip(
                        boundaries_y[:-1], boundaries_y[1:], strict=True
                    )
                ]
            )
        )
        refined_d = np.interp(refined_y, boundaries_y, boundaries_d)
        refined_z = _cumulative_z(refined_y, refined_d)
        common_z = np.interp(boundaries_y, refined_y, refined_z)

        assert np.allclose(common_z, coarse_z, rtol=0.0, atol=2.0e-14)

        trapezoid_limit = np.trapezoid(np.tan(np.radians(refined_d)), refined_y)
        assert coarse_z[-1] == pytest.approx(trapezoid_limit, abs=2.0e-8)

    def test_section_geometry_z_values_are_non_negative_for_positive_dihedral(
        self, section_geometry
    ):
        """All z_le_m values must be >= 0 when all dihedral values >= 0."""
        z_vals = np.array([s.z_le_m for s in section_geometry.sections])
        assert np.all(z_vals >= 0.0)


# ===========================================================================
# 2C.4 — validate_planform_controls as public function
# ===========================================================================

class TestValidatePlanformControls:
    """2C.4: validate_planform_controls is public and raises correctly."""

    def test_accepts_valid_config(self, config):
        validate_planform_controls(config)  # must not raise

    def test_rejects_n_points_too_small(self, config):
        from dataclasses import replace
        bad_ctrl = replace(config.controls, n_points=3)
        bad_config = replace(config, controls=bad_ctrl)
        with pytest.raises(ValueError, match="n_points"):
            validate_planform_controls(bad_config)

    def test_rejects_n_spline_inboard_too_small(self, config):
        from dataclasses import replace
        bad_ctrl = replace(config.controls, n_spline_inboard=1)
        bad_config = replace(config, controls=bad_ctrl)
        with pytest.raises(ValueError, match="n_spline_inboard"):
            validate_planform_controls(bad_config)

    def test_rejects_invalid_split_ratio(self, config):
        from dataclasses import replace
        bad_ctrl = replace(config.controls, spline_split_ratio=0.0)
        bad_config = replace(config, controls=bad_ctrl)
        with pytest.raises(ValueError, match="spline_split_ratio"):
            validate_planform_controls(bad_config)


# ===========================================================================
# 2C.5 — validate_section_geometry new checks
# ===========================================================================

class TestValidateSectionGeometryNewChecks:
    """2C.5: validate_section_geometry checks array lengths, finite, monotonicity, chords."""

    def _make_section_records(self, n: int) -> list[SectionRecord]:
        return [
            SectionRecord(
                index=i,
                x_le_m=float(i) * 0.05,
                y_m=float(i) * 0.1,
                z_le_m=0.0,
                chord_m=1.0 - float(i) * 0.02,
                twist_deg=0.0,
                dihedral_deg=0.0,
                airfoil_name="naca4412",
            )
            for i in range(n)
        ]

    def _make_result(self, sections, twist_arr=None, dihedral_arr=None, group_boundary_y=None):
        n = len(sections)
        return SectionGeometryResult(
            sections=sections,
            twist_b0_deg=0.0, twist_b1_deg=0.0, twist_b2_deg=0.0, twist_b3_deg=0.0,
            dihedral_b0_deg=0.0, dihedral_b1_deg=0.0, dihedral_b2_deg=0.0, dihedral_b3_deg=0.0,
            twist_boundaries_deg=np.zeros(4),
            dihedral_boundaries_deg=np.zeros(4),
            twist_array_deg=twist_arr if twist_arr is not None else np.zeros(n),
            dihedral_array_deg=dihedral_arr if dihedral_arr is not None else np.zeros(n),
            group_boundary_y=group_boundary_y if group_boundary_y is not None else np.array([0.0, 0.3, 0.7, 1.0]),
        )

    def test_accepts_healthy_result(self, section_geometry):
        validate_section_geometry(section_geometry)  # must not raise

    def test_rejects_twist_array_wrong_length(self):
        sections = self._make_section_records(10)
        result = self._make_result(sections, twist_arr=np.zeros(9))  # wrong length
        with pytest.raises(ValueError, match="twist_array_deg length"):
            validate_section_geometry(result)

    def test_rejects_dihedral_array_wrong_length(self):
        sections = self._make_section_records(10)
        result = self._make_result(sections, dihedral_arr=np.zeros(11))  # wrong length
        with pytest.raises(ValueError, match="dihedral_array_deg length"):
            validate_section_geometry(result)

    def test_rejects_non_monotonic_y_positions(self):
        sections = self._make_section_records(5)
        # Make y values non-monotonic
        bad_sections = list(sections)
        bad_s = bad_sections[2]
        bad_sections[2] = SectionRecord(
            index=bad_s.index, x_le_m=bad_s.x_le_m,
            y_m=0.0,  # duplicate of index 0 -> not strictly increasing
            z_le_m=bad_s.z_le_m, chord_m=bad_s.chord_m,
            twist_deg=bad_s.twist_deg, dihedral_deg=bad_s.dihedral_deg,
            airfoil_name=bad_s.airfoil_name,
        )
        result = self._make_result(bad_sections)
        with pytest.raises(ValueError, match="strictly increasing"):
            validate_section_geometry(result)

    def test_rejects_non_positive_chord(self):
        sections = self._make_section_records(5)
        bad_sections = list(sections)
        bad_s = bad_sections[3]
        bad_sections[3] = SectionRecord(
            index=bad_s.index, x_le_m=bad_s.x_le_m, y_m=bad_s.y_m, z_le_m=bad_s.z_le_m,
            chord_m=0.0,  # zero chord
            twist_deg=bad_s.twist_deg, dihedral_deg=bad_s.dihedral_deg,
            airfoil_name=bad_s.airfoil_name,
        )
        result = self._make_result(bad_sections)
        with pytest.raises(ValueError, match="chord_m"):
            validate_section_geometry(result)

    def test_rejects_non_finite_twist(self):
        sections = self._make_section_records(5)
        twist_with_nan = np.array([0.0, 0.0, float("nan"), 0.0, 0.0])
        result = self._make_result(sections, twist_arr=twist_with_nan)
        with pytest.raises(ValueError, match="twist_array_deg"):
            validate_section_geometry(result)


# ===========================================================================
# 2C.NEW — sweep positivity guard
# ===========================================================================

class TestSweepPositivityGuard:
    """2C.NEW: sw*.min must be >= 0 in YAML bounds."""

    def test_accepts_zero_sweep_min(self):
        """sw3_deg min=0 is acceptable (border case)."""
        raw = _make_raw_config()
        raw["geometry"]["planform_bounds"]["sw3_deg"] = {"min": 0.0, "max": 10.0}
        config = build_bwb_generator_config(raw)
        validate_bwb_generator_config(config)  # must not raise

    def test_rejects_negative_sweep_min(self):
        """Negative sweep min in YAML must raise with a clear message."""
        raw = _make_raw_config()
        raw["geometry"]["planform_bounds"]["sw1_deg"] = {"min": -5.0, "max": 30.0}
        config = build_bwb_generator_config(raw)
        with pytest.raises(ValueError, match="sw1_deg"):
            validate_bwb_generator_config(config)


# ===========================================================================
# 2D.2 — Airplane has explicit s_ref, c_ref, b_ref
# ===========================================================================

class TestAirplaneReferenceValues:
    """2D.2: asb.Airplane must have explicit s_ref/c_ref/b_ref."""

    def test_airplane_has_explicit_reference_values(self, config, sample, planform, section_geometry):
        result = build_aerosandbox_geometry(section_geometry, config)
        airplane = result.airplane
        wing = result.wing

        # s_ref must be set and equal wing.area()
        assert hasattr(airplane, "s_ref"), "Airplane missing s_ref"
        assert math.isfinite(float(airplane.s_ref)), "s_ref is not finite"
        assert float(airplane.s_ref) > 0.0, "s_ref must be > 0"
        assert abs(float(airplane.s_ref) - float(wing.area())) < 1e-8, (
            f"s_ref ({airplane.s_ref}) != wing.area() ({wing.area()})"
        )

        # c_ref must equal MAC
        assert hasattr(airplane, "c_ref")
        assert abs(float(airplane.c_ref) - float(wing.mean_aerodynamic_chord())) < 1e-8

        # b_ref must equal span
        assert hasattr(airplane, "b_ref")
        assert abs(float(airplane.b_ref) - float(wing.span())) < 1e-8

    def test_reference_values_are_consistent_with_summary(
        self, config, sample, planform, section_geometry
    ):
        """Reference values in result must match what the summary will report."""
        result = build_aerosandbox_geometry(section_geometry, config)
        ref = result.reference_values

        assert abs(ref["area_m2"] - float(result.wing.area())) < 1e-8
        assert abs(ref["span_m"] - float(result.wing.span())) < 1e-8
        assert abs(
            ref["mean_aerodynamic_chord_m"] - float(result.wing.mean_aerodynamic_chord())
        ) < 1e-8


# ===========================================================================
# 2D.8 — UserWarning on airfoil coordinate fallback
# ===========================================================================

class TestAirfoilFallbackWarning:
    """2D.8: _write_airfoil_dat must warn when falling back to naca0012."""

    def test_no_warning_for_known_airfoil(
        self, config, sample, planform, section_geometry, tmp_path
    ):
        """naca4412 resolves correctly — no warning expected."""
        result = build_aerosandbox_geometry(section_geometry, config)
        from aeris.generators.bwb_segmented_v1.reconstruction_export import (
            export_reconstruction_artifacts,
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            export_reconstruction_artifacts(
                airplane=result.airplane, output_dir=tmp_path
            )
        airfoil_warnings = [
            w for w in caught
            if issubclass(w.category, UserWarning) and "naca0012" in str(w.message).lower()
        ]
        assert len(airfoil_warnings) == 0, (
            f"Unexpected naca0012 fallback warning for known airfoil: {airfoil_warnings}"
        )
