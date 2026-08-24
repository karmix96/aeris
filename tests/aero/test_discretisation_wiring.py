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
    # nchordwise 12 = the DSE tier (DECISION-0013). 24 is the verification tier
    # and must be selected explicitly; shipping it as the default cost 58 s per
    # design point and made a 2000-design sweep 6.7 days.
    assert (d.n_sections, d.spanwise_panels_per_section, d.nchordwise) == (25, 4, 12)
    assert d.span_margin == 0.0
    assert d.cspace == 1.0
    # DECISION-0014 (revised): gated adaptive placement. The gate leaves benign
    # geometries on uniform+pins and engages only where the gain ramp is severe,
    # which is where it improves the worst case (1.98% -> 1.68%).
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
    ex, _, meta = build_pygeo_sections_from_config(CONFIG)
    band = (meta["control"]["start_frac"], meta["control"]["end_frac"])
    n_req = _cfg().aero_discretisation.n_sections

    moved = np.linspace(0.0, 1.0, n_req)
    for edge in band:
        moved[int(np.argmin(np.abs(moved - edge)))] = edge
    inserted = np.unique(np.concatenate([np.linspace(0.0, 1.0, n_req), list(band)]))

    assert ramp_fraction(inserted, band) < ramp_fraction(moved, band)
    # The real builder INSERTS the pins (it does not relocate a neighbour onto the
    # edge) while still honouring the budget exactly: n_sections is the FINAL count,
    # so the uniform base grid is reduced by the number of interior pins first.
    # Both properties must hold together -- an exact count with a missing pin, or
    # every pin present but an inflated count, are each a failure.
    assert meta["n_sections"] == n_req
    fracs = sorted(float(s.span_fraction) for s in ex)
    for pin in meta["feature_pins"]:
        assert any(abs(f - pin) < 1e-6 for f in fracs), f"pin {pin} was dropped"


@pytest.mark.parametrize(
    "band,expect_adaptive",
    [((0.55, 0.92), False), ((0.70, 0.85), True)],
)
def test_adaptive_placement_is_reachable_and_gated(band, expect_adaptive):
    """'auto' must engage adaptive placement only when the ramp criterion fails.

    The shipped default is now 'never' (DECISION-0014), so this forces 'auto'
    explicitly. The gate itself must keep working: adaptive placement remains the
    documented exception for short-span control surfaces, where the gain ramp is
    structurally unreachable by pinning alone.
    """
    gcfg = _cfg()
    forced = dataclasses.replace(gcfg, aero_discretisation=dataclasses.replace(
        gcfg.aero_discretisation, section_placement="auto"))
    base = get_geometry_generator("bwb_segmented").sample_one(gcfg, seed=7000)
    sample = dataclasses.replace(
        base, elevon_start_frac=band[0], elevon_end_frac=band[1]
    )
    # build_pygeo_sections_from_config re-reads the config from disk, so the
    # forced setting has to be injected at the resolver.
    import aeris.geometry.config_resolver as CR
    original = CR.resolve_generator_and_config
    CR.resolve_generator_and_config = lambda raw: ("bwb_segmented", forced)
    try:
        _, _, meta = build_pygeo_sections_from_config(CONFIG, sample=sample)
    finally:
        CR.resolve_generator_and_config = original
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
