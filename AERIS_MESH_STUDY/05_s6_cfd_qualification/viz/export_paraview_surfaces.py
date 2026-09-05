#!/usr/bin/env python
"""Export S6 surface levels for ParaView, with the arrays that explain the march.

    .venv/bin/python AERIS_MESH_STUDY/05_s6_cfd_qualification/viz/export_paraview_surfaces.py

Two separate failures are on the table and they need different arrays:

  surface failure   the leading-edge wrap is starved, so cp exceeds its physical
                    bound on the nose collar.  Seen with `turn_deg` (surface
                    turning absorbed by one cell) and `corner_cut_um`.

  volume failure    the redesigned D family fixes the wrap and then will not
                    march.  ADR-0010 says the predictors are the staged
                    cell-size range and min-cell/`s0`, so both are attached per
                    cell as `edge_over_s0` and `edge_m`, alongside the growth
                    ratios that a hyperbolic march actually integrates.

Everything QC-shaped comes from the shared authoritative definitions
(`shared/qc.py`, `shared/gates.py`, `aeris.cfd.meshing.quality`) so the picture
and the QC table cannot disagree — the ADR-0011 section 4 rule.

To inspect: open the .vtk, colour by `edge_over_s0`, Threshold below 13 to
isolate the cells the march cannot fit its first layer into.  `block_id` and
`is_tip` separate the topology; `turn_deg` shows the leading-edge starvation.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve()
QUAL = HERE.parents[1]
STUDIES = HERE.parents[2] / "04_strategy_studies"
REPO_ROOT = HERE.parents[3]
for _p in (str(STUDIES), str(STUDIES / "S6_bounded_mesh_atlas"), str(REPO_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DEFAULT_LEVELS = (
    "candidate_c01", "candidate_c02", "candidate_c03",
    "candidate_d01", "candidate_d02", "candidate_d03",
)
SET_NAME = "lhs100_seed42"
INDEX = 83
OUT = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/paraview_inspection/s6_leading_edge"

#: ADR-0010 reference band, measured in Stage 02 and quoted in `shared/gates.py`:
#: min-cell/s0 of 0.9 exploded, 15.4 marched clean, 48.7 marched.  `ingestion.py`
#: records 7.6-17.6 as "mostly fails" and 13.1-20.0 as the succeeding band.
MARCH_FLOOR = 13.0


def build(level: str, spec=None):
    import strategy_s6

    if spec is not None:
        strategy_s6.LEVELS["_export_tmp"] = spec
        level = "_export_tmp"
    with tempfile.TemporaryDirectory() as tmp:
        blocks, info, _case = strategy_s6.build_locked_surface(
            SET_NAME, INDEX, Path(tmp), level=level
        )
    return blocks, info


def cell_arrays(xyz: np.ndarray, s0: float) -> dict[str, np.ndarray]:
    """Per-cell arrays on one structured block, in (ni-1, nj-1) order."""
    di = np.linalg.norm(np.diff(xyz, axis=0), axis=2)   # (ni-1, nj) i-edges
    dj = np.linalg.norm(np.diff(xyz, axis=1), axis=2)   # (ni, nj-1) j-edges
    # cell edge lengths: average the two opposite edges of each direction
    ei = 0.5 * (di[:, :-1] + di[:, 1:])                 # (ni-1, nj-1)
    ej = 0.5 * (dj[:-1, :] + dj[1:, :])                 # (ni-1, nj-1)
    smallest = np.minimum(ei, ej)
    largest = np.maximum(ei, ej)

    # growth of the i-spacing from cell to cell: what the march has to follow
    gi = np.ones_like(ei)
    if ei.shape[0] > 1:
        r = ei[1:, :] / np.maximum(ei[:-1, :], 1e-30)
        r = np.maximum(r, 1.0 / np.maximum(r, 1e-30))
        gi[:-1, :] = np.maximum(gi[:-1, :], r)
        gi[1:, :] = np.maximum(gi[1:, :], r)

    # surface turning absorbed by one cell, along i
    seg = np.diff(xyz, axis=0)
    unit = seg / np.maximum(np.linalg.norm(seg, axis=2, keepdims=True), 1e-30)
    turn = np.zeros(di.shape)                            # (ni-1, nj) per i-segment
    if unit.shape[0] > 1:
        cos = np.clip((unit[:-1] * unit[1:]).sum(axis=2), -1.0, 1.0)
        ang = np.degrees(np.arccos(cos))                 # (ni-2, nj) at interior nodes
        turn[:-1, :] += 0.5 * ang
        turn[1:, :] += 0.5 * ang
    turn_c = 0.5 * (turn[:, :-1] + turn[:, 1:])

    return {
        "edge_m": smallest,
        "edge_over_s0": smallest / s0,
        "chord_edge_m": ei,
        "span_edge_m": ej,
        "aspect_ratio": largest / np.maximum(smallest, 1e-30),
        "chord_growth": gi,
        "turn_deg": turn_c,
    }


def write_vtk(path: Path, blocks, s0: float) -> dict:
    from shared.export_paraview import cell_metrics

    points: list[np.ndarray] = []
    quads: list[tuple[int, int, int, int]] = []
    extra: dict[str, list[np.ndarray]] = {}
    sj_all, shape_all, skew_all, bid_all, tip_all = [], [], [], [], []
    offset = 0
    for bid, b in enumerate(blocks):
        xyz = np.asarray(b.xyz, dtype=float)
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
        sj_all.append(sj.ravel())
        shape_all.append(shape.ravel())
        skew_all.append(skew.ravel())
        bid_all.append(np.full(sj.size, bid))
        tip_all.append(np.full(sj.size, 1 if b.name.startswith("tip") else 0))
        for name, arr in cell_arrays(xyz, s0).items():
            extra.setdefault(name, []).append(arr.ravel())
        offset += ni * nj

    pts = np.concatenate(points, axis=0)
    arrays: dict[str, tuple[np.ndarray, str]] = {
        "scaled_jacobian": (np.concatenate(sj_all), "float"),
        "shape_metric": (np.concatenate(shape_all), "float"),
        "skewness": (np.concatenate(skew_all), "float"),
        "block_id": (np.concatenate(bid_all), "int"),
        "is_tip": (np.concatenate(tip_all), "int"),
    }
    for name, chunks in extra.items():
        arrays[name] = (np.concatenate(chunks), "float")

    lines = [
        "# vtk DataFile Version 3.0",
        f"AERIS S6 surface - {path.stem}",
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
    for name, (data, fmt) in arrays.items():
        lines.append(f"SCALARS {name} {fmt} 1")
        lines.append("LOOKUP_TABLE default")
        lines += [f"{v:.9g}" if fmt == "float" else f"{int(v)}" for v in data]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return {"cells": len(quads), "points": len(pts)}


def per_block_table(blocks, s0: float) -> list[dict]:
    rows = []
    for b in blocks:
        xyz = np.asarray(b.xyz, dtype=float)
        a = cell_arrays(xyz, s0)
        rows.append({
            "block": b.name,
            "shape": list(xyz.shape[:2]),
            "min_edge_m": float(a["edge_m"].min()),
            "min_edge_over_s0": round(float(a["edge_over_s0"].min()), 2),
            "max_edge_m": float(a["edge_m"].max()),
            "max_aspect_ratio": round(float(a["aspect_ratio"].max()), 1),
            "max_chord_growth": round(float(a["chord_growth"].max()), 3),
            "max_turn_deg": round(float(a["turn_deg"].max()), 2),
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--levels", nargs="*", default=list(DEFAULT_LEVELS))
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    from resolution import first_cell_fraction
    from shared.gates import marchability_metrics
    from shared.pyhyp_runner import characteristic_length
    from shared.qc import qc_blocks

    summary = {"schema": "aeris.s6.paraview_surface_export.v1",
               "set": SET_NAME, "index": INDEX,
               "march_floor_min_cell_over_s0": MARCH_FLOOR,
               "levels": {}}
    for level in args.levels:
        blocks, _info = build(level)
        char_len = characteristic_length(blocks)
        s0 = first_cell_fraction(level) * char_len
        qc = qc_blocks(blocks)
        march = marchability_metrics(qc, s0)
        path = args.out / f"{level}_surface.vtk"
        written = write_vtk(path, blocks, s0)
        summary["levels"][level] = {
            "vtk": str(path.relative_to(REPO_ROOT)),
            "characteristic_length_m": round(char_len, 6),
            "s0_m": s0,
            "s0_um": round(s0 * 1e6, 3),
            "cells": written["cells"],
            "min_scaled_jacobian": qc["global"]["min_scaled_jacobian"],
            "min_cell_edge_m": march["min_cell_edge_m"],
            "min_cell_edge_block": march["min_cell_edge_block"],
            "max_cell_edge_m": march["max_cell_edge_m"],
            "cell_size_range": round(march["cell_size_range"], 1),
            "min_cell_over_s0": round(march["min_cell_over_s0"], 2),
            "clears_march_floor": march["min_cell_over_s0"] >= MARCH_FLOOR,
            "blocks": per_block_table(blocks, s0),
        }
        print(f"{level:16s} min/s0 {march['min_cell_over_s0']:8.2f}"
              f"  range {march['cell_size_range']:8.1f}x"
              f"  min cell {march['min_cell_edge_m'] * 1e6:9.1f} um"
              f"  in {march['min_cell_edge_block']}")

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
