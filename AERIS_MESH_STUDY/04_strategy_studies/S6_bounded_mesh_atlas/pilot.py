#!/usr/bin/env python3
"""Development-set pilot for deforming proven S1 volumes to exact S6 walls."""

from __future__ import annotations

import argparse
import gc
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _path in (HERE, REPO_ROOT / "src", STUDIES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from deform import (  # noqa: E402
    acceptance_report,
    deform_volume_blocks,
    load_surface_blocks,
)
from shared.qc import write_surface_artifacts  # noqa: E402
from strategy_s6 import build_locked_surface  # noqa: E402

from aeris.cfd.meshing.volume_audit import read_volume_blocks  # noqa: E402

S1_ROOT = (
    REPO_ROOT
    / "AERIS_MESH_STUDY/artifacts/strategy_studies"
    / "S1_tip_first/L2_smoke/smoke"
)


def _default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def run_pilot(output: Path, indices: list[int]) -> dict[str, Any]:
    output = output.resolve()
    rows: list[dict[str, Any]] = []
    for index in indices:
        geometry_id = f"lhs100_seed42_{index:03d}"
        template_dir = S1_ROOT / geometry_id / "eps20"
        template_cgns = template_dir / "wing_vol.cgns"
        template_surface_path = template_dir / "surface_blocks.npz"
        if not template_cgns.is_file() or not template_surface_path.is_file():
            rows.append({"geometry_id": geometry_id, "state": "MISSING_S1_TEMPLATE"})
            continue

        template_surface = load_surface_blocks(template_surface_path)
        first_template_block = next(iter(template_surface.values()))
        span_cells = int(first_template_block.shape[1] - 1)
        blocks, surface_info, _case = build_locked_surface(
            "lhs100_seed42",
            index,
            output / "_geometry",
            level="smoke",
            span_cells=span_cells,
        )
        target_dir = output / "targets" / geometry_id
        artifacts = write_surface_artifacts(blocks, target_dir)
        (target_dir / "surface_report.json").write_text(
            json.dumps(surface_info, indent=2, sort_keys=True, default=_default) + "\n",
            encoding="utf-8",
        )

        volume = read_volume_blocks(template_cgns)
        target_surface = load_surface_blocks(Path(artifacts["surface_npz"]["path"]))
        deformed, metadata = deform_volume_blocks(
            volume, template_surface, target_surface
        )
        acceptance = acceptance_report(deformed, metadata)
        quality = acceptance["quality"]
        rows.append(
            {
                "geometry_id": geometry_id,
                "state": (
                    "PASS" if acceptance["production_floor_passed"] else "FAIL"
                ),
                "wall_error_m": metadata["max_wall_error_m"],
                "max_residual_displacement_m": metadata[
                    "max_residual_displacement_m"
                ],
                "inverted_cells": quality["inverted_cells"],
                "min_volume": quality["min_volume"],
                "min_scaled_quality": quality["min_scaled_quality"],
                "mean_scaled_quality": quality["mean_scaled_quality"],
                "production_floor": acceptance["production_floor"],
            }
        )
        del volume, template_surface, target_surface, deformed
        gc.collect()

    passes = sum(row["state"] == "PASS" for row in rows)
    qualities = [
        row["min_scaled_quality"] for row in rows if row["state"] == "PASS"
    ]
    report = {
        "schema": "aeris.mesh.s6_development_pilot.v1",
        "purpose": "S1 marched volume to exact S6 wall, same locked geometry",
        "indices": indices,
        "passed": passes,
        "attempted": len(indices),
        "pass_fraction": passes / len(indices) if indices else 0.0,
        "worst_min_scaled_quality": min(qualities) if qualities else None,
        "rows": rows,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "pilot_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=_default) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--indices", type=int, nargs="+", default=list(range(10)))
    args = parser.parse_args()
    report = run_pilot(args.output, args.indices)
    print(json.dumps(report, indent=2, default=_default))
    return 0 if report["passed"] == report["attempted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
