"""Where to refine, per wing: the transition and bubble positions from the Stage 1 flow dataset.

The generic transition band (upper 0–85 % c, lower 60–100 % c) covers every wing. This module asks the
flow-map engine (2-D XFOIL section tables, strips along the semi-span, a uniform induced angle) where the
flow of ONE wing turns turbulent, where its bubbles sit and where it separates, at every flight condition
of a grid (Mach × angle × altitude), and turns that into a band per strip and side: the envelope over the
conditions the mesh must serve, plus a margin.

    from cfdauto.mesh.refine_map import strip_map, envelope_band
    sm = strip_map("bwb", "reference", 0)
    band = envelope_band(sm, machs=(0.03, 0.13), alphas=(0, 8), margin=0.10)

Limits, inherited from the dataset: 2-D strips, e^N with N_crit 9 (calm air), a uniform (elliptic) induced
angle, no crossflow transition on swept panels, no 3-D relief of bubbles, no tip effects. Where a strip has
no XFOIL answer (beyond the section's 2-D stall) the band falls back to the generic one for that strip.
"""

from __future__ import annotations

import math

import numpy as np

GENERIC_BAND = {"upper": (0.0, 0.85), "lower": (0.60, 1.0)}
MACHS = (0.03, 0.05, 0.08, 0.10, 0.13, 0.16, 0.20)
ALPHAS = tuple(float(a) for a in range(-2, 13))
ALTS = (0.0, 3000.0)
FOCUS_MACH = {"tailless": (0.03, 0.13), "conventional": (0.03, 0.20)}


def _nanlist(a) -> list:
    return [None if not math.isfinite(float(v)) else round(float(v), 4) for v in np.asarray(a).ravel()]


def strip_map(wing_type: str, set_name: str, index: int, machs=MACHS, alphas=ALPHAS, alts=ALTS,
              n_per_panel: int = 4) -> dict:
    """The flow answers of one wing on a condition grid, per strip: a plain dict (JSON-ready)."""
    from ..flowmap import engine
    from ..geometry.build import load_set
    from ..geometry.params import load_config, resolve

    cfg = load_config()
    spec = cfg.types[wing_type]
    vec = resolve(spec, load_set(wing_type, set_name)["vectors"][index])
    ws = engine.wing_strips(spec, vec, None, n_per_panel)
    M, A, H = np.meshgrid(np.asarray(machs, float), np.asarray(alphas, float), np.asarray(alts, float), indexing="ij")
    r = engine.evaluate(ws, M.ravel(), H.ravel(), A.ravel())
    f = r["free"]
    pf = ws.pf
    tailless = wing_type in ("bwb", "flying_wing")
    out = {
        "wing": {"type": wing_type, "set": set_name, "index": index, "family": "tailless" if tailless else "conventional",
                 "semi_span_m": float(pf.semi_span), "mean_chord_m": float(pf.area() / (2 * pf.semi_span)),
                 "aspect_ratio": float(vec["aspect_ratio"]), "full_span_m": float(2 * pf.semi_span),
                 "stations": {"y": [float(v) for v in pf.y], "x_le": [float(v) for v in pf.x_le],
                              "chord": [float(v) for v in pf.chord], "sweep_le_deg": [float(v) for v in pf.sweep_le_deg],
                              "airfoils": [s.airfoil.name for s in ws.stations]}},
        "grid": {"mach": [float(v) for v in machs], "alpha_deg": [float(v) for v in alphas], "alt_m": [float(v) for v in alts],
                 "order": "mach-major, then alpha, then altitude (C-order of the meshgrid)",
                 "n": int(M.size)},
        "strips": {"y": [float(v) for v in ws.y], "y_over_S": [float(v / ws.semi_span) for v in ws.y],
                   "chord": [float(v) for v in ws.chord], "x_le": [float(v) for v in ws.x_le],
                   "twist_deg": [float(v) for v in ws.twist], "sweep_deg": [float(v) for v in ws.sweep],
                   "section": [ws.section_name(i) for i in range(len(ws.y))]},
        "per_condition": {"alpha_induced_deg": _nanlist(r["alpha_induced"]), "cl_wing": _nanlist(r["cl_wing"]),
                          "re_mean": _nanlist(engine.rho_over_mu(H.ravel()) * M.ravel() * engine.sound_speed(H.ravel())
                                              * (pf.area() / (2 * pf.semi_span)))},
        "fields": {},                                   # each: n_strips × n_conditions, row-major, null = no answer
        "limits": ("2-D strips (XFOIL e^N, N_crit 9 = calm air) with a uniform induced angle: no crossflow transition on "
                   "swept panels, no 3-D relief of bubbles, no tip effects. Where to look, not the 3-D answer."),
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
    out["shape"] = [int(len(ws.y)), int(M.size)]
    return out


def _field(sm: dict, name: str) -> np.ndarray:
    n, m = sm["shape"]
    return np.array([np.nan if v is None else v for v in sm["fields"][name]], float).reshape(n, m)


def condition_mask(sm: dict, machs: tuple[float, float], alphas: tuple[float, float], alts=None) -> np.ndarray:
    g = sm["grid"]
    M, A, H = np.meshgrid(np.asarray(g["mach"]), np.asarray(g["alpha_deg"]), np.asarray(g["alt_m"]), indexing="ij")
    keep = (M.ravel() >= machs[0] - 1e-9) & (M.ravel() <= machs[1] + 1e-9) & (A.ravel() >= alphas[0] - 1e-9) & (A.ravel() <= alphas[1] + 1e-9)
    if alts is not None:
        keep &= np.isin(H.ravel(), np.asarray(alts, float))
    return keep


def envelope_band(sm: dict, machs=(0.03, 0.13), alphas=(0.0, 8.0), margin: float = 0.10, alts=None) -> dict:
    """Per strip and side, the stretch of chord the mesh must keep fine over the chosen conditions.

    lo = the earliest of (bubble start, transition − margin), hi = the latest of (bubble end, transition + margin,
    separation start), over every condition that has an answer; clipped to [0, 1]. A strip with no answered
    condition gets the generic band. Also the shortest bubble seen on each strip (for the band cell)."""
    keep = condition_mask(sm, machs, alphas, alts)
    n = sm["shape"][0]
    ans = np.array(sm["fields"]["answered"]).reshape(sm["shape"]) & keep[None, :]
    out = {"machs": list(machs), "alphas": list(alphas), "margin": margin, "upper": [], "lower": [],
           "shortest_bubble_c": {"upper": [], "lower": []}, "fallback": []}
    for side, xtr_k, bs_k, be_k, sep_k in (("upper", "xtr_u", "bub_u_s", "bub_u_e", "sep_u_x"), ("lower", "xtr_l", "bub_l_s", "bub_l_e", "sep_l_x")):
        xtr, bs, be, sep = (_field(sm, k) for k in (xtr_k, bs_k, be_k, sep_k))
        for i in range(n):
            m = ans[i]
            if not m.any():
                out[side].append(list(GENERIC_BAND[side]))
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


def band_cells(sm: dict, band: dict, re_mean: float, rules) -> dict:
    """Cells along the chord the band costs per strip, generic against per-wing, at one Re on the mean chord."""
    c = np.asarray(sm["strips"]["chord"])
    re_loc = re_mean * c / sm["wing"]["mean_chord_m"]
    h = np.array([rules.band_spacing_c(float(r)) for r in re_loc])
    gen = sum((GENERIC_BAND[s][1] - GENERIC_BAND[s][0]) / h for s in ("upper", "lower"))
    own = sum((np.array(band[s])[:, 1] - np.array(band[s])[:, 0]) / h for s in ("upper", "lower"))
    return {"generic": [float(v) for v in gen], "per_wing": [float(v) for v in own], "band_cell_c": [float(v) for v in h]}
