"""Study 9 (7 Nov 2026): the new screen of the surface mesher, with the new rules (configs/surface.yaml).

    python scripts/screen_study.py                 # merge the parts; the study files; the figures
    python scripts/screen_study.py --figures-only  # the figures from the study files already written

The screen runs in parts (scripts/screen.py --resume, one process at a time; data/meshes/run_screen.sh):
  ref_VC, ref_C, ref_M, ref_F   the 20 reference wings x the four Re levels on the mean chord, at each level
  VC_<type>, F_<type>           the other sets (training_focus, training_full, corner1, corner2) at Re 3e5
Writes data/studies/screen_VC.json and screen_F.json (every set at Re 3e5; the reference wings at all four Re levels),
screen_reference_new.json (the reference wings at VC, C, M, F), screen_new_summary.json (every number the docs quote)
and docs/page/screen_new_counts.png, screen_new_cells.png, screen_new_family.png, screen_new_checks.png.

Cells of the wing blocks per mesh (an estimate; scripts/screen.py): n = max over the stations of
ceil(ln(1 + (g - 1) D / s0) / ln g), cells = (ring nodes - 1)(stations - 1) n + cap quads x n, with g the level's wall
growth (1.25 at VC; 1.187, 1.141, 1.107 at C, M, F), s0 the level's first cell at the station's local Re and D = 2
local chords. RAM for ADflow: 1.51 GiB + 9.46 GiB per million cells (AERIS ADR-0020): the desktop today takes about
1.2 M cells (13 GB for WSL), with +32 GB about 4.6 M.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve()
STAGE2 = HERE.parents[1]
STUDIES = STAGE2 / "data" / "studies"
PARTS = STAGE2 / "data" / "meshes" / "screen_parts"
OUT = STAGE2 / "docs" / "page"
LEVELS = ("VC", "C", "M", "F")
TYPES = ("bwb", "flying_wing", "cranked", "tapered")
TYPE_NAME = {"bwb": "BWB", "flying_wing": "flying wing", "cranked": "cranked", "tapered": "tapered"}
RE_LEVELS = (1.0e5, 3.0e5, 1.5e6, 3.0e6)
RE_NAME = {1.0e5: "10⁵", 3.0e5: "3 × 10⁵", 1.5e6: "1.5 × 10⁶", 3.0e6: "3 × 10⁶"}
SPACINGS = ("nose_root", "nose_tip", "te_root", "band_root", "band_tip", "root_gap", "tip_gap", "base_cell")
SPACING_NAME = {"nose_root": "nose cell, root", "nose_tip": "nose cell, tip", "te_root": "trailing-edge cell",
                "band_root": "band cell, root", "band_tip": "band cell, tip", "root_gap": "first station gap",
                "tip_gap": "last station gap (tip)", "base_cell": "base cell"}
RAM_BASE, RAM_PER_M = 1.51, 9.46                       # GiB, GiB per million cells (ADflow; AERIS ADR-0020)
DESKTOP, DESKTOP_32 = 1.2e6, 4.6e6                     # cells: the desktop today (13 GB WSL cap), and with +32 GB
ASKED = (9e6, 11e6)                                    # the fine level asked on 3 Nov
F_ESTIMATE_6NOV = 10.9e6                               # the 6 Nov estimate (plan file; 20 reference wings x 4 Re)
EXACT = ("loft_stations_hit", "planar_stations", "ring_count")    # checks that hold to machine precision

INK, MUTED, LINE = "#142230", "#566573", "#D6DEE6"
ACC, BWB, WARN, AMBER, VIOLET = "#0C5EA8", "#2E8B57", "#B02A20", "#9A6200", "#6A4BB0"
GREY = "#8C98A4"
COLS = {"bwb": BWB, "flying_wing": AMBER, "cranked": ACC, "tapered": VIOLET}
LCOL = {"VC": "#7FA7CF", "C": "#4A83BD", "M": "#1F5F9E", "F": "#0B3C6E"}
plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": LINE, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.titlesize": 10, "axes.titlecolor": INK, "legend.fontsize": 8.5,
                     "figure.dpi": 130, "savefig.dpi": 130, "axes.spines.top": False, "axes.spines.right": False})


def ram_gib(cells: float) -> float:
    return RAM_BASE + RAM_PER_M * cells / 1e6


# --- merging --------------------------------------------------------------------------------------------
def read_part(name: str) -> dict | None:
    """A finished part (.json), else the rows built so far (.jsonl), else None."""
    js, jl = PARTS / f"{name}.json", PARTS / f"{name}.jsonl"
    if js.exists():
        return json.loads(js.read_text()) | {"finished": True}
    if jl.exists():
        rows = []
        for line in jl.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return {"rows": rows, "finished": False}
    return None


def write_rows_json(path: Path, head: dict, rows: list[dict]) -> None:
    """The header indented, one compact line per row (about a third of the size of an indented file)."""
    txt = json.dumps(head, indent=1)
    body = ",\n".join(json.dumps(r, separators=(",", ":")) for r in rows)
    path.write_text(txt[:-2] + ',\n "rows": [\n' + body + "\n ]\n}\n")


def _sort(rows):
    return sorted(rows, key=lambda r: (TYPES.index(r["wing_type"]), r["set"], r["index"], r["re_mean"]))


def merge(final: bool = True) -> dict:
    sys.path.insert(0, str(HERE.parent))
    from screen import summarise
    parts, out = {}, {}
    for name in [f"ref_{lev}" for lev in LEVELS] + [f"{lev}_{t}" for lev in ("VC", "F") for t in TYPES]:
        d = read_part(name)
        if d is not None:
            parts[name] = d
    heads = {n: d for n, d in parts.items() if d.get("finished")}
    hashes = {d["mesh_code_hash"] for d in heads.values()}
    if len(hashes) > 1:
        raise SystemExit(f"the parts were built with different mesh code: {hashes}")
    for lev in ("VC", "F"):
        names = [f"ref_{lev}"] + [f"{lev}_{t}" for t in TYPES]
        rows = _sort([r for n in names if n in parts for r in parts[n]["rows"]])
        done = all(n in heads for n in names)
        h = heads.get(f"ref_{lev}") or next((heads[n] for n in names if n in heads), {})
        out[lev] = {"rows": rows, "complete": done}
        if final and done and rows:
            head = {k: h[k] for k in ("code_version", "mesh_code_hash", "level", "config", "rules", "check_rules",
                                      "cell_estimate")}
            head |= {"date": "2026-11-07", "parts": names, "summary": summarise(rows)}
            write_rows_json(STUDIES / f"screen_{lev}.json", head, rows)
            print(f"wrote screen_{lev}.json: {head['summary']['passed']} of {head['summary']['total']} passed")
    ref = {lev: parts[f"ref_{lev}"]["rows"] for lev in LEVELS if f"ref_{lev}" in parts}
    out["ref"] = ref
    out["ref_complete"] = all(f"ref_{lev}" in heads for lev in LEVELS)
    if final and out["ref_complete"]:
        rows = [r for lev in LEVELS for r in _sort(ref[lev])]
        h = heads["ref_VC"]
        head = {"code_version": h["code_version"], "mesh_code_hash": h["mesh_code_hash"], "config": h["config"],
                "date": "2026-11-07", "levels": list(LEVELS), "re_levels": list(RE_LEVELS),
                "rules": {lev: heads[f"ref_{lev}"]["rules"] for lev in LEVELS},
                "check_rules": {lev: heads[f"ref_{lev}"]["check_rules"] for lev in LEVELS},
                "cell_estimate": h["cell_estimate"],
                "summary": {lev: summarise(ref[lev]) for lev in LEVELS}}
        write_rows_json(STUDIES / "screen_reference_new.json", head, rows)
        print("wrote screen_reference_new.json:", {lev: head["summary"][lev]["passed"] for lev in LEVELS})
    out["heads"] = heads
    return out


# --- the numbers ------------------------------------------------------------------------------------------
def mmm(v) -> dict:
    v = np.asarray(v, dtype=float)
    if v.size == 0:
        return {}
    return {"min": float(v.min()), "median": float(np.median(v)), "max": float(v.max()), "n": int(v.size)}


def used_share(c: dict) -> float | None:
    """How much of the room to its limit a check used: 1 = at the limit (refused above 1)."""
    v, lim, kind = c["value"], c["limit"], c["kind"]
    if kind == "max":
        base = 1.0 if lim > 1.0 and lim < 2.0 else 0.0          # growth-type limits (1.1 ... 1.3): the room is lim - 1
        return (v - base) / (lim - base) if lim != base else None
    if kind == "min":
        return lim / v if v > 0 else float("inf")
    if kind == "band":
        lo, hi = lim
        return max((v - 1.0) / (hi - 1.0) if v >= 1.0 else (1.0 - v) / (1.0 - lo), 0.0)
    return None


def level_numbers(rows: list[dict]) -> dict:
    built = [r for r in rows if r["built"]]
    out = {"builds": len(rows), "passed": sum(r["passed"] for r in rows),
           "refused": sum(1 for r in built if not r["passed"]), "crashed": sum(1 for r in rows if not r["built"]),
           "wings": len({(r["wing_type"], r["set"], r["index"]) for r in rows}),
           "failed_checks": {}, "repairs": sum(1 for r in built if r["turning_repairs"] > 0),
           "repair_rounds_max": max([r["turning_repairs"] for r in built], default=0),
           "repaired": sorted({f"{r['wing_type']} {r['set']} {r['index']}" for r in built if r["turning_repairs"] > 0}),
           "repaired_by_type": {t: sum(1 for r in built if r["turning_repairs"] > 0 and r["wing_type"] == t) for t in TYPES}}
    for r in rows:
        for f in r["failed"]:
            out["failed_checks"][f] = out["failed_checks"].get(f, 0) + 1
    for k in ("n_ring", "n_span", "quads", "cap_quads", "seconds", "cells_est", "wall_layers"):
        out[k] = mmm([r[k] for r in built])
    out["ram_gib"] = mmm([ram_gib(r["cells_est"]) for r in built])
    out["fits_desktop"] = sum(r["cells_est"] <= DESKTOP for r in built)
    out["fits_desktop_32"] = sum(r["cells_est"] <= DESKTOP_32 for r in built)
    st = {}
    for r in built:
        for k, n in r["nose_solved_at"].items():
            st[k] = st.get(k, 0) + n
    out["nose_solved_at_stations"] = st
    out["builds_with_a_VC_nose"] = sum(1 for r in built if r["nose_solved_at"].get("VC", 0) > 0)
    worst = {}
    for r in built:
        for name, c in r["checks"].items():
            u = used_share(c) if name not in EXACT else None
            w = worst.setdefault(name, {"min_margin": None})
            if w["min_margin"] is None or c["margin"] < w["min_margin"]:
                w.update({"min_margin": c["margin"], "value": c["value"], "limit": c["limit"], "kind": c["kind"],
                          "at": f"{r['wing_type']} {r['set']} {r['index']} Re {r['re_mean']:.1e}"})
            if u is not None:
                w["used_max"] = max(w.get("used_max", -1e9), u)
    out["checks"] = worst
    out["nose_turning"] = mmm([r["checks"]["nose_turning"]["value"] for r in built])
    out["wing_quads_J"] = mmm([r["checks"]["wing_quads"]["value"] for r in built])
    out["cap_quads_J"] = mmm([r["checks"]["cap_quads"]["value"] for r in built])
    out["chord_growth"] = mmm([r["checks"]["chord_growth"]["value"] for r in built])
    out["span_growth"] = mmm([r["checks"]["span_growth"]["value"] for r in built])
    out["tip_gap"] = mmm([r["checks"]["tip_gap"]["value"] for r in built])
    out["by_type"] = {}
    for t in TYPES:
        rt = [r for r in rows if r["wing_type"] == t]
        bt = [r for r in rt if r["built"]]
        out["by_type"][t] = {"builds": len(rt), "passed": sum(r["passed"] for r in rt),
                             **{k: mmm([r[k] for r in bt]) for k in ("n_ring", "n_span", "quads", "cells_est", "seconds")},
                             "wing_quads_J": mmm([r["checks"]["wing_quads"]["value"] for r in bt]),
                             "cap_quads_J": mmm([r["checks"]["cap_quads"]["value"] for r in bt])}
    out["by_set"] = {}
    for s in sorted({r["set"] for r in rows}):
        rs = [r for r in rows if r["set"] == s]
        out["by_set"][s] = {"builds": len(rs), "passed": sum(r["passed"] for r in rs)}
    out["by_re"] = {}
    for re in RE_LEVELS:
        rr = [r for r in built if r["set"] == "reference" and r["re_mean"] == re]
        if rr:
            out["by_re"][f"{re:.1e}"] = {k: mmm([r[k] for r in rr]) for k in ("n_ring", "n_span", "cells_est")}
    return out


def family(ref: dict) -> dict:
    """Ratios between neighbouring levels on the reference wings, matched by wing and Re (coarser / finer for the
    spacings, finer / coarser for the counts)."""
    idx = {lev: {(r["wing_type"], r["index"], r["re_mean"]): r for r in ref.get(lev, []) if r["built"]} for lev in LEVELS}
    out = {}
    for a, b in zip(LEVELS[:-1], LEVELS[1:]):
        keys = sorted(set(idx[a]) & set(idx[b]))
        if not keys:
            continue
        d = {"pairs": len(keys), "spacings": {}, "counts": {}, "spacings_no_repair": {}}
        rep = [k for k in keys if idx[a][k]["turning_repairs"] > 0 or idx[b][k]["turning_repairs"] > 0]
        clean = [k for k in keys if k not in rep]
        d["repaired_pairs"] = len(rep)
        d["repaired"] = sorted({f"{k[0]} {k[1]}" for k in rep})
        for s in SPACINGS:
            d["spacings"][s] = mmm([idx[a][k]["spacings"][s] / idx[b][k]["spacings"][s] for k in keys])
            d["spacings_no_repair"][s] = mmm([idx[a][k]["spacings"][s] / idx[b][k]["spacings"][s] for k in clean])
            if rep:
                d.setdefault("spacings_repaired", {})[s] = mmm([idx[a][k]["spacings"][s] / idx[b][k]["spacings"][s] for k in rep])
        for c in ("n_ring", "n_span", "wall_layers", "quads", "cells_est"):
            d["counts"][c] = mmm([idx[b][k][c] / idx[a][k][c] for k in keys])
        d["counts"]["ring_cells"] = mmm([(idx[b][k]["n_ring"] - 1) / (idx[a][k]["n_ring"] - 1) for k in keys])
        d["counts"]["station_gaps"] = mmm([(idx[b][k]["n_span"] - 1) / (idx[a][k]["n_span"] - 1) for k in keys])
        out[f"{a}/{b}"] = d
    return out


def summary(m: dict) -> dict:
    s = {"date": "2026-11-07", "desktop_cells": DESKTOP, "desktop_32_cells": DESKTOP_32,
         "ram": f"{RAM_BASE} GiB + {RAM_PER_M} GiB per million cells (ADflow; AERIS ADR-0020)",
         "asked_F": list(ASKED), "F_estimate_6nov": F_ESTIMATE_6NOV,
         "complete": {"VC": m["VC"]["complete"], "F": m["F"]["complete"], "reference": m["ref_complete"]},
         "full": {lev: level_numbers(m[lev]["rows"]) for lev in ("VC", "F") if m[lev]["rows"]},
         "full_re3e5": {lev: level_numbers([r for r in m[lev]["rows"] if r["re_mean"] == 3.0e5])
                        for lev in ("VC", "F") if m[lev]["rows"]},
         "reference": {lev: level_numbers(rows) for lev, rows in m["ref"].items() if rows},
         "family": family(m["ref"])}
    if m["heads"]:
        h = next(iter(m["heads"].values()))
        s["mesh_code_hash"] = h["mesh_code_hash"]
        s["code_version"] = h["code_version"]
    rv = s["reference"]
    if "F" in rv and rv["F"]["builds"]:
        f = rv["F"]["cells_est"]
        s["F_reference_median_cells"] = f["median"]
        s["F_reference_vs_6nov"] = f["median"] / F_ESTIMATE_6NOV
    return s


# --- figures ----------------------------------------------------------------------------------------------
def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT / name)
    plt.close(fig)
    print("wrote", name)


def _box(a, data, pos, col, width=0.16):
    data = [d if len(d) else [np.nan] for d in data]
    bp = a.boxplot(data, positions=pos, widths=width, patch_artist=True, showfliers=True, whis=(0, 100),
                   medianprops=dict(color=INK, lw=1.2), flierprops=dict(ms=2))
    for b in bp["boxes"]:
        b.set(facecolor=col, alpha=0.75, edgecolor=col)
    for w in bp["whiskers"] + bp["caps"]:
        w.set(color=col)


def fig_counts(m: dict) -> None:
    """Ring nodes, stations and cells per level and type: all sets at Re 3e5 (VC, F) and the reference wings."""
    ref = m["ref"]
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.6))
    for a, key, label, log in ((ax[0], "n_ring", "ring nodes", False), (ax[1], "n_span", "stations", False),
                               (ax[2], "cells_est", "cells per mesh, wing blocks [millions]", True)):
        for j, lev in enumerate(LEVELS):
            data = []
            for t in TYPES:
                rows = [r for r in ref.get(lev, []) if r["built"] and r["wing_type"] == t]
                data.append([r[key] / (1e6 if key == "cells_est" else 1) for r in rows])
            _box(a, data, [i * 5 + j for i in range(len(TYPES))], LCOL[lev], width=0.75)
        a.set_xticks([i * 5 + 1.5 for i in range(len(TYPES))], [TYPE_NAME[t] for t in TYPES])
        a.set_ylabel(label)
        if log:
            a.set_yscale("log")
        a.grid(axis="y", color=LINE, lw=0.5)
    for lev in LEVELS:
        ax[0].bar([0], [0], color=LCOL[lev], label=lev)
    ax[0].legend(title="level", ncol=4, loc="upper left", fontsize=8, title_fontsize=8, frameon=False)
    ax[0].set_title("ring nodes (20 reference wings × 4 Re levels)", fontsize=9.5)
    ax[1].set_title("stations (the same 80 builds per level)", fontsize=9.5)
    a = ax[2]
    a.axhspan(ASKED[0] / 1e6, ASKED[1] / 1e6, color=BWB, alpha=0.12)
    a.axhline(DESKTOP / 1e6, color=WARN, ls="--", lw=1)
    a.axhline(DESKTOP_32 / 1e6, color=AMBER, ls="--", lw=1)
    a.text(19.6, DESKTOP / 1e6 * 0.88, "desktop today ≈ 1.2 M", color=WARN, fontsize=7.6, ha="right", va="top")
    a.text(19.6, DESKTOP_32 / 1e6 * 1.08, "with +32 GB ≈ 4.6 M", color=AMBER, fontsize=7.6, ha="right")
    a.text(-0.6, ASKED[1] / 1e6 * 1.06, "F asked: 9–11 M", color=BWB, fontsize=7.6)
    a.set_title("cells per mesh (estimate: surface × wall layers)", fontsize=9.5)
    save(fig, "screen_new_counts.png")


def fig_cells(m: dict, s: dict) -> None:
    fig, ax = plt.subplots(1, 2, figsize=(14.5, 4.5), gridspec_kw={"width_ratios": [1.25, 1]})
    a = ax[0]
    ref = m["ref"]
    x = np.arange(len(LEVELS))
    for off, (lab, rowsf, col) in enumerate((
            ("20 reference wings × 4 Re levels", lambda lev: [r for r in ref.get(lev, []) if r["built"]], ACC),
            ("every set at Re 3 × 10⁵ (VC and F only)",
             lambda lev: [r for r in m.get(lev, {}).get("rows", []) if r["built"] and r["re_mean"] == 3.0e5] if lev in ("VC", "F") else [],
             AMBER))):
        med, mx, xs = [], [], []
        for i, lev in enumerate(LEVELS):
            rr = rowsf(lev)
            if rr:
                v = np.array([r["cells_est"] for r in rr]) / 1e6
                med.append(np.median(v)); mx.append(v.max()); xs.append(i + (off - 0.5) * 0.36)
        if xs:
            a.bar(xs, med, 0.34, color=col, alpha=0.85, label=f"{lab}: median (bar), largest (tick)")
            a.errorbar(xs, med, yerr=[np.zeros(len(med)), np.array(mx) - np.array(med)], fmt="none", ecolor=INK, capsize=4, lw=1)
            for xx, mm_, xm in zip(xs, med, mx):
                a.text(xx, xm * 1.12, f"{mm_:.2g}\n({xm:.2g})", ha="center", fontsize=7.4)
    a.axhspan(ASKED[0] / 1e6, ASKED[1] / 1e6, color=BWB, alpha=0.12)
    a.text(-0.45, ASKED[1] / 1e6 * 1.05, "F asked: 9–11 M (3 Nov)", color=BWB, fontsize=7.8)
    a.axhline(DESKTOP / 1e6, color=WARN, ls="--", lw=1)
    a.text(3.45, DESKTOP / 1e6 * 0.86, "desktop today ≈ 1.2 M cells (13 GB)", color=WARN, fontsize=7.6, ha="right", va="top")
    a.axhline(DESKTOP_32 / 1e6, color=AMBER, ls="--", lw=1)
    a.text(3.45, DESKTOP_32 / 1e6 * 1.06, "with +32 GB ≈ 4.6 M cells", color=AMBER, fontsize=7.6, ha="right")
    a.set_yscale("log"); a.set_ylim(0.1, 60); a.set_xticks(x, LEVELS); a.set_ylabel("cells per mesh, wing blocks [millions]")
    a.legend(loc="upper left", fontsize=7.6, frameon=False)
    a.set_title("cells per mesh, per level (wing blocks; the C-H wake lines not counted)", fontsize=9.5)
    sec = a.secondary_yaxis("right", functions=(lambda c: RAM_BASE + RAM_PER_M * c, lambda g: (g - RAM_BASE) / RAM_PER_M))
    sec.set_ylabel("RAM for ADflow [GiB]")
    a = ax[1]
    rv = s["reference"].get("F")
    names = ["6 Nov estimate\n(plan file, real-size\nwings, fewer stations)", "7 Nov screen\n(built rules,\nunit mean chord)",
             "7 Nov screen\n+ C-H wake lines\n(rough +30…60 %)"]
    if rv:
        f = rv["cells_est"]
        med = [F_ESTIMATE_6NOV / 1e6, f["median"] / 1e6, f["median"] / 1e6 * 1.45]
        lo = [4.9, f["min"] / 1e6, f["median"] / 1e6 * 1.30]
        hi = [15.9, f["max"] / 1e6, f["median"] / 1e6 * 1.60]
        bars = a.bar(names, med, color=[GREY, ACC, ACC], alpha=0.85, width=0.6)
        bars[2].set_hatch("//"); bars[2].set_alpha(0.45)
        a.errorbar(range(3), med, yerr=[np.array(med) - np.array(lo), np.array(hi) - np.array(med)], fmt="none",
                   ecolor=INK, capsize=4, lw=1)
        for i, v in enumerate(med):
            a.text(i + 0.33, v, f"{v:.1f} M" if i < 2 else f"≈ {v:.0f} M", fontsize=8.5, va="center")
    a.axhspan(ASKED[0] / 1e6, ASKED[1] / 1e6, color=BWB, alpha=0.12)
    a.text(-0.45, ASKED[1] / 1e6 + 0.3, "asked: 9–11 M", color=BWB, fontsize=7.8)
    a.set_ylabel("fine level F, cells per mesh [millions]")
    a.set_title("fine level F, 20 reference wings × 4 Re: median, range", fontsize=9.5)
    save(fig, "screen_new_cells.png")


def fig_family(s: dict) -> None:
    fam = s["family"]
    pairs = [p for p in ("VC/C", "C/M", "M/F") if p in fam]
    fig, ax = plt.subplots(1, 2, figsize=(14.5, 4.3), gridspec_kw={"width_ratios": [1.5, 1]})
    a = ax[0]
    x = np.arange(len(SPACINGS))
    pc = {"VC/C": LCOL["C"], "C/M": LCOL["M"], "M/F": LCOL["F"]}
    for k, p in enumerate(pairs):
        d = fam[p]["spacings_no_repair"]
        med = np.array([d[q]["median"] for q in SPACINGS])
        lo = np.array([d[q]["min"] for q in SPACINGS]); hi = np.array([d[q]["max"] for q in SPACINGS])
        xx = x + (k - (len(pairs) - 1) / 2) * 0.26
        a.bar(xx, med, 0.25, color=pc[p], label=f"{p} ({fam[p]['pairs'] - fam[p].get('repaired_pairs', 0)} pairs)")
        a.errorbar(xx, med, yerr=[med - lo, hi - med], fmt="none", ecolor=INK, capsize=2, lw=0.8)
        if fam[p].get("repaired_pairs"):
            dr = fam[p]["spacings_repaired"]
            for q in ("nose_root", "nose_tip"):
                i = SPACINGS.index(q)
                a.plot([xx[i]], [dr[q]["median"]], "x", color=WARN, ms=7, mew=1.6,
                       label="nose, builds repaired at M" if (q == "nose_root" and p == next(pp for pp in pairs if fam[pp].get("repaired_pairs"))) else None)
    a.axhline(1.3, color=WARN, ls="--", lw=1)
    a.text(len(SPACINGS) - 0.5, 1.305, "r = 1.3", color=WARN, fontsize=8, ha="right", va="bottom")
    a.set_xticks(x, [SPACING_NAME[q] for q in SPACINGS], rotation=25, ha="right", fontsize=8.2)
    a.set_ylim(1.0, 1.6); a.set_ylabel("spacing, coarser level / finer level")
    a.legend(loc="upper left", fontsize=8, frameon=False, ncol=3)
    a.set_title("every spacing between neighbouring levels: median (bar) and range, 20 reference wings × 4 Re\n(the builds without a nose repair; ×: the nose of the builds repaired at M)", fontsize=9.5)
    a = ax[1]
    keys = [("ring_cells", "ring cells"), ("station_gaps", "station gaps"), ("wall_layers", "wall layers"),
            ("cells_est", "cells")]
    x = np.arange(len(keys))
    for k, p in enumerate(pairs):
        d = fam[p]["counts"]
        med = np.array([d[q]["median"] for q, _ in keys])
        lo = np.array([d[q]["min"] for q, _ in keys]); hi = np.array([d[q]["max"] for q, _ in keys])
        xx = x + (k - (len(pairs) - 1) / 2) * 0.26
        a.bar(xx, med, 0.25, color=pc[p], label=p)
        a.errorbar(xx, med, yerr=[med - lo, hi - med], fmt="none", ecolor=INK, capsize=2, lw=0.8)
    a.axhline(1.3, color=WARN, ls="--", lw=1); a.axhline(1.3 ** 3, color=AMBER, ls="--", lw=1)
    a.text(3.4, 1.3 ** 3 + 0.04, "1.3³ = 2.2", color=AMBER, fontsize=8, ha="right")
    a.set_xticks(x, [n for _, n in keys]); a.set_ylabel("count, finer level / coarser level"); a.set_ylim(1.0, 2.8)
    a.set_title("counts between neighbouring levels: median and range", fontsize=9.5)
    save(fig, "screen_new_family.png")


def fig_checks(s: dict) -> None:
    names = [("nose_turning", "nose turning"), ("geometry_kinks", "geometry kinks"), ("nose_envelope", "nose envelope"),
             ("chord_growth", "growth along the ring"), ("band_spacing", "band cell"), ("te_spacing", "trailing-edge cell"),
             ("span_growth", "growth between station gaps"), ("tip_gap", "tip gap"), ("wing_quads", "wing quads"),
             ("cap_quads", "cap quads")]
    sets = [("VC", s["full"].get("VC")), ("C", s["reference"].get("C")), ("M", s["reference"].get("M")),
            ("F", s["full"].get("F"))]
    sets = [(lev, d) for lev, d in sets if d]
    fig, ax = plt.subplots(1, 2, figsize=(14.5, 4.6), gridspec_kw={"width_ratios": [1.6, 1]})
    a = ax[0]
    y = np.arange(len(names))[::-1]
    for k, (lev, d) in enumerate(sets):
        v = [max(d["checks"].get(n, {}).get("used_max", np.nan), 0.0) for n, _ in names]
        a.barh(y + (k - (len(sets) - 1) / 2) * 0.2, v, 0.19, color=LCOL[lev], label=f"{lev} ({d['passed']} of {d['builds']} passed)")
    a.axvline(1.0, color=WARN, lw=1.2, ls="--")
    a.text(1.01, len(names) - 0.6, "the limit:\nrefused beyond", color=WARN, fontsize=7.6, va="top")
    a.set_yticks(y, [n for _, n in names], fontsize=8.5); a.set_xlim(0, 1.25)
    a.set_xlabel("share of the room to the limit used by the worst build (1 = at the limit)")
    a.legend(loc="lower right", fontsize=7.6, frameon=False)
    a.set_title("how close the worst build came to each refusal limit (VC and F: every set; C and M: the reference wings)",
                fontsize=9.2)
    a = ax[1]
    for k, (lev, d) in enumerate(sets):
        st = d["nose_solved_at_stations"]
        tot = sum(st.values()) or 1
        a.barh(k, st.get("F", 0) / tot * 100, color=LCOL["F"], label="nose set by the F solve" if k == 0 else None)
        a.barh(k, st.get("VC", 0) / tot * 100, left=st.get("F", 0) / tot * 100, color=AMBER,
               label="nose set by the VC solve" if k == 0 else None)
        nt = d["nose_turning"]
        a.text(101, k, f"largest turning {nt['min']:.1f}–{nt['max']:.1f}°", va="center", fontsize=7.6)
    a.set_yticks(range(len(sets)), [lev for lev, _ in sets]); a.set_xlim(0, 150); a.invert_yaxis()
    a.set_xlabel("stations [%]")
    a.legend(loc="lower right", fontsize=7.6, frameon=False)
    a.set_title("which solve set the nose, and the largest turning delivered", fontsize=9.2)
    save(fig, "screen_new_checks.png")


def load_studies() -> dict:
    """The merged study files (after a full run), for --figures-only."""
    m = {"heads": {}}
    for lev in ("VC", "F"):
        d = json.loads((STUDIES / f"screen_{lev}.json").read_text())
        m[lev] = {"rows": d["rows"], "complete": True}
        m["heads"][f"ref_{lev}"] = d
    d = json.loads((STUDIES / "screen_reference_new.json").read_text())
    m["ref"] = {lev: [r for r in d["rows"] if r["level"] == lev] for lev in LEVELS}
    m["ref_complete"] = True
    return m


def main() -> None:
    figs_only = "--figures-only" in sys.argv
    m = load_studies() if figs_only else merge(final="--draft" not in sys.argv)
    s = summary(m)
    if not figs_only and "--draft" not in sys.argv:
        (STUDIES / "screen_new_summary.json").write_text(json.dumps(s, indent=1))
        print("wrote screen_new_summary.json")
    if "--draft" in sys.argv:
        global OUT
        OUT = Path(sys.argv[sys.argv.index("--draft") + 1])
        (OUT / "screen_new_summary.json").parent.mkdir(parents=True, exist_ok=True)
        (OUT / "screen_new_summary.json").write_text(json.dumps(s, indent=1))
    fig_counts(m)
    fig_cells(m, s)
    fig_family(s)
    fig_checks(s)


if __name__ == "__main__":
    main()
