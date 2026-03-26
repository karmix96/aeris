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
        "control_surfaces": {
            "enabled": False,
            "surfaces": [],
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

def test_build_bwb_generator_config_defaults_to_disabled_control_surfaces():
    config = build_bwb_generator_config(make_raw_config())

    assert config.control_surfaces.enabled is False
    assert config.control_surfaces.surfaces == ()


def test_build_bwb_generator_config_parses_control_surface_block():
    raw = make_raw_config()
    raw["geometry"]["control_surfaces"] = {
        "enabled": True,
        "surfaces": [
            {
                "name": "elevon",
                "family": "trailing_edge",
                "hinge_point": 0.75,
                "symmetric": True,
                "spanwise": {
                    "start_frac": 0.60,
                    "end_frac": 0.95,
                },
                "deflection_sign": "standard",
                "required": False,
            }
        ],
    }

    config = build_bwb_generator_config(raw)

    assert config.control_surfaces.enabled is True
    assert len(config.control_surfaces.surfaces) == 1

    cs = config.control_surfaces.surfaces[0]
    assert cs.name == "elevon"
    assert cs.family == "trailing_edge"
    assert cs.hinge_point == 0.75
    assert cs.symmetric is True
    assert cs.side is None
    assert cs.spanwise.start_frac == 0.60
    assert cs.spanwise.end_frac == 0.95
    assert cs.deflection_sign == "standard"
    assert cs.required is False


def test_build_bwb_generator_config_rejects_invalid_control_surface_span_range():
    raw = make_raw_config()
    raw["geometry"]["control_surfaces"] = {
        "enabled": True,
        "surfaces": [
            {
                "name": "elevon",
                "family": "trailing_edge",
                "hinge_point": 0.75,
                "symmetric": True,
                "spanwise": {
                    "start_frac": 0.95,
                    "end_frac": 0.60,
                },
            }
        ],
    }

    with pytest.raises(ValueError, match="invalid spanwise range"):
        build_bwb_generator_config(raw)


def test_build_bwb_generator_config_rejects_invalid_hinge_point():
    raw = make_raw_config()
    raw["geometry"]["control_surfaces"] = {
        "enabled": True,
        "surfaces": [
            {
                "name": "elevon",
                "family": "trailing_edge",
                "hinge_point": 1.20,
                "symmetric": True,
                "spanwise": {
                    "start_frac": 0.60,
                    "end_frac": 0.95,
                },
            }
        ],
    }

    with pytest.raises(ValueError, match="hinge_point"):
        build_bwb_generator_config(raw)


def test_build_bwb_generator_config_rejects_duplicate_control_surface_names():
    raw = make_raw_config()
    raw["geometry"]["control_surfaces"] = {
        "enabled": True,
        "surfaces": [
            {
                "name": "elevon",
                "family": "trailing_edge",
                "hinge_point": 0.75,
                "symmetric": True,
                "spanwise": {"start_frac": 0.60, "end_frac": 0.80},
            },
            {
                "name": "elevon",
                "family": "trailing_edge",
                "hinge_point": 0.75,
                "symmetric": True,
                "spanwise": {"start_frac": 0.82, "end_frac": 0.95},
            },
        ],
    }

    with pytest.raises(ValueError, match="Duplicate control surface name"):
        build_bwb_generator_config(raw)


def test_build_bwb_generator_config_rejects_side_for_symmetric_surface():
    raw = make_raw_config()
    raw["geometry"]["control_surfaces"] = {
        "enabled": True,
        "surfaces": [
            {
                "name": "elevon",
                "family": "trailing_edge",
                "hinge_point": 0.75,
                "symmetric": True,
                "side": "left",
                "spanwise": {"start_frac": 0.60, "end_frac": 0.95},
            }
        ],
    }

    with pytest.raises(ValueError, match="symmetric=True"):
        build_bwb_generator_config(raw)