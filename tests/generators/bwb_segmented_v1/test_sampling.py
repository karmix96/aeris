"""Tests for sampling in bwb_segmented_v1.sampling."""

from __future__ import annotations

import numpy as np

from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design


def test_sample_bwb_design_stays_within_bounds(config):
    """Sampled design variables should stay within configured bounds."""
    rng = np.random.default_rng(7)
    sample = sample_bwb_design(config, rng)

    pb = config.planform_bounds
    sb = config.section_bounds

    assert pb.c1_m.min <= sample.c1_m <= pb.c1_m.max
    assert pb.c2_ratio.min <= sample.c2_ratio <= pb.c2_ratio.max
    assert pb.c3_ratio.min <= sample.c3_ratio <= pb.c3_ratio.max
    assert pb.c4_ratio.min <= sample.c4_ratio <= pb.c4_ratio.max
    assert pb.b_total_m.min <= sample.b_total_m <= pb.b_total_m.max
    assert pb.b3_ratio.min <= sample.b3_ratio <= pb.b3_ratio.max
    assert pb.split_ratio.min <= sample.split_ratio <= pb.split_ratio.max

    assert -pb.sw1_deg.max <= sample.sw1_deg <= -pb.sw1_deg.min
    assert -pb.sw2_deg.max <= sample.sw2_deg <= -pb.sw2_deg.min
    assert -pb.sw3_deg.max <= sample.sw3_deg <= -pb.sw3_deg.min

    assert sb.twist_b0_deg.min <= sample.twist_b0_deg <= sb.twist_b0_deg.max
    assert sb.twist_b1_deg.min <= sample.twist_b1_deg <= sb.twist_b1_deg.max
    assert sb.twist_b2_deg.min <= sample.twist_b2_deg <= sb.twist_b2_deg.max
    assert sb.twist_b3_deg.min <= sample.twist_b3_deg <= sb.twist_b3_deg.max
    assert sb.dihedral_b1_deg.min <= sample.dihedral_b1_deg <= sb.dihedral_b1_deg.max
    assert sb.dihedral_b2_deg.min <= sample.dihedral_b2_deg <= sb.dihedral_b2_deg.max
    assert sb.dihedral_b3_deg.min <= sample.dihedral_b3_deg <= sb.dihedral_b3_deg.max


def test_sample_bwb_design_is_deterministic_for_same_seed(config):
    """Using the same RNG seed should reproduce the same sampled design."""
    rng1 = np.random.default_rng(99)
    rng2 = np.random.default_rng(99)

    s1 = sample_bwb_design(config, rng1)
    s2 = sample_bwb_design(config, rng2)

    assert s1 == s2


def test_sample_bwb_design_uses_negative_internal_sweep_convention(config):
    """Internal sweep convention should store aft sweep as negative degrees."""
    rng = np.random.default_rng(1234)
    sample = sample_bwb_design(config, rng)

    assert sample.sw1_deg <= 0.0
    assert sample.sw2_deg <= 0.0
    assert sample.sw3_deg <= 0.0