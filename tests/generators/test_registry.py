"""Tests for framework-level geometry generator registry behavior."""

from __future__ import annotations

from aeris.geometry.registry import get_geometry_generator, list_geometry_generators


def test_bwb_segmented_v1_is_registered():
    """The built-in bwb_segmented_v1 generator should be registered and discoverable."""
    generator_ids = list_geometry_generators()

    assert "bwb_segmented_v1" in generator_ids


def test_get_geometry_generator_returns_generator_instance():
    """Registry lookup should instantiate the requested generator."""
    generator = get_geometry_generator("bwb_segmented_v1")

    assert generator.generator_id == "bwb_segmented_v1"