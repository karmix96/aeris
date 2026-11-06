"""Nose curvature: the raw airfoil files against the Stage 1 built sections (open decision 64).

One curvature method for every curve, so the answer depends on no frame and no formula: the
curvature kappa(sigma) along the arc length sigma, from each curve's own first and second
derivatives. sigma = 0 is the Stage 1 leading-edge point (rule D25: the raw point farthest from
the trailing-edge midpoint), + on the upper side, - on the lower side. Every curve is put in the
D25 frame of the raw file (unit chord), so lengths are in that chord c.

Curves:
  raw         cubic interpolating spline (not-a-knot) through the raw file points, x and y against
              the cumulative chord length;
  raw5        the same with a quintic spline (how much the reference itself depends on the spline);
  built       the Stage 1 section as the loft holds it: load_airfoil(name), two copies lofted by
              cfdauto.geometry.loft.build_loft (numpy backend), the loft's own B-splines in s = sqrt(x/c);
  built_avg   the same section points with averaging knots (Piegl and Tiller, eq. 9.8), the other
              usual knot rule;
  exact       NACA 4415 only: the formula (m 0.04, p 0.4, t 0.15, open trailing edge -0.1015,
              thickness normal to the camber line), exact derivatives, placed on the file by a
              least-squares similarity fit (raw points with x < 0.6);
  fixed       the prototype fix, in this script only: the leading edge at the point of the raw
              spline farthest from the trailing-edge midpoint (not the farthest raw point), both sides
              sampled from that spline at the cosine x (101 points per side, as now), the same loft;
  fixed200    the same fix with 201 points per side;
  apex_pchip  diagnostic: the leading edge at the spline apex, but the sides still resampled by PCHIP
              in sqrt(x) through the raw points, as now (which half of the fix does what).

Mesh number: T(h) = the largest turning a cell of arc length h gets near the nose = the largest
integral of kappa over a window [sigma, sigma + h] inside |sigma| <= 3 % c,
for h = 0.04, 0.10, 0.18, 0.30, 0.50 % c.

Criterion (fixed before computing, 7 Nov 2026): if |T_built(h) - T_raw(h)| / T_raw(h) < 5 % for
every h on all ten airfoils, decision 64 closes with no fix (the built nose is faithful at mesh
scale). Otherwise the prototype fix is measured the same way.

Stage 2 check: the nose solve of the Stage 2 page (tapered training wing 35, station 21, NACA 4415):
the largest turning per ring node against the nose spacing, with the built section and with the
fixed one (swapped in at run time; cfdauto is not changed).

    cd CFD_Automation && python Stage_1_geometry/scripts/nose_curvature.py      # under 30 s

Writes Stage_1_geometry/data/studies/nose_curvature.json and Stage_1_geometry/docs/nose_curvature.png.
"""

from __future__ import annotations

import contextlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import numpy as np
import scipy
from scipy.interpolate import CubicSpline, PchipInterpolator, make_interp_spline
from scipy.optimize import brentq, least_squares
from scipy.signal import find_peaks
from scipy.spatial import cKDTree

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]          # Stage_1_geometry
sys.path.insert(0, str(ROOT.parent))                # CFD_Automation: the cfdauto package

from cfdauto.geometry import airfoils as A  # noqa: E402
from cfdauto.geometry import sections as S  # noqa: E402
from cfdauto.geometry.loft import build_loft  # noqa: E402
from cfdauto.geometry.sections import Airfoil, Station, cosine_x, load_airfoil  # noqa: E402
from cfdauto.paths import REPO  # noqa: E402

AIRFOILS = ("naca4415", "e387", "sd7032", "mh104", "mh61", "mh45", "mh60", "s5010", "la2573a", "naca25118")
LABEL = {"naca4415": "NACA 4415", "e387": "E387", "sd7032": "SD7032", "mh104": "MH 104", "mh61": "MH 61",
         "mh45": "MH 45", "mh60": "MH 60", "s5010": "S5010", "la2573a": "LA2573A", "naca25118": "NACA 25118"}
H_PCT = (0.04, 0.10, 0.18, 0.30, 0.50)    # cell arc lengths [% c]
WIN_C = 0.03                              # windows and the curvature peak: within 3 % c of arc
PROF_C = 0.02                             # stored profile: +-2 % c
PROF_N = 401
LIMIT_PCT = 5.0                           # the criterion
N_SIDE_DENSE = 30001                      # evaluation points per side (arc step about 1e-6 c)
STAGE2_WING = ("tapered", "training_focus", 35, 21)   # Stage 2 page, nose solve, NACA 4415 panel
OUT_JSON = ROOT / "data" / "studies" / "nose_curvature.json"
OUT_PNG = ROOT / "docs" / "nose_curvature.png"


# --- one method for every curve -----------------------------------------------------------------

@dataclass
class Nose:
    """A curve near the nose, ordered from the lower side to the upper side."""
    sigma: np.ndarray    # arc length from the LE point [c], - lower, + upper
    kappa: np.ndarray    # curvature [1/c], > 0 on a convex nose
    theta: np.ndarray    # tangent angle [rad], grows with sigma on a convex nose


def nose_from(tau: np.ndarray, dP: np.ndarray, ddP: np.ndarray, i0: int) -> Nose:
    """tau: increasing parameter (lower side -> upper side); dP, ddP: derivatives in tau;
    i0: index of the leading-edge point (sigma = 0)."""
    speed = np.hypot(dP[:, 0], dP[:, 1])
    arc = np.concatenate([[0.0], np.cumsum(0.5 * (speed[1:] + speed[:-1]) * np.diff(tau))])
    cross = dP[:, 0] * ddP[:, 1] - dP[:, 1] * ddP[:, 0]
    theta = -np.unwrap(np.arctan2(dP[:, 1], dP[:, 0]))
    return Nose(arc - arc[i0], -cross / speed ** 3, theta - theta[i0])


def turning_max(sigma: np.ndarray, theta: np.ndarray, h: float) -> tuple[float, float]:
    """T(h) [deg] and the window centre [% c]: the largest |theta(s + h) - theta(s)| within 3 % c."""
    w = (sigma >= -WIN_C) & (sigma <= WIN_C - h)
    s0 = sigma[w]
    turn = np.abs(np.interp(s0 + h, sigma, theta) - theta[w])
    j = int(np.argmax(turn))
    return float(np.degrees(turn[j])), float(100 * (s0[j] + 0.5 * h))


def measures(n: Nose) -> dict:
    """Smallest radius near the nose, where it sits, and T(h) with the window centre."""
    m = np.abs(n.sigma) <= WIN_C
    k = int(np.argmax(np.where(m, n.kappa, -np.inf)))
    out = {"R_min_c": float(1.0 / n.kappa[k]), "sigma_at_R_min_pct": float(100 * n.sigma[k]),
           "T_deg": [], "T_centre_pct": []}
    for h in np.array(H_PCT) / 100:
        t, c = turning_max(n.sigma, n.theta, h)
        out["T_deg"].append(t)
        out["T_centre_pct"].append(c)
    return out


def profile(n: Nose) -> list[float]:
    grid = np.linspace(-PROF_C, PROF_C, PROF_N)
    return [float(f"{v:.5g}") for v in np.interp(grid, n.sigma, n.kappa)]


def peaks(n: Nose, rel: float = 0.02) -> list[dict]:
    """Local curvature maxima inside +-3 % c (prominence > rel x the largest curvature)."""
    m = np.abs(n.sigma) <= WIN_C
    s, k = n.sigma[m], n.kappa[m]
    idx, _ = find_peaks(k, prominence=rel * k.max())
    return [{"sigma_pct": float(100 * s[i]), "kappa": float(k[i])} for i in idx]


def similarity(P: np.ndarray, scale: float, rot: np.ndarray, shift) -> np.ndarray:
    """scale * rot @ P + shift for row vectors (shift 0 for derivatives)."""
    return scale * P @ rot.T + shift


def rotation(a: float) -> np.ndarray:
    return np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])


# --- the raw file in the Stage 1 frame ----------------------------------------------------------

def d25(pts: np.ndarray):
    """The frame airfoil_from_points uses (sections.py): LE = raw point farthest from the
    trailing-edge midpoint, chord along x, unit chord."""
    te_mid = 0.5 * (pts[0] + pts[-1])
    i_le = int(np.argmax(np.linalg.norm(pts - te_mid, axis=1)))
    le = pts[i_le]
    d = te_mid - le
    p = (pts - le) @ rotation(-float(np.arctan2(d[1], d[0]))).T / float(np.linalg.norm(d))
    if np.mean(p[: i_le + 1, 1]) < np.mean(p[i_le:, 1]):
        raise RuntimeError("file lists the lower side first; this study assumes Selig order")
    return p, i_le


def raw_spline(p: np.ndarray, i_le: int, quintic: bool = False):
    """Spline through the raw points against cumulative chord length (Selig order: upper first)."""
    keep = np.concatenate([[True], np.linalg.norm(np.diff(p, axis=0), axis=1) > 1e-12])
    i_le = int(np.sum(keep[: i_le + 1]) - 1)
    p = p[keep]
    t = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
    spl = make_interp_spline(t, p, k=5) if quintic else CubicSpline(t, p)
    return spl, t, i_le


def nose_raw(spl, t: np.ndarray, i_le: int) -> Nose:
    """tau = -t, so the curve runs from the lower side to the upper side."""
    tl = t[i_le]
    tt = np.concatenate([np.linspace(tl + 0.045, tl, N_SIDE_DENSE), np.linspace(tl, tl - 0.045, N_SIDE_DENSE)[1:]])
    tt = np.clip(tt, t[0], t[-1])
    return nose_from(-tt, -spl(tt, 1), spl(tt, 2), N_SIDE_DENSE - 1)


def _arc(spl, a: float, b: float, n: int = 2001) -> float:
    q = np.linspace(a, b, n)
    d = spl(q, 1)
    sp = np.hypot(d[:, 0], d[:, 1])
    return float(np.sum(0.5 * (sp[1:] + sp[:-1]) * np.diff(q)))


# --- the built section, as the loft holds it -------------------------------------------------------

def loft_curves(af: Airfoil):
    """The loft's own B-splines (upper, lower) in s = sqrt(x/c) at a station: two copies of the
    section, unit chord, no twist, lofted by cfdauto (numpy backend). Returns (x, z) callables."""
    st = [Station("a", 0.0, 0.0, 0.0, 1.0, 0.0, af), Station("b", 1.0, 0.0, 0.0, 1.0, 0.0, af)]
    loft = build_loft(st, 2, backend="numpy")
    up, lo = loft.geo.surfs[0].curves[0], loft.geo.surfs[1].curves[0]
    u = np.linspace(0.0, 0.05, 11)                       # the loft evaluates exactly these curves
    assert np.allclose(loft.upper(u, np.zeros_like(u)), up(np.sqrt(u)), atol=1e-15)
    xz = lambda c: (lambda s, nu=0: c(s, nu)[..., [0, 2]])  # noqa: E731  section plane: x and z
    return xz(up), xz(lo)


def avg_knot_curves(af: Airfoil):
    """Same section points, cubic interpolation with averaging knots."""
    s = np.sqrt(af.x)
    inner = [(s[j] + s[j + 1] + s[j + 2]) / 3.0 for j in range(1, len(s) - 3)]
    kn = np.r_[[s[0]] * 4, inner, [s[-1]] * 4]
    up = make_interp_spline(s, np.column_stack([af.x, af.yu]), k=3, t=kn)
    lo = make_interp_spline(s, np.column_stack([af.x, af.yl]), k=3, t=kn)
    return (lambda q, nu=0: up(q, nu)), (lambda q, nu=0: lo(q, nu))


def nose_two_sided(up, lo, s_max: float = 0.3, scale: float = 1.0, rot=np.eye(2)) -> Nose:
    """A curve given as two branches from the nose (parameter s >= 0 on each), joined at s = 0:
    tau = -s on the lower branch, +s on the upper. scale and rot map derivatives into the raw frame.
    sigma = 0 appears twice: the lower branch's kappa(0-), then the upper branch's kappa(0+)."""
    s = np.linspace(0.0, s_max, N_SIDE_DENSE)
    dP = similarity(np.vstack([-lo(s[::-1], 1), up(s, 1)]), scale, rot, 0.0)
    ddP = similarity(np.vstack([lo(s[::-1], 2), up(s, 2)]), scale, rot, 0.0)
    return nose_from(np.concatenate([-s[::-1], s]), dP, ddP, N_SIDE_DENSE)


def polyline_check(names=("naca4415", "sd7032", "mh60")) -> float:
    """T(h) of the built section from a dense polyline of loft.upper / loft.lower points (the way the
    mesher samples the loft), against the analytic T(h): the largest difference [deg]."""
    worst = 0.0
    for name in names:
        af = load_airfoil(name)
        loft = build_loft([Station("a", 0.0, 0.0, 0.0, 1.0, 0.0, af), Station("b", 1.0, 0.0, 0.0, 1.0, 0.0, af)],
                          2, backend="numpy")
        u = np.linspace(0.0, 0.3, 200001) ** 2              # uniform in s = sqrt(x/c)
        v = np.zeros_like(u)
        P = np.vstack([loft.lower(u, v)[::-1, [0, 2]], loft.upper(u, v)[1:, [0, 2]]])
        d = np.diff(P, axis=0)
        sig = np.concatenate([[0.0], np.cumsum(np.hypot(d[:, 0], d[:, 1]))])
        mid = 0.5 * (sig[1:] + sig[:-1]) - sig[len(u) - 1]
        theta = -np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
        exact = measures(nose_two_sided(*loft_curves(af)))["T_deg"]
        poly = [turning_max(mid, theta, h)[0] for h in np.array(H_PCT) / 100]
        worst = max(worst, max(abs(a - b) for a, b in zip(poly, exact)))
    return float(worst)


def one_sided_le(up, lo, scale: float = 1.0) -> dict:
    """Curvature radius of each branch at the leading edge itself (s = 0)."""
    out = {}
    for name, c in (("upper", up), ("lower", lo)):
        d1, d2 = c(np.array([0.0]), 1)[0], c(np.array([0.0]), 2)[0]
        out[f"R_le_{name}_c"] = float(scale * np.hypot(*d1) ** 3 / abs(d1[0] * d2[1] - d1[1] * d2[0]))
    return out


# --- NACA 4415 from the formula ------------------------------------------------------------------

NACA_M, NACA_P, NACA_T = 0.04, 0.4, 0.15
NACA_A = 5 * NACA_T * np.array([0.2969, -0.1260, -0.3516, 0.2843, -0.1015])


def naca4_branch(upper: bool):
    """x, y and their first two derivatives in u = sqrt(x_c), exact (u <= 1)."""
    a, p, sg = NACA_A, NACA_P, (1.0 if upper else -1.0)

    def f(u, nu=0):
        u = np.asarray(u, dtype=float)
        front = u * u < p
        k = np.where(front, NACA_M / p ** 2, NACA_M / (1 - p) ** 2)       # camber: front / aft of p
        y0 = np.where(front, 0.0, NACA_M / (1 - p) ** 2 * (1 - 2 * p))
        yt = [a[0] * u + a[1] * u**2 + a[2] * u**4 + a[3] * u**6 + a[4] * u**8,
              a[0] + 2 * a[1] * u + 4 * a[2] * u**3 + 6 * a[3] * u**5 + 8 * a[4] * u**7,
              2 * a[1] + 12 * a[2] * u**2 + 30 * a[3] * u**4 + 56 * a[4] * u**6]
        yc = [y0 + k * (2 * p * u**2 - u**4), k * (4 * p * u - 4 * u**3), k * (4 * p - 12 * u**2)]
        g, g1, g2 = 2 * k * (p - u**2), -4 * k * u, -4 * k * np.ones_like(u)
        c = 1.0 / np.sqrt(1.0 + g * g)
        cs = [c, -g * g1 * c**3, -(g1**2 + g * g2) * c**3 + 3 * g**2 * g1**2 * c**5]
        sn = [g * c, g1 * c**3, g2 * c**3 - 3 * g * g1**2 * c**5]
        prod = lambda f1, f2, n: [f1[0] * f2[0], f1[1] * f2[0] + f1[0] * f2[1],  # noqa: E731
                                  f1[2] * f2[0] + 2 * f1[1] * f2[1] + f1[0] * f2[2]][n]
        xu = [u**2, 2 * u, 2 * np.ones_like(u)]
        return np.stack([xu[nu] - sg * prod(yt, sn, nu), yc[nu] + sg * prod(yt, cs, nu)], axis=-1)

    return f


def check_naca_derivatives() -> float:
    """Largest relative error of the exact derivatives against central differences."""
    u, e, worst = np.linspace(0.01, 0.3, 7), 1e-6, 0.0
    for upper in (True, False):
        f = naca4_branch(upper)
        for nu in (1, 2):
            fd = (f(u + e, nu - 1) - f(u - e, nu - 1)) / (2 * e)
            worst = max(worst, float(np.max(np.abs(fd - f(u, nu)) / np.abs(f(u, nu)).max())))
    return worst


def fit_exact(p: np.ndarray) -> dict:
    """Similarity map formula frame -> D25 raw frame, fitted to the raw points with x < 0.6."""
    u = np.linspace(0.0, np.sqrt(0.62), 40001)
    dense = np.vstack([naca4_branch(True)(u)[::-1], naca4_branch(False)(u)[1:]])
    tree = cKDTree(dense)

    def dist(q):
        _, j = tree.query(q)
        j = np.clip(j, 1, len(dense) - 2)
        best = np.full(len(q), np.inf)
        for a, b in ((j - 1, j), (j, j + 1)):
            d = dense[b] - dense[a]
            w = np.clip(((q - dense[a]) * d).sum(1) / (d * d).sum(1), 0.0, 1.0)
            best = np.minimum(best, np.linalg.norm(q - dense[a] - w[:, None] * d, axis=1))
        return best

    def to_formula(x, pts):
        return (pts - x[:2]) @ rotation(-x[2]).T / x[3]

    sel = p[:, 0] < 0.6
    fit = least_squares(lambda x: dist(to_formula(x, p[sel])), [0.0, 0.0, 0.0, 1.0],
                        x_scale=[1e-3] * 4, xtol=1e-15, ftol=1e-15)
    r = dist(to_formula(fit.x, p[sel]))
    near = np.linalg.norm(p[sel], axis=1) < 0.02
    tx, ty, ang, sc = (float(v) for v in fit.x)
    return {"shift_c": [tx, ty], "rotation_deg": float(np.degrees(ang)), "scale": sc,
            "residual_max_c": float(r.max()), "residual_rms_c": float(np.sqrt(np.mean(r**2))),
            "residual_max_within_2pct_c_of_le": float(r[near].max()), "points_used": int(sel.sum())}


def nose_exact(fit: dict) -> tuple[Nose, float]:
    """The formula in the raw D25 frame; sigma = 0 at the curve point nearest the raw LE point."""
    rot, sc, shift = rotation(np.radians(fit["rotation_deg"])), fit["scale"], np.array(fit["shift_c"])
    up, lo = naca4_branch(True), naca4_branch(False)
    n = nose_two_sided(up, lo, s_max=0.3, scale=sc, rot=rot)
    s = np.linspace(0.0, 0.3, N_SIDE_DENSE)
    P = similarity(np.vstack([lo(s[::-1]), up(s)]), sc, rot, shift)
    i0 = int(np.argmin(np.linalg.norm(P, axis=1)))
    return Nose(n.sigma - n.sigma[i0], n.kappa, n.theta - n.theta[i0]), float(np.linalg.norm(P[i0]))


# --- the prototype fix (this script only) --------------------------------------------------------

def apex(spl, t: np.ndarray, i_le: int) -> float:
    """Parameter of the spline point farthest from the trailing-edge midpoint (1, 0): there the
    tangent is square to the chord, which the sqrt(x) section assumes."""
    g = lambda q: float(np.dot(spl(q) - [1.0, 0.0], spl(q, 1)))  # noqa: E731
    return brentq(g, t[i_le - 1], t[i_le + 1], xtol=1e-15)


def apex_frame(spl, t: np.ndarray, i_le: int) -> dict:
    """The D25 frame moved to the spline apex: map from the raw D25 frame to the new frame."""
    ts = apex(spl, t, i_le)
    le = spl(ts)
    d = np.array([1.0, 0.0]) - le
    sigma_le = float(np.sign(t[i_le] - ts) * abs(_arc(spl, ts, t[i_le])))   # + when the apex is on the upper side
    return {"t": ts, "le": le, "scale": float(np.linalg.norm(d)), "angle": float(np.arctan2(d[1], d[0])),
            "apex_sigma_pct": 100 * sigma_le}


def fixed_airfoil(name: str, spl, t: np.ndarray, i_le: int, n_side: int = 100):
    """Prototype: LE at the spline apex; both sides sampled from the raw spline at the cosine x.
    The trailing-edge end is clamped (not studied here)."""
    fr = apex_frame(spl, t, i_le)
    to_new = lambda q: (spl(q) - fr["le"]) @ rotation(-fr["angle"]).T / fr["scale"]  # noqa: E731
    x = cosine_x(n_side)
    ys = []
    for t_end in (t[0], t[-1]):                                    # upper side, then lower side
        tt = np.linspace(fr["t"], t_end, 20001)
        px = to_new(tt)[:, 0]
        y = np.zeros_like(x)
        for i, xi in enumerate(x[1:], start=1):
            j = int(np.argmax(px >= xi)) if np.any(px >= xi) else -1
            if j <= 0:                                             # beyond the side's end: clamp
                y[i] = to_new(tt[-1:])[0, 1]
                continue
            lo_t, hi_t = sorted((tt[j - 1], tt[j]))
            q = brentq(lambda v: to_new(np.array([v]))[0, 0] - xi, lo_t, hi_t, xtol=1e-15)
            y[i] = to_new(np.array([q]))[0, 1]
        ys.append(y)
    return Airfoil(name, x, ys[0], ys[1]), fr


def apex_pchip_airfoil(name: str, p: np.ndarray, spl, t: np.ndarray, i_le: int, n_side: int = 100):
    """Diagnostic: LE at the spline apex, sides still resampled as now (PCHIP in sqrt(x) through
    the raw points, x kept increasing, last point at x = 1)."""
    fr = apex_frame(spl, t, i_le)
    q = (p - fr["le"]) @ rotation(-fr["angle"]).T / fr["scale"]
    x = cosine_x(n_side)
    ys = []
    for side in (np.vstack([[0.0, 0.0], q[t < fr["t"]][::-1]]), np.vstack([[0.0, 0.0], q[t > fr["t"]]])):
        xs, yv = np.clip(side[:, 0], 0.0, None), side[:, 1]
        keep = np.concatenate([[True], xs[1:] > np.maximum.accumulate(xs)[:-1] + 1e-12])
        xs, yv = xs[keep], yv[keep]
        xs[-1] = 1.0
        ys.append(PchipInterpolator(np.sqrt(xs), yv)(np.sqrt(x)))
    return Airfoil(name, x, ys[0], ys[1]), fr


def nose_moved(af: Airfoil, fr: dict) -> Nose:
    """A section built in the apex frame, its loft mapped back into the raw D25 frame,
    sigma = 0 at the raw LE point."""
    up, lo = loft_curves(af)
    n = nose_two_sided(up, lo, scale=fr["scale"], rot=rotation(fr["angle"]))
    return Nose(n.sigma + fr["apex_sigma_pct"] / 100, n.kappa, n.theta)


# --- per airfoil ------------------------------------------------------------------------------------

def diff_pct(a: dict, ref: dict) -> list[float]:
    return [float(100 * (x - r) / r) for x, r in zip(a["T_deg"], ref["T_deg"])]


def study(name: str) -> tuple[dict, dict]:
    pts = A.raw_points(name)
    p, i_le = d25(pts)
    spl, t, il = raw_spline(p, i_le)
    curves = {"raw": nose_raw(spl, t, il), "raw5": nose_raw(*raw_spline(p, i_le, quintic=True))}

    af = load_airfoil(name)
    assert np.allclose([af.yu[0], af.yl[0]], 0.0) and np.allclose(p[i_le], 0.0)
    up, lo = loft_curves(af)
    curves["built"] = nose_two_sided(up, lo)
    curves["built_avg"] = nose_two_sided(*avg_knot_curves(af))

    out = {"source": str(Path(A.source(name)).relative_to(REPO)) if A.find_file(name) else A.source(name),
           "n_points": int(len(pts))}
    if name == "naca4415":
        fit = fit_exact(p)
        curves["exact"], fit["raw_le_to_formula_curve_c"] = nose_exact(fit)
        out["exact_fit"] = fit

    af_fix, fr = fixed_airfoil(name, spl, t, il, 100)
    curves["fixed"] = nose_moved(af_fix, fr)
    curves["fixed200"] = nose_moved(*fixed_airfoil(name, spl, t, il, 200))
    curves["apex_pchip"] = nose_moved(*apex_pchip_airfoil(name, p, spl, t, il))

    # the raw points next to the LE, the spline apex, and the turning between the apex and the LE
    # point: the angle the built section forces into the first gaps (> 0: apex on the lower side)
    r = curves["raw"]
    out["raw_gap_upper_pct"] = 100 * abs(_arc(spl, t[il - 1], t[il]))
    out["raw_gap_lower_pct"] = 100 * abs(_arc(spl, t[il], t[il + 1]))
    out["apex_sigma_pct"] = fr["apex_sigma_pct"]
    out["tangent_tilt_at_le_deg"] = float(-np.degrees(np.interp(fr["apex_sigma_pct"] / 100, r.sigma, r.theta)))
    out["fix_moves_le_pct"] = float(100 * np.linalg.norm(fr["le"]))
    out["fix_turns_chord_deg"] = float(np.degrees(fr["angle"]))
    out["built_le_one_sided"] = one_sided_le(up, lo)
    out["fixed_le_one_sided"] = one_sided_le(*loft_curves(af_fix), scale=fr["scale"])

    out["curves"] = {k: measures(v) for k, v in curves.items()}
    ref = out["curves"]["raw"]
    for k, v in out["curves"].items():
        if k != "raw":
            v["T_diff_vs_raw_pct"] = diff_pct(v, ref)
        if "exact" in out["curves"] and k != "exact":
            v["T_diff_vs_exact_pct"] = diff_pct(v, out["curves"]["exact"])
    out["peaks"] = {k: peaks(v) for k, v in curves.items()}
    out["profile_kappa"] = {k: profile(v) for k, v in curves.items()}
    for k in ("built", "fixed", "fixed200"):
        out[f"{k}_passes"] = bool(np.all(np.abs(out["curves"][k]["T_diff_vs_raw_pct"]) < LIMIT_PCT))
    return out, curves


# --- the Stage 2 nose solve with the built and the fixed section --------------------------------------

@contextlib.contextmanager
def fixed_sections(name: str):
    """Swap the fixed section in for `name` while a wing is built (cfdauto itself is not changed)."""
    p, i_le = d25(A.raw_points(name))
    spl, t, il = raw_spline(p, i_le)
    af, _ = fixed_airfoil(name, spl, t, il, 100)       # 101 points per side: the wing's other sections
    orig = S.load_airfoil
    S.load_airfoil = lambda n, *a, **k: af if n == name else orig(n, *a, **k)
    try:
        yield
    finally:
        S.load_airfoil = orig


def stage2_nose_line() -> dict:
    """Largest turning per ring node against the nose spacing on the Stage 2 page's NACA 4415 station
    (figure 'nose_solve'), and where the worst node sits."""
    from cfdauto.mesh.laws import rules
    from cfdauto.mesh.ring import RingSpec, Section, build_ring, cells_per_side, nose_turning, turning
    from cfdauto.mesh.surface import build_surface, wing_from_set

    wtype, wset, idx, j = STAGE2_WING
    rc = rules("C")
    w = wing_from_set(wtype, wset, idx)
    st = build_surface(w.loft, 3.0e5, "C").stations[j]
    with fixed_sections("naca4415"):
        w_fix = wing_from_set(wtype, wset, idx)
    hs = np.geomspace(2e-5, 5e-3, 40)
    out = {"wing": f"{wtype} {wset} {idx}, station {j}", "v": float(st["v"]), "chord_m": float(st["chord_m"]),
           "h_band_c": float(st["h_band_c"]), "sections_either_side": [s.airfoil.name for s in w.loft.stations[:2]],
           "h_le_pct": [float(100 * h) for h in hs]}
    for key, wing in (("built", w), ("fixed", w_fix)):
        sec = Section.at(wing.loft, st["v"], rc.dense_per_side)
        c = sec.chord
        worst, where, cells = [], [], []
        for h in hs:
            sp = RingSpec(h * c, st["h_band_c"] * c, rc.max_spacing_c * c, rc.te_spacing_c * c)
            n = int(np.ceil(cells_per_side(sec, sp, rc))) + 1
            ring = build_ring(sec, sp, rc, n)["ring"]
            tn = turning(ring)
            tn[[0, 2 * n - 2]] = 0.0
            k = int(np.argmax(tn))
            seg = np.linalg.norm(np.diff(ring, axis=0), axis=1)
            arc = np.concatenate([[0.0], np.cumsum(seg)])
            worst.append(nose_turning(ring, n))
            where.append(float(100 * (arc[n - 1] - arc[k]) / c))     # + upper, - lower (ring: upper TE -> LE -> lower TE)
            cells.append(float(100 * 0.5 * (seg[k - 1] + seg[k]) / c))
        ok = [h for h, tdeg in zip(out["h_le_pct"], worst) if tdeg <= rc.nose_turning_deg]
        out[key] = {"turning_deg": worst, "worst_node_sigma_pct": where, "worst_node_cell_pct": cells,
                    "largest_h_le_pct_meeting_10deg": float(max(ok)) if ok else None}
    return out


# --- the figure ------------------------------------------------------------------------------------

INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e4e2dc", "#fcfcfb"
C_FIX, C_BUILT = "#2a78d6", "#eb6834"          # reference palette slots 1 and 2 (validated, light)


def figure(res: dict, keep: dict) -> None:
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2,
                         "ytick.color": INK2, "axes.titlesize": 10, "axes.titlecolor": INK, "legend.fontsize": 8,
                         "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURF,
                         "axes.facecolor": SURF, "savefig.facecolor": SURF})
    fig = plt.figure(figsize=(15, 9.2), dpi=130)
    gs = fig.add_gridspec(2, 12, height_ratios=[1, 1.05], hspace=0.42, wspace=1.6)
    show = ("naca4415", "e387", "sd7032", "mh104")
    for i, name in enumerate(show):
        a = fig.add_subplot(gs[0, 3 * i:3 * i + 3])
        cv, r = keep[name], res["airfoils"][name]
        ref = cv["raw"]
        top = 2.3 * np.max(ref.kappa[np.abs(ref.sigma) <= PROF_C])
        lines = [("raw", "raw file (cubic spline)", INK2, "-", 1.6), ("exact", "formula", INK, ":", 1.4),
                 ("built", "built now", C_BUILT, "-", 1.4), ("fixed200", "fix (apex, 201 points/side)", C_FIX, "--", 1.4)]
        for key, lab, col, ls, lw in lines:
            if key not in cv:
                continue
            n = cv[key]
            m = np.abs(n.sigma) <= PROF_C
            a.plot(100 * n.sigma[m], np.minimum(n.kappa[m], top * 1.2), ls=ls, color=col, lw=lw, label=lab)
        a.set_xlim(-2, 2)
        a.set_ylim(0, top)
        a.axvline(0, color=GRID, lw=0.8, zorder=0)
        a.grid(True, color=GRID, lw=0.5)
        b = cv["built"]
        k_le = float(np.max(b.kappa[np.abs(b.sigma) < 1e-9]))
        if k_le > top:
            side = "upper" if r["built_le_one_sided"]["R_le_upper_c"] < r["built_le_one_sided"]["R_le_lower_c"] else "lower"
            a.annotate(f"built at the LE ({side} side):\n{k_le:.0f}/c, R = {1 / k_le:.4f} c", xy=(0, top),
                       xytext=(0.12 if side == "upper" else -0.12, 0.93 * top), ha="left" if side == "upper" else "right",
                       va="top", fontsize=7.5, color=INK2, arrowprops={"arrowstyle": "->", "color": MUTED, "lw": 0.8})
        if name == "naca4415":
            pk = max((q for q in r["peaks"]["built"] if q["sigma_pct"] < -0.3), key=lambda q: q["kappa"])
            a.annotate(f"bump {pk['kappa']:.1f}/c\n(raw {np.interp(pk['sigma_pct'] / 100, ref.sigma, ref.kappa):.1f}/c)",
                       xy=(pk["sigma_pct"], pk["kappa"]), xytext=(-1.95, 0.80 * top), fontsize=7.5, color=INK2,
                       arrowprops={"arrowstyle": "->", "color": MUTED, "lw": 0.8})
        a.set_title(f"{LABEL[name]} ({r['n_points']} points): nose curvature\n"
                    f"apex {r['apex_sigma_pct']:+.3f} % c from the LE point, tilt {r['tangent_tilt_at_le_deg']:+.1f}°",
                    fontsize=9.5)
        a.set_xlabel("arc from the LE point [% c]; − lower, + upper", fontsize=8.5)
        if i == 0:
            a.set_ylabel("curvature [1/c]")
            fig.legend(*a.get_legend_handles_labels(), loc="upper center", ncol=4, frameon=False,
                       bbox_to_anchor=(0.5, 0.975), fontsize=8.5)

    h = np.array(H_PCT)
    # (e) the current build against the raw file
    a = fig.add_subplot(gs[1, 0:4])
    a.axhspan(0.95, 1.05, color=GRID, alpha=0.8, lw=0, zorder=0)
    a.text(0.58, 0.895, "±5 % band (criterion)", ha="right", va="center", fontsize=7.5, color=INK2)
    quiet = []
    for name in AIRFOILS:
        c = res["airfoils"][name]["curves"]
        ratio = np.array(c["built"]["T_deg"]) / np.array(c["raw"]["T_deg"])
        a.plot(h, ratio, "-o", color=C_BUILT, lw=1.1, ms=3.5, alpha=0.9)
        if ratio[0] > 1.4 or name == "mh60":
            a.text(0.037, ratio[0], LABEL[name], ha="right", va="center", fontsize=7.5, color=INK2)
        else:
            quiet.append(LABEL[name])
    a.set_xscale("log")
    a.set_yscale("log")
    a.set_xticks(h, [f"{v:.2f}" for v in h])
    a.set_yticks([0.9, 1, 1.5, 2, 3, 4, 5], ["0.9", "1", "1.5", "2", "3", "4", "5"])
    a.minorticks_off()
    a.set_xlim(0.022, 0.6)
    a.set_ylim(0.85, 6.2)
    a.grid(True, color=GRID, lw=0.5)
    a.set_xlabel("cell arc length h [% c]")
    a.set_ylabel("T built / T raw  (largest turning per cell)")
    a.set_title("Built now, all ten: turning per cell against the raw file")
    a.text(0.98, 0.97, "one line per airfoil; the lines near 1.15–1.25:\n" + ", ".join(quiet[:3]) + ",\n"
           + ", ".join(quiet[3:]), transform=a.transAxes, ha="right", va="top", fontsize=7.5, color=INK2)

    # (f) the fix against the raw file
    a = fig.add_subplot(gs[1, 4:8])
    a.axhspan(-LIMIT_PCT, LIMIT_PCT, color=GRID, alpha=0.8, lw=0, zorder=0)
    for key, ls, lab in (("fixed", "--", "fix, 101 points per side (as now)"), ("fixed200", "-", "fix, 201 points per side")):
        for i, name in enumerate(AIRFOILS):
            d = res["airfoils"][name]["curves"][key]["T_diff_vs_raw_pct"]
            a.plot(h, d, ls=ls, marker="o", color=C_FIX, lw=1.1 if key == "fixed200" else 0.9, ms=3.0,
                   alpha=1.0 if key == "fixed200" else 0.55, label=lab if i == 0 else None)
    for key, dy in (("fixed", 0.0), ("fixed200", 0.0)):
        d = res["airfoils"]["mh60"]["curves"][key]["T_diff_vs_raw_pct"][0]
        a.text(0.042, d + dy, f" MH 60: {d:+.1f} %", ha="left", va="center", fontsize=7.5, color=INK2)
    a.set_xscale("log")
    a.set_xticks(h, [f"{v:.2f}" for v in h])
    a.minorticks_off()
    a.set_xlim(0.035, 0.6)
    a.set_ylim(-11, 6)
    a.grid(True, color=GRID, lw=0.5)
    a.set_xlabel("cell arc length h [% c]")
    a.set_ylabel("(T fix − T raw) / T raw [%]")
    a.set_title("With the fix (apex + spline), all ten")
    a.legend(loc="lower right", frameon=False)
    a.text(0.6, 4.6, "±5 % (criterion)", ha="right", va="center", fontsize=7.5, color=INK2)

    # (g) the Stage 2 nose solve
    a = fig.add_subplot(gs[1, 8:12])
    s2 = res["stage2_nose_line"]
    hl = np.array(s2["h_le_pct"])
    a.axhline(10.0, color=MUTED, lw=1.0, ls="--")
    a.text(0.0022, 10.15, "target 10°", fontsize=7.5, color=INK2, va="bottom")
    for key, col, lab in (("built", C_BUILT, "built now"), ("fixed", C_FIX, "fix (apex + spline)")):
        a.semilogx(hl, s2[key]["turning_deg"], "-o", color=col, lw=1.1, ms=3.0, label=lab)
    a.set_xlim(0.0015, 0.6)
    a.set_ylim(5, 12.5)
    a.grid(True, color=GRID, lw=0.5)
    a.set_xlabel("nose spacing [% c]")
    a.set_ylabel("largest turning per node [°]")
    a.set_title("Stage 2 nose solve, NACA 4415 station (wing 35, station 21)")
    lo_b = [v for v, hh in zip(s2["built"]["worst_node_sigma_pct"], hl) if hh < 0.2]
    a.text(0.03, 0.97, f"below 0.2 % c both lines are flat: the worst node sits\n"
           f"{-max(lo_b):.1f}–{-min(lo_b):.1f} % c down the lower side, where cells\n"
           f"are set by growth 1.2, not by the nose spacing",
           transform=a.transAxes, ha="left", va="top", fontsize=7.5, color=INK2)
    a.legend(loc="lower right", frameon=False)
    fig.suptitle("Decision 64: the built nose against the raw file, one curvature method (7 Nov 2026)",
                 fontsize=11.5, color=INK, y=1.0)
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, bbox_inches="tight")
    plt.close(fig)


# --- main ------------------------------------------------------------------------------------------

_NUM_LIST = re.compile(r"\[\s+(-?[\d.eE+-]+(?:,\s+-?[\d.eE+-]+)*)\s+\]")


def dumps(obj) -> str:
    """json with indent 1, but every list of plain numbers on one line."""
    return _NUM_LIST.sub(lambda m: "[" + ", ".join(v.strip() for v in m.group(1).split(",")) + "]",
                         json.dumps(obj, indent=1))


def git_head() -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> None:
    res = {"meta": {
        "date": "2026-11-07", "decision": 64, "git_base": git_head(),
        "criterion": f"|T_built(h) - T_raw(h)| / T_raw(h) < {LIMIT_PCT} % for every h on all ten airfoils",
        "h_pct": list(H_PCT), "window_pct": 100 * WIN_C, "profile_sigma_pct": [-100 * PROF_C, 100 * PROF_C, PROF_N],
        "units": "lengths in the D25 chord of the raw file (c); kappa in 1/c; T in degrees",
        "sigma": "arc length from the Stage 1 LE point (farthest raw point from the TE midpoint), + upper, - lower",
        "tangent_tilt_at_le_deg": "turning of the raw spline between its apex and the LE point (> 0: apex on the lower side)",
        "loft_backend": "numpy (pyGeo not installed); built_avg checks the other knot rule",
        "numpy": np.__version__, "scipy": scipy.__version__,
        "naca_derivative_check_rel_err": check_naca_derivatives(),
        "polyline_check_max_diff_deg": polyline_check()},
        "airfoils": {}}
    keep = {}
    for name in AIRFOILS:
        res["airfoils"][name], keep[name] = study(name)
        c = res["airfoils"][name]["curves"]
        print(f"{name:10s} R_min raw {c['raw']['R_min_c']:.4f} built {c['built']['R_min_c']:.4f} "
              f"fix200 {c['fixed200']['R_min_c']:.4f} | built-raw % " +
              " ".join(f"{v:+7.1f}" for v in c["built"]["T_diff_vs_raw_pct"]) +
              " | fix200-raw % " + " ".join(f"{v:+5.1f}" for v in c["fixed200"]["T_diff_vs_raw_pct"]))
    res["verdict"] = {k: [n for n, a in res["airfoils"].items() if not a[f"{k}_passes"]]
                      for k in ("built", "fixed", "fixed200")}
    res["verdict"] = {"fails_" + k: v for k, v in res["verdict"].items()}
    res["verdict"]["decision_64_closes_without_fix"] = not res["verdict"]["fails_built"]
    res["stage2_nose_line"] = stage2_nose_line()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(dumps(res))
    figure(res, keep)
    print("wrote", OUT_JSON.relative_to(ROOT.parent), "and", OUT_PNG.relative_to(ROOT.parent))
    print(json.dumps(res["verdict"]))


if __name__ == "__main__":
    main()
