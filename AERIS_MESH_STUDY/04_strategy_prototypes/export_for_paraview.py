"""Export Stage 02 strategy surfaces as VTK for manual ParaView inspection.

Writes one legacy-VTK unstructured grid per strategy per geometry, with every
block merged and per-CELL quality arrays attached, so the bad cells can be found
by thresholding rather than by hunting visually:

    scaled_jacobian   minimum corner scaled Jacobian, signed. NEGATIVE = folded.
    shape_metric      minimum corner shape metric. Near zero = degenerate.
    skewness          equiangle skewness, 0 good, 1 degenerate.
    block_id          integer index of the source block.
    is_tip            1 for tip-cap blocks, 0 for OML blocks.

Run from the repository root:

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_prototypes/export_for_paraview.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))
for sub in ("", "S1_tip_first", "S3_station_sweep", "S4_analytic_multiblock", "S5_frozen_rbf"):
    sys.path.insert(0, str(HERE / sub))

import strategy_s1  # noqa: E402
import strategy_s3  # noqa: E402
import strategy_s4  # noqa: E402
import strategy_s5  # noqa: E402
from aeris.dataset.sampling.samplers.lhs_v1 import build_lhs_design_matrix  # noqa: E402
from aeris.generators.bwb_segmented_v1.params import (  # noqa: E402
    BWBDesignSample,
    build_bwb_generator_config,
)
from aeris.geometry.registry import get_geometry_generator  # noqa: E402

OUT_DIR = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/stage02/paraview"
GEOMETRIES = (0, 3, 7)


def cell_metrics(xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-cell signed scaled Jacobian, shape metric and equiangle skewness."""
    p00, p10 = xyz[:-1, :-1], xyz[1:, :-1]
    p11, p01 = xyz[1:, 1:], xyz[:-1, 1:]
    normal = np.cross(p10 - p00, p01 - p00)
    ref = normal.reshape(-1, 3).sum(axis=0)
    ref = ref / (np.linalg.norm(ref) or 1.0)

    corners = [
        (p10 - p00, p01 - p00),
        (p11 - p10, p00 - p10),
        (p01 - p11, p10 - p11),
        (p00 - p01, p11 - p01),
    ]
    sj, shape, angles = [], [], []
    for e1, e2 in corners:
        n1 = np.linalg.norm(e1, axis=2)
        n2 = np.linalg.norm(e2, axis=2)
        denom = np.where(n1 * n2 < 1e-30, 1e-30, n1 * n2)
        sj.append(np.einsum("ijk,k->ij", np.cross(e1, e2), ref) / denom)
        cr = np.linalg.norm(np.cross(e1, e2), axis=2)
        d2 = np.sum(e1 * e1, axis=2) + np.sum(e2 * e2, axis=2)
        shape.append(np.divide(2 * cr, d2, out=np.zeros_like(cr), where=d2 > 0))
        cosang = np.clip(np.sum(e1 * e2, axis=2) / denom, -1.0, 1.0)
        angles.append(np.degrees(np.arccos(cosang)))
    sj = np.min(np.stack(sj), axis=0)
    shape = np.min(np.stack(shape), axis=0)
    angles = np.stack(angles)
    skew = np.maximum((angles.max(axis=0) - 90.0) / 90.0, (90.0 - angles.min(axis=0)) / 90.0)
    return sj, shape, np.clip(skew, 0.0, 1.0)


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
        f"AERIS Stage 02 surface - {path.stem}",
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


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = build_bwb_generator_config(
        yaml.safe_load((REPO_ROOT / "configs/geometry/bwb.yaml").read_text())
    )
    matrix = build_lhs_design_matrix(cfg, 10, np.random.default_rng(7))
    names = cfg.active_design_variable_names()
    gen = get_geometry_generator("bwb_segmented")

    wings = {}
    for i in sorted(set(GEOMETRIES) | {0}):
        sample = BWBDesignSample(**{n: float(v) for n, v in zip(names, matrix[i], strict=True)})
        wings[i] = gen.run_full_case(
            sample=sample,
            config=cfg,
            output_dir=REPO_ROOT / f"AERIS_MESH_STUDY/artifacts/stage02/geom/lhs7_{i:02d}",
            save_plot=False,
            build_aerosandbox=True,
        ).wing

    builders = {
        "S1_tip_first": lambda w: strategy_s1.build_surface(w)[0],
        "S3_station_sweep": lambda w: strategy_s3.build_surface(w)[0],
        "S4_analytic_multiblock": lambda w: strategy_s4.build_surface(w)[0],
        "S5_frozen_rbf": lambda w: strategy_s5.build_surface(wings[0], w)[0],
    }

    summary = []
    for sid, build in builders.items():
        for i in GEOMETRIES:
            path = OUT_DIR / f"{sid}__lhs7_{i:02d}.vtk"
            stats = write_vtk(path, build(wings[i]))
            summary.append((path.name, stats))
            print(
                f"{path.name:44s} cells={stats['cells']:6d} "
                f"folded={stats['folded_cells']:4d} min_sj={stats['min_scaled_jacobian']:+.4f}"
            )

    readme = [
        "# Stage 02 surfaces for ParaView",
        "",
        "One file per strategy per geometry. All blocks are merged into a single",
        "unstructured grid; use the `block_id` array to separate them again.",
        "",
        "## Finding the defect quickly",
        "",
        "1. Open a file, set Representation to **Surface With Edges**.",
        "2. Colour by **scaled_jacobian**. Negative means the cell is folded.",
        "3. Apply a **Threshold** filter on `scaled_jacobian` from -1 to 0 to isolate",
        "   the folded cells. They should all sit in the tip cap.",
        "4. `is_tip` = 1 selects the tip-cap blocks, 0 the OML blocks.",
        "",
        "## What to look for",
        "",
        "The OML is healthy on every strategy (worst scaled Jacobian about +0.57",
        "across the whole ten-geometry set). Every folded cell is in the tip cap.",
        "The current diagnosis is that the cap's inner ring locally leaves the",
        "section on the cambered lower surface, so the inner and outer rings cross;",
        "in ParaView that should look like the cap's inner grid lines bulging",
        "through or touching the lower contour rather than staying inside it.",
        "",
        "S4 uses a different tip construction (four analytic domains) from S1/S3/S5",
        "(five-block butterfly), so it is worth comparing those two families.",
        "",
        "| file | cells | folded cells | min scaled Jacobian |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, st in summary:
        readme.append(
            f"| `{name}` | {st['cells']} | {st['folded_cells']} | {st['min_scaled_jacobian']:+.4f} |"
        )
    (OUT_DIR / "README.md").write_text("\n".join(readme) + "\n")
    print(f"\nwrote {len(summary)} VTK files + README.md to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
