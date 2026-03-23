"""Tests for hard validation in bwb_segmented_v1.validation."""

from __future__ import annotations

import pytest

from aeris.generators.bwb_segmented_v1.validation import (
    validate_bwb_generator_config,
    validate_planform_result,
    validate_section_geometry,
)


def test_validate_bwb_generator_config_accepts_valid_config(config):
    """A valid generator config should pass validation."""
    validate_bwb_generator_config(config)


def test_validate_bwb_generator_config_rejects_invalid_range_order(raw_config):
    """A min>=max range should fail validation."""
    raw_config["geometry"]["planform_bounds"]["c1_m"] = {"min": 2.0, "max": 2.0}

    from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config

    config = build_bwb_generator_config(raw_config)

    with pytest.raises(ValueError, match="c1_m"):
        validate_bwb_generator_config(config)


def test_validate_bwb_generator_config_rejects_invalid_b3_ratio(raw_config):
    """b3_ratio bounds must lie strictly within (0, 1)."""
    raw_config["geometry"]["planform_bounds"]["b3_ratio"] = {"min": -0.1, "max": 0.5}

    from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config

    config = build_bwb_generator_config(raw_config)

    with pytest.raises(ValueError, match="b3_ratio"):
        validate_bwb_generator_config(config)


def test_validate_bwb_generator_config_rejects_invalid_split_ratio(raw_config):
    """split_ratio bounds must lie strictly within (0, 1)."""
    raw_config["geometry"]["planform_bounds"]["split_ratio"] = {"min": 0.2, "max": 1.2}

    from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config

    config = build_bwb_generator_config(raw_config)

    with pytest.raises(ValueError, match="split_ratio"):
        validate_bwb_generator_config(config)


def test_validate_planform_result_rejects_non_positive_local_chord(planform):
    """Planform validation should fail if fine-section local chords are non-positive."""
    bad = planform.__class__(**{**planform.__dict__, "rear_x_fine": planform.front_x_fine.copy()})

    with pytest.raises(ValueError, match="local chords"):
        validate_planform_result(bad)


def test_validate_section_geometry_rejects_empty_sections(section_geometry):
    """Section geometry validation should fail if no sections exist."""
    bad = section_geometry.__class__(**{**section_geometry.__dict__, "sections": []})

    with pytest.raises(ValueError, match="no section records"):
        validate_section_geometry(bad)