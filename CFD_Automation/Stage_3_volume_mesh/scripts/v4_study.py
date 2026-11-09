"""V4: the family on the reference wings, Re 3e5: check 13 (every judged spacing 1.3 within 3 % between neighbouring
levels), the counts per level (built where they fit here, counted otherwise), one figure.

    python scripts/family_study.py --types bwb flying_wing --levels VC C --tag ref_a       # 10 wings, VC and C built
    python scripts/family_study.py --types cranked tapered --levels VC C --tag ref_b       # 10 wings
    python scripts/family_study.py --indices 0 --levels VC C M --tag m4                    # M on one wing per type
    python scripts/family_study.py --types bwb --indices 0 --levels VC C M F --tag f1      # F on BWB 0
    python scripts/v4_study.py                       # -> data/studies/v4.json, docs/page/v4_family.png
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ruleset import CONFIG, PREFIX  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(HERE.parent))
import style as S                                          # noqa: E402
from cfdauto.volume.family import JUDGED                  # noqa: E402

STUDIES = HERE / "data" / "studies"
NAMES = {"s0": "s0 per station", "wall_growth": "wall growth (ln g)", "band_cell": "band cell",
         "outboard_first_gap": "first outboard gap", "first_wake_cell": "first wake cell",
         "cell_1c_wall": "cell 1 c from the wall", "cell_1c_wake": "cell 1 c behind the TE"}


def load(tags) -> list[dict]:
    out = []
    for t in tags:
        p = STUDIES / f"family_{PREFIX}{t}.jsonl"
        if p.exists():
            out += [json.loads(l) | {"tag": t} for l in p.read_text().splitlines()]
    return out


def main() -> None:
    base = load(("ref_a", "ref_b"))
    deep = load(("m4", "f1"))
    rows = base + deep
    s = {"wings": len(base), "deep_runs": [(r["type"], r["index"], [l for l, v in r["levels"].items() if v.get("built")])
                                           for r in deep]}
    s["check13"] = {"passed": sum(1 for r in base if r.get("check13", {}).get("passed")),
                    "of": sum(1 for r in base if "check13" in r),
                    "worst": max((r["check13"]["value"], f"{r['type']} {r['index']}: {r['check13']['where']}")
                                 for r in rows if "check13" in r)}
    seen = {}
    for r in rows:                                           # one outcome per wing and level (the same build in two runs)
        for lev, v in r["levels"].items():
            if v.get("built"):
                seen[(r["type"], r["index"], lev)] = v["outcome"]
    after = {}                                               # decision 101 (Mike): the same meshes rebuilt with it
    cs = STUDIES / f"{PREFIX}v4_cap_split.json"
    if cs.exists():
        for key, v in json.loads(cs.read_text()).get("after_decision_101", {}).get("results", {}).items():
            t, i, lev = key.split()
            after[(t, int(i), lev)] = v["outcome"]
    s["before_decision_101"] = {f"{t} {i} {lev}": o for (t, i, lev), o in seen.items() if (t, i, lev) in after}
    seen.update({k: v for k, v in after.items() if k in seen})
    outcomes = {}
    for (t, i, lev), o in seen.items():
        outcomes.setdefault(lev, {}).setdefault(o, []).append(f"{t} {i}")
    s["outcomes_built"] = {lev: {o: len(w) for o, w in d.items()} for lev, d in outcomes.items()}
    s["outcomes_built_wings"] = {lev: d for lev, d in outcomes.items() if lev in ("M", "F")}
    ratios = {}
    for r in rows:
        for pair, t in r.get("check13", {}).get("ratios", {}).items():
            for k in JUDGED:
                ratios.setdefault(pair, {}).setdefault(k, []).append(t[k])
            for k, v in t["counts"].items():
                ratios.setdefault(pair, {}).setdefault("count_" + k, []).append(v)
    s["ratios"] = {p: {k: {"min": float(min(v)), "median": float(np.median(v)), "max": float(max(v)), "n": len(v)}
                       for k, v in d.items()} for p, d in ratios.items()}
    cells = {}
    for r in base:
        for lev, v in r["levels"].items():
            cells.setdefault(lev, []).append(v["cells"])
    s["cells"] = {lev: {"min": int(min(v)), "median": float(np.median(v)), "max": int(max(v)),
                        "ram_gib_median": 1.51 + 9.46 * float(np.median(v)) / 1e6,
                        "ram_gib_ank_only_median": 2.69 + 7.23 * float(np.median(v)) / 1e6} for lev, v in cells.items()}
    bvc = {}
    for r in deep:
        for lev, v in r["levels"].items():
            if v.get("built") and lev in ("M", "F"):
                bvc[(r["type"], r["index"], lev)] = {"wing": f"{r['type']} {r['index']}", "level": lev, "cells": v["cells"],
                                                     "outcome": after.get((r["type"], r["index"], lev), v["outcome"]),
                                                     "failed": [] if (r["type"], r["index"], lev) in after else v.get("failed"),
                                                     "seconds": v.get("seconds"), "max_rss_gib": r.get("max_rss_gib")}
    if cs.exists():
        for key, v in json.loads(cs.read_text()).get("after_decision_101", {}).get("results", {}).items():
            t, i, lev = key.split()
            bvc.setdefault((t, int(i), lev), {"wing": f"{t} {i}", "level": lev, "cells": v["cells"], "outcome": v["outcome"],
                                              "failed": v["failed"], "seconds": None, "max_rss_gib": None})
            seen.setdefault((t, int(i), lev), v["outcome"])
    s["built_vs_counted"] = list(bvc.values())
    outcomes = {}
    for (t, i, lev), o in seen.items():
        outcomes.setdefault(lev, {}).setdefault(o, []).append(f"{t} {i}")
    s["outcomes_built"] = {lev: {o: len(w) for o, w in d.items()} for lev, d in outcomes.items()}
    s["outcomes_built_wings"] = {lev: d for lev, d in outcomes.items() if lev in ("M", "F")}
    (STUDIES / f"{PREFIX}v4.json").write_text(json.dumps(s, indent=1))

    fig, ax = S.plt.subplots(1, 2, figsize=(13.2, 4.6), gridspec_kw={"width_ratios": [1.35, 1]})
    a = ax[0]
    keys = list(JUDGED)
    for ki, k in enumerate(keys):
        v = [r["check13"]["ratios"]["VC/C"][k] for r in base if "check13" in r]
        a.plot(np.full(len(v), ki) + np.linspace(-0.18, 0.18, len(v)), v, "o", ms=4, color=S.ACCENT, mec="white",
               mew=0.5, zorder=3, label="VC / C, one dot per wing" if ki == 0 else None)
        dv = [r["check13"]["ratios"][p][k] for r in deep for p in r.get("check13", {}).get("ratios", {}) if p != "VC/C"]
        if dv:
            a.plot(np.full(len(dv), ki) + 0.3, dv, "D", ms=4.5, color=S.RAMP4[3], mec="white", mew=0.5, zorder=3,
                   label="C / M and M / F" if ki == 0 else None)
    a.axhspan(1.3 * 0.97, 1.3 * 1.03, color=S.OK, alpha=0.10, lw=0)
    a.axhline(1.3, color=S.MUTED, lw=0.8)
    a.annotate("limit: 1.3 ± 3 %", (1.0, 1.3 * 1.03), xycoords=("axes fraction", "data"), xytext=(-4, 3),
               textcoords="offset points", ha="right", fontsize=7.8, color=S.INK)
    a.set_ylim(1.245, 1.355)
    a.set_xticks(range(len(keys)), [NAMES[k] for k in keys], rotation=18, ha="right")
    a.set_ylabel("coarse / fine")
    a.set_title("(a) Check 13: every judged spacing between neighbouring levels")
    a.legend(loc="lower left", frameon=False)
    a.grid(axis="y", color=S.LINE, lw=0.5)
    a = ax[1]
    for li, lev in enumerate(S.LEVELS):
        v = [r["levels"][lev]["cells"] / 1e6 for r in base]
        built = [r["levels"][lev].get("built", False) for r in base]
        a.plot(np.full(len(v), li) + np.linspace(-0.2, 0.2, len(v)), v, "o" if all(built) else "o", ms=4,
               color=S.RAMP4[li], mfc=S.RAMP4[li] if all(built) else "white", mec=S.RAMP4[li], mew=1.0, zorder=3,
               label=("built" if all(built) else "counted") if li in (0, 2) else None)
    if PREFIX:                                    # rule set 2: the target is M about 10 M (decision 107)
        a.plot([1.6, 2.4], [10, 10], color=S.LIMIT, lw=1.1, ls="--")
        a.annotate("target at M:\nabout 10 M", (2.42, 10), xytext=(4, 0), textcoords="offset points", ha="left",
                   va="center", fontsize=7.8, color=S.LIMIT)
        a.axhspan(4.6, 5.9, color=S.MUTED, alpha=0.13, lw=0)
        a.annotate("48 GB holds 4.6–5.9 M (ADflow, S8's two laws)", (0.0, 5.9), xycoords=("axes fraction", "data"),
                   xytext=(4, 3), textcoords="offset points", fontsize=7.6, color=S.MUTED)
        marks = ((1.2, "16 GB desktop ≈ 1.2 M"),)
    else:
        a.axhspan(9, 11, color=S.LIMIT, alpha=0.10, lw=0)
        a.annotate("asked for at F: 9–11 M", (3.0, 11), xytext=(0, 4), textcoords="offset points", ha="center",
                   fontsize=7.8, color=S.LIMIT)
        marks = ((1.2, "16 GB desktop ≈ 1.2 M"), (5.0, "+ 36 GB ≈ 5.0 M"))
    for v, t in marks:
        a.axhline(v, color=S.MUTED, lw=0.9, ls=":")
        a.annotate(t, (0.0, v), xycoords=("axes fraction", "data"), xytext=(4, 3), textcoords="offset points",
                   fontsize=7.6, color=S.MUTED)
    a.set_yscale("log")
    from matplotlib.ticker import FixedLocator, NullFormatter
    a.yaxis.set_major_locator(FixedLocator([1, 2, 5, 10, 20, 50]))
    a.yaxis.set_major_formatter(S.plt.FuncFormatter(lambda v, _: f"{v:g}"))
    a.yaxis.set_minor_formatter(NullFormatter())
    a.set_xticks(range(4), list(S.LEVELS))
    a.set_ylabel("cells (millions)")
    a.set_title("(b) Cells per level, 20 reference wings, Re 3e5")
    a.legend(loc="upper left", frameon=False)
    a.grid(axis="y", color=S.LINE, lw=0.5)
    S.save(fig, HERE / "docs" / "page" / f"{PREFIX}v4_family.png")
    print(json.dumps({k: s[k] for k in ("wings", "check13", "outcomes_built", "cells")}, indent=1))


if __name__ == "__main__":
    main()
