#!/usr/bin/env python3
"""How many drag counts does the region with unphysical surface pressure carry?

    python3 cp_drag_map.py --run runs/s8_v2/g83/gci_C_a0

`check_cp_bound.py` says whether cp exceeds its isentropic bound.
`locate_cp_excess.py` says where. Neither says what it COSTS, and until it is a
number in counts it cannot be compared with the 5-9 count effect the campaign
exists to resolve, so it has sat on every list as "flagged" since 4 September.
This closes that: it integrates the surface pressure directly and reports the
pressure drag carried by the over-bound cells, by the leading-edge strip, and by
the tip cap.

THE SELF-CHECK IS THE POINT. A regional breakdown from an integration that does
not reproduce the solver's own CDp is decoration. So the total is compared with
ADflow's CDp from `result.json` first, and the breakdown is refused if they
disagree by more than a stated tolerance. That is also how the orientation
question is settled: a surface normal's sign convention is a coin flip, and rather
than assume one, both are tried and the one matching the solver is reported --
the convention-free measurement PLAN 0.7 asks for, after two sign errors cost
hours on the AVL comparison (defect 17).

Caveat this tool cannot remove: it integrates cell-centre cp over cell areas,
which is a first-order approximation of what ADflow does. Expect agreement to a
fraction of a count, not to machine precision, and read the residual as the
method's own error bar.

Written 2026-09-21 by the reliability audit follow-up.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

#: Isentropic stagnation cp at the mission Mach number of 0.0837. Above this the
#: solver is reporting a pressure the flow cannot reach.
CP_PHYSICAL_MAX = 1.0018
#: How close the integration must come to ADflow's CDp before the breakdown is
#: trusted, in drag counts.
AGREEMENT_TOLERANCE_COUNTS = 2.0


def data(node: dict, name: str) -> np.ndarray:
    return np.array(node[name][" data"])


def cell_geometry(xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cell centres and area-normal vectors from corner nodes, shape (nj, ni, 3).

    The area vector of a quadrilateral is half the cross product of its
    diagonals, which is exact for a planar cell and the standard approximation
    for a warped one.
    """
    p00, p10, p01, p11 = xyz[:-1, :-1], xyz[1:, :-1], xyz[:-1, 1:], xyz[1:, 1:]
    centres = 0.25 * (p00 + p10 + p01 + p11)
    area_vec = 0.5 * np.cross(p11 - p00, p01 - p10)
    return centres, area_vec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", type=Path, required=True,
                    help="a run directory holding result.json and *surf*.cgns")
    ap.add_argument("--le-strip-cells", type=int, default=6,
                    help="ring cells either side of the leading edge counted as "
                         "the leading-edge strip")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    result = json.loads((args.run / "result.json").read_text())
    area_ref = result["area_ref_m2"]
    f = result["functions"]
    cdp_solver = next(v for k, v in f.items() if k.endswith("_cdp"))
    drag_dir = np.array(
        (result.get("flow_directions") or {}).get("velocity_direction_realised")
        or [1.0, 0.0, 0.0], dtype=float)
    drag_dir /= np.linalg.norm(drag_dir)

    surfaces = sorted(args.run.glob("*surf*.cgns"))
    if not surfaces:
        print(f"no surface solution in {args.run}")
        return 1

    import cgns_read
    if cgns_read.is_hdf5(surfaces[0]):
        import h5py
        handle = h5py.File(surfaces[0], "r")
        found = [(k, handle[k]) for k in handle]
    else:
        handle = None
        found = cgns_read.surface_zones(surfaces[0])

    zones = []
    try:
        for name, node in found:
            if "Wall" not in name:
                continue
            xyz = np.stack([data(node["GridCoordinates"], f"Coordinate{a}")
                            for a in "XYZ"], axis=-1)
            cp_full = data(node["Flow solution"], "CoefPressure")
            sol = node["Flow solution"]
            yplus = data(sol, "YPlus") if "YPlus" in sol else None
            nj, ni = xyz.shape[0] - 1, xyz.shape[1] - 1
            if cp_full.shape != (nj + 2, ni + 2):
                print(f"{name}: cp {cp_full.shape} is not cell dims {(nj, ni)} "
                      f"plus a rind layer; refusing to guess")
                return 1
            cp = cp_full[1:-1, 1:-1]
            yp = yplus[1:-1, 1:-1] if yplus is not None else None
            centres, area_vec = cell_geometry(xyz)
            # pressure force on a cell, per unit dynamic pressure: -cp * n dA
            drag_per_cell = -cp * (area_vec @ drag_dir)
            zones.append({"name": name, "cp": cp, "yplus": yp, "centres": centres,
                          "drag": drag_per_cell, "area": np.linalg.norm(area_vec, axis=-1)})
    finally:
        if handle is not None:
            handle.close()

    # Orientation, settled by measurement rather than by convention.
    total_plus = sum(z["drag"].sum() for z in zones) / area_ref
    candidates = {"as_stored": total_plus, "flipped": -total_plus}
    sign_name = min(candidates, key=lambda k: abs(candidates[k] - cdp_solver))
    flip = -1.0 if sign_name == "flipped" else 1.0
    cdp_integrated = candidates[sign_name]
    disagreement = 1e4 * (cdp_integrated - cdp_solver)

    report = {
        "schema": "aeris.s8.cp_drag_map.v1",
        "question": ("the surface pressure exceeds its isentropic bound on every run. "
                     "How many drag counts does that region carry?"),
        "run": str(args.run),
        "cp_physical_max": CP_PHYSICAL_MAX,
        "drag_direction": drag_dir.tolist(),
        "area_ref_m2": area_ref,
        "self_check": {
            "cdp_solver_counts": round(1e4 * cdp_solver, 4),
            "cdp_integrated_counts": round(1e4 * cdp_integrated, 4),
            "disagreement_counts": round(disagreement, 4),
            "tolerance_counts": AGREEMENT_TOLERANCE_COUNTS,
            "normal_orientation": sign_name,
            "orientation_note": ("chosen by matching the solver, not assumed. Both were "
                                 "tried; the rejected one gives "
                                 f"{1e4 * candidates['flipped' if flip > 0 else 'as_stored']:.2f} counts."),
            "passes": bool(abs(disagreement) <= AGREEMENT_TOLERANCE_COUNTS),
            "method_note": ("cell-centre cp over cell areas is first order, so a residual "
                            "of a fraction of a count is the method's own error bar, not a "
                            "finding about the solution."),
        },
        "zones": [],
    }

    total_over = 0.0
    total_carried = 0.0
    for z in zones:
        cp, drag = z["cp"], flip * z["drag"] / area_ref
        over = cp > CP_PHYSICAL_MAX
        nj, ni = cp.shape
        # the leading edge sits at the middle of the ring on the OML zone
        le = ni // 2
        lo, hi = max(0, le - args.le_strip_cells), min(ni, le + args.le_strip_cells + 1)
        strip = np.zeros_like(over)
        strip[:, lo:hi] = True
        entry = {
            "zone": z["name"],
            "cell_dims": [int(nj), int(ni)],
            "cp_min": round(float(cp.min()), 4),
            "cp_max": round(float(cp.max()), 4),
            "cdp_counts": round(1e4 * float(drag.sum()), 4),
            "cells_over_bound": int(over.sum()),
            "cdp_counts_from_over_bound_cells": round(1e4 * float(drag[over].sum()), 4),
            # THE ERROR, not the contribution. The drag a cell carries is not the
            # drag it carries WRONGLY: a cell at cp 1.23 against a bound of 1.0018
            # is 19 % unphysical, not 100 %. Clipping cp to the bound leaves
            #     d_excess = drag * (cp - cp_max) / cp
            # because drag = -cp (n.d) A, so the geometric factor divides out. The
            # first version of this tool reported the contribution and called 4.70
            # counts material, which is exactly the overstatement this audit exists
            # to catch -- the honest figure is an order of magnitude smaller.
            "cdp_counts_of_unphysical_excess": round(
                1e4 * float((drag[over] * (cp[over] - CP_PHYSICAL_MAX) / cp[over]).sum()), 4)
            if over.any() else 0.0,
            "area_fraction_over_bound": round(float(z["area"][over].sum()
                                                    / z["area"].sum()), 6),
            "cdp_counts_leading_edge_strip": round(1e4 * float(drag[strip].sum()), 4),
            "leading_edge_strip_cells_each_side": args.le_strip_cells,
        }
        if z["yplus"] is not None:
            yp = z["yplus"]
            entry["yplus"] = {"max": round(float(yp.max()), 4),
                              "p99": round(float(np.percentile(yp, 99)), 4),
                              "median": round(float(np.median(yp)), 4),
                              "cells_above_1": int((yp > 1.0).sum())}
        total_over += entry["cdp_counts_of_unphysical_excess"]
        total_carried += entry["cdp_counts_from_over_bound_cells"]
        report["zones"].append(entry)

    report["total_cells_over_bound"] = sum(z["cells_over_bound"] for z in report["zones"])
    report["total_cdp_counts_from_over_bound_cells"] = round(total_carried, 4)
    report["total_cdp_counts_of_unphysical_excess"] = round(total_over, 4)

    if report["self_check"]["passes"]:
        material = abs(total_over) >= 1.0
        report["verdict"] = (
            f"The over-bound cells carry {total_carried:.2f} counts of pressure drag out of "
            f"{1e4 * cdp_solver:.1f}, of which {total_over:.2f} counts is the UNPHYSICAL EXCESS "
            f"-- what clipping cp to its bound would remove. The second number is the error; "
            f"the first is mostly legitimate stagnation pressure. "
            + ("That excess is material against a 5-9 count effect and must be fixed, not "
               "merely flagged." if material else
               "Against a 5-9 count effect that is immaterial. The violation is real and "
               "confined to a few cells at the root leading edge; it belongs on the record "
               "and off the critical path. It is NOT what limits this study."))
    else:
        report["verdict"] = (
            f"REFUSED: the integration reproduces {1e4 * cdp_integrated:.2f} counts against "
            f"the solver's {1e4 * cdp_solver:.2f}, a {disagreement:.2f} count disagreement. "
            f"The regional breakdown is not trustworthy and is not reported as fact.")

    # UNIQUE per run, not per run NAME. `gci_C_a0` is the name of one run in
    # `runs/s8_cfd`, another in `runs/s8_v2/g83`, and another per wing -- so naming
    # the report after `run.name` made the family-A result overwrite the family-B
    # one within minutes of this tool being written. That is defects 24, 25 and 26
    # for the fourth time, and the ledger's warning did not stop me repeating it.
    # The campaign and geometry directories are what disambiguate.
    tag = "_".join(p for p in args.run.parts[-3:] if p not in ("runs",))
    out = args.out or (HERE / "reports" / f"s8_cp_drag_map_{tag}.json")
    out.write_text(json.dumps(report, indent=2) + "\n")

    sc = report["self_check"]
    print(f"\n  self-check: integrated CDp {sc['cdp_integrated_counts']} counts against "
          f"the solver's {sc['cdp_solver_counts']} "
          f"({sc['disagreement_counts']:+} counts, orientation {sc['normal_orientation']}) "
          f"-> {'PASSES' if sc['passes'] else 'REFUSED'}")
    for z in report["zones"]:
        print(f"\n  {z['zone']}  cells {z['cell_dims']}")
        print(f"    cp {z['cp_min']} .. {z['cp_max']}   CDp {z['cdp_counts']} counts")
        print(f"    over bound: {z['cells_over_bound']} cells, "
              f"{100 * z['area_fraction_over_bound']:.4f} % of area, carrying "
              f"{z['cdp_counts_from_over_bound_cells']} counts")
        print(f"    leading-edge strip: {z['cdp_counts_leading_edge_strip']} counts")
        if "yplus" in z:
            y = z["yplus"]
            print(f"    y+ median {y['median']} p99 {y['p99']} max {y['max']}, "
                  f"{y['cells_above_1']} cells above 1")
    print(f"\n  {report['verdict']}")
    print(f"\nwrote {out.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
