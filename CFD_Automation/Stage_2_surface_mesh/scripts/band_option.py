"""Study 13: the transition band option (owner, 9 Nov 2026). What the band costs, per level and Re level.

    python scripts/screen.py --family --sets reference --band off --types bwb cranked          # one process
    python scripts/screen.py --family --sets reference --band off --types flying_wing tapered  # the other
    python scripts/band_option.py

The band on: the family screen (Study 12, data/studies/screen_family_<level>.json, the 20 reference wings at the
four Re levels). The band off: the same wings, Re and levels built with --band off (data/meshes/screen_family/
<types>_noband_<level>.json). Both are one nose factor per family. Writes data/studies/band_option.json and
docs/page/band_option.png. The cells are the estimate of the wing blocks (Study 9): no C-H wake lines, no outer
field past 2 chords, no outboard blocks.
"""

from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve()
STAGE2 = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
from screen_study import (ACC, AMBER, DESKTOP, DESKTOP_36, INK, LCOL, LEVELS, LINE, MUTED, RE_LEVELS,  # noqa: E402
                          RE_NAME, TYPE_NAME, TYPES, WARN)

STUDIES = STAGE2 / "data" / "studies"
FAMILY = STAGE2 / "data" / "meshes" / "screen_family"
OFF_TAGS = ("bwb_cranked_noband", "flying_wing_tapered_noband")
OUT_JSON = STUDIES / "band_option.json"
OUT_FIG = STAGE2 / "docs" / "page" / "band_option.png"


def key(r: dict) -> tuple:
    return r["wing_type"], int(r["index"]), float(r["re_mean"])


def load() -> tuple[dict, dict, list]:
    on, off, heads = {}, {}, []
    for lev in LEVELS:
        d = json.loads((STUDIES / f"screen_family_{lev}.json").read_text())
        on[lev] = {key(r): r for r in d["rows"] if r["set"] == "reference" and r.get("built")}
        off[lev] = {}
        for tag in OFF_TAGS:
            f = FAMILY / f"{tag}_{lev}.json"
            if not f.exists():
                raise SystemExit(f"missing {f.name}: run scripts/screen.py --family --sets reference --band off first")
            p = json.loads(f.read_text())
            assert p["rules"]["transition_band"] is False, f.name
            heads.append({"part": f.name, "mesh_code_hash": p["mesh_code_hash"], "builds": len(p["rows"])})
            off[lev] |= {key(r): r for r in p["rows"]}
    return on, off, heads


def numbers(on: dict, off: dict) -> dict:
    out = {"levels": {}, "by_type_F": {}, "checks": {}}
    for lev in LEVELS:
        ks = sorted(set(on[lev]) & set(off[lev]))
        passed = sum(off[lev][k]["passed"] for k in ks)
        rep = sum((off[lev][k].get("nose_family") or {}).get("rounds", 0) > 0 for k in ks)
        per_re = {}
        for re in RE_LEVELS:
            kr = [k for k in ks if k[2] == re]
            c_on = [on[lev][k]["cells_est"] for k in kr]
            c_off = [off[lev][k]["cells_est"] for k in kr]
            ratio = [a / b for a, b in zip(c_on, c_off)]
            per_re[f"{re:.0e}"] = {
                "wings": len(kr),
                "cells_on": {"median": st.median(c_on), "max": max(c_on)},
                "cells_off": {"median": st.median(c_off), "max": max(c_off)},
                "ratio": {"median": st.median(ratio), "min": min(ratio), "max": max(ratio)},
                "ring_on": st.median(on[lev][k]["n_ring"] for k in kr),
                "ring_off": st.median(off[lev][k]["n_ring"] for k in kr),
                "same_stations": sum(on[lev][k]["n_span"] == off[lev][k]["n_span"] for k in kr),
            }
        c_off_all = [off[lev][k]["cells_est"] for k in ks]
        fails = [{"wing": f"{TYPE_NAME[k[0]]} reference {k[1]}", "re": k[2], "failed": off[lev][k].get("failed"),
                  "cap_quads": off[lev][k]["checks"]["cap_quads"]["value"],
                  "cap_quads_on": on[lev][k]["checks"]["cap_quads"]["value"]}
                 for k in ks if not off[lev][k]["passed"]]
        caps_off = [off[lev][k]["checks"]["cap_quads"]["value"] for k in ks]
        caps_on = [on[lev][k]["checks"]["cap_quads"]["value"] for k in ks]
        out["levels"][lev] = {"builds": len(ks), "passed_off": passed, "families_repaired_off": rep, "failed_off": fails,
                              "cap_quads_min_off": min(caps_off), "cap_quads_min_on": min(caps_on),
                              "per_re": per_re, "largest_off": max(c_off_all),
                              "largest_on": max(on[lev][k]["cells_est"] for k in ks),
                              "fits_desktop_off": sum(c <= DESKTOP for c in c_off_all),
                              "fits_desktop_on": sum(on[lev][k]["cells_est"] <= DESKTOP for k in ks),
                              "fits_desktop_36_off": sum(c <= DESKTOP_36 for c in c_off_all),
                              "fits_desktop_36_on": sum(on[lev][k]["cells_est"] <= DESKTOP_36 for k in ks)}
    ks = sorted(set(on["F"]) & set(off["F"]))
    for t in TYPES:
        r = [on["F"][k]["cells_est"] / off["F"][k]["cells_est"] for k in ks if k[0] == t and k[2] != RE_LEVELS[0]]
        out["by_type_F"][t] = {"ratio_median_above_lowest_re": st.median(r)}
    # the family rule with the band off: the asked nose spacing x 1.3 per level step at the root of every wing
    ratios = []
    for a, b in zip(LEVELS[:-1], LEVELS[1:]):
        for k in ks:
            ra, rb = off[a][k], off[b][k]
            if ra.get("spacings") and rb.get("spacings") and ra["spacings"].get("nose_root") and rb["spacings"].get("nose_root"):
                ratios.append(ra["spacings"]["nose_root"] / rb["spacings"]["nose_root"])
    out["checks"]["nose_root_delivered_ratio"] = {"min": min(ratios), "max": max(ratios)} if ratios else None
    return out


def figure(n: dict) -> None:
    fig, ax = plt.subplots(1, 2, figsize=(12.4, 4.6), gridspec_kw={"width_ratios": [1.15, 1]})
    a = ax[0]
    xs = np.arange(len(RE_LEVELS))
    f = n["levels"]["F"]["per_re"]
    for off_, (lab, col, sh) in enumerate((("band on", ACC, -0.19), ("band off", AMBER, 0.19))):
        kk = "cells_on" if lab == "band on" else "cells_off"
        med = [f[f"{re:.0e}"][kk]["median"] / 1e6 for re in RE_LEVELS]
        mx = [f[f"{re:.0e}"][kk]["max"] / 1e6 for re in RE_LEVELS]
        a.bar(xs + sh, med, 0.36, color=col, alpha=0.85, label=f"{lab}: median (bar), largest (tick)")
        a.errorbar(xs + sh, med, yerr=[np.zeros(len(med)), np.array(mx) - np.array(med)], fmt="none", ecolor=INK,
                   capsize=4, lw=1)
        for x, m_, M in zip(xs + sh, med, mx):
            a.text(x, M + 0.25, f"{m_:.2f}\n({M:.2f})", ha="center", va="bottom", fontsize=7.4,
                   bbox=dict(facecolor="white", edgecolor="none", pad=0.4, alpha=0.9))
    a.axhline(DESKTOP_36 / 1e6, color=AMBER, ls="--", lw=1, label="desktop + 36 GB: ≈ 5.0 M cells")
    a.set_xticks(xs, [f"Re {RE_NAME[re]}" for re in RE_LEVELS])
    a.set_ylabel("cells per mesh at F [millions] (wing blocks)")
    a.set_ylim(0, 13.5)
    a.grid(axis="y", color=LINE, lw=0.5)
    a.legend(loc="upper left", frameon=False)
    a.set_title("F, 20 reference wings: the band on (transition runs) and off (fully turbulent runs)")
    a = ax[1]
    for lev in LEVELS:
        pr = n["levels"][lev]["per_re"]
        med = [pr[f"{re:.0e}"]["ratio"]["median"] for re in RE_LEVELS]
        lo = [pr[f"{re:.0e}"]["ratio"]["min"] for re in RE_LEVELS]
        hi = [pr[f"{re:.0e}"]["ratio"]["max"] for re in RE_LEVELS]
        a.plot(xs, med, "-o", color=LCOL[lev], lw=2, ms=5, label=lev)
        a.fill_between(xs, lo, hi, color=LCOL[lev], alpha=0.10, lw=0)
    a.axhline(1.0, color=MUTED, lw=0.8)
    a.set_xticks(xs, [f"Re {RE_NAME[re]}" for re in RE_LEVELS])
    a.set_ylabel("cells with the band ÷ cells without")
    a.set_ylim(0.9, 2.15)
    a.grid(axis="y", color=LINE, lw=0.5)
    a.legend(title="level: median (line), range (shade)", loc="lower right", frameon=False, ncol=4)
    a.set_title("what the band costs, every level (20 reference wings)")
    fig.tight_layout()
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG)
    plt.close(fig)
    print("wrote", OUT_FIG.name)


def main() -> None:
    on, off, heads = load()
    n = numbers(on, off)
    n["parts_off"] = heads
    n["note"] = ("cells: the wing-block estimate of Study 9 (no C-H wake lines, no outer field past 2 chords, "
                 "no outboard blocks); band on = Study 12, band off = --band off, the same wings, Re and levels")
    OUT_JSON.write_text(json.dumps(n, indent=1))
    print("wrote", OUT_JSON.name)
    figure(n)
    for lev in LEVELS:
        L = n["levels"][lev]
        print(lev, f"cap min off {L['cap_quads_min_off']:.4f} (on {L['cap_quads_min_on']:.4f}); fails",
              [(x['wing'], x['re'], x['failed'], round(x['cap_quads'], 4)) for x in L['failed_off']])
        print(lev, f"passed off {L['passed_off']}/{L['builds']}, repaired {L['families_repaired_off']}; ratio by Re "
              + ", ".join(f"{re}: {v['ratio']['median']:.2f} ({v['ratio']['min']:.2f}-{v['ratio']['max']:.2f})"
                          for re, v in L["per_re"].items())
              + f"; largest off {L['largest_off'] / 1e6:.2f} M (on {L['largest_on'] / 1e6:.2f}); desktop off "
                f"{L['fits_desktop_off']} (on {L['fits_desktop_on']}), +36 GB off {L['fits_desktop_36_off']} "
                f"(on {L['fits_desktop_36_on']})")
    print({TYPE_NAME[t]: round(v["ratio_median_above_lowest_re"], 2) for t, v in n["by_type_F"].items()},
          n["checks"])


if __name__ == "__main__":
    main()
