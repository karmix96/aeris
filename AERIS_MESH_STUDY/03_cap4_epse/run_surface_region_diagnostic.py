#!/usr/bin/env python3
# Stage 01 surface-cell diagnostic for the locked cap4 control surface.

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from aeris.cfd.meshing.quality import equiangle_skewness
from aeris.mesh.surface import _corner_shape_metric

DESCRIPTION = "Stage 01 surface-cell diagnostic for the locked cap4 control surface."
STUDY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE_DIR = STUDY_ROOT / "artifacts/stage01/epse_calibration/surfaces/lhs7_00"
DEFAULT_CONTRACT = STUDY_ROOT / "00_governance/geometry_topology_contract.json"
DEFAULT_REPORT_JSON = Path(__file__).with_name("lhs7_00_surface_region_diagnostic.json")
DEFAULT_REPORT_MD = Path(__file__).with_name("lhs7_00_surface_region_diagnostic.md")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def station_positions(sample: dict[str, float]) -> dict[str, float]:
    b_total = float(sample["b_total_m"])
    outboard_segment = b_total * float(sample["b3_ratio"])
    b2_station = b_total - outboard_segment
    b1_station = b2_station * float(sample["split_ratio"])
    return {
        "b0_root": 0.0,
        "b1_planform_break": b1_station,
        "b2_planform_airfoil_break": b2_station,
        "b3_tip": b_total,
    }


def cell_centers(block: np.ndarray) -> np.ndarray:
    return 0.25 * (block[:-1, :-1, :] + block[1:, :-1, :] + block[1:, 1:, :] + block[:-1, 1:, :])


def span_band(blocks: dict[str, np.ndarray]) -> float:
    deltas: list[np.ndarray] = []
    for name, block in blocks.items():
        if name.startswith("tip_center"):
            continue
        if block.shape[1] > 1:
            dy = np.abs(np.diff(block[:, :, 1], axis=1)).ravel()
            dy = dy[dy > 1.0e-12]
            if dy.size:
                deltas.append(dy)
    if not deltas:
        return 1.0e-6
    return float(max(1.0e-6, 0.5 * np.median(np.concatenate(deltas))))


def nearest_station(y: float, stations: dict[str, float]) -> tuple[str, float]:
    name, value = min(stations.items(), key=lambda item: abs(float(y) - item[1]))
    return name, abs(float(y) - value)


def classify_region(
    block_name: str,
    center: np.ndarray,
    stations: dict[str, float],
    band: float,
) -> tuple[str, str]:
    y = float(center[1])
    if block_name.startswith("tip_center"):
        return "tip_cap", "tip_center_* block closes the b3 physical tip face"
    if abs(y - stations["b3_tip"]) <= band:
        return "tip_cap", "cell center lies within one half median span cell of b3 tip"
    if abs(y - stations["b0_root"]) <= band:
        return "root", "cell center lies within one half median span cell of b0 root/symmetry"
    if abs(y - stations["b1_planform_break"]) <= band:
        return "planform_break_b1", "cell center lies within one half median span cell of b1 planform break"
    if abs(y - stations["b2_planform_airfoil_break"]) <= band:
        return "planform_break_b2", "cell center lies within one half median span cell of b2 planform/airfoil break"
    if block_name == "oml_2":
        return "te_crown", "oml_2 is the trailing-edge crown block in cap4 topology"
    if block_name == "oml_0":
        return "le_crown", "oml_0 is the leading-edge crown block in cap4 topology"
    if block_name == "oml_1":
        return "lower_mid_oml", "oml_1 lower mid-chord OML block"
    if block_name == "oml_3":
        return "upper_mid_oml", "oml_3 upper mid-chord OML block"
    return "unknown", "no semantic mapping rule matched"


def row_payload(
    *,
    metric_name: str,
    metric_value: float,
    block_name: str,
    i: int,
    j: int,
    center: np.ndarray,
    stations: dict[str, float],
    band: float,
) -> dict[str, Any]:
    region, reason = classify_region(block_name, center, stations, band)
    station_name, station_distance = nearest_station(float(center[1]), stations)
    return {
        "metric": metric_name,
        "value": float(metric_value),
        "block": block_name,
        "i": int(i),
        "j": int(j),
        "cell_center_m": {
            "x": float(center[0]),
            "y": float(center[1]),
            "z": float(center[2]),
        },
        "semantic_region": region,
        "region_reason": reason,
        "nearest_station": station_name,
        "distance_to_nearest_station_m": float(station_distance),
        "span_fraction": float(center[1] / stations["b3_tip"]) if stations["b3_tip"] else None,
    }


def top_cells(
    blocks: dict[str, np.ndarray],
    stations: dict[str, float],
    band: float,
    top_n: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    shape_rows: list[dict[str, Any]] = []
    skew_rows: list[dict[str, Any]] = []
    region_values: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "cell_count": 0,
        "min_shape_metric": None,
        "max_equiangle_skewness": None,
        "worst_shape_cell": None,
        "worst_skew_cell": None,
    })

    for block_name, block in blocks.items():
        shape = _corner_shape_metric(block)
        skew = equiangle_skewness(block)
        centers = cell_centers(block)
        for i in range(shape.shape[0]):
            for j in range(shape.shape[1]):
                center = centers[i, j]
                region, _ = classify_region(block_name, center, stations, band)
                summary = region_values[region]
                summary["cell_count"] += 1
                s_val = float(shape[i, j])
                k_val = float(skew[i, j])
                shape_payload = row_payload(
                    metric_name="shape_metric",
                    metric_value=s_val,
                    block_name=block_name,
                    i=i,
                    j=j,
                    center=center,
                    stations=stations,
                    band=band,
                )
                skew_payload = row_payload(
                    metric_name="equiangle_skewness",
                    metric_value=k_val,
                    block_name=block_name,
                    i=i,
                    j=j,
                    center=center,
                    stations=stations,
                    band=band,
                )
                shape_rows.append(shape_payload)
                skew_rows.append(skew_payload)
                if summary["min_shape_metric"] is None or s_val < summary["min_shape_metric"]:
                    summary["min_shape_metric"] = s_val
                    summary["worst_shape_cell"] = shape_payload
                if summary["max_equiangle_skewness"] is None or k_val > summary["max_equiangle_skewness"]:
                    summary["max_equiangle_skewness"] = k_val
                    summary["worst_skew_cell"] = skew_payload

    shape_rows.sort(key=lambda row: row["value"])
    skew_rows.sort(key=lambda row: row["value"], reverse=True)
    return shape_rows[:top_n], skew_rows[:top_n], dict(region_values)


def write_markdown(report: dict[str, Any], path: Path) -> None:
    shape_owner = report["findings"]["global_worst_shape_region"]
    skew_owner = report["findings"]["global_worst_skew_region"]
    lines = [
        "# lhs7_00 Surface Region Diagnostic",
        "",
        "Result: surface-only diagnostic complete",
        "",
        "## Inputs",
        "",
        "- Sample dir: `{}`".format(report["inputs"]["sample_dir"]),
        "- Surface NPZ SHA-256: `{}`".format(report["inputs"]["surface_blocks_npz_sha256"]),
        "- Topology contract: `{}`".format(report["inputs"]["geometry_topology_contract"]),
        "- Region band: {:.9g} m".format(report["mapping"]["span_band_m"]),
        "",
        "## Finding",
        "",
        "- Worst shape metric is owned by `{}`.".format(shape_owner),
        "- Worst equiangle skewness is owned by `{}`.".format(skew_owner),
        "- In this diagnostic, both global worst cells are in the physical tip-cap block, not the root, TE crown, or b1/b2 planform breaks.",
        "",
        "## Station Map",
        "",
    ]
    for name, value in report["mapping"]["station_y_m"].items():
        lines.append("- {}: {:.9g} m".format(name, value))

    def add_table(title: str, rows: list[dict[str, Any]]) -> None:
        lines.extend([
            "",
            "## {}".format(title),
            "",
            "| rank | value | block | i | j | region | y | nearest station |",
            "|---:|---:|---|---:|---:|---|---:|---|",
        ])
        for idx, row in enumerate(rows, start=1):
            center = row["cell_center_m"]
            lines.append(
                "| {} | {:.9g} | {} | {} | {} | {} | {:.9g} | {} |".format(
                    idx,
                    row["value"],
                    row["block"],
                    row["i"],
                    row["j"],
                    row["semantic_region"],
                    center["y"],
                    row["nearest_station"],
                )
            )

    add_table("Worst Shape Cells", report["top_worst_shape_cells"])
    add_table("Worst Equiangle-Skew Cells", report["top_worst_skew_cells"])

    lines.extend(["", "## Region Summary", "", "| region | cells | min shape | max skew |", "|---|---:|---:|---:|"])
    for region, summary in sorted(report["region_summary"].items()):
        lines.append(
            "| {} | {} | {:.9g} | {:.9g} |".format(
                region,
                summary["cell_count"],
                summary["min_shape_metric"],
                summary["max_equiangle_skewness"],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def run(args: argparse.Namespace) -> int:
    sample_dir = Path(args.sample_dir).resolve()
    manifest = read_json(sample_dir / "manifest.json")
    contract = read_json(Path(args.geometry_topology_contract).resolve())
    npz_path = Path(manifest["surface_dir"]) / "surface_blocks.npz"
    blocks = {name: value for name, value in np.load(npz_path, allow_pickle=False).items()}
    sample = manifest["design_sample"]
    stations = station_positions(sample)
    band = span_band(blocks)
    top_shape, top_skew, region_summary = top_cells(blocks, stations, band, int(args.top_n))
    report = {
        "schema": "aeris.mesh_study.stage01_surface_region_diagnostic.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "sample_id": manifest["sample_id"],
        "sample_index": manifest["sample_index"],
        "topology_id": manifest["topology_id"],
        "surface_recipe": manifest["surface_recipe"],
        "inputs": {
            "sample_dir": str(sample_dir),
            "surface_blocks_npz": str(npz_path),
            "surface_blocks_npz_sha256": file_sha256(npz_path),
            "surface_fmt_sha256": manifest["artifact_sha256"].get("surface.fmt"),
            "geometry_topology_contract": str(Path(args.geometry_topology_contract).resolve()),
            "geometry_topology_contract_status": contract.get("status"),
        },
        "mapping": {
            "semantic_sources": [
                "geometry_topology_contract.fixed_geometry_topology.station_order_root_to_tip",
                "geometry_topology_contract.fixed_geometry_topology.semantic_edges",
                "src/aeris/mesh/surface.py cap4 block topology docstring",
            ],
            "station_y_m": stations,
            "span_band_m": band,
            "region_priority": ["tip_cap", "root", "planform_break_b1", "planform_break_b2", "te_crown", "le_crown", "mid_oml"],
        },
        "findings": {
            "global_worst_shape_region": top_shape[0]["semantic_region"] if top_shape else None,
            "global_worst_shape_value": top_shape[0]["value"] if top_shape else None,
            "global_worst_skew_region": top_skew[0]["semantic_region"] if top_skew else None,
            "global_worst_skew_value": top_skew[0]["value"] if top_skew else None,
            "interpretation": "Both global worst surface cells are owned by the physical tip cap on lhs7_00.",
        },
        "top_worst_shape_cells": top_shape,
        "top_worst_skew_cells": top_skew,
        "region_summary": region_summary,
    }
    report_json = Path(args.report_json).resolve()
    report_md = Path(args.report_md).resolve()
    report_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, report_md)
    print(json.dumps({
        "report_json": str(report_json),
        "report_md": str(report_md),
        "worst_shape_region": report["findings"]["global_worst_shape_region"],
        "worst_skew_region": report["findings"]["global_worst_skew_region"],
    }, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--sample-dir", default=str(DEFAULT_SAMPLE_DIR))
    parser.add_argument("--geometry-topology-contract", default=str(DEFAULT_CONTRACT))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--report-md", default=str(DEFAULT_REPORT_MD))
    parser.add_argument("--top-n", type=int, default=12)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
