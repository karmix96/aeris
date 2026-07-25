"""The panelling decisions must be reachable from the config, CLI and GUI.

DECISIONS-0009/0010/0011 are only real if production code honours them. This
guards the wiring itself, not the aerodynamics:

  * the config block parses and enforces AVL's array limits;
  * `build_pygeo_sections_from_config` takes its defaults FROM the config;
  * adaptive placement is actually reachable and gated on the ramp criterion;
  * band-edge snapping INSERTS rather than moves (moving widens the gain ramp,
    which is the thing DECISION-0010 says to minimise);
  * the CLI and GUI expose the knobs.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pytest

from aeris.common.config import load_yaml_config
from aeris.generators.bwb_segmented_v1.params import AeroDiscretisationConfig
from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
    build_pygeo_sections_from_config,
)
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.geometric_information import ramp_fraction
from aeris.geometry.registry import get_geometry_generator

CONFIG = Path("configs/geometry/bwb.yaml")


def _cfg():
    return resolve_generator_and_config(load_yaml_config(CONFIG))[1]


def test_config_carries_the_decided_discretisation():
    d = _cfg().aero_discretisation
    assert (d.n_sections, d.spanwise_panels_per_section, d.nchordwise) == (25, 4, 24)
    assert d.span_margin == 0.0
    assert d.cspace == 1.0
    assert d.section_placement == "auto"


def test_config_enforces_avl_array_limits():
    ok, msg = AeroDiscretisationConfig().avl_limits_ok()
    assert ok, msg
    # 49 sections / 4 spanwise / 16 chordwise = 6144 vortices -> over the limit
    bad = AeroDiscretisationConfig(n_sections=49, nchordwise=16)
    assert not bad.avl_limits_ok()[0]
    # 65 sections / 4 spanwise = 512 strips -> over NSMAX
    assert not AeroDiscretisationConfig(n_sections=65).avl_limits_ok()[0]


def test_sections_builder_takes_defaults_from_the_config():
    """No explicit arguments -> the config's values must be used."""
    _, _, meta = build_pygeo_sections_from_config(CONFIG)
    assert meta["span_margin"] == _cfg().aero_discretisation.span_margin


def test_band_edge_snapping_inserts_rather_than_moves():
    """Moving the nearest section onto the edge leaves its neighbour a full
    spacing away, which WIDENS the gain ramp -- the opposite of what
    DECISION-0010 requires. Inserting keeps the edge exact and the neighbour close.
    """
    _, _, meta = build_pygeo_sections_from_config(CONFIG)
    band = (meta["control"]["start_frac"], meta["control"]["end_frac"])
    n_req = _cfg().aero_discretisation.n_sections

    moved = np.linspace(0.0, 1.0, n_req)
    for edge in band:
        moved[int(np.argmin(np.abs(moved - edge)))] = edge
    inserted = np.unique(np.concatenate([np.linspace(0.0, 1.0, n_req), list(band)]))

    assert ramp_fraction(inserted, band) < ramp_fraction(moved, band)
    # and the real builder gains sections rather than relocating them
    assert meta["n_sections"] > n_req


@pytest.mark.parametrize(
    "band,expect_adaptive",
    [((0.55, 0.92), False), ((0.70, 0.85), True)],
)
def test_adaptive_placement_is_reachable_and_gated(band, expect_adaptive):
    """'auto' must engage adaptive placement only when the ramp criterion fails."""
    gcfg = _cfg()
    base = get_geometry_generator("bwb_segmented").sample_one(gcfg, seed=7000)
    sample = dataclasses.replace(
        base, elevon_start_frac=band[0], elevon_end_frac=band[1]
    )
    _, _, meta = build_pygeo_sections_from_config(CONFIG, sample=sample)
    used = meta["section_placement"] == "adaptive"
    assert used is expect_adaptive, (
        f"band {band}: placement={meta['section_placement']} "
        f"ramp={meta['ramp_fraction']:.3f}"
    )
    assert "ramp_fraction" in meta


def test_cli_and_gui_expose_the_knobs():
    cli = Path("src/aeris/commands/aero.py").read_text()
    for flag in ("--nchordwise", "--spanwise-panels", "--span-margin",
                 "--cspace", "--section-placement"):
        assert flag in cli, f"CLI is missing {flag}"
    gui = Path("src/aeris/gui/app.py").read_text()
    for flag in ("--nchordwise", "--spanwise-panels", "--cspace",
                 "--section-placement"):
        assert flag in gui, f"GUI does not pass {flag}"
