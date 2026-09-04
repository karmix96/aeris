#!/usr/bin/env python
"""Write the S8 closed wing surface for ParaView: O-ring OML plus butterfly tip cap.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/export_surface.py \
        --level oh_L3

Surface only, no volume.  This is the file to open when the question is about
topology rather than about the boundary layer: how the ring runs around the
section, where the leading-edge clustering sits, and how the tip closes without
a collapsed pole.

Quality arrays come from the shared exporter (`shared/export_paraview.py`), so
they are the same `scaled_jacobian`, `shape_metric` and `skewness` definitions
every other strategy is judged on -- ADR-0011 section 4.  Two arrays are added
that matter for this topology specifically:

    turn_deg        surface turning absorbed by one cell along the ring.  The
                    whole point of S8: it is a request, not an outcome.
    edge_over_s0    smallest cell edge over the first cell height.  ADR-0010's
                    marchability predictor, the one D03 failed at 8.8.

To inspect: colour by `turn_deg` and zoom the leading edge; `is_tip` separates
the cap from the OML; `block_id` separates the three blocks.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (
    str(HERE), str(HERE.parent), str(HERE.parent / "S6_bounded_mesh_atlas"), str(REPO / "src")
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import strategy_s8  # noqa: E402
from shared.ingestion import SurfaceBlock  # noqa: E402

Array = np.ndarray


def ring_cell_arrays(xyz: Array, s0: float) -> dict[str, Array]:
    """Per-cell turning and edge ratio on a block whose first axis is the ring."""
    di = np.linalg.norm(np.diff(xyz, axis=0), axis=2)
    dj = np.linalg.norm(np.diff(xyz, axis=1), axis=2)
    ei = 0.5 * (di[:, :-1] + di[:, 1:])
    ej = 0.5 * (dj[:-1, :] + dj[1:, :])
    smallest = np.minimum(ei, ej)

    seg = np.diff(xyz, axis=0)
    unit = seg / np.maximum(np.linalg.norm(seg, axis=2, keepdims=True), 1.0e-30)
    turn = np.zeros(di.shape)
    if unit.shape[0] > 1:
        cos = np.clip((unit[:-1] * unit[1:]).sum(axis=2), -1.0, 1.0)
        ang = np.degrees(np.arccos(cos))
        turn[:-1, :] += 0.5 * ang
        turn[1:, :] += 0.5 * ang
    return {
        "turn_deg": 0.5 * (turn[:, :-1] + turn[:, 1:]),
        "edge_over_s0": smallest / s0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--level", default="oh_L3", choices=sorted(strategy_s8.LEVELS))
    ap.add_argument("--set-name", default="lhs100_seed42")
    ap.add_argument("--index", type=int, default=83)
    ap.add_argument("--out", type=Path,
                    default=REPO / "AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh")
    args = ap.parse_args()

    import strategy_s6
    from shared.export_paraview import cell_metrics
    from shared.qc import qc_blocks

    level = strategy_s8.LEVELS[args.level]
    with tempfile.TemporaryDirectory() as tmp:
        _b, _i, case = strategy_s6.build_locked_surface(
            args.set_name, args.index, Path(tmp), level="candidate_c01"
        )
    pygeo = case.pygeo_result.pygeo.geometry

    oml, report = strategy_s8.build_oml_ring(pygeo, level)
    cap_blocks, cap_info = strategy_s8.build_tip_cap(oml[:, -1, :], level)

    # Close the ring seam for display.  As a structured block the ring's first
    # and last rows are adjacent but not joined, so without this there is a
    # one-cell slit down the trailing edge in ParaView that looks like a defect
    # and is not one.  The duplicated row is display-only and is not written to
    # the volume grid, where periodicity is handled by the block connectivity.
    oml_closed = np.concatenate([oml, oml[:1]], axis=0)

    diagonal = float(np.linalg.norm(np.ptp(oml.reshape(-1, 3), axis=0)))
    s0 = level.s0_frac * diagonal

    blocks = [SurfaceBlock(name="oml_ring", xyz=oml_closed, family="wall")] + cap_blocks
    qc = qc_blocks(blocks)

    points: list[Array] = []
    quads: list[tuple[int, int, int, int]] = []
    arrays: dict[str, list[Array]] = {}
    offset = 0
    for bid, block in enumerate(blocks):
        xyz = np.asarray(block.xyz, dtype=float)
        ni, nj, _ = xyz.shape
        points.append(xyz.reshape(-1, 3))
        for i in range(ni - 1):
            for j in range(nj - 1):
                quads.append((
                    offset + i * nj + j,
                    offset + (i + 1) * nj + j,
                    offset + (i + 1) * nj + j + 1,
                    offset + i * nj + j + 1,
                ))
        sj, shape, skew = cell_metrics(xyz)
        extra = ring_cell_arrays(xyz, s0)
        for name, data in (
            ("scaled_jacobian", sj), ("shape_metric", shape), ("skewness", skew),
            ("turn_deg", extra["turn_deg"]), ("edge_over_s0", extra["edge_over_s0"]),
            ("block_id", np.full(sj.shape, bid)),
            ("is_tip", np.full(sj.shape, 0 if bid == 0 else 1)),
        ):
            arrays.setdefault(name, []).append(np.asarray(data).ravel())
        offset += ni * nj

    pts = np.concatenate(points, axis=0)
    lines = [
        "# vtk DataFile Version 3.0",
        f"AERIS S8 O-H closed wing surface - {args.level}",
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
    for name, chunks in arrays.items():
        data = np.concatenate(chunks)
        fmt = "int" if name in ("block_id", "is_tip") else "float"
        lines.append(f"SCALARS {name} {fmt} 1")
        lines.append("LOOKUP_TABLE default")
        lines += [f"{int(v)}" if fmt == "int" else f"{v:.9g}" for v in data]

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.level}_surface.vtk"
    path.write_text("\n".join(lines) + "\n")

    summary = {
        "schema": "aeris.s8.oh_surface.v1",
        "level": args.level,
        "blocks": {b.name: list(np.asarray(b.xyz).shape[:2]) for b in blocks},
        "cells": len(quads),
        "target_le_turn_deg": report["target_le_turn_deg"],
        "worst_le_turn_per_cell_deg": report["worst_le_turn_per_cell_deg"],
        "all_stations_met_target": report["all_stations_met_target"],
        "min_scaled_jacobian": qc["global"]["min_scaled_jacobian"],
        "max_equiangle_skewness": qc["global"]["max_equiangle_skewness"],
        "max_adjacent_normal_angle_deg": qc["global"]["max_adjacent_normal_angle_deg"],
        "min_cell_edge_m": qc["min_cell_edge_m"],
        "min_cell_edge_block": qc["min_cell_edge_block"],
        "cell_size_range": qc["cell_size_range"],
        "min_cell_over_s0": qc["min_cell_edge_m"] / s0,
        "s0_m": s0,
        "tip_cap": cap_info,
        "vtk": str(path.relative_to(REPO)),
    }
    (args.out / f"{args.level}_surface_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
