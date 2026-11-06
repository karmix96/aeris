import math

import numpy as np
import pytest

from cfdauto.geometry import params, sample

CFG = params.load_config()


@pytest.mark.parametrize("n,expect", [(17, 8), (18, 8), (16, 8), (10, 6), (35, 8), (36, 9)])
def test_corner2_size(n, expect):
    assert sample.corner2_size(n) == expect
    assert math.comb(expect - 1, math.ceil(expect / 2)) >= n


@pytest.mark.parametrize("n", [3, 10, 17, 18, 35, 60])
def test_corner2_covers_every_pair(n):
    m = sample.corner2_matrix(n)
    assert not m[0].any()
    assert sample.covers_all_pairs(m)


def test_pair_check_catches_a_repeated_column():
    m = sample.corner2_matrix(5)
    m[:, 1] = m[:, 0]
    assert not sample.covers_all_pairs(m)


@pytest.mark.parametrize("space", ["types", "full"])
def test_lhs_one_point_per_slice(space):
    spec = getattr(CFG, space)["bwb"]      # no span cap in either space (decision 70): an exact Latin hypercube
    vecs = sample.lhs(spec, 100, 1001)
    u = np.array([params.to_unit(spec, v) for v in vecs])
    for j in range(u.shape[1]):
        assert sorted(np.floor(u[:, j] * 100).astype(int)) == list(range(100))


def test_same_seeds_same_shapes_as_the_first_sets():
    """Decision 70 took the root chord out of the vector; the same seeds still give the same shapes
    (values of the first sets, 6 Nov 2026). Full space: the exact draw; focus: the first rows of the
    same 2n-row draw, which the 7 m span cap used to filter (this wing passed it)."""
    full = sample.lhs(CFG.full["bwb"], 40, 1101)[0]
    assert full["c2_ratio"] == pytest.approx(0.5805668742801138, abs=1e-15)
    assert full["aspect_ratio"] == pytest.approx(2.839716749043898, abs=1e-15)
    assert full["airfoils"] == ["naca4415", "naca4415", "mh45", "naca4412"]
    focus = sample.lhs(CFG.types["tapered"], 100, 1003, sample.focus_rows(100))[0]
    assert focus["c4_ratio"] == pytest.approx(0.5209003546544425, abs=1e-15)
    assert focus["aspect_ratio"] == pytest.approx(16.486918754368247, abs=1e-15)


@pytest.mark.parametrize("wing_type", params.WING_TYPES)
def test_focus_sets_have_no_size_cap(wing_type):
    """The focus space ends at its shape ranges only: wings up to the top aspect ratio are kept."""
    spec = CFG.types[wing_type]
    vecs = sample.lhs(spec, 100, 1001, sample.focus_rows(100))
    assert len(vecs) == 100 and all(params.in_ranges(spec, v) for v in vecs)
    lo, hi = spec.ranges["aspect_ratio"]
    assert max(v["aspect_ratio"] for v in vecs) > hi - 0.05 * (hi - lo)


def test_lhs_fixed_seed_and_holdout_differs():
    spec = CFG.types["cranked"]
    a = sample.lhs(spec, 10, 2002)
    assert a == sample.lhs(spec, 10, 2002)
    train = sample.lhs(spec, 100, 1002)
    assert not any(v in train for v in a)


def test_corner1():
    spec = CFG.types["bwb"]
    c = sample.corner1(spec)
    assert len(c) == 2 * len(spec.free_variables) == 32          # 16 free variables (no root chord)
    k = spec.free_variables.index("sweep2_deg")
    lo, hi = spec.ranges["sweep2_deg"]
    assert c[2 * k]["sweep2_deg"] == lo and c[2 * k + 1]["sweep2_deg"] == hi
    assert c[0]["sweep2_deg"] == pytest.approx(0.5 * (lo + hi))


def test_sets_and_reference_rules():
    sets = sample.make_sets(CFG, "bwb")
    assert len(sets["training_focus"]["vectors"]) == 100
    assert len(sets["holdout_focus"]["vectors"]) == 10 and sets["holdout_focus"]["sealed"]
    assert len(sets["corner2"]["vectors"]) == 8
    m = np.array(sets["corner2"]["matrix"], dtype=bool)
    assert m.shape == (8, 16) and not m[0].any() and sample.covers_all_pairs(m)
    ref = sets["reference"]
    assert ref["rules"] == ["mid_range", "lowest_aspect_ratio", "highest_aspect_ratio",
                            "most_sweep_smallest_tip", "strongest_washout"]
    idx = [i for i in ref["training_index"] if i is not None]
    assert len(set(idx)) == 4
    tr = sets["training_focus"]["vectors"]
    ar = [v["aspect_ratio"] for v in tr]
    assert ref["training_index"][1] == int(np.argmin(ar))
    wash = [v["twist3_deg"] - v["twist0_deg"] for v in tr]
    rest = [i for i in range(len(tr)) if i not in ref["training_index"][1:4]]
    assert ref["training_index"][4] == min(rest, key=lambda i: wash[i])
    assert ref["coverage"]["passed"]


def test_area_rules_are_aspect_ratio_rules_at_unit_mean_chord():
    """At unit mean chord the area is the aspect ratio, so the size rules became shape rules."""
    from cfdauto.geometry.planform import build_planform
    spec = CFG.types["cranked"]
    for v in sample.lhs(spec, 20, 5):
        assert build_planform(spec, v).area() == pytest.approx(v["aspect_ratio"], rel=1e-12)


def test_coverage_definition():
    train = np.array([[0.0, 0.0], [1.0, 1.0], [0.5, 0.5]])
    assert sample.coverage(np.array([[0.5, 0.5]]), train) == pytest.approx(math.sqrt(0.5))
    assert sample.coverage(train, train) == 0.0


def test_mixed_shares():
    drawn = sample.draw_mixed(CFG, 10, 7)
    counts = {t: sum(k == t for k, _ in drawn) for t in params.WING_TYPES}
    assert sum(counts.values()) == 10
    assert all(abs(counts[t] - 10 * CFG.shares[t]) <= 1 for t in params.WING_TYPES)
