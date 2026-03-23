"""Tests for section geometry realization in bwb_segmented_v1.sections."""

from __future__ import annotations

import numpy as np


def test_build_section_geometry_matches_planform_num_sections(section_geometry, planform):
    """Section count should match the discretized planform section count."""
    assert len(section_geometry.sections) == planform.num_sections
    assert section_geometry.twist_array_deg.size == planform.num_sections
    assert section_geometry.dihedral_array_deg.size == planform.num_sections


def test_build_section_geometry_has_monotonic_spanwise_stations(section_geometry):
    """Section spanwise stations should be monotonically increasing."""
    ys = np.array([section.y_m for section in section_geometry.sections], dtype=float)
    assert np.all(np.diff(ys) >= 0.0)


def test_build_section_geometry_has_positive_chords(section_geometry):
    """All section chords should be positive."""
    chords = np.array([section.chord_m for section in section_geometry.sections], dtype=float)
    assert np.all(chords > 0.0)


def test_build_section_geometry_uses_config_root_dihedral(section_geometry, config):
    """Root dihedral should come from fixed config, not the sampled design."""
    assert section_geometry.dihedral_b0_deg == config.section_bounds.dihedral_root_deg


def test_build_section_geometry_propagates_boundary_arrays(section_geometry):
    """Boundary arrays should have the expected 4-value group representation."""
    assert section_geometry.twist_boundaries_deg.shape == (4,)
    assert section_geometry.dihedral_boundaries_deg.shape == (4,)
    assert section_geometry.group_boundary_y.shape == (4,)