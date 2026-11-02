"""Pictures of one surface mesh: the planform with its stations, the root and tip rings with
the cell size along the chord, and the tip cap. Drawn from the mesh arrays, never by hand."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INK, MUTED, BAND, NOSE = "#1F2A33", "#8A96A3", "#D9822B", "#2B6CB0"


def overview(mesh, title: str, path: Path) -> Path:
    w, n_side = mesh.wing, mesh.info["n_side"]
    le = n_side - 1
    fig, ax = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle(title, fontsize=11, color=INK)

    # planform: every station as a chord line, nose and trailing edge
    a = ax[0, 0]
    for j in range(w.shape[1]):
        a.plot([w[le, j, 0], w[0, j, 0]], [w[le, j, 1], w[0, j, 1]], color=MUTED, lw=0.5)
    a.plot(w[le, :, 0], w[le, :, 1], color=INK, lw=1)
    a.plot(w[0, :, 0], w[0, :, 1], color=INK, lw=1)
    for y in mesh.info["loft_station_y_m"]:
        a.axhline(y, color=BAND, lw=0.6, ls="--")
    a.set_aspect("equal"); a.set_xlabel("x [m]"); a.set_ylabel("y [m]")
    a.set_title(f"{w.shape[1]} stations (dashed: loft stations b0..b3); gaps {mesh.info['cells_per_panel']} per panel", fontsize=9)

    # root and tip rings
    for a, j, name in ((ax[0, 1], 0, "root"), (ax[1, 1], w.shape[1] - 1, "tip")):
        r = np.vstack([w[:, j], w[:1, j]])
        a.plot(r[:, 0], r[:, 2], color=INK, lw=0.4)
        a.plot(r[:, 0], r[:, 2], ".", color=NOSE, ms=1.5)
        a.set_aspect("equal")
        row = mesh.stations[j]
        a.set_title(f"{name} ring: {w.shape[0]} nodes, chord {row['chord_m']:.3f} m, Re {row['re_local']:.2g}, "
                    f"nose turning {row['turning_deg']:.2f} deg", fontsize=9)
        a.set_xlabel("x [m]"); a.set_ylabel("z [m]")

    # cell size along the chord, root station, upper and lower
    a = ax[1, 0]
    j = 0
    c = mesh.stations[j]["chord_m"]
    for side, sl, col in (("upper", slice(0, n_side), NOSE), ("lower", slice(n_side - 1, 2 * n_side - 1), BAND)):
        pts = w[sl, j]
        u = mesh.u[sl, j]
        d = np.linalg.norm(np.diff(pts, axis=0), axis=1) / c
        a.semilogy(0.5 * (u[1:] + u[:-1]), d, color=col, lw=1, label=side)
    rules = mesh.info["rules"]
    a.axhline(mesh.stations[j]["h_band_c"], color=MUTED, ls=":", lw=0.8)
    a.axhline(rules["te_spacing_c"], color=MUTED, ls=":", lw=0.8)
    a.axvspan(*rules["band_upper"], color=NOSE, alpha=0.06)
    a.axvspan(*rules["band_lower"], color=BAND, alpha=0.06)
    a.set_xlabel("x / c"); a.set_ylabel("cell size / chord")
    a.set_title("root station: cell size along the chord (shaded: transition bands; dotted: band and TE targets)", fontsize=9)
    a.legend(fontsize=8)
    fig.tight_layout()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def cap_figure(mesh, title: str, path: Path) -> Path:
    cap = mesh.cap
    fig, ax = plt.subplots(figsize=(9, 4))
    for i in range(cap.shape[0]):
        ax.plot(cap[i, :, 0], cap[i, :, 2], color=MUTED, lw=0.3)
    for j in range(cap.shape[1]):
        ax.plot(cap[:, j, 0], cap[:, j, 2], color=INK, lw=0.4)
    ax.set_aspect("equal"); ax.set_title(title, fontsize=9)
    ax.set_xlabel("x [m]"); ax.set_ylabel("z [m]")
    fig.tight_layout()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path
