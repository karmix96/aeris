"""Robustness screen of the surface mesher: every wing of the built sets, every type, one level (default VC).

    python scripts/screen.py                 # all sets at Re 3e5; reference wings at all four Re levels
    python scripts/screen.py --sets reference --re 1e5 3e5 1e6 4e6
    python scripts/screen.py --level F --sets reference

Writes data/studies/screen_<level>.json (one row per wing and Re: passed, every check with its value, limit and
margin, the failed checks with their rule, counts, the nose source per station, the spacings for the family
ratios, the wall layers and the cell estimate of the wing blocks, build time) and prints the summary. Failures
stay in every count. The header holds the level's rule values with their reasons and every check's rule.
data/studies/screen_C.json is the screen of the first approach (2-3 Nov, its level C = the coarsest);
with another config (--config, e.g. configs/surface_first.yaml) the file is screen_<level>_<config name>.json,
and a new screen at level C refuses to overwrite screen_C.json unless --out names it.

Cell estimate of the wing blocks (a structured block has one layer count, so the largest over the stations):
    n  = max over stations of ceil( ln(1 + (g - 1) D / s0) / ln g )
    cells = (ring nodes - 1)(stations - 1) n + cap quads x n
with g the level's wall growth (1.25 at VC, 1.25^(1/1.3^k) at level k: 1.187, 1.141, 1.107 at C, M, F), s0 the
level's first cell at the station's local Re (law 13, y+ of the level) and D = 2 local chords.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cfdauto import __version__  # noqa: E402
from cfdauto.geometry.build import load_set  # noqa: E402
from cfdauto.mesh.laws import CONFIG, rules  # noqa: E402
from cfdauto.mesh.surface import build_surface, mesh_code_hash, wing_from_set  # noqa: E402
from cfdauto.paths import STAGE2, re_levels  # noqa: E402

TYPES = ("bwb", "flying_wing", "cranked", "tapered")
SETS = ("reference", "training_focus", "training_full", "corner1", "corner2")
RE_LEVELS = re_levels()     # Stage 0 values.yaml: 1e5, 3e5, 1e6, 4e6 since 8 Nov 2026 (were 1e5, 3e5, 1.5e6, 3e6)
FIRST_SCREEN = STAGE2 / "data" / "studies" / "screen_C.json"     # the first approach's screen (2-3 Nov)
WALL_GROWTH_VC = 1.25          # wall-normal growth at VC (decision 71, hard minimum); 1.107 at F by the family rule
WALL_DEPTH_C = 2.0             # wall-normal depth of the wing blocks, in local chords (for the cell estimate only)


def check_limits(rl, info: dict) -> dict:
    """Each check's numeric limit, as run_checks in cfdauto/mesh/surface.py applies it: (kind, limit)."""
    ch = rl.checks
    turn = rl.nose_turning_deg + 10 * rl.nose_turning_tol_deg
    js = float(ch["min_scaled_jacobian"])
    return {"nose_turning": ("max", turn), "geometry_kinks": ("max", turn),
            "nose_envelope": ("max", rl.nose_envelope * 1.01), "chord_growth": ("max", rl.chord_growth_limit * 1.01),
            "band_spacing": ("max", 1.01), "te_spacing": ("max", 1.01), "span_growth": ("max", rl.span_growth_limit),
            "loft_stations_hit": ("max", 1e-12), "tip_gap": ("band", tuple(float(x) for x in ch["tip_gap_band"])),
            "planar_stations": ("max", float(ch["on_loft_m"])), "wing_quads": ("min", js), "cap_quads": ("min", js),
            "cap_nose_corners": ("min", 0.0), "ring_count": ("eq", float(2 * info["n_side"] + info["n_base"] - 3))}


def margin(kind: str, lim, v: float) -> float:
    """How far inside the limit (> 0 inside, < 0 outside), in the check's own units."""
    if kind == "max":
        return float(lim - v)
    if kind == "min":
        return float(v - lim)
    if kind == "band":
        return float(min(v - lim[0], lim[1] - v))
    return float(-abs(v - lim))


def checks_with_margins(m, rl) -> dict:
    lims = check_limits(rl, m.info)
    out = {}
    for c in m.checks:
        kind, lim = lims[c.name]
        out[c.name] = {"passed": bool(c.passed), "value": float(c.value),
                       "limit": list(lim) if isinstance(lim, tuple) else float(lim), "kind": kind,
                       "margin": margin(kind, lim, float(c.value))}
    return out


def spacings(m) -> dict[str, float]:
    """The spacings the family rule acts on (as scripts/family_check.py, Study 2)."""
    y = np.array([r["y_m"] for r in m.stations])
    root, tip = m.stations[0], m.stations[-1]
    return {"nose_root": root["h_le_c"], "nose_tip": tip["h_le_c"], "te_root": root["h_te_c_delivered"],
            "band_root": root["band_max_c"], "band_tip": tip["band_max_c"],
            "root_gap": float(np.diff(y)[0]), "tip_gap": float(np.diff(y)[-1]),
            "base_cell": float(np.linalg.norm(m.wing[-1, 0] - m.wing[0, 0]))}


def wall_cells(m, rl) -> dict:
    """Wall layers n (largest over the stations) and the cell estimate of the wing blocks (see the module text)."""
    g = WALL_GROWTH_VC ** (1.0 / rl.scale)
    n_st = []
    for r in m.stations:
        s0 = rl.first_cell_c(r["re_local"]) * r["chord_m"]
        d = WALL_DEPTH_C * r["chord_m"]
        n_st.append(int(np.ceil(np.log(1.0 + (g - 1.0) * d / s0) / np.log(g) - 1e-9)))
    j = int(np.argmax(n_st))
    n = n_st[j]
    wing = (m.info["n_ring"] - 1) * (m.info["n_span"] - 1) * n
    cap = m.info["cap_quads"] * n
    return {"wall_growth": g, "wall_layers": n, "wall_layers_root": n_st[0], "wall_layers_station": j,
            "re_local_max": float(max(r["re_local"] for r in m.stations)),
            "s0_c_at_max": float(rl.first_cell_c(m.stations[j]["re_local"])),
            "cells_wing": int(wing), "cells_cap": int(cap), "cells_est": int(wing + cap)}


def one(wing_type: str, set_name: str, index: int, re: float, level: str, config=None) -> dict:
    row = {"wing_type": wing_type, "set": set_name, "index": index, "re_mean": re, "level": level}
    t0 = time.time()
    try:
        rl = rules(level, config)
        w = wing_from_set(wing_type, set_name, index)
        m = build_surface(w.loft, re, level, config)
        row |= {"built": True, "passed": m.passed, "failed": [c.name for c in m.failed()],
                "failed_detail": {c.name: f"{c.value:.6g}, limit {c.limit}" for c in m.failed()},
                "checks": checks_with_margins(m, rl),
                "n_ring": m.info["n_ring"], "n_span": m.info["n_span"], "n_side": m.info["n_side"],
                "n_base": m.info["n_base"], "wing_quads": m.info["wing_quads"], "cap_quads": m.info["cap_quads"],
                "quads": m.info["wing_quads"] + m.info["cap_quads"],
                "cells_per_panel": m.info["cells_per_panel"], "turning_repairs": m.info["turning_repairs"],
                "semi_span_m": m.info["semi_span_m"], "mean_chord_m": m.info["mean_chord_m"],
                "tip_chord_m": m.info["tip_chord_m"], "re_tip": m.info["re_tip"],
                "nose_tightened": int(sum(r["nose_tightened"] for r in m.stations)),
                "nose_capped_at_band": int(sum(r["nose_capped_at_band"] for r in m.stations)),
                "nose_solved_at": {k: sum(r["nose_solved_at"] == k for r in m.stations)
                                   for k in sorted({r["nose_solved_at"] for r in m.stations})},
                "nose_set_by": {k: sum(("band" if r["nose_capped_at_band"] else r["nose_solved_at"]) == k for r in m.stations)
                                for k in sorted({"band" if r["nose_capped_at_band"] else r["nose_solved_at"] for r in m.stations})},
                "nose_h_le_c": [float(min(r["h_le_c"] for r in m.stations)), float(max(r["h_le_c"] for r in m.stations))],
                "spacings": spacings(m), **wall_cells(m, rl),
                "input_hash": w.input_hash, "node_hash": m.node_hash()}
    except Exception as exc:  # a crash is a failure with a reason, never a missing row
        row |= {"built": False, "passed": False, "failed": ["exception"], "error": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc().splitlines()[-3:]}
    row["seconds"] = round(time.time() - t0, 2)
    return row


def check_rules(level: str, config=None) -> dict:
    """Every check's rule in words at this level (from one small build: the text does not depend on the wing)."""
    w = wing_from_set("tapered", "reference", 0)
    m = build_surface(w.loft, 3.0e5, level, config)
    return {c.name: c.limit for c in m.checks}


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sets", nargs="+", default=list(SETS))
    p.add_argument("--types", nargs="+", default=list(TYPES))
    p.add_argument("--re", nargs="+", type=float, default=None, help="Re levels; default 3e5 (reference: the four Stage 0 levels)")
    p.add_argument("--level", default=None, help="a level of the config (default: the coarsest, VC)")
    p.add_argument("--config", default=None, help="rules file (default configs/surface.yaml)")
    p.add_argument("--out", default=None, help="default data/studies/screen_<level>.json (see above)")
    p.add_argument("--resume", default=None,
                   help="a .jsonl file: every row is appended as it is built, and rows already in it are not built "
                        "again, so a stopped screen goes on where it stopped (the full JSON is written at the end)")
    a = p.parse_args(argv)
    rl = rules(a.level, a.config)
    level = rl.level
    other = a.config and Path(a.config).resolve() != CONFIG.resolve()
    out = Path(a.out) if a.out else STAGE2 / "data" / "studies" / (
        f"screen_{level}_{Path(a.config).stem}.json" if other else f"screen_{level}.json")
    if out.resolve() == FIRST_SCREEN.resolve() and not a.out:
        p.error(f"{FIRST_SCREEN.name} holds the first approach's screen: pass --out to write a new screen at level C")
    done, log = {}, None
    if a.resume:
        log = Path(a.resume)
        log.parent.mkdir(parents=True, exist_ok=True)
        if log.exists():
            for line in log.read_text().splitlines():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue                      # a line cut by a stop: built again
                if r.get("level") == level:
                    done[(r["wing_type"], r["set"], r["index"], float(r["re_mean"]))] = r
        print(f"resume: {len(done)} rows already in {log.name}", flush=True)
    rows = []
    for t in a.types:
        for s in a.sets:
            n = len(load_set(t, s)["vectors"])
            res = a.re or (list(RE_LEVELS) if s == "reference" else [3.0e5])
            for i in range(n):
                for re in res:
                    key = (t, s, i, float(re))
                    if key in done:
                        rows.append(done[key])
                        continue
                    r = one(t, s, i, re, level, a.config)
                    rows.append(r)
                    if log is not None:
                        with open(log, "a") as f:
                            f.write(json.dumps(r) + "\n")
                    flag = "ok " if r["passed"] else "XX "
                    print(f"{flag}{t:12s} {s:15s} {i:3d} Re {re:7.1e}  "
                          + (f"ring {r['n_ring']:4d} x {r['n_span']:3d}  {r['seconds']:5.1f} s  "
                             f"{r['cells_est'] / 1e6:5.2f} M  {r['failed'] or ''}"
                             if r["built"] else r["error"]), flush=True)
    summary = summarise(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"code_version": __version__, "mesh_code_hash": mesh_code_hash(), "level": level,
                               "config": str(a.config or CONFIG), "rules": rl.values(),
                               "check_rules": check_rules(level, a.config),
                               "cell_estimate": {"wall_growth_vc": WALL_GROWTH_VC, "wall_depth_c": WALL_DEPTH_C,
                                                 "formula": "n = max_j ceil(ln(1 + (g-1) D/s0_j) / ln g); cells = "
                                                            "(n_ring-1)(n_span-1) n + cap_quads n"},
                               "summary": summary, "rows": rows}, indent=1))
    print(json.dumps(summary, indent=1))


def summarise(rows: list[dict]) -> dict:
    out = {"total": len(rows), "passed": sum(r["passed"] for r in rows)}
    out["by_type_set"] = {}
    for r in rows:
        k = f"{r['wing_type']}/{r['set']}"
        d = out["by_type_set"].setdefault(k, {"n": 0, "passed": 0, "failed_checks": {}})
        d["n"] += 1
        d["passed"] += int(r["passed"])
        for f in r["failed"]:
            d["failed_checks"][f] = d["failed_checks"].get(f, 0) + 1
    ok = [r for r in rows if r["built"]]
    if ok:
        for k in ("n_ring", "n_span", "quads", "seconds", "cells_est", "wall_layers"):
            if all(k in r for r in ok):
                v = np.array([r[k] for r in ok], dtype=float)
                out[k] = {"min": float(v.min()), "median": float(np.median(v)), "max": float(v.max())}
    return out


if __name__ == "__main__":
    main()
