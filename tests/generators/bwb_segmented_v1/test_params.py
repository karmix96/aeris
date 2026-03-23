"""Tests for typed config construction in bwb_segmented_v1.params."""

import pytest

from aeris.generators.bwb_segmented_v1.params import (
    BWBGeneratorConfig,
    build_bwb_generator_config,
)


def make_raw_config() -> dict:
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


def test_build_bwb_generator_config_returns_typed_config():
    config = build_bwb_generator_config(make_raw_config())
    assert isinstance(config, BWBGeneratorConfig)
    assert config.generator.family == "bwb_segmented"
    assert config.generator.version == "v1"
    assert config.name == "test_bwb"


def test_build_bwb_generator_config_requires_generator_identity():
    raw = make_raw_config()
    del raw["geometry"]["generator"]["family"]

    with pytest.raises(KeyError):
        build_bwb_generator_config(raw)