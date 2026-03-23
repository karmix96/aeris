"""Tests for AeroSandbox conversion in bwb_segmented_v1.aerosandbox_adapter."""

from __future__ import annotations

import math

from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import build_aerosandbox_geometry


def test_build_aerosandbox_geometry_returns_expected_structure(section_geometry, config):
    """AeroSandbox adapter should build finite metadata and matching section count."""
    result = build_aerosandbox_geometry(section_geometry, config)

    assert result.n_xsecs == len(section_geometry.sections)
    assert result.airfoil_name == config.section_bounds.airfoil_name
    assert result.wing is not None
    assert result.airplane is not None

    assert "area_m2" in result.reference_values
    assert "mean_aerodynamic_chord_m" in result.reference_values
    assert "twist_deg" in result.mean_angles_deg
    assert "x_m" in result.aerodynamic_center

    assert math.isfinite(result.reference_values["area_m2"])
    assert result.reference_values["area_m2"] > 0.0