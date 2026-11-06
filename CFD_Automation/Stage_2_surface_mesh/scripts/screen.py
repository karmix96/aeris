"""Robustness screen of the surface mesher: every wing of the built sets, every type, one level (default VC).

    python scripts/screen.py                 # all sets at Re 3e5; reference wings at all four Re levels
    python scripts/screen.py --sets reference --re 1e5 3e5 1.5e6 3e6
    python scripts/screen.py --level F --sets reference

Writes data/studies/screen_<level>.json (one row per wing and Re: passed, the failed checks, counts,
worst values, build time) and prints the summary. Failures stay in every count.
data/studies/screen_C.json is the screen of the first approach (2-3 Nov, its level C = the coarsest);
with another config (--config, e.g. configs/surface_first.yaml) the file is screen_<level>_<config name>.json,
and a new screen at level C refuses to overwrite screen_C.json unless --out names it.
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
from cfdauto.paths import STAGE2  # noqa: E402

TYPES = ("bwb", "flying_wing", "cranked", "tapered")
SETS = ("reference", "training_focus", "training_full", "corner1", "corner2")
RE_LEVELS = (1.0e5, 3.0e5, 1.5e6, 3.0e6)
FIRST_SCREEN = STAGE2 / "data" / "studies" / "screen_C.json"     # the first approach's screen (2-3 Nov)


def one(wing_type: str, set_name: str, index: int, re: float, level: str, config=None) -> dict:
    row = {"wing_type": wing_type, "set": set_name, "index": index, "re_mean": re, "level": level}
    t0 = time.time()
    try:
        w = wing_from_set(wing_type, set_name, index)
        m = build_surface(w.loft, re, level, config)
        row |= {"built": True, "passed": m.passed, "failed": [c.name for c in m.failed()],
                "checks": {c.name: c.value for c in m.checks},
                "n_ring": m.info["n_ring"], "n_span": m.info["n_span"], "n_side": m.info["n_side"],
                "quads": m.info["wing_quads"] + m.info["cap_quads"],
                "cells_per_panel": m.info["cells_per_panel"], "turning_repairs": m.info["turning_repairs"],
                "semi_span_m": m.info["semi_span_m"], "mean_chord_m": m.info["mean_chord_m"],
                "tip_chord_m": m.info["tip_chord_m"], "re_tip": m.info["re_tip"],
                "nose_tightened": int(sum(r["nose_tightened"] for r in m.stations)),
                "nose_capped_at_band": int(sum(r["nose_capped_at_band"] for r in m.stations)),
                "nose_solved_at": {k: sum(r["nose_solved_at"] == k for r in m.stations)
                                   for k in sorted({r["nose_solved_at"] for r in m.stations})},
                "input_hash": w.input_hash, "node_hash": m.node_hash()}
    except Exception as exc:  # a crash is a failure with a reason, never a missing row
        row |= {"built": False, "passed": False, "failed": ["exception"], "error": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc().splitlines()[-3:]}
    row["seconds"] = round(time.time() - t0, 2)
    return row


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sets", nargs="+", default=list(SETS))
    p.add_argument("--types", nargs="+", default=list(TYPES))
    p.add_argument("--re", nargs="+", type=float, default=None, help="Re levels; default 3e5 (reference: all four)")
    p.add_argument("--level", default=None, help="a level of the config (default: the coarsest, VC)")
    p.add_argument("--config", default=None, help="rules file (default configs/surface.yaml)")
    p.add_argument("--out", default=None, help="default data/studies/screen_<level>.json (see above)")
    a = p.parse_args(argv)
    level = rules(a.level, a.config).level
    other = a.config and Path(a.config).resolve() != CONFIG.resolve()
    out = Path(a.out) if a.out else STAGE2 / "data" / "studies" / (
        f"screen_{level}_{Path(a.config).stem}.json" if other else f"screen_{level}.json")
    if not a.out and out.resolve() == FIRST_SCREEN.resolve():
        p.error(f"{FIRST_SCREEN.name} holds the first approach's screen: pass --out to write a new screen at level C")
    rows = []
    for t in a.types:
        for s in a.sets:
            n = len(load_set(t, s)["vectors"])
            res = a.re or (list(RE_LEVELS) if s == "reference" else [3.0e5])
            for i in range(n):
                for re in res:
                    r = one(t, s, i, re, level, a.config)
                    rows.append(r)
                    flag = "ok " if r["passed"] else "XX "
                    print(f"{flag}{t:12s} {s:15s} {i:3d} Re {re:7.1e}  "
                          + (f"ring {r['n_ring']:4d} x {r['n_span']:3d}  {r['seconds']:5.1f} s  {r['failed'] or ''}"
                             if r["built"] else r["error"]), flush=True)
    summary = summarise(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"code_version": __version__, "mesh_code_hash": mesh_code_hash(), "level": level,
                               "config": str(a.config or CONFIG), "summary": summary, "rows": rows}, indent=1))
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
        for k in ("n_ring", "n_span", "quads", "seconds"):
            v = np.array([r[k] for r in ok], dtype=float)
            out[k] = {"min": float(v.min()), "median": float(np.median(v)), "max": float(v.max())}
    return out


if __name__ == "__main__":
    main()
