"""The wake fan (law 18; decisions 108, 111), drawn on a real mesh: BWB reference wing 0, VC, Re 3e5 (rule set 2).

Four panels: a station plane with the fan (law 18) on top, the trailing edge close up, the cell height along one
vertical line 1 local chord behind the trailing edge, and a top view of where the fan runs.
Writes docs/page/{PREFIX}wake_fan.png.

    python scripts/wake_fan_figure.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ruleset import CONFIG, PREFIX                      # noqa: E402
from style import ACCENT, INK, LIMIT, LINE, MUTED, plt, save   # noqa: E402
sys.path.insert(0, str(HERE.parent))

from cfdauto.mesh.surface import build_surface, wing_from_set   # noqa: E402
from cfdauto.volume.volume import build_volume                  # noqa: E402

MESH = "#9db0c4"


def plane_lines(a, B, k, lw=0.3):
    for n in ("WU", "CU", "CN", "CL", "WL", "B"):
        X = B[f"{n}_in"][:, :, k]
        for j in range(X.shape[1]):
            a.plot(X[:, j, 0], X[:, j, 2], "-", color=MESH, lw=lw, zorder=1)
        for i in range(X.shape[0]):
            a.plot(X[i, :, 0], X[i, :, 2], "-", color=MESH, lw=lw, zorder=1)


def fan(a, st, b, label=True, rays=True):
    L = float(b["length_local_c"]) * st.chord
    s = np.linspace(0.0, L, 50)
    xm, zm = st.wake.M
    up = zm + b["margin_c"] + s * np.tan(np.radians(b["alpha_hi_deg"]))
    lo = zm - b["margin_c"] + s * np.tan(np.radians(b["alpha_lo_deg"]))
    a.fill_between(xm + s, lo, up, color=ACCENT, alpha=0.10, lw=0, zorder=0)
    a.plot(xm + s, up, "-", color=ACCENT, lw=1.3, zorder=3)
    a.plot(xm + s, lo, "-", color=ACCENT, lw=1.3, zorder=3)
    a.plot([xm + L, xm + L], [lo[-1], up[-1]], "-", color=ACCENT, lw=1.3, zorder=3)
    if rays:
        lo_a, hi_a = float(b["alpha_lo_deg"]), float(b["alpha_hi_deg"])
        for al in (lo_a, 0.0, 0.5 * hi_a, hi_a):
            a.plot(xm + s, zm + s * np.tan(np.radians(al)), "--", color=INK, lw=0.7, zorder=4)
            a.annotate(f"α = {al:g}°", (xm + L, zm + L * np.tan(np.radians(al))), xytext=(4, 0),
                       textcoords="offset points", fontsize=7.8, color=INK, va="center")
    if label:
        a.annotate(f"+{float(b['alpha_hi_deg']):g}° edge", (xm + 0.45 * L, up[22]), xytext=(-6, 6), textcoords="offset points",
                   fontsize=8, color=ACCENT, ha="right", rotation=0)
        a.annotate(f"−{-float(b['alpha_lo_deg']):g}° edge", (xm + 0.45 * L, lo[22]), xytext=(0, -12), textcoords="offset points",
                   fontsize=8, color=ACCENT, ha="center")
        a.annotate("end: 2 local chords\nbehind the trailing edge", (xm + L, lo[-1]), xytext=(-4, -26),
                   textcoords="offset points", fontsize=8, color=ACCENT, ha="right")
    return L


def main() -> None:
    w = wing_from_set("bwb", "reference", 0)
    sm = build_surface(w.loft, 3e5, "VC")
    vm = build_volume(sm, config=CONFIG)
    P = vm._plane
    rl, sts, dq = P["rules"], P["sts"], P["dq"]
    b = rl.band
    B = vm.blocks
    y = np.array([s.y for s in sts])
    k = int(np.argmin(np.abs(y - 0.5 * y[-1])))
    st = sts[k]
    c = st.chord
    xm, zm = st.wake.M

    fig = plt.figure(figsize=(13.5, 9.4))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.55, 1.0], hspace=0.22, wspace=0.14)

    # (a) the station plane with the fan
    a = fig.add_subplot(gs[0, 0])
    plane_lines(a, B, k)
    L = fan(a, st, b)
    a.set_xlim(xm - 1.15 * c, xm + L + 0.55 * c)
    a.set_ylim(zm - 0.55 * c, zm + 0.80 * c)
    a.set_aspect("equal")
    a.set_title(f"(a) One station plane (y = {st.y:.2f} c, local chord {c:.2f} c): the fan behind the trailing edge")
    a.set_xlabel("x [c]")
    a.set_ylabel("z [c]")

    # (b) the trailing edge close up
    a = fig.add_subplot(gs[0, 1])
    plane_lines(a, B, k, lw=0.45)
    fan(a, st, b, label=False, rays=False)
    a.set_xlim(xm - 0.07 * c, xm + 0.20 * c)
    a.set_ylim(zm - 0.085 * c, zm + 0.115 * c)
    a.set_aspect("equal")
    a.annotate("0.05 c margin above\nand below the edge", (xm + 0.002, zm + b["margin_c"]), xytext=(xm + 0.06 * c, zm + 0.095 * c),
               fontsize=8, color=ACCENT, arrowprops=dict(arrowstyle="->", color=ACCENT, lw=0.8))
    a.annotate("wing", (xm - 0.045 * c, zm + 0.004), fontsize=8.5, color=INK, ha="center", va="center",
               bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none"))
    a.annotate("wake cut: the wall spacing\ncarries on along it", (xm + 0.12 * c, zm), xytext=(xm + 0.09 * c, zm - 0.07 * c),
               fontsize=8, color=INK, arrowprops=dict(arrowstyle="->", color=INK, lw=0.8))
    a.set_title("(b) The trailing edge, close up (light blue: inside the fan)")
    a.set_xlabel("x [c]")

    # (c) cell height along a vertical line 1 local chord behind the trailing edge
    a = fig.add_subplot(gs[1, 0])
    s_line = 1.0 * c
    zs, hs = [], []
    for name, up in (("WU_in", True), ("WL_in", False)):
        X = B[name][:, :, k]
        q = np.arange(X.shape[0])[::-1] if up else np.arange(X.shape[0])
        ii = int(np.argmin(np.abs(dq[q, k] - s_line)))
        line = X[ii]
        h = np.linalg.norm(np.diff(line, axis=0), axis=1)
        zmid = 0.5 * (line[1:, 2] + line[:-1, 2])
        zs.append(zmid)
        hs.append(h)
        s_got = float(dq[q, k][ii])
    zs, hs = np.concatenate(zs), np.concatenate(hs)
    o = np.argsort(zs)
    zs, hs = zs[o], hs[o]
    top = zm + b["margin_c"] + s_got * np.tan(np.radians(b["alpha_hi_deg"]))
    bot = zm - b["margin_c"] + s_got * np.tan(np.radians(b["alpha_lo_deg"]))
    a.axhspan(bot - zm, top - zm, color=ACCENT, alpha=0.10, lw=0)
    sel = (zs - zm > -1.6 * c) & (zs - zm < 2.2 * c)
    a.plot(hs[sel], zs[sel] - zm, "o-", color=INK, ms=2.6, lw=0.8)
    bc = rl.band_cell(s_got)
    a.axvline(bc, color=LIMIT, lw=1.0, ls="--")
    a.annotate(f"band cell here: {bc:.4f} c\n(limit inside the fan)", (bc, top - zm), xytext=(14, -26),
               textcoords="offset points", fontsize=8, color=LIMIT, bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none"))
    a.annotate("blue: inside the fan, every cell ≤ the band cell", (hs[sel].min() * 1.3, top - zm + 0.12),
               fontsize=8, color=ACCENT)
    a.set_xscale("log")
    a.set_xlabel("cell height [c] (log)")
    a.set_ylabel("height above the trailing edge [c]")
    a.set_title(f"(c) Cell height on the vertical line {s_got / c:.2f} local chords behind the trailing edge")
    a.grid(color=LINE, lw=0.5)

    # (d) top view: where the fan runs
    a = fig.add_subplot(gs[1, 1])
    le = np.array([s.ring[:, 0].min() for s in sts])
    te = np.array([s.wake.M[0] for s in sts])
    ch = np.array([s.chord for s in sts])
    end = te + float(b["length_local_c"]) * ch
    a.fill_betweenx(y, te, end, color=ACCENT, alpha=0.12, lw=0)
    a.plot(le, y, "-", color=INK, lw=1.2)
    a.plot(te, y, "-", color=INK, lw=1.2)
    a.plot(end, y, "-", color=ACCENT, lw=1.3)
    for kk in range(0, len(sts), 3):
        a.plot([le[kk], end[kk]], [y[kk], y[kk]], "-", color=MESH, lw=0.4, zorder=0)
    a.plot([le[k], end[k]], [y[k], y[k]], "-", color=LIMIT, lw=1.0)
    a.annotate("station of (a)", (end[k], y[k]), xytext=(4, 0), textcoords="offset points", fontsize=8,
               color=LIMIT, va="center")
    a.annotate("fan: from the trailing edge\nto 2 local chords behind it", (0.5 * (te[0] + end[0]) - 0.25, 0.42),
               fontsize=8, color=ACCENT, ha="center")
    a.annotate("half wing", (0.5 * (le[0] + te[0]), 0.35), fontsize=8.5, color=INK, ha="center")
    a.set_aspect("equal")
    a.set_xlabel("x [c]")
    a.set_ylabel("y [c] (root at 0, tip at the top)")
    a.set_title("(d) Top view: the fan runs behind every station")
    a.grid(color=LINE, lw=0.5)
    path = HERE / "docs" / "page" / f"{PREFIX}wake_fan.png"
    save(fig, path)
    print(path, "station", k, "y", st.y, "chord", c, "s_line", s_got, "band cell", bc, "cells", vm.cells)


if __name__ == "__main__":
    main()
