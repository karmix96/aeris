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

from .params import FAMILIES, WING_TYPES, Config, TypeSpec, from_unit, load_config, mid_vector, to_unit
from .planform import build_planform

SETS_DIR = Path(__file__).resolve().parents[2] / "data" / "sets"


def lhs(spec: TypeSpec, n: int, seed: int) -> list[dict]:
    """n wings by Latin hypercube over the type's box.

    Section choices (if any) get their own hypercube columns, so each candidate is used about
    equally often. With a span cap (focus space, `max_full_span_m`), the hypercube is drawn larger
    and only the wings within the cap are kept, in draw order, until n are found: still space-filling,
    but the strata are no longer exactly balanced where the cap cuts the box."""
    names = spec.free_variables + spec.choice_variables
    if spec.max_full_span_m is None:
        unit = qmc.LatinHypercube(d=len(names), rng=np.random.default_rng(seed)).random(n)
        return [from_unit(spec, dict(zip(names, row))) for row in unit]
    m = max(2 * n, 8)
    while True:
        unit = qmc.LatinHypercube(d=len(names), rng=np.random.default_rng(seed)).random(m)
        out = []
        for row in unit:
            v = from_unit(spec, dict(zip(names, row)))
            if 2.0 * build_planform(spec, v).semi_span <= spec.max_full_span_m * (1 + 1e-12):
                out.append(v)
                if len(out) == n:
                    return out
        m *= 2
        if m > 4096 * max(n, 1):
            raise ValueError(f"{spec.name}: the span cap {spec.max_full_span_m} m leaves almost no wings in the box")


def within_cap(spec: TypeSpec, vec: dict) -> bool:
    """True when the wing's full span (tip to tip) is within the type's cap (or there is none)."""
    return spec.max_full_span_m is None or 2.0 * build_planform(spec, vec).semi_span <= spec.max_full_span_m * (1 + 1e-12)


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
    sweep = np.mean([unit[:, names.index(f"sweep{i}_deg")] for i in (1, 2, 3)
                     if f"sweep{i}_deg" in names], axis=0)
    tip = np.array([build_planform(spec, v).chord[-1] for v in training])
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
    """For wing_type = mixed (all types) or a family name (its two types): n wings split by the shares."""
    pool = FAMILIES.get(cfg.wing_type, WING_TYPES)       # a family draws only its own two types
    types = [t for t in pool if cfg.shares.get(t, 0.0) > 0]
    total = sum(cfg.shares[t] for t in types)
    exact = [n * cfg.shares[t] / total for t in types]
    counts = [math.floor(x) for x in exact]
    # largest remainder: the wings left over go to the types with the biggest fractions
    for k in sorted(range(len(types)), key=lambda k: exact[k] - counts[k], reverse=True)[: n - sum(counts)]:
        counts[k] += 1
    return [(t, v) for k, (t, m) in enumerate(zip(types, counts)) for v in lhs(cfg.types[t], m, seed + k)]


def make_sets(cfg: Config, wing_type: str) -> dict[str, dict]:
    """Dense in the focus space (realistic wings), sparse in the full space (everything supported).

    focus: training, reference, holdout.  full: training_full, holdout_full, and both corner
    sets (the corners test the edges of what we claim to support)."""
    spec, full = cfg.types[wing_type], cfg.full[wing_type]
    seeds = cfg.sets["seeds"][wing_type]
    used = [seeds[k] for k in ("training_focus", "holdout_focus", "training_full", "holdout_full")]
    if len(set(used)) != len(used):
        raise ValueError("training, hold-out and their full versions need different seeds")
    training = lhs(spec, cfg.sets["training_focus_size"], seeds["training_focus"])
    ref = reference(spec, training)
    head = {"wing_type": wing_type, "space": "focus", "variables": list(spec.free_variables)}
    head_f = head | {"space": "full", "variables": list(full.free_variables)}
    return {
        "training_focus": head | {"how": "latin hypercube", "seed": seeds["training_focus"], "vectors": training},
        "training_full": head_f | {"how": "latin hypercube over the full space", "seed": seeds["training_full"],
                                   "vectors": lhs(full, cfg.sets["training_full_size"], seeds["training_full"])},
        "corner1": head_f | {"how": "each variable at each bound of the full space, others mid-range",
                             "vectors": corner1(full)},
        "corner2": head_f | {"how": "binary covering array of strength 2 on the full space",
                             "size_rule": "smallest N with C(N-1, ceil(N/2)) >= n_variables",
                             "matrix": corner2_matrix(len(full.free_variables)).astype(int).tolist(),
                             "vectors": corner2(full)},
        "reference": head | {"how": "five wings by rule", "rules": [r["rule"] for r in ref],
                             "training_index": [r["training_index"] for r in ref],
                             "coverage": coverage_check(spec, ref, training, cfg.sets["coverage_random_sets"],
                                                        cfg.sets["coverage_seed"]),
                             "vectors": [r["vector"] for r in ref]},
        "holdout_focus": head | {"how": "latin hypercube, other seed; sealed: never built in Stage 1",
                           "seed": seeds["holdout_focus"], "sealed": True,
                           "vectors": lhs(spec, cfg.sets["holdout_focus_size"], seeds["holdout_focus"])},
        "holdout_full": head_f | {"how": "latin hypercube over the full space, other seed; sealed",
                                  "seed": seeds["holdout_full"], "sealed": True,
                                  "vectors": lhs(full, cfg.sets["holdout_full_size"], seeds["holdout_full"])},
    }


def write_sets(cfg: Config, out: Path = SETS_DIR) -> None:
    for t in WING_TYPES:
        (out / t).mkdir(parents=True, exist_ok=True)
        for name, data in make_sets(cfg, t).items():
            (out / t / f"{name}.json").write_text(json.dumps(data, indent=1))


if __name__ == "__main__":
    c = load_config()
    write_sets(c)
    for t in WING_TYPES:
        cov = json.loads((SETS_DIR / t / "reference.json").read_text())["coverage"]
        print(f"{t}: sets written; reference coverage {cov['coverage']:.3f} vs random median "
              f"{cov['random_median']:.3f} -> {'pass' if cov['passed'] else 'FAIL'}")
