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
    rc = rules("C")
    j = 0
    r = m.stations[j]
    sec = Section.at(w.loft, r["v"], rc.dense_per_side)
    c = sec.chord
    s = sec.arc_up
    u = sec.u
    h_max = np.full_like(u, rc.max_spacing_c * c)
    band = np.where((u >= rc.band_upper[0]) & (u <= rc.band_upper[1]), r["h_band_c"] * c, h_max)
    curv = np.minimum(band, np.where(u > 0.005, np.radians(rc.nose_turning_deg) * sec.curvature_radius(True), np.inf))
    ends = flat_ends(s, curv, 4 * r["h_le_c_asked"] * c, rc.te_spacing_c * c)
    final = limit_growth(s, ends, rc.chord_growth)
    fig, ax = plt.subplots(figsize=(13, 4.2))
    ax.semilogy(u, h_max / c, color=LINE, lw=3, label="1. largest cell 2 % c")
    ax.semilogy(u, band / c, color=AMBER, lw=2, label=f"2. transition band 0–85 % c: bubble / 20 = {r['h_band_c'] * 100:.2f} % c at Re {r['re_local']:.1e}")
    ax.semilogy(u, curv / c, color=VIOLET, lw=1.5, label="3. curvature cap: cell ≤ R × 10° (x/c > 0.5 %)")
    ax.semilogy(u, ends / c, color=BWB, lw=1.2, label=f"4. this station's nose {r['h_le_c_asked'] * 100:.3f} % c held over 4 cells (solved for 10°); trailing edge 0.1 % c")
    ax.semilogy(u, final / c, color=ACC, lw=2.2, label="5. growth ≤ 1.2 per cell: this station's upper-side field")
    lo_band = np.where((u >= rc.band_lower[0]) & (u <= rc.band_lower[1]), r["h_band_c"] * c, np.nan)
    ax.semilogy(u, lo_band / c, color=WARN, lw=2, ls="--", label="6. the lower side's band 60–100 % c: shared with the upper side through the one distribution")
    um, d = side_cells(m, j, True)
    ax.semilogy(um, d / c, ".", color=INK, ms=3, label="cells delivered (upper side, root): the strictest station and side at every place")
    nose_del = d[0] / c * 100
    ax.text(0.012, 2.6e-4, f"delivered nose {nose_del:.3f} % c: the sharpest nose of the wing (tip, MH 61)\nsets it for every station", color=MUTED, fontsize=8.5)
    ax.set_xlabel("x / c (upper surface)"); ax.set_ylabel("cell size / chord"); ax.legend(loc="lower right")
    ax.set_title(f"the size field around the root section, rule by rule ({m.info['n_side']} nodes per side)")
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
