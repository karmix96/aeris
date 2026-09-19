#!/usr/bin/env python
"""Choose the ten pilot geometries by maximin, and measure that the choice is good.

    .venv/bin/python .../select_pilot_geometries.py \
        --out AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/reports/s8_pilot_geometries.json

PLAN_desktop_campaign.md 4.1.  The set is fixed BEFORE the first pilot case runs,
and it is fixed by a script rather than by a list in a document, so that anyone
can ask where the ten came from and get the same ten back.

The seed set is not a space-filling choice and is not pretending to be
--------------------------------------------------------------------
Five of the ten are chosen for reasons that have nothing to do with covering the
design space:

    65, 23, 16, 13    four of the fifteen designs that FOLDED before the
                      span-normal frame fix.  The fix exists for these, and not
                      one of them has ever been through CFD.  A pilot that
                      skipped them would test the fix on designs that never
                      needed it.
    83                the reference.  Every prior S8 result, the grid family,
                      the AVL cross-check and the cp-bound work are all on 83,
                      and dropping it would break continuity with all of it.

The remaining five are chosen purely for cover, by maximin: repeatedly add the
design whose distance to the nearest already-chosen design is largest.  Index 12
comes out of that process and is ALSO a former folder, which is a coincidence
worth noticing rather than a design of the selection.

Coverage is reported against alternatives, not asserted
-------------------------------------------------------
"Space-filling" is a claim, and the claim is checkable: the coverage of a set is
the worst distance from any of the 100 designs to its nearest chosen one, lower
being better.  This script computes it for the chosen ten, for the first ten, for
the old S6/S7 representative five, and for a distribution of random tens, so the
number that ends up in the record has something to be compared against.

Normalisation matters and is the reason this is not eyeballed: the 20 design
variables carry different units and ranges, and an un-normalised distance is
dominated by whichever variable happens to have the largest numerical spread.
Each is scaled to [0, 1] over the 100 designs first.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for extra in (HERE, HERE.parent, HERE.parent / "S6_bounded_mesh_atlas", REPO / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

#: PLAN 4.1 / AUDIT 2026-09-05.  Order is the order they enter the maximin loop,
#: which is what makes the result reproducible.
SEED = [65, 23, 16, 13, 83]
FORMER_FOLDERS = {12, 13, 16, 23, 65}
#: The set S6 and S7 actually used, imported rather than retyped so that this
#: comparison keeps tracking it if it ever changes.  It is here only as a
#: coverage baseline: five evenly-indexed designs out of an LHS are not a
#: space-filling choice in 20 dimensions, and the number below says by how much.
try:
    from S7_unstructured_gmsh_su2.qualification import REPRESENTATIVE_INDICES
    S6_S7_REPRESENTATIVE = list(REPRESENTATIVE_INDICES)
    S6_S7_SOURCE = "S7_unstructured_gmsh_su2.qualification.REPRESENTATIVE_INDICES"
except Exception:  # noqa: BLE001 - a comparison baseline is not worth failing over
    S6_S7_REPRESENTATIVE = [0, 24, 49, 74, 99]
    S6_S7_SOURCE = "hard-coded fallback; the S7 module could not be imported"
TARGET = 10


def normalise(X: np.ndarray) -> np.ndarray:
    span = np.maximum(X.max(0) - X.min(0), 1e-300)
    return (X - X.min(0)) / span


def maximin(Z: np.ndarray, seed: list[int], target: int) -> tuple[list[int], list[dict]]:
    chosen = list(seed)
    trace = []
    while len(chosen) < target:
        d = np.min(np.linalg.norm(Z[:, None, :] - Z[None, chosen, :], axis=-1), axis=1)
        d[chosen] = -1.0
        pick = int(np.argmax(d))
        trace.append({"added": pick, "distance_to_nearest_chosen": float(d[pick])})
        chosen.append(pick)
    return chosen, trace


def coverage(Z: np.ndarray, chosen: list[int]) -> float:
    """Worst distance from any design to its nearest chosen one. Lower is better."""
    d = np.min(np.linalg.norm(Z[:, None, :] - Z[None, chosen, :], axis=-1), axis=1)
    return float(d.max())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set-name", default="lhs100_seed42")
    ap.add_argument("--target", type=int, default=TARGET)
    ap.add_argument("--random-draws", type=int, default=200)
    ap.add_argument("--seed", type=int, nargs="*", default=SEED)
    ap.add_argument("--rng-seed", type=int, default=0,
                    help="for the random-ten comparison only; it never affects "
                         "the selection, which is deterministic")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    from shared.geometry_sets import design_matrix
    X, names = design_matrix(args.set_name)
    X = np.asarray(X, float)
    Z = normalise(X)
    print(f"{args.set_name}: {X.shape[0]} designs, {X.shape[1]} design variables")

    chosen, trace = maximin(Z, list(args.seed), args.target)
    chosen_sorted = sorted(chosen)

    rng = np.random.default_rng(args.rng_seed)
    randoms = [coverage(Z, list(rng.choice(X.shape[0], args.target, replace=False)))
               for _ in range(args.random_draws)]
    comparison = {
        "these_ten": coverage(Z, chosen),
        f"random_{args.target}_median_of_{args.random_draws}": float(np.median(randoms)),
        f"random_{args.target}_best_of_{args.random_draws}": float(np.min(randoms)),
        f"first_{args.target}": coverage(Z, list(range(args.target))),
        "s6_s7_representative_five": coverage(Z, S6_S7_REPRESENTATIVE),
    }

    print(f"\nseed set (chosen for their own reasons, not for cover): {args.seed}")
    for step in trace:
        flag = "  (also a former folder)" if step["added"] in FORMER_FOLDERS else ""
        print(f"  maximin adds {step['added']:>3}  at distance "
              f"{step['distance_to_nearest_chosen']:.4f}{flag}")
    print(f"\nselected: {chosen_sorted}")
    print(f"  former folders included : "
          f"{sorted(set(chosen_sorted) & FORMER_FOLDERS)}")
    print(f"  reference included      : {'yes' if 83 in chosen_sorted else 'NO'}")

    print(f"\ncoverage -- worst distance from any design to its nearest chosen one, "
          f"lower is better")
    for label, value in sorted(comparison.items(), key=lambda kv: kv[1]):
        mark = "  <-- these ten" if label == "these_ten" else ""
        print(f"  {label:<40}{value:>9.4f}{mark}")

    beaten = [k for k, v in comparison.items() if k != "these_ten" and v < comparison["these_ten"]]
    if beaten:
        print(f"\n  NOTE: {', '.join(beaten)} covers the space better than the chosen "
              f"ten. That is expected and is not a defect: five of the ten are fixed "
              f"by what they are, not by where they sit, so the chosen set trades "
              f"some cover for designs that must be tested. It is worth knowing by "
              f"how much.")

    report = {"plan_section": "4.1", "set_name": args.set_name,
              "n_designs": int(X.shape[0]), "n_design_variables": int(X.shape[1]),
              "design_variable_names": list(names),
              "seed_set": list(args.seed),
              "seed_set_rationale": {
                  "65_23_16_13": "four of the fifteen designs that folded before the "
                                 "span-normal frame fix; the fix exists for these and "
                                 "none has been through CFD",
                  "83": "the reference: the grid family, the AVL cross-check and every "
                        "prior S8 result are on it"},
              "method": "maximin over design variables normalised to [0,1] over the set",
              "maximin_trace": trace,
              "selected": chosen_sorted,
              "selected_in_selection_order": chosen,
              "former_folders_included": sorted(set(chosen_sorted) & FORMER_FOLDERS),
              "coverage": comparison,
              "s6_s7_representative_five": {"indices": S6_S7_REPRESENTATIVE,
                                            "source": S6_S7_SOURCE},
              "coverage_definition": "worst distance from any of the designs to its "
                                     "nearest chosen one, in normalised design-variable "
                                     "space; lower is better"}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
