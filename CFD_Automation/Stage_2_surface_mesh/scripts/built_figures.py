"""The pictures of what was finished on 7 Nov 2026, for the Stage 2 page and summary (docs/page/*.png).

    python scripts/built_figures.py      # seconds: reads the study files, builds nothing

nose_fixed.png        Study 4, second correction (decision 64): the nose defect and its fix in Stage 1, from
                      Stage_1_geometry/data/studies/nose_curvature.json, and the nose cell the mesher delivers on the
                      NACA 4415 reference wings before and after (data/studies/similarity_check.json)
similarity_check.png  Study 10 (decision 70): the 20 reference shapes of before similarity at real size against the
                      same shapes at unit mean chord (data/studies/similarity_check.json), and the four Re levels
                      against the real UAVs (Stage_1_geometry/docs/real_uavs.json)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
import matplotlib.ticker
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve()
STAGE2 = HERE.parents[1]
STAGE1 = HERE.parents[2] / "Stage_1_geometry"
OUT = STAGE2 / "docs" / "page"
INK, MUTED, LINE = "#142230", "#566573", "#D6DEE6"
ACC, BWB, WARN, AMBER, VIOLET = "#0C5EA8", "#2E8B57", "#B02A20", "#9A6200", "#6A4BB0"
GREY = "#8C98A4"
TYPES = ("bwb", "flying_wing", "cranked", "tapered")
TYPE_NAME = {"bwb": "BWB", "flying_wing": "flying wing", "cranked": "cranked", "tapered": "tapered"}
COLS = {"bwb": BWB, "flying_wing": AMBER, "cranked": ACC, "tapered": VIOLET}
sys.path.insert(0, str(HERE.parents[2]))           # CFD_Automation: the cfdauto package
from cfdauto.paths import re_levels  # noqa: E402

RE_LEVELS = re_levels()     # Stage 0 values.yaml: 1e5, 3e5, 1e6, 4e6 since 8 Nov 2026 (were 1e5, 3e5, 1.5e6, 3e6)
RE_LAB = {1e5: "10⁵", 3e5: "3 × 10⁵", 1e6: "10⁶", 1.5e6: "1.5 × 10⁶", 3e6: "3 × 10⁶", 4e6: "4 × 10⁶"}
FAM_COL = {"tailless": BWB, "conventional": ACC, "delta": VIOLET}
AIRFOILS = ("naca4415", "e387", "sd7032", "mh104", "mh61", "mh45", "mh60", "s5010", "la2573a", "naca25118")
AF_NAME = {"naca4415": "NACA 4415", "e387": "E387", "sd7032": "SD7032", "mh104": "MH 104", "mh61": "MH 61",
           "mh45": "MH 45", "mh60": "MH 60", "s5010": "S5010", "la2573a": "LA2573A", "naca25118": "NACA 25118"}
plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": LINE, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.titlesize": 10, "axes.titlecolor": INK, "legend.fontsize": 8.5,
                     "figure.dpi": 130, "savefig.dpi": 130, "axes.spines.top": False, "axes.spines.right": False})


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT / name)
    plt.close(fig)
    print("wrote", name)


def _key(r: dict) -> tuple:
    return (r["wing_type"], int(r["index"]), float(r["re_mean"]))


# --- Study 4, second correction: the nose defect was real; fixed in Stage 1 -------------------------------
def fig_nose_fixed() -> None:
    nc = json.loads((STAGE1 / "data" / "studies" / "nose_curvature.json").read_text())
    sim = json.loads((STAGE2 / "data" / "studies" / "similarity_check.json").read_text())
    fig, ax = plt.subplots(1, 4, figsize=(16.5, 4.3), gridspec_kw={"width_ratios": [1.15, 1.0, 1.1, 1.0]})

    # (a) NACA 4415: curvature along the nose arc, true against the two rules
    a = ax[0]
    m = nc["meta"]["profile_sigma_pct"]
    s = np.linspace(m[0], m[1], int(m[2]))
    pk = nc["airfoils"]["naca4415"]["profile_kappa"]
    a.plot(s, pk["raw"], color=INK, lw=2.0, label="true shape (the raw file)")
    a.plot(s, pk["old"], color=WARN, lw=1.3, label="built, old rule")
    a.plot(s, pk["new"], color=ACC, lw=1.3, ls="--", label="built, new rule (7 Nov)")
    a.set_ylim(0, 100)
    a.annotate("spike on the upper side:\n567 / c at the leading edge\n(radius 0.0018 c)", xy=(0.02, 98), xytext=(0.35, 74),
               fontsize=7.8, color=WARN, arrowprops=dict(arrowstyle="->", color=WARN, lw=0.8))
    a.annotate("flat spot on the lower side (6.4 / c),\nthen a bump (77.5 / c at −0.76 % c)", xy=(-0.04, 7), xytext=(-1.97, 88),
               fontsize=7.8, color=WARN, arrowprops=dict(arrowstyle="->", color=WARN, lw=0.8))
    a.set_xlabel("arc length from the leading edge [% c]  (− lower side, + upper side)")
    a.set_ylabel("curvature [1 / c]")
    a.set_title("NACA 4415: the curvature around the nose", fontsize=9.5)
    a.legend(loc="lower left", fontsize=7.5, frameon=False)

    # (b) ten airfoils: the worst error of the turning per cell, old against new rule
    a = ax[1]
    y = np.arange(len(AIRFOILS))[::-1]
    worst = {rule: [max(abs(v) for v in nc["airfoils"][n]["curves"][rule]["T_diff_vs_raw_pct"]) for n in AIRFOILS]
             for rule in ("old", "new")}
    a.axvspan(1e-2, 5, color=BWB, alpha=0.10)
    a.text(0.012, -0.85, "shaded: within 5 %, the test passes", color=BWB, fontsize=7.6, va="center")
    for k, n in enumerate(AIRFOILS):
        a.plot([max(worst["new"][k], 0.02), worst["old"][k]], [y[k], y[k]], color=LINE, lw=1.0, zorder=1)
    a.scatter(worst["old"], y, color=WARN, s=26, zorder=3, label="old rule: fails on all ten")
    a.scatter(np.maximum(worst["new"], 0.02), y, color=ACC, s=26, zorder=3, label="new rule: passes on all ten")
    for k, n in enumerate(AIRFOILS):
        a.text(worst["old"][k] * 1.25, y[k], f"{worst['old'][k]:.0f} %", fontsize=7, color=WARN, va="center")
    a.set_yticks(y, [AF_NAME[n] for n in AIRFOILS], fontsize=8)
    a.set_xscale("log"); a.set_xlim(1e-2, 3e3); a.set_ylim(-2.6, len(AIRFOILS) - 0.4)
    a.set_xlabel("worst error of the turning per cell [%]\n(cells of 0.04–0.50 % c, against the raw file)")
    db = nc["database"]["summary"]
    a.set_title(f"ten airfoils; whole database: {db['pass_old_share_pct']:.1f} % → {db['pass_new_share_pct']:.1f} % pass",
                fontsize=9.5)
    a.legend(loc="lower right", fontsize=7.3, frameon=False, ncol=1, bbox_to_anchor=(1.0, -0.02))

    # (c) the Stage 2 nose solve on a NACA 4415 station: old against new section
    a = ax[2]
    ln = nc["stage2_nose_line"]
    h = np.array(ln["h_le_pct"])
    for rule, col, lab in (("old", WARN, "old section"), ("new", ACC, "new section")):
        t = np.array(ln[rule]["turning_deg"])
        hm = ln[rule]["largest_h_le_pct_meeting_10deg"]
        a.semilogx(h, t, ".-", color=col, lw=1.1, ms=3.5, label=f"{lab}: 10° met up to {hm:.3f} % c")
        a.axvline(hm, color=col, lw=0.8, ls=":")
    a.axhline(10, color=MUTED, lw=1, ls="--")
    a.text(0.0022, 10.15, "target 10° (first rules, level C)", color=MUTED, fontsize=7.6)
    a.text(0.0022, 5.15, "flat at about 6–7° on both: the worst node sits 1.8–2.4 % c\ndown the lower side, where growth 1.2 sets the cells",
           color=MUTED, fontsize=7.4)
    a.set_ylim(5, 12.5)
    a.set_xlabel("nose spacing [% c]"); a.set_ylabel("largest turning per ring node [°]")
    a.set_title("the nose solve on a NACA 4415 station\n(tapered training wing 35, station 21)", fontsize=9.5)
    a.legend(loc="upper left", fontsize=7.3, frameon=False, bbox_to_anchor=(0.0, 0.93))

    # (d) the nose cell the mesher delivers on the 20 reference shapes, before and after the fix
    a = ax[3]
    before = {_key(r): r for r in sim["similarity_only"]["rows"]}
    after = {_key(r): r for r in sim["similarity_and_nose"]["rows"]}
    for t in TYPES:
        ks = [k for k in before if k[0] == t and k in after]
        a.scatter([100 * before[k]["nose_h_le_c"][0] for k in ks], [100 * after[k]["nose_h_le_c"][0] for k in ks],
                  s=22, color=COLS[t], label=f"{TYPE_NAME[t]} (5 wings × 4 Re)", zorder=3, alpha=0.85)
    lim = [0.02, 0.5]
    a.plot(lim, lim, color=MUTED, lw=0.8, ls="--")
    a.text(0.022, 0.026, "the same as before", color=MUTED, fontsize=7.4, rotation=38)
    conv = [k for k in before if k[0] in ("cranked", "tapered") and k in after]
    rb = [100 * before[k]["nose_h_le_c"][0] for k in conv]; ra = [100 * after[k]["nose_h_le_c"][0] for k in conv]
    a.text(0.03, 0.33, f"NACA 4415 / 4412 wings:\n{min(rb):.3f} → {min(ra):.3f}–{max(ra):.3f} % c", color=INK, fontsize=7.6)
    a.set_xscale("log"); a.set_yscale("log"); a.set_xlim(lim); a.set_ylim(lim)
    tk = [0.02, 0.05, 0.1, 0.2, 0.5]
    for axis in (a.xaxis, a.yaxis):
        axis.set_major_locator(matplotlib.ticker.FixedLocator(tk))
        axis.set_major_formatter(matplotlib.ticker.FixedFormatter([f"{v:g}" for v in tk]))
        axis.set_minor_locator(matplotlib.ticker.NullLocator())
    a.set_xlabel("nose cell, old section [% c]"); a.set_ylabel("nose cell, new section [% c]")
    a.set_title("the nose cell delivered at level C (first rules),\nthe same 20 shapes, old against new section", fontsize=9.5)
    a.legend(loc="lower right", fontsize=7.0, frameon=False)
    save(fig, "nose_fixed.png")


# --- Study 10: the similarity check ----------------------------------------------------------------------
def fig_similarity() -> None:
    sim = json.loads((STAGE2 / "data" / "studies" / "similarity_check.json").read_text())
    old = {_key(r): r for r in sim["old"]["rows"]}
    new = {_key(r): r for r in sim["similarity_only"]["rows"]}
    both = {_key(r): r for r in sim["similarity_and_nose"]["rows"]}
    ks = [k for k in old if k in new]
    fig, ax = plt.subplots(1, 4, figsize=(16.5, 4.2), gridspec_kw={"width_ratios": [1, 1, 1, 1.25]})

    for a, key, label in ((ax[0], "n_ring", "ring nodes"), (ax[1], "n_span", "stations")):
        for t in TYPES:
            kk = [k for k in ks if k[0] == t]
            a.scatter([old[k][key] for k in kk], [new[k][key] for k in kk], s=18, color=COLS[t], label=TYPE_NAME[t], zorder=3)
        v = [old[k][key] for k in ks] + [new[k][key] for k in ks]
        lo, hi = min(v) * 0.9, max(v) * 1.05
        a.plot([lo, hi], [lo, hi], color=MUTED, lw=0.8, ls="--")
        a.set_xlim(lo, hi); a.set_ylim(lo, hi)
        a.set_xlabel(f"{label}, real size (first screen)"); a.set_ylabel(f"{label}, unit mean chord")
    same = sum(old[k]["n_ring"] == new[k]["n_ring"] for k in ks)
    ax[0].set_title(f"ring nodes: the same on {same} of {len(ks)} meshes", fontsize=9.5)
    ax[0].legend(loc="upper left", fontsize=7.5, frameon=False)
    drop = [old[k]["n_span"] - new[k]["n_span"] for k in ks]
    sw = [k for k in ks if old[k]["n_panels"] > new[k]["n_panels"]]
    wings_sw = sorted({k[:2] for k in sw})
    dd = [old[k]["n_span"] - new[k]["n_span"] for k in sw]
    ax[1].set_title(f"stations: {len(wings_sw)} wings lost their switch section\n(−{min(dd)} to −{max(dd)} stations there)" if sw
                    else "stations", fontsize=9.5)
    for k in sw:
        ax[1].annotate("", xy=(old[k]["n_span"], new[k]["n_span"]), xytext=(old[k]["n_span"], old[k]["n_span"]),
                       arrowprops=dict(arrowstyle="->", color=WARN, lw=0.6, alpha=0.6))

    a = ax[2]
    for t in TYPES:
        kk = [k for k in ks if k[0] == t]
        a.scatter([old[k]["cap_quads_J"] for k in kk], [new[k]["cap_quads_J"] for k in kk], s=18, color=COLS[t], zorder=3)
    a.plot([0, 0.6], [0, 0.6], color=MUTED, lw=0.8, ls="--")
    a.axhline(0.05, color=WARN, lw=1, ls="--"); a.text(0.01, 0.058, "refusal limit 0.05", color=WARN, fontsize=7.5)
    a.set_xlim(0, 0.6); a.set_ylim(0, 0.6)
    a.set_xlabel("cap quads, smallest scaled Jacobian, real size"); a.set_ylabel("the same, unit mean chord")
    fall = [k for k in ks if new[k]["cap_quads_J"] < old[k]["cap_quads_J"] - 0.01]
    big = max(fall, key=lambda k: old[k]["cap_quads_J"] - new[k]["cap_quads_J"]) if fall else None
    a.set_title(f"cap quality falls on {len(fall)} of {len(ks)} (most: {old[big]['cap_quads_J']:.3f} → {new[big]['cap_quads_J']:.3f});\n"
                f"lowest {min(old[k]['cap_quads_J'] for k in ks):.3f} → {min(new[k]['cap_quads_J'] for k in ks):.3f}, "
                "against the refusal limit 0.05", fontsize=9.5)

    a = ax[3]
    uav = json.loads((STAGE1 / "docs" / "real_uavs.json").read_text())["rows"]
    rr = sorted([r for r in uav if r.get("re_low") and r.get("re_high") and r.get("use") == "ranges"], key=lambda r: r["re_low"])
    for i, r in enumerate(rr):
        a.plot([r["re_low"], r["re_high"]], [i, i], color=FAM_COL.get(r["family"], GREY), lw=2.2, solid_capstyle="butt")
    gk = json.loads((STAGE1 / "docs" / "greek_uavs.json").read_text())["rows"]      # 8 Nov 2026: estimates (AR 8 assumed)
    gk = sorted(gk, key=lambda r: r["re_cruise_3048m"])
    for k, r in enumerate(gk):
        y = len(rr) + 1.2 + k
        a.plot([r["re_cruise_3048m"], max(r["re_top_sea_level"])], [y, y], color=BWB if r["family"] == "tailless" else ACC,
               lw=2.2, ls=(0, (3, 1.5)), solid_capstyle="butt")
        a.text(r["re_cruise_3048m"] / 1.08, y, r["name"], fontsize=6.6, color=MUTED, ha="right", va="center")
    top_y = len(rr) + 1.2 + len(gk)
    for re in RE_LEVELS:
        a.axvline(re, color=AMBER, lw=1.2, ls="--")
    a.text(1.0e5 * 0.97, top_y + 0.4, "10⁵", color=AMBER, fontsize=8, ha="right")
    for re in RE_LEVELS[1:]:
        a.text(re * 1.04, top_y + 0.4, RE_LAB.get(re, f"{re:.2g}"), color=AMBER, fontsize=8)
    lo = rr[0]["re_low"]
    a.annotate(f"slowest real UAV: {lo / 1e5:.2f} × 10⁵\n(10⁵ is {100 * (1 - 1e5 / lo):.0f} % below it: a margin)",
               xy=(lo, 0), xytext=(1.06e5, 0.78 * len(rr)), fontsize=7.6, color=INK,
               arrowprops=dict(arrowstyle="->", color=MUTED, lw=0.8))
    a.set_xscale("log"); a.set_xlim(6e4, 8e6); a.set_ylim(-1, top_y + 1.6)
    a.set_yticks([]); a.set_xlabel("Re on the mean chord (area / full span), cruise to top speed")
    for fam, col in FAM_COL.items():
        if any(r["family"] == fam for r in rr):
            a.plot([], [], color=col, lw=2.2, label=f"{fam} ({sum(r['family'] == fam for r in rr)})")
    a.set_title(f"Re levels (8 Nov) against {len(rr)} real UAVs ({rr[0]['re_low'] / 1e5:.2f} × 10⁵ – "
                f"{max(r['re_high'] for r in rr) / 1e6:.2f} × 10⁶)\nand the Greek tactical UAVs (dashed bars, AR 8 assumed)", fontsize=9.5)
    a.legend(loc="lower right", fontsize=7.5, frameon=False)
    save(fig, "similarity_check.png")


def main() -> None:
    which = sys.argv[1:] or ["nose", "similarity"]
    if "nose" in which:
        fig_nose_fixed()
    if "similarity" in which:
        fig_similarity()


if __name__ == "__main__":
    main()
