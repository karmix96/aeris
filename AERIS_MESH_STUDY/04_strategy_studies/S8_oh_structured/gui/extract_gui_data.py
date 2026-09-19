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


def mesh(index: int, level: str, decim: int, volume: bool = False,
         sj: int = 2, jcap: int = 40) -> dict | None:
    """Wing surface plus the volume, decimated, with the decimation recorded."""
    for root in (S8 / "runs/s8_v2", S8 / "runs/s8_cloud", S8 / "runs/s8_pilot"):
        f = root / f"g{index}" / f"{level}_blocks.npz"
        if f.exists():
            break
    else:
        return None
    d = np.load(f)
    out = {"level": level, "index": index, "decimation": decim, "blocks": {}}
    for key in d.files:
        a = d[key]
        if a.ndim < 4:
            continue
        ni, nj, nk = a.shape[:3]
        out["blocks"][key] = {"full_shape": [ni, nj, nk],
                              "cells": (ni - 1) * (nj - 1) * (nk - 1)}
    w = d["o_wing"]                       # (i ring, j wall-normal, k span, 3)
    ni, nj, nk = w.shape[:3]
    si, sk = max(1, decim), max(1, decim // 2)
    surf = w[::si, 0, ::sk, :]            # j = 0 is the wall
    out["surface"] = {"shape": list(surf.shape[:2]),
                      "xyz": [round(float(v), 6) for v in surf.reshape(-1)],
                      "note": "j=0 of o_wing: the wall the solver sees"}
    if not volume:
        return out
    # A cut plane the user drags has to exist at every position, not at five
    # of them, so the whole block goes -- decimated in the ring and wall-normal
    # directions but keeping EVERY span station, because span is the axis the
    # chordwise cut slides along. jmax caps how far into the far field we carry:
    # past the boundary layer the cells are metres across and show nothing.
    jmax = min(nj, jcap)
    vol = w[::si, :jmax:sj, :, :]
    out["volume"] = {"shape": list(vol.shape[:3]),
                     "stride": [si, sj, 1],
                     "j_cap": jmax,
                     "xyz": [round(float(v), 5) for v in vol.reshape(-1)],
                     "note": ("o_wing decimated in i and j, every k kept. Cut planes "
                              "index this block directly, so they move continuously "
                              "rather than snapping between a few stored sheets.")}
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

    # gci_C carries the volume: it is the level you inspect, and three volumes
    # would not fit in a page. M and F carry the surface, which is what you
    # compare between levels anyway.
    for level, decim, vol in (("gci_C", 3, True), ("gci_M", 4, False), ("gci_F", 5, False)):
        m = mesh(83, level, decim, volume=vol)
        if m:
            payload["meshes"][level] = m
            v = m.get("volume")
            print(f"  mesh {level}: surface {m['surface']['shape']}"
                  + (f", volume {v['shape']} (j capped at {v['j_cap']})" if v else ""))
    for level in ("gci_C", "gci_M"):
        r = results(83, level)
        if r:
            payload["results"][level] = r
            print(f"  results {level}: {len(r)} angles")
    payload["surface_fields"] = {}
    for alpha in (-2.0, 0.0, 4.0, 8.0):
        sf = surface_field(83, "gci_C", alpha, si=3, sk=1)
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
