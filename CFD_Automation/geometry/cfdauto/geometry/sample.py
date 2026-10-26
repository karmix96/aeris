"""The wing sets: Latin hypercube, corner sets, reference wings, hold-out.

    python -m cfdauto.geometry.sample        # writes data/sets/<type>/*.json
"""

from __future__ import annotations

import itertools
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import qmc

from .params import Config, TypeSpec, from_unit, load_config, mid_vector, to_unit
from .planform import build_planform

SETS_DIR = Path(__file__).resolve().parents[2] / "data" / "sets"


def lhs(spec: TypeSpec, n: int, seed: int) -> list[dict]:
    names = spec.free_variables
    unit = qmc.LatinHypercube(d=len(names), rng=np.random.default_rng(seed)).random(n)
    return [from_unit(spec, dict(zip(names, row))) for row in unit]


def corner1(spec: TypeSpec) -> list[dict]:
    """Each variable at its lower and its upper bound, all others mid-range."""
    out = []
    for v in spec.free_variables:
        out.append(from_unit(spec, {v: 0.0}))
        out.append(from_unit(spec, {v: 1.0}))
    return out


def corner2_size(n_vars: int) -> int:
    """Smallest N with C(N-1, ceil(N/2)) >= n_vars."""
    n = 2
    while math.comb(n - 1, math.ceil(n / 2)) < n_vars:
        n += 1
    return n


def corner2_matrix(n_vars: int) -> np.ndarray:
    """Rows = wings, columns = variables, True = upper bound.

    Row 0 all low. Each variable is high on a distinct ceil(N/2)-element subset
    of rows {1 .. N-1}. Two distinct subsets of the same size each have a row
    the other lacks (high/low and low/high); two subsets of more than half of
    N-1 rows always share a row (high/high); row 0 gives low/low.
    """
    n = corner2_size(n_vars)
    subsets = itertools.islice(itertools.combinations(range(1, n), math.ceil(n / 2)), n_vars)
    m = np.zeros((n, n_vars), dtype=bool)
    for j, rows in enumerate(subsets):
        m[list(rows), j] = True
    return m


def covers_all_pairs(m: np.ndarray) -> bool:
    """Brute force: every pair of columns shows all four low/high combinations."""
    for a, b in itertools.combinations(range(m.shape[1]), 2):
        if len({(bool(x), bool(y)) for x, y in zip(m[:, a], m[:, b])}) != 4:
            return False
    return True


def corner2(spec: TypeSpec) -> list[dict]:
    names = spec.free_variables
    m = corner2_matrix(len(names))
    return [from_unit(spec, {v: float(m[r, j]) for j, v in enumerate(names)}) for r in range(len(m))]


def reference(spec: TypeSpec, training: list[dict]) -> list[dict]:
    """Five wings by rule. Mid-range is built from the ranges; the other four are
    picked from the training set (no wing picked twice)."""
    area = np.array([build_planform(spec, v).area() for v in training])
    unit = np.array([to_unit(spec, v) for v in training])
    names = list(spec.free_variables)
    sweep = np.mean([unit[:, names.index(f"sweep{i}_deg")] for i in (1, 2, 3)], axis=0)
    tip = np.array([v["root_chord_m"] * v["c4_ratio"] for v in training])
    tip_u = (tip - tip.min()) / max(np.ptp(tip), 1e-12)
    washout = np.array([v["twist3_deg"] - v["twist0_deg"] for v in training])

    picks, out = [], [{"rule": "mid_range", "training_index": None, "vector": mid_vector(spec)}]
    for rule, order in [
        ("smallest_area", np.argsort(area)),
        ("largest_area", np.argsort(-area)),
        ("most_sweep_smallest_tip", np.argsort(-(sweep - tip_u))),
        ("strongest_washout", np.argsort(washout)),
    ]:
        i = int(next(k for k in order if k not in picks))
        picks.append(i)
        out.append({"rule": rule, "training_index": i, "vector": training[i]})
    return out


def coverage(ref_unit: np.ndarray, train_unit: np.ndarray) -> float:
    """Largest distance from a training wing to its nearest reference wing."""
    d = np.linalg.norm(train_unit[:, None, :] - ref_unit[None, :, :], axis=2)
    return float(np.max(np.min(d, axis=1)))


def coverage_check(spec: TypeSpec, ref: list[dict], training: list[dict], n_random: int, seed: int) -> dict:
    tu = np.array([to_unit(spec, v) for v in training])
    ru = np.array([to_unit(spec, r["vector"]) for r in ref])
    rng = np.random.default_rng(seed)
    rand = [coverage(tu[rng.choice(len(tu), len(ru), replace=False)], tu) for _ in range(n_random)]
    c, med = coverage(ru, tu), float(np.median(rand))
    return {"coverage": c, "random_median": med, "random_min": float(np.min(rand)),
            "random_max": float(np.max(rand)), "n_random": n_random, "passed": c <= med}


def draw_mixed(cfg: Config, n: int, seed: int) -> list[tuple[str, dict]]:
    """For wing_type = mixed: n wings split between the types by the shares."""
    n_bwb = round(n * cfg.shares["bwb"])
    return ([("bwb", v) for v in lhs(cfg.types["bwb"], n_bwb, seed)]
            + [("conventional", v) for v in lhs(cfg.types["conventional"], n - n_bwb, seed + 1)])


def make_sets(cfg: Config, wing_type: str) -> dict[str, dict]:
    spec = cfg.types[wing_type]
    seeds = cfg.sets["seeds"][wing_type]
    if seeds["training"] == seeds["holdout"]:
        raise ValueError("training and hold-out need different seeds")
    training = lhs(spec, cfg.sets["training_size"], seeds["training"])
    ref = reference(spec, training)
    head = {"wing_type": wing_type, "variables": list(spec.free_variables)}
    return {
        "training": head | {"how": "latin hypercube", "seed": seeds["training"], "vectors": training},
        "corner1": head | {"how": "each variable at each bound, others mid-range", "vectors": corner1(spec)},
        "corner2": head | {"how": "binary covering array of strength 2",
                           "size_rule": "smallest N with C(N-1, ceil(N/2)) >= n_variables",
                           "matrix": corner2_matrix(len(spec.free_variables)).astype(int).tolist(),
                           "vectors": corner2(spec)},
        "reference": head | {"how": "five wings by rule", "rules": [r["rule"] for r in ref],
                             "training_index": [r["training_index"] for r in ref],
                             "coverage": coverage_check(spec, ref, training, cfg.sets["coverage_random_sets"],
                                                        cfg.sets["coverage_seed"]),
                             "vectors": [r["vector"] for r in ref]},
        "holdout": head | {"how": "latin hypercube, other seed; sealed: never built in Stage 1",
                           "seed": seeds["holdout"], "sealed": True,
                           "vectors": lhs(spec, cfg.sets["holdout_size"], seeds["holdout"])},
    }


def write_sets(cfg: Config, out: Path = SETS_DIR) -> None:
    for t in ("bwb", "conventional"):
        (out / t).mkdir(parents=True, exist_ok=True)
        for name, data in make_sets(cfg, t).items():
            (out / t / f"{name}.json").write_text(json.dumps(data, indent=1))


if __name__ == "__main__":
    c = load_config()
    write_sets(c)
    for t in ("bwb", "conventional"):
        cov = json.loads((SETS_DIR / t / "reference.json").read_text())["coverage"]
        print(f"{t}: sets written; reference coverage {cov['coverage']:.3f} vs random median "
              f"{cov['random_median']:.3f} -> {'pass' if cov['passed'] else 'FAIL'}")
