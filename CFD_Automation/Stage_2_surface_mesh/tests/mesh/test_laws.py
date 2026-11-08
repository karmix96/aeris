"""The anchors (decision 71): each value is met at its anchor level and follows the family rule elsewhere.

No mesh is built here: these are the values laws.py gives every level."""

import pytest

from cfdauto.mesh.laws import SETTINGS, first_cell_c, rules
from cfdauto.paths import STAGE2

LEVELS = ("VC", "C", "M", "F")
FIRST = STAGE2 / "configs" / "surface_first.yaml"
G = lambda g: tuple(g ** (1.0 / 1.3 ** k) for k in range(4))      # a growth met at VC, on VC, C, M, F

# the new approach, VC, C, M, F (the anchored value x 1.3^(anchor - level))
NEW = {
    "nose_turning_deg": (16.9, 13.0, 10.0, 7.6923),           # 10 deg at M (accuracy target)
    "te_spacing_c": (0.00169, 0.0013, 0.001, 0.00076923),     # 0.1 % c at M
    "max_spacing_c": (0.0338, 0.026, 0.02, 0.015385),         # 2 % c at M
    "span_spacing_c": (0.4225, 0.325, 0.25, 0.19231),         # 0.25 x local chord at M
    "cells_per_bubble": (9.1033, 11.834, 15.385, 20.0),       # 20 at F (transition target): the inverse
    "yplus": (1.0, 0.76923, 0.59172, 0.45517),                # y+ = 1 at VC (hard minimum)
    "chord_growth": G(1.20),                                  # 1.2 built at VC: 1.2, 1.151, 1.114, 1.087
    "chord_growth_limit": G(1.25),                            # 1.25 checked at VC: 1.25, 1.187, 1.141, 1.107
    "span_growth": G(1.20),
    "span_growth_limit": G(1.30),
}
COUNTS = {"base_cells": (8, 10, 14, 18),                      # 8 at VC, even counts
          "min_cells_per_panel": (8, 10, 12, 16)}             # 12 at M: 7.1 -> 8, 9.2 -> 10, 12, 15.6 -> 16


@pytest.mark.parametrize("name", list(NEW))
def test_anchored_values_at_every_level(name):
    for lev, want in zip(LEVELS, NEW[name]):
        assert rules(lev).setting(name) == pytest.approx(want, rel=1e-4), (name, lev)


@pytest.mark.parametrize("name", list(COUNTS))
def test_whole_numbers_at_every_level(name):
    assert tuple(rules(lev).setting(name) for lev in LEVELS) == COUNTS[name]


def test_exact_at_the_anchor():
    assert rules("M").nose_turning_deg == 10.0 and rules("M").te_spacing_c == 0.001
    assert rules("M").span_spacing_c == 0.25 and rules("M").min_cells_per_panel == 12
    assert rules("F").cells_per_bubble == 20.0 and rules("VC").yplus == 1.0 and rules("VC").base_cells == 8


def test_band_cell_and_bubble_table():
    f, vc = rules("F"), rules("VC")
    for re in (4.0e5, 1.0e6, 3.0e6):                           # floor 0.10 c from local Re 4e5 (decision 72)
        assert f.bubble_length_c(re) == pytest.approx(0.10)
        assert f.band_spacing_c(re) == pytest.approx(0.10 / 20)  # 0.5 % c at F
        assert vc.band_spacing_c(re) == pytest.approx(0.10 / 9.1033, rel=1e-4)
    assert f.bubble_length_c(6.0e4) == pytest.approx(0.40) and f.bubble_length_c(3.0e4) == pytest.approx(0.40)
    assert f.bubble_length_c(1.0e5) == pytest.approx(0.30)
    assert vc.band_spacing_c(6.0e4) == pytest.approx(vc.max_spacing_c)   # 0.40 / 9.1 = 4.4 % c, capped at 3.38 % c


def test_tip_gap_is_two_s0_at_every_level():
    for k, lev in enumerate(LEVELS):
        r = rules(lev)
        assert r.tip_gap_in_s0 == 2.0
        s0 = r.first_cell_c(3.0e5)
        assert s0 == pytest.approx(first_cell_c(3.0e5, 1.0) / 1.3 ** k, rel=1e-12)   # s0 / 1.3 per level


def test_bands():
    for lev in LEVELS:
        assert rules(lev).band_upper == (0.0, 1.0)              # owner, 8 Nov 2026 (was 0-85 % c, decision 58)
        assert rules(lev).band_lower == (0.0, 1.0)              # decision 74, option A


def test_nose_solve_levels():
    assert rules().nose_solve_levels == ["VC", "C", "M", "F"]   # the strictest answer wins (surface_rules.md, 14)
    assert rules("C", FIRST).nose_solve_levels == ["C"]         # the first approach: the coarsest level only


def test_every_setting_has_a_reason():
    for lev in LEVELS:
        reasons = rules(lev).reasons()
        assert set(SETTINGS) <= set(reasons)
    assert rules("VC").reason("nose_turning_deg") == (
        "law 1: largest turning per ring cell [deg]: 10 at M (accuracy target, decision 71); "
        "VC is 2 levels coarser: x 1.3^2 = 16.9")
    assert rules("F").reason("min_cells_per_panel").endswith("F is 1 level finer: x 1.3^1, rounded up = 16")


def test_levels_and_anchors_refused_when_unknown(tmp_path):
    with pytest.raises(ValueError):
        rules("FF")                                             # the new ladder is VC, C, M, F
    with pytest.raises(ValueError):
        rules("VC", FIRST)                                      # the first ladder is C, M, F, FF
    bad = tmp_path / "bad.yaml"
    bad.write_text(FIRST.read_text().replace("te_spacing_c: 0.001 ", "te_spacing_c: {value: 0.001, at: XX} "))
    with pytest.raises(ValueError):
        rules("C", bad).te_spacing_c


def test_the_first_approach_keeps_its_meaning():
    """configs/surface_first.yaml (plain numbers): every rule at C, the coarsest; the spacings / 1.3^k, the counts
    x 1.3^k, the growth g^(1/1.3^k); the nose angle and the growth limits the same at every level."""
    for k, lev in enumerate(("C", "M", "F", "FF")):
        r, s = rules(lev, FIRST), 1.3 ** k
        assert r.nose_turning_deg == 10.0
        assert r.te_spacing_c == 0.001 / s and r.max_spacing_c == 0.02 / s and r.span_spacing_c == 0.2 / s
        assert r.yplus == 1.0 / s and r.tip_gap_in_s0 == 1.0
        assert r.cells_per_bubble == 20 * s
        assert r.chord_growth == 1.2 ** (1 / s) and r.chord_growth_limit == 1.25 and r.span_growth_limit == 1.3
        assert r.base_cells == (8, 10, 14, 18)[k] and r.min_cells_per_panel == (12, 16, 21, 27)[k]
        assert r.band_lower == (0.6, 1.0)
        assert r.band_spacing_c(1.0e6) == pytest.approx(0.05 / 20 / s, rel=1e-12)
