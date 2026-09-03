#!/usr/bin/env python
"""Render the S6 surface mesh, with the leading-edge wrap made visible.

The leading-edge defect is invisible in every integrated quantity, so the point
of these views is to show the wrap cells directly: how many there are and how
much the surface turns across each one.

    python visualize_surface.py --level candidate_c03 --out-dir <dir>
    python visualize_surface.py --compare candidate_c03 candidate_d03 --out-dir <dir>

Reads a built surface_blocks.npz, or builds one from the locked geometry.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve()
S6 = HERE.parents[2] / "04_strategy_studies/S6_bounded_mesh_atlas"
STUDIES = HERE.parents[2] / "04_strategy_studies"
for path in (str(STUDIES), str(S6), str(HERE.parents[3] / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

WRAP = "oml_nose"
BASE = "oml_base"


def load_blocks(level: str, npz: Path | None, index: int) -> dict[str, np.ndarray]:
    if npz is not None:
        data = np.load(npz, allow_pickle=True)
        return {name: np.asarray(data[name], dtype=float) for name in data.files}
    import tempfile

    from strategy_s6 import build_locked_surface

    with tempfile.TemporaryDirectory() as tmp:
        blocks, _info, _case = build_locked_surface(
            "lhs100_seed42", index, Path(tmp), level=level
        )
    return {b.name: np.asarray(b.xyz, dtype=float) for b in blocks}


def wrap_turning(wrap: np.ndarray) -> np.ndarray:
    """Total surface turning at each span station, in degrees."""
    out = []
    for station in range(wrap.shape[1]):
        seg = np.diff(wrap[:, station, :], axis=0)
        length = np.linalg.norm(seg, axis=1)
        unit = seg / length[:, None]
        cosines = np.clip((unit[:-1] * unit[1:]).sum(axis=1), -1.0, 1.0)
        out.append(np.degrees(np.arccos(cosines)).sum())
    return np.array(out)


def corner_cut(wrap: np.ndarray, station_fraction: float = 0.5) -> float:
    """How far the straight-line mesh falls inside the true curved surface.

    The mesh nodes sit on the exact pyGeo curve to within microns; it is the
    straight segments *between* them that cut the corner. That sagitta is the
    real geometric error at the leading edge, and it is what no integrated
    quantity reveals.
    """
    j = int(round(station_fraction * (wrap.shape[1] - 1)))
    line = wrap[:, j, :]
    worst = 0.0
    for i in range(len(line) - 2):
        p1, p2, p3 = line[i], line[i + 1], line[i + 2]
        a = np.linalg.norm(p2 - p3)
        b = np.linalg.norm(p1 - p3)
        c = np.linalg.norm(p1 - p2)
        s = 0.5 * (a + b + c)
        area = max(s * (s - a) * (s - b) * (s - c), 1.0e-30) ** 0.5
        radius = a * b * c / (4.0 * area)
        half = 0.5 * c
        worst = max(worst, radius - np.sqrt(max(radius * radius - half * half, 0.0)))
    return float(worst)


def section(blocks: dict[str, np.ndarray], station_fraction: float = 0.5):
    """One chordwise section, walking the blocks around the aerofoil."""
    wrap = blocks[WRAP]
    j = int(round(station_fraction * (wrap.shape[1] - 1)))
    y = wrap[0, j, 1]
    out = {}
    for name, block in blocks.items():
        if not name.startswith("oml_"):
            continue
        k = int(np.argmin(np.abs(block[0, :, 1] - y)))
        out[name] = block[:, k, :]
    return out, y


def plot_section(blocks, level, ax_full, ax_zoom):
    sec, y = section(blocks)
    colours = {
        "oml_nose": "#d1495b", "oml_base": "#3d7ea6",
        "oml_upper_fore": "#8d99ae", "oml_upper_aft": "#adb5bd",
        "oml_lower_fore": "#8d99ae", "oml_lower_aft": "#adb5bd",
    }
    for name, pts in sec.items():
        lw = 2.4 if name in (WRAP, BASE) else 1.0
        z = 3 if name in (WRAP, BASE) else 1
        for ax in (ax_full, ax_zoom):
            ax.plot(pts[:, 0], pts[:, 2], "-", color=colours.get(name, "#999"),
                    lw=lw, zorder=z)
            ax.plot(pts[:, 0], pts[:, 2], "o", color=colours.get(name, "#999"),
                    ms=4.5 if name in (WRAP, BASE) else 2.0, zorder=z + 1)

    nose = sec[WRAP]
    turning = wrap_turning(blocks[WRAP])
    cells = blocks[WRAP].shape[0] - 1
    per_cell = float(np.median(turning)) / cells

    ax_full.set_title(f"{level} — section at y = {y:.3f} m", fontsize=10)
    ax_full.set_aspect("equal")
    ax_full.set_xlabel("x (m)")
    ax_full.set_ylabel("z (m)")

    pad = 0.6 * (nose[:, 0].max() - nose[:, 0].min() + 1e-6)
    ax_zoom.set_xlim(nose[:, 0].min() - pad, nose[:, 0].max() + pad)
    ax_zoom.set_ylim(nose[:, 2].min() - pad, nose[:, 2].max() + pad)
    ax_zoom.set_aspect("equal")
    cut = corner_cut(blocks[WRAP])
    ax_zoom.set_title(
        f"leading edge: {cells} cells, {per_cell:.1f}° per cell\n"
        f"straight segments cut {cut * 1e6:.0f} µm inside the true surface",
        fontsize=10,
    )
    ax_zoom.set_xlabel("x (m)")
    ax_zoom.tick_params(axis="x", labelrotation=30, labelsize=8)
    return per_cell, cells, cut


def render(levels, blocks_by_level, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    n = len(levels)
    fig, axes = plt.subplots(n, 2, figsize=(11, 4.4 * n), squeeze=False)
    summary = {}
    for row, level in enumerate(levels):
        per_cell, cells, cut = plot_section(
            blocks_by_level[level], level, axes[row][0], axes[row][1]
        )
        summary[level] = {
            "wrap_cells": cells,
            "turning_per_cell_deg": per_cell,
            "corner_cut_m": cut,
            "corner_cut_um": cut * 1e6,
        }
    fig.suptitle(
        "S6 surface mesh — the leading-edge wrap is the red block",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    section_png = out_dir / "surface_sections.png"
    fig.savefig(section_png, dpi=150)
    plt.close(fig)

    # Planform, coloured by block, so the wrap can be seen running the full span.
    fig, axes = plt.subplots(1, n, figsize=(6.0 * n, 5.4), squeeze=False)
    for col, level in enumerate(levels):
        ax = axes[0][col]
        for name, block in blocks_by_level[level].items():
            colour = "#d1495b" if name == WRAP else (
                "#3d7ea6" if name == BASE else "#c9ccd1")
            ax.plot(block[:, :, 0].ravel(), block[:, :, 1].ravel(), ".",
                    ms=0.7, color=colour)
        ax.set_aspect("equal")
        ax.set_title(f"{level} planform — wrap in red", fontsize=10)
        ax.set_xlabel("x (m)")
        ax.set_ylabel("y, span (m)")
    fig.tight_layout()
    planform_png = out_dir / "surface_planform.png"
    fig.savefig(planform_png, dpi=150)
    plt.close(fig)

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return {"sections": str(section_png), "planform": str(planform_png),
            "summary": summary}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--level", default="candidate_c03")
    ap.add_argument("--compare", nargs="*", default=None,
                    help="two or more level names to place side by side")
    ap.add_argument("--npz", type=Path, default=None,
                    help="use an existing surface_blocks.npz instead of rebuilding")
    ap.add_argument("--index", type=int, default=83)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    levels = args.compare if args.compare else [args.level]
    blocks = {lv: load_blocks(lv, args.npz if len(levels) == 1 else None, args.index)
              for lv in levels}
    result = render(levels, blocks, args.out_dir)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
