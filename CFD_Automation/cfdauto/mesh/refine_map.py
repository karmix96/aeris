"""Where to refine, per wing: the transition and bubble positions from the Stage 1 flow-map engine.

This module asks the flow-map engine (2-D XFOIL section tables, strips along the semi-span, a uniform induced
angle) where the flow of ONE wing turns turbulent, where its bubbles sit and where it separates, at every
flight condition of a grid, and turns that into a band per strip and side: the envelope over the conditions
the mesh must serve, plus a margin. Two grids:

  - Re mode (similarity, decision 70; since 7 Nov 2026): Re on the mean chord (the four levels) × root angle,
    sea level, unit mean chord. The speed follows from Re (V = Re / (ρ/μ) / mean chord) and the 2-D tables are
    read at Mach 0.1. The map records its grid as "re".
  - Mach mode (the first approach, 3–6 Nov 2026; kept as the record): Mach × root angle × altitude, with the
    chords read as metres. At unit mean chord, Mach 0.03–0.13 at sea level is Re 7 × 10⁵ – 3 × 10⁶ on the mean
    chord: the two lowest Re levels (10⁵, 3 × 10⁵) are outside it. The map records its grid as "mach".

    from cfdauto.mesh.refine_map import RE_LEVELS, strip_map, envelope_band
    sm = strip_map("bwb", "reference", 0, res=RE_LEVELS)                    # Re mode
    band = envelope_band(sm, res=(1e5, 1e5), alphas=(-5, 8), margin=0.10)
    sm = strip_map("bwb", "reference", 0)                                   # Mach mode (first approach)
    band = envelope_band(sm, machs=(0.03, 0.13), alphas=(-5, 8), margin=0.10)

Bands. GENERIC_BAND is the first approach's generic band (upper 0–85 % c, lower 60–100 % c; Study 8's option B).
DECIDED_BAND is the band decided on 7 Nov 2026 (upper 0–85 % c, lower 0–100 % c; decision 74, option A;
configs/surface.yaml). A strip with no XFOIL answer falls back to the band of its mode: GENERIC_BAND in the
Mach mode, DECIDED_BAND in the Re mode.

Limits, inherited from the dataset: 2-D strips, e^N with N_crit 9 (calm air), a uniform (elliptic) induced
angle, no crossflow transition on swept panels, no 3-D relief of bubbles, no tip effects. Where a strip has
no XFOIL answer (beyond the section's 2-D stall, or a failed point) the band falls back to the generic one for
that strip. A strip whose local Re is outside the tables (1.5 × 10⁴ – 6 × 10⁶) is read at the table edge: the
field "re_clamped" marks it.
"""

from __future__ import annotations

import math

import numpy as np

GENERIC_BAND = {"upper": (0.0, 0.85), "lower": (0.60, 1.0)}     # first approach (record); Study 8's option B
DECIDED_BAND = {"upper": (0.0, 0.85), "lower": (0.0, 1.0)}      # decided 7 Nov 2026 (decision 74, option A)
MACHS = (0.03, 0.05, 0.08, 0.10, 0.13, 0.16, 0.20)
ALPHAS = tuple(float(a) for a in range(-5, 13))      # root angle; from -5 deg since 6 Nov 2026 (was -2)
ALTS = (0.0, 3000.0)
FOCUS_MACH = {"tailless": (0.03, 0.13), "conventional": (0.03, 0.20)}
RE_LEVELS = (1.0e5, 3.0e5, 1.5e6, 3.0e6)             # Re on the mean chord (decision 70; Stage 0 levels)
MACH_SIMILARITY = 0.1                                # Mach of the 2-D tables in the Re mode (decision 70)


def _nanlist(a) -> list:
    return [None if not math.isfinite(float(v)) else round(float(v), 4) for v in np.asarray(a).ravel()]


def grid_axis(sm: dict) -> str:
    """'re' for a map made in the Re mode (similarity), 'mach' for one made in the Mach mode (first approach)."""
    return "re" if "re" in sm["grid"] else "mach"


def strip_map(wing_type: str, set_name: str, index: int, machs=MACHS, alphas=ALPHAS, alts=ALTS,
              n_per_panel: int = 4, res=None) -> dict:
    """The flow answers of one wing on a condition grid, per strip: a plain dict (JSON-ready).

    res given: the Re mode (similarity, decision 70). The conditions are res (Re on the mean chord) × alphas at
    sea level; the speed is Re / (ρ/μ) / mean chord and the 2-D tables are read at Mach 0.1; machs and alts are
    not used. res None: the Mach mode (the first approach), machs × alphas × alts with the chords in metres."""
    from ..flowmap import engine
    from ..geometry.build import load_set
    from ..geometry.params import load_config, resolve

    cfg = load_config()
    spec = cfg.types[wing_type]
    vec = resolve(spec, load_set(wing_type, set_name)["vectors"][index])
    ws = engine.wing_strips(spec, vec, None, n_per_panel)
    pf = ws.pf
    c_mean = float(pf.area() / (2 * pf.semi_span))
    re_mode = res is not None
    first = np.asarray(res if re_mode else machs, float)
    alts = (0.0,) if re_mode else alts
    F, A, H = np.meshgrid(first, np.asarray(alphas, float), np.asarray(alts, float), indexing="ij")
    if re_mode:
        speed = F.ravel() / (engine.rho_over_mu(H.ravel()) * c_mean)
        mach = speed / engine.sound_speed(H.ravel())
        r = engine.evaluate(ws, mach, H.ravel(), A.ravel(), mach_in_tables=np.full(mach.shape, MACH_SIMILARITY))
    else:
        mach = F.ravel()
        r = engine.evaluate(ws, mach, H.ravel(), A.ravel())
    f = r["free"]
    tailless = wing_type in ("bwb", "flying_wing")
    if re_mode:
        grid = {"re": [float(v) for v in first], "alpha_deg": [float(v) for v in alphas], "alt_m": [0.0],
                "order": "re-major, then alpha, then altitude (C-order of the meshgrid)", "n": int(F.size),
                "mach_in_tables": MACH_SIMILARITY,
                "speed_m_s": [float(v / (engine.rho_over_mu(0.0) * c_mean)) for v in first],
                "note": ("similarity (decision 70): Re on the mean chord, sea level, unit mean chord; speed = Re / (ρ/μ) / "
                         "mean chord; the 2-D tables read at Mach 0.1")}
    else:
        grid = {"mach": [float(v) for v in machs], "alpha_deg": [float(v) for v in alphas], "alt_m": [float(v) for v in alts],
                "order": "mach-major, then alpha, then altitude (C-order of the meshgrid)",
                "n": int(F.size)}
    out = {
        "mode": "re" if re_mode else "mach",
        "wing": {"type": wing_type, "set": set_name, "index": index, "family": "tailless" if tailless else "conventional",
                 "semi_span_m": float(pf.semi_span), "mean_chord_m": c_mean,
                 "aspect_ratio": float(vec["aspect_ratio"]), "full_span_m": float(2 * pf.semi_span),
                 "stations": {"y": [float(v) for v in pf.y], "x_le": [float(v) for v in pf.x_le],
                              "chord": [float(v) for v in pf.chord], "sweep_le_deg": [float(v) for v in pf.sweep_le_deg],
                              "airfoils": [s.airfoil.name for s in ws.stations]}},
        "grid": grid,
        "strips": {"y": [float(v) for v in ws.y], "y_over_S": [float(v / ws.semi_span) for v in ws.y],
                   "chord": [float(v) for v in ws.chord], "x_le": [float(v) for v in ws.x_le],
                   "twist_deg": [float(v) for v in ws.twist], "sweep_deg": [float(v) for v in ws.sweep],
                   "section": [ws.section_name(i) for i in range(len(ws.y))]},
        "per_condition": {"alpha_induced_deg": _nanlist(r["alpha_induced"]), "cl_wing": _nanlist(r["cl_wing"]),
                          "re_mean": _nanlist(engine.rho_over_mu(H.ravel()) * mach * engine.sound_speed(H.ravel()) * c_mean)},
        "fields": {},                                   # each: n_strips × n_conditions, row-major, null = no answer
        "limits": ("2-D strips (XFOIL e^N, N_crit 9 = calm air) with a uniform induced angle: no crossflow transition on "
                   "swept panels, no 3-D relief of bubbles, no tip effects. Where to look, not the 3-D answer."
                   + (" Tables read at Mach 0.1 (decision 70)." if re_mode else "")),
    }
    out["fields"]["re"] = _nanlist(r["re"])
    out["fields"]["alpha_local"] = _nanlist(r["alpha_local"])
    for k_out, k_in in (("cl", "cl"), ("xtr_u", "xtr_top"), ("xtr_l", "xtr_bot"), ("bub_u_s", "bub_u_s"), ("bub_u_e", "bub_u_e"),
                        ("bub_l_s", "bub_l_s"), ("bub_l_e", "bub_l_e"), ("sep_u_x", "sep_u_x"), ("sep_l_x", "sep_l_x")):
        v = np.array(f[k_in], float)
        if k_out.startswith("bub_u"):
            v = np.where(np.asarray(f["bub_u"], float) >= 0.5, v, np.nan)
        if k_out.startswith("bub_l"):
            v = np.where(np.asarray(f["bub_l"], float) >= 0.5, v, np.nan)
        if k_out == "sep_u_x":
            v = np.where(np.asarray(f["sep_u"], float) >= 0.5, v, np.nan)
        if k_out == "sep_l_x":
            v = np.where(np.asarray(f["sep_l"], float) >= 0.5, v, np.nan)
        out["fields"][k_out] = _nanlist(v)
    out["fields"]["answered"] = [bool(math.isfinite(float(v))) for v in np.asarray(f["cd"], float).ravel()]
    out["fields"]["re_clamped"] = [bool(v) for v in np.asarray(f["re_clamped"], bool).ravel()]   # Re outside the tables
    out["shape"] = [int(len(ws.y)), int(F.size)]
    return out


def _field(sm: dict, name: str) -> np.ndarray:
    n, m = sm["shape"]
    return np.array([np.nan if v is None else v for v in sm["fields"][name]], float).reshape(n, m)


def condition_mask(sm: dict, machs: tuple[float, float] | None = None, alphas: tuple[float, float] | None = None,
                   alts=None, res: tuple[float, float] | None = None) -> np.ndarray:
    """The conditions of the map inside the given ranges (None: no limit on that axis). A map has one grid:
    give machs for a Mach-mode map, res (Re on the mean chord) for a Re-mode map."""
    g = sm["grid"]
    axis = grid_axis(sm)
    if (axis == "re" and machs is not None) or (axis == "mach" and res is not None):
        raise ValueError(f"this map's grid is {axis!r}: give {'res' if axis == 're' else 'machs'}, "
                         f"not {'machs' if axis == 're' else 'res'}")
    F, A, H = np.meshgrid(np.asarray(g[axis], float), np.asarray(g["alpha_deg"], float), np.asarray(g["alt_m"], float),
                          indexing="ij")
    F, A, H = F.ravel(), A.ravel(), H.ravel()
    keep = np.ones(F.shape, bool)
    if axis == "mach" and machs is not None:
        keep &= (F >= machs[0] - 1e-9) & (F <= machs[1] + 1e-9)
    if axis == "re" and res is not None:
        keep &= (F >= res[0] * (1 - 1e-9)) & (F <= res[1] * (1 + 1e-9))
    if alphas is not None:
        keep &= (A >= alphas[0] - 1e-9) & (A <= alphas[1] + 1e-9)
    if alts is not None:
        keep &= np.isin(H, np.asarray(alts, float))
    return keep


def envelope_band(sm: dict, machs=None, alphas=(-5.0, 8.0), margin: float = 0.10, alts=None, res=None,
                  fallback: dict | None = None) -> dict:
    """Per strip and side, the stretch of chord the mesh must keep fine over the chosen conditions.

    lo = the earliest of (bubble start, transition − margin), hi = the latest of (bubble end, transition + margin,
    separation start), over every condition that has an answer; clipped to [0, 1]. A strip with no answered
    condition gets the generic band (fallback; default: GENERIC_BAND for a Mach-mode map, DECIDED_BAND for a
    Re-mode map). Also the shortest bubble seen on each strip (for the band cell).
    Conditions: machs (Mach mode; default 0.03–0.13, as before) or res (Re mode; default all levels), and alphas."""
    axis = grid_axis(sm)
    if axis == "mach" and machs is None and res is None:
        machs = (0.03, 0.13)
    keep = condition_mask(sm, machs, alphas, alts, res)
    gen = fallback or (DECIDED_BAND if axis == "re" else GENERIC_BAND)
    n = sm["shape"][0]
    ans = np.array(sm["fields"]["answered"]).reshape(sm["shape"]) & keep[None, :]
    rng = res if axis == "re" else machs
    out = {("res" if axis == "re" else "machs"): None if rng is None else list(rng),
           "alphas": None if alphas is None else list(alphas), "margin": margin, "upper": [], "lower": [],
           "shortest_bubble_c": {"upper": [], "lower": []}, "fallback": []}
    for side, xtr_k, bs_k, be_k, sep_k in (("upper", "xtr_u", "bub_u_s", "bub_u_e", "sep_u_x"), ("lower", "xtr_l", "bub_l_s", "bub_l_e", "sep_l_x")):
        xtr, bs, be, sep = (_field(sm, k) for k in (xtr_k, bs_k, be_k, sep_k))
        for i in range(n):
            m = ans[i]
            if not m.any():
                out[side].append(list(gen[side]))
                out["shortest_bubble_c"][side].append(None)
                if side == "upper":
                    out["fallback"].append(True)
                continue
            lo = np.nanmin(np.concatenate([xtr[i, m] - margin, bs[i, m]]))
            hi = np.nanmax(np.concatenate([xtr[i, m] + margin, be[i, m], sep[i, m]]))
            out[side].append([float(np.clip(lo, 0.0, 1.0)), float(np.clip(hi, 0.0, 1.0))])
            L = be[i, m] - bs[i, m]
            out["shortest_bubble_c"][side].append(None if not np.isfinite(L).any() else float(np.nanmin(L)))
            if side == "upper":
                out["fallback"].append(False)
    return out


def band_cells(sm: dict, band: dict, re_mean: float, rules, generic: dict | None = None) -> dict:
    """Cells along the chord the band costs per strip, generic against per-wing, at one Re on the mean chord.
    generic: the generic band to compare with (default: GENERIC_BAND for a Mach-mode map, DECIDED_BAND for a Re-mode map)."""
    c = np.asarray(sm["strips"]["chord"])
    re_loc = re_mean * c / sm["wing"]["mean_chord_m"]
    h = np.array([rules.band_spacing_c(float(r)) for r in re_loc])
    G = generic or (DECIDED_BAND if grid_axis(sm) == "re" else GENERIC_BAND)
    gen = sum((G[s][1] - G[s][0]) / h for s in ("upper", "lower"))
    own = sum((np.array(band[s])[:, 1] - np.array(band[s])[:, 0]) / h for s in ("upper", "lower"))
    return {"generic": [float(v) for v in gen], "per_wing": [float(v) for v in own], "band_cell_c": [float(v) for v in h]}
