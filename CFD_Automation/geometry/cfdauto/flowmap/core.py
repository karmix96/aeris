"""Flow map of one wing: what the flow will do, where, and which model to use.

    from cfdauto.flowmap.core import flow_map, sweep_sheet, plot, plot_sheet
    fm = flow_map(spec, vec, tailless=True, speed_m_s=25, altitude_m=1000, alpha_deg=3)
    sh = sweep_sheet(spec, vec, machs=[0.05, 0.1, 0.15], alphas=[0, 4, 8])

Steps
  1. Classify: family (input: tailless or conventional) and type (our rules, labels.classify).
  2. Strips along the semi-span (engine.wing_strips): chord, twist, sweep, section.
  3. Local Reynolds number on the chord, Re = (rho/mu) V c (Stage 0 air), and Mach.
  4. 2-D answers per strip, free transition and tripped at 1 % chord: from the section tables
     (default: the same numbers as the flow dataset) or from direct XFOIL runs (sections without
     tables, or method="xfoil").
  5. Wing metrics (engine.metrics): the drag change of fully turbulent SA, laminar run, bubbles,
     trailing-edge separation, Re bands.
  6. Phenomena and a proposed model by the dataset's rule (engine.category), where the wing sits in the
     flow dataset of its type, and the other section sets of its type at the same condition.

Limits (said in every output): 2-D strips; no induced angle (the local angle is too high toward the
tip), no crossflow transition on swept wings, no 3-D relief of bubbles; e^N with N_crit 9 (quiet air).
It shows where to look and what to expect, not the 3-D answer.
"""

from __future__ import annotations

import json
import math

import numpy as np

from ..geometry.labels import label
from ..geometry.measure import measure, table_from_stations
from ..geometry.params import GEOMETRY_ROOT, TypeSpec, resolve
from ..geometry.sections import build_wing_sections
from . import engine, tables, xfoil

RHO_MU = engine.RHO_MU
BANDS = engine.BANDS
LIMITS = ("2-D strips (XFOIL e^N, N_crit 9 = quiet air): no induced angle (the local angle is too high toward the tip), "
          "no crossflow transition on swept wings, no 3-D relief of bubbles. Where to look, not the 3-D answer.")
SUMMARY = GEOMETRY_ROOT / "docs" / "flow_summary.json"
MODELS = {
    0: "Spalart–Allmaras, fully turbulent (ADflow)",
    1: "Transition model: Langtry–Menter γ-Reθ with SST (SU2) for drag; SA fully turbulent (ADflow) for mesh studies and as a bound",
    2: "Transition model: Langtry–Menter γ-Reθ with SST (SU2) for drag; SA fully turbulent (ADflow) for mesh studies and as a bound",
    3: "Beyond 2-D stall: the strips cannot judge; expect separated flow (URANS or hybrid RANS–LES if this condition matters)",
}


def rho_over_mu(alt_m: float) -> float:
    return float(engine.rho_over_mu(alt_m))


def sound_speed(alt_m: float) -> float:
    return float(engine.sound_speed(alt_m))


def band(re_: float) -> tuple[str, str]:
    return engine.band(re_)


def strips(pf, stations, n_per_panel: int = 2) -> list[dict]:
    """Strip positions with chord, LE position, twist, sweep and the blended section (geometry only)."""
    out = []
    for y in engine.strip_positions(pf, n_per_panel):
        k = min(int(np.searchsorted(pf.y, y, side="right")) - 1, 2)
        a, b = stations[k], stations[k + 1]
        s = (y - a.y) / (b.y - a.y)
        out.append({"y": float(y), "panel": k, "s": float(s), "chord": a.chord + s * (b.chord - a.chord),
                    "x_le": a.x_le + s * (b.x_le - a.x_le), "twist": a.twist_deg + s * (b.twist_deg - a.twist_deg),
                    "sweep": float(pf.sweep_le_deg[k]), "airfoil": a.airfoil.blend(b.airfoil, s) if s > 1e-9 else a.airfoil})
    return out


# --------------------------------------------------------------------------------------------- 2-D answers
def _direct(ws: engine.WingStrips, mach: float, alt_m: float, alpha_deg: float, ncrit: float) -> dict:
    """Direct XFOIL runs per strip, in the same layout as engine.evaluate (one condition)."""
    v = mach * sound_speed(alt_m)
    re_ = rho_over_mu(alt_m) * v * ws.chord
    al = alpha_deg + ws.twist
    n = len(ws.y)
    free = {f: np.full((n, 1), np.nan) for f in tables.FIELDS}
    trip = {f: np.full((n, 1), np.nan) for f in tables.FIELDS}
    for i in range(n):
        pts = ws.airfoil(i).selig()
        for out, tripped in ((free, False), (trip, True)):
            d = xfoil.run(pts, float(re_[i]), float(al[i]), tripped, mach, ncrit if not tripped else xfoil.NCRIT)
            for f in tables.FIELDS:
                if d and d.get(f) is not None:
                    out[f][i, 0] = float(d[f])
    free["re_clamped"] = trip["re_clamped"] = np.zeros((n, 1), bool)
    return {"re": re_[:, None], "alpha_local": al[:, None], "alpha_induced": np.zeros(1), "free": free, "trip": trip,
            "mach": np.array([mach]), "alt_m": np.array([alt_m]), "alpha_root": np.array([alpha_deg]), "speed": np.array([v])}


def _empty(ws: engine.WingStrips, mach: float, alt_m: float, alpha_deg: float) -> dict:
    v = mach * sound_speed(alt_m)
    n = len(ws.y)
    nan = {f: np.full((n, 1), np.nan) for f in tables.FIELDS} | {"re_clamped": np.zeros((n, 1), bool)}
    return {"re": (rho_over_mu(alt_m) * v * ws.chord)[:, None], "alpha_local": (alpha_deg + ws.twist)[:, None],
            "alpha_induced": np.zeros(1), "free": nan, "trip": dict(nan), "mach": np.array([mach]),
            "alt_m": np.array([alt_m]), "alpha_root": np.array([alpha_deg]), "speed": np.array([v])}


def choose_method(ws: engine.WingStrips, method: str, ncrit: float, run_xfoil: bool = True) -> str:
    if not run_xfoil:
        return "none"
    if method == "auto":
        return "tables" if engine.tables_cover(ws, ncrit) else ("xfoil" if xfoil.available() else "none")
    if method == "tables" and not engine.tables_cover(ws, ncrit):
        raise FileNotFoundError("section tables missing for " + ", ".join(sorted(engine.sections_needed(ws)))
                                + ": run python -m cfdauto.flowmap.tables --build, or use method='xfoil'")
    return method


def _val(x) -> float | None:
    x = float(x)
    return x if math.isfinite(x) else None


# --------------------------------------------------------------------------------------------- one wing
def flow_map(spec: TypeSpec, vec: dict, tailless: bool, speed_m_s: float | None = None, altitude_m: float = 0.0,
             alpha_deg: float = 2.0, airfoils: list[str] | None = None, run_xfoil: bool = True, method: str = "auto",
             mach: float | None = None, ncrit: float = 9.0, n_per_panel: int = 2, induced: bool = False,
             compare_sets: bool = True) -> dict:
    """Flow map at one condition. Give speed_m_s or mach. method: auto (tables when every section has
    one, else direct XFOIL), tables, xfoil. ncrit 5 / 11 use the Mach 0.1 tables (sensitivity only)."""
    a_snd = sound_speed(altitude_m)
    if speed_m_s is None:
        if mach is None:
            raise ValueError("give speed_m_s or mach")
        speed_m_s = mach * a_snd
    M = speed_m_s / a_snd
    vec = dict(vec)
    if airfoils:
        vec["airfoils"] = list(airfoils)
    vec = resolve(spec, vec)
    ws = engine.wing_strips(spec, vec, None, n_per_panel)
    _, st_te = build_wing_sections(spec, vec, _te_rule())
    labels, values = label(measure(table_from_stations(st_te), st_te), tailless)
    meth = choose_method(ws, method, ncrit, run_xfoil)
    if meth == "tables":
        r = engine.evaluate(ws, [M], [altitude_m], [alpha_deg], ncrit=ncrit, induced=induced,
                            mach_in_tables=None if ncrit == 9.0 else 0.1)
    elif meth == "xfoil":
        r = _direct(ws, M, altitude_m, alpha_deg, ncrit)
    else:
        r = _empty(ws, M, altitude_m, alpha_deg)
    met = {k: (v[0] if np.ndim(v) else v) for k, v in engine.metrics(ws, r).items()}
    rows = _rows(ws, r, meth != "none")
    pf = ws.pf
    fm = {"family": labels[0], "type": labels[1], "labels": labels, "generator_type": spec.name, "method": meth,
          "assumptions": {"ncrit": ncrit, "induced_angle": induced, "strips_per_panel": n_per_panel,
                          "tables_mach": (0.1 if (meth == "tables" and ncrit != 9.0) else None)},
          "conditions": {"speed_m_s": speed_m_s, "altitude_m": altitude_m, "alpha_deg": alpha_deg, "mach": M,
                         "rho_over_mu": rho_over_mu(altitude_m)},
          "geometry": {"full_span_m": 2 * pf.semi_span, "semi_span_m": pf.semi_span, "root_chord_m": float(pf.chord[0]),
                       "tip_chord_m": float(pf.chord[-1]), "mean_chord_m": pf.area() / (2 * pf.semi_span),
                       "y": pf.y.tolist(), "x_le": pf.x_le.tolist(), "chord": pf.chord.tolist(),
                       "sweep_le_deg": pf.sweep_le_deg.tolist(), "airfoils": [s.airfoil.name for s in ws.stations],
                       "aspect_ratio": vec["aspect_ratio"]},
          "strips": rows, "metrics": {k: (_val(v) if isinstance(v, (float, np.floating)) else
                                          (bool(v) if isinstance(v, (bool, np.bool_)) else int(v))) for k, v in met.items()},
          "limits": LIMITS}
    if meth == "none":
        fm["metrics"]["category"] = None
    fm["level_flight"] = level_flight(fm)
    fm["phenomena"] = phenomena(fm, values)
    fm["model"] = proposal(fm)
    fm["dataset_position"] = dataset_position(fm)
    if compare_sets and meth == "tables" and ncrit == 9.0 and not induced:
        fm["section_sets"] = other_sets(spec, vec, M, altitude_m, alpha_deg, n_per_panel)
    return fm


def _rows(ws: engine.WingStrips, r: dict, have: bool) -> list[dict]:
    f, t = r["free"], r["trip"]
    out = []
    for i in range(len(ws.y)):
        re_ = float(r["re"][i, 0])
        row = {"y": float(ws.y[i]), "y_over_S": float(ws.y[i] / ws.semi_span), "chord": float(ws.chord[i]),
               "x_le": float(ws.x_le[i]), "twist": float(ws.twist[i]), "sweep": float(ws.sweep[i]),
               "section": ws.section_name(i), "re": re_, "re_normal": re_ * math.cos(math.radians(ws.sweep[i])),
               "band": band(re_)[0], "alpha_local": float(r["alpha_local"][i, 0])}
        if have:
            def g(d, k):
                return _val(d[k][i, 0])
            bu, bl = g(f, "bub_u"), g(f, "bub_l")
            row |= {"cl": g(f, "cl"), "cd_free": g(f, "cd"), "cd_tripped": g(t, "cd"), "xtr_upper": g(f, "xtr_top"),
                    "xtr_lower": g(f, "xtr_bot"),
                    "bubbles_upper": [(g(f, "bub_u_s"), g(f, "bub_u_e"))] if (bu or 0) >= 0.5 and g(f, "bub_u_s") is not None else [],
                    "bubbles_lower": [(g(f, "bub_l_s"), g(f, "bub_l_e"))] if (bl or 0) >= 0.5 and g(f, "bub_l_s") is not None else [],
                    "te_separation": bool((g(f, "sep_u") or 0) >= 0.5), "te_separation_x": g(f, "sep_u_x"),
                    "converged": g(f, "cd") is not None and g(t, "cd") is not None,
                    "re_clamped": bool(f["re_clamped"][i, 0])}
        out.append(row)
    return out


def _te_rule():
    from ..geometry.params import load_config
    return load_config().te


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
        out.append({"what": "Laminar run, then transition", "where": "upper surface, every converged strip",
                    "detail": f"turns turbulent at {100 * mn['xtr_upper']:.0f}–{100 * mx['xtr_upper']:.0f} % chord"})
    bub = [(r, b) for r in rows for b in r.get("bubbles_upper") or []]
    if bub:
        y0, y1 = min(r["y_over_S"] for r, _ in bub), max(r["y_over_S"] for r, _ in bub)
        x0, x1 = min(b[0] for _, b in bub), max(b[1] for _, b in bub)
        out.append({"what": "Laminar separation bubble", "where": f"{100 * y0:.0f}–{100 * y1:.0f} % of the semi-span",
                    "detail": f"upper surface, {100 * x0:.0f}–{100 * x1:.0f} % chord"})
    if any(r.get("te_separation") for r in rows):
        ys = [r["y_over_S"] for r in rows if r.get("te_separation")]
        xs = [r["te_separation_x"] for r in rows if r.get("te_separation") and r.get("te_separation_x") is not None]
        out.append({"what": "Trailing-edge separation", "where": f"{100 * min(ys):.0f}–{100 * max(ys):.0f} % of the semi-span",
                    "detail": f"upper surface, from {100 * min(xs):.0f} % chord to the edge" if xs else "upper surface"})
    nc = [r for r in rows if "converged" in r and not r["converged"]]
    if nc:
        out.append({"what": "No converged 2-D answer (beyond 2-D stall)",
                    "where": f"{len(nc)} of {len(rows)} strips, {100 * min(r['y_over_S'] for r in nc):.0f}–"
                             f"{100 * max(r['y_over_S'] for r in nc):.0f} % of the semi-span",
                    "detail": "local angle past the section's 2-D stall: expect separated flow there"})
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
    """The dataset's rule (engine.category): SA when fully turbulent SA changes the profile drag by
    under 10 %, the upper surface turns turbulent near the nose (mean laminar run under 20 % chord) and no
    strip is below Re 1e5; a transition model otherwise; beyond 2-D stall when under half the span converges."""
    m, rows = fm["metrics"], fm["strips"]
    cat, bias = m.get("category"), m.get("sa_bias")
    notes = []
    if cat is None:
        return {"model": "Not judged: no 2-D answers (build the section tables or install XFOIL)", "why": "geometry and Re only",
                "category": None, "sa_drag_bias": None, "notes": notes}
    lam = max((r.get("xtr_upper") or 0.0) for r in rows)
    if cat == 0:
        why = (f"fully turbulent SA changes the profile drag by only {100 * bias:+.0f} % (within ±10 %) and the upper surface turns "
               f"turbulent near the nose (mean laminar run {100 * m['lam_upper']:.0f} % of chord): transition matters little")
    elif cat in (1, 2) and abs(bias) < engine.SA_OK:
        why = (f"the profile drag of fully turbulent SA matches ({100 * bias:+.0f} %) only by coincidence: laminar flow reaches up to "
               f"{100 * lam:.0f} % of chord, with bubbles, so transition still shapes the pressure field")
    elif cat in (1, 2):
        why = (f"fully turbulent SA would change the profile drag by {100 * bias:+.0f} % (laminar flow reaches up to "
               f"{100 * lam:.0f} % of chord), so where it turns turbulent sets the drag")
    else:
        why = f"only {100 * m['conv_span']:.0f} % of the semi-span has a converged 2-D answer at this angle"
    if m.get("span_re_lt_1e5", 0) > 0:
        notes.append(f"{100 * m['span_re_lt_1e5']:.0f} % of the semi-span is below Re 10⁵: results there are indicative with any "
                     "RANS model; use scale-resolving simulation (ILES/LES) as a reference if that region matters.")
    bub = [b for r in rows for b in (r.get("bubbles_upper") or []) + (r.get("bubbles_lower") or [])]
    if bub:
        x0, x1 = min(b[0] for b in bub), max(b[1] for b in bub)
        notes.append(f"Laminar bubbles at {100 * x0:.0f}–{100 * x1:.0f} % chord: cluster chordwise cells there "
                     "(a transition model needs about 2 × the chordwise cells of fully turbulent RANS) and keep y+ ≤ 1.")
    if any(p["what"].startswith("Crossflow") for p in fm["phenomena"]):
        notes.append("Swept leading edge: add a crossflow-sensitive transition option, or treat the inboard transition as uncertain.")
    if not fm["assumptions"]["induced_angle"]:
        notes.append(f"Local angles have no induced angle, so they are too high toward the tip (more so at low AR, here "
                     f"{fm['geometry']['aspect_ratio']:.1f}); the dataset checks show what that changes.")
    if any(r.get("re_clamped") for r in rows):
        notes.append("Some strips are outside the tables' Re range (1.5 × 10⁴ – 6 × 10⁶): their values are taken at the edge.")
    return {"model": MODELS[cat], "why": why, "category": engine.CATEGORIES[cat], "sa_drag_bias": bias, "notes": notes}


# --------------------------------------------------------------------------------------------- context
def level_flight(fm: dict) -> dict | None:
    """The wing loading this condition carries in level flight (W/S = CL_3D q) against real wings of the
    same full span and family (configs/flowmap.yaml, level_flight)."""
    from .dataset import load_flow_config, wing_loading_band
    ws = fm["metrics"].get("wing_loading")
    if ws is None:
        return None
    lo, hi = wing_loading_band(fm["geometry"]["full_span_m"], fm["family"], load_flow_config())
    return {"wing_loading_n_m2": ws, "cl3d": fm["metrics"].get("cl3d"), "real_band_n_m2": [float(lo), float(hi)],
            "ok": bool(lo <= ws <= hi)}


def _summary() -> dict | None:
    try:
        return json.loads(SUMMARY.read_text())
    except (OSError, ValueError):
        return None


def dataset_position(fm: dict) -> dict | None:
    """Percentile of the wing's main metrics among the focus wings of its generator type (realistic
    speeds, all section sets, angles and altitudes of the flow dataset)."""
    s = _summary()
    if not s or fm["generator_type"] not in s or fm["method"] == "none":
        return None
    out = {}
    for k, q in s[fm["generator_type"]].items():
        v = fm["metrics"].get(k)
        if v is None:
            continue
        ps = sorted((int(n[1:]), x) for n, x in q.items())
        xs = np.array([x for _, x in ps]); pc = np.array([p for p, _ in ps], float)
        if np.ptp(xs) == 0:
            p = 50.0
        elif v <= xs[0]:
            p = float(pc[0]) if v == xs[0] else 2.5
        elif v >= xs[-1]:
            p = float(pc[-1]) if v == xs[-1] else 97.5
        else:
            p = float(np.interp(v, xs, pc))
        out[k] = {"value": v, "percentile": p, "median": float(q["q50"])}
    return out


def other_sets(spec: TypeSpec, vec: dict, mach: float, alt_m: float, alpha_deg: float, n_per_panel: int = 2) -> list[dict]:
    """The section sets of the generator type (configs/flowmap.yaml) at the same condition."""
    from .dataset import load_flow_config
    sets = load_flow_config()["section_sets"].get(spec.name, [])
    out = []
    for st in sets:
        ws = engine.wing_strips(spec, vec, st["sections"], n_per_panel)
        if not engine.tables_cover(ws):
            continue
        m = engine.metrics(ws, engine.evaluate(ws, [mach], [alt_m], [alpha_deg]))
        out.append({"id": st["id"], "label": st["label"], "sections": st["sections"],
                    **{k: _val(m[k][0]) for k in ("sa_bias", "lam_upper", "bubble_span", "te_sep_span", "conv_span")},
                    "category": engine.CATEGORIES[int(m["category"][0])]})
    return out


def sweep_sheet(spec: TypeSpec, vec: dict, machs, alphas, altitude_m: float = 0.0, airfoils: list[str] | None = None,
                ncrit: float = 9.0, n_per_panel: int = 2) -> dict:
    """One wing over a grid of Mach x root angle (section tables): the main metrics as 2-D arrays."""
    ws = engine.wing_strips(spec, vec, airfoils, n_per_panel)
    choose_method(ws, "tables", ncrit)
    M, A = np.meshgrid(np.asarray(machs, float), np.asarray(alphas, float), indexing="ij")
    r = engine.evaluate(ws, M.ravel(), np.full(M.size, altitude_m), A.ravel(), ncrit=ncrit,
                        mach_in_tables=None if ncrit == 9.0 else 0.1)
    m = engine.metrics(ws, r)
    keys = ("sa_bias", "lam_upper", "bubble_span", "te_sep_span", "conv_span", "re_min", "re_max", "span_re_lt_1e5", "category",
            "wing_loading")
    from ..geometry.params import FAMILY_OF
    from .dataset import load_flow_config, wing_loading_band
    lo, hi = wing_loading_band(2 * ws.semi_span, FAMILY_OF[spec.name], load_flow_config())
    wl = np.asarray(m["wing_loading"], float).reshape(M.shape)
    level = (wl >= lo) & (wl <= hi) & (np.asarray(m["conv_span"]).reshape(M.shape) >= 0.5)
    return {"machs": list(map(float, machs)), "alphas": list(map(float, alphas)), "altitude_m": altitude_m,
            "airfoils": [s.airfoil.name for s in ws.stations], "generator_type": spec.name,
            "full_span_m": 2 * ws.semi_span, "wing_loading_band": [float(lo), float(hi)], "level_flight": level.tolist(),
            **{k: np.asarray(m[k], float).reshape(M.shape).tolist() for k in keys}}


# --------------------------------------------------------------------------------------------- figures
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
    fig = plt.figure(figsize=(13, 6.6), dpi=110)
    ax = fig.add_axes((0.06, 0.26, 0.50, 0.66))
    tx = fig.add_axes((0.60, 0.03, 0.39, 0.92)); tx.axis("off")
    ys = np.array([r["y"] for r in rows])
    edges = np.concatenate([[0.0], 0.5 * (ys[1:] + ys[:-1]), [S]])
    yy, xl, ch = np.array(g["y"]), np.array(g["x_le"]), np.array(g["chord"])
    for (e0, e1), r in zip(zip(edges[:-1], edges[1:]), rows):
        ye = np.array([e0] + [b for b in yy[1:-1] if e0 < b < e1] + [e1])      # follow the planform across a break
        xe, ce = np.interp(ye, yy, xl), np.interp(ye, yy, ch)
        poly = [(a, -b) for a, b in zip(ye, xe)] + [(a, -(b + c)) for a, b, c in zip(ye[::-1], xe[::-1], ce[::-1])]
        ax.add_patch(mp.Polygon(poly, closed=True, fc=band(r["re"])[1], ec="white", lw=0.4, alpha=0.85,
                                hatch="//" if r.get("converged") is False else None))
    t = [(r["y"], r["x_le"] + r["xtr_upper"] * r["chord"]) for r in rows if r.get("xtr_upper") is not None]
    if t:
        ax.plot([a for a, _ in t], [-b for _, b in t], color="white", lw=2.6)
        ax.plot([a for a, _ in t], [-b for _, b in t], color="#1F2A33", lw=1.4, ls="--")
    for r in rows:
        for b0, b1 in r.get("bubbles_upper") or []:
            ax.plot([r["y"]] * 2, [-(r["x_le"] + b0 * r["chord"]), -(r["x_le"] + b1 * r["chord"])], color="#7A1F1F", lw=4,
                    solid_capstyle="butt")
        if r.get("te_separation"):
            xs = r.get("te_separation_x") or 0.95
            ax.plot([r["y"]] * 2, [-(r["x_le"] + xs * r["chord"]), -(r["x_le"] + r["chord"])], color="#7A1F1F", lw=1.6, ls=":")
            ax.plot(r["y"], -(r["x_le"] + r["chord"]), marker="x", color="#7A1F1F", ms=7, mew=2)
    ax.plot(yy, -xl, color="#1F2A33", lw=1); ax.plot(yy, -(xl + ch), color="#1F2A33", lw=1)
    ax.plot([0, 0], [0, -ch[0]], color="#1F2A33", lw=1); ax.plot([S, S], [-xl[-1], -(xl[-1] + ch[-1])], color="#1F2A33", lw=1)
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("y along the semi-span [m]  (root at 0; the other half is the mirror)")
    ax.set_ylabel("x [m]  (flight direction up)")
    ax.grid(alpha=0.2)
    h = [mp.Patch(color=c, label=f"Re {n}") for _, _, n, c in BANDS]
    h += [plt.Line2D([], [], color="#1F2A33", ls="--", label="transition, upper surface"),
          plt.Line2D([], [], color="#7A1F1F", lw=4, label="laminar bubble, upper surface"),
          plt.Line2D([], [], color="#7A1F1F", marker="x", ls=":", label="trailing-edge separation"),
          mp.Patch(fc="white", ec="#1F2A33", hatch="//", label="no 2-D answer (stall)")]
    fig.legend(handles=h, loc="lower left", bbox_to_anchor=(0.04, 0.0), ncol=4, fontsize=7.5, frameon=False)
    c, m = fm["conditions"], fm["model"]
    ax.set_title(title or f"{fm['family']} → {fm['type']}", loc="left", fontsize=11, fontweight="bold")
    lines = [f"Family: {fm['family']}    Type (our rules): {fm['type']}    2-D answers: {fm['method']}",
             f"Full span b {g['full_span_m']:.2f} m, root chord {g['root_chord_m']:.2f} m, AR {g['aspect_ratio']:.1f}",
             f"Sections b0–b3: {', '.join(g['airfoils'])}",
             f"V {c['speed_m_s']:.3g} m/s at {c['altitude_m']:.0f} m, Mach {c['mach']:.3f}, α {c['alpha_deg']:g}° (+ local twist)",
             "", "What the flow will do:"]
    for p in fm["phenomena"]:
        lines += textwrap.wrap(f"• {p['what']} — {p['where']}: {p['detail']}", 78, subsequent_indent="   ")
    lines += ["", "Proposed model:"] + textwrap.wrap(m["model"], 78) + textwrap.wrap(f"Why: {m['why']}", 78)
    for n in m["notes"]:
        lines += textwrap.wrap(f"• {n}", 78, subsequent_indent="   ")
    lf = fm.get("level_flight")
    if lf:
        lines += [""] + textwrap.wrap(
            f"Level flight here carries W/S {lf['wing_loading_n_m2']:.0f} N/m² (CL ≈ {lf['cl3d']:.2f}); real wings of this span: "
            f"{lf['real_band_n_m2'][0]:.0f}–{lf['real_band_n_m2'][1]:.0f} N/m² → "
            + ("a realistic condition." if lf["ok"] else "not a realistic level-flight condition."), 78)
    dp = fm.get("dataset_position")
    if dp and "sa_bias" in dp:
        lines += [""] + textwrap.wrap(
            "SA drag error = profile drag of fully turbulent CFD (SA) ÷ profile drag of the real flow (free transition) − 1, "
            "from 2-D XFOIL strips: + means SA gives too much drag.", 78)
        lines += textwrap.wrap(
            f"Among {fm['generator_type']} wings of the flow dataset: SA drag error at percentile {dp['sa_bias']['percentile']:.0f} "
            f"(median {100 * dp['sa_bias']['median']:+.0f} %)"
            + (f", laminar run at percentile {dp['lam_upper']['percentile']:.0f}" if "lam_upper" in dp else ""), 78)
    if fm.get("section_sets"):
        lines += ["", "Other section sets, same condition (SA drag error / bubble span):"]
        for s in fm["section_sets"]:
            b = "–" if s["sa_bias"] is None else f"{100 * s['sa_bias']:+.0f} %"
            lines.append(f"  {s['id']}  {s['label']}: {b} / {100 * (s['bubble_span'] or 0):.0f} %")
    lines += [""] + textwrap.wrap("Limits: " + fm["limits"], 84)
    tx.text(0, 1, "\n".join(lines), va="top", ha="left", fontsize=7.2, family="DejaVu Sans", color="#1F2A33")
    fig.savefig(path)
    plt.close(fig)


def plot_sheet(sh: dict, path, title: str = "") -> None:
    """Four maps over Mach x root angle: SA drag error with the model category, laminar run, bubble
    span and trailing-edge separation span."""
    import logging
    import matplotlib
    matplotlib.use("Agg")
    logging.getLogger("matplotlib").setLevel(logging.ERROR)
    import matplotlib.pyplot as plt
    M, A = np.array(sh["machs"]), np.array(sh["alphas"])
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.9), dpi=110, sharey=True)
    for ax, (k, lab, cmap, lo, hi) in zip(axes, (("sa_bias", "SA drag error [%]", "magma_r", 0, 120),
                                                  ("lam_upper", "laminar run, upper [% chord]", "viridis", 0, 100),
                                                  ("bubble_span", "span with a bubble [%]", "Reds", 0, 100),
                                                  ("te_sep_span", "span with TE separation [%]", "Purples", 0, 100))):
        z = 100 * np.array(sh[k], float)
        lvl = np.array(sh.get("level_flight", np.ones(z.shape, bool)), bool)
        im = ax.pcolormesh(M, A, z.T, cmap=cmap, vmin=lo, vmax=hi, shading="nearest")
        for i, mm in enumerate(M):
            for j, aa in enumerate(A):
                v = z[i, j]
                ax.text(mm, aa, "–" if not np.isfinite(v) else f"{v:.0f}", ha="center", va="center", fontsize=7, zorder=3,
                        color="white" if np.isfinite(v) and (v - lo) / (hi - lo) > 0.55 and lvl[i, j] else "#1F2A33")
        if k == "sa_bias":
            cat = np.array(sh["category"], float)
            for i, mm in enumerate(M):
                for j, aa in enumerate(A):
                    if cat[i, j] == 0:
                        ax.add_patch(plt.Rectangle((mm - 0.45 * np.diff(M).min() if len(M) > 1 else mm - 0.01,
                                                    aa - 0.45 * (np.diff(A).min() if len(A) > 1 else 1)),
                                                   0.9 * (np.diff(M).min() if len(M) > 1 else 0.02),
                                                   0.9 * (np.diff(A).min() if len(A) > 1 else 2), fill=False, ec="#2E8B57", lw=2))
        lv = np.array(sh.get("level_flight", np.ones(z.shape, bool)), bool)
        dm = np.diff(M).min() if len(M) > 1 else 0.02
        da = np.diff(A).min() if len(A) > 1 else 2.0
        for i, mm in enumerate(M):
            for j, aa in enumerate(A):
                if not lv[i, j]:
                    ax.add_patch(plt.Rectangle((mm - dm / 2, aa - da / 2), dm, da, fc="#FFFFFF", ec="none", alpha=0.6, zorder=2))
        ax.set_title(lab, fontsize=9.5); ax.set_xlabel("flight Mach")
        fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    axes[0].set_ylabel("root angle [°]")
    fig.suptitle((title or f"{sh['generator_type']} wing, sections {', '.join(sh['airfoils'])}, {sh['altitude_m']:.0f} m")
                 + "  (green box: fully turbulent SA adequate; faded: not level flight at a real wing loading)",
                 x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path)
    plt.close(fig)
