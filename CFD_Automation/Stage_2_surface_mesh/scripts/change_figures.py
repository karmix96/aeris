"""The pictures of the 'what was first, what changes' section of the Stage 2 page (6 Nov 2026, updated 7 Nov).

    python scripts/change_figures.py        # docs/page/levels_first_new.png, topology_first_new.png,
                                            # cost_first_new.png, band_negative.png (seconds)

levels_first_new.png reads the values of both approaches from the code (cfdauto/mesh/laws.py with
configs/surface_first.yaml and configs/surface.yaml: the new rules, built on 7 Nov) and, once the new screen has run,
the turning each level delivered (data/studies/screen_new_summary.json). cost_first_new.png keeps the estimate of
6 Nov (Stage 0 decisions, the status report; not recomputed here); the measured cells are Study 9
(scripts/screen_study.py). The band count in band_negative.png is Study 8 (7 Nov, scripts/band_count.py); option A
was decided and built on 7 Nov.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from cfdauto.mesh.laws import rules  # noqa: E402

STAGE2 = Path(__file__).resolve().parents[1]
FIRST = STAGE2 / "configs" / "surface_first.yaml"
OUT = STAGE2 / "docs" / "page"
INK, MUTED, LINE = "#142230", "#566573", "#D6DEE6"
ACC, BWB, WARN, AMBER, VIOLET = "#0C5EA8", "#2E8B57", "#B02A20", "#9A6200", "#6A4BB0"
GREY = "#8C98A4"
plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": LINE, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.titlesize": 10, "axes.titlecolor": INK, "legend.fontsize": 8.5,
                     "figure.dpi": 130, "savefig.dpi": 130, "axes.spines.top": False, "axes.spines.right": False})
R = 1.3                                    # family ratio
LEVELS = ["1st\nfirst: C\nnew: VC", "2nd\nfirst: M\nnew: C", "3rd\nfirst: F\nnew: M", "4th\nfirst: FF\nnew: F"]


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT / name)
    plt.close(fig)
    print("wrote", name)


def ladder(value_at_anchor: float, anchor: int, power: float = 1.0) -> np.ndarray:
    """Value at levels 0..3 when the value is set at level `anchor` and every spacing is ÷ r per level."""
    k = np.arange(4)
    return value_at_anchor * R ** (power * (anchor - k))


def naca4(m=0.04, p=0.4, t=0.15, n=200, te=0.004):
    """A NACA 4-digit section with a small blunt base (te = base thickness / c), for the sketches only."""
    b = 0.5 * (1 - np.cos(np.linspace(0, np.pi, n)))
    yt = 5 * t * (0.2969 * np.sqrt(b) - 0.1260 * b - 0.3516 * b ** 2 + 0.2843 * b ** 3 - 0.1015 * b ** 4)
    yt += 0.5 * te * b
    yc = np.where(b < p, m / p ** 2 * (2 * p * b - b ** 2), m / (1 - p) ** 2 * ((1 - 2 * p) + 2 * p * b - b ** 2))
    dy = np.where(b < p, 2 * m / p ** 2 * (p - b), 2 * m / (1 - p) ** 2 * (p - b))
    th = np.arctan(dy)
    up = np.column_stack([b - yt * np.sin(th), yc + yt * np.cos(th)])
    lo = np.column_stack([b + yt * np.sin(th), yc - yt * np.cos(th)])
    return up, lo


# --- 1. where each rule sits on the ladder, first against new (values from the code) ---------------------
def fig_levels():
    first = [rules(lev, FIRST) for lev in ("C", "M", "F", "FF")]
    new = [rules(lev) for lev in ("VC", "C", "M", "F")]
    summ = STAGE2 / "data" / "studies" / "screen_new_summary.json"
    delivered = None
    if summ.exists():                             # the largest turning each level delivered in the new screen
        s = json.loads(summ.read_text())
        src = {"VC": s["full"].get("VC"), "C": s["reference"].get("C"), "M": s["reference"].get("M"), "F": s["full"].get("F")}
        if all(src.values()):
            delivered = [(src[lev]["nose_turning"]["min"], src[lev]["nose_turning"]["max"]) for lev in ("VC", "C", "M", "F")]
    fig, ax = plt.subplots(2, 3, figsize=(13, 6.8))
    x = np.arange(4)
    g = lambda rs, f: np.array([f(r) for r in rs])
    panels = [
        ("Nose: turning per cell [°]", ladder(10, 0), g(new, lambda r: r.nose_turning_deg), 10, "target 10° (law 1)",
         "first: met at C · new: met at M (accuracy target, as DPW sets its medium grid);\neach level checked against its own angle + 0.2°"),
        ("Band: cells across a bubble", g(first, lambda r: r.cells_per_bubble), g(new, lambda r: r.cells_per_bubble), 20,
         "target 20 (Ansys CFX guide)", "first: met at C · new: met at F (transition target)"),
        ("Station gap / local chord", g(first, lambda r: r.span_spacing_c), g(new, lambda r: r.span_spacing_c), None, None,
         "first: 0.2 c at C · new: 0.25 c at M (lighter rule);\nat least " + ", ".join(str(r.min_cells_per_panel) for r in new)
         + " gaps per panel at VC, C, M, F"),
        ("Trailing-edge cell [% c]", g(first, lambda r: 100 * r.te_spacing_c), g(new, lambda r: 100 * r.te_spacing_c), 0.1,
         "target 0.1 % c (DPW)", "first: met at C · new: met at M"),
        ("Growth limits", g(first, lambda r: r.chord_growth_limit), g(new, lambda r: r.chord_growth_limit), 1.1,
         "1.1 asked with a transition model", "checked growth, solid: along the ring; dotted: between station gaps. New: 1.25 at VC to " +
         f"{new[3].chord_growth_limit:.3f} at F,\nthe same as the wall growth planned for Stage 3, just above 1.1 (1.23 at VC would give exactly 1.1);\n"
         "first: 1.25 and 1.3 at every level"),
    ]
    for a, (title, fv, nv, target, tlabel, note) in zip(ax.flat, panels):
        a.plot(x, fv, "-o", color=GREY, lw=1.6, ms=5, label="first (built 2–3 Nov)")
        a.plot(x, nv, "-o", color=ACC, lw=2.0, ms=5, label="new (built 7 Nov; from laws.py)")
        for xi, v in zip(x, nv):
            a.annotate(f"{v:.3g}", (xi, v), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=7.4, color=ACC)
        if target is not None:
            a.axhline(target, color=AMBER, ls="--", lw=1.0)
            xl = {"Nose: turning per cell [°]": 2.2, "Band: cells across a bubble": 1.45,
                  "Trailing-edge cell [% c]": 0.5, "Growth limits": 0.45}.get(title, 1.0)
            a.text(xl, target, tlabel, color=AMBER, fontsize=7.5, va="bottom", ha="left")
        a.set_xticks(x, LEVELS, fontsize=7.5)
        a.set_title(title)
        a.text(0.0, -0.47, note, transform=a.transAxes, fontsize=7.6, color=MUTED, va="top")
        a.grid(axis="y", color=LINE, lw=0.5)
    a = ax[1, 1]
    a.plot(x, g(first, lambda r: r.span_growth_limit), ":o", color=GREY, lw=1.2, ms=3)
    a.plot(x, g(new, lambda r: r.span_growth_limit), ":o", color=ACC, lw=1.2, ms=3)
    a.set_ylim(1.08, 1.33)
    ax[0, 2].plot([0], [first[0].span_spacing_c], marker="*", color=GREY, ms=13)
    ax[0, 2].plot([2], [new[2].span_spacing_c], marker="*", color=ACC, ms=13)
    if delivered:
        a = ax[0, 0]
        for xi, (lo, hi) in zip(x, delivered):
            a.plot([xi + 0.12, xi + 0.12], [lo, hi], color=BWB, lw=4, solid_capstyle="butt", alpha=0.8)
        a.plot([], [], color=BWB, lw=4, label="delivered, new screen (7 Nov)")
    a = ax[1, 2]
    a.axis("off")
    h, lab = ax[0, 0].get_legend_handles_labels()
    a.legend(h, lab, loc="upper left", bbox_to_anchor=(-0.02, 1.16), frameon=False, fontsize=8)
    lines = ["Built 7 Nov (configs/surface.yaml, laws.py):",
             "hard minimums at VC, the same as before:",
             "  · y⁺ ≤ 1 at the wall (" + ", ".join(f"{r.yplus:.2f}" for r in new[1:]) + " at C, M, F)",
             "  · growth ≤ 1.25 along the ring and off the wall",
             f"  · base ≥ 8 cells ({', '.join(str(r.base_cells) for r in new)})",
             "  · no kinks; every check refuses as before",
             f"  · tip gap {new[0].tip_gap_in_s0:g} × s0 (was s0: lighter rule)",
             "Decided 7 Nov: the nose solved at every level,",
             "  · each for its own angle; the strictest wins",
             "Two builder choices (stricter), for Mike:",
             "  · the growth limits follow the family rule",
             "  · station growth 1.2 kept (plan file: 1.25, 7 gaps)"]
    for i, s_ in enumerate(lines):
        a.text(0.0, 0.74 - i * 0.075, s_, fontsize=8.2, color=INK if i in (0, 1, 7, 9) else MUTED, va="top",
               transform=a.transAxes, fontweight="bold" if i in (0, 7, 9) else None)
    save(fig, "levels_first_new.png")


# --- 2. the volume topology, first against new ----------------------------------------------
def fig_topology():
    up, lo = naca4()
    ring = np.vstack([up[::-1], lo[1:]])            # TE upper -> nose -> TE lower
    fig, ax = plt.subplots(1, 3, figsize=(14, 4.9), gridspec_kw={"width_ratios": [1, 1, 1.05]})

    def offsets(curve, ds):
        t = np.gradient(curve, axis=0)
        nrm = np.column_stack([t[:, 1], -t[:, 0]]); nrm /= np.linalg.norm(nrm, axis=1)[:, None]
        return [curve + d * nrm for d in ds]

    # (a) first: O rings around the closed section + the overset wake box
    a = ax[0]
    closed = np.vstack([ring, ring[:1]])
    centre = np.array([0.5, 0.0])
    ang = np.arctan2(closed[:, 1] - centre[1], closed[:, 0] - centre[0])
    n_l = 11
    for k in range(n_l):                                   # rings blended from the section to circles along rays
        w = ((k + 1) / n_l) ** 1.6
        rad = 0.55 + 1.6 * w
        circ = centre + rad * np.column_stack([np.cos(ang), np.sin(ang)])
        L = (1 - w) * closed + w * circ
        a.plot(L[:, 0], L[:, 1], color=MUTED, lw=0.45)
    for k in range(0, len(closed) - 1, 16):                # lines off the wall
        rr = [(1 - ((j + 1) / n_l) ** 1.6) * closed[k] + ((j + 1) / n_l) ** 1.6 * (centre + (0.55 + 1.6 * ((j + 1) / n_l) ** 1.6) * np.array([np.cos(ang[k]), np.sin(ang[k])])) for j in range(n_l)]
        rr = np.vstack([closed[k], rr])
        a.plot(rr[:, 0], rr[:, 1], color=LINE, lw=0.5)
    a.plot(closed[:, 0], closed[:, 1], color=INK, lw=1.4)
    a.add_patch(plt.Rectangle((0.98, -0.42), 2.2, 0.84, fill=False, ls="--", color=AMBER, lw=1.3))
    a.text(1.05, -0.62, "overset wake box: a mesh of its own,\noverlapping the O mesh", color=AMBER, fontsize=8,
           va="top", bbox=dict(fc="white", ec="none", pad=1.5))
    a.set_xlim(-1.8, 3.3); a.set_ylim(-2.35, 2.45); a.set_aspect("equal"); a.axis("off")
    a.set_title("first: O rings around the section (S8);\nthe wake carried by overset boxes (ADflow only)", fontsize=9.5)

    # (b) new: C-H, the C rows wrap the nose and leave the trailing edge; H blocks behind
    a = ax[1]
    ds = np.geomspace(0.008, 1.6, 11)
    xw = np.linspace(1.0, 3.2, 12)
    tops, bots = [], []
    for d, L in zip(ds, offsets(ring, ds)):
        far = L.copy()
        front = L[:, 0] < 0.5
        angf = np.arctan2(L[front, 1], L[front, 0] - 0.5)
        far[front] = np.column_stack([0.5 + (0.55 + d) * np.cos(angf), (0.55 + d) * np.sin(angf)])
        far[~front, 1] = np.sign(L[~front, 1] + 1e-9) * (0.55 + d)
        wgt = np.clip((d - 0.06) / 0.9, 0, 1)
        C = (1 - wgt) * L + wgt * far
        yt, yb = C[0, 1], C[-1, 1]
        a.plot(np.concatenate([[3.2], C[:, 0], [3.2]]), np.concatenate([[yt], C[:, 1], [yb]]), color=MUTED, lw=0.45)
        tops.append(yt); bots.append(yb)
    for k in range(0, len(ring), 14):                       # normal lines from the ring
        pts = [ring[k]] + [offsets(ring, [d])[0][k] for d in ds[:4]]
        pts = np.array(pts)
        a.plot(pts[:, 0], pts[:, 1], color=LINE, lw=0.5)
    for xx in xw:                                           # H lines across the wake
        a.plot([xx, xx], [bots[-1], tops[-1]], color=LINE, lw=0.5)
    te_mid = 0.5 * (ring[0] + ring[-1])
    a.plot([te_mid[0], 3.2], [te_mid[1], te_mid[1]], color=WARN, lw=1.1, ls=(0, (4, 2)))
    a.plot(ring[:, 0], ring[:, 1], color=INK, lw=1.4)
    a.text(1.3, -0.16, "wake lines from the trailing edge\nto the far field (80 c)", color=WARN, fontsize=8, va="top",
           bbox=dict(fc="white", ec="none", pad=1.5))
    a.text(-1.75, -2.3, "nose kept inside the C block's ring direction:\nno nose collar (S6's 5-point collar was the defect)", fontsize=7.8, color=MUTED,
           bbox=dict(fc="white", ec="none", pad=1.5))
    a.set_xlim(-1.8, 3.3); a.set_ylim(-2.35, 2.45); a.set_aspect("equal"); a.axis("off")
    a.set_title("new: one matched C-H mesh for ADflow and SU2;\nthe ring (Stage 2) is still the first row", fontsize=9.5)

    # (c) new, top view: the stations go on past the tip (outboard blocks) and behind the wing (wake)
    a = ax[2]
    s, c0, ct, sweep = 3.0, 1.0, 0.45, 0.6
    yy = np.concatenate([np.linspace(0, s, 22)[:-1], s - np.geomspace(0.25, 0.003, 9)[::-1] * 0 + np.linspace(s - 0.2, s, 9)])
    yy = np.unique(np.clip(yy, 0, s))
    le = sweep * yy / s; te = le + c0 + (ct - c0) * yy / s
    a.fill(np.concatenate([le, te[::-1]]), np.concatenate([yy, yy[::-1]]), color=LINE, alpha=0.7)
    for j in range(0, len(yy), 2):
        a.plot([le[j], te[j]], [yy[j], yy[j]], color=MUTED, lw=0.4)
        a.plot([te[j], 4.6], [yy[j], yy[j]], color=LINE, lw=0.6)          # station lines go on behind the wing
    yo = s + np.cumsum(0.02 * 1.35 ** np.arange(12))                       # outboard blocks: gaps grow from the tip gap
    for y in yo[yo < 4.3]:
        a.plot([le[-1] - 0.6, 4.6], [y, y], color=VIOLET, lw=0.5, alpha=0.8)
    a.plot(le, yy, color=INK, lw=1.1); a.plot(te, yy, color=INK, lw=1.1)
    a.plot([te[-1], 4.6], [s - 0.02, s + 0.05], color=WARN, lw=1.6, ls=":")
    a.text(te[-1] + 0.25, s + 0.12, "tip-vortex path: cells clustered along it\nin the outboard blocks (no tube)", color=WARN, fontsize=7.8,
           bbox=dict(fc="white", ec="none", pad=1.5))
    a.text(le[-1] - 0.55, 4.12, "outboard H blocks: the stations go on past the tip,\ngrowing from the tip gap", color=VIOLET, fontsize=7.8,
           bbox=dict(fc="white", ec="none", pad=1.5))
    a.text(2.0, 0.55, "wake: the station lines\ncarry on behind the wing", color=MUTED, fontsize=7.8, bbox=dict(fc="white", ec="none", pad=1.5))
    a.annotate("", xy=(4.4, -0.05), xytext=(3.4, -0.05), arrowprops=dict(arrowstyle="->", color=MUTED, lw=1))
    a.text(3.4, -0.02, "flow", color=MUTED, fontsize=7.5, va="bottom")
    a.set_xlim(-0.4, 4.7); a.set_ylim(-0.1, 4.5); a.set_aspect("equal"); a.axis("off")
    a.set_title("new, top view of a half wing (schematic)")
    save(fig, "topology_first_new.png")


# --- 3. the cost, first plan against new rules ----------------------------------------------
def fig_cost():
    fig, ax = plt.subplots(1, 2, figsize=(12.5, 4.2), gridspec_kw={"width_ratios": [1, 1.15]})
    a = ax[0]
    lv = ["VC", "C", "M", "F"]
    med = np.array([1.0, 2.3, 5.0, 10.9]); mx = np.array([1.5, 3.3, 7.2, 15.9])
    a.bar(lv, med, color=ACC, alpha=0.85, width=0.6)
    a.errorbar(lv, med, yerr=[np.zeros(4), mx - med], fmt="none", ecolor=INK, capsize=4, lw=1)
    for i, (m_, x_) in enumerate(zip(med, mx)):
        a.text(i, x_ * 1.12, f"{m_:g} M\n(max {x_:g})", ha="center", fontsize=8)
    a.axhline(1.2, color=WARN, ls="--", lw=1)
    a.text(-0.45, 1.27, "desktop limit ≈ 1.2 M cells (13 GB)", color=WARN, fontsize=8)
    a.set_yscale("log"); a.set_ylim(0.5, 40); a.set_ylabel("cells per mesh [millions]")
    a.set_title("New levels, lighter band: median and largest\n(20 reference wings × 4 Re, wing blocks)")
    a.text(0.0, -0.2, "VC on the desktop; C, M and F on the university HPC", transform=a.transAxes, fontsize=8, color=MUTED)
    a = ax[1]
    names = ["planned rules\n(targets anchored,\nfirst band)", "lighter band\n(0.5 % c where\nlocal Re ≥ 4 × 10⁵)", "lighter band\n+ C-H wake lines\n(rough +30…60 %)"]
    med = [15.2, 10.9, 10.9 * 1.45]; lo = [4.9, 4.9, 10.9 * 1.30]; hi = [24.2, 15.9, 10.9 * 1.60]
    cols = [GREY, ACC, ACC]
    bars = a.bar(names, med, color=cols, alpha=0.85, width=0.6)
    bars[2].set_hatch("//"); bars[2].set_alpha(0.45)
    a.errorbar(range(3), med, yerr=[np.array(med) - np.array(lo), np.array(hi) - np.array(med)], fmt="none", ecolor=INK, capsize=4, lw=1)
    for i, m_ in enumerate(med):
        a.text(i + 0.33, m_, f"{m_:.1f} M" if i < 2 else f"≈ {m_:.0f} M", fontsize=8.5, va="center")
    a.axhspan(9, 11, color=BWB, alpha=0.12)
    a.text(-0.45, 11.4, "asked: 9–11 M (3 Nov)", color=BWB, fontsize=8, va="bottom", ha="left")
    a.set_ylabel("fine level F, median cells [millions]"); a.set_ylim(0, 27)
    a.set_title("Fine level: what each rule set costs (bars: range over the wings)")
    a.text(0.0, -0.33, "Also decided: tip gap 2 × s0 (about −8 %) and station gap 0.25 c at M (about −7 %): estimates, to be screened.\n"
                       "The +30…60 % of the C-H wake lines is a rough count, to be counted on the first wing in Stage 3.",
           transform=a.transAxes, fontsize=7.8, color=MUTED)
    save(fig, "cost_first_new.png")


# --- 4. the lower band at negative angles: the two options ------------------------------------
def fig_band_negative():
    up, lo = naca4()
    fig, ax = plt.subplots(1, 3, figsize=(13.5, 3.4))

    def draw(a, title, lower, note, col=AMBER):
        a.plot(up[:, 0], up[:, 1], color=INK, lw=1); a.plot(lo[:, 0], lo[:, 1], color=INK, lw=1)
        m = up[:, 0] <= 0.85
        a.plot(up[m, 0], up[m, 1] + 0.012, color=AMBER, lw=4, solid_capstyle="butt", alpha=0.8)
        ml = (lo[:, 0] >= lower[0]) & (lo[:, 0] <= lower[1])
        a.plot(lo[ml, 0], lo[ml, 1] - 0.012, color=col, lw=4, solid_capstyle="butt", alpha=0.8)
        a.text(0.0, 0.135, "upper band 0–85 % c", color=AMBER, fontsize=8)
        a.text(lower[0], -0.13, f"lower band {lower[0] * 100:.0f}–{lower[1] * 100:.0f} % c", color=col, fontsize=8)
        a.text(0.0, -0.21, note, fontsize=7.8, color=MUTED, va="top")
        a.set_xlim(-0.05, 1.08); a.set_ylim(-0.36, 0.18); a.set_aspect("equal"); a.axis("off"); a.set_title(title)

    draw(ax[0], "first: lower band 60–100 % c (angles 0–8°)", (0.6, 1.0),
         "At −5° the lower side takes the suction peak at the nose:\ntransition and bubbles move forward there, outside the band.\nBand length: 85 + 40 = 125 % of the chord.")
    ax[0].annotate("", xy=(0.12, -0.07), xytext=(0.45, -0.07), arrowprops=dict(arrowstyle="->", color=WARN, lw=1.2))
    ax[0].text(0.12, -0.105, "at −5°", color=WARN, fontsize=8)
    draw(ax[1], "option A: lower band from the leading edge", (0.0, 1.0),
         "One rule for both sides. On paper 85 + 100 = 185 % of the chord\n(about 1.5 × longer). Counted (Study 8, 7 Nov): no extra ring nodes\non the 20 reference wings × 4 Re: both sides share one node list.", col=WARN)
    draw(ax[2], "option B: keep the band; transition runs at ≥ 0° only", (0.6, 1.0),
         "SU2 with LM (transition) only at angles of 0° and above;\nADflow SA (fully turbulent) covers −5° to 0°. No extra cells.")
    save(fig, "band_negative.png")


def main() -> None:
    fig_levels()
    fig_topology()
    fig_cost()
    fig_band_negative()


if __name__ == "__main__":
    main()
