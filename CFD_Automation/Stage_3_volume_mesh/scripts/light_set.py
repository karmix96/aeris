"""Lighter meshes: several loosened rules together (the knobs of knob_study.py), counted on the 20 reference wings at
the 4 Re levels and built to see whether they still pass. A what-if study: the rules files are copied and changed;
the rules are unchanged.

    python scripts/light_set.py                       (about 30 min on 2 cores)
    python scripts/light_set.py --packages Bdpw       (one package, with the rules as they are: light_set_Bdpw.json)
    python scripts/light_set.py --packages A2,B2_100,B2_dpw,C2   (the final packages, 11 Nov; about 30 min)
    python scripts/light_set.py --figure              (docs/page/light_set.png from the json files)

Counts: the 20 reference wings at VC, Re 1e5, 3e5, 1e6, 4e6; the 4 wings 0 at M, Re 3e5 and 4e6.
Builds: the 4 wings 0 at VC, Re 3e5 and 4e6, every package (the surface checks and the volume checks).
-> data/studies/light_set.json
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from knob_study import KNOBS, SURFACE, VOLUME, TYPES          # noqa: E402
sys.path.insert(0, str(HERE.parent))
from cfdauto.mesh.surface import build_surface, wing_from_set   # noqa: E402
from cfdauto.volume.volume import build_volume, count_volume     # noqa: E402

RES = (1e5, 3e5, 1e6, 4e6)
M_RES = (3e5, 4e6)
_A = ["wall_g130", "span_g125", "chord_g125"]
PACKAGES = {
    "base": ([], "the rules as they are"),
    "A": (_A, "A: the growth rates up to the guideline values (wall 1.30 at VC, 1.17 at M; stations and ring 1.25 at VC)"),
    "B20": (_A + ["tip_20s0"], "B20: A + tip gap 20 x s0"),
    "B100": (_A + ["tip_100s0"], "B100: A + tip gap 100 x s0"),
    "C": (_A + ["tip_100s0", "band_off"], "C: B100 + no band (fully turbulent runs only)"),
    "D": (_A + ["tip_100s0", "band_off", "far_40"], "D: C + far field 40 mean chords"),
    "Bdpw": (_A + ["tip_dpw"], "Bdpw: A + tip gap 0.1 % of the semi-span at M (DPW's value; in s0 per wing and Re)"),
    # without the ring growth: in A it breaks the tip cap at Re 1e5 (BWB, flying wing; cap_quads 0.044)
    "A2": (_A2 := ["wall_g130", "span_g125"], "A2: wall-normal growth 1.30 and station growth 1.25 at VC"),
    "B2_100": (_A2 + ["tip_100s0"], "B2_100: A2 + tip gap 100 x s0"),
    "B2_dpw": (_A2 + ["tip_dpw"], "B2_dpw: A2 + tip gap 0.1 % of the semi-span at M (DPW's value)"),
    "C2": (_A2 + ["tip_dpw", "band_off"], "C2: B2_dpw + no band (fully turbulent runs only)"),
}
LEVEL_K = {"VC": 0, "C": 1, "M": 2, "F": 3}


def tip_dpw_in_s0(sm, level: str) -> float:
    """The tip gap as DPW asks it at the medium mesh, 0.1 % of the semi-span at M, written in s0 of this wing and Re
    (s0 follows y+, so the same number of s0 keeps the family ratio at every level)."""
    s0_m = sm.info["s0_tip_m"] * 1.3 ** (LEVEL_K[level] - LEVEL_K["M"])
    return 0.001 * sm.info["semi_span_m"] / s0_m


def variant(name: str, tip_s0: float | None = None) -> tuple[Path | None, Path | None]:
    """(surface config, volume config) for one package; None = that file as it is. tip_s0: the "tip_dpw" value."""
    knobs = PACKAGES[name][0]
    out = []
    for which, src in (("surface", SURFACE), ("volume", VOLUME)):
        reps = [rep for k in knobs if k != "tip_dpw" and KNOBS[k][0] == which for rep in KNOBS[k][1]]
        if which == "surface" and "tip_dpw" in knobs:
            reps.append(("  tip_gap_in_s0: 2.0 ", f"  tip_gap_in_s0: {tip_s0:.1f} "))
        if not reps:
            out.append(None)
            continue
        text = src.read_text()
        for old, new in reps:
            assert text.count(old) == 1, (name, old)
            text = text.replace(old, new)
        # the file name carries a hash of the text: the rules loaders cache by path (lru_cache on _load), so a
        # changed text under the same name would be read once and then reused
        tag = hashlib.sha1(text.encode()).hexdigest()[:10]
        p = Path(tempfile.gettempdir()) / f"light_{os.getpid()}_{name}_{tag}_{src.name}"
        p.write_text(text)
        out.append(p)
    return out[0], out[1]


def one(job) -> list[dict]:
    t, i, level, re, build = job
    w = wing_from_set(t, "reference", i)
    rows, cache, tip_s0 = [], {}, None
    for name in PACKAGES:                                   # "base" first: its surface gives the DPW tip gap
        s_cfg, v_cfg = variant(name, tip_s0)
        key = s_cfg.read_text() if s_cfg else None        # one surface build per distinct surface rules file
        if key not in cache:
            cache[key] = build_surface(w.loft, re, level, config=s_cfg)
        sm = cache[key]
        if name == "base":
            tip_s0 = tip_dpw_in_s0(sm, level)
        c = count_volume(sm, config=v_cfg)
        r = {"package": name, "type": t, "index": i, "level": level, "re": re, "cells": c["cells"],
             "n_layers": c["n_layers"], "n_c": c["n_c"], "n_span": c["n_span"], "n_wake": c["n_wake"],
             "n_out": c["n_out"], "surface_passed": bool(sm.passed),
             "tip_gap_in_s0": float(sm.info["tip_gap_asked_m"] / sm.info["s0_tip_m"])}
        if build:
            t0 = time.time()
            vm = build_volume(sm, config=v_cfg) if sm.passed else None
            r |= {"outcome": vm.outcome if vm else "surface refused",
                  "failed": [x.name for x in vm.failed()] if vm else [x.name for x in sm.failed()],
                  "built_cells": vm.cells if vm else None, "seconds": round(time.time() - t0, 1)}
        rows.append(r)
    return rows


def dist(v) -> dict:
    v = np.asarray(v, float)
    return {"min": float(v.min()), "median": float(np.median(v)), "max": float(v.max()), "n": int(v.size)}


def main() -> None:
    out_name = "light_set.json"
    if "--packages" in sys.argv:                            # a subset (base always), e.g. --packages Bdpw
        keep = ["base"] + sys.argv[sys.argv.index("--packages") + 1].split(",")
        for k in [k for k in PACKAGES if k not in keep]:
            del PACKAGES[k]
        out_name = f"light_set_{'_'.join(keep[1:])}.json"
    jobs = [(t, 0, "M", re, False) for t in TYPES for re in M_RES]
    jobs += [(t, i, "VC", re, i == 0 and re in M_RES) for t in TYPES for i in range(5) for re in RES]
    with Pool(2) as p:
        rows = [r for part in p.map(one, jobs, chunksize=1) for r in part]
    summary = {}
    for name in PACKAGES:
        s = {"words": PACKAGES[name][1], "knobs": PACKAGES[name][0]}
        for level, res in (("VC", RES), ("M", M_RES)):
            for re in res:
                rr = [r for r in rows if r["package"] == name and r["level"] == level and r["re"] == re]
                bb = {(r["type"], r["index"]): r for r in rows
                      if r["package"] == "base" and r["level"] == level and r["re"] == re}
                s[f"{level} Re {re:.0e}"] = {
                    "cells": dist([r["cells"] for r in rr]),
                    "vs_base": dist([r["cells"] / bb[(r["type"], r["index"])]["cells"] for r in rr]),
                    "parts": {k: float(np.median([r[k] for r in rr]))
                              for k in ("n_layers", "n_c", "n_span", "n_wake", "n_out")}}
        built = [r for r in rows if r["package"] == name and "outcome" in r]
        s["built_VC_wing0"] = {"passed": sum(r["outcome"] == "passed" for r in built), "of": len(built),
                               "failed": sorted({x for r in built for x in r["failed"]})}
        summary[name] = s
    out = {"what": "loosened rules together (packages of knob_study.py knobs): cells counted on the 20 reference "
                   "wings at VC (4 Re) and the 4 wings 0 at M (Re 3e5, 4e6), rule set 2; the 4 wings 0 built at VC "
                   "(Re 3e5, 4e6)", "packages": {k: v[0] for k, v in PACKAGES.items()},
           "summary": summary, "rows": rows}
    (HERE / "data" / "studies" / out_name).write_text(json.dumps(out, indent=1))
    for name, s in summary.items():
        print(f"{name:10s} " + "  ".join(f"{k} {s[k]['cells']['median'] / 1e6:.2f} M x{s[k]['vs_base']['median']:.2f}"
                                          for k in s if k.startswith(("VC", "M "))) +
              f"  built {s['built_VC_wing0']['passed']}/{s['built_VC_wing0']['of']} {s['built_VC_wing0']['failed']}")


def figure() -> None:
    """docs/page/light_set.png from the light_set*.json files: M cells per package at Re 3e5 and 4e6."""
    from style import INK, LIMIT, LINE, MUTED, RAMP4, plt, save          # noqa: E402
    s, rows = {}, []
    for f in sorted((HERE / "data" / "studies").glob("light_set*.json")):
        d = json.loads(f.read_text())
        s |= d["summary"]
        rows += [r for r in d["rows"] if r["package"] != "base" or not any(x["package"] == "base" for x in rows)]
    order = [k for k in ("base", "A2", "B2_100", "B2_dpw", "C2") if k in s]
    label = {"base": "today", "A2": "A2\nwall growth 1.30\nstation growth 1.25",
             "B2_100": "A2 + tip gap\n100 x s0", "B2_dpw": "A2 + tip gap\n0.1 % semi-span\n(DPW)",
             "C2": "A2 + DPW tip\n+ no band\n(SA runs only)"}
    fig, a = plt.subplots(figsize=(9.0, 4.4))
    w = 0.38
    for x, k in enumerate(order):
        bad = sorted({f"{r['type']} {r['index']}" for r in rows if r["package"] == k and not r["surface_passed"]})
        ok = not bad and s[k]["built_VC_wing0"]["passed"] == s[k]["built_VC_wing0"]["of"]
        for j, (re, col) in enumerate(((3e5, RAMP4[1]), (4e6, RAMP4[3]))):
            v = s[k][f"M Re {re:.0e}"]["cells"]["median"] / 1e6
            a.bar(x + (j - 0.5) * w, v, width=w * 0.92, color=col if ok else "white", edgecolor=col, lw=0.9,
                  hatch=None if ok else "////", label={3e5: "Re 3 × 10⁵", 4e6: "Re 4 × 10⁶"}[re] if x == 0 else None,
                  zorder=3)
            a.annotate(f"{v:.1f}", (x + (j - 0.5) * w, v), xytext=(0, 2), textcoords="offset points", ha="center",
                       va="bottom", fontsize=8, color=INK)
        if not ok:
            a.annotate("the BWB tip cap\nfails at M", (x, s[k]["M Re 4e+06"]["cells"]["median"] / 1e6),
                       xytext=(0, 16), textcoords="offset points", ha="center", va="bottom", fontsize=7.6, color=MUTED)
    a.axhline(10, color=LIMIT, lw=1.0, ls="--", zorder=2)
    a.annotate("10 M", (len(order) - 0.5, 10), xytext=(-2, 3), textcoords="offset points", ha="right", va="bottom",
               fontsize=8, color=LIMIT)
    a.set_xticks(range(len(order)), [label[k] for k in order], fontsize=8)
    a.set_ylabel("cells at M (millions)")
    a.grid(axis="y", color=LINE, lw=0.5, zorder=0)
    a.legend(loc="upper right", frameon=False, title="the 4 wings 0, median", title_fontsize=8)
    a.set_title("Loosened rules together: the cells at M (filled: every check passes; hatched: a check fails)",
                fontsize=9.5)
    fig.text(0.01, 0.005, "Rule set 2; what-if packages, the rules unchanged (light_set*.json). Checked: every counted "
             "surface (20 wings x 4 Re at VC, 4 x 2 at M) and 8 VC volume builds. F is about 2.2 x M.",
             fontsize=7.4, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    save(fig, HERE / "docs" / "page" / "light_set.png")


if __name__ == "__main__":
    if "--figure" in sys.argv:
        figure()
    else:
        main()
