"""Shared fixtures for bwb_segmented_v1 generator tests."""

from __future__ import annotations

import numpy as np
import pytest

from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config
from aeris.generators.bwb_segmented_v1.planform import generate_bwb_planform_from_sample
from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design
from aeris.generators.bwb_segmented_v1.sections import build_section_geometry_from_sample


def make_raw_config() -> dict:
    """Return a valid minimal raw config for bwb_segmented_v1 tests."""
    return {
        "name": "test_bwb",
        "geometry": {
            "generator": {
                "family": "bwb_segmented",
                "version": "v1",
                "seed": 42,
            },
            "controls": {
                "n_points": 10,
                "n_spline_inboard": 4,
                "n_spline_outboard": 5,
                "desired_curvature_strength": 0.7,
                "spline_split_ratio": 0.55,
                "segment_length_variation": 0.25,
                "sweep_variation": 0.10,
            },
            "planform_bounds": {
                "c1_m": {"min": 1.0, "max": 2.0},
                "c2_ratio": {"min": 0.4, "max": 0.8},
                "c3_ratio": {"min": 0.2, "max": 0.6},
                "c4_ratio": {"min": 0.1, "max": 0.4},
                "b_total_m": {"min": 2.0, "max": 4.0},
                "b3_ratio": {"min": 0.2, "max": 0.5},
                "split_ratio": {"min": 0.2, "max": 0.8},
                "sw1_deg": {"min": 10.0, "max": 30.0},
                "sw2_deg": {"min": 5.0, "max": 20.0},
                "sw3_deg": {"min": 0.0, "max": 10.0},
            },
            "section_bounds": {
                "airfoil_name": "naca4412",
                "dihedral_root_deg": 0.0,
                "twist_b0_deg": {"min": -2.0, "max": 2.0},
                "twist_b1_deg": {"min": -3.0, "max": 3.0},
                "twist_b2_deg": {"min": -4.0, "max": 4.0},
                "twist_b3_deg": {"min": -5.0, "max": 5.0},
                "dihedral_b1_deg": {"min": 0.0, "max": 5.0},
                "dihedral_b2_deg": {"min": 0.0, "max": 8.0},
                "dihedral_b3_deg": {"min": 0.0, "max": 10.0},
            },
            "outputs": {
                "save_plot": False,
                "build_aerosandbox": True,
            },
        },
    }


@pytest.fixture
def raw_config() -> dict:
    """Provide a fresh raw config for each test."""
    return make_raw_config()


@pytest.fixture
def config(raw_config):
    """Provide a typed generator config."""
    return build_bwb_generator_config(raw_config)


@pytest.fixture
def sample(config):
    """Provide a deterministic sampled design."""
    rng = np.random.default_rng(123)
    return sample_bwb_design(config, rng)


@pytest.fixture
def planform(config, sample):
    """Provide a deterministic generated planform."""
    return generate_bwb_planform_from_sample(sample, config)


@pytest.fixture
def section_geometry(config, sample, planform):
    """Provide deterministic generated section geometry."""
    return build_section_geometry_from_sample(planform, sample, config)