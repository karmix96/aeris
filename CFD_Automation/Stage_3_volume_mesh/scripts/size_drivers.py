"""Axis 1: is the mesh size set by the wing and the flow? Each count of the mesh against the wing quantity the rules
compute it from (the 702 built wings at VC, Re 3e5, V6), and the cells against Re (the 20 reference wings, band on).

    python scripts/size_drivers.py

-> data/studies/size_drivers.json, docs/page/size_drivers.png
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from style import ACCENT, INK, LINE, MUTED, TYPE_NAME, TYPES, plt, save   # noqa: E402
sys.path.insert(0, str(HERE.parent))
from cfdauto.geometry.build import load_set                    # noqa: E402
from cfdauto.geometry.params import load_config, resolve       # noqa: E402
from cfdauto.geometry.sections import build_wing_sections      # noqa: E402

STUDIES = HERE / "data" / "studies"
MARK = {"bwb": "o", "flying_wing": "s", "cranked": "^", "tapered": "D"}


def planform(stations) -> dict:
    y = np.array([s.y for s in stations])
    c = np.array([s.chord for s in stations])
    s_local = 0.0                                   # the semi-span in local chords: the integral of dy / c(y)
    for k in range(3):
        dy, c0, c1 = y[k + 1] - y[k], c[k], c[k + 1]
        if dy > 0:
            s_local += dy * (np.log(c1 / c0) / (c1 - c0) if abs(c1 - c0) > 1e-9 else 1.0 / c0)
    return {"semi_span_c": float(y[-1]), "semi_span_local_c": float(s_local), "chord_max": float(c.max()),
            "chord_min": float(c.min()), "taper_tip_root": float(c[-1] / c[0])}


def main() -> None:
    cfg = load_config()
    rows = []
    for tag in ("s_a1", "s_a2", "s_b1", "s_b2"):
        rows += [json.loads(x) for x in (STUDIES / f"screen_r2_{tag}.jsonl").read_text().splitlines()]
    rows = [r for r in rows if r.get("cells")]
    sets, out = {}, []
    for r in rows:
        key = (r["type"], r["set"])
        if key not in sets:
            sets[key] = load_set(*key)["vectors"]
        vec = resolve(cfg.types[r["type"]], sets[key][r["index"]])
        _, st = build_wing_sections(cfg.types[r["type"]], vec, cfg.te)
        out.append({k: r[k] for k in ("type", "set", "index", "cells")} | r["counts"] | planform(st)
                   | {"aspect_ratio": vec["aspect_ratio"]})
    a = {k: np.array([o[k] for o in out], float) for k in out[0] if k not in ("type", "set")}
    corr = lambda u, v: float(np.corrcoef(a[u], a[v])[0, 1])
    links = {"n_span (stations) ~ semi-span in local chords": corr("n_span", "semi_span_local_c"),
             "n_c (nodes around the section) ~ taper (tip / root chord)": corr("n_c", "taper_tip_root"),
             "n_wake (wake nodes) ~ smallest chord": corr("n_wake", "chord_min"),
             "n_layers (wall-normal) ~ largest chord": corr("n_layers", "chord_max"),
             "cells ~ taper": corr("cells", "taper_tip_root"), "cells ~ aspect ratio": corr("cells", "aspect_ratio")}
    planes = a["n_span"] + a["n_out"]
    product = (a["n_c"] + 2 * a["n_wake"]) * a["n_layers"] * planes
    links["cells ~ (around + 2 x wake) x layers x planes"] = float(np.corrcoef(a["cells"], product)[0, 1])
    sf = json.loads((STUDIES / "size_factors.json").read_text())
    per = {}
    for r in sf["rows"]:
        if r["band"]:
            per.setdefault(f"{r['type']} {r['index']}", {})[str(r["re"])] = r["cells"]
    res = sorted({float(k) for v in per.values() for k in v})
    ratio = [v[str(res[-1])] / v[str(res[0])] for v in per.values()]
    summary = {"wings": len(out), "cells": {"min": float(a["cells"].min()), "max": float(a["cells"].max())},
               "correlations": links, "re_ratio_4e6_over_1e5": {"min": min(ratio), "max": max(ratio)},
               "counts_range": {k: [float(a[k].min()), float(a[k].max())] for k in ("n_c", "n_layers", "n_span", "n_wake", "n_out")}}
    (STUDIES / "size_drivers.json").write_text(json.dumps({"summary": summary, "rows": out}, indent=1))

    fig, ax = plt.subplots(1, 4, figsize=(15.5, 3.9))
    a0 = ax[0]                                       # (a) every reference wing against Re
    for name, v in per.items():
        t = name.rsplit(" ", 1)[0]
        a0.plot(res, [v[str(r)] / 1e6 for r in res], "-", color=ACCENT, lw=0.9, alpha=0.55)
        a0.plot(res, [v[str(r)] / 1e6 for r in res], MARK[t], color=ACCENT, ms=3.6, mec="white", mew=0.4, alpha=0.85)
    a0.set_xscale("log")
    a0.set_xlabel("Re on the mean chord")
    a0.set_ylabel("cells at VC (millions)")
    a0.set_title("(a) each reference wing against Re")
    panels = [("semi_span_local_c", "n_span", "semi-span in local chords (∫ dy / c)", "stations along the semi-span",
               "(b) stations follow the planform"),
              ("taper_tip_root", "n_c", "taper (tip chord / root chord)", "nodes around the section",
               "(c) nodes around follow the chord spread"),
              ("chord_min", "n_wake", "smallest chord (mean chords)", "wake nodes, base to outflow",
               "(d) wake nodes follow the smallest chord")]
    for axk, (xk, yk, xl, yl, title) in zip(ax[1:], panels):
        for t in TYPES:
            m = np.array([o["type"] == t for o in out])
            axk.plot(a[xk][m], a[yk][m], MARK[t], color=ACCENT, ms=3.2, mec="white", mew=0.3, alpha=0.7,
                     label=TYPE_NAME[t])
        axk.set_xlabel(xl)
        axk.set_ylabel(yl)
        axk.set_title(title)
        r = float(np.corrcoef(a[xk], a[yk])[0, 1])
        axk.annotate(f"correlation {r:+.2f}", (0.03, 0.95), xycoords="axes fraction", va="top", fontsize=8.5,
                     color=INK)
    for axk in ax:
        axk.grid(color=LINE, lw=0.5)
    ax[1].legend(loc="lower right", frameon=False, title="wing type (marker)", title_fontsize=8)
    fig.text(0.01, 0.005, "Rule set 2, Re 3 × 10⁵ for (b)–(d): the 702 built wings at VC (V6). (a): the 20 reference "
             "wings, band on, VC.", fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    save(fig, HERE / "docs" / "page" / "size_drivers.png")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
