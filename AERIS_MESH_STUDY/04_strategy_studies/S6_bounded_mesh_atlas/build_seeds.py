#!/usr/bin/env python3
"""Build and audit the maximin S1 seed volumes used by the S6 atlas."""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _path in (HERE, REPO_ROOT / "src", STUDIES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from atlas import farthest_point_indices, normalize_matrix  # noqa: E402
from campaign import _run_with_timeout, indices_from_atlas_manifest  # noqa: E402
from deform import WALL_TOLERANCE_M, sha256, volume_interface_report  # noqa: E402
from resolution import epsilon_tag, first_cell_fraction  # noqa: E402
from S1_tip_first import strategy_s1  # noqa: E402
from shared.gates import EPSE_LADDER  # noqa: E402
from shared.geometry_sets import design_matrix, geometry_id, wing  # noqa: E402
from shared.pyhyp_runner import prepare, read_result  # noqa: E402
from shared.volume_qc import volume_report  # noqa: E402

from aeris.cfd.meshing.pyhyp_extrude import mach_aero_python  # noqa: E402
from aeris.cfd.meshing.pyhyp_options import GRID_LEVELS  # noqa: E402
from aeris.cfd.meshing.volume_audit import read_volume_blocks  # noqa: E402

SCHEMA = "aeris.mesh.s6_seed_build.v1"
PRODUCTION_FLOOR = 0.10
ALLOWED_LEVELS = ("smoke", "fine", "production")


def _default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def _write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=_default) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def selected_indices(template_count: int) -> list[int]:
    matrix, names = design_matrix("lhs100_seed42")
    return farthest_point_indices(normalize_matrix(matrix, names), template_count)


def _audit_run(run_dir: Path) -> dict[str, Any]:
    try:
        result = read_result(run_dir) or {}
    except Exception as error:
        return {
            "state": "FAIL",
            "failure_reasons": ["invalid_march_result"],
            "error_type": type(error).__name__,
            "error": str(error),
        }
    cgns = run_dir / "wing_vol.cgns"
    surface = run_dir / "surface_blocks.npz"
    if not cgns.is_file() or not surface.is_file():
        return {
            "state": "FAIL",
            "failure_reasons": ["missing_volume_or_surface"],
            "march_result": result,
        }

    try:
        volume = read_volume_blocks(cgns)
        quality = volume_report(volume)
        interfaces = volume_interface_report(volume)
    except Exception as error:
        return {
            "state": "FAIL",
            "failure_reasons": ["volume_audit_error"],
            "error_type": type(error).__name__,
            "error": str(error),
            "march_result": result,
        }
    reasons: list[str] = []
    if not result.get("march_completed", False):
        reasons.append("march_not_completed")
    if quality.get("inverted_cells") != 0:
        reasons.append("inverted_cells")
    if float(quality.get("min_volume", -1.0)) <= 0.0:
        reasons.append("nonpositive_volume")
    if float(quality.get("min_scaled_quality", -1.0)) < PRODUCTION_FLOOR:
        reasons.append("quality_below_production_floor")
    if interfaces["paired_face_count"] != 20:
        reasons.append("unexpected_interface_count")
    if interfaces["max_mismatch_m"] > WALL_TOLERANCE_M:
        reasons.append("nonconformal_interfaces")
    report = {
        "state": "PASS" if not reasons else "FAIL",
        "failure_reasons": reasons,
        "march_result": result,
        "cgns": str(cgns.resolve()),
        "cgns_sha256": sha256(cgns),
        "surface_npz": str(surface.resolve()),
        "surface_npz_sha256": sha256(surface),
        "quality": quality,
        "interfaces": interfaces,
    }
    del volume
    gc.collect()
    return report


def build(
    *,
    output: Path,
    level: str,
    indices: list[int],
    timeout_s: float,
    report_stem: str = "seed_build",
    eps_e: float = 2.0,
    first_cell_fraction_override: float | None = None,
) -> dict[str, Any]:
    if level not in ALLOWED_LEVELS:
        raise ValueError(f"unsupported seed level {level!r}")
    eps_tag = epsilon_tag(eps_e)
    policy_fraction = first_cell_fraction(level)
    selected_fraction = (
        policy_fraction
        if first_cell_fraction_override is None
        else float(first_cell_fraction_override)
    )
    if not np.isfinite(selected_fraction) or selected_fraction <= 0.0:
        raise ValueError("first-cell fraction must be finite and positive")
    if not indices or len(indices) != len(set(indices)):
        raise ValueError("seed indices must be non-empty and unique")
    if (
        not report_stem
        or Path(report_stem).name != report_stem
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
            for character in report_stem
        )
    ):
        raise ValueError("report stem must be a simple file-name component")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output / f"{report_stem}_checkpoint.json"
    rows: list[dict[str, Any]] = []
    started = time.monotonic()

    for sequence, index in enumerate(indices, start=1):
        gid = geometry_id("lhs100_seed42", index)
        run_dir = output / gid / eps_tag
        case_started = time.monotonic()
        existing = _audit_run(run_dir) if run_dir.is_dir() else {"state": "MISSING"}
        returncode: int | None = None
        resumed = existing.get("state") == "PASS"
        if resumed:
            audit = existing
        else:
            try:
                geometry = wing("lhs100_seed42", index)
                blocks, _surface_info = strategy_s1.build_surface(geometry, level="L2_smoke")
                prepared = prepare(
                    strategy_id=strategy_s1.STRATEGY_ID,
                    geometry_id=gid,
                    blocks=blocks,
                    out_dir=output,
                    level=level,
                    epse_ladder=(eps_e,),
                    s0_fraction_override=selected_fraction,
                )
                run_dir = Path(prepared["runs"][0]["dir"]).resolve()
                runner = Path(prepared["runs"][0]["runner"]).resolve()
                returncode = _run_with_timeout(
                    [str(mach_aero_python()), str(runner)],
                    run_dir,
                    run_dir / "run_stdout.log",
                    timeout_s,
                )
                audit = _audit_run(run_dir)
            except Exception as error:
                audit = {
                    "state": "FAIL",
                    "failure_reasons": ["seed_build_error"],
                    "error_type": type(error).__name__,
                    "error": str(error),
                }

        row = {
            "sequence": sequence,
            "geometry_index": index,
            "geometry_id": gid,
            "level": level,
            "eps_e": eps_e,
            "normal_points": int(GRID_LEVELS[level]["N"]),
            "first_cell_fraction_characteristic": selected_fraction,
            "state": audit["state"],
            "resumed": resumed,
            "return_code": returncode,
            "elapsed_s": time.monotonic() - case_started,
            "audit": audit,
        }
        rows.append(row)
        _write_json(
            checkpoint_path,
            {
                "schema": SCHEMA,
                "level": level,
                "eps_e": eps_e,
                "first_cell_fraction_characteristic": selected_fraction,
                "indices": indices,
                "rows": rows,
            },
        )
        print(
            f"{sequence:03d}/{len(indices):03d} {gid} {row['state']} resumed={resumed}",
            flush=True,
        )

    passed = sum(row["state"] == "PASS" for row in rows)
    report = {
        "schema": SCHEMA,
        "level": level,
        "eps_e": eps_e,
        "normal_points": int(GRID_LEVELS[level]["N"]),
        "first_cell_fraction_characteristic": selected_fraction,
        "wall_spacing_source": (
            "policy" if first_cell_fraction_override is None else "explicit_calibration"
        ),
        "indices": indices,
        "attempted": len(rows),
        "passed": passed,
        "pass_fraction": passed / len(rows),
        "elapsed_s": time.monotonic() - started,
        "rows": rows,
    }
    _write_json(output / f"{report_stem}_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--level", choices=ALLOWED_LEVELS, required=True)
    parser.add_argument("--template-count", type=int, default=16)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--indices", type=int, nargs="+")
    selection.add_argument("--atlas-manifest", type=Path)
    parser.add_argument("--timeout-s", type=float, default=3600.0)
    parser.add_argument("--eps-e", type=float, choices=EPSE_LADDER, default=2.0)
    parser.add_argument("--first-cell-fraction", type=float)
    parser.add_argument("--report-stem", default="seed_build")
    args = parser.parse_args()
    indices = (
        indices_from_atlas_manifest(args.atlas_manifest)
        if args.atlas_manifest
        else args.indices or selected_indices(args.template_count)
    )
    report = build(
        output=args.output,
        level=args.level,
        indices=indices,
        timeout_s=args.timeout_s,
        report_stem=args.report_stem,
        eps_e=args.eps_e,
        first_cell_fraction_override=args.first_cell_fraction,
    )
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "level",
                    "eps_e",
                    "first_cell_fraction_characteristic",
                    "indices",
                    "attempted",
                    "passed",
                    "elapsed_s",
                )
            },
            indent=2,
        )
    )
    return 0 if report["passed"] == report["attempted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
