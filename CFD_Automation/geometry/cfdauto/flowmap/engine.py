"""Vectorized flow-map engine: wing strips x flight conditions -> strip results and wing metrics.

The single-wing tool (core.flow_map) and the dataset (dataset.py) both use it, so the dataset and the
tool give the same answer for the same wing and condition.

Assumptions (baseline since 2 Nov 2026):
  - strips along the semi-span; each strip is a 2-D section (XFOIL, via the section tables);
  - local angle = root angle + local twist - induced angle: a uniform (elliptic) downwash CL / (pi AR),
    iterated to convergence (induced=True, the default). induced=False is the old baseline without it,
    kept as a check: it puts the strips too close to stall at high angle (logic check L8, 1 Nov 2026);
  - free transition: e^N with N_crit 9 (quiet air); fully turbulent: tripped at 1 % chord;
  - Re on the local chord with Stage 0 air; Mach in XFOIL by Karman-Tsien.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..geometry.params import TypeSpec, resolve
from ..geometry.sections import build_stations
from . import tables

RHO_MU = ((0.0, 68500.0), (1524.0, 60600.0), (3048.0, 53500.0))     # Stage 0 air [s/m^2]
SA_OK = 0.10            # |SA profile-drag bias| below this: fully turbulent SA is adequate (our threshold) ...
LAM_SHORT = 0.20        # ... if the upper surface also turns turbulent near the nose (mean laminar run below this)
LOW_RE = 1e5
CROSSFLOW_SWEEP, CROSSFLOW_RE = 25.0, 1e6   # rough crossflow flag on one strip (our threshold, not sourced)
BANDS = ((0.0, 1e5, "below 10⁵", "#C0392B"), (1e5, 5e5, "10⁵ – 5 × 10⁵", "#E0A030"),
         (5e5, 3e6, "5 × 10⁵ – 3 × 10⁶", "#5B8FD0"), (3e6, 1e12, "above 3 × 10⁶", "#1F3F7A"))
CATEGORIES = ("SA adequate", "transition model", "transition model; part below 10⁵", "no XFOIL answer")


def rho_over_mu(alt_m) -> np.ndarray:
    a, r = zip(*RHO_MU)
    return np.interp(np.asarray(alt_m, float), a, r)


def sound_speed(alt_m) -> np.ndarray:
    return np.sqrt(1.4 * 287.05 * (288.15 - 0.0065 * np.asarray(alt_m, float)))


def density(alt_m) -> np.ndarray:
    """ISA troposphere density [kg/m^3]."""
    return 1.225 * (1.0 - 2.25577e-5 * np.asarray(alt_m, float)) ** 4.2559


def lift_slope_ratio(aspect_ratio: float, sweep_deg: float) -> float:
    """3-D over 2-D lift-curve slope, a / 2 pi = AR / (2 + sqrt(4 + AR^2 (1 + tan^2 sweep)))
    (Helmbold / DATCOM form, sweep of the half-chord line). Used only without the induced angle."""
    t = math.tan(math.radians(sweep_deg))
    return aspect_ratio / (2.0 + math.sqrt(4.0 + aspect_ratio ** 2 * (1.0 + t * t)))


def half_chord_sweep(pf) -> float:
    """Area-weighted sweep of the half-chord line over the three panels [deg]."""
    xh = np.asarray(pf.x_le, float) + 0.5 * np.asarray(pf.chord, float)
    dy = np.diff(np.asarray(pf.y, float))
    lam = np.degrees(np.arctan2(np.diff(xh), dy))
    area = 0.5 * (np.asarray(pf.chord[:-1], float) + np.asarray(pf.chord[1:], float)) * dy
    return float(np.sum(lam * area) / np.sum(area))


@dataclass
class WingStrips:
    y: np.ndarray            # strip span positions [m]
    w: np.ndarray            # span weights (trapezoid share of the semi-span, sum 1)
    chord: np.ndarray
    x_le: np.ndarray
    twist: np.ndarray        # deg
    sweep: np.ndarray        # LE sweep of the strip's panel, deg
    sec_a: list
    sec_b: list              # None when the strip sits on one station section
    s: np.ndarray            # blend fraction toward sec_b
    semi_span: float
    aspect_ratio: float
    pf: object
    stations: list
    panel: np.ndarray        # panel index of each strip (0..2)
    s_geo: np.ndarray        # geometric fraction along the panel (for the blended section in direct runs)

    def airfoil(self, i: int):
        """The section of strip i as geometry (the ruled blend of its panel's two station sections)."""
        k, s = int(self.panel[i]), float(self.s_geo[i])
        a, b = self.stations[k].airfoil, self.stations[k + 1].airfoil
        return a if s < 1e-9 else (b if s > 1 - 1e-9 else a.blend(b, s))

    def section_name(self, i: int) -> str:
        a, b, s = self.sec_a[i], self.sec_b[i], self.s[i]
        return a if b is None else f"{a}→{b} {s:.2f}"


def strip_positions(pf, n_per_panel: int = 2) -> np.ndarray:
    """Root, n_per_panel strips inside each panel, every break, and 97 % of the semi-span."""
    S = pf.semi_span
    ys = [0.0]
    for k in range(3):
        a, b = pf.y[k], pf.y[k + 1]
        ys += [a + (b - a) * (j + 1) / (n_per_panel + 1) for j in range(n_per_panel)]
        ys.append(b if k < 2 else 0.97 * S)
    return np.array(sorted(set(round(v, 12) for v in ys)))


def wing_strips(spec: TypeSpec, vec: dict, airfoils: list[str] | None = None, n_per_panel: int = 2) -> WingStrips:
    """Strips at strip_positions: chord, LE position, twist and sweep, and the section as a pair of
    station sections with the ruled-blend fraction."""
    vec = dict(vec)
    if airfoils:
        vec["airfoils"] = list(airfoils)
    vec = resolve(spec, vec)
    pf, st = build_stations(spec, vec)
    S = pf.semi_span
    rows = []
    for y in strip_positions(pf, n_per_panel):
        k = min(int(np.searchsorted(pf.y, y, side="right")) - 1, 2)
        a, b = st[k], st[k + 1]
        s = (y - a.y) / (b.y - a.y)
        na, nb = a.airfoil.name, b.airfoil.name
        if s < 1e-9 or na == nb:
            pair = (na, None, 0.0)
        elif s > 1 - 1e-9:
            pair = (nb, None, 0.0)
        else:
            pair = (na, nb, s)
        rows.append((y, a.chord + s * (b.chord - a.chord), a.x_le + s * (b.x_le - a.x_le),
                     a.twist_deg + s * (b.twist_deg - a.twist_deg), float(pf.sweep_le_deg[k]), *pair, k, s))
    y = np.array([r[0] for r in rows])
    edges = np.concatenate([[0.0], 0.5 * (y[1:] + y[:-1]), [S]])
    return WingStrips(y=y, w=np.diff(edges) / S, chord=np.array([r[1] for r in rows]), x_le=np.array([r[2] for r in rows]),
                      twist=np.array([r[3] for r in rows]), sweep=np.array([r[4] for r in rows]),
                      sec_a=[r[5] for r in rows], sec_b=[r[6] for r in rows], s=np.array([r[7] for r in rows]),
                      semi_span=S, aspect_ratio=float(vec["aspect_ratio"]), pf=pf, stations=st,
                      panel=np.array([r[8] for r in rows]), s_geo=np.array([r[9] for r in rows]))


def sections_needed(ws: WingStrips) -> set[str]:
    return {x for x in ws.sec_a + ws.sec_b if x}


def tables_cover(ws: WingStrips, ncrit: float = 9.0) -> bool:
    """True when every section of the wing has free (at this N_crit) and tripped tables."""
    return all(tables.has(s, "free", ncrit) and tables.has(s, "trip", 9.0) for s in sections_needed(ws))


def evaluate(ws: WingStrips, mach, alt_m, alpha_deg, ncrit: float = 9.0, induced: bool = True,
             mach_in_tables: np.ndarray | None = None) -> dict:
    """Strip results for m conditions (mach, alt_m, alpha_deg: arrays of length m, root angle).

    Returns arrays of shape (n_strips, m): re, alpha_local and, for 'free' and 'trip', the table fields.
    mach_in_tables overrides the Mach used for the 2-D compressibility only (sensitivity checks).
    induced: subtract a uniform downwash angle CL_w / (pi AR) (elliptic), iterated with the relaxation that
    is exact for a lift slope of 2 pi (factor 1 / (1 + 2 / AR)), so a few steps converge. The returned
    alpha_induced is the one the returned strips were evaluated at. induced=False: the old baseline (a check)."""
    mach, alt_m, alpha_deg = (np.atleast_1d(np.asarray(v, float)) for v in (mach, alt_m, alpha_deg))
    mach, alt_m, alpha_deg = np.broadcast_arrays(mach, alt_m, alpha_deg)
    v = mach * sound_speed(alt_m)
    re_ = rho_over_mu(alt_m)[None, :] * v[None, :] * ws.chord[:, None]
    m_tab = mach if mach_in_tables is None else np.broadcast_to(np.asarray(mach_in_tables, float), mach.shape)
    alpha_i = np.zeros(mach.shape)
    groups: dict = {}
    for i, (a, b) in enumerate(zip(ws.sec_a, ws.sec_b)):
        groups.setdefault((a, b), []).append(i)

    def look(mode, al_loc, nc):
        out = {f: np.full(re_.shape, np.nan) for f in tables.FIELDS}
        out["re_clamped"] = np.zeros(re_.shape, bool)
        for (a, b), idx in groups.items():
            idx = np.array(idx)
            r = tables.lookup(a, b, ws.s[idx][:, None], re_[idx], m_tab[None, :], al_loc[idx], mode,
                              nc if mode == "free" else 9.0)
            for f in out:
                out[f][idx] = r[f]
        return out

    relax = 1.0 / (1.0 + 2.0 / max(float(ws.aspect_ratio), 1e-6))
    n_iter = 5 if induced else 1
    for it in range(n_iter):
        al_loc = alpha_deg[None, :] + ws.twist[:, None] - alpha_i[None, :]
        free = look("free", al_loc, ncrit)
        wc = ws.w[:, None] * ws.chord[:, None] * np.isfinite(free["cl"])
        cl_w = np.nansum(wc * np.nan_to_num(free["cl"]), 0) / np.maximum(wc.sum(0), 1e-12)
        if it == n_iter - 1:
            break
        alpha_i = alpha_i + relax * (np.degrees(cl_w / (math.pi * ws.aspect_ratio)) - alpha_i)
    trip = look("trip", al_loc, 9.0)
    return {"re": re_, "alpha_local": al_loc, "alpha_induced": alpha_i, "cl_wing": cl_w, "induced": bool(induced),
            "free": free, "trip": trip, "mach": mach, "alt_m": alt_m, "alpha_root": alpha_deg, "speed": v}


def metrics(ws: WingStrips, r: dict) -> dict:
    """Wing-level numbers for each condition (arrays of length m)."""
    f, t, re_ = r["free"], r["trip"], r["re"]
    w = ws.w[:, None] * np.ones(re_.shape)
    wc = w * ws.chord[:, None]
    ok = np.isfinite(f["cd"]) & np.isfinite(t["cd"])

    def wmean(x, weights, mask):
        ww = np.where(mask & np.isfinite(x), weights, 0.0)
        return np.where(ww.sum(0) > 0, np.nansum(ww * np.nan_to_num(x), 0) / np.maximum(ww.sum(0), 1e-12), np.nan)

    cdf = np.nansum(np.where(ok, wc * np.nan_to_num(f["cd"]), 0), 0)
    cdt = np.nansum(np.where(ok, wc * np.nan_to_num(t["cd"]), 0), 0)
    conv = np.sum(np.where(ok, w, 0), 0)
    bias = np.where(conv >= 0.5, cdt / np.maximum(cdf, 1e-12) - 1.0, np.nan)
    bub = np.nan_to_num(f["bub_u"]) >= 0.5
    sep = np.nan_to_num(f["sep_u"]) >= 0.5
    blen = np.where(bub, f["bub_u_e"] - f["bub_u_s"], np.nan)
    out = {
        "re_min": re_.min(0), "re_max": re_.max(0), "re_mean": np.sum(wc * re_, 0) / np.sum(wc, 0),
        "re_root": re_[0], "re_tip": re_[-1],
        "span_re_lt_1e5": np.sum(w * (re_ < 1e5), 0), "span_re_1e5_5e5": np.sum(w * ((re_ >= 1e5) & (re_ < 5e5)), 0),
        "span_re_5e5_3e6": np.sum(w * ((re_ >= 5e5) & (re_ < 3e6)), 0), "span_re_gt_3e6": np.sum(w * (re_ >= 3e6), 0),
        "conv_span": conv,
        "cd_free": np.where(conv >= 0.5, cdf / np.maximum(np.sum(np.where(ok, wc, 0), 0), 1e-12), np.nan),
        "cd_trip": np.where(conv >= 0.5, cdt / np.maximum(np.sum(np.where(ok, wc, 0), 0), 1e-12), np.nan),
        "sa_bias": bias,
        "cl2d": wmean(f["cl"], wc, np.isfinite(f["cl"])),
        "lam_upper": wmean(f["xtr_top"], wc, np.isfinite(f["xtr_top"])),
        "lam_lower": wmean(f["xtr_bot"], wc, np.isfinite(f["xtr_bot"])),
        "xtr_upper_min": np.nanmin(np.where(np.isfinite(f["xtr_top"]), f["xtr_top"], np.inf), 0),
        "xtr_upper_max": np.nanmax(np.where(np.isfinite(f["xtr_top"]), f["xtr_top"], -np.inf), 0),
        "bubble_span": np.sum(w * bub, 0),
        "bubble_len": _colmean(blen),
        "bubble_start": _colmean(np.where(bub, f["bub_u_s"], np.nan)),
        "te_sep_span": np.sum(w * sep, 0),
        "re_clamped_span": np.sum(w * (f["re_clamped"] | t["re_clamped"]), 0),
        "alpha_induced": r["alpha_induced"],
        "max_sweep": np.full(re_.shape[1], float(np.max(ws.sweep))),
        "re_normal_max": np.max(re_ * np.cos(np.radians(ws.sweep))[:, None], 0),
    }
    # level-flight check: the wing loading this condition would carry. With the induced angle the strips
    # already carry the downwash, so their chord-weighted lift is the wing CL; without it (the old
    # baseline) the 2-D lift is scaled by the Helmbold lift-slope ratio.
    if r.get("induced", False):
        out["cl3d"] = out["cl2d"]
    else:
        out["cl3d"] = out["cl2d"] * lift_slope_ratio(ws.aspect_ratio, half_chord_sweep(ws.pf))
    q = 0.5 * density(r["alt_m"]) * np.asarray(r["speed"], float) ** 2
    out["wing_loading"] = out["cl3d"] * q
    out["lam_mean"] = 0.5 * (out["lam_upper"] + out["lam_lower"])
    for k in ("xtr_upper_min", "xtr_upper_max"):
        out[k] = np.where(np.isfinite(out[k]), out[k], np.nan)
    out["category"] = category(out)
    # rough crossflow flag: one strip both swept beyond 25 deg and above Re 1e6 normal to its edge
    cf = (ws.sweep[:, None] > CROSSFLOW_SWEEP) & (re_ * np.cos(np.radians(ws.sweep))[:, None] > CROSSFLOW_RE)
    out["crossflow_risk"] = cf.any(0)
    return out


def _colmean(a: np.ndarray) -> np.ndarray:
    """Mean of the finite values in each column; NaN for a column without any."""
    ok = np.isfinite(a)
    n = ok.sum(0)
    return np.where(n > 0, np.where(ok, a, 0.0).sum(0) / np.maximum(n, 1), np.nan)


def category(m: dict) -> np.ndarray:
    """Model proposal per condition (index into CATEGORIES), by stated rules (our choices):
    no XFOIL answer when under half the span has one (often near stall, sometimes a failed point; not a
    measured stall); else SA adequate when |bias| < 10 %, the upper
    surface turns turbulent near the nose (mean laminar run < 20 % chord: a small bias with a long
    laminar run is a coincidence of two different flows) and no strip is below Re 1e5; else a transition
    model (with a low-Re caution when part of the span is below 1e5)."""
    b, low, conv = m["sa_bias"], m["span_re_lt_1e5"] > 0, m["conv_span"]
    lam = np.nan_to_num(np.asarray(m["lam_upper"], float), nan=1.0)
    cat = np.where((np.abs(b) < SA_OK) & (lam < LAM_SHORT), 0, 1)
    cat = np.where(low, 2, cat)
    cat = np.where((conv < 0.5) | ~np.isfinite(b), 3, cat)
    return cat


def band(re_: float) -> tuple[str, str]:
    for lo, hi, name, col in BANDS:
        if lo <= re_ < hi:
            return name, col
    return BANDS[-1][2], BANDS[-1][3]
