#!/usr/bin/env python3
"""Pull the real S8 data the GUI shows, into one JSON the browser can hold.

Nothing here is invented. The airfoils are the database files the generator
loads, the mesh is the node array the solver was handed, the forces and surface
fields are what ADflow wrote, and the level definitions are read from
strategy_s8 rather than retyped. Where the GUI cannot show the real thing --
the pyGeo B-spline loft, which needs pyGeo -- it says so rather than pretending.

The volume is decimated for the browser: the full gci_C wing block is 296k
nodes, and a page that has to hold four levels of that will not open on a
laptop. Every decimation factor is recorded beside the data it applies to.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
S8 = HERE.parent
REPO = S8.parents[2]
sys.path.insert(0, str(S8))
sys.path.insert(0, str(S8.parent))

AIRFOILS = REPO / "data/airfoil_database"
OUT = HERE / "s8_gui_data.json"


def airfoil(name: str) -> dict:
    """Coordinates as the generator reads them: Selig order, x from 1 to 0 to 1."""
    rows = []
    for line in (AIRFOILS / f"{name}.dat").read_text().splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            rows.append([float(parts[0]), float(parts[1])])
        except ValueError:
            continue
    a = np.array(rows)
    return {"name": name, "n": len(a), "xy": [[round(x, 6), round(y, 6)] for x, y in a]}


def design_variables() -> dict:
    from shared.geometry_sets import design_matrix
    X, names = design_matrix("lhs100_seed42")
    return {
        "names": list(names),
        "bounds": [[float(X[:, i].min()), float(X[:, i].max())] for i in range(X.shape[1])],
        "designs": {str(i): [round(float(v), 5) for v in X[i]] for i in range(X.shape[0])},
        "note": "the 100-design LHS the campaign samples; g83 is the reference wing",
    }


def levels() -> dict:
    import strategy_s8 as s
    import dataclasses
    out = {}
    for name in ("gci_C", "gci_M", "gci_F", "gci_FF"):
        d = dataclasses.asdict(s.LEVELS[name])
        out[name] = {k: d[k] for k in
                     ("n_side", "n_base", "n_span", "n_normal", "ds_te_frac",
                      "s0_frac", "farfield_chords", "target_le_turn_deg",
                      "le_span_growth_max", "tip_span_first_cell_in_s0")
                     if k in d}
    return {"levels": out, "ratio": 1.3,
            "note": "read from strategy_s8.LEVELS, not retyped"}


def f32(a: np.ndarray) -> str:
    """Float32, base64. Text JSON costs about seven bytes a number; this costs
    5.33, it is exact to single precision, and the browser gets a typed array
    without parsing a million strings."""
    import base64
    return base64.b64encode(np.ascontiguousarray(a, dtype="<f4").tobytes()).decode()


def mesh(index: int, level: str, jcap: int | None) -> dict | None:
    """The wing block at FULL resolution.

    The first version of this strided the ring and the span to keep the payload
    small. That was wrong in a way that matters: a structured mesh puts its
    points where the geometry turns -- packed at the leading edge, at the
    trailing edge and around the tip -- and a uniform stride throws away exactly
    that packing. The mesh came out looking evenly spaced, which is the one
    thing it is not, and the whole point of looking at it is to see the
    clustering. Full surfaces cost 0.07-0.21 MB. There was never a reason.

    `jcap` limits how far into the far field the volume is carried. Past the
    boundary layer the cells are metres across and carry nothing you would look
    at; the cap is recorded so the view can say what it is not showing.
    """
    for root in (S8 / "runs/s8_v2", S8 / "runs/s8_cloud", S8 / "runs/s8_pilot"):
        f = root / f"g{index}" / f"{level}_blocks.npz"
        if f.exists():
            break
    else:
        return None
    d = np.load(f)
    out = {"level": level, "index": index, "blocks": {}}
    for key in d.files:
        a = d[key]
        if a.ndim >= 4:
            ni, nj, nk = a.shape[:3]
            out["blocks"][key] = {"shape": [ni, nj, nk],
                                  "cells": (ni - 1) * (nj - 1) * (nk - 1)}
    # the real total, from the build's own summary, not a formula
    s = f.with_name(f"{level}_summary.json")
    if s.exists():
        sd = json.loads(s.read_text())
        out["cells_total"] = int(sd["cells"])
        out["folded"] = int(sd["negative_cells_all_blocks"])
        out["wall_layer_error_m"] = float(sd["volume"]["wall_layer_error_m"])

    w = d["o_wing"]
    ni, nj, nk = w.shape[:3]
    out["surface"] = {"shape": [ni, nk], "f32": f32(w[:, 0, :, :].reshape(-1)),
                      "note": "j=0 of o_wing at full resolution: the wall the solver sees"}
    # the tip cap, so the tip clustering is actually visible
    if "cap_out" in d.files:
        c = d["cap_out"]
        out["cap"] = {"shape": [c.shape[0], c.shape[1]],
                      "f32": f32(c[:, :, 0, :].reshape(-1)),
                      "note": "k=0 of cap_out: the tip cap face"}
    if jcap:                       # 0 or None: no volume. -1: the whole block.
        j = nj if jcap < 0 else min(nj, jcap)
        out["volume"] = {"shape": [ni, j, nk], "j_cap": j, "j_full": nj,
                         "f32": f32(w[:, :j, :, :].reshape(-1)),
                         "note": ("full ring and span, wall-normal capped. Cut planes "
                                  "index this directly, so the leading-edge, trailing-edge "
                                  "and tip clustering is the mesh's own.")}
    return out


def results(index: int, level: str) -> dict:
    out = {}
    for alpha in (-2.0, 0.0, 4.0, 8.0):
        for root in (S8 / "runs/s8_v2", S8 / "runs/s8_hf"):
            r = root / f"g{index}" / f"{level}_a{alpha:g}" / "result.json"
            if r.exists():
                d = json.loads(r.read_text())
                f = {k.rsplit("_", 1)[-1]: v for k, v in (d.get("functions") or {}).items()}
                out[f"{alpha:g}"] = {
                    "CL": f.get("cl"), "CD": f.get("cd"), "CDp": f.get("cdp"),
                    "CDv": f.get("cdv"), "CMy": f.get("cmy"),
                    "iterations": d.get("iterations_completed"),
                    "relative_residual": d.get("relative_residual"),
                    "converged": d.get("converged"),
                    "area_ref_m2": d.get("area_ref_m2"),
                    "solver": d.get("solver_options_effective"),
                    "mission": d.get("mission")}
                break
    return out


def surface_field(index: int, level: str, alpha: float, si: int, sk: int) -> dict | None:
    """cp, cf and y+ ON the wing grid, so they can be painted on the mesh.

    ADflow writes the wall zone cell-centred with one rind layer each side, and
    transposed: for gci_C the array is (50, 94) against a wall of 92 i-cells by
    48 k-cells. Stripping the rind and transposing puts every value on the cell
    it belongs to, which is what makes a contour plot mean something rather than
    being a pretty texture.
    """
    import cgns_read
    for root in (S8 / "runs/s8_v2", S8 / "runs/s8_hf"):
        run = root / f"g{index}" / f"{level}_a{alpha:g}"
        surf = sorted(run.glob("*surf*.cgns"))
        if surf:
            break
    else:
        return None
    blocks = None
    for root in (S8 / "runs/s8_v2", S8 / "runs/s8_cloud"):
        b = root / f"g{index}" / f"{level}_blocks.npz"
        if b.exists():
            blocks = np.load(b)
            break
    if blocks is None:
        return None
    ni, _, nk = blocks["o_wing"].shape[:3]
    want = (nk - 1 + 2, ni - 1 + 2)               # cells plus one rind each side

    zones = cgns_read.surface_zones(surf[0])
    out = {"alpha_deg": alpha, "level": level,
           "grid": [len(range(0, ni - 1, si)), len(range(0, nk - 1, sk))],
           "note": ("cell values on the wing wall, rind stripped and transposed onto "
                    "the same (i,k) grid as the surface geometry")}
    for var, key in (("CoefPressure", "cp"),
                     ("SkinFrictionMagnitude", "cf"),
                     ("YPlus", "yplus")):
        found = None
        for name, z in zones:
            if "Wall" not in name:
                continue
            sol = z.get("Flow solution", {})
            if var not in sol:
                continue
            a = np.asarray(sol[var][" data"])
            if a.shape == want:
                found = a[1:-1, 1:-1].T           # -> (i cells, k cells)
                break
        if found is None:
            continue
        sub = found[::si, ::sk]
        out[key] = {"shape": list(sub.shape),
                    "min": float(found.min()), "max": float(found.max()),
                    "values": [round(float(x), 5) for x in sub.reshape(-1)]}
    return out if len(out) > 3 else None


def main() -> int:
    payload = {
        "schema": "aeris.s8.gui_data.v1",
        "provenance": {
            "repo_commit": None,
            "note": ("every number here is read from the project's own files: airfoil "
                     "coordinates from data/airfoil_database, design vectors from "
                     "shared.geometry_sets, level definitions from strategy_s8.LEVELS, "
                     "meshes from the node arrays the solver was handed, forces and "
                     "surface fields from what ADflow wrote."),
        },
        "airfoils": {n: airfoil(n) for n in ("mh91", "e374", "nlf1015")},
        "design": design_variables(),
        "levels": levels(),
        "meshes": {},
        "results": {},
    }
    import subprocess
    try:
        payload["provenance"]["repo_commit"] = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=15).stdout.strip() or None
    except Exception:  # noqa: BLE001
        pass

    # Full surfaces for every level -- they are tiny and they are where the
    # leading-edge, trailing-edge and tip clustering shows. Volumes for the two
    # levels you would actually slice.
    for level, jcap in (("gci_C", -1), ("gci_M", 40), ("gci_F", 0)):
        m = mesh(83, level, jcap)
        if m:
            payload["meshes"][level] = m
            v = m.get("volume")
            print(f"  mesh {level}: surface {m['surface']['shape']} FULL"
                  + (f", volume {v['shape']} (j {v['j_cap']}/{v['j_full']})" if v else ", surface only")
                  + f", {m.get('cells_total', 0):,} cells")
    for level in ("gci_C", "gci_M"):
        r = results(83, level)
        if r:
            payload["results"][level] = r
            print(f"  results {level}: {len(r)} angles")
    payload["surface_fields"] = {}
    for alpha in (-2.0, 0.0, 4.0, 8.0):
        sf = surface_field(83, "gci_C", alpha, si=1, sk=1)
        if sf:
            payload["surface_fields"][f"{alpha:g}"] = sf
    if payload["surface_fields"]:
        one = next(iter(payload["surface_fields"].values()))
        print(f"  surface fields: {len(payload['surface_fields'])} angles, "
              f"{[k for k in one if isinstance(one[k], dict)]} on a {one['grid']} grid")

    OUT.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"\n  wrote {OUT}  ({OUT.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
