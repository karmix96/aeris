#!/usr/bin/env python
"""Turn the S8 O-H blocks into an ADflow-ready CGNS file with boundary conditions.

Runs under the MACH-Aero interpreter, not the project venv, because
`cgnsutilities` needs libcgns and the venv cannot load it:

    /home/mike/miniconda3/envs/mach-aero/bin/python \
        AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/write_cgns.py \
        --blocks AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh/oh_L3_blocks.npz

Boundary conditions, with (i, j, k) = (xi around the ring, eta wall-normal,
zeta spanwise):

    o_wing   jMin  bcwallviscous     wall   the OML
             jMax  bcfarfield        far
             kMin  bcsymmetryplane   sym    the root plane, planar to 8e-18 m
             kMax  ->  o_out kMin           block-to-block
             iMin/iMax  -> each other       the ring's periodic seam
    o_out    jMin  ->  cap_out sides        block-to-block
             jMax  bcfarfield        far
             kMax  bcfarfield        far    the outboard end
    cap_out  kMin  bcwallviscous     wall   the tip cap
             kMax  bcfarfield        far
             i/j sides -> o_out jMin        block-to-block

Everything not given a BC here has to be picked up by `split` and `connect` as a
block-to-block match.  The script checks afterwards that no face was left
unclaimed, because an unclaimed face is a hole in the domain that ADflow will
either reject or, worse, silently treat as a wall.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from cgnsutilities.cgnsutilities import Block, Boco, Grid

WALL = "bcwallviscous"
FAR = "bcfarfield"
SYM = "bcsymmetryplane"


def face_ranges(dims):
    ni, nj, nk = dims
    return {
        "iMin": [[1, 1], [1, nj], [1, nk]],
        "iMax": [[ni, ni], [1, nj], [1, nk]],
        "jMin": [[1, ni], [1, 1], [1, nk]],
        "jMax": [[1, ni], [nj, nj], [1, nk]],
        "kMin": [[1, ni], [1, nj], [1, 1]],
        "kMax": [[1, ni], [1, nj], [nk, nk]],
    }


#: face -> (bc type, family).  Faces absent here must be resolved by `connect`.
BCS = {
    "o_wing": {"jMin": (WALL, "wall"), "jMax": (FAR, "far"), "kMin": (SYM, "sym")},
    "o_out": {"jMax": (FAR, "far"), "kMax": (FAR, "far")},
    "cap_out": {"kMin": (WALL, "wall"), "kMax": (FAR, "far")},
}
ORDER = ("o_wing", "o_out", "cap_out")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--blocks", type=Path, required=True,
                    help="the *_blocks.npz written by build_volume.py")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--tol", type=float, default=1.0e-10)
    args = ap.parse_args()

    data = np.load(args.blocks)
    out = args.out or args.blocks.with_name(args.blocks.name.replace("_blocks.npz", "_volume.cgns"))

    grid = Grid()
    grid.cellDim = 3
    report = {"blocks": {}, "checks": {}}
    for name in ORDER:
        if name not in data:
            continue
        arr = np.asarray(data[name], dtype=float)
        dims = list(arr.shape[:3])
        coords = np.asfortranarray(arr)
        block = Block(name, dims, coords)
        ranges = face_ranges(dims)
        for face, (bc, family) in BCS[name].items():
            block.addBoco(Boco(face, bc, np.array(ranges[face]), family))
        grid.addBlock(block)
        report["blocks"][name] = {
            "dims": dims,
            "cells": int(np.prod(np.array(dims) - 1)),
            "explicit_bcs": {f: list(v) for f, v in BCS[name].items()},
        }

    # the root plane must actually be a plane before it is called a symmetry plane
    root = np.asarray(data["o_wing"])[:, :, 0, 1]
    report["checks"]["root_plane_y_spread_m"] = float(np.ptp(root))
    report["checks"]["root_plane_y_max_abs_m"] = float(np.abs(root).max())

    grid.split([])
    grid.connect(args.tol)

    n_b2b = sum(len(b.B2Bs) for b in grid.blocks)
    n_boco = sum(len(b.bocos) for b in grid.blocks)
    report["checks"]["block_to_block_connections"] = int(n_b2b)
    report["checks"]["boundary_conditions"] = int(n_boco)

    grid.writeToCGNS(str(out))
    report["cgns"] = str(out)
    report["total_cells"] = sum(b["cells"] for b in report["blocks"].values())
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
