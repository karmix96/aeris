"""Study 14: the hold-outs, opened once with the surface rules frozen (owner, 9 Nov 2026; decision 83).

The 60 hold-out wings (15 per type: holdout_focus 10, holdout_full 5) were sealed: never built or meshed. With the
surface rules frozen (decision 82) they test the mesher on wings it has never seen (Grand Roadmap A3: "robust on the
set the method was tuned on is not generalisation").

    python scripts/holdout_study.py --gates                      # Stage 1: build, gates and labels (numpy loft)
    python scripts/screen.py --family --open-holdouts --sets holdout_focus holdout_full --types bwb cranked \\
        --re 1e5 3e5 1e6 4e6 --tag holdout_bwb_cranked           # and --types flying_wing tapered, in a 2nd process
    python scripts/holdout_study.py                              # merge: data/studies/holdout_screen.json + figure

The wings are built by the same code as every other set. No rule is changed from this result: a failed check is
reported, not fixed (decision 82). The cells are the estimate of the wing blocks (Study 9).
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
import time
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve()
STAGE2 = HERE.parents[1]
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE.parent))

from cfdauto.geometry import build as geometry_build  # noqa: E402
from cfdauto.geometry.params import load_config  # noqa: E402
from screen_study import ACC, AMBER, INK, LCOL, LEVELS, LINE, MUTED, RE_LEVELS, RE_NAME, TYPE_NAME, TYPES, WARN  # noqa: E402,F401

STUDIES = STAGE2 / "data" / "studies"
FAMILY = STAGE2 / "data" / "meshes" / "screen_family"
TAGS = ("holdout_bwb_cranked", "holdout_flying_wing_tapered")
SETS = ("holdout_focus", "holdout_full")
GATES_JSON = STUDIES / "holdout_gates.json"
OUT_JSON = STUDIES / "holdout_screen.json"
OUT_FIG = STAGE2 / "docs" / "page" / "holdout_screen.png"
REF_SUMMARY = STUDIES / "screen_family_summary.json"


def gates() -> None:
    """Stage 1 on the hold-outs: build each wing (numpy loft), run the four gates, label it."""
    cfg = load_config()
    rows = []
    for t in TYPES:
        for s in SETS:
            for i, vec in enumerate(geometry_build.load_set(t, s)["vectors"]):
                t0 = time.time()
                out = geometry_build.WINGS_DIR / t / s / f"{i:03d}"
                r = geometry_build.build(vec, t, cfg, out)
                rows.append({"wing_type": t, "set": s, "index": i, "passed": r["passed"], "gate": r.get("gate"),
                             "reason": r.get("reason"), "input_hash": r["input_hash"],
                             "surface_hash": r.get("surface_hash"), "labels": r.get("labels"),
                             "seconds": round(time.time() - t0, 2)})
                print(f"{'ok ' if r['passed'] else 'XX '}{t:12s} {s:14s} {i:2d}  "
                      + (", ".join(r.get("labels") or []) if r["passed"] else f"{r.get('gate')}: {r.get('reason')}"),
                      flush=True)
    GATES_JSON.write_text(json.dumps({"what": "Stage 1 build, gates and labels of the 60 hold-out wings (numpy loft), "
                                              "opened once on 9 Nov 2026 (decision 83)",
                                      "rows": rows}, indent=1))
    print(f"wrote {GATES_JSON.name}: {sum(r['passed'] for r in rows)} of {len(rows)} pass the gates")


def load_rows() -> dict:
    out = {}
    for lev in LEVELS:
        rows = []
        for tag in TAGS:
            f = FAMILY / f"{tag}_{lev}.json"
            if not f.exists():
                raise SystemExit(f"missing {f.name}: run the two hold-out screens first (see the top of this file)")
            p = json.loads(f.read_text())
            assert p["rules"]["transition_band"] is True, f.name
            rows += p["rows"]
        out[lev] = rows
    return out, p["mesh_code_hash"]


def numbers(rows: dict, gate_rows: list) -> dict:
    ref = json.loads(REF_SUMMARY.read_text())
    n = {"gates": {"wings": len(gate_rows), "passed": sum(r["passed"] for r in gate_rows),
                   "refused": [r for r in gate_rows if not r["passed"]]},
         "levels": {}, "against_study12": {}}
    for lev in LEVELS:
        R = rows[lev]
        built = [r for r in R if r.get("built")]
        cells = [r["cells_est"] for r in built]
        checks = {}
        for r in built:
            for name, c in r["checks"].items():
                checks.setdefault(name, []).append(c["value"])
        turn = [r["checks"]["nose_turning"]["value"] for r in built]
        cap = [r["checks"]["cap_quads"]["value"] for r in built]
        n["levels"][lev] = {
            "builds": len(R), "built": len(built), "passed": sum(r["passed"] for r in R),
            "crashed": sum(not r.get("built") for r in R),
            "failed": [{"wing": f"{TYPE_NAME[r['wing_type']]} {r['set']} {r['index']}", "re": r["re_mean"],
                        "failed": r.get("failed"), "error": r.get("error")} for r in R if not r["passed"]],
            "nose_repairs": sum(((r.get("nose_family") or {}).get("rounds") or 0) > 0 for r in built),
            "cells": {"median": st.median(cells), "max": max(cells), "min": min(cells)} if cells else None,
            "nose_turning_max": max(turn) if turn else None,
            "cap_quads_min": min(cap) if cap else None,
            "by_type_cells_median": {t: st.median([r["cells_est"] for r in built if r["wing_type"] == t])
                                     for t in TYPES if any(r["wing_type"] == t for r in built)},
        }
        fs = ref["full"][lev]
        n["against_study12"][lev] = {"cells_median": fs["cells_est"]["median"], "cells_max": fs["cells_est"]["max"],
                                     "cap_quads_min": (fs.get("cap_quads_J") or {}).get("min"),
                                     "nose_turning_max": (fs.get("nose_turning") or {}).get("max")}
    # the family rule on the hold-outs: nose and trailing-edge cells per level step
    ratios = {}
    for a, b in zip(LEVELS[:-1], LEVELS[1:]):
        ka = {(r["wing_type"], r["set"], r["index"], r["re_mean"]): r for r in rows[a] if r.get("built")}
        kb = {(r["wing_type"], r["set"], r["index"], r["re_mean"]): r for r in rows[b] if r.get("built")}
        vals = {"nose_root": [], "te_root": []}
        for k in set(ka) & set(kb):
            sa, sb = ka[k].get("spacings") or {}, kb[k].get("spacings") or {}
            for name in vals:
                if sa.get(name) and sb.get(name):
                    vals[name].append(sa[name] / sb[name])
        ratios[f"{a}/{b}"] = {name: {"min": min(v), "max": max(v)} for name, v in vals.items() if v}
    n["family_ratios"] = ratios
    return n


def figure(n: dict, rows: dict) -> None:
    fig, ax = plt.subplots(1, 2, figsize=(12.4, 4.4), gridspec_kw={"width_ratios": [1.1, 1]})
    a = ax[0]
    xs = np.arange(len(LEVELS))
    ref = n["against_study12"]
    med_h = [n["levels"][lev]["cells"]["median"] / 1e6 for lev in LEVELS]
    max_h = [n["levels"][lev]["cells"]["max"] / 1e6 for lev in LEVELS]
    med_r = [ref[lev]["cells_median"] / 1e6 for lev in LEVELS]
    max_r = [ref[lev]["cells_max"] / 1e6 for lev in LEVELS]
    for sh, med, mx, col, lab in ((-0.19, med_r, max_r, MUTED, "every set seen before (Study 12)"),
                                  (0.19, med_h, max_h, ACC, "the 60 hold-outs (never seen)")):
        a.bar(xs + sh, med, 0.36, color=col, alpha=0.85, label=f"{lab}: median (bar), largest (tick)")
        a.errorbar(xs + sh, med, yerr=[np.zeros(len(med)), np.array(mx) - np.array(med)], fmt="none", ecolor=INK,
                   capsize=4, lw=1)
        for x, m_, M in zip(xs + sh, med, mx):
            a.text(x, M + 0.2, f"{m_:.2f}\n({M:.2f})", ha="center", va="bottom", fontsize=7.4,
                   bbox=dict(facecolor="white", edgecolor="none", pad=0.4, alpha=0.9))
    a.set_xticks(xs, LEVELS)
    a.set_ylabel("cells per mesh [millions] (wing blocks)")
    a.set_ylim(0, max(max_h + max_r) * 1.35)
    a.grid(axis="y", color=LINE, lw=0.5)
    a.legend(loc="upper left", frameon=False)
    a.set_title("cells per level: the hold-outs against every set seen before")
    a = ax[1]
    for lev in LEVELS:
        built = [r for r in rows[lev] if r.get("built")]
        caps = sorted(r["checks"]["cap_quads"]["value"] for r in built)
        a.plot(caps, np.linspace(0, 1, len(caps)), color=LCOL[lev], lw=2, label=lev)
    a.axvline(0.05, color=WARN, ls="--", lw=1.2, label="limit 0.05")
    a.set_xlabel("tip cap quality (lowest scaled Jacobian per mesh)")
    a.set_ylabel("share of hold-out meshes at or below")
    a.grid(color=LINE, lw=0.5)
    a.legend(title="level", loc="lower right", frameon=False)
    a.set_title("the closest check, the tip cap, on the hold-outs")
    fig.tight_layout()
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG)
    plt.close(fig)
    print("wrote", OUT_FIG.name)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--gates", action="store_true", help="Stage 1 only: build, gate and label the 60 hold-outs")
    a = p.parse_args()
    if a.gates:
        return gates()
    gate_rows = json.loads(GATES_JSON.read_text())["rows"]
    rows, code_hash = load_rows()
    n = numbers(rows, gate_rows)
    n["mesh_code_hash"] = code_hash
    n["note"] = ("decision 83 (owner, 9 Nov 2026): the hold-outs opened once, the surface rules frozen (82); every "
                 "level, the four Re levels; cells = the wing-block estimate of Study 9")
    OUT_JSON.write_text(json.dumps(n, indent=1))
    print("wrote", OUT_JSON.name)
    figure(n, rows)
    print("gates:", n["gates"]["passed"], "of", n["gates"]["wings"])
    for lev in LEVELS:
        L, R = n["levels"][lev], n["against_study12"][lev]
        print(f"{lev}: passed {L['passed']}/{L['builds']}, crashed {L['crashed']}, nose repairs {L['nose_repairs']}; "
              f"cells median {L['cells']['median'] / 1e6:.2f} M (Study 12 {R['cells_median'] / 1e6:.2f}), largest "
              f"{L['cells']['max'] / 1e6:.2f} M (Study 12 {R['cells_max'] / 1e6:.2f}); nose max {L['nose_turning_max']:.2f}"
              f" (Study 12 {R['nose_turning_max']}); cap min {L['cap_quads_min']:.4f} (Study 12 {R['cap_quads_min']}); "
              f"failed {L['failed']}")
    print(n["family_ratios"])


if __name__ == "__main__":
    main()
