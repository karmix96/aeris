"""Tests for audit-style validators in bwb_segmented_v1.validators."""

from __future__ import annotations

import numpy as np

from aeris.generators.bwb_segmented_v1.validators import audit_geometry_result


def test_audit_geometry_result_passes_for_healthy_case(planform, section_geometry):
    """A healthy geometry should pass the audit."""
    result = audit_geometry_result(planform=planform, section_geometry=section_geometry)

    assert result.passed is True
    assert result.errors == []
    assert isinstance(result.metrics, dict)


def test_audit_geometry_result_flags_non_finite_planform(planform, section_geometry):
    """Non-finite values should produce audit errors."""
    bad_x_le = planform.x_le.copy()
    bad_x_le[0] = np.nan

    bad_planform = planform.__class__(**{**planform.__dict__, "x_le": bad_x_le})
    result = audit_geometry_result(planform=bad_planform, section_geometry=section_geometry)

    assert result.passed is False
    assert any("non-finite" in error for error in result.errors)


def test_audit_geometry_result_warns_on_section_count_mismatch(planform, section_geometry):
    """Section count mismatch should warn, not necessarily hard-fail."""
    bad_planform = planform.__class__(**{**planform.__dict__, "num_sections": planform.num_sections + 1})
    result = audit_geometry_result(planform=bad_planform, section_geometry=section_geometry)

    assert any("section count mismatch" in warning for warning in result.warnings)


def test_audit_geometry_result_flags_near_zero_section_chord(planform, section_geometry):
    """Near-zero section chord should hard-fail the audit."""
    first = section_geometry.sections[0]
    bad_first = first.__class__(
        index=first.index,
        x_le_m=first.x_le_m,
        y_m=first.y_m,
        z_le_m=first.z_le_m,
        chord_m=0.0,
        twist_deg=first.twist_deg,
        dihedral_deg=first.dihedral_deg,
        airfoil_name=first.airfoil_name,
    )
    bad_sections = [bad_first, *section_geometry.sections[1:]]
    bad_section_geometry = section_geometry.__class__(**{**section_geometry.__dict__, "sections": bad_sections})

    result = audit_geometry_result(planform=planform, section_geometry=bad_section_geometry)

    assert result.passed is False
    assert any("section chord" in error.lower() for error in result.errors)