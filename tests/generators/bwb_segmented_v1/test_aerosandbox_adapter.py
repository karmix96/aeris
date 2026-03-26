"""Tests for AeroSandbox conversion in bwb_segmented_v1.aerosandbox_adapter."""

from __future__ import annotations

import math

import numpy as np

from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import build_aerosandbox_geometry
from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config
from aeris.generators.bwb_segmented_v1.planform import generate_bwb_planform_from_sample
from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design
from aeris.generators.bwb_segmented_v1.sections import build_section_geometry_from_sample


def _make_config_with_control_surface(raw_config: dict):
    raw = {
        **raw_config,
        "geometry": {
            **raw_config["geometry"],
            "control_surfaces": {
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
            },
        },
    }
    return build_bwb_generator_config(raw)


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

    assert "has_control_surfaces" in result.metadata
    assert "control_surface_count" in result.metadata
    assert "applied_control_surfaces" in result.metadata


def test_build_aerosandbox_geometry_without_control_surfaces(raw_config):
    config = build_bwb_generator_config(raw_config)
    rng = np.random.default_rng(123)
    sample = sample_bwb_design(config, rng)
    planform = generate_bwb_planform_from_sample(sample, config)
    section_geometry = build_section_geometry_from_sample(planform, sample, config)

    result = build_aerosandbox_geometry(section_geometry, config)
    airplane = result.airplane

    total_cs = sum(
        len(getattr(xsec, "control_surfaces", []))
        for wing in airplane.wings
        for xsec in wing.xsecs
    )

    assert total_cs == 0
    assert result.metadata["has_control_surfaces"] is False
    assert result.metadata["control_surface_count"] == 0
    assert result.metadata["applied_control_surfaces"] == []


def test_build_aerosandbox_geometry_applies_control_surfaces(raw_config):
    config = _make_config_with_control_surface(raw_config)
    rng = np.random.default_rng(123)
    sample = sample_bwb_design(config, rng)
    planform = generate_bwb_planform_from_sample(sample, config)
    section_geometry = build_section_geometry_from_sample(planform, sample, config)

    result = build_aerosandbox_geometry(section_geometry, config)
    airplane = result.airplane

    tagged: list[int] = []
    for wing in airplane.wings:
        for i, xsec in enumerate(wing.xsecs):
            if len(getattr(xsec, "control_surfaces", [])) > 0:
                tagged.append(i)

    assert len(tagged) > 0
    assert result.metadata["has_control_surfaces"] is True
    assert result.metadata["control_surface_count"] == 1

    applied = result.metadata["applied_control_surfaces"]
    assert len(applied) == 1
    assert applied[0]["name"] == "elevon"
    assert applied[0]["hinge_point"] == 0.75
    assert applied[0]["start_frac"] == 0.60
    assert applied[0]["end_frac"] == 0.95
    assert applied[0]["applied_xsec_indices"] == tagged


def test_build_aerosandbox_geometry_control_surface_deflection_stays_zero(raw_config):
    config = _make_config_with_control_surface(raw_config)
    rng = np.random.default_rng(123)
    sample = sample_bwb_design(config, rng)
    planform = generate_bwb_planform_from_sample(sample, config)
    section_geometry = build_section_geometry_from_sample(planform, sample, config)

    result = build_aerosandbox_geometry(section_geometry, config)
    airplane = result.airplane

    seen = []
    for wing in airplane.wings:
        for xsec in wing.xsecs:
            for cs in getattr(xsec, "control_surfaces", []):
                seen.append(cs)
                assert cs.deflection == 0.0

    assert len(seen) > 0
