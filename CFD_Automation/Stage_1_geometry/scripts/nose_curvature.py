"""Nose curvature: the raw airfoil files against the Stage 1 built sections (decision 64).

One curvature method for every curve, so the answer depends on no frame and no formula: the
curvature kappa(sigma) along the arc length sigma, from each curve's own first and second
derivatives. sigma = 0 is the farthest raw point from the trailing-edge midpoint (the old rule D25
leading edge), + on the upper side, - on the lower side. Every curve is put in the frame of that
point (unit chord), so lengths are in that chord c.

Curves:
  raw         cubic interpolating spline (not-a-knot) through the raw file points, x and y against
              the cumulative chord length;
  raw5        the same with a quintic spline (how much the reference itself depends on the spline);
  old         the section by the rule before decision 64 (frozen copy below: LE at the farthest raw
              point, PCHIP in sqrt(x) per side, 101 points per side), as the loft holds it;
  new         the section by cfdauto now (load_airfoil: LE at the apex of one cubic spline through the
              raw points, both sides sampled from it, 201 points per side), as the loft holds it;
  new101      the new rule with 101 points per side (why 201 are needed);
  new_avg     the new section points with averaging knots (Piegl and Tiller, eq. 9.8), the other
              usual knot rule;
  apex_pchip  diagnostic: LE at the apex, but the sides still resampled by PCHIP as before;
  exact       NACA 4415 only: the formula (m 0.04, p 0.4, t 0.15, open trailing edge -0.1015,
              thickness normal to the camber line), exact derivatives, placed on the file by a
              least-squares similarity fit (raw points with x < 0.6).
"As the loft holds it": two copies lofted by cfdauto.geometry.loft.build_loft (numpy backend), the
loft's own B-splines in s = sqrt(x/c).

Mesh number: T(h) = the largest turning a cell of arc length h gets near the nose = the largest
integral of kappa over a window [sigma, sigma + h] inside |sigma| <= 3 % c,
for h = 0.04, 0.10, 0.18, 0.30, 0.50 % c.

Criterion (fixed before computing, 7 Nov 2026): if |T_built(h) - T_raw(h)| / T_raw(h) < 5 % for
every h on all ten airfoils, decision 64 closes with no fix (the built nose is faithful at mesh
scale). Otherwise a fix is made and measured the same way.

Stage 2 check: the nose solve of the Stage 2 page (tapered training wing 35, station 21, NACA 4415):
the largest turning per ring node against the nose spacing, on the wing built by the old rule and
by the new one.

Database pass (--database): every airfoil file on the search path (about 2,180), built by the old
and the new rule; T(h) at h = 0.04 and 0.18 % c against the file's raw spline; the leading-edge
move and the chord turn of the new rule.

    cd CFD_Automation && python Stage_1_geometry/scripts/nose_curvature.py              # under 1 min
    cd CFD_Automation && python Stage_1_geometry/scripts/nose_curvature.py --database   # about 4 min more

Writes Stage_1_geometry/data/studies/nose_curvature.json and Stage_1_geometry/docs/nose_curvature.png.
Without --database the database results already in the JSON are kept.
"""

from __future__ import annotations

import contextlib
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import numpy as np
import scipy
from scipy.interpolate import CubicSpline, PchipInterpolator, make_interp_spline
from scipy.optimize import least_squares
from scipy.signal import find_peaks
from scipy.spatial import cKDTree

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]          # Stage_1_geometry
sys.path.insert(0, str(ROOT.parent))                # CFD_Automation: the cfdauto package

from cfdauto.geometry import airfoils as A  # noqa: E402
from cfdauto.geometry import sections as S  # noqa: E402
from cfdauto.geometry.loft import build_loft  # noqa: E402
from cfdauto.geometry.sections import Airfoil, Station, airfoil_from_points, cosine_x, load_airfoil  # noqa: E402
from cfdauto.paths import REPO  # noqa: E402

AIRFOILS = ("naca4415", "e387", "sd7032", "mh104", "mh61", "mh45", "mh60", "s5010", "la2573a", "naca25118")
LABEL = {"naca4415": "NACA 4415", "e387": "E387", "sd7032": "SD7032", "mh104": "MH 104", "mh61": "MH 61",
         "mh45": "MH 45", "mh60": "MH 60", "s5010": "S5010", "la2573a": "LA2573A", "naca25118": "NACA 25118"}
H_PCT = (0.04, 0.10, 0.18, 0.30, 0.50)    # cell arc lengths [% c]
H_DB_PCT = (0.04, 0.18)                   # the database pass
WIN_C = 0.03                              # windows and the curvature peak: within 3 % c of arc
PROF_C = 0.02                             # stored profile: +-2 % c
PROF_N = 401
LIMIT_PCT = 5.0                           # the criterion
N_DENSE = 30001                           # evaluation points per side (arc step about 1e-6 c)
N_DENSE_DB = 8001                         # the same, for the database pass
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


# --- the raw file in the frame of its farthest point -----------------------------------------------

def d25(pts: np.ndarray, strict: bool = True):
    """LE = raw point farthest from the trailing-edge midpoint, chord along x, unit chord."""
    te_mid = 0.5 * (pts[0] + pts[-1])
    i_le = int(np.argmax(np.linalg.norm(pts - te_mid, axis=1)))
    le = pts[i_le]
    d = te_mid - le
    p = (pts - le) @ rotation(-float(np.arctan2(d[1], d[0]))).T / float(np.linalg.norm(d))
    if strict and np.mean(p[: i_le + 1, 1]) < np.mean(p[i_le:, 1]):
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


def nose_raw(spl, t: np.ndarray, i_le: int, n: int = N_DENSE) -> Nose:
    """tau = -t, so the curve runs from the lower side to the upper side."""
    tl = t[i_le]
    tt = np.concatenate([np.linspace(tl + 0.045, tl, n), np.linspace(tl, tl - 0.045, n)[1:]])
    tt = np.clip(tt, t[0], t[-1])
    return nose_from(-tt, -spl(tt, 1), spl(tt, 2), n - 1)


def _arc(spl, a: float, b: float, n: int = 2001) -> float:
    q = np.linspace(a, b, n)
    d = spl(q, 1)
    sp = np.hypot(d[:, 0], d[:, 1])
    return float(np.sum(0.5 * (sp[1:] + sp[:-1]) * np.diff(q)))


# --- the sections as the loft holds them ------------------------------------------------------------

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


def nose_two_sided(up, lo, s_max: float = 0.3, scale: float = 1.0, rot=np.eye(2), n: int = N_DENSE) -> Nose:
    """A curve given as two branches from the nose (parameter s >= 0 on each), joined at s = 0:
    tau = -s on the lower branch, +s on the upper. scale and rot map derivatives into the raw frame.
    sigma = 0 appears twice: the lower branch's kappa(0-), then the upper branch's kappa(0+)."""
    s = np.linspace(0.0, s_max, n)
    dP = similarity(np.vstack([-lo(s[::-1], 1), up(s, 1)]), scale, rot, 0.0)
    ddP = similarity(np.vstack([lo(s[::-1], 2), up(s, 2)]), scale, rot, 0.0)
    return nose_from(np.concatenate([-s[::-1], s]), dP, ddP, n)


def one_sided_le(up, lo, scale: float = 1.0) -> dict:
    """Curvature radius of each branch at the leading edge itself (s = 0)."""
    out = {}
    for name, c in (("upper", up), ("lower", lo)):
        d1, d2 = c(np.array([0.0]), 1)[0], c(np.array([0.0]), 2)[0]
        out[f"R_le_{name}_c"] = float(scale * np.hypot(*d1) ** 3 / abs(d1[0] * d2[1] - d1[1] * d2[0]))
    return out


def polyline_check(names=("naca4415", "sd7032", "mh60")) -> float:
    """T(h) of the new section from a dense polyline of loft.upper / loft.lower points (the way the
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


# --- the old rule (before decision 64), frozen here for the comparison ----------------------------------

def old_airfoil(name: str, pts: np.ndarray | None = None, n_side: int = 100) -> Airfoil:
    """cfdauto's airfoil_from_points up to commit 382274f0: LE at the farthest raw point, each side
    resampled by PCHIP in sqrt(x) through the raw points, 101 points per side."""
    pts = A.raw_points(name) if pts is None else pts
    te_mid = 0.5 * (pts[0] + pts[-1])
    i_le = int(np.argmax(np.linalg.norm(pts - te_mid, axis=1)))
    le = pts[i_le]
    d = te_mid - le
    p = (pts - le) @ rotation(-float(np.arctan2(d[1], d[0]))).T / float(np.linalg.norm(d))
    upper, lower = p[: i_le + 1][::-1], p[i_le:]
    if np.mean(upper[:, 1]) < np.mean(lower[:, 1]):
        upper, lower = lower, upper
    x = cosine_x(n_side)
    return Airfoil(name, x, _old_resample(upper, x), _old_resample(lower, x))


def _old_resample(side: np.ndarray, x: np.ndarray) -> np.ndarray:
    xs = np.clip(side[:, 0], 0.0, None)
    ys = side[:, 1]
    keep = np.concatenate([[True], xs[1:] > np.maximum.accumulate(xs)[:-1] + 1e-12])
    xs, ys = xs[keep], ys[keep]
    bad = A.suspect_points(np.column_stack([xs, ys]))
    if len(bad):
        xs, ys = np.delete(xs, bad), np.delete(ys, bad)
    xs[0], ys[0] = 0.0, 0.0
    xs[-1] = 1.0
    return PchipInterpolator(np.sqrt(xs), ys)(np.sqrt(x))


# --- the new rule's frame, from cfdauto's own helpers ----------------------------------------------

def new_frame(pts: np.ndarray) -> dict:
    """The frame airfoil_from_points uses now, in terms of the old one (farthest raw point): where
    the apex sits (sigma along the cleaned spline, + upper side), the LE move, the chord turn, and
    the map from the new frame into the old one (scale, angle)."""
    te_mid = 0.5 * (pts[0] + pts[-1])
    p = S._clean(pts, te_mid)
    t = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
    spl = CubicSpline(t, p, bc_type="natural")           # as airfoil_from_points
    i = int(np.argmax(np.linalg.norm(p - te_mid, axis=1)))
    t_le = S._apex(spl, t, i, te_mid)
    d_old, d_new = te_mid - p[i], te_mid - spl(t_le)
    c_old = float(np.linalg.norm(d_old))
    a_old, a_new = (float(np.arctan2(d[1], d[0])) for d in (d_old, d_new))
    sigma = float(np.sign(t[i] - t_le) * abs(_arc(spl, t_le, t[i]))) / c_old    # Selig: the upper side first
    return {"apex_sigma_pct": 100 * sigma, "le_move_pct": 100 * abs(sigma),
            "chord_turn_deg": float(np.degrees(a_new - a_old)), "scale": float(np.linalg.norm(d_new)) / c_old,
            "angle": a_new - a_old, "points_dropped": int(len(pts) - len(p)),
            "_check": (spl, t, t_le, te_mid, d_new, a_new)}


def check_new_frame(af: Airfoil, fr: dict) -> float:
    """Largest difference between the section rebuilt from new_frame and load_airfoil's (should be 0)."""
    spl, t, t_le, te_mid, d, a = fr["_check"]
    frame = lambda q: (spl(q) - spl(t_le)) @ rotation(-a).T / np.linalg.norm(d)  # noqa: E731
    up, lo = S._resample(frame, t_le, t[0], t[1], af.x), S._resample(frame, t_le, t[-1], t[-2], af.x)
    if np.mean(up) < np.mean(lo):
        up, lo = lo, up
    return float(max(np.abs(up - af.yu).max(), np.abs(lo - af.yl).max()))


def apex_pchip_airfoil(name: str, pts: np.ndarray, fr: dict, n_side: int = 100) -> Airfoil:
    """Diagnostic: LE at the apex, the sides still resampled by PCHIP through the raw points."""
    spl, t, t_le, te_mid, d, a = fr["_check"]
    q = (pts - spl(t_le)) @ rotation(-a).T / np.linalg.norm(d)
    i = int(np.argmax(np.linalg.norm(pts - te_mid, axis=1)))
    cut = i if fr["apex_sigma_pct"] > 0 else i + 1          # the first raw point on the lower side
    x = cosine_x(n_side)
    ys = [_old_resample(np.vstack([[0.0, 0.0], side]), x) for side in (q[:cut][::-1], q[cut:])]
    return Airfoil(name, x, ys[0], ys[1])


def nose_new(af: Airfoil, fr: dict, n: int = N_DENSE) -> Nose:
    """A section built in the new frame, its loft mapped into the old frame, sigma = 0 at the
    farthest raw point."""
    n_ = nose_two_sided(*loft_curves(af), scale=fr["scale"], rot=rotation(fr["angle"]), n=n)
    return Nose(n_.sigma + fr["apex_sigma_pct"] / 100, n_.kappa, n_.theta)


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
    """Similarity map formula frame -> raw frame, fitted to the raw points with x < 0.6."""
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


def nose_exact(fit: dict) -> tuple[Nose, float, float]:
    """The formula in the raw frame; sigma = 0 at the curve point nearest the raw LE point.
    Also returns the distance of that point from the raw LE point and the sigma of the formula's origin."""
    rot, sc, shift = rotation(np.radians(fit["rotation_deg"])), fit["scale"], np.array(fit["shift_c"])
    up, lo = naca4_branch(True), naca4_branch(False)
    n = nose_two_sided(up, lo, s_max=0.3, scale=sc, rot=rot)
    s = np.linspace(0.0, 0.3, N_DENSE)
    P = similarity(np.vstack([lo(s[::-1]), up(s)]), sc, rot, shift)
    i0 = int(np.argmin(np.linalg.norm(P, axis=1)))
    n = Nose(n.sigma - n.sigma[i0], n.kappa, n.theta - n.theta[i0])
    return n, float(np.linalg.norm(P[i0])), float(100 * n.sigma[N_DENSE])


# --- per airfoil ------------------------------------------------------------------------------------

def diff_pct(a: dict, ref: dict) -> list[float]:
    return [float(100 * (x - r) / r) for x, r in zip(a["T_deg"], ref["T_deg"])]


def study(name: str) -> tuple[dict, dict]:
    pts = A.raw_points(name)
    p, i_le = d25(pts)
    spl, t, il = raw_spline(p, i_le)
    curves = {"raw": nose_raw(spl, t, il), "raw5": nose_raw(*raw_spline(p, i_le, quintic=True))}

    af_old = old_airfoil(name, pts)
    up_old, lo_old = loft_curves(af_old)
    curves["old"] = nose_two_sided(up_old, lo_old)

    fr = new_frame(pts)
    af_new = load_airfoil(name)
    rebuilt = check_new_frame(af_new, fr)
    assert rebuilt < 1e-13, f"{name}: new_frame does not reproduce load_airfoil ({rebuilt:.1e})"
    curves["new"] = nose_new(af_new, fr)
    curves["new101"] = nose_new(airfoil_from_points(name, pts, 100), fr)
    n_avg = nose_two_sided(*avg_knot_curves(af_new), scale=fr["scale"], rot=rotation(fr["angle"]))
    curves["new_avg"] = Nose(n_avg.sigma + fr["apex_sigma_pct"] / 100, n_avg.kappa, n_avg.theta)
    curves["apex_pchip"] = nose_new(apex_pchip_airfoil(name, pts, fr), fr)

    out = {"source": str(Path(A.source(name)).relative_to(REPO)) if A.find_file(name) else A.source(name),
           "n_points": int(len(pts)), "points_dropped_by_new_rule": fr["points_dropped"]}
    if name == "naca4415":
        fit = fit_exact(p)
        curves["exact"], fit["raw_le_to_formula_curve_c"], fit["formula_origin_sigma_pct"] = nose_exact(fit)
        out["exact_fit"] = fit

    # the raw points next to the LE point, the apex, and the turning between the apex and the LE point:
    # the angle the old rule forced into the first gaps (> 0: apex on the lower side)
    r = curves["raw"]
    out["raw_gap_upper_pct"] = 100 * abs(_arc(spl, t[il - 1], t[il]))
    out["raw_gap_lower_pct"] = 100 * abs(_arc(spl, t[il], t[il + 1]))
    out["apex_sigma_pct"] = fr["apex_sigma_pct"]
    out["tangent_tilt_at_le_deg"] = float(-np.degrees(np.interp(fr["apex_sigma_pct"] / 100, r.sigma, r.theta)))
    out["le_move_pct"] = fr["le_move_pct"]
    out["chord_turn_deg"] = fr["chord_turn_deg"]
    out["old_le_one_sided"] = one_sided_le(up_old, lo_old)
    out["new_le_one_sided"] = one_sided_le(*loft_curves(af_new), scale=fr["scale"])

    out["curves"] = {k: measures(v) for k, v in curves.items()}
    ref = out["curves"]["raw"]
    for k, v in out["curves"].items():
        if k != "raw":
            v["T_diff_vs_raw_pct"] = diff_pct(v, ref)
        if "exact" in out["curves"] and k != "exact":
            v["T_diff_vs_exact_pct"] = diff_pct(v, out["curves"]["exact"])
    out["peaks"] = {k: peaks(v) for k, v in curves.items()}
    out["profile_kappa"] = {k: profile(v) for k, v in curves.items() if k not in ("new_avg", "apex_pchip")}
    for k in ("old", "new", "new101", "apex_pchip"):
        out[f"{k}_passes"] = bool(np.all(np.abs(out["curves"][k]["T_diff_vs_raw_pct"]) < LIMIT_PCT))
    return out, curves


# --- the Stage 2 nose solve on the old and the new wing ----------------------------------------------

@contextlib.contextmanager
def old_sections():
    """Build wings by the old rule while inside (every section: the loft needs one x for all)."""
    orig = S.load_airfoil
    S.load_airfoil = lambda n, *a, **k: old_airfoil(n)
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
    with old_sections():
        w_old = wing_from_set(wtype, wset, idx)
        st = build_surface(w_old.loft, 3.0e5, "C").stations[j]
    w_new = wing_from_set(wtype, wset, idx)
    hs = np.geomspace(2e-5, 5e-3, 40)
    out = {"wing": f"{wtype} {wset} {idx}, station {j}", "v": float(st["v"]), "chord_m": float(st["chord_m"]),
           "h_band_c": float(st["h_band_c"]), "sections_either_side": [s.airfoil.name for s in w_old.loft.stations[:2]],
           "h_le_pct": [float(100 * h) for h in hs]}
    for key, wing in (("old", w_old), ("new", w_new)):
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


# --- every airfoil file: old and new rule ---------------------------------------------------------------

def _t_pair(n: Nose) -> list[float]:
    return [turning_max(n.sigma, n.theta, h / 100)[0] for h in H_DB_PCT]


def _why(e: Exception) -> str:
    return f"{type(e).__name__}: {str(e).splitlines()[0][:120] if str(e) else ''}"


HOOK_KAPPA = -1000.0      # a "hook": curvature below -1000/c within 3 % c of the LE (a tiny loop or fold)


def _config_sections() -> list[str]:
    """Every section the wing families and the published wings name (wing.yaml, published_wings.yaml)."""
    import yaml

    names: set[str] = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("airfoils", "full_airfoils"):
                    for x in v:
                        names.update(x if isinstance(x, list) else [x])
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    for f in ("wing.yaml", "published_wings.yaml"):
        walk(yaml.safe_load((ROOT / "configs" / f).read_text()))
    return sorted(n for n in names if isinstance(n, str))


def database_pass() -> dict:
    """Old and new rule on every file of the search path; T(h) at H_DB_PCT against the raw spline."""
    names = A.available()
    cols = ["name", "points", "dropped", "T_raw_004", "T_raw_018", "T_raw5_004", "T_raw5_018", "T_old_004", "T_old_018",
            "T_new_004", "T_new_018", "le_move_pct", "chord_turn_deg", "kmin_old", "kmin_new", "crossing_old", "crossing_new"]
    rows, fails = [], {"read": [], "old": [], "new": [], "measure": []}
    for k, name in enumerate(names):
        if k % 250 == 0:
            print(f"  database {k}/{len(names)}", flush=True)
        try:
            pts = A.raw_points(name)
        except Exception as e:  # noqa: BLE001
            fails["read"].append([name, _why(e)])
            continue
        built = {}
        for key, make in (("old", lambda: old_airfoil(name, pts)), ("new", lambda: airfoil_from_points(name, pts))):
            try:
                af = make()
                if not np.all(np.isfinite(np.r_[af.yu, af.yl])):
                    raise FloatingPointError("non-finite section points")
                built[key] = af
            except Exception as e:  # noqa: BLE001
                fails[key].append([name, _why(e)])
        rec = dict.fromkeys(cols)
        rec["name"], rec["points"] = name, int(len(pts))
        try:
            p, i_le = d25(pts, strict=False)
            spl, t, il = raw_spline(p, i_le)
            rec["T_raw_004"], rec["T_raw_018"] = _t_pair(nose_raw(spl, t, il, N_DENSE_DB))
            rec["T_raw5_004"], rec["T_raw5_018"] = _t_pair(nose_raw(*raw_spline(p, i_le, quintic=True), N_DENSE_DB))
            for key in ("old", "new"):
                if key not in built:
                    continue
                if key == "old":
                    n = nose_two_sided(*loft_curves(built["old"]), n=N_DENSE_DB)
                else:
                    fr = new_frame(pts)
                    rec["dropped"], rec["le_move_pct"], rec["chord_turn_deg"] = (
                        fr["points_dropped"], fr["le_move_pct"], fr["chord_turn_deg"])
                    n = nose_new(built["new"], fr, N_DENSE_DB)
                rec[f"T_{key}_004"], rec[f"T_{key}_018"] = _t_pair(n)
                rec[f"kmin_{key}"] = float(n.kappa[np.abs(n.sigma) <= WIN_C].min())
                rec[f"crossing_{key}"] = bool(np.any(built[key].thickness[1:-1] <= 0))
        except Exception as e:  # noqa: BLE001
            fails["measure"].append([name, _why(e)])
        rows.append([round(v, 6) if isinstance(v, float) else v for v in (rec[k] for k in cols)])
    return {"columns": cols, "rows": rows, "fails": fails, "summary": database_summary(cols, rows, fails, len(names))}


def _measured(c: dict, rows: list) -> tuple[list, list]:
    """Rows with every T, and among the rest those whose raw spline gives no turning (a broken file)."""
    have = [r for r in rows if None not in (r[c["T_raw_004"]], r[c["T_raw5_004"]], r[c["T_old_004"]], r[c["T_new_004"]])]
    ok = [r for r in have if min(r[c["T_raw_004"]], r[c["T_raw_018"]], r[c["T_raw5_004"]], r[c["T_raw5_018"]]) > 1e-6]
    return ok, [r[0] for r in have if r not in ok]


def database_summary(cols, rows, fails, n_names) -> dict:
    c = {k: i for i, k in enumerate(cols)}
    full, degenerate = _measured(c, rows)

    def dev(r, key, ref="raw"):
        return max(abs(100 * (r[c[f"T_{key}_{h}"]] - r[c[f"T_{ref}_{h}"]]) / r[c[f"T_{ref}_{h}"]]) for h in ("004", "018"))

    d_old, d_new = np.array([dev(r, "old") for r in full]), np.array([dev(r, "new") for r in full])
    spread = np.array([dev(r, "raw5") for r in full])            # quintic against cubic: the reference's own spread
    move = np.array([r[c["le_move_pct"]] for r in full])
    turn = np.array([r[c["chord_turn_deg"]] for r in full])
    hook = {k: {r[0] for r in rows if r[c[f"kmin_{k}"]] is not None and r[c[f"kmin_{k}"]] < HOOK_KAPPA} for k in ("old", "new")}
    cross = {k: sorted(r[0] for r in rows if r[c[f"crossing_{k}"]]) for k in ("old", "new")}
    fail_new = d_new >= LIMIT_PCT
    pct = lambda a: {f"p{q}": float(np.percentile(a, q)) for q in (50, 90, 99)} | {"max": float(a.max())}  # noqa: E731
    order = np.argsort(d_new)[::-1][:10]
    by_name = {r[0]: (i, r) for i, r in enumerate(full)}
    config = {}
    for n in _config_sections():
        if n in by_name:
            i, r = by_name[n]
            config[n] = {"dev_old_pct": float(d_old[i]), "dev_new_pct": float(d_new[i]), "le_move_pct": float(move[i]),
                         "chord_turn_deg": float(turn[i]), "hook_new": n in hook["new"], "crossing_new": n in cross["new"]}
        else:
            config[n] = "no file: built from the NACA formula" if A.find_file(n) is None else "not measured"
    return {
        "files": n_names, "read_failures": len(fails["read"]),
        "why_read_fails": dict(Counter(w.split(": ", 2)[-1] for _, w in fails["read"])),
        "built_old": n_names - len(fails["read"]) - len(fails["old"]),
        "built_new": n_names - len(fails["read"]) - len(fails["new"]),
        "measured_both": len(full), "measure_failures": len(fails["measure"]),
        "raw_spline_gives_no_turning": degenerate,
        "why_old_fails": dict(Counter(w for _, w in fails["old"])),
        "why_new_fails": dict(Counter(w for _, w in fails["new"])),
        "criterion": f"|T_built - T_raw| / T_raw < {LIMIT_PCT} % at h = 0.04 and 0.18 % c",
        "pass_old": int(np.sum(d_old < LIMIT_PCT)), "pass_new": int(np.sum(~fail_new)),
        "pass_old_share_pct": float(100 * np.mean(d_old < LIMIT_PCT)),
        "pass_new_share_pct": float(100 * np.mean(~fail_new)),
        "new_fails_where_quintic_and_cubic_differ_by_5pct_or_more": int(np.sum(fail_new & (spread >= LIMIT_PCT))),
        "new_fails_within_5pct_of_the_quintic": int(np.sum(fail_new & (np.array([dev(r, "new", "raw5") for r in full]) < LIMIT_PCT))),
        "worst_dev_old_pct": pct(d_old), "worst_dev_new_pct": pct(d_new),
        "worst_ten_new": [{"name": full[i][0], "points": full[i][1], "dev_new_pct": float(d_new[i]),
                           "dev_old_pct": float(d_old[i]), "quintic_vs_cubic_pct": float(spread[i]),
                           "hook_new": full[i][0] in hook["new"], "hook_old": full[i][0] in hook["old"],
                           "le_move_pct": float(move[i]), "chord_turn_deg": float(turn[i])} for i in order],
        "le_move_pct": pct(move) | {"over_0.1": int(np.sum(move > 0.1)), "over_0.2": int(np.sum(move > 0.2)),
                                    "over_0.5": int(np.sum(move > 0.5))},
        "chord_turn_abs_deg": pct(np.abs(turn)) | {"over_0.05": int(np.sum(np.abs(turn) > 0.05)),
                                                   "over_0.1": int(np.sum(np.abs(turn) > 0.1)),
                                                   "over_0.3": int(np.sum(np.abs(turn) > 0.3))},
        "hooks_old": len(hook["old"]), "hooks_new": len(hook["new"]),
        "hooks_new_not_old": sorted(hook["new"] - hook["old"]), "hooks_old_not_new": len(hook["old"] - hook["new"]),
        "hooks_both": sorted(hook["old"] & hook["new"]),
        "crossing_old": cross["old"], "crossing_new": cross["new"],
        "config_sections": config,
    }


# --- the figure ------------------------------------------------------------------------------------

INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e4e2dc", "#fcfcfb"
C_NEW, C_OLD = "#2a78d6", "#eb6834"            # reference palette slots 1 and 2 (validated, light)


def figure(res: dict, keep: dict) -> None:
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2,
                         "ytick.color": INK2, "axes.titlesize": 10, "axes.titlecolor": INK, "legend.fontsize": 8,
                         "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURF,
                         "axes.facecolor": SURF, "savefig.facecolor": SURF})
    db = res.get("database")
    fig = plt.figure(figsize=(15, 13.2 if db else 9.2), dpi=130)
    gs = fig.add_gridspec(3 if db else 2, 12, height_ratios=[1, 1.05, 1.0][: 3 if db else 2], hspace=0.5, wspace=1.6,
                          top=0.915 if db else 0.885)
    for i, name in enumerate(("naca4415", "e387", "sd7032", "mh104")):
        a = fig.add_subplot(gs[0, 3 * i:3 * i + 3])
        cv, r = keep[name], res["airfoils"][name]
        ref = cv["raw"]
        top = 2.3 * np.max(ref.kappa[np.abs(ref.sigma) <= PROF_C])
        for key, lab, col, ls, lw in (("raw", "raw file (cubic spline)", INK2, "-", 1.6), ("exact", "formula", INK, ":", 1.4),
                                      ("old", "built, old rule", C_OLD, "-", 1.4), ("new", "built, new rule (201 points/side)", C_NEW, "--", 1.4)):
            if key in cv:
                n = cv[key]
                m = np.abs(n.sigma) <= PROF_C
                a.plot(100 * n.sigma[m], np.minimum(n.kappa[m], top * 1.2), ls=ls, color=col, lw=lw, label=lab)
        a.set_xlim(-2, 2)
        a.set_ylim(0, top)
        a.axvline(0, color=GRID, lw=0.8, zorder=0)
        a.grid(True, color=GRID, lw=0.5)
        b = cv["old"]
        k_le = float(np.max(b.kappa[np.abs(b.sigma) < 1e-9]))
        if k_le > top:
            side = "upper" if r["old_le_one_sided"]["R_le_upper_c"] < r["old_le_one_sided"]["R_le_lower_c"] else "lower"
            a.annotate(f"old rule at the LE ({side} side):\n{k_le:.0f}/c, R = {1 / k_le:.4f} c", xy=(0, top),
                       xytext=(0.12 if side == "upper" else -0.12, 0.93 * top), ha="left" if side == "upper" else "right",
                       va="top", fontsize=7.5, color=INK2, arrowprops={"arrowstyle": "->", "color": MUTED, "lw": 0.8})
        if name == "naca4415":
            pk = max((q for q in r["peaks"]["old"] if q["sigma_pct"] < -0.3), key=lambda q: q["kappa"])
            a.annotate(f"bump {pk['kappa']:.1f}/c\n(raw {np.interp(pk['sigma_pct'] / 100, ref.sigma, ref.kappa):.1f}/c)",
                       xy=(pk["sigma_pct"], pk["kappa"]), xytext=(-1.95, 0.80 * top), fontsize=7.5, color=INK2,
                       arrowprops={"arrowstyle": "->", "color": MUTED, "lw": 0.8})
        a.set_title(f"{LABEL[name]} ({r['n_points']} points)\n"
                    f"apex {r['apex_sigma_pct']:+.3f} % c, tilt {r['tangent_tilt_at_le_deg']:+.1f}°", fontsize=9.5)
        a.set_xlabel("arc [% c]; − lower, + upper", fontsize=8.5)
        if i == 0:
            a.set_ylabel("curvature [1/c]")
            fig.legend(*a.get_legend_handles_labels(), loc="upper center", ncol=4, frameon=False,
                       bbox_to_anchor=(0.5, 0.963 if db else 0.95), fontsize=8.5)

    h = np.array(H_PCT)
    a = fig.add_subplot(gs[1, 0:4])                     # the old rule against the raw file
    a.axhspan(0.95, 1.05, color=GRID, alpha=0.8, lw=0, zorder=0)
    a.text(0.58, 0.895, "±5 % band (criterion)", ha="right", va="center", fontsize=7.5, color=INK2)
    quiet = []
    for name in AIRFOILS:
        c = res["airfoils"][name]["curves"]
        ratio = np.array(c["old"]["T_deg"]) / np.array(c["raw"]["T_deg"])
        a.plot(h, ratio, "-o", color=C_OLD, lw=1.1, ms=3.5, alpha=0.9)
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
    a.set_title("Old rule, all ten: turning per cell against the raw file")
    a.text(0.98, 0.97, "one line per airfoil; the lines near 1.15–1.25:\n" + ", ".join(quiet[:3]) + ",\n"
           + ", ".join(quiet[3:]), transform=a.transAxes, ha="right", va="top", fontsize=7.5, color=INK2)

    a = fig.add_subplot(gs[1, 4:8])                     # the new rule against the raw file
    a.axhspan(-LIMIT_PCT, LIMIT_PCT, color=GRID, alpha=0.8, lw=0, zorder=0)
    for key, ls, lab in (("new101", "--", "new rule, 101 points per side"), ("new", "-", "new rule, 201 points per side (built)")):
        for i, name in enumerate(AIRFOILS):
            d = res["airfoils"][name]["curves"][key]["T_diff_vs_raw_pct"]
            a.plot(h, d, ls=ls, marker="o", color=C_NEW, lw=1.1 if key == "new" else 0.9, ms=3.0,
                   alpha=1.0 if key == "new" else 0.55, label=lab if i == 0 else None)
    for key in ("new101", "new"):
        d = res["airfoils"]["mh60"]["curves"][key]["T_diff_vs_raw_pct"][0]
        a.text(0.042, d, f" MH 60: {d:+.1f} %", ha="left", va="center", fontsize=7.5, color=INK2)
    a.set_xscale("log")
    a.set_xticks(h, [f"{v:.2f}" for v in h])
    a.minorticks_off()
    a.set_xlim(0.035, 0.6)
    a.set_ylim(-11, 6)
    a.grid(True, color=GRID, lw=0.5)
    a.set_xlabel("cell arc length h [% c]")
    a.set_ylabel("(T built − T raw) / T raw [%]")
    a.set_title("New rule (cfdauto now), all ten")
    a.legend(loc="lower right", frameon=False)
    a.text(0.6, 4.6, "±5 % (criterion)", ha="right", va="center", fontsize=7.5, color=INK2)

    a = fig.add_subplot(gs[1, 8:12])                    # the Stage 2 nose solve
    s2 = res["stage2_nose_line"]
    hl = np.array(s2["h_le_pct"])
    a.axhline(10.0, color=MUTED, lw=1.0, ls="--")
    a.text(0.0022, 10.15, "target 10°", fontsize=7.5, color=INK2, va="bottom")
    for key, col, lab in (("old", C_OLD, "old rule"), ("new", C_NEW, "new rule")):
        a.semilogx(hl, s2[key]["turning_deg"], "-o", color=col, lw=1.1, ms=3.0, label=lab)
    a.set_xlim(0.0015, 0.6)
    a.set_ylim(5, 12.5)
    a.grid(True, color=GRID, lw=0.5)
    a.set_xlabel("nose spacing [% c]")
    a.set_ylabel("largest turning per node [°]")
    a.set_title("Stage 2 nose solve, NACA 4415 station (wing 35, station 21)")
    lo_b = [v for v, hh in zip(s2["old"]["worst_node_sigma_pct"], hl) if hh < 0.2]
    a.text(0.03, 0.97, f"below 0.2 % c both lines are flat: the worst node sits\n"
           f"{-max(lo_b):.1f}–{-min(lo_b):.1f} % c down the lower side, where cells\n"
           f"are set by growth 1.2, not by the nose spacing",
           transform=a.transAxes, ha="left", va="top", fontsize=7.5, color=INK2)
    a.legend(loc="lower right", frameon=False)

    if db:
        s = db["summary"]
        cols = {k: i for i, k in enumerate(db["columns"])}
        full, _ = _measured(cols, db["rows"])

        def dev(r, key):
            return max(abs(100 * (r[cols[f"T_{key}_{hh}"]] - r[cols[f"T_raw_{hh}"]]) / r[cols[f"T_raw_{hh}"]])
                       for hh in ("004", "018"))

        a = fig.add_subplot(gs[2, 0:4])
        for key, col, lab in (("old", C_OLD, "old rule"), ("new", C_NEW, "new rule")):
            d = np.sort([max(dev(r, key), 1e-3) for r in full])
            a.step(d, 100 * np.arange(1, len(d) + 1) / len(d), where="post", color=col, lw=1.4,
                   label=f"{lab}: {s[f'pass_{key}_share_pct']:.1f} % pass")
        a.axvline(LIMIT_PCT, color=MUTED, lw=1.0, ls="--")
        a.text(LIMIT_PCT * 1.08, 4, "5 %", fontsize=7.5, color=INK2)
        a.set_xscale("log")
        a.set_xlim(1e-2, 2e3)
        a.set_ylim(0, 100)
        a.grid(True, color=GRID, lw=0.5)
        a.set_xlabel("worst |T built − T raw| / T raw at h = 0.04 and 0.18 % c [%]")
        a.set_ylabel("share of files at or below [%]")
        a.set_title(f"All {s['measured_both']} database files: old against new rule\n"
                    f"hooks at the nose: old {s['hooks_old']}, new {s['hooks_new']}; "
                    f"crossing surfaces: old {len(s['crossing_old'])}, new {len(s['crossing_new'])}", fontsize=9.5)
        a.legend(loc="lower right", frameon=False)

        move = np.array([r[cols["le_move_pct"]] for r in full])
        turn = np.array([r[cols["chord_turn_deg"]] for r in full])
        a = fig.add_subplot(gs[2, 4:8])
        a.hist(move, bins=np.linspace(0, max(0.3, move.max() * 1.02), 61), color=C_NEW, alpha=0.9, rwidth=0.85)
        a.set_yscale("log")
        a.grid(True, color=GRID, lw=0.5)
        a.set_xlabel("leading-edge move along the nose [% c]")
        a.set_ylabel("files")
        lm = s["le_move_pct"]
        a.set_title("Side effect 1: the leading edge moves")
        a.text(0.97, 0.95, f"median {lm['p50']:.3f} % c, 90 % {lm['p90']:.3f}, 99 % {lm['p99']:.3f}\n"
               f"max {lm['max']:.3f} % c; over 0.1 % c: {lm['over_0.1']} files",
               transform=a.transAxes, ha="right", va="top", fontsize=7.5, color=INK2)
        a = fig.add_subplot(gs[2, 8:12])
        lim = max(0.15, np.abs(turn).max() * 1.02)
        a.hist(turn, bins=np.linspace(-lim, lim, 61), color=C_NEW, alpha=0.9, rwidth=0.85)
        a.set_yscale("log")
        a.grid(True, color=GRID, lw=0.5)
        a.set_xlabel("chord turn [°] (+: chord tilts up toward the TE)")
        a.set_ylabel("files")
        ct = s["chord_turn_abs_deg"]
        a.set_title("Side effect 2: the chord line turns")
        a.text(0.03, 0.95, f"|turn|: median {ct['p50']:.3f}°\n90 % {ct['p90']:.3f}°, 99 % {ct['p99']:.3f}°\n"
               f"max {ct['max']:.3f}°; over 0.1°:\n{ct['over_0.1']} files",
               transform=a.transAxes, ha="left", va="top", fontsize=7.5, color=INK2)
    fig.suptitle("Decision 64: the built nose against the raw file, old and new rule (7 Nov 2026)",
                 fontsize=11.5, color=INK, y=1.0)
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, bbox_inches="tight")
    plt.close(fig)


# --- main ------------------------------------------------------------------------------------------

_NUM_LIST = re.compile(r"\[\s+(-?[\d.eE+-]+(?:,\s+-?[\d.eE+-]+)*)\s+\]")


def dumps(obj) -> str:
    """json with indent 1, but every list of plain numbers on one line, and each database row too."""
    text = _NUM_LIST.sub(lambda m: "[" + ", ".join(v.strip() for v in m.group(1).split(",")) + "]",
                         json.dumps(obj, indent=1))
    return re.sub(r"\[\s+(\"[^\"\n]*\"(?:,\s+(?:-?[\d.eE+-]+|null|true|false|\"[^\"\n]*\"))+)\s+\]",
                  lambda m: "[" + ", ".join(v.strip() for v in re.split(r",\s+(?=[-\d\"nft])", m.group(1))) + "]", text)


def git_head() -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main(argv: list[str]) -> None:
    res = {"meta": {
        "date": "2026-11-07", "decision": 64, "git_base": git_head(),
        "criterion": f"|T_built(h) - T_raw(h)| / T_raw(h) < {LIMIT_PCT} % for every h on all ten airfoils",
        "h_pct": list(H_PCT), "window_pct": 100 * WIN_C, "profile_sigma_pct": [-100 * PROF_C, 100 * PROF_C, PROF_N],
        "units": "lengths in the chord from the farthest raw point to the TE midpoint (c); kappa in 1/c; T in degrees",
        "sigma": "arc length from the raw point farthest from the TE midpoint (the old LE), + upper, - lower",
        "tangent_tilt_at_le_deg": "turning of the raw spline between its apex and the farthest raw point (> 0: apex on the lower side)",
        "loft_backend": "numpy (pyGeo not installed); new_avg checks the other knot rule",
        "numpy": np.__version__, "scipy": scipy.__version__,
        "naca_derivative_check_rel_err": check_naca_derivatives(),
        "polyline_check_max_diff_deg": polyline_check()},
        "airfoils": {}}
    keep = {}
    for name in AIRFOILS:
        res["airfoils"][name], keep[name] = study(name)
        c = res["airfoils"][name]["curves"]
        print(f"{name:10s} R_min raw {c['raw']['R_min_c']:.4f} old {c['old']['R_min_c']:.4f} "
              f"new {c['new']['R_min_c']:.4f} | old-raw % " +
              " ".join(f"{v:+7.1f}" for v in c["old"]["T_diff_vs_raw_pct"]) +
              " | new-raw % " + " ".join(f"{v:+5.1f}" for v in c["new"]["T_diff_vs_raw_pct"]))
    res["verdict"] = {"fails_" + k: [n for n, a in res["airfoils"].items() if not a[f"{k}_passes"]]
                      for k in ("old", "new", "new101", "apex_pchip")}
    res["verdict"]["decision_64_closes_without_fix"] = not res["verdict"]["fails_old"]
    res["stage2_nose_line"] = stage2_nose_line()
    if "--database" in argv:
        res["database"] = database_pass()
    elif OUT_JSON.exists() and "database" in (prev := json.loads(OUT_JSON.read_text())):
        res["database"] = prev["database"]
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    text = dumps(res)
    assert json.dumps(json.loads(text), sort_keys=True) == json.dumps(res, sort_keys=True), "compact json lost data"
    OUT_JSON.write_text(text)
    figure(res, keep)
    print("wrote", OUT_JSON.relative_to(ROOT.parent), "and", OUT_PNG.relative_to(ROOT.parent))
    print(json.dumps(res["verdict"]))
    if "database" in res:
        print(json.dumps(res["database"]["summary"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
