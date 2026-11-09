"""V6: the screen of every built set at VC (not the hold-outs), Re 3e5; F counted on a seeded 10 % sample; one figure.

    python scripts/screen.py --sets training_focus training_full corner1 corner2 --types bwb flying_wing --tag s_a
    python scripts/screen.py --sets training_focus training_full corner1 corner2 --types cranked tapered --tag s_b
    python scripts/screen.py --sets training_focus training_full corner1 corner2 --count --levels F --sample 0.1 --tag F_sample
    python scripts/v6_study.py        # -> data/studies/v6.json, docs/page/v6_screen.png

The reference set comes from V2 (screen_ref_VC_a/b, its Re 3e5 rows). Every failure stays in every count.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import style as S                                          # noqa: E402

STUDIES = HERE / "data" / "studies"
SETS = ("reference", "training_focus", "training_full", "corner1", "corner2")


def rows_of(tags) -> list[dict]:
    out = []
    for t in tags:
        p = STUDIES / f"screen_{t}.jsonl"
        if p.exists():
            out += [json.loads(l) for l in p.read_text().splitlines()]
    return out


def dist(v) -> dict:
    v = np.asarray([x for x in v if x is not None], float)
    if not v.size:
        return {"n": 0}
    return {"n": int(v.size), "min": float(v.min()), "median": float(np.median(v)), "p95": float(np.percentile(v, 95)),
            "max": float(v.max())}


def main() -> None:
    ref = [r for r in rows_of(("ref_VC_a", "ref_VC_b")) if r["re"] == 3e5]
    rows = ref + rows_of(("s_a", "s_b"))
    fs = rows_of(("F_sample",)) + [r for r in rows_of(("F_ref",))]
    s = {"meshes": len(rows), "outcomes": dict(Counter(r["outcome"] for r in rows)),
         "stopped": "9 Nov 2026, 20:09, by decision 105 (the cells must drop: the rules will change)"}
    # decision 101 came while the screen ran (it judged every cell): a mesh refused only by check 3, whose cells but the
    # cap's two nose-corner columns are >= 0.05, passes under it
    d101 = [r for r in rows if r["outcome"] == "refused" and r.get("failed") == ["cell_quality"]
            and (r.get("min_sj_but_cap_nose_corners") or 0.0) >= 0.05]
    s["passes_with_decision_101"] = [f"{r['type']} {r['set']} {r['index']}" for r in d101]
    oc = Counter(r["outcome"] for r in rows)
    oc["passed"] += len(d101)
    oc["refused"] -= len(d101)
    s["outcomes_with_decision_101"] = {k: v for k, v in oc.items() if v}
    sys.path.insert(0, str(HERE.parent))
    from cfdauto.geometry.build import load_set
    s["screened_of"] = {st: {t: [sum(1 for r in rows if r["set"] == st and r["type"] == t),
                                 len(load_set(t, st)["vectors"])] for t in S.TYPES} for st in SETS}
    s["by_set"] = {st: {t: dict(Counter(r["outcome"] for r in rows if r["set"] == st and r["type"] == t)) for t in S.TYPES}
                   for st in SETS}
    s["failed_checks"] = dict(Counter(c for r in rows for c in (r.get("failed") or [])))
    s["refused"] = [{"type": r["type"], "set": r["set"], "index": r["index"], "failed": r.get("failed"),
                     "values": {c: r["checks"][c]["value"] for c in (r.get("failed") or [])}}
                    for r in rows if r["outcome"] == "refused"]
    s["crashed"] = [{"type": r["type"], "set": r["set"], "index": r["index"], "stage": r.get("stage"),
                     "error": r.get("error")} for r in rows if r["outcome"] == "crashed"]
    s["review"] = dict(Counter(str(r.get("review")) for r in rows if r["outcome"] == "needs review"))
    ok = [r for r in rows if "checks" in r]
    pick = lambda f: [f(r) for r in ok]
    s["cells"] = dist(pick(lambda r: r["cells"]))
    s["cells_by_type"] = {t: dist([r["cells"] for r in ok if r["type"] == t]) for t in S.TYPES}
    s["ram_gib"] = dist(pick(lambda r: r["ram_gib"]))
    s["fits_16GB"] = sum(r["fits"]["desktop_16GB"] for r in ok)
    s["fits_52GB"] = sum(r["fits"]["desktop_52GB"] for r in ok)
    for k, f in {"cell_quality": lambda r: r["checks"]["cell_quality"]["value"],
                 "growth_over_limit": lambda r: r["checks"]["growth"]["value"],
                 "bl_cells_min": lambda r: r["bl_cells_min"],
                 "wall_angle_in_plane_deg": lambda r: r["checks"]["wall_orthogonality"]["value"],
                 "wall_angle_3d_max_deg": lambda r: r["wall_angle_3d_deg"]["max"],
                 "cap_min_sj": lambda r: r["cap_min_sj"], "inboard_min_sj": lambda r: r["inboard_min_sj"],
                 "outboard_min_sj": lambda r: r["outboard_min_sj"],
                 "base_te_cells_min_sj": lambda r: min(r["base_cells_min_sj"], r["te_corner_cells_min_sj"]),
                 "wake_over_limit": lambda r: r["checks"]["wake"]["value"], "rung": lambda r: r["rung"],
                 "outboard_share": lambda r: r["parts"]["outboard"] / r["cells"],
                 "seconds": lambda r: r["seconds"]}.items():
        s[k] = dist(pick(f))
    # F: counted on the sample; the ratio F / VC on the same wings carries the rest
    vc = {(r["type"], r["set"], r["index"]): r["cells"] for r in ok}
    pairs = [(vc[(r["type"], r["set"], r["index"])], r["cells"]) for r in fs
             if r.get("outcome") == "counted" and (r["type"], r["set"], r["index"]) in vc]
    for t in ("ref_a", "ref_b"):                              # the reference wings: F counted in the family study (V4)
        p = STUDIES / f"family_{t}.jsonl"
        if p.exists():
            for r in map(json.loads, p.read_text().splitlines()):
                pairs.append((r["levels"]["VC"]["cells"], r["levels"]["F"]["cells"]))
    if pairs:
        a = np.array(pairs, float)
        ratio = a[:, 1] / a[:, 0]
        s["F_sample"] = {"wings": len(pairs), "note": "a seeded 10 % of each set and type, plus the 20 reference wings (V4)",
                         "cells": dist(a[:, 1]), "F_over_VC": dist(ratio),
                         "ram_gib": dist(1.51 + 9.46 * a[:, 1] / 1e6)}
        allvc = np.array(list(vc.values()), float)
        s["F_estimated_all"] = {"wings": int(allvc.size), "cells": dist(allvc * np.median(ratio)),
                                "note": "VC cells x the median F/VC of the counted sample"}
    (STUDIES / "v6.json").write_text(json.dumps(s, indent=1))

    fig, ax = S.plt.subplots(1, 3, figsize=(13.2, 4.0))
    by = lambda f: [(r["type"], f(r)) for r in ok]
    for a, (f, lim, lt, yl, ti, log) in zip(ax, (
            (lambda r: r["cells"] / 1e6, None, None, "cells (millions)", "(a) Cells at VC, every built set", False),
            (lambda r: r["checks"]["cell_quality"]["value"], 0.05, "limit ≥ 0.05", "smallest scaled Jacobian",
             "(b) The worst cell of each mesh", False),
            (lambda r: r["checks"]["growth"]["value"], 1.01, "limit ≤ 1.01", "largest growth / its limit",
             "(c) The growth margin", False))):
        for ti_, t in enumerate(S.TYPES):
            v = np.array([x for tt, x in by(f) if tt == t])
            if not v.size:
                continue
            xs = ti_ + np.random.default_rng(ti_).uniform(-0.28, 0.28, v.size)
            a.plot(xs, v, "o", ms=2.6, color=S.ACCENT, alpha=0.55, mec="none", zorder=3)
            a.plot([ti_ - 0.32, ti_ + 0.32], [np.median(v)] * 2, color=S.INK, lw=1.6, zorder=4)
        if lim is not None:
            a.axhline(lim, color=S.LIMIT, lw=1.1, ls="--")
            a.annotate(lt, (1.0, lim), xycoords=("axes fraction", "data"), xytext=(-4, 3), textcoords="offset points",
                       ha="right", fontsize=7.8, color=S.LIMIT)
        a.set_xticks(range(4), [S.TYPE_NAME[t] for t in S.TYPES])
        a.set_ylabel(yl)
        a.set_title(ti)
        a.grid(axis="y", color=S.LINE, lw=0.5)
    S.save(fig, HERE / "docs" / "page" / "v6_screen.png")
    print(json.dumps({k: s[k] for k in ("meshes", "outcomes", "failed_checks")}, indent=1))


if __name__ == "__main__":
    main()
