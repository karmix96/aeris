"""Write S4's constructed volume as a legacy-VTK hexahedral grid for ParaView.

    .venv/bin/python .../S4_analytic_multiblock/export_s4_volume.py [--geom N]

`shared/export_paraview.py` writes surface quads; this writes the volume, with the
same per-cell arrays so the two are read the same way:

    scaled_quality   ADR-0014 V4, minimum corner scaled Jacobian. NEGATIVE = folded.
    cell_volume      signed hex volume, mesh-wide orientation applied.
    block_id         integer index of the source block.
    is_tip           1 for tip-cap blocks, 0 for the wing's own boundary layer.

To inspect: colour by `scaled_quality`, `Threshold -1 to 0` isolates every folded
cell. On this mesh that threshold lands entirely on the tip cap, which is the
result S4 is reporting.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _p in (str(REPO_ROOT / "src"), str(STUDIES), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import strategy_s4 as S4  # noqa: E402
import volume_s4 as V4  # noqa: E402
from shared import geometry_sets, volume_qc  # noqa: E402

from aeris.cfd.meshing.volume_audit import signed_cell_volumes  # noqa: E402

OUT = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/paraview_inspection/S4_volume"


def write_volume_vtk(path: Path, blocks: dict, orientation: float) -> dict:
    pts, cells, quality, volumes, block_id, is_tip = [], [], [], [], [], []
    offset = 0
    for bid, (name, arr) in enumerate(sorted(blocks.items())):
        a = np.asarray(arr, dtype=float)
        nk, nj, ni = a.shape[:3]
        pts.append(a.reshape(-1, 3))

        idx = np.arange(nk * nj * ni).reshape(nk, nj, ni) + offset
        c = np.stack(
            [
                idx[:-1, :-1, :-1], idx[:-1, :-1, 1:], idx[:-1, 1:, 1:], idx[:-1, 1:, :-1],
                idx[1:, :-1, :-1], idx[1:, :-1, 1:], idx[1:, 1:, 1:], idx[1:, 1:, :-1],
            ],
            axis=-1,
        ).reshape(-1, 8)
        cells.append(c)

        q = volume_qc.hex_scaled_jacobian(a, orientation=orientation).ravel()
        v = (orientation * signed_cell_volumes(a)).ravel()
        quality.append(q)
        volumes.append(v)
        block_id.append(np.full(q.size, bid, dtype=int))
        is_tip.append(np.full(q.size, 1 if name.startswith("tip") else 0, dtype=int))
        offset += nk * nj * ni

    P = np.concatenate(pts)
    C = np.concatenate(cells)
    Q = np.concatenate(quality)
    V = np.concatenate(volumes)
    B = np.concatenate(block_id)
    T = np.concatenate(is_tip)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write("# vtk DataFile Version 3.0\nS4 constructed boundary-layer volume\n")
        f.write("ASCII\nDATASET UNSTRUCTURED_GRID\n")
        f.write(f"POINTS {len(P)} float\n")
        np.savetxt(f, P, fmt="%.9g")
        f.write(f"\nCELLS {len(C)} {len(C) * 9}\n")
        np.savetxt(f, np.hstack([np.full((len(C), 1), 8, dtype=int), C]), fmt="%d")
        f.write(f"\nCELL_TYPES {len(C)}\n")
        np.savetxt(f, np.full(len(C), 12, dtype=int), fmt="%d")
        f.write(f"\nCELL_DATA {len(C)}\n")
        for name, data, kind in (
            ("scaled_quality", Q, "float"), ("cell_volume", V, "float"),
            ("block_id", B, "int"), ("is_tip", T, "int"),
        ):
            f.write(f"SCALARS {name} {kind} 1\nLOOKUP_TABLE default\n")
            np.savetxt(f, data, fmt="%.9g" if kind == "float" else "%d")
    return {"points": len(P), "cells": len(C), "min_quality": float(Q.min()),
            "folded_cells": int((Q <= 0).sum())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geom", type=int, default=0)
    ap.add_argument("--level", default="smoke")
    a = ap.parse_args()

    gid = geometry_sets.geometry_id("lhs100_seed42", a.geom)
    wing = geometry_sets.wing("lhs100_seed42", a.geom)
    blocks, _info = S4.build_surface(wing, level="L2_smoke")
    s0 = V4.S0_for(blocks, a.level)
    vol, vinfo = V4.build_volume(
        wing, blocks, bl_points=S4.LEVELS["L2_smoke"]["bl_points"], s0=s0
    )
    rep = volume_qc.volume_report(vol)
    path = OUT / f"S4_{gid}_volume_{a.level}.vtk"
    info = write_volume_vtk(path, vol, rep["orientation"])

    print(f"{path}")
    for k, v in info.items():
        print(f"  {k:16s} {v}")
    print(f"  delta range      {vinfo['delta_range_m']}")
    print(f"  s0               {s0:.4e} m")
    print("\nColour by `scaled_quality`; Threshold -1..0 isolates the folded cells.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
