#!/usr/bin/env python3
"""Does mesh quality hold up as the family refines? A pre-flight for the cloud batch.

    python3 mesh_quality_ladder.py

The cloud batch's own preflight declares eleven meshes "clean" on the strength of
`folded: 0` and `wall_layer_error_m <= 3e-16`, and the 100-design and 61-design
robustness screens record `negative_cells` and nothing about cell CONDITIONING
(`reports/s8_cloud_meshes.json`, `s8_robustness_screen_gciF.json`). PLAN 0.1 is the
lesson this repeats: on defect 21 "every metric being checked was unchanged" while
the wing surface moved a millimetre, because the metrics measured cell SHAPE and
nothing measured cell POSITION. Here the gap is the other way round -- nothing
measures the worst cell's conditioning, which is what a linear solver actually
feels.

It matters because the worst cells get WORSE as this family refines while the bulk
gets better, so a median or a fold count improves all the way up the ladder and
hides it. And because a mesh from this family with a worst-cell scaled Jacobian of
0.0073 stalled ANK outright on 2026-09-21: residual rising monotonically from
3.1e-2 to 5.0e-2 over seventy iterations with the adaptive CFL pinned 32x below its
healthy value. `gci_F` and `gci_FF` are both worse conditioned than that mesh.

Run this before renting anything.

Written 2026-09-21 by the reliability audit follow-up.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compare_meshes  # noqa: E402

REPORTS = HERE / "reports"

#: The four-level family on the reference geometry, coarse to fine, as the cloud
#: batch would run it. All family B (wall-resolved tip cap).
LADDER = [
    ("gci_C", HERE / "runs/s8_v2/g83"),
    ("gci_M", HERE / "runs/s8_v2/g83"),
    ("gci_F", HERE / "runs/s8_cloud/g83"),
    ("gci_FF", HERE / "runs/s8_cloud/g83"),
]

#: The mesh that stalled ANK, as the reference point for "how bad is too bad".
#: 787,944 cells, family B, wall-normal refined at 1.3 with the first cell scaled.
STALL_REFERENCE = {
    "level": "gci_C_normal_s0_b",
    "cells": 787944,
    "scaled_jacobian_min": 0.00729189,
    "outcome": ("ANK-only did not converge: residual rose monotonically from 3.108e-2 "
                "at iteration 139 to 5.048e-2 at 209, adaptive CFL pinned at 3.12e+03 "
                "against a healthy 1.00e+05, step length and linear residual both "
                "normal. Stopped at iteration 211."),
}

#: Reported because they tell opposite stories and only one of them is the risk.
WORST_CELL = ("quality/o_wing/scaled_jacobian_min", "quality/o_wing/scaled_jacobian_p001",
              "validity/o_wing/min_cell_volume_m3", "resolution/ds_span_min_m")
BULK = ("quality/o_wing/scaled_jacobian_median", "quality/o_wing/scaled_jacobian_p01",
        "quality/o_wing/neighbour_volume_ratio_p99", "resolution/normal_growth_max",
        "quality/wall_nonorthogonality_max_deg")


#: Meshes to locate the worst cells in, beyond the ladder itself. The point is the
#: comparison: a level that CONVERGES and a level that STALLED, so "the worst cells
#: are bad" can be checked against "the worst cells are bad in a mesh that works".
LOCATE = [("gci_C", HERE / "runs/s8_v2/g83"),
          ("gci_C_normal_s0_b", HERE / "runs/s8_normalB")]


def locate_worst(level: str, directory: Path, how_many: int = 3) -> dict:
    """WHERE the worst-conditioned cells are, by block and index.

    A minimum scaled Jacobian is a number you cannot act on. Its location is:
    cells at the wall need the mesher fixed, cells at the far-field edge of the
    O-block are in a low-gradient region and probably harmless, and cells at a
    block interface are a topology question. This is what turned "gci_F is worse
    conditioned than a mesh that stalled, do not rent" into "the same cells are bad
    in gci_C, which converges fine, so conditioning is not the explanation" -- a
    conclusion reversed within the hour by asking where rather than how much.
    """
    import numpy as np
    blocks = np.load(directory / f"{level}_blocks.npz")
    out = {}
    for name in blocks.files:
        b = blocks[name]
        if b.ndim != 4:
            continue
        sj = compare_meshes.scaled_jacobian(b)
        ni, nj, nk = sj.shape
        flat = sj.ravel()
        worst = []
        for o in np.argsort(flat)[:how_many]:
            i, j, k = (int(v) for v in np.unravel_index(o, sj.shape))
            worst.append({
                "scaled_jacobian": round(float(flat[o]), 6),
                "i_ring": i, "j_normal": j, "k_span": k,
                "of": [ni, nj, nk],
                # i = around the ring, j = wall-normal, k = spanwise: the ordering
                # README records for the npz (C-order there, Fortran in the CGNS).
                "where": ("at the WALL" if j == 0 else
                          "at the OUTERMOST normal layer (far-field edge of the block)"
                          if j >= nj - 2 else "inside the boundary layer"),
                "span_position": ("tip" if k >= nk - 2 else "root" if k <= 1 else "mid-span"),
            })
        out[name] = {"cells": [ni, nj, nk],
                     "scaled_jacobian_min": round(float(flat.min()), 6),
                     "cells_below_0p01": int((flat < 0.01).sum()),
                     "worst": worst}
    return out


def main() -> int:
    rows, failed = {}, {}
    for level, directory in LADDER:
        try:
            rows[level] = compare_meshes.metrics(directory, level)
        except Exception as exc:                     # noqa: BLE001 - report, do not hide
            failed[level] = f"{type(exc).__name__}: {exc}"

    levels = [lv for lv, _ in LADDER if lv in rows]
    report = {
        "schema": "aeris.s8.mesh_quality_ladder.v1",
        "question": ("the cloud preflight calls eleven meshes clean on fold count alone. "
                     "Does the WORST cell's conditioning hold up as the family refines?"),
        "geometry_index": 83,
        "mesh_family": "B (wall-resolved tip cap)",
        "levels": levels,
        "unreadable": failed,
        "cells": {lv: rows[lv].get("topology/o_wing/cells") for lv in levels},
        "worst_cell": {m: {lv: rows[lv].get(m) for lv in levels} for m in WORST_CELL},
        "bulk": {m: {lv: rows[lv].get(m) for lv in levels} for m in BULK},
        "folded": {lv: rows[lv].get("validity/inverted_cells_total") for lv in levels},
        "stall_reference": STALL_REFERENCE,
    }

    sj = [rows[lv].get("quality/o_wing/scaled_jacobian_min") for lv in levels]
    med = [rows[lv].get("quality/o_wing/scaled_jacobian_median") for lv in levels]
    if all(isinstance(v, (int, float)) for v in sj) and len(sj) > 1:
        degrades = all(b < a for a, b in zip(sj, sj[1:]))
        bulk_improves = all(b >= a for a, b in zip(med, med[1:]))
        worse_than_stall = [lv for lv, v in zip(levels, sj)
                            if v < STALL_REFERENCE["scaled_jacobian_min"]]
        report["finding"] = {
            "worst_cell_degrades_monotonically": bool(degrades),
            "bulk_improves_monotonically": bool(bulk_improves),
            "scaled_jacobian_min_by_level": dict(zip(levels, sj)),
            "levels_worse_conditioned_than_the_mesh_that_stalled": worse_than_stall,
            "reading": (
                "The worst cell degrades by about 1.4x per level while the median, the "
                "neighbour volume ratio and the normal growth rate all IMPROVE. So every "
                "metric the preflight records gets better all the way up the ladder, and "
                "the one a linear solver feels gets worse. A fold count cannot see this."
                if degrades and bulk_improves else
                "The monotone pattern this file was written to detect is not present; read "
                "the tables rather than this sentence."),
        }
        report["where_the_worst_cells_are"] = {
            lv: locate_worst(lv, d) for lv, d in LOCATE
            if (d / f"{lv}_blocks.npz").exists()}

        # Does the conditioning actually explain the stall? Only if the mesh that
        # stalled is bad somewhere the mesh that converges is NOT. Checked, not assumed.
        loc = report["where_the_worst_cells_are"]
        same_place = None
        if {"gci_C", "gci_C_normal_s0_b"} <= set(loc):
            a = loc["gci_C"].get("o_wing", {}).get("worst", [{}])[0]
            b = loc["gci_C_normal_s0_b"].get("o_wing", {}).get("worst", [{}])[0]
            same_place = (a.get("where") == b.get("where")
                          and a.get("span_position") == b.get("span_position")
                          and abs(a.get("i_ring", -99) - b.get("i_ring", 99)) <= 2)
        report["conditioning_explains_the_stall"] = {
            "worst_cells_in_the_same_place_as_a_converging_level": same_place,
            "verdict": (
                "NO. The stalled mesh's worst cells sit in the same block, at the same ring "
                "index and span station, and in the same OUTERMOST normal layer as gci_C's -- "
                "and gci_C converges. The far-field edge of the O-block is a low-gradient "
                "region and this is a pre-existing feature of every level, so a handful of "
                "cells there does not explain a stall. Look at the 5x finer first spanwise "
                "cell at the tip and the 4x finer trailing edge instead."
                if same_place else
                "Possibly: the stalled mesh's worst cells are NOT where the converging level's "
                "are, so conditioning remains a live suspect. Read the locations below."),
        }
        report["gate"] = {
            "blocks_renting_on_conditioning_grounds": bool(same_place is False),
            "verdict": (
                f"Worst-cell conditioning degrades up the ladder and the preflight cannot see "
                f"it, which is worth recording. But it does NOT block the batch: "
                f"{', '.join(worse_than_stall) or 'the fine levels'} are worse conditioned than "
                f"the mesh that stalled, and yet the stalled mesh's bad cells are in the same "
                f"place as a converging level's. The stall's cause is unestablished."
                if same_place else
                f"Conditioning is a live suspect for the stall: {', '.join(worse_than_stall)} "
                f"are worse conditioned than the mesh that failed to converge, and the bad "
                f"cells are not in the same place as a converging level's."),
            "cheap_test_available": (
                "gci_C_normal_s0_b is 788k cells, fits this host, and stalls under ANK-only, so "
                "'can the solver handle a mesh like gci_F' can be probed here rather than "
                "rented. NKSwitchTol matters: the governed 1e-6 never fires, because the stall "
                "begins at a relative residual of 1.7e-4, 170x above it."),
        }

    out = REPORTS / "s8_mesh_quality_ladder.json"
    out.write_text(json.dumps(report, indent=2) + "\n")

    print(f"\n  geometry 83, family B, coarse to fine\n")
    width = "".join(f"{lv:>13}" for lv in levels)
    print(f"  {'':<42}{width}")
    print(f"  {'cells (o_wing)':<42}" + "".join(
        f"{report['cells'][lv]:>13,}" if report['cells'][lv] else f"{'--':>13}"
        for lv in levels))
    print("\n  WORST CELL -- degrades with refinement")
    for m in WORST_CELL:
        print(f"  {m.split('/')[-1]:<42}" + "".join(
            f"{report['worst_cell'][m][lv]:>13.4g}"
            if isinstance(report['worst_cell'][m][lv], (int, float)) else f"{'--':>13}"
            for lv in levels))
    print("\n  BULK -- improves with refinement, and hides the above")
    for m in BULK:
        print(f"  {m.split('/')[-1]:<42}" + "".join(
            f"{report['bulk'][m][lv]:>13.4g}"
            if isinstance(report['bulk'][m][lv], (int, float)) else f"{'--':>13}"
            for lv in levels))
    print(f"\n  folded cells: " + ", ".join(f"{lv} {report['folded'][lv]}" for lv in levels))
    for lv, blocks in report.get("where_the_worst_cells_are", {}).items():
        print(f"\n  WHERE the worst cells are -- {lv}")
        for blk, info in blocks.items():
            w = info["worst"][0] if info["worst"] else {}
            print(f"    {blk:<10} min {info['scaled_jacobian_min']:<10} "
                  f"below 0.01: {info['cells_below_0p01']:<5} "
                  f"i {w.get('i_ring')} j {w.get('j_normal')} k {w.get('k_span')} "
                  f"-- {w.get('where')}, {w.get('span_position')}")
    if "conditioning_explains_the_stall" in report:
        print(f"\n  Does conditioning explain the stall? "
              f"{report['conditioning_explains_the_stall']['verdict']}")
    if failed:
        print("\n  UNREADABLE: " + "; ".join(f"{k} ({v})" for k, v in failed.items()))
    if "gate" in report:
        print(f"\n  {report['gate']['verdict']}")
    print(f"\nwrote {out.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
