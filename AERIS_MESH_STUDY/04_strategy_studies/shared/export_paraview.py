"""ParaView export — SHARED CONTROL.

ADR-0011 section 4: one exporter, so that inspecting two strategies' meshes means
looking at the same arrays computed the same way. Migrated unchanged from
`04_strategy_prototypes/export_for_paraview.py`.

Writes one legacy-VTK unstructured grid per call, with every block merged and
per-CELL quality arrays attached, so bad cells are found by thresholding rather
than by hunting visually:

    scaled_jacobian   minimum corner scaled Jacobian, signed. NEGATIVE = folded.
    shape_metric      minimum corner shape metric. Near zero = degenerate.
    skewness          equiangle skewness, 0 good, 1 degenerate.
    block_id          integer index of the source block.
    is_tip            1 for tip-cap blocks, 0 for OML blocks.

To inspect: open the .vtk, colour by `scaled_jacobian`, Threshold -1 to 0 to
isolate folds. `is_tip` separates cap from OML. Mike inspects meshes in ParaView,
so this is the intended output of any surface diagnosis.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def cell_metrics(xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-cell scaled Jacobian, shape metric and equiangle skewness.

    **Instrument bug 9**, found on 2026-08-14 while exporting S0 for ParaView and
    fixed here. This function used to compute the scaled Jacobian against a
    BLOCK-AVERAGED reference normal::

        ref = normal.reshape(-1, 3).sum(axis=0); ref /= norm(ref)

    That is meaningless for a block that curves through a large angle. cap4's
    `oml_nose_wrap` wraps around the leading edge, so cells on opposite sides have
    opposing normals, their average is near zero, and the sign flips arbitrarily.
    The exporter reported **7 folded cells and a minimum of -0.132** on a surface
    that `qc_blocks` scores at **+0.191 with no negative cell anywhere** — and it
    reported them in the file a human opens to go looking for folds.

    The authoritative metric signs each corner against the cell's OWN first-corner
    normal (`aeris.cfd.meshing.quality.scaled_jacobian`). It is now called
    directly, along with the authoritative skewness, so the picture and the QC
    table cannot disagree again. That is what ADR-0011 section 4 means by sharing
    QC metric *definitions*: one definition, used everywhere, including in the
    pictures.
    """
    from aeris.cfd.meshing.quality import equiangle_skewness, scaled_jacobian

    from .ingestion import _corner_shape_metric

    return scaled_jacobian(xyz), _corner_shape_metric(xyz), equiangle_skewness(xyz)


def write_vtk(path: Path, blocks) -> dict:
    points: list[np.ndarray] = []
    quads: list[tuple[int, int, int, int]] = []
    sj_all, shape_all, skew_all, bid_all, tip_all = [], [], [], [], []
    offset = 0
    for bid, b in enumerate(blocks):
        xyz = b.xyz
        ni, nj, _ = xyz.shape
        points.append(xyz.reshape(-1, 3))
        for i in range(ni - 1):
            for j in range(nj - 1):
                quads.append(
                    (
                        offset + i * nj + j,
                        offset + (i + 1) * nj + j,
                        offset + (i + 1) * nj + j + 1,
                        offset + i * nj + j + 1,
                    )
                )
        sj, shape, skew = cell_metrics(xyz)
        n_cells = sj.size
        sj_all.append(sj.ravel())
        shape_all.append(shape.ravel())
        skew_all.append(skew.ravel())
        bid_all.append(np.full(n_cells, bid))
        tip_all.append(np.full(n_cells, 1 if b.name.startswith("tip") else 0))
        offset += ni * nj

    pts = np.concatenate(points, axis=0)
    sj = np.concatenate(sj_all)
    lines = [
        "# vtk DataFile Version 3.0",
        f"AERIS strategy study surface - {path.stem}",
        "ASCII",
        "DATASET UNSTRUCTURED_GRID",
        f"POINTS {len(pts)} float",
    ]
    lines += [f"{p[0]:.9g} {p[1]:.9g} {p[2]:.9g}" for p in pts]
    lines.append(f"CELLS {len(quads)} {5 * len(quads)}")
    lines += [f"4 {a} {b} {c} {d}" for a, b, c, d in quads]
    lines.append(f"CELL_TYPES {len(quads)}")
    lines += ["9"] * len(quads)
    lines.append(f"CELL_DATA {len(quads)}")
    for name, data, fmt in (
        ("scaled_jacobian", sj, "float"),
        ("shape_metric", np.concatenate(shape_all), "float"),
        ("skewness", np.concatenate(skew_all), "float"),
        ("block_id", np.concatenate(bid_all), "int"),
        ("is_tip", np.concatenate(tip_all), "int"),
    ):
        lines.append(f"SCALARS {name} {fmt} 1")
        lines.append("LOOKUP_TABLE default")
        lines += [f"{v:.9g}" if fmt == "float" else f"{int(v)}" for v in data]
    path.write_text("\n".join(lines) + "\n")
    return {
        "cells": len(quads),
        "folded_cells": int((sj < 0).sum()),
        "min_scaled_jacobian": float(sj.min()),
    }
