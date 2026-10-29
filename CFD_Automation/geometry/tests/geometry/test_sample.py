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


def test_lhs_one_point_per_slice():
    spec = CFG.types["bwb"]
    vecs = sample.lhs(spec, 100, 1001)
    u = np.array([params.to_unit(spec, v) for v in vecs])
    for j in range(u.shape[1]):
        assert sorted(np.floor(u[:, j] * 100).astype(int)) == list(range(100))


def test_lhs_fixed_seed_and_holdout_differs():
    spec = CFG.types["conventional"]
    a = sample.lhs(spec, 10, 2002)
    assert a == sample.lhs(spec, 10, 2002)
    train = sample.lhs(spec, 100, 1002)
    assert not any(v in train for v in a)


def test_corner1():
    spec = CFG.types["bwb"]
    c = sample.corner1(spec)
    assert len(c) == 2 * len(spec.free_variables)
    lo, hi = spec.ranges["sweep2_deg"]
    assert c[2 * 8]["sweep2_deg"] == lo and c[2 * 8 + 1]["sweep2_deg"] == hi
    assert c[0]["sweep2_deg"] == pytest.approx(0.5 * (lo + hi))


def test_sets_and_reference_rules():
    sets = sample.make_sets(CFG, "bwb")
    assert len(sets["training"]["vectors"]) == 100
    assert len(sets["holdout"]["vectors"]) == 10 and sets["holdout"]["sealed"]
    assert len(sets["corner2"]["vectors"]) == 8
    ref = sets["reference"]
    assert ref["rules"] == ["mid_range", "smallest_area", "largest_area",
                            "most_sweep_smallest_tip", "strongest_washout"]
    idx = [i for i in ref["training_index"] if i is not None]
    assert len(set(idx)) == 4
    tr = sets["training"]["vectors"]
    wash = [v["twist3_deg"] - v["twist0_deg"] for v in tr]
    assert ref["training_index"][4] == int(np.argmin(wash))
    assert ref["coverage"]["passed"]


def test_coverage_definition():
    train = np.array([[0.0, 0.0], [1.0, 1.0], [0.5, 0.5]])
    assert sample.coverage(np.array([[0.5, 0.5]]), train) == pytest.approx(math.sqrt(0.5))
    assert sample.coverage(train, train) == 0.0


def test_mixed_shares():
    drawn = sample.draw_mixed(CFG, 10, 7)
    counts = {t: sum(k == t for k, _ in drawn) for t in params.WING_TYPES}
    assert sum(counts.values()) == 10
    assert all(abs(counts[t] - 10 * CFG.shares[t]) <= 1 for t in params.WING_TYPES)
