"""Forecast cells, memory and solve time for each grid level, from one measured level.

M5 needs a coupled coarse/medium/fine family.  Whether that family can run at all
on the inventoried host is a question worth answering BEFORE spending days on
M1B and M3, because the answer may be no -- S6 reached exactly that terminal
state, `RESOURCE_BLOCKED_16GB`, and S7 inherits the same host.

The forecast is anchored on a measured level rather than on a cell-count target.
`POLICY.yaml` defines each level by edge lengths, so the refinement ratio between
levels is exact; what is estimated is only how cell counts follow it:

- Surface triangles scale as r^2, where r is the ratio of surface edge lengths.
  This is geometry, not a model.
- Prisms are surface wall triangles times prism layers, so they scale as r^2
  times the layer ratio.  Also not a model.
- Tetrahedra scale as r_core^3.  This IS the estimate -- an isotropic core filled
  at a uniformly refined size field.  It is the one number to replace with a
  measurement, which `--measured LEVEL=CELLS` does.

Memory uses the one law measured for this solver, shared with `solver_tuning`:
each MPI rank reads the whole mesh before partitioning.

    python -m S7_unstructured_gmsh_su2.grid_family_forecast \\
        --prisms 126984 --tets 1422127 --budget-gib 11.36
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .common import load_policy
from .solver_tuning import (
    MEMORY_HEADROOM_FRACTION,
    MESH_GIB_PER_MILLION_CELLS,
    gib_per_rank,
)

# Measured on the index-0 coarse half mesh by a rank sweep on an idle machine,
# differencing 5- and 25-iteration probes:
#
#   ranks   s/iteration   startup s
#   1       4.60          12.0
#   2       5.65          39.8
#
# More ranks are SLOWER.  The solve is memory-bandwidth bound, so extra ranks buy
# halo exchange and partitioning cost for no arithmetic gain, and each one also
# holds another full copy of the mesh.  The forecast therefore does NOT divide by
# rank count: one rank is both the cheapest in memory and the fastest in time.
#
# The 1- and 2-rank histories are byte-identical over 25 iterations, so the
# decomposition changes cost and nothing else.
SECONDS_PER_ITERATION_PER_MILLION_CELLS = 4.60 / 1.549111


def level_forecast(
    policy: dict[str, Any],
    *,
    reference: str,
    prisms: int,
    tets: int,
    measured: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    levels = policy["grid_family"]["levels"]
    if reference not in levels:
        raise KeyError(f"unknown reference level {reference!r}; have {sorted(levels)}")
    ref = levels[reference]
    ref_surface = float(ref["surface_edge_over_L"])
    ref_core = float(ref["near_core_edge_over_L"])
    ref_layers = float(ref["prism_layers"])
    measured = measured or {}

    rows: list[dict[str, Any]] = []
    for name, spec in levels.items():
        surface_ratio = ref_surface / float(spec["surface_edge_over_L"])
        core_ratio = ref_core / float(spec["near_core_edge_over_L"])
        layer_ratio = float(spec["prism_layers"]) / ref_layers
        forecast_prisms = prisms * surface_ratio**2 * layer_ratio
        forecast_tets = tets * core_ratio**3
        cells = forecast_prisms + forecast_tets
        source = "forecast"
        if name in measured:
            cells = float(measured[name])
            source = "measured"
        elif name == reference:
            cells = float(prisms + tets)
            source = "measured"
        rows.append(
            {
                "level": name,
                "surface_refinement_ratio": round(surface_ratio, 4),
                "core_refinement_ratio": round(core_ratio, 4),
                "prism_layers": int(spec["prism_layers"]),
                "prisms": int(round(forecast_prisms)),
                "tetrahedra": int(round(forecast_tets)),
                "cells": int(round(cells)),
                "source": source,
                "gib_per_rank_1": round(gib_per_rank(cells, 1), 2),
                # The mesh is replicated on every rank, so this is the least any
                # rank can cost no matter how the job is decomposed.
                "floor_gib": round(cells / 1.0e6 * MESH_GIB_PER_MILLION_CELLS, 2),
            }
        )
    return rows


def solvability(rows: list[dict[str, Any]], budget_gib: float) -> list[dict[str, Any]]:
    """How many ranks each level admits, and whether it is solvable at all."""
    usable = budget_gib * MEMORY_HEADROOM_FRACTION
    out = []
    for row in rows:
        floor = float(row["floor_gib"])
        # Search upward: more ranks lower the per-rank cost toward the floor, so
        # a level is solvable if ANY rank count fits, and unsolvable outright
        # once the floor alone exceeds the budget.
        max_ranks = 0
        if floor <= usable:
            for candidate in range(1, 65):
                if gib_per_rank(row["cells"], candidate) <= usable:
                    max_ranks = candidate
                    break
        per_rank = gib_per_rank(row["cells"], max_ranks) if max_ranks else floor
        # No division by ranks: the sweep shows they do not help.  This is the
        # single-rank cost, which is also the cheapest memory footprint.
        seconds = row["cells"] / 1.0e6 * SECONDS_PER_ITERATION_PER_MILLION_CELLS
        out.append(
            {
                **row,
                "usable_gib": round(usable, 2),
                "min_ranks_that_fit": max_ranks,
                "gib_per_rank_at_that_count": round(per_rank, 2),
                # A level needing more than the whole budget for ONE rank cannot
                # be solved on this host at any decomposition.
                "solvable": max_ranks >= 1,
                "seconds_per_iteration_at_max_ranks": round(seconds, 1),
                "hours_for_6000_iterations": round(seconds * 6000.0 / 3600.0, 1),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", default="coarse")
    parser.add_argument("--prisms", type=int, required=True)
    parser.add_argument("--tets", type=int, required=True)
    parser.add_argument(
        "--budget-gib",
        type=float,
        default=11.36,
        help="host memory available to one solve; default is the S6 desktop inventory",
    )
    parser.add_argument(
        "--measured",
        action="append",
        default=[],
        metavar="LEVEL=CELLS",
        help="replace a forecast cell count with a measured one",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    measured = {}
    for item in args.measured:
        level, _, count = item.partition("=")
        measured[level.strip()] = int(count)

    rows = solvability(
        level_forecast(
            load_policy(),
            reference=args.reference,
            prisms=args.prisms,
            tets=args.tets,
            measured=measured,
        ),
        args.budget_gib,
    )

    print("%-8s %10s %9s %9s %8s %7s %8s %9s" % (
        "level", "cells", "1 rank", "floor", "min rank", "s/iter", "h/6000", "solvable"))
    for r in rows:
        print("%-8s %10d %9.2f %9.2f %8s %7.1f %8.1f %9s" % (
            r["level"], r["cells"], r["gib_per_rank_1"], r["floor_gib"],
            r["min_ranks_that_fit"] or "-",
            r["seconds_per_iteration_at_max_ranks"], r["hours_for_6000_iterations"],
            "yes" if r["solvable"] else "NO"))
    print(
        "\nTetrahedral counts are an r^3 estimate; replace them with --measured as "
        "soon as a level is meshed.  Times are SINGLE-RANK, which the rank sweep "
        "shows is the fastest as well as the smallest: 4.60 s/iteration at one "
        "rank against 5.65 at two.  'ranks' is what the memory budget admits, not "
        "a recommendation to use them."
    )
    if args.output:
        args.output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
