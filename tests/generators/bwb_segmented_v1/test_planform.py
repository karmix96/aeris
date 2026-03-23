"""Tests for deterministic planform generation in bwb_segmented_v1.planform."""

import numpy as np

from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config
from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design
from aeris.generators.bwb_segmented_v1.planform import generate_bwb_planform_from_sample


def make_config():
    from tests.generators.bwb_segmented_v1.test_params import make_raw_config
    return build_bwb_generator_config(make_raw_config())


def test_generate_bwb_planform_from_sample_is_deterministic():
    config = make_config()
    rng = np.random.default_rng(42)
    sample = sample_bwb_design(config, rng)

    p1 = generate_bwb_planform_from_sample(sample, config)
    p2 = generate_bwb_planform_from_sample(sample, config)

    assert np.allclose(p1.x_le, p2.x_le)
    assert np.allclose(p1.y_le, p2.y_le)
    assert np.allclose(p1.front_x_fine, p2.front_x_fine)
    assert np.allclose(p1.rear_x_fine, p2.rear_x_fine)
    assert p1.full_span_m == p2.full_span_m
    assert p1.approx_area_m2 == p2.approx_area_m2


def test_generate_bwb_planform_from_sample_produces_positive_geometry():
    config = make_config()
    rng = np.random.default_rng(1)
    sample = sample_bwb_design(config, rng)
    planform = generate_bwb_planform_from_sample(sample, config)

    assert planform.full_span_m > 0.0
    assert planform.approx_area_m2 > 0.0
    assert planform.approx_aspect_ratio > 0.0
    assert planform.N1 + planform.N2 + planform.N3 == planform.n_points - 1