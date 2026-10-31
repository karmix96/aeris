"""Flow map of one wing: what the flow will do, where, and which model to use.

    from cfdauto.flowmap.core import flow_map, plot
    fm = flow_map(spec, vec, tailless=True, speed_m_s=25, altitude_m=1000, alpha_deg=3)

Steps
  1. Classify: family (input: tailless or conventional) and type (our rules, labels.classify).
  2. Strips along the semi-span (root, mid-panels, breaks, near tip): local chord, twist, leading-edge
     sweep and section (the ruled blend of the two station sections).
  3. Local Reynolds number on the chord, Re = (rho/mu) V c (Stage 0 air), and Mach.
  4. Each strip in XFOIL at alpha + local twist, free transition and tripped at 1 % chord:
     transition point, laminar bubbles (Cf < 0), trailing-edge separation, and the drag that fully
     turbulent CFD would add.
  5. Phenomena list and a proposed turbulence model, by stated rules.

Limits (said in every output): 2-D strips; no induced angle (the local angle is too high toward the
tip), no crossflow transition on swept wings, no 3-D relief of bubbles. It shows where to look and
what to expect, not the 3-D answer.
"""

from __future__ import annotations

import math

import numpy as np

from ..geometry.labels import label
from ..geometry.measure import measure, table_from_stations
from ..geometry.params import TypeSpec, resolve
from ..geometry.sections import build_stations, build_wing_sections
from . import xfoil

# Stage 0 air (ISA, Sutherland): rho/mu [s/m^2] by altitude
RHO_MU = ((0.0, 68500.0), (1524.0, 60600.0), (3048.0, 53500.0))
BANDS = ((0.0, 1e5, "below 10⁵", "#C0392B"), (1e5, 5e5, "10⁵ – 5 × 10⁵", "#E0A030"),
         (5e5, 3e6, "5 × 10⁵ – 3 × 10⁶", "#5B8FD0"), (3e6, 1e12, "above 3 × 10⁶", "#1F3F7A"))
LIMITS = ("2-D XFOIL strips (e^N, N_crit 9): no induced angle (local angle too high toward the tip), "
          "no crossflow transition on swept wings, no 3-D relief of bubbles. Where to look, not the 3-D answer.")


def rho_over_mu(alt_m: float) -> float:
    a, r = zip(*RHO_MU)
    return float(np.interp(alt_m, a, r))


def sound_speed(alt_m: float) -> float:
    return math.sqrt(1.4 * 287.05 * (288.15 - 0.0065 * alt_m))


def band(re_: float) -> tuple[str, str]:
    for lo, hi, name, col in BANDS:
        if lo <= re_ < hi:
            return name, col
    return BANDS[-1][2], BANDS[-1][3]


def strips(pf, stations, n_per_panel: int = 2) -> list[dict]:
    """Strip positions: root, inside each panel, every break, and near the tip (97 % of S)."""
    S = pf.semi_span
    ys = [0.0]
    for k in range(3):
        a, b = pf.y[k], pf.y[k + 1]
        ys += [a + (b - a) * (j + 1) / (n_per_panel + 1) for j in range(n_per_panel)]
        ys.append(b if k < 2 else 0.97 * S)
    out = []
    for y in sorted(set(round(v, 12) for v in ys)):
        k = min(int(np.searchsorted(pf.y, y, side="right")) - 1, 2)
        a, b = stations[k], stations[k + 1]
        s = (y - a.y) / (b.y - a.y)
        out.append({"y": y, "panel": k, "s": s,
                    "chord": a.chord + s * (b.chord - a.chord),
                    "x_le": a.x_le + s * (b.x_le - a.x_le),
                    "twist": a.twist_deg + s * (b.twist_deg - a.twist_deg),
                    "sweep": float(pf.sweep_le_deg[k]),
                    "airfoil": a.airfoil.blend(b.airfoil, s) if s > 1e-9 else a.airfoil,
                    "section": a.airfoil.name if s < 1e-9 else (b.airfoil.name if s > 1 - 1e-9 else
                                                                 f"{a.airfoil.name}→{b.airfoil.name} {s:.2f}")})
    return out


def flow_map(spec: TypeSpec, vec: dict, tailless: bool, speed_m_s: float, altitude_m: float,
             alpha_deg: float, airfoils: list[str] | None = None, run_xfoil: bool = True) -> dict:
    vec = dict(vec)
    if airfoils:
        vec["airfoils"] = list(airfoils)
    vec = resolve(spec, vec)
    pf, st = build_stations(spec, vec)
    _, st_te = build_wing_sections(spec, vec, _te_rule())
    labels, values = label(measure(table_from_stations(st_te), st_te), tailless)
    rm, a_snd = rho_over_mu(altitude_m), sound_speed(altitude_m)
    rows = []
    for sp in strips(pf, st):
        re_ = rm * speed_m_s * sp["chord"]
        al = alpha_deg + sp["twist"]
        row = {k: sp[k] for k in ("y", "chord", "x_le", "twist", "sweep", "section")}
        row |= {"y_over_S": sp["y"] / pf.semi_span, "re": re_, "re_normal": re_ * math.cos(math.radians(sp["sweep"])),
                "band": band(re_)[0], "alpha_local": al}
        if run_xfoil and xfoil.available():
            pts = sp["airfoil"].selig()
            f, t = xfoil.run(pts, re_, al, False), xfoil.run(pts, re_, al, True)
            if f:
                row |= {"cl": f["cl"], "cd_free": f["cd"], "xtr_upper": f["xtr_top"], "xtr_lower": f["xtr_bot"],
                        "bubbles_upper": xfoil.bubbles(f["upper"], f["xtr_top"]),
                        "bubbles_lower": xfoil.bubbles(f["lower"], f["xtr_bot"]),
                        "te_separation": bool(np.any((np.array(f["upper"]["x"]) > 0.85) &
                                                     (np.array(f["upper"]["cf"]) < 0)))}
            if t:
                row["cd_tripped"] = t["cd"]
        rows.append(row)
    fm = {"family": labels[0], "type": labels[1], "labels": labels,
          "conditions": {"speed_m_s": speed_m_s, "altitude_m": altitude_m, "alpha_deg": alpha_deg,
                         "mach": speed_m_s / a_snd, "rho_over_mu": rm},
          "geometry": {"full_span_m": 2 * pf.semi_span, "semi_span_m": pf.semi_span,
                       "root_chord_m": float(pf.chord[0]), "tip_chord_m": float(pf.chord[-1]),
                       "y": pf.y.tolist(), "x_le": pf.x_le.tolist(), "chord": pf.chord.tolist(),
                       "sweep_le_deg": pf.sweep_le_deg.tolist(), "airfoils": [s.airfoil.name for s in st],
                       "aspect_ratio": vec["aspect_ratio"]},
          "strips": rows, "limits": LIMITS}
    fm["phenomena"] = phenomena(fm, values)
    fm["model"] = proposal(fm)
    return fm


def _te_rule():
    from ..geometry.params import load_config
    return load_config().te


def _drag_bias(rows: list[dict]) -> float | None:
    """Chord-weighted profile drag: tripped over free, minus one (strip trapezoids along y)."""
    ok = [r for r in rows if r.get("cd_free") and r.get("cd_tripped")]
    if len(ok) < 2:
        return None
    y = np.array([r["y"] for r in ok])
    w = np.array([r["chord"] for r in ok])
    f = np.trapezoid(w * np.array([r["cd_free"] for r in ok]), y)
    t = np.trapezoid(w * np.array([r["cd_tripped"] for r in ok]), y)
    return float(t / f - 1)


def phenomena(fm: dict, v: dict) -> list[dict]:
    rows, g = fm["strips"], fm["geometry"]
    out = []
    res = [r["re"] for r in rows]
    out.append({"what": "Reynolds number along the span", "where": "root → tip",
                "detail": f"{min(res):.2g} at the tip to {max(res):.2g} at the root (×{max(res) / min(res):.1f})"})
    lam = [r for r in rows if r.get("xtr_upper") is not None]
    if lam:
        mx = max(lam, key=lambda r: r["xtr_upper"])
        mn = min(lam, key=lambda r: r["xtr_upper"])
        out.append({"what": "Laminar run, then transition", "where": "upper surface, every strip",
                    "detail": f"turns turbulent at {100 * mn['xtr_upper']:.0f}–{100 * mx['xtr_upper']:.0f} % chord"})
    bub = [(r, b) for r in rows for b in r.get("bubbles_upper") or []]
    if bub:
        y0, y1 = min(r["y_over_S"] for r, _ in bub), max(r["y_over_S"] for r, _ in bub)
        x0, x1 = min(b[0] for _, b in bub), max(b[1] for _, b in bub)
        out.append({"what": "Laminar separation bubble", "where": f"{100 * y0:.0f}–{100 * y1:.0f} % of the semi-span",
                    "detail": f"upper surface, {100 * x0:.0f}–{100 * x1:.0f} % chord"})
    if any(r.get("te_separation") for r in rows):
        ys = [r["y_over_S"] for r in rows if r.get("te_separation")]
        out.append({"what": "Trailing-edge separation", "where": f"{100 * min(ys):.0f}–{100 * max(ys):.0f} % of the semi-span",
                    "detail": "upper surface, last 15 % of chord (high local angle)"})
    low = [r for r in rows if r["re"] < 1e5]
    if low:
        out.append({"what": "Very low Re (below 10⁵)", "where": f"from {100 * min(r['y_over_S'] for r in low):.0f} % of the semi-span outward",
                    "detail": "laminar separation without reattachment possible; no RANS model is reliable here"})
    sw = max(g["sweep_le_deg"])
    if sw > 15:
        out.append({"what": "Spanwise flow (sweep)", "where": "swept panels", "detail": f"leading-edge sweep up to {sw:.0f}°: "
                    "the boundary layer drifts outboard; the tip stalls first at high angle"})
        if sw > 25 and max(r["re_normal"] for r in rows) > 1e6:
            out.append({"what": "Crossflow transition possible", "where": "swept leading edge",
                        "detail": "Λ > 25° and Re normal to the edge > 10⁶; XFOIL and LM without a crossflow term miss it"})
    if "cranked" in fm["labels"] or v.get("kinks_at_span_fraction"):
        ks = ", ".join(f"{100 * y / g['semi_span_m']:.0f} %" for y in g["y"][1:3])
        out.append({"what": "Kinks (panel breaks)", "where": f"{ks} of the semi-span", "detail": "local suction peak and a jump in the span loading"})
    out.append({"what": "Tip vortex and wake", "where": "tip; behind the whole trailing edge",
                "detail": f"strongest at low aspect ratio (here {g['aspect_ratio']:.1f})"})
    return out


def proposal(fm: dict) -> dict:
    rows = fm["strips"]
    res = [r["re"] for r in rows]
    lam = max((r.get("xtr_upper") or 0.0) for r in rows)
    bias = _drag_bias(rows)
    bub = [b for r in rows for b in (r.get("bubbles_upper") or []) + (r.get("bubbles_lower") or [])]
    notes = []
    if min(res) < 1e5:
        notes.append("Part of the span is below Re 10⁵: results there are indicative with any RANS model; "
                     "use scale-resolving simulation (ILES/LES) as a reference if that region matters.")
    if lam >= 0.10 and min(res) < 3.5e6:
        model = "Transition model: Langtry–Menter γ-Reθ with SST (SU2) for drag; SA fully turbulent (ADflow) for mesh studies and as a bound"
        why = (f"laminar flow reaches {100 * lam:.0f} % of chord, so where it turns turbulent sets the drag"
               + (f"; fully turbulent SA would raise the profile drag by about {100 * bias:+.0f} % (XFOIL strips)" if bias is not None else ""))
    else:
        model = "Spalart–Allmaras, fully turbulent (ADflow)"
        why = "transition sits close to the nose everywhere; a laminar run changes little"
    if bub:
        x0, x1 = min(b[0] for b in bub), max(b[1] for b in bub)
        notes.append(f"Laminar bubbles at {100 * x0:.0f}–{100 * x1:.0f} % chord: cluster chordwise cells there "
                     "(a transition model needs about 2 × the chordwise cells of fully turbulent RANS) and keep y+ ≤ 1.")
    if any(p["what"].startswith("Crossflow") for p in fm["phenomena"]):
        notes.append("Swept leading edge: add a crossflow-sensitive transition option, or treat the inboard transition as uncertain.")
    return {"model": model, "why": why, "sa_drag_bias": bias, "notes": notes}


# ---------------------------------------------------------------------------------------------
def plot(fm: dict, path, title: str | None = None) -> None:
    import logging
    import matplotlib
    matplotlib.use("Agg")
    logging.getLogger("matplotlib").setLevel(logging.ERROR)
    import matplotlib.pyplot as plt
    import matplotlib.patches as mp
    import textwrap

    g, rows = fm["geometry"], fm["strips"]
    S = g["semi_span_m"]
    fig = plt.figure(figsize=(13, 6.2), dpi=110)
    ax = fig.add_axes((0.06, 0.24, 0.50, 0.68))
    tx = fig.add_axes((0.60, 0.04, 0.39, 0.90)); tx.axis("off")
    ys = np.array([r["y"] for r in rows])
    edges = np.concatenate([[0.0], 0.5 * (ys[1:] + ys[:-1]), [S]])
    yy, xl, ch = np.array(g["y"]), np.array(g["x_le"]), np.array(g["chord"])
    for (e0, e1), r in zip(zip(edges[:-1], edges[1:]), rows):
        x0, x1 = np.interp([e0, e1], yy, xl)
        c0, c1 = np.interp([e0, e1], yy, ch)
        ax.add_patch(mp.Polygon([(e0, -x0), (e1, -x1), (e1, -(x1 + c1)), (e0, -(x0 + c0))], closed=True,
                                fc=band(r["re"])[1], ec="white", lw=0.4, alpha=0.85))
    # transition line (upper surface) and bubbles
    t = [(r["y"], r["x_le"] + r["xtr_upper"] * r["chord"]) for r in rows if r.get("xtr_upper") is not None]
    if t:
        ax.plot([a for a, _ in t], [-b for _, b in t], color="white", lw=2.6)
        ax.plot([a for a, _ in t], [-b for _, b in t], color="#1F2A33", lw=1.4, ls="--", label="upper-surface transition (free)")
    for r in rows:
        for b0, b1 in r.get("bubbles_upper") or []:
            ax.plot([r["y"]] * 2, [-(r["x_le"] + b0 * r["chord"]), -(r["x_le"] + b1 * r["chord"])], color="#7A1F1F", lw=4,
                    solid_capstyle="butt")
        if r.get("te_separation"):
            ax.plot(r["y"], -(r["x_le"] + 0.95 * r["chord"]), marker="x", color="#7A1F1F", ms=7, mew=2)
    ax.plot(yy, -xl, color="#1F2A33", lw=1); ax.plot(yy, -(xl + ch), color="#1F2A33", lw=1)
    ax.plot([0, 0], [0, -ch[0]], color="#1F2A33", lw=1); ax.plot([S, S], [-xl[-1], -(xl[-1] + ch[-1])], color="#1F2A33", lw=1)
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("y along the semi-span [m]  (root at 0; the other half is the mirror)")
    ax.set_ylabel("x [m]  (flight direction up)")
    ax.grid(alpha=0.2)
    h = [mp.Patch(color=c, label=f"Re {n}") for _, _, n, c in BANDS]
    h += [plt.Line2D([], [], color="#1F2A33", ls="--", label="transition, upper surface"),
          plt.Line2D([], [], color="#7A1F1F", lw=4, label="laminar bubble, upper surface"),
          plt.Line2D([], [], color="#7A1F1F", marker="x", ls="none", label="trailing-edge separation")]
    fig.legend(handles=h, loc="lower left", bbox_to_anchor=(0.04, 0.0), ncol=4, fontsize=7.5, frameon=False)
    c = fm["conditions"]
    ax.set_title(title or f"{fm['family']} → {fm['type']}", loc="left", fontsize=11, fontweight="bold")
    lines = [f"Family: {fm['family']}    Type (our rules): {fm['type']}",
             f"Full span b {g['full_span_m']:.2f} m, root chord {g['root_chord_m']:.2f} m, AR {g['aspect_ratio']:.1f}",
             f"Sections b0–b3: {', '.join(g['airfoils'])}",
             f"V {c['speed_m_s']:g} m/s at {c['altitude_m']:.0f} m, Mach {c['mach']:.3f}, α {c['alpha_deg']:g}° (+ local twist)",
             "", "What the flow will do:"]
    for p in fm["phenomena"]:
        lines += textwrap.wrap(f"• {p['what']} — {p['where']}: {p['detail']}", 78, subsequent_indent="   ")
    m = fm["model"]
    lines += ["", "Proposed model:"] + textwrap.wrap(m["model"], 78) + textwrap.wrap(f"Why: {m['why']}", 78)
    for n in m["notes"]:
        lines += textwrap.wrap(f"• {n}", 78, subsequent_indent="   ")
    lines += [""] + textwrap.wrap("Limits: " + fm["limits"], 84)
    tx.text(0, 1, "\n".join(lines), va="top", ha="left", fontsize=7.6, family="DejaVu Sans", color="#1F2A33")
    fig.savefig(path)
    plt.close(fig)
