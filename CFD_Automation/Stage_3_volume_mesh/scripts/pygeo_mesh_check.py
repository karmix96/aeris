"""The surface and volume meshes on the pyGeo loft against the numpy loft (a weak point of 11 Nov: every Stage 2 and 3
mesh here was built on the numpy twin; on 8 Nov only the 20 reference surfaces were compared on pyGeo). Needs pyGeo
(Mike's machine). Per wing, Re and level: both lofts, the same input hash, the same counts and checks, and how far
apart the nodes are.

    python scripts/pygeo_mesh_check.py                            # the 20 reference wings, VC, Re 3e5 (about 10 min)
    python scripts/pygeo_mesh_check.py --levels VC C --res 1e5 3e5 1e6 4e6
    python scripts/pygeo_mesh_check.py --backends numpy numpy      # tests this script without pyGeo (must be 0)

-> data/studies/pygeo_mesh_check.json (rows and a summary); prints one line per mesh. Expected: the same counts on
every mesh, every check passing on both, nodes apart by round-off (the 8 Nov surfaces: 6e-10 in turning, degrees).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ruleset import CONFIG                                     # noqa: E402
sys.path.insert(0, str(HERE.parent))
from cfdauto.geometry.loft import pygeo_available               # noqa: E402
from cfdauto.mesh.surface import _jsonable, build_surface, wing_from_set   # noqa: E402
from cfdauto.volume.volume import build_volume                  # noqa: E402

TYPES = ("bwb", "flying_wing", "cranked", "tapered")


def compare(a: dict, b: dict) -> dict:
    """Same block names and shapes, and the largest node distance [mean chords] (None if the shapes differ)."""
    same = sorted(a) == sorted(b) and all(a[k].shape == b[k].shape for k in a)
    d = max(float(np.abs(a[k] - b[k]).max()) for k in a) if same else None
    return {"same_shapes": same, "max_node_difference": d}


def one(t: str, i: int, re: float, lev: str, backends: tuple[str, str]) -> dict:
    t0 = time.time()
    w = [wing_from_set(t, "reference", i, backend=bk) for bk in backends]
    s = [build_surface(x.loft, re, lev) for x in w]
    v = [build_volume(x, config=CONFIG) if x.passed else None for x in s]
    surf = compare({"wing": s[0].wing, "cap": s[0].cap}, {"wing": s[1].wing, "cap": s[1].cap})
    row = {"type": t, "index": i, "re": re, "level": lev, "backends": list(backends),
           "loft_backends_got": [x.loft.backend for x in w],
           "same_input_hash": w[0].input_hash == w[1].input_hash,
           "surface_passed": [bool(x.passed) for x in s], "surface_failed": [[c.name for c in x.failed()] for x in s],
           "surface_same_shapes": surf["same_shapes"], "surface_max_node_difference": surf["max_node_difference"],
           "n_ring": [int(x.wing.shape[0]) for x in s], "n_span": [int(x.wing.shape[1]) for x in s]}
    if all(v):
        vol = compare(v[0].blocks, v[1].blocks)
        row |= {"volume_passed": [bool(x.passed) for x in v], "volume_failed": [[c.name for c in x.failed()] for x in v],
                "cells": [x.cells for x in v], "volume_same_shapes": vol["same_shapes"],
                "volume_max_node_difference": vol["max_node_difference"],
                "min_sj": [x.info.get("min_sj_but_cap_nose_corners") for x in v]}
    else:
        row |= {"volume_passed": None, "note": "a surface was refused: no volume"}
    row["same"] = bool(row["same_input_hash"] and row["surface_same_shapes"] and row.get("volume_same_shapes")
                       and row["surface_passed"][0] == row["surface_passed"][1]
                       and row.get("volume_passed") is not None and row["volume_passed"][0] == row["volume_passed"][1])
    row["seconds"] = round(time.time() - t0, 1)
    return row


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--levels", nargs="+", default=["VC"], choices=["VC", "C", "M", "F"])
    p.add_argument("--res", nargs="+", type=float, default=[3e5])
    p.add_argument("--types", nargs="+", default=list(TYPES), choices=list(TYPES))
    p.add_argument("--indices", nargs="+", type=int, default=[0, 1, 2, 3, 4])
    p.add_argument("--backends", nargs=2, default=["numpy", "pygeo"], choices=["numpy", "pygeo"])
    p.add_argument("--out", default=str(HERE / "data" / "studies" / "pygeo_mesh_check.json"))
    a = p.parse_args(argv)
    if "pygeo" in a.backends and not pygeo_available():
        raise SystemExit("pyGeo is not importable in this Python: activate the AERIS .venv (conda activate <repo>/.venv)")
    rows = []
    for lev in a.levels:
        for re in a.res:
            for t in a.types:
                for i in a.indices:
                    r = one(t, i, re, lev, tuple(a.backends))
                    rows.append(r)
                    print(f"{t:11s} {i}  Re {re:.0e}  {lev:3s}  same {r['same']}  cells {r.get('cells')}  "
                          f"surface {r['surface_max_node_difference']}  volume {r.get('volume_max_node_difference')}  "
                          f"passed {r['surface_passed']} {r.get('volume_passed')}  {r['seconds']} s", flush=True)
    dv = [r["volume_max_node_difference"] for r in rows if r.get("volume_max_node_difference") is not None]
    ds = [r["surface_max_node_difference"] for r in rows if r.get("surface_max_node_difference") is not None]
    summary = {"meshes": len(rows), "same": sum(r["same"] for r in rows),
               "both_passed": sum(1 for r in rows if r.get("volume_passed") == [True, True]),
               "surface_max_node_difference": max(ds) if ds else None,
               "volume_max_node_difference": max(dv) if dv else None,
               "backends": a.backends, "levels": a.levels, "res": a.res,
               "conclusion": None}
    summary["conclusion"] = ("the same meshes on both lofts, nodes apart by round-off"
                             if summary["same"] == len(rows) and (summary["volume_max_node_difference"] or 0) < 1e-6
                             else "NOT the same on every mesh: see the rows")
    Path(a.out).write_text(json.dumps(_jsonable({"summary": summary, "rows": rows}), indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
