"""Design-space figures: what we support (full), where we focus (focus), what real wings do.

    python scripts/design_space_figs.py
      docs/design_space.png        every variable: full bar, focus bar, published values
      docs/pair_<name>.png         four key pairs, one panel per type
      docs/family_<type>.png       how each variable group changes the wing (full/focus min, mid, max)

Published values: configs/shape_evidence.yaml (shapes) and configs/real_uavs.yaml (sizes).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cfdauto.geometry.params import WING_TYPES, from_unit, load_config, mid_vector  # noqa: E402
from cfdauto.geometry.planform import build_planform  # noqa: E402
from cfdauto.geometry.sample import lhs  # noqa: E402
from cfdauto.geometry.sections import build_stations  # noqa: E402

import logging  # noqa: E402
import matplotlib  # noqa: E402
logging.getLogger("matplotlib").setLevel(logging.ERROR)
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

DOCS = ROOT / "docs"
NAME = {"bwb": "BWB", "conventional": "Cranked", "tapered": "Tapered", "flying_wing": "Flying wing"}
COL = {"bwb": "#2E8B57", "conventional": "#0C5EA8", "tapered": "#5B8FD0", "flying_wing": "#B07000"}
FAMILY = {"bwb": "tailless", "flying_wing": "tailless", "conventional": "tailed", "tapered": "tailed"}
INK, MUTED = "#1F2A33", "#6B7785"
N = 1500
plt.rcParams.update({"font.size": 9, "axes.edgecolor": "#B8C0C8", "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "font.family": "DejaVu Sans"})


# ---------------------------------------------------------------------------------------------
def derived(spec, v: dict) -> dict:
    pf = build_planform(spec, v)
    span, area = 2 * pf.semi_span, pf.area()
    return {"span_m": span, "mean_chord_m": area / span, "taper": pf.chord[-1] / pf.chord[0],
            "aspect_ratio": span ** 2 / area, "washout_deg": v["twist0_deg"] - v["twist3_deg"],
            "sweep1_deg": v["sweep1_deg"], "root_chord_m": v["root_chord_m"]}


def samples(cfg) -> dict:
    out = {}
    for t in WING_TYPES:
        for sp, spec in (("focus", cfg.types[t]), ("full", cfg.full[t])):
            rows = [derived(spec, v) for v in lhs(spec, N, 11)]
            out[(t, sp)] = {k: np.array([r[k] for r in rows]) for k in rows[0]}
    return out


def evidence() -> tuple[list[dict], list[dict]]:
    ev = yaml.safe_load((ROOT / "configs" / "shape_evidence.yaml").read_text())["points"]
    real = json.loads((DOCS / "real_uavs.json").read_text())["rows"]
    real = [r for r in real if r.get("use") == "ranges" and r.get("mean_chord")]
    return ev, real


ROWS = [  # (group, var, label, log scale, derived)
    ("Size", "root_chord_m", "Root chord [m]", True, False),
    ("Size", "aspect_ratio", "Aspect ratio", False, False),
    ("Size", "span_m", "Span [m]  (derived)", True, True),
    ("Size", "mean_chord_m", "Mean chord [m]  (derived)", True, True),
    ("Chords", "c2_ratio", "Chord at b1  (BWB × root; cranked × inboard)", False, False),
    ("Chords", "c3_ratio", "Chord at b2  (BWB × root; cranked × inboard)", False, False),
    ("Chords", "c4_ratio", "Tip chord  (BWB × root; cranked × inboard; taper)", False, False),
    ("Chords", "taper", "Overall taper tip/root  (derived)", False, True),
    ("Layout", "b3_ratio", "Outer panel share of semi-span", False, False),
    ("Layout", "split_ratio", "Inner panel share of the rest", False, False),
    ("Sweep", "sweep1_deg", "LE sweep, panel 1 [°]", False, False),
    ("Sweep", "sweep2_deg", "LE sweep, panel 2 [°]", False, False),
    ("Sweep", "sweep3_deg", "LE sweep, panel 3 [°]", False, False),
    ("Twist", "twist0_deg", "Root twist [°]  (sets incidence only)", False, False),
    ("Twist", "washout_deg", "Washout root − tip [°]  (derived)", False, True),
    ("Dihedral", "dihedral_p1_deg", "Dihedral, panel 1 [°]", False, False),
    ("Dihedral", "dihedral_p2_deg", "Dihedral, panel 2 [°]", False, False),
    ("Dihedral", "dihedral_p3_deg", "Dihedral, panel 3 [°]", False, False),
]


def rng(cfg, smp, t, sp, var, is_derived):
    spec = (cfg.types if sp == "focus" else cfg.full)[t]
    if not is_derived:
        if var in spec.derived:
            return None
        return spec.ranges[var]
    a = smp[(t, sp)][var]
    if var == "washout_deg":   # exact from the twist bounds
        r = spec.ranges
        return (r["twist0_deg"][0] - r["twist3_deg"][1], r["twist0_deg"][1] - r["twist3_deg"][0])
    return (float(a.min()), float(a.max()))


def fig_design_space(cfg, smp, ev, real) -> None:
    n = len(ROWS)
    fig, axes = plt.subplots(n, 1, figsize=(11, 0.78 * n + 1.4), dpi=110)
    lanes = {t: 3 - k for k, t in enumerate(WING_TYPES)}
    last_grp = None
    for ax, (grp, var, label, log, der) in zip(axes, ROWS):
        lo_all, hi_all = [], []
        bounds = set()
        for t in WING_TYPES:
            y = lanes[t]
            fr, fo = rng(cfg, smp, t, "full", var, der), rng(cfg, smp, t, "focus", var, der)
            if fr is None:
                ax.text(0.5, y, "derived from other inputs", transform=ax.get_yaxis_transform(), va="center",
                        ha="center", fontsize=7, color=MUTED, style="italic")
                continue
            ax.barh(y, fr[1] - fr[0], left=fr[0], height=0.62, color=COL[t], alpha=0.18, lw=0)
            ax.barh(y, fo[1] - fo[0], left=fo[0], height=0.62, color=COL[t], alpha=0.85, lw=0)
            lo_all += [fr[0], fo[0]]
            hi_all += [fr[1], fo[1]]
            # published values
            for p in ev:
                if p["var"] != var or t not in p["types"]:
                    continue
                vv = p.get("value")
                filled = p["tag"] == "checked"
                if "range" in p and p.get("bound"):
                    bounds.add((p["range"][0], p["range"][1], p["src"]))
                elif "range" in p:
                    a, b = p["range"]
                    ax.plot([a, b], [y, y], color=INK, lw=1.3, solid_capstyle="butt", zorder=4)
                    for e in (a, b):
                        ax.plot([e, e], [y - 0.28, y + 0.28], color=INK, lw=1.3, zorder=4)
                    lo_all.append(a); hi_all.append(b)
                else:
                    ax.plot(vv, y, marker="D", ms=5.5, mfc=INK if filled else "white", mec=INK, mew=1.1, ls="none", zorder=4)
                    lo_all.append(vv); hi_all.append(vv)
            # real wings (sizes)
            if var in ("span_m", "mean_chord_m", "aspect_ratio"):
                vals = [r["span"] if var == "span_m" else r["mean_chord"] if var == "mean_chord_m" else r["aspect_ratio"]
                        for r in real if r["family"] == FAMILY[t]]
                ax.plot(vals, [y] * len(vals), marker="|", ms=11, mew=1.4, color=INK, ls="none", zorder=4, alpha=0.8)
                lo_all += vals; hi_all += vals
        for a, b, src in bounds:
            for e in (a, b):
                ax.axvline(e, color=MUTED, lw=1.1, ls=":", zorder=1)
            ax.text(b, 3.55, src + " ", ha="right", va="bottom", fontsize=6.5, color=MUTED)
            lo_all += [a]; hi_all += [b]
        if log:
            ax.set_xscale("log")
        lo, hi = min(lo_all), max(hi_all)
        pad = (hi / lo) ** 0.04 if log else 0.04 * (hi - lo)
        ax.set_xlim(lo / pad, hi * pad) if log else ax.set_xlim(lo - pad, hi + pad)
        ax.set_ylim(-0.7, 3.7)
        ax.set_yticks([lanes[t] for t in WING_TYPES])
        ax.set_yticklabels([NAME[t] for t in WING_TYPES], fontsize=7)
        for t, tl in zip(WING_TYPES, ax.get_yticklabels()):
            tl.set_color(COL[t])
        ax.tick_params(axis="x", labelsize=7.5, pad=1)
        ax.grid(axis="x", alpha=0.25)
        ax.set_title(label, loc="left", fontsize=9, color=INK, pad=2, fontweight="bold" if grp != last_grp else "normal")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        last_grp = grp
    # legend
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    h = [Patch(color="#7A8794", alpha=0.18, label="full space: what we support (40 + 5 wings per type, corners at its edges)"),
         Patch(color="#7A8794", alpha=0.85, label="focus space: where we put the emphasis (100 + 5 + 10 wings per type)"),
         Line2D([], [], marker="D", ls="none", mfc=INK, mec=INK, label="published value, checked"),
         Line2D([], [], marker="D", ls="none", mfc="white", mec=INK, label="published value, agent or second-hand"),
         Line2D([], [], marker="|", ls="none", ms=11, mew=1.4, color=INK, label="real Class I–II wing (area published)"),
         Line2D([], [], color=INK, lw=1.3, marker="|", ms=8, label="published range"),
         Line2D([], [], color=MUTED, lw=1.1, ls=":", label="design-space bound of another automated study")]
    fig.legend(handles=h, loc="upper left", ncol=2, fontsize=8, frameon=False, bbox_to_anchor=(0.01, 0.998))
    fig.tight_layout(rect=(0, 0, 1, 1 - 1.15 / (0.78 * n + 1.4)), h_pad=0.6)
    fig.savefig(DOCS / "design_space.png")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
PAIRS = [  # name, x, y, x label, y label, log x, log y
    ("size", "span_m", "mean_chord_m", "Span [m]", "Mean chord [m]", True, True),
    ("planform", "aspect_ratio", "taper", "Aspect ratio", "Overall taper (tip / root)", False, False),
    ("sweep", "aspect_ratio", "sweep1_deg", "Aspect ratio", "LE sweep, inner panel [°]", False, False),
    ("twist", "sweep1_deg", "washout_deg", "LE sweep, inner panel [°]", "Washout root − tip [°]", False, False),
]
EV_VAR = {"taper": {"bwb": "c4_ratio", "flying_wing": "c4_ratio", "tapered": "c4_ratio"}}


def joint_points(ev, t, xv, yv):
    """Published wings that give both quantities (same source wing)."""
    def key(p):
        return p["src"].split(" (")[0]
    def var_for(v):
        return EV_VAR.get(v, {}).get(t, v)
    by = {}
    for p in ev:
        if t in p["types"] and "value" in p:
            by.setdefault(key(p), {})[p["var"]] = p
    out = []
    for k, d in by.items():
        a, b = d.get(var_for(xv)), d.get(var_for(yv))
        if a and b:
            out.append((a["value"], b["value"], k, a["tag"] == "checked" and b["tag"] == "checked"))
    return out


def fig_pairs(cfg, smp, ev, real) -> None:
    for name, xv, yv, xl, yl, lx, ly in PAIRS:
        fig, axes = plt.subplots(1, 4, figsize=(13, 3.6), dpi=110, sharex=True, sharey=True)
        for ax, t in zip(axes, WING_TYPES):
            fu, fo = smp[(t, "full")], smp[(t, "focus")]
            ax.scatter(fu[xv], fu[yv], s=3, color=COL[t], alpha=0.12, lw=0, label="full space")
            ax.scatter(fo[xv], fo[yv], s=3, color=COL[t], alpha=0.75, lw=0, label="focus space")
            if name == "size":
                rr = [r for r in real if r["family"] == FAMILY[t]]
                ax.scatter([r["span"] for r in rr], [r["mean_chord"] for r in rr], s=26, marker="D", color=INK,
                           edgecolor="white", lw=0.6, zorder=4, label="real wing")
            for x, y, k, ok in joint_points(ev, t, xv, yv):
                ax.scatter([x], [y], s=34, marker="D", color=INK if ok else "white", edgecolor=INK, lw=1.1, zorder=5)
                ax.annotate(k, (x, y), fontsize=6.5, xytext=(4, 3), textcoords="offset points", color=INK)
            ax.set_title(NAME[t], color=COL[t], fontsize=10, fontweight="bold")
            ax.set_xlabel(xl)
            if lx:
                ax.set_xscale("log")
            if ly:
                ax.set_yscale("log")
            ax.grid(alpha=0.25)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
        axes[0].set_ylabel(yl)
        from matplotlib.lines import Line2D
        h = [Line2D([], [], marker="o", ls="none", color="#7A8794", alpha=0.25, label="full space (supported)"),
             Line2D([], [], marker="o", ls="none", color="#7A8794", alpha=0.9, label="focus space (emphasis)"),
             Line2D([], [], marker="D", ls="none", mfc=INK, mec=INK, label="real / published wing (checked)"),
             Line2D([], [], marker="D", ls="none", mfc="white", mec=INK, label="published (agent or second-hand)")]
        fig.legend(handles=h, loc="lower center", ncol=4, fontsize=8, frameon=False)
        fig.tight_layout(rect=(0, 0.07, 1, 1))
        fig.savefig(DOCS / f"pair_{name}.png")
        plt.close(fig)


# ---------------------------------------------------------------------------------------------
GROUPS = [  # label, variables, view
    ("Aspect ratio", ["aspect_ratio"], "top"),
    ("Chords / taper", ["c2_ratio", "c3_ratio", "c4_ratio"], "top"),
    ("Where the breaks sit", ["b3_ratio", "split_ratio"], "top"),
    ("LE sweep", ["sweep1_deg", "sweep2_deg", "sweep3_deg"], "top"),
    ("Washout (root and tip sections)", ["twist0_deg", "twist3_deg"], "twist"),
    ("Dihedral (front view)", ["dihedral_p1_deg", "dihedral_p2_deg", "dihedral_p3_deg"], "front"),
]
COLS = [("full min", "full", 0.0), ("focus min", "focus", 0.0), ("mid (focus)", "focus", 0.5),
        ("focus max", "focus", 1.0), ("full max", "full", 1.0)]


def fig_family(cfg) -> None:
    for t in WING_TYPES:
        foc, ful = cfg.types[t], cfg.full[t]
        groups = [g for g in GROUPS if any(v in foc.free_variables for v in g[1])]
        fig, axes = plt.subplots(len(groups), 5, figsize=(13, 1.85 * len(groups) + 0.6), dpi=105)
        for r, (glab, vars_, view) in enumerate(groups):
            for c, (clab, sp, u) in enumerate(COLS):
                spec = foc if sp == "focus" else ful
                # others at the focus mid-range; the group's variables at this column's bound
                vec_mid = mid_vector(foc)
                lo_hi = {}
                for v in vars_:
                    if v in spec.free_variables:
                        a, b = spec.ranges[v]
                        lo_hi[v] = a + u * (b - a)
                # washout: root up / tip down at the "max" end
                if view == "twist" and "twist0_deg" in lo_hi:
                    a0, b0 = spec.ranges["twist0_deg"]; a3, b3 = spec.ranges["twist3_deg"]
                    lo_hi["twist0_deg"] = a0 + u * (b0 - a0)
                    lo_hi["twist3_deg"] = b3 - u * (b3 - a3)
                from cfdauto.geometry.params import resolve
                vec = resolve(foc, {**vec_mid, **lo_hi})
                ax = axes[r, c]
                draw_view(ax, foc, vec, view, COL[t], dashed=(sp == "full"))
                if r == 0:
                    ax.set_title(clab, fontsize=9, color=INK if sp == "focus" else MUTED,
                                 fontweight="bold" if sp == "focus" else "normal")
                if c == 0:
                    ax.text(-0.04, 0.5, glab, transform=ax.transAxes, rotation=90, ha="right", va="center",
                            fontsize=8.5, color=INK)
                ax.text(0.5, -0.02, value_text(vec, vars_, view), transform=ax.transAxes, ha="center", va="top",
                        fontsize=7, color=MUTED)
        fig.suptitle(f"{NAME[t]}: one variable group at a time (others at the focus mid-range). "
                     "Solid = focus space, dashed outline = full space. Top views to equal span.",
                     x=0.01, ha="left", fontsize=10, color=INK)
        fig.tight_layout(rect=(0.02, 0, 1, 0.97), h_pad=1.4)
        fig.savefig(DOCS / f"family_{t}.png")
        plt.close(fig)


def value_text(vec, vars_, view) -> str:
    if view == "twist":
        return f"root {vec['twist0_deg']:+.1f}°, tip {vec['twist3_deg']:+.1f}° (washout {vec['twist0_deg'] - vec['twist3_deg']:.1f}°)"
    short = {"aspect_ratio": "AR", "c2_ratio": "c2", "c3_ratio": "c3", "c4_ratio": "c4", "b3_ratio": "b3",
             "split_ratio": "split", "sweep1_deg": "Λ1", "sweep2_deg": "Λ2", "sweep3_deg": "Λ3",
             "dihedral_p1_deg": "Γ1", "dihedral_p2_deg": "Γ2", "dihedral_p3_deg": "Γ3"}
    return ", ".join(f"{short[v]} {vec[v]:.2f}".rstrip("0").rstrip(".") for v in vars_ if v in short)


def draw_view(ax, spec, vec, view, color, dashed) -> None:
    import matplotlib.patches as mp
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    pf = build_planform(spec, vec)
    s_ = pf.semi_span
    kw = dict(fill=False, ec=color, lw=1.4, ls=(0, (4, 2))) if dashed else dict(fc=color, ec=color, alpha=0.75, lw=1)
    if view == "top":
        y, x, c = pf.y / s_, pf.x_le / s_, pf.chord / s_
        half = list(zip(y, -x)) + list(zip(y[::-1], -(x + c)[::-1]))
        pts = np.array(half + [(-a, b) for a, b in half[::-1]])
        ax.add_patch(mp.Polygon(pts, closed=True, **kw))
        ax.set_xlim(-1.05, 1.05); ax.set_ylim(min(-1.0, pts[:, 1].min() - 0.05), 0.1)
        ax.set_aspect("equal", adjustable="datalim")
    elif view == "front":
        _, st = build_stations(spec, vec)
        y = np.array([q.y for q in st]) / s_
        z = np.array([q.z_le for q in st]) / s_
        for sgn in (1, -1):
            ax.plot(sgn * y, z, color=color, lw=2.2, ls="--" if dashed else "-")
        ax.axhline(0, color="#C9D1D9", lw=0.8)
        ax.set_xlim(-1.05, 1.05); ax.set_ylim(-0.25, 0.25); ax.set_aspect("equal")
    else:   # twist: root and tip sections, unit chord, side by side
        _, st = build_stations(spec, vec)
        for k, q in ((0, st[0]), (1, st[-1])):
            a = q.airfoil
            tw = np.radians(q.twist_deg)
            xx = np.concatenate([a.x, a.x[::-1]]); yy = np.concatenate([a.yu, a.yl[::-1]])
            X = xx * np.cos(tw) + yy * np.sin(tw) + 1.25 * k
            Z = -xx * np.sin(tw) + yy * np.cos(tw)
            ax.fill(X, Z, color=color, alpha=0.0 if dashed else 0.75, lw=0)
            ax.plot(X, Z, color=color, lw=1.2, ls="--" if dashed else "-")
            ax.plot([1.25 * k - 0.05, 1.25 * k + 1.05], [0, 0], color="#C9D1D9", lw=0.8)
        ax.text(0.5, 0.2, "root", ha="center", fontsize=7, color=MUTED)
        ax.text(1.75, 0.2, "tip", ha="center", fontsize=7, color=MUTED)
        ax.set_xlim(-0.1, 2.35); ax.set_ylim(-0.32, 0.28); ax.set_aspect("equal")


BANDS = [(0, 1e5, "#C0392B", "below 10⁵: laminar separation, RANS poor"),
         (1e5, 5e5, "#E0A030", "10⁵ – 5 × 10⁵: laminar bubbles, RANS biased"),
         (5e5, 3e6, "#5B8FD0", "5 × 10⁵ – 3 × 10⁶: transitional to turbulent, RANS good"),
         (3e6, 1e9, "#1F3F7A", "above 3 × 10⁶: turbulent")]


def fig_local_re(cfg) -> None:
    """Each type's smallest focus wing at its slowest and largest at its fastest: local chord Re along the span."""
    ext = json.loads((DOCS / "size_extremes.json").read_text())
    air = yaml.safe_load((ROOT / "configs" / "real_uavs.yaml").read_text())["air"]
    import matplotlib.patches as mp
    fig, axes = plt.subplots(2, 4, figsize=(13.5, 5.6), dpi=110)
    for c, t in enumerate(WING_TYPES):
        r = ext[f"{t}/focus"]
        lo, hi = r["speed_m_s"]
        for row, (key, v, rho_mu, txt) in enumerate((("smallest", lo, air["3048_m"], f"smallest focus wing, {lo:g} m/s at 3,048 m"),
                                                    ("largest", hi, air["sea_level"], f"largest focus wing, {hi:g} m/s at sea level"))):
            ax = axes[row, c]
            spec = cfg.types[t]
            pf = build_planform(spec, r[key]["vector"])
            S = pf.semi_span
            ys = np.linspace(0, S, 120)
            xl, ch = pf.at(ys)
            for y0, y1, x0, x1, c0, c1 in zip(ys[:-1], ys[1:], xl[:-1], xl[1:], ch[:-1], ch[1:]):
                re_ = rho_mu * v * 0.5 * (c0 + c1)
                colr = next(cc for a, b, cc, _ in BANDS if a <= re_ < b)
                for sg in (1, -1):
                    poly = [(sg * y0 / S, -x0 / S), (sg * y1 / S, -x1 / S), (sg * y1 / S, -(x1 + c1) / S), (sg * y0 / S, -(x0 + c0) / S)]
                    ax.add_patch(mp.Polygon(poly, closed=True, fc=colr, ec=colr, lw=0.3))
            re_root, re_tip = rho_mu * v * pf.chord[0], rho_mu * v * pf.chord[-1]
            ax.set_xlim(-1.05, 1.05)
            ax.set_ylim(min(-1.0, -(pf.x_le + pf.chord).max() / S - 0.05), 0.12)
            ax.set_aspect("equal", adjustable="datalim")
            ax.set_xticks([]); ax.set_yticks([])
            for sp_ in ax.spines.values():
                sp_.set_visible(False)
            sci = lambda x: f"{x:.1e}".replace("e+0", "e")  # noqa: E731
            ax.set_title(f"{NAME[t]}: span {2 * S:.2f} m" if row == 0 else f"span {2 * S:.1f} m", fontsize=9.5,
                         color=COL[t], fontweight="bold" if row == 0 else "normal")
            ax.text(0.5, -0.04, f"{txt}\nroot Re {sci(re_root)}, tip Re {sci(re_tip)}", transform=ax.transAxes,
                    ha="center", va="top", fontsize=7.5, color=MUTED)
    h = [mp.Patch(color=cc, label=lab) for _, _, cc, lab in BANDS]
    fig.legend(handles=h, loc="lower center", ncol=2, fontsize=8, frameon=False)
    fig.suptitle("Local Reynolds number along the span (chord-based). Top: the worst low-Re case. Bottom: the highest-Re case.",
                 x=0.01, ha="left", fontsize=10.5, color=INK)
    fig.tight_layout(rect=(0, 0.1, 1, 0.95), h_pad=2.2)
    fig.savefig(DOCS / "local_re.png")
    plt.close(fig)


def main() -> None:
    cfg = load_config()
    fig_local_re(cfg)
    smp = samples(cfg)
    ev, real = evidence()
    fig_design_space(cfg, smp, ev, real)
    fig_pairs(cfg, smp, ev, real)
    fig_family(cfg)
    print("written: design_space.png, pair_*.png, family_*.png")


if __name__ == "__main__":
    main()
