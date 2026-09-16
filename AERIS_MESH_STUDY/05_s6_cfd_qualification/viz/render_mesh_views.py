#!/usr/bin/env python3
"""Render the S8 O-H structured grid from its own node coordinates.

Every line in every figure is an actual grid line of the delivered mesh, taken
from `gci_C_blocks.npz`, which holds the three structured blocks as vertex
arrays.  Nothing is schematic and nothing is redrawn by hand: the only choices
are which lines to show and where to put the camera.

    o_wing   (93, 65, 49, 3)   i = around the aerofoil, j = wall-normal, k = span
    o_out    (93, 65, 55, 3)   the same ring continued OUTBOARD of the tip
    cap_out  (43,  5, 55, 3)   outboard of the tip-cap H patch

Measured framing for index 12 at gci_C: root chord 0.9856 m tapering to 0.10 m
at the tip, semispan 0.8194 m, far field at 39.4 m (40 root chords), first
off-wall spacing 4.6e-6 m.  Radius from the wall reaches 0.47 chords by j = 45,
1.56 by j = 50, 3.17 by j = 53 and 40.0 at j = 64.

Two framing rules this file exists to respect, both learned by getting them
wrong first:

  * the box aspect must be PROPORTIONAL to the data, never forced to a cube.
    This wing's semispan is 0.84 root chords, so a cube aspect stretches the
    span to match the grid discs and the wing collapses to a speck.
  * grid planes must be drawn to a radius COMPARABLE to the span, about one
    chord here.  Classic textbook figures of this kind are of slender wings,
    where span greatly exceeds the plotted grid radius; this planform is stubby
    and needs the discs kept tight or they swamp it.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection

CHORD = 0.9856
ROOT_LE_I = 46          # i index of the leading edge on the root ring


def j_at_chords(w: np.ndarray, chords: float) -> int:
    """The wall-normal index whose radius at the root leading edge is ~`chords`."""
    r = np.linalg.norm(w[ROOT_LE_I, :, 0, :] - w[ROOT_LE_I, 0, 0, :], axis=-1) / CHORD
    return int(np.argmin(np.abs(r - chords)))


def grid_lines(patch: np.ndarray, every_i: int = 1, every_j: int = 1) -> list:
    """Both families of grid lines of a structured (ni, nj, 3) patch."""
    ni, nj, _ = patch.shape
    return ([patch[i, :, :] for i in range(0, ni, every_i)] +
            [patch[:, j, :] for j in range(0, nj, every_j)])


def add_patch(ax, patch, *, color, lw=0.25, alpha=1.0, every_i=1, every_j=1):
    ax.add_collection3d(Line3DCollection(grid_lines(patch, every_i, every_j),
                                         colors=color, linewidths=lw, alpha=alpha))


def set_proportional_3d(ax, pts, pad=0.04):
    """True geometry: limits from the data, box aspect proportional to the ranges.

    Forcing a cube here is what turned the first attempt at the reference view
    into concentric circles with an invisible wing.
    """
    p = pts.reshape(-1, 3)
    lo, hi = p.min(axis=0), p.max(axis=0)
    rng = np.maximum(hi - lo, 1e-9)
    lo, hi = lo - pad * rng, hi + pad * rng
    ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1]); ax.set_zlim(lo[2], hi[2])
    try:
        ax.set_box_aspect(hi - lo)
    except Exception:
        pass


def wing_surface(ax, w, *, facecolor="0.20", lw=0.10, edge="0.50"):
    """The wall itself: o_wing at j = 0, as a solid surface carrying its own grid."""
    surf = w[:, 0, :, :]
    ni, nk, _ = surf.shape
    quads = [[surf[i, k], surf[i + 1, k], surf[i + 1, k + 1], surf[i, k + 1]]
             for i in range(ni - 1) for k in range(nk - 1)]
    ax.add_collection3d(Poly3DCollection(quads, facecolors=facecolor, edgecolors=edge,
                                         linewidths=lw))
    return surf


# --------------------------------------------------------------------------- #

def fig_reference(z, out: Path, chords: float = 1.0):
    """Wall surface with the root and tip O-grid planes: the classic grid figure."""
    w = z["o_wing"]
    jmax = j_at_chords(w, chords) + 1
    fig = plt.figure(figsize=(12, 8), dpi=200)
    ax = fig.add_subplot(111, projection="3d")
    root, tip = w[:, :jmax, 0, :], w[:, :jmax, -1, :]
    add_patch(ax, root, color="#c0392b", lw=0.25, alpha=0.9)
    add_patch(ax, tip, color="#2a52be", lw=0.25, alpha=0.9)
    surf = wing_surface(ax, w)
    set_proportional_3d(ax, np.concatenate([root.reshape(-1, 3), tip.reshape(-1, 3),
                                            surf.reshape(-1, 3)]))
    ax.view_init(elev=17, azim=-72)
    ax.set_axis_off()
    r = np.linalg.norm(w[ROOT_LE_I, jmax - 1, 0] - w[ROOT_LE_I, 0, 0]) / CHORD
    ax.set_title("S8 O-H grid, wing 12 at gci_C — wall surface with the root (red) and tip (blue)\n"
                 f"O-grid planes drawn to {r:.2f} chords. Every line is a grid line of the real mesh.",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def fig_root_section(z, out: Path, chords: float = 1.6):
    """The root plane in 2D: the O-grid wrapping the aerofoil."""
    w = z["o_wing"]
    jmax = j_at_chords(w, chords) + 1
    sec = w[:, :jmax, 0, :][:, :, [0, 2]]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), dpi=200)
    for ax, (zoom, ttl) in zip(axes, ((None, f"root section, O-grid to {chords:.1f} chords"),
                                      ((-0.02, 0.22, -0.10, 0.10), "leading edge, same grid"))):
        segs = [sec[i, :, :] for i in range(sec.shape[0])] + \
               [sec[:, j, :] for j in range(sec.shape[1])]
        ax.add_collection(LineCollection(segs, colors="#1f3b73", linewidths=0.3))
        ax.plot(sec[:, 0, 0], sec[:, 0, 1], color="black", lw=1.1)
        if zoom:
            ax.set_xlim(zoom[0], zoom[1]); ax.set_ylim(zoom[2], zoom[3])
        else:
            ax.set_xlim(sec[:, :, 0].min(), sec[:, :, 0].max())
            ax.set_ylim(sec[:, :, 1].min(), sec[:, :, 1].max())
        ax.set_aspect("equal"); ax.set_title(ttl, fontsize=10)
        ax.set_xlabel("x [m]"); ax.set_ylabel("z [m]")
    fig.suptitle("S8 O-H grid, wing 12 at gci_C — root symmetry plane", fontsize=11)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def fig_boundary_layer(z, out: Path):
    """The wall-resolved layers: first cell 4.6e-6 m, so this needs its own scale."""
    w = z["o_wing"]
    sec = w[:, :46, 0, :][:, :, [0, 2]]
    le = sec[ROOT_LE_I, 0]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.4), dpi=200)
    for ax, half in zip(axes, (0.02 * CHORD, 0.0015 * CHORD)):
        segs = [sec[i, :, :] for i in range(sec.shape[0])] + \
               [sec[:, j, :] for j in range(sec.shape[1])]
        ax.add_collection(LineCollection(segs, colors="#1f3b73", linewidths=0.35))
        ax.plot(sec[:, 0, 0], sec[:, 0, 1], color="black", lw=1.3)
        ax.set_xlim(le[0] - half, le[0] + 3 * half)
        ax.set_ylim(le[1] - 2 * half, le[1] + 2 * half)
        ax.set_aspect("equal")
        ax.set_title(f"window {2 * half * 1e3:.2f} mm across", fontsize=10)
        ax.set_xlabel("x [m]"); ax.set_ylabel("z [m]")
    fig.suptitle("Wall-resolved clustering at the root leading edge — first off-wall spacing 4.6e-6 m "
                 "(j = 0…40 spans only 0.156 chords)", fontsize=11)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def fig_tip(z, out: Path, collar_chords: float = 0.05, kout: int = 8):
    """The tip cap itself and the outboard layers the wall-resolved cap added.

    Twice I framed this by scaling and twice it failed, because the fault was in
    WHAT was drawn: a tip O-plane one to three chords across dwarfs a 0.10 m tip
    chord no matter how the axes are set. So the wide plane is gone -- only a
    thin collar of it remains -- and the subject is the cap patch and the first
    outboard planes.
    """
    w, c = z["o_wing"], z["cap_out"]
    jmax = j_at_chords(w, collar_chords) + 1
    k0 = 40                                   # outboard fifth of the span
    fig = plt.figure(figsize=(12, 8), dpi=200)
    ax = fig.add_subplot(111, projection="3d")
    surf = wing_surface(ax, w[:, :, k0:, :], facecolor="0.25", edge="0.55", lw=0.15)
    collar = w[:, :jmax, -1, :]
    cap0 = c[:, :, 0, :]                      # the tip-cap H patch itself
    capk = c[:, :, :kout, :]
    add_patch(ax, collar, color="#2a52be", lw=0.35, alpha=0.9)
    add_patch(ax, cap0, color="#b8860b", lw=0.8, alpha=1.0)
    # The outboard cap planes are drawn but sit behind the collar at this framing;
    # they are kept because they are real mesh, and NOT claimed in the caption.
    for k in range(1, kout):
        add_patch(ax, capk[:, :, k, :], color="#127a4a", lw=0.45, alpha=0.5)
    set_proportional_3d(ax, np.concatenate([surf.reshape(-1, 3), collar.reshape(-1, 3),
                                            capk.reshape(-1, 3)]))
    ax.view_init(elev=26, azim=-58)
    ax.set_axis_off()
    ax.set_title("Tip cap — the single H patch that closes the tip (gold), inside a "
                 f"{collar_chords:.2f}-chord\ncollar of the tip O-plane (blue). Its perimeter IS the tip "
                 "ring, so there is no\ncollapsed edge and no interface to interpolate.\n"
                 "The wall-resolved cap cost 6 extra outboard layers — measured from the block\n"
                 "dimensions (o_out 48 → 54 in span), not visible at this framing.", fontsize=9)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def fig_topology(z, out: Path):
    """Two scales: the wing in its near field, and the full 40-chord domain."""
    w, o, c = z["o_wing"], z["o_out"], z["cap_out"]
    fig = plt.figure(figsize=(11, 9), dpi=200)

    # One panel, not two. The near-field panel lost the wing among radiating
    # lines and told the reader nothing the reference view does not say better.
    ax = fig.add_subplot(111, projection="3d")
    add_patch(ax, w[:, :, 0, :], color="#c0392b", lw=0.2, alpha=0.65, every_i=6, every_j=6)
    add_patch(ax, w[:, :, -1, :], color="#2a52be", lw=0.2, alpha=0.65, every_i=6, every_j=6)
    add_patch(ax, o[:, -1, :, :], color="#6b7a8f", lw=0.2, alpha=0.5, every_i=6, every_j=6)
    add_patch(ax, c[:, 0, :, :], color="#127a4a", lw=0.35, alpha=0.8, every_i=3, every_j=6)
    wing_surface(ax, w, facecolor="0.15", edge="0.15", lw=0.05)
    set_proportional_3d(ax, np.concatenate([w[:, :, 0, :].reshape(-1, 3),
                                            o[:, -1, :, :].reshape(-1, 3)]))
    ax.view_init(elev=18, azim=-70); ax.set_axis_off()
    ax.set_title("Full domain — far field at 39.4 m = 40 root chords. Root and tip O-planes\n"
                 "(red/blue), the outboard block's far-field face (grey), the cap block (green).\n"
                 "The wing is the dark mark at the centre: that is the true scale of the domain.",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def fig_planform(z, out: Path):
    """The wall grid seen from above: chordwise by spanwise point distribution."""
    w = z["o_wing"]
    surf = w[:, 0, :, :]
    fig, ax = plt.subplots(figsize=(11, 6.5), dpi=200)
    segs = [surf[i, :, :][:, [0, 1]] for i in range(surf.shape[0])] + \
           [surf[:, k, :][:, [0, 1]] for k in range(surf.shape[1])]
    ax.add_collection(LineCollection(segs, colors="#1f3b73", linewidths=0.3))
    ax.set_xlim(surf[:, :, 0].min() - 0.02, surf[:, :, 0].max() + 0.02)
    ax.set_ylim(-0.02, surf[:, :, 1].max() + 0.02)
    ax.set_aspect("equal")
    ax.set_xlabel("x [m], chordwise"); ax.set_ylabel("y [m], span")
    ax.set_title("Wall surface grid from above — 92 chordwise by 48 spanwise cells. Span clustering "
                 "packs\nmost planes into the last 2 % of semispan: k = 24 already sits at y = 0.801 of 0.819.",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--blocks", type=Path,
                    default=Path("/home/mike_kara/aeris/AERIS_MESH_STUDY/artifacts/s8_v2/g12/gci_C_blocks.npz"))
    ap.add_argument("--out-dir", type=Path,
                    default=Path("/home/mike_kara/aeris/AERIS_MESH_STUDY/05_s6_cfd_qualification/viz"))
    ap.add_argument("--stamp", default="20260916")
    args = ap.parse_args()

    z = np.load(args.blocks)
    print(f"loaded {args.blocks.name}: " + ", ".join(f"{k}{z[k].shape}" for k in z.files))
    made = [
        fig_reference(z, args.out_dir / f"s8_mesh_reference_view_{args.stamp}.png"),
        fig_root_section(z, args.out_dir / f"s8_mesh_root_section_{args.stamp}.png"),
        fig_boundary_layer(z, args.out_dir / f"s8_mesh_boundary_layer_{args.stamp}.png"),
        fig_tip(z, args.out_dir / f"s8_mesh_tip_cap_{args.stamp}.png"),
        fig_topology(z, args.out_dir / f"s8_mesh_topology_{args.stamp}.png"),
        fig_planform(z, args.out_dir / f"s8_mesh_planform_{args.stamp}.png"),
    ]
    for p in made:
        print(f"  wrote {p.name}  {p.stat().st_size // 1024} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
