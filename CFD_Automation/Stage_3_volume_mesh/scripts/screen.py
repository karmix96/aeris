"""The volume screen: build and judge volume meshes (no mesh files written; one JSON row per mesh).

    python scripts/screen.py --sets reference --re 1e5 3e5 1e6 4e6 --levels VC --tag ref_VC        # V2, V3
    python scripts/screen.py --sets training_focus training_full corner1 corner2 --levels VC --types bwb cranked --tag s_bc
    python scripts/screen.py --sets reference --levels C M --re 3e5 --tag ref_CM                     # V4
    python scripts/screen.py --count --levels F --tag F_all                                          # F counted, not built
    python scripts/screen.py --only tapered:4 flying_wing:2 --tag ref_VC_rerun                       # some wings again
    python scripts/screen.py --sets training_focus training_full corner1 corner2 --count --levels F --sample 0.1 --tag F_sample

A row: the wing, the level, the Re, the outcome (passed / refused / needs review), every check with its value, the
cells (by part), RAM, the plane-grid counts, the quality by block, and the V2/V3 measurements: the in-plane angle at
the nose and off the base, the smallest scaled Jacobian of the cells next to the base and the trailing-edge corners,
the cells at the tip-vortex path. Failures stay in the file (a crash is a row with the error). Rows go to
data/studies/screen_<tag>.jsonl; --resume skips the rows already there.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ruleset import CONFIG, PREFIX  # noqa: E402
sys.path.insert(0, str(HERE.parent))

from cfdauto.geometry.build import load_set                                 # noqa: E402
from cfdauto.mesh.surface import _jsonable, build_family, build_surface, wing_from_set      # noqa: E402
from cfdauto.paths import re_levels                                         # noqa: E402
from cfdauto.volume import march as mr                                      # noqa: E402
from cfdauto.volume.checks import cell_quality_map                          # noqa: E402
from cfdauto.volume.volume import build_volume, count_volume                # noqa: E402

TYPES = ("bwb", "flying_wing", "cranked", "tapered")
VORTEX_ALPHAS = (-5.0, 4.0, 12.0, 20.0)
VORTEX_DIST = (0.5, 1.0, 2.0)


def extra(vm) -> dict:
    """The V2 and V3 measurements on one mesh."""
    B = vm.blocks
    P = vm._plane
    sts, lay = P["sts"], P["lay"]
    out = {}
    # nose: the in-plane angle of the first line at the nose-arc nodes (CN), against the ring's bisector normal
    worst_nose, worst_base = 0.0, 0.0
    for k, st in enumerate(sts):
        ring = st.ring[: lay.n_air]
        nrm = mr.line_normals(ring)
        a = lay.blocks()["CN"][0] - lay.i_te_up
        G = B["CN_in"][:, :, k]
        v = mr.unit(G[:, 1, [0, 2]] - G[:, 0, [0, 2]])
        ang = np.degrees(np.arccos(np.clip((v * nrm[a: a + G.shape[0]]).sum(1), -1, 1)))
        worst_nose = max(worst_nose, float(ang.max()))
        # base: the first streamwise line off every base node against the base normal
        Gb = B["B_in"][:, :, k]
        base = Gb[:, 0, [0, 2]]
        ub = mr.unit(base[-1] - base[0])
        nb = np.array([ub[1], -ub[0]])
        vb = mr.unit(Gb[:, 1, [0, 2]] - Gb[:, 0, [0, 2]])
        worst_base = max(worst_base, float(np.degrees(np.arccos(np.clip(vb @ nb, -1, 1))).max()))
    out["nose_wall_angle_deg"] = worst_nose
    out["base_wall_angle_deg"] = worst_base
    # cells next to the base and at the trailing-edge corners (first 10 layers), inboard
    nb_ = 10
    qb = cell_quality_map(B["B_in"][:, : nb_ + 1])
    qc = min(float(cell_quality_map(B["CU_in"][:6, : nb_ + 1]).min()), float(cell_quality_map(B["CL_in"][-6:, : nb_ + 1]).min()),
             float(cell_quality_map(B["WU_in"][-6:, : nb_ + 1]).min()), float(cell_quality_map(B["WL_in"][:6, : nb_ + 1]).min()))
    out["base_cells_min_sj"] = float(qb.min())
    out["te_corner_cells_min_sj"] = qc
    # the spacing jump across the trailing-edge line at the wall: the wing's last chordwise cell / the first cell
    # behind the base
    jumps = []
    for k, st in enumerate(sts):
        h_te = np.linalg.norm(B["CU_in"][1, 0, k] - B["CU_in"][0, 0, k])
        h_w = np.linalg.norm(B["WU_in"][-1, 0, k] - B["WU_in"][-2, 0, k])
        jumps.append(h_te / h_w)
    out["te_jump_ratio_max"] = float(max(jumps))
    # the tip-vortex path: from the tip trailing edge, at the angles, at distances behind; the cell there
    tip = sts[-1]
    xte, zte = tip.wake.M
    WU, WL, Bo = B["WU_out"][:, :, 0], B["WL_out"][:, :, 0], B["B_out"][:, :, 0]
    y_in = np.array([s.y for s in sts])
    y_out = np.array(vm.info["y_out"])
    gaps_near = np.concatenate([np.diff(y_in)[-30:], np.diff(y_out)[:30]])
    pts = []
    for d in VORTEX_DIST:
        for a in VORTEX_ALPHAS:
            x, z = xte + d, zte + d * np.tan(np.radians(a))
            best = None
            for G in (WU, WL):
                P2 = G[:, :, [0, 2]]
                dist = np.hypot(P2[..., 0] - x, P2[..., 1] - z)
                i, j = np.unravel_index(np.argmin(dist), dist.shape)
                i2, j2 = min(i, G.shape[0] - 2), min(j, G.shape[1] - 2)
                hx = np.linalg.norm(G[i2 + 1, j2, [0, 2]] - G[i2, j2, [0, 2]])
                hz = np.linalg.norm(G[i2, j2 + 1, [0, 2]] - G[i2, j2, [0, 2]])
                if best is None or dist[i, j] < best[0]:
                    best = (float(dist[i, j]), float(hx), float(hz))
            pts.append({"d_c": d, "alpha_deg": a, "h_streamwise_c": best[1], "h_cross_c": best[2]})
    out["vortex_path"] = pts
    out["vortex_h_max_c"] = float(max(max(p["h_streamwise_c"], p["h_cross_c"]) for p in pts))
    out["vortex_span_gap_max_c"] = float(gaps_near.max())        # the station gaps within 30 of the tip, both sides
    out["cap_min_sj"] = vm.info["quality_by_block"]["CAP"]["min_sj"]
    out["cap_nose_corner_min_sj"] = vm.info.get("cap_nose_corner_min_sj")
    out["min_sj_but_cap_nose_corners"] = vm.info.get("min_sj_but_cap_nose_corners")
    out["outboard_min_sj"] = min(v["min_sj"] for k, v in vm.info["quality_by_block"].items() if k.endswith("_out"))
    out["inboard_min_sj"] = min(v["min_sj"] for k, v in vm.info["quality_by_block"].items() if k.endswith("_in"))
    return out


def row_of(vm, w, lev, re, seconds_surface) -> dict:
    parts = {"inboard": 0, "outboard": 0, "cap": 0}
    for n, b in vm.blocks.items():
        c = int(np.prod(np.array(b.shape[:3]) - 1))
        parts["cap" if n == "CAP" else ("inboard" if n.endswith("_in") else "outboard")] += c
    r = {"type": w.wing_type, "set": w.set_name, "index": w.index, "hash8": w.input_hash[:8], "level": lev, "re": re,
         "outcome": vm.outcome, "review": vm.review, "failed": [c.name for c in vm.failed()],
         "checks": {c.name: {"n": c.n, "passed": c.passed, "value": c.value, "limit": c.limit} for c in vm.checks},
         "cells": vm.cells, "parts": parts, "ram_gib": vm.info["ram_gib_adflow"], "fits": vm.info["fits"],
         "counts": {k: vm.info[k] for k in ("n_wake", "n_layers", "n_c", "n_span", "n_out", "n_side", "n_base")},
         "need": vm.info["need"], "kappa": vm.info["kappa"], "rung": vm.info["rung"],
         "wall_angle_3d_deg": vm.info["wall_angle_3d_deg"], "te_corner_angle_deg": vm.info["te_corner_angle_deg"],
         "bl_cells_min": vm.info["bl_cells_min"], "band_cell_ratio_max": vm.info["band_cell_ratio_max"],
         "seconds": vm.info["seconds_total"], "seconds_surface": seconds_surface}
    r |= extra(vm)
    return r


def sample(sets, types, share: float, seed: int) -> set:
    """A seeded share of every set and type (at least one wing each): the same wings on every run."""
    out = set()
    for si, s in enumerate(sets):
        for ti, t in enumerate(types):
            n = sum(1 for tt, ss, _ in wings([s], [t]))
            if n:
                rng = np.random.default_rng([seed, si, ti])
                k = max(1, int(np.ceil(share * n)))
                out |= {(t, s, int(i)) for i in rng.choice(n, size=k, replace=False)}
    return out


def wings(sets, types):
    for s in sets:
        for t in types:
            try:
                n = len(load_set(t, s)["vectors"])
            except FileNotFoundError:
                continue
            for i in range(n):
                yield t, s, i


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sets", nargs="+", default=["reference"])
    p.add_argument("--types", nargs="+", default=list(TYPES))
    p.add_argument("--levels", nargs="+", default=["VC"])
    p.add_argument("--re", nargs="+", type=float, default=None, help="default: 3e5 (every set); the four levels for reference")
    p.add_argument("--tag", required=True)
    p.add_argument("--count", action="store_true", help="count the cells only (no build)")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--only", nargs="+", default=None, help="type:index pairs (e.g. tapered:4) to build only these wings")
    p.add_argument("--sample", type=float, default=None, help="a seeded share of each set and type (e.g. 0.1)")
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()
    only = None if a.only is None else {(o.split(":")[0], int(o.split(":")[1])) for o in a.only}
    out = HERE / "data" / "studies" / f"screen_{PREFIX}{a.tag}.jsonl"
    done = set()
    if a.resume and out.exists():
        for line in out.read_text().splitlines():
            r = json.loads(line)
            done.add((r["type"], r["set"], r["index"], r["level"], r["re"]))
    f = open(out, "a")
    picked = sample(a.sets, a.types, a.sample, a.seed) if a.sample else None
    for t, s, i in wings(a.sets, a.types):
        if only is not None and (t, i) not in only:
            continue
        if picked is not None and (t, s, i) not in picked:
            continue
        res = a.re or (list(re_levels()) if s == "reference" else [3e5])
        for re in res:
            todo = [lev for lev in a.levels if (t, s, i, lev, re) not in done]
            if not todo:
                continue
            t0 = time.time()
            try:
                w = wing_from_set(t, s, i)
                if len(todo) == 1:
                    # one level: its own surface; the family's only if a nose repair was needed (decision 80; Study 12
                    # found none in 782 families, so the two are the same node for node)
                    fam = {todo[0]: build_surface(w.loft, re, todo[0])}
                    if fam[todo[0]].info["turning_repairs"]:
                        fam = build_family(w.loft, re)
                else:
                    fam = build_family(w.loft, re)
            except Exception as e:                                    # a surface failure stays in the count
                for lev in todo:
                    f.write(json.dumps({"type": t, "set": s, "index": i, "level": lev, "re": re, "outcome": "crashed",
                                        "stage": "surface", "error": repr(e)}) + "\n")
                f.flush()
                continue
            ts = time.time() - t0
            for lev in todo:
                try:
                    if a.count:
                        c = count_volume(fam[lev], config=CONFIG)
                        r = {"type": t, "set": s, "index": i, "hash8": w.input_hash[:8], "level": lev, "re": re,
                             "outcome": "counted"} | c
                    else:
                        vm = build_volume(fam[lev], config=CONFIG)
                        r = row_of(vm, w, lev, re, ts)
                        del vm
                except Exception as e:
                    r = {"type": t, "set": s, "index": i, "level": lev, "re": re, "outcome": "crashed",
                         "stage": "volume", "error": repr(e), "trace": traceback.format_exc()[-2000:]}
                f.write(json.dumps(_jsonable(r)) + "\n")
                f.flush()
                print(f"{t} {s} {i} {lev} {re:.0e}: {r['outcome']} {r.get('cells', '')} {r.get('failed', '')}",
                      flush=True)
    f.close()


if __name__ == "__main__":
    main()
