"""Figures for the executive summary of the geometry module.

    python scripts/summary_figs.py
      docs/summary_vector.png        the design vector on one wing: stations, panels, the 18 numbers
      docs/summary_types.png         families and types, three focus wings each, and the rule that names the type
      docs/summary_spaces.png        full space vs focus space vs real wings, key parameters only
      docs/summary_pipeline.png      the five steps (rendered from the page, needs Playwright)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from cfdauto.geometry.build import load_set  # noqa: E402
from cfdauto.geometry.params import WING_TYPES, load_config, resolve  # noqa: E402
from cfdauto.geometry.planform import build_planform  # noqa: E402

import logging  # noqa: E402
import matplotlib  # noqa: E402
logging.getLogger("matplotlib").setLevel(logging.ERROR)
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Arc, FancyArrowPatch, Polygon  # noqa: E402

DOCS = ROOT / "docs"
INK, MUTED, ACC, WARN, AMBER = "#1F2A33", "#6B7785", "#0C5EA8", "#B02A20", "#9A6200"
COL = {"bwb": "#2E8B57", "flying_wing": "#B07000", "cranked": "#0C5EA8", "tapered": "#5B8FD0"}
NAME = {"bwb": "BWB", "flying_wing": "Flying wing", "cranked": "Cranked", "tapered": "Tapered"}
plt.rcParams.update({"font.size": 10, "font.family": "DejaVu Sans", "axes.edgecolor": "#B8C0C8"})


def _naca(t=0.12, m=0.03, p=0.4, n=50):
    x = 0.5 * (1 - np.cos(np.linspace(0, np.pi, n)))
    yt = 5 * t * (0.2969 * np.sqrt(x) - 0.126 * x - 0.3516 * x ** 2 + 0.2843 * x ** 3 - 0.1036 * x ** 4)
    yc = np.where(x < p, m / p ** 2 * (2 * p * x - x ** 2), m / (1 - p) ** 2 * ((1 - 2 * p) + 2 * p * x - x ** 2))
    return x, yc + yt, yc - yt


def fig_vector() -> None:
    """One BWB (focus mid wing) with every number of the design vector drawn where it acts."""
    cfg = load_config()
    spec = cfg.types["bwb"]
    vec = resolve(spec, load_set("bwb", "reference")["vectors"][0])
    pf = build_planform(spec, vec)
    y, xl, c = pf.y, pf.x_le, pf.chord
    S = pf.semi_span
    fig = plt.figure(figsize=(15, 7.6), dpi=110)
    ax = fig.add_axes((0.02, 0.02, 0.60, 0.90))
    # planform (x downstream = down)
    poly = [(a, -b) for a, b in zip(y, xl)] + [(a, -(b + cc)) for a, b, cc in zip(y[::-1], xl[::-1], c[::-1])]
    ax.add_patch(Polygon(poly, closed=True, fc="#DCEBE2", ec=INK, lw=1.6))
    names = ["b0 (root)", "b1", "b2", "b3 (tip)"]
    cl = ["c₀ = root chord", "c₁ = c2_ratio · c₀", "c₂ = c3_ratio · c₀", "c₃ = c4_ratio · c₀"]
    for k in range(4):
        ax.plot([y[k], y[k]], [-xl[k], -(xl[k] + c[k])], color=COL["bwb"], lw=3.2, solid_capstyle="butt")
        ax.text(y[k], 0.10 * S + 0.02, names[k], ha="center", va="bottom", fontsize=10, fontweight="bold", color=INK)
        ax.text(y[k] + 0.012 * S, -(xl[k] + 0.55 * c[k]), cl[k], ha="left", va="center", fontsize=9, color=COL["bwb"],
                bbox=dict(fc="white", ec="none", alpha=0.85, pad=1.2))
    # sweep angles at each panel's leading edge
    for k in range(3):
        L = 0.35 * (y[k + 1] - y[k])
        ax.plot([y[k], y[k] + L], [-xl[k], -xl[k]], color=MUTED, lw=0.9, ls=(0, (3, 2)))
        ang = np.degrees(np.arctan2(-(xl[k + 1] - xl[k]), y[k + 1] - y[k]))
        ax.add_patch(Arc((y[k], -xl[k]), 2 * L, 2 * L, theta1=ang, theta2=0, color=ACC, lw=1.4))
        ax.text(y[k] + 1.05 * L, -xl[k] - 0.05 * S * 0.35, f"Λ{k + 1}", color=ACC, fontsize=11, fontweight="bold", va="top")
    # panel spans (dimension lines under the wing)
    yb = -(max(xl + c)) - 0.10 * S
    lab = ["inner panel", "middle panel", "outer panel"]
    for k in range(3):
        ax.add_patch(FancyArrowPatch((y[k], yb), (y[k + 1], yb), arrowstyle="<->", mutation_scale=10, color=INK, lw=1.0))
        ax.text(0.5 * (y[k] + y[k + 1]), yb - 0.035 * S, lab[k], ha="center", va="top", fontsize=9, color=INK)
    yb2 = yb - 0.16 * S
    ax.add_patch(FancyArrowPatch((0, yb2), (S, yb2), arrowstyle="<->", mutation_scale=10, color=INK, lw=1.0))
    ax.text(0.5 * S, yb2 - 0.035 * S, "semi-span S = b / 2  (from the aspect ratio AR and c₀)", ha="center", va="top",
            fontsize=9.5, color=INK)
    ax.text(0.5 * (y[2] + y[3]), yb + 0.05 * S, "b3_ratio = outer / S", ha="center", fontsize=8.5, color=MUTED)
    ax.text(0.5 * (y[0] + y[2]), yb + 0.05 * S, "split_ratio = inner / (inner + middle)", ha="center", fontsize=8.5,
            color=MUTED)
    ax.annotate("", xy=(-0.04 * S, -0.30 * S), xytext=(-0.04 * S, 0.02 * S),
                arrowprops=dict(arrowstyle="->", color=INK, lw=1.2))
    ax.text(-0.055 * S, -0.12 * S, "flow", rotation=90, ha="right", va="center", fontsize=9, color=INK)
    # front view under the top view, same span scale: dihedral per panel (heights exaggerated)
    yfv = yb2 - 0.30 * S
    gam = [vec["dihedral_p1_deg"] + 4, vec["dihedral_p2_deg"] + 6, vec["dihedral_p3_deg"] + 8]
    zf = [0.0]
    for k in range(3):
        zf.append(zf[-1] + (y[k + 1] - y[k]) * np.tan(np.radians(gam[k])))
    zf = np.array(zf) * (0.14 * S / max(zf[-1], 1e-9))
    ax.plot([0, S], [yfv, yfv], color=MUTED, lw=0.8, ls=(0, (3, 2)))
    ax.plot(y, yfv + zf, color=INK, lw=2.2, marker="o", ms=4)
    for k in range(3):
        ax.text(0.5 * (y[k] + y[k + 1]), yfv + 0.5 * (zf[k] + zf[k + 1]) + 0.035 * S, f"Γ{k + 1}", color=WARN,
                fontsize=11, fontweight="bold", ha="center")
    ax.text(S, yfv - 0.04 * S, "front view: dihedral per panel (heights exaggerated)", fontsize=9, color=MUTED,
            ha="right", va="top")
    ax.set_aspect("equal")
    ax.set_xlim(-0.12 * S, 1.06 * S)
    ax.set_ylim(yfv - 0.12 * S, 0.20 * S)
    ax.axis("off")
    ax.set_title("Top view of a half wing (BWB example): 4 stations, 3 straight (ruled) panels", loc="left",
                 fontsize=11.5, fontweight="bold", color=INK)
    # sections: twist and airfoil per station
    sx = fig.add_axes((0.63, 0.55, 0.14, 0.34))
    xs, yu, yl = _naca()
    for k, (th, nm) in enumerate(((vec["twist0_deg"] + 3, "root b0"), (vec["twist3_deg"] - 3, "tip b3"))):
        a = np.radians(th)
        off = -0.55 * k
        for yy in (yu, yl):
            X = xs * np.cos(a) + yy * np.sin(a)
            Y = -xs * np.sin(a) + yy * np.cos(a) + off
            sx.plot(X, Y, color=AMBER, lw=1.6)
        sx.plot([0, 1.1], [off, off], color=MUTED, lw=0.8, ls=(0, (3, 2)))
        sx.text(1.15, off, f"θ{0 if k == 0 else 3}  ({nm})", va="center", fontsize=10, color=AMBER, fontweight="bold")
    sx.text(0.0, 0.28, "sections: twist θ0–θ3 and an airfoil per station", fontsize=9, color=MUTED)
    sx.text(0.0, -0.95, "washout = θ0 − θ3  (derived)", fontsize=9, color=MUTED)
    sx.set_aspect("equal"); sx.set_xlim(-0.05, 1.9); sx.set_ylim(-1.05, 0.38); sx.axis("off")
    # the 18 numbers
    tx = fig.add_axes((0.64, 0.02, 0.35, 0.50)); tx.axis("off")
    rows = [("Size", "c₀ root chord, AR aspect ratio  → S derived", COL["bwb"]),
            ("Chords", "c2_ratio, c3_ratio, c4_ratio", COL["bwb"]),
            ("Layout", "b3_ratio, split_ratio  (where b1, b2 sit)", INK),
            ("Sweep", "Λ1, Λ2, Λ3  (leading edge, per panel)", ACC),
            ("Twist", "θ0, θ1, θ2, θ3  (per station)", AMBER),
            ("Dihedral", "Γ1, Γ2, Γ3  (per panel)", WARN)]
    tx.text(0, 1.0, "The design vector: 18 numbers + 4 airfoil names", fontsize=11.5, fontweight="bold", color=INK, va="top")
    for k, (g, t, col) in enumerate(rows):
        yy = 0.86 - 0.115 * k
        tx.text(0.0, yy, g, fontsize=10.5, fontweight="bold", color=col, va="top")
        tx.text(0.25, yy, t, fontsize=10, color=INK, va="top")
    tx.text(0.0, 0.14, "Each type's laws fix some numbers (tapered: one taper, one sweep);\nthe sampler varies the rest. "
            "Same vector shape for every type:\none hash, one sampler, one ML input.", fontsize=9, color=MUTED, va="top")
    fig.savefig(DOCS / "summary_vector.png", bbox_inches="tight")
    plt.close(fig)


RULES = {"bwb": "tailless → BWB: rule: root chord ≥ 2.2 × the outer-half mean chord",
         "flying_wing": "tailless → flying wing: rule: otherwise (straight edges, moderate taper)",
         "cranked": "conventional → cranked: rule: a kink in the leading edge or the chord",
         "tapered": "conventional → tapered: rule: no kink (straight edges)"}


def fig_types() -> None:
    """Three focus wings per type (10th, 50th, 90th percentile of aspect ratio), whole wing, each to its own span."""
    cfg = load_config()
    fig, axes = plt.subplots(1, 4, figsize=(15, 4.6), dpi=110)
    for ax, t in zip(axes, WING_TYPES):
        spec = cfg.types[t]
        vecs = [resolve(spec, v) for v in load_set(t, "training")["vectors"]]
        ars = np.array([v["aspect_ratio"] for v in vecs])
        picks = [int(np.argsort(ars)[int(q * (len(ars) - 1))]) for q in (0.1, 0.5, 0.9)]
        for j, i in enumerate(picks):
            pf = build_planform(spec, vecs[i])
            s = pf.semi_span
            yy = np.concatenate([-pf.y[::-1], pf.y]) / s
            le = np.concatenate([pf.x_le[::-1], pf.x_le]) / s
            te = np.concatenate([(pf.x_le + pf.chord)[::-1], pf.x_le + pf.chord]) / s
            off = -1.15 * j
            ax.fill(np.concatenate([yy, yy[::-1]]), np.concatenate([-le, -te[::-1]]) + off, color=COL[t], alpha=0.75, lw=0)
            ax.text(1.08, off - 0.2, f"b {2 * s:.1f} m\nAR {vecs[i]['aspect_ratio']:.1f}", fontsize=8.5, color=MUTED,
                    va="center")
        ax.set_aspect("equal"); ax.set_xlim(-1.05, 1.6); ax.set_ylim(-3.55, 0.25); ax.axis("off")
        fam = "Tailless" if t in ("bwb", "flying_wing") else "Conventional"
        import textwrap
        ax.set_title(f"{fam}: {NAME[t]}\n" + "\n".join(textwrap.wrap(RULES[t].split(": ", 1)[1], 40)),
                     color=COL[t], fontweight="bold", fontsize=11, loc="left")
    fig.suptitle("Two families (an input: must the wing trim itself?), two types each (set by our rules). "
                 "Three focus wings per type, each drawn to its own span.", x=0.01, ha="left", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(DOCS / "summary_types.png")
    plt.close(fig)


def fig_spaces() -> None:
    """The design-space map for the key parameters only: full bar, focus bar, real wings (no sources)."""
    import design_space_figs as dsf
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    rows = [("root_chord_m", "Root chord [m]", True, False), ("aspect_ratio", "Aspect ratio", False, False),
            ("span_m", "Full span b [m]  (derived)", True, True), ("mean_chord_m", "Mean chord [m]  (derived)", True, True),
            ("taper", "Overall taper, tip / root  (derived)", False, True), ("sweep1_deg", "LE sweep, inner panel [°]", False, False),
            ("washout_deg", "Washout, root − tip [°]  (derived)", False, True)]
    cfg = load_config()
    smp = dsf.samples(cfg)
    _, real = dsf.evidence()
    fig, axes = plt.subplots(len(rows), 1, figsize=(11, 0.82 * len(rows) + 1.0), dpi=110)
    lanes = {t: 3 - k for k, t in enumerate(WING_TYPES)}
    for ax, (var, label, log, der) in zip(axes, rows):
        lo_all, hi_all = [], []
        for t in WING_TYPES:
            yy = lanes[t]
            fr, fo = dsf.rng(cfg, smp, t, "full", var, der), dsf.rng(cfg, smp, t, "focus", var, der)
            ax.barh(yy, fr[1] - fr[0], left=fr[0], height=0.62, color=COL[t], alpha=0.18, lw=0)
            ax.barh(yy, fo[1] - fo[0], left=fo[0], height=0.62, color=COL[t], alpha=0.85, lw=0)
            lo_all += [fr[0], fo[0]]; hi_all += [fr[1], fo[1]]
            if var in ("span_m", "mean_chord_m", "aspect_ratio"):
                key = {"span_m": "span", "mean_chord_m": "mean_chord", "aspect_ratio": "aspect_ratio"}[var]
                fam = "tailless" if t in ("bwb", "flying_wing") else "conventional"
                vals = [r[key] for r in real if r["family"] == fam and r.get(key)]
                ax.plot(vals, [yy] * len(vals), marker="|", ms=11, mew=1.4, color=INK, ls="none", alpha=0.8)
                lo_all += vals; hi_all += vals
        if log:
            ax.set_xscale("log")
        lo, hi = min(lo_all), max(hi_all)
        pad = (hi / lo) ** 0.04 if log else 0.04 * (hi - lo)
        ax.set_xlim(lo / pad, hi * pad) if log else ax.set_xlim(lo - pad, hi + pad)
        ax.set_ylim(-0.7, 3.7)
        ax.set_yticks([lanes[t] for t in WING_TYPES]); ax.set_yticklabels([NAME[t] for t in WING_TYPES], fontsize=7.5)
        for t, tl in zip(WING_TYPES, ax.get_yticklabels()):
            tl.set_color(COL[t])
        ax.tick_params(axis="x", labelsize=8, pad=1)
        ax.grid(axis="x", alpha=0.25)
        ax.set_title(label, loc="left", fontsize=9.5, color=INK, pad=2, fontweight="bold")
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    h = [Patch(color="#7A8794", alpha=0.18, label="full space: everything we support (sampled sparsely)"),
         Patch(color="#7A8794", alpha=0.85, label="focus space: real Class I–II wings, b ≤ 7 m (sampled densely)"),
         Line2D([], [], marker="|", ls="none", ms=11, mew=1.4, color=INK, label="a real UAV wing (published size)")]
    fig.legend(handles=h, loc="upper left", ncol=2, fontsize=8.5, frameon=False, bbox_to_anchor=(0.01, 0.998))
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.75 / (0.82 * len(rows) + 1.0)), h_pad=0.6)
    fig.savefig(DOCS / "summary_spaces.png")
    plt.close(fig)


def fig_page_svg(section: str, name: str) -> None:
    """Render one of the page's diagrams (the svg in section #<section>) to docs/<name> (needs node + Playwright)."""
    js = ROOT / "docs" / f"_render_{section}.js"
    js.write_text("""const { chromium } = require('playwright');
(async () => { const b = await chromium.launch(); const p = await b.newPage({viewport: {width: 1200, height: 900}, deviceScaleFactor: 2});
await p.goto('file://%s'); const el = await p.$('#%s .svgwrap'); await el.screenshot({path: '%s'}); await b.close(); })();"""
                  % (DOCS / "GEOMETRY_GENERATOR.html", section, DOCS / name))
    try:
        subprocess.run(["node", str(js)], check=True, capture_output=True, timeout=120)
    finally:
        js.unlink(missing_ok=True)


def fig_pipeline() -> None:
    """The page's five-step figure."""
    fig_page_svg("pipeline", "summary_pipeline.png")


def fig_runs() -> None:
    """The page's 'What was run' diagram: 2-D runs, strip theory, outputs, no 3-D CFD yet."""
    fig_page_svg("runs", "summary_runs.png")


def fig_mesh_zones() -> None:
    """Where the mesh must be fine and why: numbered zones on the BWB reference wing (top view) and on one
    section (side view). Schematic; the reasons and rules are in the summary's table."""
    from matplotlib.patches import Circle, Ellipse, FancyBboxPatch
    from cfdauto.geometry.sections import load_airfoil
    cfg = load_config()
    spec = cfg.types["bwb"]
    vec = resolve(spec, load_set("bwb", "reference")["vectors"][0])
    pf = build_planform(spec, vec)
    y, xl, c = pf.y, pf.x_le, pf.chord
    S = pf.semi_span
    RED, AMB, BLU, VIO, LBL = "#C0392B", "#B07000", "#0C5EA8", "#6B4FA0", "#5B8FD0"
    fig = plt.figure(figsize=(15, 8.0), dpi=130)
    ax = fig.add_axes((0.01, 0.33, 0.47, 0.62))
    bx = fig.add_axes((0.50, 0.40, 0.49, 0.50))

    def yy(frac):                       # spanwise interpolation of LE and chord
        yv = frac * S
        return yv, np.interp(yv, y, xl), np.interp(yv, y, c)

    def band(f0, f1, a0=0.0, a1=1.0, n=60):
        fr = np.linspace(a0, a1, n)
        pts = [yy(f) for f in fr]
        top = [(p[0], -(p[1] + f0 * p[2])) for p in pts]
        bot = [(p[0], -(p[1] + f1 * p[2])) for p in pts][::-1]
        return top + bot

    def num(axx, x, yv, k, col):
        axx.text(x, yv, str(k), ha="center", va="center", fontsize=11, fontweight="bold", color=col, zorder=7,
                 bbox=dict(boxstyle="circle,pad=0.28", fc="white", ec=col, lw=2.0))

    # ---- top view
    te_max = float(np.max(xl + c))
    wake_end = -te_max - 0.65 * c[0]
    te_pts = [(a, -(b + cc)) for a, b, cc in zip(y, xl, c)]
    ax.add_patch(Polygon(te_pts + [(S, wake_end), (0, wake_end)], closed=True, fc="#DCE8F5", ec="none", zorder=0))  # wake
    tip_te = -(xl[3] + c[3])
    ax.add_patch(FancyBboxPatch((S * 0.95, wake_end), 0.06 * S, tip_te - wake_end,
                                boxstyle="round,pad=0,rounding_size=0.02", fc="#A9C4E6", ec="none", zorder=1))  # vortex tube
    poly = [(a, -b) for a, b in zip(y, xl)] + [(a, -(b + cc)) for a, b, cc in zip(y[::-1], xl[::-1], c[::-1])]
    ax.add_patch(Polygon(poly, closed=True, fc="#EEF2F5", ec=INK, lw=1.6, zorder=2))
    ax.add_patch(Polygon(band(0.10, 0.85), closed=True, fc="#F6E7C8", ec=AMB, lw=0.0, hatch="///", zorder=3, alpha=0.9))
    ax.add_patch(Polygon(band(0.0, 0.05), closed=True, fc=RED, ec="none", alpha=0.45, zorder=4))
    ax.add_patch(Polygon(band(0.95, 1.0), closed=True, fc=RED, ec="none", alpha=0.45, zorder=4))
    ax.add_patch(Polygon(band(0.0, 1.0, 0.86, 1.0), closed=True, fc=BLU, ec="none", alpha=0.18, zorder=4))
    for k in (1, 2):
        ax.plot([y[k], y[k]], [-xl[k], -(xl[k] + c[k])], color=AMB, lw=3.2, solid_capstyle="butt", zorder=5)
    ax.plot([0, 0], [-xl[0], -(xl[0] + c[0])], color=VIO, lw=4.5, solid_capstyle="butt", zorder=5)
    ax.plot([y[3], y[3]], [-xl[3], -(xl[3] + c[3])], color=BLU, lw=3.2, solid_capstyle="butt", zorder=5)
    # markers
    num(ax, -0.06 * S, -(xl[0] + 0.5 * c[0]), 1, VIO)
    yv, xv, cv = yy(0.68); num(ax, yv, -(xv) + 0.07 * S, 2, RED)
    yv, xv, cv = yy(0.45); num(ax, yv, -(xv + 0.5 * cv), 3, AMB)
    num(ax, y[1], -xl[1] + 0.07 * S, 4, AMB); num(ax, y[2], -xl[2] + 0.07 * S, 4, AMB)
    yv, xv, cv = yy(0.93); num(ax, yv, -(xv + 0.5 * cv), 5, BLU)
    yv, xv, cv = yy(0.62); num(ax, yv, -(xv + cv) - 0.065 * S, 6, RED)
    num(ax, 0.45 * S, 0.5 * (wake_end - te_max), 7, LBL)
    ax.text(0.0, 0.12 * S, "Top view: half of the BWB reference wing (root at left), flow downward", fontsize=10.5,
            color=INK, va="bottom")
    ax.set_xlim(-0.12 * S, 1.08 * S); ax.set_ylim(wake_end - 0.03 * S, 0.2 * S)
    ax.set_aspect("equal"); ax.axis("off")

    # ---- side view of one section
    af = load_airfoil("mh104")
    pts = af.selig()
    xs, ys = pts[:, 0], pts[:, 1]
    bx.add_patch(Polygon([(1.0, 0.012), (2.05, 0.10), (2.05, -0.16), (1.0, -0.012)], closed=True, fc="#DCE8F5", ec="none"))
    d = np.gradient(pts, axis=0); nrm = np.column_stack([d[:, 1], -d[:, 0]]); nrm /= np.linalg.norm(nrm, axis=1)[:, None]
    for off in (0.012, 0.024, 0.036):
        o = pts + off * nrm
        bx.plot(o[:, 0], o[:, 1], color=VIO, lw=0.8, alpha=0.75)
    bx.fill(xs, ys, fc="#EEF2F5", ec=INK, lw=1.6, zorder=3)
    half = np.arange(len(pts)) < len(pts) // 2
    up = half & (pts[:, 0] >= 0.10) & (pts[:, 0] <= 0.85)
    lo = ~half & (pts[:, 0] >= 0.60)
    bx.plot(xs[up], ys[up] + 0.004, color=AMB, lw=5, solid_capstyle="butt", zorder=4)
    bx.plot(xs[lo], ys[lo] - 0.004, color=AMB, lw=5, solid_capstyle="butt", zorder=4)
    xb = np.linspace(0.42, 0.62, 40); yb = np.interp(xb, xs[up][::-1], ys[up][::-1]) + 0.004 + 0.022 * np.sin(np.pi * (xb - 0.42) / 0.20)
    bx.plot(xb, yb, color=AMB, lw=1.4, ls=(0, (3, 2)), zorder=4)
    bx.add_patch(Circle((0.0, 0.0), 0.045, fc=RED, ec="none", alpha=0.45, zorder=4))
    bx.add_patch(Circle((1.0, 0.0), 0.045, fc=RED, ec="none", alpha=0.45, zorder=4))
    num(bx, -0.10, 0.09, 2, RED); num(bx, 0.52, 0.17, 3, AMB); num(bx, 1.02, 0.10, 6, RED)
    num(bx, 0.25, -0.13, 1, VIO); num(bx, 1.55, -0.14, 7, LBL)
    bx.text(0.40, -0.135, "wall layers", fontsize=9, color=VIO, va="center")
    bx.text(0.52, 0.225, "bubble", fontsize=9, color=AMB, ha="center")
    bx.text(-0.2, 0.33, "Side view: one section (MH 104, BWB root)", fontsize=10.5, color=INK, va="bottom")
    bx.set_xlim(-0.2, 2.05); bx.set_ylim(-0.25, 0.33); bx.set_aspect("equal"); bx.axis("off")

    # ---- key
    rows = [(1, VIO, "Wall layers, all over: first cell from y⁺ ≤ 1 at each station's own Re (root and tip differ up to 17 × in Re)"),
            (2, RED, "Leading edge: suction peak; at high angle the flow turns turbulent at the nose"),
            (3, AMB, "Transition band: upper surface 10–85 % chord, lower surface 60–100 % (laminar run ends, bubbles; for a transition model)"),
            (4, AMB, "Breaks b1, b2: kinks in the surface, jump in the span loading: a mesh station exactly on each"),
            (5, BLU, "Tip: smallest chord and Re (below 10⁵ on small wings), tip vortex, first to stall on swept wings"),
            (6, RED, "Trailing edge and blunt base: base flow and the start of the wake; separation there only near stall"),
            (7, LBL, "Wake and tip vortex: downwash and induced drag; fine to about 2 chords behind the wing")]
    kx = fig.add_axes((0.02, 0.01, 0.96, 0.30)); kx.axis("off"); kx.set_xlim(0, 1); kx.set_ylim(0, 1)
    for i, (k, col, txt) in enumerate(rows):
        yk = 0.93 - i * 0.14
        kx.text(0.012, yk, str(k), ha="center", va="center", fontsize=10, fontweight="bold", color=col,
                bbox=dict(boxstyle="circle,pad=0.28", fc="white", ec=col, lw=2.0))
        kx.text(0.034, yk, txt, ha="left", va="center", fontsize=10.5, color=INK)
    fig.savefig(DOCS / "summary_mesh_zones.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    fig_vector()
    fig_types()
    fig_spaces()
    fig_pipeline()
    fig_runs()
    fig_mesh_zones()
    print("written: docs/summary_vector.png, summary_types.png, summary_spaces.png, summary_pipeline.png, summary_runs.png, summary_mesh_zones.png")


if __name__ == "__main__":
    main()
