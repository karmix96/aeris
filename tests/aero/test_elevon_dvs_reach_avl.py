"""Regression guard: the three elevon DVs must reach the AVL control surface.

They are sampled per design (DECISION-0002 gives the DoE 3 elevon geometry DVs so
the optimiser can search for the elevon that meets the controllability
requirement). A defect found 2026-07-25 had the aero entry point reading the
elevon from the STATIC CONFIG instead of the sample, so every design in a DoE flew
the same elevon and all three DVs were inert on the aero path -- invisible unless
you compare the sample against the control dict.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from aeris.common.config import load_yaml_config
from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
    build_pygeo_sections_from_config,
)
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator

CONFIG = Path("configs/geometry/bwb.yaml")


def _sample(seed):
    raw = load_yaml_config(CONFIG)
    gid, g = resolve_generator_and_config(raw)
    return get_geometry_generator(gid).sample_one(g, seed=seed), g


@pytest.mark.parametrize("seed", [7000, 7001, 7005])
def test_sampled_elevon_dvs_reach_the_avl_control(seed):
    s, _ = _sample(seed)
    _, _, meta = build_pygeo_sections_from_config(CONFIG, n_sections=9, seed=seed)
    c = meta["control"]
    assert c["start_frac"] == pytest.approx(s.elevon_start_frac)
    assert c["end_frac"] == pytest.approx(s.elevon_end_frac)
    assert c["hinge_point"] == pytest.approx(s.elevon_hinge_frac)


def test_elevon_actually_differs_between_designs():
    """Guards the failure mode directly: if the config were being read instead of
    the sample, every seed would return an identical elevon."""
    seen = set()
    for seed in (7000, 7001, 7002, 7005):
        _, _, meta = build_pygeo_sections_from_config(CONFIG, n_sections=9, seed=seed)
        c = meta["control"]
        seen.add((round(c["start_frac"], 6), round(c["end_frac"], 6),
                  round(c["hinge_point"], 6)))
    assert len(seen) == 4, f"elevon geometry is not varying across designs: {seen}"


def test_constructed_extreme_hinge_is_honoured():
    """Task 5 builds extreme designs by hand; the override must respect them."""
    s, _ = _sample(7000)
    for hinge in (0.65, 0.82):
        ext = dataclasses.replace(s, elevon_hinge_frac=hinge)
        _, _, meta = build_pygeo_sections_from_config(CONFIG, n_sections=9, sample=ext)
        assert meta["control"]["hinge_point"] == pytest.approx(hinge)
