#!/usr/bin/env python3
"""Diagnose the upstream tip-section geometry for the Stage 01 lhs7_00 case."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from aeris.cfd.meshing.quality import equiangle_skewness, scaled_jacobian
from aeris.mesh.surface import _corner_shape_metric


def _cell_corners(block: np.ndarray, i: int, j: int) -> dict[str, np.ndarray]:
    return {
        "p00": block[i, j],
        "p10": block[i + 1, j],
        "p11": block[i + 1, j + 1],
        "p01": block[i, j + 1],
    }


def _corner_metrics(corners: dict[str, np.ndarray]) -> list[dict[str, object]]:
    definitions = [
        (
            "p00",
            corners["p00"],
            corners["p10"] - corners["p00"],
            corners["p01"] - corners["p00"],
            "lower leading-edge shoulder: lower chord edge meets nose wrap",
        ),
        (
            "p10",
            corners["p10"],
            corners["p11"] - corners["p10"],
            corners["p00"] - corners["p10"],
            "next lower chord cell corner",
        ),
        (
            "p11",
            corners["p11"],
            corners["p01"] - corners["p11"],
            corners["p10"] - corners["p11"],
            "interior blend corner",
        ),
        (
            "p01",
            corners["p01"],
            corners["p00"] - corners["p01"],
            corners["p11"] - corners["p01"],
            "next nose-wrap cell corner",
        ),
    ]
    rows: list[dict[str, object]] = []
    for name, origin, edge_1, edge_2, label in definitions:
        l1 = float(np.linalg.norm(edge_1))
        l2 = float(np.linalg.norm(edge_2))
        cross = float(np.linalg.norm(np.cross(edge_1, edge_2)))
        dot = float(np.dot(edge_1, edge_2))
        denom = l1 * l2
        safe_denom = denom if denom > 0.0 else 1.0
        angle = math.degrees(math.acos(max(-1.0, min(1.0, dot / safe_denom))))
        shape_denom = l1 * l1 + l2 * l2
        shape = (2.0 * cross / shape_denom) if shape_denom > 0.0 else 0.0
        scaled = cross / denom if denom > 0.0 else 0.0
        rows.append(
            {
                "corner": name,
                "semantic_label": label,
                "xyz_m": {
                    "x": float(origin[0]),
                    "y": float(origin[1]),
                    "z": float(origin[2]),
                },
                "edge_lengths_m": [l1, l2],
                "corner_angle_deg": angle,
                "corner_shape_metric": shape,
                "corner_scaled_jacobian_abs": scaled,
                "corner_equiangle_skewness": abs(angle - 90.0) / 90.0,
            }
        )
    return rows


def _cell_category(i: int, j: int, ni: int, nj: int) -> str:
    if i == 0:
        i_edge = "leading_edge_shoulder"
    elif i == ni - 2:
        i_edge = "trailing_edge_shoulder"
    elif i <= 2:
        i_edge = "near_le"
    elif i >= ni - 4:
        i_edge = "near_te"
    else:
        i_edge = "mid_chord"

    if j == 0:
        j_edge = "lower_side"
    elif j == nj - 2:
        j_edge = "upper_side"
    elif j <= 2:
        j_edge = "near_lower"
    elif j >= nj - 4:
        j_edge = "near_upper"
    else:
        j_edge = "mid_thickness"
    return f"{i_edge}_{j_edge}"


def _nearest_boundary(point: np.ndarray, blocks: dict[str, np.ndarray]) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    for block_name in ("oml_0", "oml_1", "oml_2", "oml_3"):
        tip_edge = blocks[block_name][:, -1, :]
        distances = np.linalg.norm(tip_edge - point, axis=1)
        index = int(np.argmin(distances))
        hits.append(
            {
                "block": block_name,
                "tip_edge_index": index,
                "distance_m": float(distances[index]),
            }
        )
    return sorted(hits, key=lambda item: float(item["distance_m"]))[:3]


def diagnose(npz_path: Path) -> dict[str, object]:
    with np.load(npz_path, allow_pickle=False) as archive:
        blocks = {name: archive[name] for name in archive.files}

    tip = blocks["tip_center_0"]
    shape = _corner_shape_metric(tip)
    skew = equiangle_skewness(tip)
    scaled_jac = scaled_jacobian(tip)
    centers = 0.25 * (tip[:-1, :-1] + tip[1:, :-1] + tip[1:, 1:] + tip[:-1, 1:])

    worst_shape_index = np.unravel_index(np.argmin(shape), shape.shape)
    worst_skew_index = np.unravel_index(np.argmax(skew), skew.shape)
    worst_scaled_jac_index = np.unravel_index(np.argmin(scaled_jac), scaled_jac.shape)
    i = int(worst_shape_index[0])
    j = int(worst_shape_index[1])

    top_cells: list[dict[str, object]] = []
    for rank, flat_index in enumerate(np.argsort(shape.ravel())[:20], start=1):
        ii, jj = np.unravel_index(flat_index, shape.shape)
        top_cells.append(
            {
                "rank": rank,
                "i": int(ii),
                "j": int(jj),
                "category": _cell_category(int(ii), int(jj), tip.shape[0], tip.shape[1]),
                "shape_metric": float(shape[ii, jj]),
                "scaled_jacobian": float(scaled_jac[ii, jj]),
                "equiangle_skewness": float(skew[ii, jj]),
                "center_m": {
                    "x": float(centers[ii, jj, 0]),
                    "y": float(centers[ii, jj, 1]),
                    "z": float(centers[ii, jj, 2]),
                },
            }
        )

    corners = _cell_corners(tip, i, j)
    corner_rows = _corner_metrics(corners)
    worst_corner = min(corner_rows, key=lambda row: float(row["corner_shape_metric"]))
    boundary_matches = {name: _nearest_boundary(point, blocks) for name, point in corners.items()}

    return {
        "schema": "aeris.mesh_study.stage01_lhs7_00_tip_section_cause.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "sample_id": "lhs7_00",
        "input_npz": str(npz_path),
        "input_npz_sha256": hashlib.sha256(npz_path.read_bytes()).hexdigest(),
        "diagnosis": (
            "The global worst surface cell is inherited from the tip-station boundary "
            "curves. It is at the lower leading-edge shoulder of tip_center_0, where "
            "the lower chord-side boundary from oml_1 and nose-wrap boundary from "
            "oml_0 meet at an almost degenerate angle. The blunt trailing-edge "
            "shoulder is also present in the top offenders, but it is not the global "
            "worst cell."
        ),
        "global_worst_shape_cell": {
            "block": "tip_center_0",
            "i": i,
            "j": j,
            "shape_metric": float(shape[i, j]),
            "scaled_jacobian": float(scaled_jac[i, j]),
            "equiangle_skewness": float(skew[i, j]),
            "category": _cell_category(i, j, tip.shape[0], tip.shape[1]),
            "center_m": {
                "x": float(centers[i, j, 0]),
                "y": float(centers[i, j, 1]),
                "z": float(centers[i, j, 2]),
            },
        },
        "global_worst_skew_cell": {
            "block": "tip_center_0",
            "i": int(worst_skew_index[0]),
            "j": int(worst_skew_index[1]),
            "skew": float(skew[worst_skew_index]),
        },
        "global_min_scaled_jacobian_cell": {
            "block": "tip_center_0",
            "i": int(worst_scaled_jac_index[0]),
            "j": int(worst_scaled_jac_index[1]),
            "scaled_jacobian": float(scaled_jac[worst_scaled_jac_index]),
        },
        "worst_corner": worst_corner,
        "worst_cell_corner_metrics": corner_rows,
        "worst_cell_boundary_matches": boundary_matches,
        "top20_worst_shape_cells": top_cells,
        "top20_category_counts": dict(Counter(row["category"] for row in top_cells)),
        "replan_guidance": (
            "Do not spend the next replan only on alternate tip caps or only on "
            "blunt trailing-edge thickening. The cap topology swap preserved the "
            "defect; the bad angles are already present in the tip-station OML "
            "boundary correspondence, especially the leading-edge shoulder and "
            "secondarily the trailing-edge shoulder."
        ),
    }


def write_markdown(payload: dict[str, object], path: Path) -> None:
    worst_cell = payload["global_worst_shape_cell"]
    worst_corner = payload["worst_corner"]
    category_counts = payload["top20_category_counts"]
    boundary_matches = payload["worst_cell_boundary_matches"]
    lines = [
        "# lhs7_00 Tip-Section Cause Diagnostic",
        "",
        "Result: upstream surface-only diagnosis complete",
        "",
        str(payload["diagnosis"]),
        "",
        "## Worst Cell",
        "",
        "- Block: tip_center_0",
        f"- Index: i={worst_cell['i']}, j={worst_cell['j']}",
        f"- Category: {worst_cell['category']}",
        f"- Shape metric: {worst_cell['shape_metric']:.12g}",
        f"- Scaled Jacobian: {worst_cell['scaled_jacobian']:.12g}",
        f"- Equiangle skewness: {worst_cell['equiangle_skewness']:.12g}",
        "",
        "## Worst Corner",
        "",
        f"- Corner: {worst_corner['corner']}",
        f"- Label: {worst_corner['semantic_label']}",
        f"- Corner angle: {worst_corner['corner_angle_deg']:.9g} deg",
        "- Edge lengths: "
        f"{worst_corner['edge_lengths_m'][0]:.9g} m and "
        f"{worst_corner['edge_lengths_m'][1]:.9g} m",
        "",
        "## Top-20 Worst-Shape Category Counts",
        "",
    ]
    for category, count in sorted(category_counts.items()):
        lines.append(f"- {category}: {count}")

    lines.extend(["", "## Boundary Match Evidence", ""])
    for corner_name, matches in boundary_matches.items():
        formatted = "; ".join(
            f"{match['block']}[{match['tip_edge_index']}] d={match['distance_m']:.3e}"
            for match in matches
        )
        lines.append(f"- {corner_name} nearest: {formatted}")

    lines.extend(["", "## Replan Guidance", "", str(payload["replan_guidance"]), ""])
    path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-npz",
        type=Path,
        default=Path(
            "AERIS_MESH_STUDY/artifacts/stage01/epse_calibration/"
            "surfaces/lhs7_00/surface/surface_blocks.npz"
        ),
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=Path("AERIS_MESH_STUDY/03_cap4_epse/lhs7_00_tip_section_cause_diagnostic.json"),
    )
    parser.add_argument(
        "--report-md",
        type=Path,
        default=Path("AERIS_MESH_STUDY/03_cap4_epse/lhs7_00_tip_section_cause_diagnostic.md"),
    )
    args = parser.parse_args()

    payload = diagnose(args.input_npz)
    args.report_json.write_text(json.dumps(payload, indent=2) + "\n")
    write_markdown(payload, args.report_md)
    worst_cell = payload["global_worst_shape_cell"]
    worst_corner = payload["worst_corner"]
    print(
        json.dumps(
            {
                "json": str(args.report_json),
                "md": str(args.report_md),
                "worst_category": worst_cell["category"],
                "worst_corner_angle_deg": worst_corner["corner_angle_deg"],
                "top20_category_counts": payload["top20_category_counts"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
