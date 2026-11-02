"""The pictures of the Stage 2 page (docs/page/*.png), every one drawn from the mesh arrays.

    python scripts/page_figures.py          # about 3 minutes
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cfdauto.geometry import airfoils as A  # noqa: E402
from cfdauto.geometry.sections import load_airfoil  # noqa: E402
from cfdauto.mesh.checks import scaled_jacobian  # noqa: E402
from cfdauto.mesh.laws import first_cell_c, rules  # noqa: E402
from cfdauto.mesh.ring import (RingSpec, Section, build_ring, build_ring_at, cells_per_side, fields,  # noqa: E402
                               nose_turning, turning, union_distribution)
from cfdauto.mesh.spacing import cells_needed, equidistribute, flat_ends, limit_growth  # noqa: E402
from cfdauto.mesh.stations import SpanTable, place_stations  # noqa: E402
from cfdauto.mesh.surface import build_surface, wing_from_set  # noqa: E402
from cfdauto.paths import STAGE2  # noqa: E402

OUT = STAGE2 / "docs" / "page"
INK, MUTED, LINE = "#142230", "#566573", "#D6DEE6"
ACC, BWB, WARN, AMBER, VIOLET = "#0C5EA8", "#2E8B57", "#B02A20", "#9A6200", "#6A4BB0"
TYPES = ("bwb", "flying_wing", "cranked", "tapered")
TYPE_NAME = {"bwb": "BWB", "flying_wing": "flying wing", "cranked": "cranked", "tapered": "tapered"}
COLS = {"bwb": BWB, "flying_wing": AMBER, "cranked": ACC, "tapered": VIOLET}
plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": LINE, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.titlesize": 10, "axes.titlecolor": INK, "legend.fontsize": 8.5,
                     "figure.dpi": 130, "savefig.dpi": 130, "axes.spines.top": False, "axes.spines.right": False})


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT / name)
    plt.close(fig)
    print("wrote", name)


def side_cells(m, j, upper=True):
    n = m.info["n_side"]
    sl = slice(0, n) if upper else slice(n - 1, 2 * n - 1)
    p, u = m.wing[sl, j], m.u[sl, j]
    if upper:
        p, u = p[::-1], u[::-1]
    d = np.linalg.norm(np.diff(p, axis=0), axis=1)
    return 0.5 * (u[1:] + u[:-1]), d


# --- 1. the dense section and the arc-length parameter ---------------------------------------
def fig_dense(w, m):
    rc = rules("C")
    sec = Section.at(w.loft, 0.0, rc.dense_per_side)
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.6))
    vv = np.zeros_like(sec.u)
    up, lo = w.loft.upper(sec.u, vv), w.loft.lower(sec.u, vv)
    a = ax[0]
    a.plot(up[:, 0], up[:, 2], color=INK, lw=0.8); a.plot(lo[:, 0], lo[:, 2], color=INK, lw=0.8)
    k = 120
    a.plot(up[:k, 0], up[:k, 2], ".", color=ACC, ms=2.5); a.plot(lo[:k, 0], lo[:k, 2], ".", color=AMBER, ms=2.5)
    a.set_xlim(-0.002, 0.03); a.set_ylim(-0.016, 0.016); a.set_aspect("equal")
    a.set_title("the dense section at the nose: 6,001 points per side, cosine in x/c\n(the first 120 shown; blue upper, amber lower)")
    a.set_xlabel("x [m]"); a.set_ylabel("z [m]")
    a = ax[1]
    a.plot(sec.u, sec.arc_up / sec.chord, color=ACC, label="upper"); a.plot(sec.u, sec.arc_lo / sec.chord, color=AMBER, label="lower")
    a.set_xlabel("u = x / c"); a.set_ylabel("arc length from the nose / c"); a.legend()
    a.set_title("arc length against x/c: the table that turns a spacing [m] into u")
    a = ax[2]
    r_up, r_lo = sec.curvature_radius(True) / sec.chord, sec.curvature_radius(False) / sec.chord
    a.loglog(sec.u[1:], r_up[1:], color=ACC, label="upper"); a.loglog(sec.u[1:], r_lo[1:], color=AMBER, label="lower")
    a.set_xlabel("u = x / c"); a.set_ylabel("radius of curvature / c"); a.legend()
    a.set_title("curvature radius of the built section (root, MH 104): the two sides differ at the nose")
    save(fig, "dense_section.png")


# --- 2. stations along the span ---------------------------------------------------------------
def fig_stations(w, m):
    rl = rules("C")
    tab = SpanTable.of(w.loft, rl.dense_span)
    tip_gap = m.info["s0_tip_m"]
    tab = tab.refined_at_tip(w.loft, tip_gap)
    st = place_stations(tab, rl, tip_gap, w.loft.station_v)
    y = st["y"]
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.8))
    a = ax[0]
    a.semilogy(tab.y, rl.span_spacing_c * tab.chord, color=MUTED, ls="--", lw=1, label="0.2 × local chord")
    a.semilogy(tab.y, st["size_field"], color=ACC, lw=1.2, label="size field used (12 per panel, tip squeeze, growth 1.2)")
    a.semilogy(0.5 * (y[1:] + y[:-1]), np.diff(y), ".", color=AMBER, ms=4, label="gaps delivered")
    for yl in tab.loft_y:
        a.axvline(yl, color=LINE, lw=0.8)
    a.set_xlabel("y [m] (root to tip)"); a.set_ylabel("station gap [m]"); a.legend(loc="lower left")
    a.set_title(f"station gap along the span; vertical lines: loft stations; {len(y)} stations")
    a = ax[1]
    le = m.wing[m.info["n_side"] - 1]
    te = m.wing[0]
    for j in range(len(y)):
        a.plot([le[j, 0], te[j, 0]], [le[j, 1], te[j, 1]], color=MUTED, lw=0.5)
    a.plot(le[:, 0], le[:, 1], color=INK, lw=1); a.plot(te[:, 0], te[:, 1], color=INK, lw=1)
    a.set_aspect("equal"); a.set_xlabel("x [m]"); a.set_ylabel("y [m]"); a.set_title("every station as one chord line (top view)")
    a = ax[2]
    yt = tab.semi_span
    for j in range(len(y)):
        if y[j] > yt - 0.012:
            a.plot([le[j, 0], te[j, 0]], [y[j], y[j]], color=MUTED, lw=0.6)
    a.set_ylim(yt - 0.012, yt + 0.0005); a.set_xlabel("x [m]"); a.set_ylabel("y [m]")
    a.set_title(f"the last 12 mm before the tip: gaps shrink by 1.2 per station to s0 = {tip_gap * 1e6:.0f} µm")
    save(fig, "stations.png")


# --- 3. the size field around the section, rule by rule --------------------------------------
def fig_size_field(w, m):
    """Six panels: one rule added per panel, the previous result in grey behind it."""
    rc = rules("C")
    j = 0
    r = m.stations[j]
    sec = Section.at(w.loft, r["v"], rc.dense_per_side)
    c = sec.chord
    s_arc = sec.arc_up
    u = sec.u
    h1 = np.full_like(u, rc.max_spacing_c * c)
    h2 = np.where((u >= rc.band_upper[0]) & (u <= rc.band_upper[1]), r["h_band_c"] * c, h1)
    h3 = np.minimum(h2, np.where(u > 0.005, np.radians(rc.nose_turning_deg) * sec.curvature_radius(True), np.inf))
    h4 = flat_ends(s_arc, h3, r["h_le_c_asked"] * c, rc.te_spacing_c * c, n0=4)
    h5 = limit_growth(s_arc, h4, rc.chord_growth)
    lo_band = np.where((u >= rc.band_lower[0]) & (u <= rc.band_lower[1]), r["h_band_c"] * c, np.nan)
    um, d = side_cells(m, j, True)
    steps = [
        ("1 · start: no cell larger than 2 % of the chord", None, h1, LINE, "flat line: 2 % c everywhere"),
        (f"2 · the transition band, 0–85 % c: cells of {r['h_band_c'] * 100:.2f} % c", h1, h2, AMBER, "bubble length / 20 at this station's Re 6 × 10⁵"),
        ("3 · the curvature cap: a cell may turn the surface by ≤ 10°", h2, h3, VIOLET, "acts only where the surface bends: nothing here, the nose is handled next"),
        (f"4 · the nose ({r['h_le_c_asked'] * 100:.3f} % c, held over 4 cells) and the trailing edge (0.1 % c)", h3, h4, BWB, "two small cells at the two ends"),
        ("5 · growth ≤ 1.2 per cell: the jumps become ramps", h4, h5, ACC, "this is the station's own wish list"),
        ("6 · shared with the lower side and every other station: the cells delivered", h5, None, INK, "the lower band (60–100 % c, dashed) and the tip's sharper nose set the rest"),
    ]
    fig, ax = plt.subplots(2, 3, figsize=(13, 6.4), sharex=True, sharey=True)
    for a, (title, prev, cur, col, note) in zip(ax.ravel(), steps):
        if prev is not None:
            a.semilogy(u, prev / c, color=MUTED, lw=1.2, alpha=0.5)
        if cur is not None:
            a.semilogy(u, cur / c, color=col, lw=2.2)
        else:
            a.semilogy(u, lo_band / c, "--", color=WARN, lw=1.6)
            a.semilogy(um, d / c, ".", color=INK, ms=3)
        a.axvspan(*rc.band_upper, color=AMBER, alpha=0.05)
        a.set_title(title, fontsize=9)
        a.text(0.02, 0.06, note, transform=a.transAxes, fontsize=8, color=MUTED)
        a.set_ylim(1e-4, 5e-2)
    for a in ax[1]:
        a.set_xlabel("x / c, upper surface (nose at 0, trailing edge at 1)")
    for a in ax[:, 0]:
        a.set_ylabel("cell size / chord")
    fig.suptitle("the size field of the root section, built one rule at a time (grey: the previous panel)", fontsize=10, color=INK)
    save(fig, "size_field.png")


# --- 4. the nose solve: turning against spacing ----------------------------------------------
def fig_nose_solve(w_bwb, m_bwb, w_tap, m_tap):
    rc = rules("C")
    fig, ax = plt.subplots(1, 2, figsize=(13, 4))
    for a, w, m, j, name in ((ax[0], w_bwb, m_bwb, 0, "BWB reference wing, root (MH 104)"),
                             (ax[1], w_tap, m_tap, 21, "tapered training wing 35, station 21 (NACA 4415)")):
        r = m.stations[j]
        sec = Section.at(w.loft, r["v"], rc.dense_per_side)
        c = sec.chord
        hs = np.geomspace(2e-5, 5e-3, 40)
        ts = []
        for h in hs:
            sp = RingSpec(h * c, r["h_band_c"] * c, rc.max_spacing_c * c, rc.te_spacing_c * c)
            n = int(np.ceil(cells_per_side(sec, sp, rc))) + 1
            out = build_ring(sec, sp, rc, n)
            ts.append(nose_turning(out["ring"], n))
        a.semilogx(hs * 100, ts, "-", color=ACC, lw=1.2)
        a.semilogx(hs * 100, ts, ".", color=ACC, ms=4)
        a.axhline(rc.nose_turning_deg, color=WARN, lw=1, ls="--", label="target 10°")
        a.axvline(r["h_le_c_solved"] * 100, color=BWB, lw=1, ls=":", label=f"solved: {r['h_le_c_solved'] * 100:.3f} % c")
        a.set_xlabel("nose spacing / chord [%]"); a.set_ylabel("largest turning per cell [deg]"); a.legend()
        a.set_title(name)
    ax[0].text(0.03, 0.95, "smooth: the turning falls steadily as the nose cell shrinks", transform=ax[0].transAxes, va="top", color=MUTED, fontsize=8.5)
    ax[1].text(0.03, 0.95, "the built NACA 4415 nose: not monotone (open decision 64)\nso the solve walks down until a window [0.77 h, h] passes",
               transform=ax[1].transAxes, va="top", color=MUTED, fontsize=8.5)
    save(fig, "nose_solve.png")


# --- 5. one distribution for the wing: before and after --------------------------------------
def fig_union(w, m):
    """m is the mesh as built (one distribution). The 'before' uses each station's own distribution."""
    rl = rules("C")
    secs = [Section.at(w.loft, r["v"], rl.dense_per_side) for r in m.stations]
    specs = [RingSpec(r["h_le_c_asked"] * r["chord_m"], r["h_band_c"] * r["chord_m"], rl.max_spacing_c * r["chord_m"],
                      rl.te_spacing_c * r["chord_m"]) for r in m.stations]
    n_side = m.info["n_side"]
    before = np.stack([build_ring(sec, sp, rl, n_side)["ring"] for sec, sp in zip(secs, specs)], axis=1)
    J0, J1 = scaled_jacobian(before, wrap_i=True), scaled_jacobian(m.wing, wrap_i=True)
    fig, ax = plt.subplots(1, 3, figsize=(13, 4.4), gridspec_kw={"width_ratios": [1.2, 1.2, 1], "wspace": 0.35})
    for a, J, name in ((ax[0], J0, f"before: a distribution per station\n(min {J0.min():.2f})"),
                       (ax[1], J1, f"after: one distribution for the wing\n(min {J1.min():.2f})")):
        im = a.imshow(J.T, aspect="auto", origin="lower", cmap="viridis", vmin=0, vmax=1, interpolation="nearest")
        a.set_xlabel("ring index (TE corner → nose → TE corner → base)"); a.set_ylabel("station (root → tip)")
        a.set_title(name)
    fig.colorbar(im, ax=ax[:2], shrink=0.8, label="scaled Jacobian of the quad (1 = right angles, 0 = flat)")
    a = ax[2]
    a.hist(J0.ravel(), bins=50, range=(0, 1), color=WARN, alpha=0.6, label="before")
    a.hist(J1.ravel(), bins=50, range=(0, 1), color=ACC, alpha=0.6, label="after")
    a.set_yscale("log"); a.set_xlabel("scaled Jacobian"); a.set_ylabel("quads"); a.legend()
    a.set_title("all wing quads")
    fig.suptitle("flying wing, training_full 6, level C, Re 3e5: the quads between stations", fontsize=10, color=INK)
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "union_distribution.png", bbox_inches="tight")
    plt.close(fig)
    print("wrote union_distribution.png")


# --- 6. the ring, annotated --------------------------------------------------------------------
def fig_ring(w, m):
    n = m.info["n_side"]
    ring = m.wing[:, 0]
    c = m.stations[0]["chord_m"]
    fig, ax = plt.subplots(1, 3, figsize=(13, 4), gridspec_kw={"width_ratios": [2, 1, 1]})
    a = ax[0]
    closed = np.vstack([ring, ring[:1]])
    a.plot(closed[:, 0], closed[:, 2], color=LINE, lw=0.8)
    a.plot(ring[:n, 0], ring[:n, 2], ".", color=ACC, ms=2, label=f"upper: node 0 (TE corner) → {n - 1} (nose)")
    a.plot(ring[n - 1:2 * n - 1, 0], ring[n - 1:2 * n - 1, 2], ".", color=AMBER, ms=2, label=f"lower: node {n - 1} → {2 * n - 2} (TE corner)")
    a.plot(ring[2 * n - 1:, 0], ring[2 * n - 1:, 2], "o", color=WARN, ms=3, label=f"base: {m.info['n_base'] - 2} interior nodes")
    a.annotate("node 0", ring[0, [0, 2]], xytext=(ring[0, 0] - 0.08 * c, ring[0, 2] + 0.08 * c), arrowprops={"arrowstyle": "->", "color": MUTED}, color=INK)
    a.annotate(f"node {n - 1}\n(nose)", ring[n - 1, [0, 2]], xytext=(ring[n - 1, 0] + 0.05 * c, ring[n - 1, 2] + 0.1 * c), arrowprops={"arrowstyle": "->", "color": MUTED}, color=INK)
    a.set_aspect("equal"); a.legend(loc="lower right"); a.set_title(f"the ring at the root: {ring.shape[0]} unique nodes = 2 × {n} + {m.info['n_base']} − 3")
    a.set_xlabel("x [m]"); a.set_ylabel("z [m]")
    a = ax[1]
    k = 14
    sl = np.r_[n - 1 - k: n - 1 + k + 1]
    a.plot(ring[sl, 0], ring[sl, 2], "-", color=LINE); a.plot(ring[sl, 0], ring[sl, 2], ".", color=INK, ms=4)
    t = turning(ring)
    for i in (n - 1, n - 1 - 5, n - 1 + 5):
        a.annotate(f"{t[i]:.1f}°", ring[i, [0, 2]], xytext=(6, 6), textcoords="offset points", fontsize=8, color=WARN)
    a.set_aspect("equal"); a.set_title("the nose: each node turns the surface by ≤ 10°"); a.set_xlabel("x [m]")
    a = ax[2]
    sl = np.r_[0:12, 2 * n - 13: 2 * n - 1, 2 * n - 1: ring.shape[0]]
    pts = ring[sl]
    a.plot(pts[:, 0], pts[:, 2], ".", color=INK, ms=4)
    a.plot(ring[:12, 0], ring[:12, 2], "-", color=LINE); a.plot(ring[2 * n - 13:2 * n - 1, 0], ring[2 * n - 13:2 * n - 1, 2], "-", color=LINE)
    base = np.vstack([ring[2 * n - 2], ring[2 * n - 1:], ring[0]])
    a.plot(base[:, 0], base[:, 2], "-", color=WARN, lw=1)
    a.set_aspect("equal"); a.set_title(f"the trailing edge: 0.1 % c cells, {m.info['n_base'] - 1} cells across the base"); a.set_xlabel("x [m]")
    save(fig, "ring.png")


# --- 7. the tip cap and its quality --------------------------------------------------------------
def fig_cap(m):
    cap = m.cap
    J = scaled_jacobian(cap)
    fig, ax = plt.subplots(2, 1, figsize=(13, 6), gridspec_kw={"height_ratios": [1.2, 1]})
    a = ax[0]
    for i in range(cap.shape[0]):
        a.plot(cap[i, :, 0], cap[i, :, 2], color=MUTED, lw=0.3)
    for j in range(cap.shape[1]):
        a.plot(cap[:, j, 0], cap[:, j, 2], color=INK, lw=0.5)
    a.set_aspect("equal"); a.set_title(f"the tip cap: one H patch {cap.shape[0]} × {cap.shape[1]}, its edge is the tip ring node for node; "
                                       "cross lines join upper and lower nodes at the same arc fraction")
    a.set_xlabel("x [m]"); a.set_ylabel("z [m]")
    a = ax[1]
    im = a.imshow(J.T, aspect="auto", origin="lower", cmap="viridis", vmin=0, vmax=1, interpolation="nearest")
    a.set_xlabel("chordwise cell (nose arc → base)"); a.set_ylabel("across the thickness")
    Jm = J.copy(); Jm[0, [0, -1]] = np.inf
    a.set_title(f"scaled Jacobian of the cap quads: min {Jm.min():.2f} (the two nose-corner cells, {J[0, 0]:.2f} and {J[0, -1]:.2f}, reported apart)")
    fig.colorbar(im, ax=a, shrink=0.8)
    save(fig, "cap.png")


# --- 8. band cell and ring size against Re -----------------------------------------------------
def fig_re(screen):
    rc = rules("C")
    re = np.geomspace(2e4, 6e6, 200)
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.8))
    a = ax[0]
    a.loglog(re, [rc.bubble_length_c(x) for x in re], color=AMBER, lw=1.5)
    a.set_xlabel("local Re"); a.set_ylabel("bubble length / chord"); a.set_title("laminar-bubble length from the Stage 1 XFOIL table (log-log between the points)")
    a = ax[1]
    a.loglog(re, [rc.band_spacing_c(x) * 100 for x in re], color=ACC, lw=1.5, label="band cell = bubble / 20")
    a.loglog(re, [first_cell_c(x) * 100 for x in re], color=VIOLET, lw=1.5, label="first wall cell s0 (y⁺ = 1)")
    a.axhline(0.1, color=MUTED, ls=":", lw=1); a.text(2.2e4, 0.11, "trailing edge 0.1 % c", color=MUTED, fontsize=8)
    a.set_xlabel("local Re"); a.set_ylabel("cell size / chord [%]"); a.legend(); a.set_title("the two sizes that depend on Re (level C)")
    a = ax[2]
    rows = [r for r in screen["rows"] if r["set"] == "reference"]
    for t in TYPES:
        rr = sorted([r for r in rows if r["wing_type"] == t], key=lambda r: r["re_mean"])
        res = sorted({r["re_mean"] for r in rr})
        med = [np.median([r["n_ring"] for r in rr if r["re_mean"] == x]) for x in res]
        a.semilogx(res, med, "o-", color=COLS[t], label=t)
    a.axhline(150, color=MUTED, ls="--", lw=1); a.text(1.1e5, 160, "S8 ring: 150 nodes", color=MUTED, fontsize=8)
    a.set_xlabel("Re on the mean chord"); a.set_ylabel("ring nodes (median of 5 reference wings)"); a.legend()
    a.set_title("the ring grows with Re until the band cell floor (0.25 % c)")
    save(fig, "re_rules.png")


# --- 9. the family: C, M, F ------------------------------------------------------------------------
def fig_family(w, fam):
    ms = {lev: build_surface(w.loft, 3.0e5, lev) for lev in ("C", "M", "F")}
    fig, ax = plt.subplots(1, 3, figsize=(13, 4))
    a = ax[0]
    cols = {"C": ACC, "M": AMBER, "F": WARN}
    for lev, m in ms.items():
        n = m.info["n_side"]
        ring = m.wing[:, 0]
        sl = np.r_[n - 1 - 12: n - 1 + 13]
        a.plot(ring[sl, 0], ring[sl, 2], ".-", color=cols[lev], ms=4, lw=0.6, label=f"{lev}: {m.info['n_ring']} ring nodes, {m.info['n_span']} stations")
    a.set_aspect("equal"); a.legend(); a.set_title("the nose of the root ring at C, M, F: every cell ÷ 1.3 per level"); a.set_xlabel("x [m]"); a.set_ylabel("z [m]")
    a = ax[1]
    keys = ["nose_root", "nose_tip", "te_root", "band_root", "band_tip", "root_gap", "tip_gap", "base_cell"]
    x = np.arange(len(keys))
    for k, (pair, col) in enumerate((("C/M", ACC), ("M/F", AMBER))):
        vals = [fam["wings"]["bwb"]["ratios"][pair][q] for q in keys]
        a.bar(x + (k - 0.5) * 0.38, vals, 0.38, color=col, label=pair)
    a.axhline(1.3, color=WARN, ls="--", lw=1)
    a.set_xticks(x); a.set_xticklabels(keys, rotation=30, ha="right"); a.set_ylim(1.0, 1.5); a.set_ylabel("spacing ratio between levels"); a.legend()
    a.set_title("BWB reference wing: measured ratios (dashed: r = 1.3)")
    a = ax[2]
    for t in TYPES:
        cnt = fam["wings"][t]["counts"]
        a.plot(["C", "M", "F"], [cnt[l]["n_ring"] for l in ("C", "M", "F")], "o-", color=COLS[t], label=f"{t} ring")
        a.plot(["C", "M", "F"], [cnt[l]["n_span"] for l in ("C", "M", "F")], "s--", color=COLS[t], label=f"{t} stations")
    a.set_yscale("log"); a.set_ylabel("count"); a.legend(ncol=2, fontsize=7); a.set_title("counts per level: × 1.3 for rings and stations")
    save(fig, "family.png")


# --- 10. the screen: distributions ----------------------------------------------------------------
def fig_screen_dist(screen):
    rows = [r for r in screen["rows"] if r["re_mean"] == 3.0e5]
    fig, ax = plt.subplots(1, 4, figsize=(13, 3.6))
    for a, key, label in ((ax[0], "n_ring", "ring nodes"), (ax[1], "n_span", "stations")):
        for t in TYPES:
            a.hist([r[key] for r in rows if r["wing_type"] == t], bins=25, histtype="step", color=COLS[t], lw=1.3, label=t)
        a.set_xlabel(label); a.set_ylabel("wings"); a.legend()
    a = ax[2]
    data = [[r["checks"]["wing_quads"] for r in rows if r["wing_type"] == t] for t in TYPES]
    a.boxplot(data, tick_labels=TYPES, widths=0.6)
    a.set_ylabel("min scaled Jacobian, wing quads"); a.axhline(0.05, color=WARN, ls="--", lw=1); a.tick_params(axis="x", rotation=20)
    a = ax[3]
    data = [[r["checks"]["cap_quads"] for r in rows if r["wing_type"] == t] for t in TYPES]
    a.boxplot(data, tick_labels=TYPES, widths=0.6)
    a.set_ylabel("min scaled Jacobian, cap quads"); a.axhline(0.05, color=WARN, ls="--", lw=1); a.tick_params(axis="x", rotation=20)
    fig.suptitle(f"the screen at level C, Re 3e5: {len(rows)} wings (dashed: the refusal limit 0.05)", fontsize=10, color=INK)
    save(fig, "screen_dist.png")


# --- 11. the nose finding: raw against resampled ---------------------------------------------------
def fig_nose_radius():
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.8))
    for a, name, r_formula in ((ax[0], "naca4415", 1.1019 * 0.15 ** 2), (ax[1], "e387", None), (ax[2], "mh104", None)):
        pts = A.raw_points(name)
        te = 0.5 * (pts[0] + pts[-1])
        i = int(np.argmax(np.linalg.norm(pts - te, axis=1)))
        le = pts[i]
        d = te - le
        ang = np.arctan2(d[1], d[0]); sc = np.linalg.norm(d)
        rot = np.array([[np.cos(ang), np.sin(ang)], [-np.sin(ang), np.cos(ang)]])
        p = (pts - le) @ rot.T / sc
        af = load_airfoil(name)
        xx = np.linspace(0, 0.012, 400)
        from scipy.interpolate import PchipInterpolator
        a.plot(p[:, 0], p[:, 1], "o", color=INK, ms=4, label="raw file points")
        a.plot(af.x, af.yu, "-", color=ACC, lw=1.2, label="built section (Stage 1 resample)")
        a.plot(af.x, af.yl, "-", color=ACC, lw=1.2)
        s1 = np.sqrt(af.x[1])
        for yy, col, lab in ((af.yu, AMBER, "circle fitted to the built upper nose"), (af.yl, VIOLET, "circle fitted to the built lower nose")):
            R = (yy[1] / s1) ** 2 / 2
            a.add_patch(Circle((R, 0), R, fill=False, color=col, lw=1, ls="--", label=f"{lab}: R = {R:.4f} c"))
        if r_formula:
            a.add_patch(Circle((r_formula, 0), r_formula, fill=False, color=BWB, lw=1.2, label=f"NACA formula: R = {r_formula:.4f} c"))
        a.set_xlim(-0.004, 0.012); a.set_ylim(-0.008, 0.008); a.set_aspect("equal"); a.legend(fontsize=7, loc="lower right")
        a.set_title(f"{name}: the first 1.2 % of the chord"); a.set_xlabel("x / c"); a.set_ylabel("y / c")
    save(fig, "nose_radius.png")


# --- 12. the corner wing with the trailing-edge bend ------------------------------------------------
def fig_corner_bend():
    w = wing_from_set("bwb", "corner2", 0)
    m = build_surface(w.loft, 3.0e5, "C")
    j = m.wing.shape[1] - 1
    n = m.info["n_side"]
    ring = m.wing[:, j]
    c = m.stations[j]["chord_m"]
    fig, ax = plt.subplots(1, 2, figsize=(13, 3.8), gridspec_kw={"width_ratios": [1.3, 1]})
    a = ax[0]
    closed = np.vstack([ring, ring[:1]])
    a.plot(closed[:, 0], closed[:, 2], "-", color=LINE, lw=0.8); a.plot(ring[:, 0], ring[:, 2], ".", color=INK, ms=2.5)
    a.set_aspect("equal"); a.set_xlabel("x [m]"); a.set_ylabel("z [m]")
    a.set_title(f"BWB corner wing 0, tip station: chord {c * 1000:.0f} mm, trailing edge {np.linalg.norm(ring[0] - ring[2 * n - 2]) * 1000:.2f} mm thick "
                f"({np.linalg.norm(ring[0] - ring[2 * n - 2]) / c * 100:.1f} % c)")
    a = ax[1]
    um, d = side_cells(m, j, True)
    a.semilogy(um, d / c, ".", color=ACC, ms=3, label="cells delivered, upper side")
    sec = Section.at(w.loft, m.stations[j]["v"], rules("C").dense_per_side)
    a.semilogy(sec.u[1:-1], np.radians(10) * sec.curvature_radius(True)[1:-1] / c, color=VIOLET, lw=1, label="curvature cap R × 10°")
    a.set_ylim(1e-4, 5e-2); a.set_xlabel("x / c"); a.set_ylabel("cell / chord"); a.legend()
    a.set_title("the opening of the trailing edge (from 90 % c) is a tight bend: the cap shrinks the cells there")
    save(fig, "corner_bend.png")


# --- 13. the four reference meshes, top views with ring lines ---------------------------------------
def fig_four(meshes):
    fig, ax = plt.subplots(1, 4, figsize=(13, 5))
    for a, (t, m) in zip(ax, meshes.items()):
        w = m.wing
        n = m.info["n_side"]
        for j in range(0, w.shape[1], 2):
            r = np.vstack([w[:, j], w[:1, j]])
            a.plot(r[:, 0], r[:, 1], color=MUTED, lw=0.35)
        for i in range(0, n, max(1, n // 24)):
            a.plot(w[i, :, 0], w[i, :, 1], color=COLS[t], lw=0.4)
        a.plot(w[n - 1, :, 0], w[n - 1, :, 1], color=INK, lw=1); a.plot(w[0, :, 0], w[0, :, 1], color=INK, lw=1)
        a.set_aspect("equal"); a.set_title(f"{t}: ring {m.info['n_ring']} × {m.info['n_span']} stations", fontsize=9)
        a.set_xlabel("x [m]")
    ax[0].set_ylabel("y [m]")
    fig.suptitle("the four reference wings (index 0) at level C, Re 3e5: every second station and every 24th ring line (upper surface)", fontsize=10, color=INK)
    save(fig, "four_types.png")


def main() -> None:
    screen = json.loads((STAGE2 / "data" / "studies" / "screen_C.json").read_text())
    fam = json.loads((STAGE2 / "data" / "studies" / "family_ratios.json").read_text())
    w = wing_from_set("bwb", "reference", 0)
    m = build_surface(w.loft, 3.0e5, "C")
    fig_dense(w, m)
    fig_stations(w, m)
    fig_size_field(w, m)
    w_tap = wing_from_set("tapered", "training_focus", 35)
    m_tap = build_surface(w_tap.loft, 3.0e5, "C")
    fig_nose_solve(w, m, w_tap, m_tap)
    w_fw = wing_from_set("flying_wing", "training_full", 6)
    fig_union(w_fw, build_surface(w_fw.loft, 3.0e5, "C"))
    fig_ring(w, m)
    fig_cap(m)
    fig_re(screen)
    fig_family(w, fam)
    fig_screen_dist(screen)
    fig_nose_radius()
    fig_corner_bend()
    meshes = {t: build_surface(wing_from_set(t, "reference", 0).loft, 3.0e5, "C") for t in TYPES}
    fig_four(meshes)


if __name__ == "__main__":
    main()


# --- 14. why structured: the same section meshed both ways ----------------------------------------
def fig_structured_vs_unstructured(w, m):
    from scipy.spatial import Delaunay
    n = m.info["n_side"]
    ring = m.wing[:, 0]
    sides = ring[: 2 * n - 1]                                    # upper TE corner -> nose -> lower TE corner
    closed = np.vstack([ring, ring[:1]])
    c = m.stations[0]["chord_m"]
    # a few O layers for the picture: offset along the outward normal, growing 1.4 x per layer
    t = np.gradient(closed[:, [0, 2]], axis=0)
    nrm = np.column_stack([t[:, 1], -t[:, 0]])
    nrm /= np.linalg.norm(nrm, axis=1)[:, None]
    layers = [closed[:, [0, 2]]]
    d = 0.0
    for k in range(14):
        d += 0.0025 * c * 1.4 ** k
        layers.append(closed[:, [0, 2]] + d * nrm)
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.2))
    a = ax[0]
    for L in layers[::1]:
        a.plot(L[:, 0], L[:, 1], color=MUTED, lw=0.4)
    for i in range(0, len(closed), 6):
        a.plot([L[i, 0] for L in layers], [L[i, 1] for L in layers], color=MUTED, lw=0.3)
    a.plot(closed[:, 0], closed[:, 1], color=INK, lw=1)
    a.set_xlim(-0.12 * c, 1.12 * c); a.set_ylim(-0.35 * c, 0.35 * c); a.set_aspect("equal")
    a.set_title("structured (what we build): rows of quads along the surface,\nevery cell with an (i, j) address (layers drawn by a plain offset here)", fontsize=9)
    a.set_xlabel("x [m]"); a.set_ylabel("z [m]")
    a = ax[1]
    rng = np.random.default_rng(3)
    pts = [sides[::3, [0, 2]]]
    for k in range(1, 4):
        pts.append(layers[3 * k][::5] + rng.normal(0, 0.004 * c, (len(layers[3 * k][::5]), 2)))
    box = np.column_stack([rng.uniform(-0.12 * c, 1.12 * c, 500), rng.uniform(-0.35 * c, 0.35 * c, 500)])
    P = np.vstack(pts + [box])
    tri = Delaunay(P)
    cen = P[tri.simplices].mean(axis=1)
    from matplotlib.path import Path as MPath
    inside = MPath(closed[:, [0, 2]]).contains_points(cen)
    a.triplot(P[:, 0], P[:, 1], tri.simplices[~inside], color=MUTED, lw=0.3)
    a.plot(closed[:, 0], closed[:, 1], color=INK, lw=1)
    a.set_xlim(-0.12 * c, 1.12 * c); a.set_ylim(-0.35 * c, 0.35 * c); a.set_aspect("equal")
    a.set_title("unstructured (not used here): triangles joined by a list;\nany shape, but no rows and no exact refinement family", fontsize=9)
    a.set_xlabel("x [m]")
    save(fig, "structured_vs_unstructured.png")


# --- 15. the O-H topology and what Stage 3 adds ---------------------------------------------------
def fig_topology(m):
    n = m.info["n_side"]
    ring = m.wing[:, 0]
    closed = np.vstack([ring, ring[:1]])
    c = m.stations[0]["chord_m"]
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6), gridspec_kw={"width_ratios": [1, 1.25]})
    a = ax[0]
    t = np.gradient(closed[:, [0, 2]], axis=0)
    nrm = np.column_stack([t[:, 1], -t[:, 0]]); nrm /= np.linalg.norm(nrm, axis=1)[:, None]
    # offset layers near the wall, pulled onto circles further out (as the S8 march does over its outer half)
    centre = np.array([0.5 * c, 0.0])
    ang = np.arctan2(closed[:, 2] - centre[1], closed[:, 0] - centre[0])
    ds = np.geomspace(0.01 * c, 2.0 * c, 12)
    for d in ds:
        L = closed[:, [0, 2]] + d * nrm
        R = 0.55 * c + d
        circ = centre + R * np.column_stack([np.cos(ang), np.sin(ang)])
        wgt = np.clip((d - 0.1 * c) / (1.0 * c), 0.0, 1.0)
        L = (1 - wgt) * L + wgt * circ
        a.plot(L[:, 0], L[:, 1], color=MUTED, lw=0.4)
    a.plot(closed[:, 0], closed[:, 2], color=INK, lw=1.2)
    a.add_patch(plt.Rectangle((0.98 * c, -0.45 * c), 2.2 * c, 0.9 * c, fill=False, ls="--", color=AMBER, lw=1.2))
    a.text(1.05 * c, 0.5 * c, "wake box (Stage 3): 0.0075 c cells to 2 c, then to 10 c", color=AMBER, fontsize=8)
    a.text(-2.0 * c, 2.1 * c, "O layers: the march off the wall (Stage 3),\nfirst cell s0 at y⁺ = 1, reach ≈ 2 c", color=MUTED, fontsize=8)
    a.set_xlim(-2.3 * c, 3.4 * c); a.set_ylim(-2.6 * c, 2.6 * c); a.set_aspect("equal")
    a.set_title("side view: the O topology around the section (the ring is Stage 2)", fontsize=9); a.set_xlabel("x [m]"); a.set_ylabel("z [m]")
    a = ax[1]
    w = m.wing
    le, te = w[n - 1], w[0]
    a.fill(np.concatenate([le[:, 0], te[::-1, 0]]), np.concatenate([le[:, 1], te[::-1, 1]]), color=LINE, alpha=0.6)
    for j in range(0, w.shape[1], 3):
        a.plot([le[j, 0], te[j, 0]], [le[j, 1], te[j, 1]], color=MUTED, lw=0.4)
    a.plot(le[:, 0], le[:, 1], color=INK, lw=1); a.plot(te[:, 0], te[:, 1], color=INK, lw=1)
    yt = le[-1, 1]
    a.add_patch(plt.Rectangle((le[-1, 0] - 0.2 * c, yt), 1.6 * c, 0.3 * c, fill=False, color=VIOLET, lw=1.2))
    a.text(le[-1, 0] - 0.2 * c, yt + 0.33 * c, "outboard blocks + tip cap (H): the cap is Stage 2, the blocks Stage 3", color=VIOLET, fontsize=8)
    a.add_patch(plt.Rectangle((te[:, 0].max(), -0.05), 2.0 * c, yt + 0.3 * c, fill=False, ls="--", color=AMBER, lw=1.2))
    a.text(te[:, 0].max() + 0.05 * c, 0.02, "wake box", color=AMBER, fontsize=8)
    a.add_patch(plt.Rectangle((te[-1, 0] + 1.9 * c, yt - 0.25 * c), 3.0 * c, 0.5 * c, fill=False, ls=":", color=WARN, lw=1.2))
    a.text(te[-1, 0] + 1.95 * c, yt - 0.45 * c, "tip-vortex tube: from 2 c behind the tip", color=WARN, fontsize=8)
    a.set_aspect("equal"); a.set_xlim(-0.3 * c, te[-1, 0] + 5.2 * c); a.set_ylim(-0.1, yt + 0.9 * c)
    a.set_title("top view: the half wing with its stations; the nested boxes of the overset plan (Stage 3)", fontsize=9); a.set_xlabel("x [m]"); a.set_ylabel("y [m]")
    save(fig, "topology.png")


# --- 16. the station rules, one by one, on two wings ------------------------------------------------
def fig_station_rules():
    rl = rules("C")
    fig, ax = plt.subplots(2, 1, figsize=(13, 5.6))
    picks = [("bwb", "reference", 0), ("tapered", "reference", None)]
    # the most slender tapered reference wing, where the 0.2 c rule gets to act
    best, best_ar = 0, 0.0
    for i in range(5):
        w = wing_from_set("tapered", "reference", i)
        tab = SpanTable.of(w.loft, 201)
        if tab.semi_span / tab.mean_chord > best_ar:
            best, best_ar = i, tab.semi_span / tab.mean_chord
    picks[1] = ("tapered", "reference", best)
    cols = {"12 per panel": ACC, "0.2 × chord": BWB, "growth ≤ 1.2 between neighbours (the tip squeeze to s0, or the step between two panels)": AMBER}
    for a, (t, st, i) in zip(ax, picks):
        w = wing_from_set(t, st, i)
        m = build_surface(w.loft, 3.0e5, "C")
        y = np.array([r["y_m"] for r in m.stations]); ch = np.array([r["chord_m"] for r in m.stations])
        loft_y = np.array(m.info["loft_station_y_m"])
        gaps = np.diff(y); mid = 0.5 * (y[1:] + y[:-1]); cmid = 0.5 * (ch[1:] + ch[:-1])
        panel = np.array([np.diff(loft_y)[np.searchsorted(loft_y, g, side="right") - 1] for g in mid])
        rule = []
        for g, c, pw in zip(gaps, cmid, panel):
            if abs(g - pw / 12) / g < 0.03 and pw / 12 <= 0.2 * c * 1.03:
                rule.append("12 per panel")
            elif abs(g - 0.2 * c) / g < 0.03:
                rule.append("0.2 × chord")
            else:
                rule.append("growth ≤ 1.2 between neighbours (the tip squeeze to s0, or the step between two panels)")
        for g, md, r in zip(gaps, mid, rule):
            a.bar(md, g * 1000, width=g * 0.9, color=cols[r], alpha=0.85)
        for yl in loft_y:
            a.axvline(yl, color=INK, lw=1.2)
        a.set_yscale("log"); a.set_ylabel("station gap [mm]"); a.set_xlabel("y along the semi-span [m]")
        n = {r: rule.count(r) for r in cols if r in rule}
        a.set_title(f"{TYPE_NAME[t]} reference wing {i}: semi-span / mean chord = {y[-1] / m.info['mean_chord_m']:.1f}; "
                    + ", ".join(f"{v} gaps by '{k.split(' (')[0]}'" for k, v in n.items()) + f"; {len(y)} stations", fontsize=9)
        from matplotlib.patches import Patch
        a.legend(handles=[Patch(color=c, label=k) for k, c in cols.items()] + [Patch(color=INK, label="a loft station (b0..b3, trailing-edge switch)")], loc="lower left", ncol=2, fontsize=8)
    fig.suptitle("which rule sets each station gap (bars: one per gap, coloured by the rule that set it; black lines: the loft stations)", fontsize=10, color=INK)
    save(fig, "station_rules.png")


# --- 17. how the one node list is made ------------------------------------------------------------
def fig_merge(w, m):
    from cfdauto.mesh.ring import FRAC, field_in_arc_fraction
    rl = rules("C")
    js = {"root": 0, "mid-span": m.wing.shape[1] // 2, "tip": m.wing.shape[1] - 1}
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.4), gridspec_kw={"width_ratios": [1.3, 1]})
    a = ax[0]
    cols = {"root": ACC, "mid-span": BWB, "tip": AMBER}
    gs = []
    for name, j in js.items():
        r = m.stations[j]
        sec = Section.at(w.loft, r["v"], rl.dense_per_side)
        c = sec.chord
        sp = RingSpec(r["h_le_c_asked"] * c, r["h_band_c"] * c, rl.max_spacing_c * c, rl.te_spacing_c * c)
        for upper, ls in ((True, "-"), (False, "--")):
            h = sec.size_field(upper, sp.h_le, sp.h_band, sp.h_max, sp.h_te, rl.band_upper if upper else rl.band_lower, rl.chord_growth, rl.nose_turning_deg)
            arc = sec.arc_up if upper else sec.arc_lo
            a.semilogy(arc / arc[-1], h / arc[-1] * 100, ls, color=cols[name], lw=1,
                       label=f"{name} ({'upper' if upper else 'lower'}), chord {c * 100:.0f} cm, Re {r['re_local']:.1e}")
        gs.append(field_in_arc_fraction(sec, sp, rl))
    secs = [Section.at(w.loft, r["v"], rl.dense_per_side) for r in m.stations]
    specs = [RingSpec(r["h_le_c_asked"] * r["chord_m"], r["h_band_c"] * r["chord_m"], rl.max_spacing_c * r["chord_m"], rl.te_spacing_c * r["chord_m"]) for r in m.stations]
    frac, g, need = union_distribution(secs, specs, rl)
    a.semilogy(FRAC, g * 100, color=INK, lw=2.4, label=f"merged: the smallest at every place, all {len(secs)} stations → {len(frac)} nodes per side")
    a.set_xlabel("place along the side: fraction of the arc from the nose (0) to the trailing edge (1)")
    a.set_ylabel("wished cell size, % of the side's length"); a.legend(fontsize=7, loc="lower center"); a.set_ylim(1e-2, 5)
    a.set_title("step 4: each station's wish list (three of 82 shown), and the merged list", fontsize=9)
    a = ax[1]
    n = m.info["n_side"]
    for name, j in (("root", 0), ("tip", m.wing.shape[1] - 1)):
        ring = m.wing[:, j]; c = m.stations[j]["chord_m"]
        p = (ring - ring[n - 1]) / c                               # unit chord, nose at the origin
        off = 0.0 if name == "root" else -0.35
        a.plot(p[:2 * n - 1, 0], p[:2 * n - 1, 2] + off, "-", color=LINE, lw=0.8)
        a.plot(p[:2 * n - 1, 0], p[:2 * n - 1, 2] + off, ".", color=cols[name], ms=1.5)
        a.text(0.5, off + 0.16, f"{name} ring, chord {c * 100:.0f} cm, drawn at unit chord", color=cols[name], fontsize=8, ha="center")
    r0 = (m.wing[:, 0] - m.wing[n - 1, 0]) / m.stations[0]["chord_m"]
    r1 = (m.wing[:, -1] - m.wing[n - 1, -1]) / m.stations[-1]["chord_m"]
    for i in range(0, 2 * n - 1, max(1, (2 * n - 1) // 30)):
        a.plot([r0[i, 0], r1[i, 0]], [r0[i, 2], r1[i, 2] - 0.35], color=MUTED, lw=0.4)
    a.set_aspect("equal"); a.set_xlabel("x / chord"); a.set_yticks([])
    a.set_title("the same list on the root and the tip:\nnode i at the same place on both (every 30th node joined)", fontsize=9)
    save(fig, "merge.png")


# --- 20. the band cell: what it is and where the formula comes from --------------------------------
def fig_band_cell():
    rc = rules("C")
    re0, c_loc, c_mean = 3.0e5, 1.0, 1.0
    L = rc.bubble_length_c(re0)                                   # bubble length / chord at Re 3e5
    h = rc.band_spacing_c(re0)                                    # = L / 20
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.3), gridspec_kw={"width_ratios": [1.25, 1]})
    # left: a sketch of a laminar separation bubble on an upper surface, with 20 cells across it
    a = ax[0]
    x = np.linspace(0, 1, 400)
    yt = 5 * 0.12 * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1015 * x**4)
    yc = np.where(x < 0.4, 0.02 / 0.16 * (2 * 0.4 * x - x**2), 0.02 / 0.36 * (0.2 + 2 * 0.4 * x - x**2))
    up, lo = yc + yt, yc - yt
    a.fill_between(x, lo, up, color="#F1F4F7", lw=0); a.plot(x, up, color=INK, lw=1.2); a.plot(x, lo, color=INK, lw=1.2)
    # the transition band on the upper side, 0-85 % c
    mb = x <= 0.85
    a.plot(x[mb], up[mb] + 0.012, color=ACC, lw=6, alpha=0.25, solid_capstyle="butt")
    a.annotate("transition band, upper side 0–85 % c: the bubble can sit\nanywhere here, so the whole band gets the band cell", (0.845, np.interp(0.845, x, up) + 0.012),
               (0.78, -0.16), color=ACC, fontsize=8.5, ha="center", va="top", arrowprops=dict(arrowstyle="-", color=ACC, lw=0.8))
    # the bubble: laminar separation at xs, turbulent reattachment at xs + L
    xs = 0.36
    xb = np.linspace(xs, xs + L, 60)
    ub = np.interp(xb, x, up)
    bump = 0.028 * np.sin(np.pi * (xb - xs) / L) ** 1.2
    a.fill_between(xb, ub, ub + bump, color=AMBER, alpha=0.35, lw=0)
    a.plot(xb, ub + bump, color=AMBER, lw=1.4)
    a.annotate("laminar flow\nseparates", (xs, np.interp(xs, x, up)), (0.20, 0.33), color=INK, fontsize=8.5, ha="center",
               arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    a.annotate("turbulent flow\nreattaches", (xs + L, np.interp(xs + L, x, up)), (0.64, 0.33), color=INK, fontsize=8.5, ha="center",
               arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    a.text(xs + L / 2, np.interp(xs + L / 2, x, up) + 0.06, "the bubble", color=AMBER, fontsize=9, ha="center", fontweight="bold")
    # 20 cells across the bubble, drawn as ticks on the surface
    for i in range(21):
        xi = xs + i * L / 20
        yi = np.interp(xi, x, up)
        a.plot([xi, xi], [yi - 0.016, yi + 0.008], color=WARN, lw=0.9)
    a.annotate("", (xs, -0.045), (xs + L, -0.045), arrowprops=dict(arrowstyle="<->", color=INK, lw=0.9))
    a.text(xs + L / 2 - 0.12, -0.075, f"bubble length L = {L:.3f} c at Re 3 × 10⁵\n20 cells across it → band cell = L / 20 = {h * 100:.2f} % c",
           color=INK, fontsize=8.5, ha="center", va="top")
    a.set_xlim(-0.03, 1.03); a.set_ylim(-0.24, 0.4); a.axis("off")
    a.set_title("what the band cell is: 20 cells across a laminar separation bubble", fontsize=10)
    # right: how the number is derived, step by step, for one station
    a = ax[1]
    re = np.geomspace(2e4, 6e6, 200)
    a.loglog(re, [rc.bubble_length_c(x) for x in re], color=AMBER, lw=1.6, label="bubble length / chord (Stage 1 XFOIL table)")
    tab_re = [float(v) for v in rc.raw["chord"]["bubble_length"]["re"]]
    tab_l = [float(v) for v in rc.raw["chord"]["bubble_length"]["l_c"]]
    a.plot(tab_re, tab_l, "o", color=AMBER, ms=5)
    a.loglog(re, [rc.band_spacing_c(x) for x in re], color=ACC, lw=1.6, label="band cell / chord = bubble length / 20")
    a.plot([re0, re0], [2.2e-3, L], color=MUTED, lw=0.8, ls=":")
    a.plot([2e4, re0], [L, L], color=AMBER, lw=0.8, ls=":")
    a.plot([2e4, re0], [h, h], color=ACC, lw=0.8, ls=":")
    a.annotate("", (re0, h * 1.15), (re0, L / 1.15), arrowprops=dict(arrowstyle="->", color=INK, lw=1))
    a.text(re0 * 1.15, np.sqrt(L * h), "÷ 20", color=INK, fontsize=9.5, va="center", fontweight="bold")
    a.text(2.2e4, L * 1.15, f"② bubble {L:.3f} c", color=AMBER, fontsize=8.5)
    a.text(2.2e4, h / 1.15, f"③ band cell {h:.4f} c = {h * 100:.2f} % c\n   ≈ {0.85 / h:.0f} cells over the upper band", color=ACC, fontsize=8.5, va="top")
    a.text(2.2e4, 1.1e-3, "① local Re of the station = Re on the mean chord × local chord / mean chord (here 3 × 10⁵)", color=INK, fontsize=8.5, va="bottom")
    a.set_xlim(2e4, 6e6); a.set_ylim(1e-3, 0.8)
    a.set_xlabel("local Re of the station"); a.set_ylabel("length / chord")
    a.legend(loc="upper right", fontsize=8)
    a.set_title("how the number is derived for one station: Re → bubble length → ÷ 20", fontsize=10)
    save(fig, "band_cell.png")


# --- 21. how XFOIL gives the bubble length, and where the Stage 2 table sits in the Stage 1 data ---
def fig_bubble_xfoil():
    from cfdauto.paths import STAGE1
    rc = rules("C")
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.3))
    # left: a sketch of the wall friction along the upper surface, and how a bubble is read off it
    a = ax[0]
    x = np.linspace(0, 1, 600)
    xs, xr = 0.36, 0.49                                            # separation, reattachment
    lam = 0.0045 * np.sqrt(np.clip(1 - x / xs, 0, None)) + 0.0005 * np.clip(1 - x / xs, 0, None)
    bub = -0.0009 * np.sin(np.pi * np.clip((x - xs) / (xr - xs), 0, 1)) ** 0.8
    tur = (0.0040 * np.exp(-(x - xr) / 0.08) + 0.0018 * np.exp(-(x - xr) / 0.8)) * (1 - np.exp(-np.clip(x - xr, 0, None) / 0.012))
    cf = np.where(x < xs, lam, np.where(x < xr, bub, tur))
    a.axhline(0, color=INK, lw=0.8)
    a.plot(x, cf, color=ACC, lw=1.6)
    a.fill_between(x, cf, 0, where=(cf < 0), color=AMBER, alpha=0.4, lw=0)
    a.axvline(0.95, color=MUTED, ls=":", lw=1); a.text(0.955, 0.0058, "95 % c", color=MUTED, fontsize=8)
    a.annotate("", (xs, -0.0013), (xr, -0.0013), arrowprops=dict(arrowstyle="<->", color=INK, lw=0.9))
    a.text((xs + xr) / 2, -0.0016, "bubble length =\nthe stretch where Cf < 0", color=INK, fontsize=8.5, ha="center", va="top")
    a.text(0.13, 0.0050, "laminar: the wall\nfriction falls", color=INK, fontsize=8.5, ha="center", va="bottom")
    a.text(0.72, 0.0046, "turbulent after reattachment:\nthe friction jumps up, then decays", color=INK, fontsize=8.5, ha="center")
    a.annotate("separation:\nCf crosses 0", (xs, 0), (0.22, -0.0027), color=INK, fontsize=8, ha="center", arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    a.annotate("reattachment:\nCf back above 0", (xr, 0), (0.68, -0.0027), color=INK, fontsize=8, ha="center", arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    a.text(0.985, -0.0022, "Cf < 0 reaching\npast 95 % c =\ntrailing-edge\nseparation,\nnot a bubble", color=MUTED, fontsize=7.5, ha="right", va="top")
    a.set_xlim(0, 1); a.set_ylim(-0.0036, 0.0068); a.set_xlabel("x / chord along the upper surface"); a.set_ylabel("wall friction coefficient Cf (sketch)")
    a.set_title("how one XFOIL run gives one bubble: the stretch where the wall friction is negative", fontsize=10)
    # right: the Stage 1 tables (10 airfoils, free transition N_crit 9, Mach 0.1, 0-8 deg) against the Stage 2 table
    a = ax[1]
    files = sorted(p for p in (STAGE1 / "data" / "section_tables").glob("*__free__n9.npz") if "+" not in p.name)
    rows: dict[float, list[float]] = {}
    for f in files:
        d = np.load(f)
        re, mach, al = d["re"], d["mach"], d["alpha"]
        im = int(np.argmin(abs(mach - 0.1))); ia = (al >= 0) & (al <= 8)
        for i, r in enumerate(re):
            bu = d["bub_u"][i, im, ia]; L = (d["bub_u_e"] - d["bub_u_s"])[i, im, ia]
            m = (bu >= 0.5) & np.isfinite(L)
            rows.setdefault(float(r), []).extend(L[m].tolist())
    res = sorted(r for r in rows if len(rows[r]) >= 4)
    n_tot = len(files) * int(ia.sum())
    bp = a.boxplot([rows[r] for r in res], positions=res, widths=[0.22 * r for r in res], manage_ticks=False,
                   patch_artist=True, showfliers=False, medianprops=dict(color=INK, lw=1.4),
                   boxprops=dict(facecolor="#DCE6F0", edgecolor=ACC, lw=1), whiskerprops=dict(color=ACC, lw=0.9), capprops=dict(color=ACC, lw=0.9))
    for r in res:
        a.text(r, 0.0082, f"{100 * len(rows[r]) / n_tot:.0f} %", color=MUTED, fontsize=7.5, ha="center")
    a.text(2.1e4, 0.0115, "share of cases with a bubble:", color=MUTED, fontsize=7.5, ha="left", va="center")
    tab_re = [float(v) for v in rc.raw["chord"]["bubble_length"]["re"]]
    tab_l = [float(v) for v in rc.raw["chord"]["bubble_length"]["l_c"]]
    grid = np.geomspace(2e4, 6e6, 200)
    a.plot(grid, [rc.bubble_length_c(v) for v in grid], color=AMBER, lw=1.8, label="Stage 2 table (used for the band cell)")
    a.plot(tab_re, tab_l, "o", color=AMBER, ms=6)
    a.set_xscale("log"); a.set_yscale("log"); a.set_xlim(2e4, 8e6); a.set_ylim(0.0075, 1.0)
    a.set_xlabel("local Re"); a.set_ylabel("bubble length / chord (upper surface)")
    a.legend(loc="upper right", fontsize=8)
    a.set_title(f"where the table sits in the Stage 1 data: {len(files)} airfoils, 0–8°, Mach 0.1, N_crit 9\n(box: middle half of the bubbles found; whiskers: the rest)", fontsize=9.5)
    save(fig, "bubble_xfoil.png")
