#!/usr/bin/env python3
"""Build and verify every mesh the cloud batch will solve, BEFORE renting a machine.

The cloud rebuilds these itself -- the mesher is 45 s and 1.7 GiB, so shipping
gigabytes of CGNS is the wrong trade. What this does is prove, here, that every
one of the eleven meshes builds clean: zero folded cells and the wall layer on
the loft. Discovering a folded gci_FF after the meter has started is the failure
this exists to prevent.
"""
from __future__ import annotations
import json, subprocess, sys, time, resource
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import env_s8

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / "runs/s8_cloud"
VENV = ROOT / ".venv/bin/python"
INDICES = [12, 13, 16, 23, 29, 36, 47, 65, 81, 83]

WORK = [("gci_F", i) for i in INDICES] + [("gci_FF", 83)]


def build(level: str, index: int) -> dict:
    out = OUT / f"g{index}"
    out.mkdir(parents=True, exist_ok=True)
    summary = out / f"{level}_summary.json"
    t0 = time.time()
    before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    if not summary.exists():
        cmd = [str(VENV), str(HERE / "build_volume.py"), "--level", level,
               "--index", str(index), "--out", str(out)]
        with open(out / f"{level}_build.log", "w") as fh:
            rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT).returncode
        if rc != 0 or not summary.exists():
            return {"level": level, "index": index, "BUILD_FAILED": True,
                    "log": str(out / f"{level}_build.log")}
    # Write the CGNS as well. build_volume.py produces block ARRAYS; the solver
    # reads a CGNS, and nothing else in the cloud path creates one. Without this
    # the batch builds eleven clean meshes on the rented machine and then fails
    # on its first case with a missing grid -- after the meter has started.
    # Found on 2026-09-19 by checking that the files the batch needs exist,
    # rather than that the build reported success.
    cgns = out / f"{level}_volume.cgns"
    if not cgns.exists():
        env = env_s8.resolve()
        cmd = [env["mach_python"], str(HERE / "write_cgns.py"),
               "--blocks", str(out / f"{level}_blocks.npz")]
        with open(out / f"{level}_cgns.log", "w") as fh:
            rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT).returncode
        if rc != 0 or not cgns.exists():
            return {"level": level, "index": index, "CGNS_FAILED": True,
                    "log": str(out / f"{level}_cgns.log")}
    wall = time.time() - t0
    peak = max(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss, before) / 1048576
    d = json.loads(summary.read_text())
    # the .vtk previews are 150 MB a mesh and nothing downstream reads them
    for junk in out.glob(f"{level}_*.vtk"):
        junk.unlink()
    rec = {"level": level, "index": index, "cells": d["cells"],
           "folded": d["negative_cells_all_blocks"],
           "wall_layer_error_m": d["volume"]["wall_layer_error_m"],
           "blocks": {k: v["shape"] for k, v in d["blocks"].items()},
           "build_seconds": round(wall, 1), "build_peak_gib": round(peak, 2)}
    rec["cgns"] = str(cgns)
    rec["cgns_bytes"] = cgns.stat().st_size if cgns.exists() else None

    # CELL CONDITIONING, added 2026-09-22. A fold count cannot see it.
    #
    # This preflight declared eleven meshes clean on `folded == 0` and the wall layer,
    # and the 100- and 61-design robustness screens record the same two things. None of
    # them records a scaled Jacobian -- and measured across the family the WORST cell
    # degrades about 1.4x per level while every metric here IMPROVES:
    #
    #     gci_C 0.0090   gci_M 0.0063   gci_F 0.0043   gci_FF 0.0025
    #     median          0.944         0.950  0.954         0.957
    #
    # So "0 folded, clean: True" is true and silent about the one quantity a linear
    # solver actually feels (reports/s8_mesh_quality_ladder.json). That is PLAN 0.1
    # inverted: on defect 21 every metric being checked was unchanged while the wing
    # MOVED, because the metrics measured shape and nothing measured position; here they
    # measure the bulk and nothing measures the worst cell.
    #
    # Reported, NOT gated. The most poorly conditioned mesh of this family yet solved
    # (0.0073) converges to the 1e-6 stopping rule and is gate-ACCEPTED, so there is no
    # measured threshold to gate on and inventing one would refuse meshes that work.
    # A trend to watch, with the number attached.
    try:
        import numpy as np
        import compare_meshes
        blocks = np.load(out / f"{level}_blocks.npz")
        worst, below = float("inf"), 0
        for name in blocks.files:
            b = blocks[name]
            if b.ndim != 4:
                continue
            sj = compare_meshes.scaled_jacobian(b)
            worst = min(worst, float(sj.min()))
            below += int((sj < 0.01).sum())
        rec["scaled_jacobian_min"] = round(worst, 6)
        rec["cells_below_scaled_jacobian_0p01"] = below
    except Exception as exc:                        # noqa: BLE001 - report, never hide
        rec["scaled_jacobian_min"] = None
        rec["scaled_jacobian_why_absent"] = f"{type(exc).__name__}: {exc}"

    # "clean" must mean the batch can actually USE this mesh, which requires the
    # CGNS to exist, not only that the block arrays are valid.
    rec["clean"] = (rec["folded"] == 0 and rec["wall_layer_error_m"] <= 1e-9
                    and cgns.exists())
    # ANK-only memory law, fitted on this host, with the 5 % cell-variation margin
    rec["solve_gib_ank_only"] = round((2.69 + 7.23 * d["cells"] / 1e6) * 1.05, 1)
    return rec


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    for level, index in WORK:
        r = build(level, index)
        records.append(r)
        if r.get("BUILD_FAILED") or r.get("CGNS_FAILED"):
            what = "BUILD FAILED" if r.get("BUILD_FAILED") else "CGNS WRITE FAILED"
            print(f"  g{index:<3} {level:7s} {what} -- see {r['log']}", flush=True)
            continue
        flag = "clean" if r["clean"] else "*** NOT CLEAN ***"
        print(f"  g{index:<3} {level:7s} {r['cells']:>9,} cells  {r['build_seconds']:>5.1f} s  "
              f"{r['solve_gib_ank_only']:>5.1f} GiB to solve  {flag}", flush=True)
    ok = [r for r in records if r.get("clean")]
    report = HERE / "reports/s8_cloud_meshes.json"
    report.write_text(json.dumps({
        "schema": "aeris.s8.cloud_mesh_manifest.v1",
        "built_on": "development host, for verification only; the cloud rebuilds from the same commit",
        "meshes": records,
        "all_clean": len(ok) == len(records),
        "total_cells": sum(r["cells"] for r in ok),
    }, indent=2) + "\n")
    print(f"\n  {len(ok)} of {len(records)} clean")
    print(f"  wrote {report}")
    return 0 if len(ok) == len(records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
