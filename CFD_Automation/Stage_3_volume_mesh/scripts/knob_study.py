"""Which rule makes the mesh big? Each rule loosened alone (one at a time), cells counted, and the mesh built to see
whether it still passes. A what-if study: the rules files are copied and one value changed; the rules are unchanged.

    python scripts/knob_study.py               (about 50 min on 2 cores)
    python scripts/knob_study.py --figure      (the figure again, from the json)
    python scripts/knob_study.py --recheck     (name the failed surface checks of the first run; 11 Nov)

Counts: the 20 reference wings at VC (Re 3e5); the 4 wings 0 at M, to check that the ratio carries to M.
Builds: the 4 wings 0 at VC, every variant (the surface checks and the volume checks).
-> data/studies/knob_study.json, docs/page/knob_study.png
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from cfdauto.mesh.surface import build_surface, wing_from_set   # noqa: E402
from cfdauto.volume.volume import build_volume, count_volume     # noqa: E402

SURFACE = ROOT / "Stage_2_surface_mesh" / "configs" / "surface.yaml"
VOLUME = HERE / "configs" / "volume.yaml"
RE = 3e5
TYPES = ("bwb", "flying_wing", "cranked", "tapered")

# name: (file, [(old, new), ...], in words)
KNOBS = {
    "band_off": ("surface", [("  transition_band: true ", "  transition_band: false ")], "transition band off"),
    "bubble_10": ("surface", [("nodes_per_bubble: {value: 20,", "nodes_per_bubble: {value: 10,")],
                  "band: 10 cells per bubble at F (not 20)"),
    "nose_13": ("surface", [("nose_turning_deg: {value: 10.0,", "nose_turning_deg: {value: 13.0,")],
                "nose turning 13 deg at M (not 10)"),
    "te_0p2": ("surface", [("te_spacing_c: {value: 0.001,", "te_spacing_c: {value: 0.002,")],
               "trailing-edge cell 0.2 % c at M (not 0.1 %)"),
    "maxcell_3": ("surface", [("max_spacing_c: {value: 0.02,", "max_spacing_c: {value: 0.03,")],
                  "largest chordwise cell 3 % c at M (not 2 %)"),
    "chord_g125": ("surface", [('  growth: {value: 1.20, at: VC, why: "hard minimum', '  growth: {value: 1.25, at: VC, why: "hard minimum'),
                               ('growth_limit: {value: 1.25, at: VC, why: "hard minimum, decision 71; Stage 1',
                                'growth_limit: {value: 1.30, at: VC, why: "hard minimum, decision 71; Stage 1')],
                   "chordwise growth 1.25 at VC (not 1.20)"),
    "station_0p35": ("surface", [("  spacing_c: {value: 0.25,", "  spacing_c: {value: 0.35,")],
                     "station gap 0.35 local c at M (not 0.25)"),
    "panel_8": ("surface", [("min_cells_per_panel: {value: 12,", "min_cells_per_panel: {value: 8,")],
                "8 station gaps per panel at M (not 12)"),
    "span_g125": ("surface", [('  growth: {value: 1.20, at: VC, why: "first approach', '  growth: {value: 1.25, at: VC, why: "first approach')],
                  "station growth 1.25 at VC (not 1.20)"),
    "tip_20s0": ("surface", [("  tip_gap_in_s0: 2.0 ", "  tip_gap_in_s0: 20.0 ")], "tip gap 20 x s0 (not 2)"),
    "tip_100s0": ("surface", [("  tip_gap_in_s0: 2.0 ", "  tip_gap_in_s0: 100.0 ")], "tip gap 100 x s0 (not 2)"),
    "wall_g130": ("volume", [('  growth: {value: 1.25, at: VC, why: "hard minimum, decision 71; DPW"}',
                              '  growth: {value: 1.30, at: VC, why: "hard minimum, decision 71; DPW"}')],
                  "wall-normal growth 1.30 at VC (not 1.25)"),
    "bl_20": ("volume", [("bl_cells: {value: 30,", "bl_cells: {value: 20,")], "20 cells across the boundary layer at M (not 30)"),
    "fine_1c": ("volume", [("  fine_zone_local_c: 2.0 ", "  fine_zone_local_c: 1.0 ")], "wall fine zone 1 local chord (not 2)"),
    "far_g128": ("volume", [("growth_built: {value: 1.22,", "growth_built: {value: 1.28,")], "far growth built 1.28 at VC (not 1.22)"),
    "far_40": ("volume", [("  distance_c: 80.0 ", "  distance_c: 40.0 ")], "far field 40 mean chords (not 80)"),
    "wake_1p5": ("volume", [("spacing_c: {value: 0.0075,", "spacing_c: {value: 0.015,")], "wake band cell 1.5 % c at M (not 0.75 %)"),
    "fan_8": ("volume", [("fan_cells: {value: 12,", "fan_cells: {value: 8,")], "8 cells across the wake fan at M (not 12)"),
    "fan_1c": ("volume", [("    length_local_c: 2.0 ", "    length_local_c: 1.0 ")], "wake fan 1 local chord long (not 2)"),
    "aspect_16": ("volume", [("    max_aspect: 8.0 ", "    max_aspect: 16.0 ")], "wake band cell aspect up to 16 (not 8)"),
    "out_fine_1c": ("volume", [("  fine_zone_c: 2.0 ", "  fine_zone_c: 1.0 ")], "outboard fine zone 1 mean chord (not 2)"),
}


def variant(name: str) -> tuple[Path | None, Path | None]:
    """(surface config, volume config) for one knob; None = the rules as they are."""
    which, reps, _ = KNOBS[name]
    src = SURFACE if which == "surface" else VOLUME
    text = src.read_text()
    for old, new in reps:
        assert text.count(old) == 1, (name, old)
        text = text.replace(old, new)
    p = Path(tempfile.gettempdir()) / f"knob_{name}_{src.name}"
    p.write_text(text)
    return (p, None) if which == "surface" else (None, p)


def one(job) -> list[dict]:
    t, i, level, build = job
    w = wing_from_set(t, "reference", i)
    base = build_surface(w.loft, RE, level)
    rows = []
    for name in ["base"] + list(KNOBS):
        s_cfg, v_cfg = (None, None) if name == "base" else variant(name)
        sm = base if s_cfg is None else build_surface(w.loft, RE, level, config=s_cfg)
        c = count_volume(sm, config=v_cfg)
        r = {"knob": name, "type": t, "index": i, "level": level, "cells": c["cells"], "n_layers": c["n_layers"],
             "n_c": c["n_c"], "n_span": c["n_span"], "n_wake": c["n_wake"], "n_out": c["n_out"],
             "surface_passed": bool(sm.passed), "surface_failed": [x.name for x in sm.failed()]}
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


def summarize(rows: list[dict]) -> dict:
    summary = {}
    for name in ["base"] + list(KNOBS):
        s = {"words": "the rules as they are" if name == "base" else KNOBS[name][2]}
        for level in ("VC", "M"):
            rr = [r for r in rows if r["knob"] == name and r["level"] == level]
            bb = {(r["type"], r["index"]): r for r in rows if r["knob"] == "base" and r["level"] == level}
            s[level] = {"cells": dist([r["cells"] for r in rr]),
                        "vs_base": dist([r["cells"] / bb[(r["type"], r["index"])]["cells"] for r in rr]),
                        "parts_vs_base": {k: float(np.median([r[k] / bb[(r["type"], r["index"])][k] for r in rr]))
                                          for k in ("n_layers", "n_c", "n_span", "n_wake", "n_out")}}
        built = [r for r in rows if r["knob"] == name and "outcome" in r]
        s["built_VC_wing0"] = {"passed": sum(r["outcome"] == "passed" for r in built), "of": len(built),
                               "failed": sorted({x for r in built for x in r["failed"]})}
        # the surface checks of every counted mesh (the 20 wings at VC, the 4 wings 0 at M)
        s["surfaces"] = {lev: {"passed": sum(r["surface_passed"] for r in rows if r["knob"] == name and r["level"] == lev),
                               "of": sum(1 for r in rows if r["knob"] == name and r["level"] == lev),
                               "failed": sorted({f"{x} ({r['type']} {r['index']})" for r in rows
                                                 if r["knob"] == name and r["level"] == lev
                                                 for x in r.get("surface_failed", [])})}
                         for lev in ("VC", "M")}
        summary[name] = s
    return summary


def recheck() -> None:
    """Fill in which surface check failed on the counted meshes that the first run (before surface_failed was
    recorded) only marked as refused; then the summary and the figure again."""
    path = HERE / "data" / "studies" / "knob_study.json"
    d = json.loads(path.read_text())
    for r in d["rows"]:
        if not r["surface_passed"] and not r.get("surface_failed"):
            w = wing_from_set(r["type"], "reference", r["index"])
            s_cfg, _ = (None, None) if r["knob"] == "base" else variant(r["knob"])
            sm = build_surface(w.loft, RE, r["level"], config=s_cfg)
            r["surface_failed"] = [x.name for x in sm.failed()]
            print(r["knob"], r["level"], r["type"], r["index"], r["surface_failed"], flush=True)
    d["summary"] = summarize(d["rows"])
    path.write_text(json.dumps(d, indent=1))
    figure()


def main() -> None:
    jobs = [(t, i, "VC", i == 0) for t in TYPES for i in range(5)] + [(t, 0, "M", False) for t in TYPES]
    jobs.sort(key=lambda j: j[2] != "M")                       # the slow M jobs first
    with Pool(2) as p:
        rows = [r for part in p.map(one, jobs, chunksize=1) for r in part]
    summary = summarize(rows)
    out = {"what": "one rule loosened at a time: cells counted (20 reference wings at VC, wing 0 of each type at M), "
                   "Re 3e5, rule set 2; the 4 wings 0 built at VC", "knobs": {k: v[2] for k, v in KNOBS.items()},
           "summary": summary, "rows": rows}
    (HERE / "data" / "studies" / "knob_study.json").write_text(json.dumps(out, indent=1))
    for name, s in summary.items():
        print(f"{name:14s} VC x{s['VC']['vs_base']['median']:.3f}  M x{s['M']['vs_base']['median']:.3f}  "
              f"built {s['built_VC_wing0']['passed']}/{s['built_VC_wing0']['of']} {s['built_VC_wing0']['failed']}  "
              f"parts M {({k: round(v, 2) for k, v in s['M']['parts_vs_base'].items()})}")
    figure()


def figure() -> None:
    """docs/page/knob_study.png from the json: the change in cells at M per knob, and whether the meshes still pass."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from style import ACCENT, INK, LINE, MUTED, plt, save            # noqa: E402
    d = json.loads((HERE / "data" / "studies" / "knob_study.json").read_text())
    s = {k: v for k, v in d["summary"].items() if k != "base"}
    order = sorted(s, key=lambda k: s[k]["M"]["vs_base"]["median"])
    fig, a = plt.subplots(figsize=(9.2, 0.31 * len(order) + 1.4))
    names, zero = [], []
    for y, k in enumerate(order):
        v = 100 * (s[k]["M"]["vs_base"]["median"] - 1)
        b = s[k]["built_VC_wing0"]
        fails = [f"{', '.join(b['failed'])} (a VC build)"] if b["passed"] < b["of"] else []
        for lev, f in s[k].get("surfaces", {}).items():
            if f["passed"] < f["of"]:
                fails.append(f"{', '.join(f['failed']) or 'the surface'} at {lev}")
        ok = not fails
        a.barh(y, v, height=0.62, color=ACCENT if ok else "white", edgecolor=ACCENT if ok else MUTED,
               hatch=None if ok else "////", lw=0.8, zorder=3)
        a.annotate(f"{v:+.0f} %" if abs(v) >= 0.5 else "0 %", (min(v, 0), y), xytext=(-4, 0),
                   textcoords="offset points", ha="right", va="center", fontsize=8, color=INK if ok else MUTED)
        note = "; ".join(fails)
        for code, words in (("cap_quads", "tip-cap cells"), ("span_growth", "station growth"),
                            ("wake", "wake growth"), ("bwb", "BWB")):
            note = note.replace(code, words)
        names.append(s[k]["words"] + ("" if ok else f"  (fails: {note})"))
        if abs(v) < 0.5:
            zero.append(y)
    a.set_yticks(range(len(order)), names, fontsize=8)
    a.invert_yaxis()
    a.axvline(0, color=INK, lw=0.8, zorder=4)
    lo = min(100 * (s[k]["M"]["vs_base"]["median"] - 1) for k in order)
    a.set_xlim(lo * 1.25 - 4, 3)
    if zero:
        a.annotate("no effect: another rule sets that count", (lo * 0.55, (zero[0] + zero[-1]) / 2), ha="center",
                   va="center", fontsize=8.2, color=MUTED)
    a.yaxis.tick_right()
    a.tick_params(axis="y", length=0)
    a.set_xlabel("change in cells at M against the rules as they are (%)")
    a.grid(axis="x", color=LINE, lw=0.5, zorder=0)
    a.set_title("One rule loosened at a time: the change in cells at M\nfilled: every mesh passes its checks · "
                "hatched: a check fails (the 20 surfaces at VC, the 4 at M, the 4 VC volume builds)", fontsize=9.5)
    fig.text(0.01, 0.005, "Rule set 2, Re 3e5. Each bar: the median over the 4 wings 0 (one per type) at M; the 20 "
             "reference wings at VC give the same within 4 points (data/studies/knob_study.json).", fontsize=7.6,
             color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    save(fig, HERE / "docs" / "page" / "knob_study.png")


if __name__ == "__main__":
    if "--figure" in sys.argv:
        figure()
    elif "--recheck" in sys.argv:
        recheck()
    else:
        main()
