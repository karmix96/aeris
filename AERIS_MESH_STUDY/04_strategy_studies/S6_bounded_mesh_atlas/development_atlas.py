#!/usr/bin/env python3
"""Validate nearest-template S6 deformation on the 100-case development set."""

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

from atlas import ATLAS_SCHEMA, normalize_matrix, rms_distance  # noqa: E402
from deform import (  # noqa: E402
    acceptance_report,
    deform_volume_blocks,
    load_surface_blocks,
    sha256,
    write_volume_blocks,
    written_deformation_metadata,
)
from resolution import epsilon_tag  # noqa: E402
from shared.gates import EPSE_LADDER  # noqa: E402
from shared.geometry_sets import design_matrix, geometry_id  # noqa: E402
from shared.qc import write_surface_artifacts  # noqa: E402
from strategy_s6 import build_pygeo_case, build_surface  # noqa: E402

from aeris.cfd.meshing.pyhyp_options import GRID_LEVELS  # noqa: E402
from aeris.cfd.meshing.volume_audit import read_volume_blocks  # noqa: E402

S1_ROOT = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/strategy_studies" / "S1_tip_first/L2_smoke/smoke"


def _default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
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


CHECKPOINT_SCHEMA = "aeris.mesh.s6_atlas_checkpoint.v2"
REPORT_SCHEMA = "aeris.mesh.s6_atlas_development_validation.v2"


def _template_paths(index: int, template_root: Path, eps_e: float = 2.0) -> tuple[Path, Path]:
    directory = Path(template_root) / f"lhs100_seed42_{index:03d}" / epsilon_tag(eps_e)
    return directory / "wing_vol.cgns", directory / "surface_blocks.npz"


def _template_configuration(
    template_indices: list[int], template_root: Path, eps_e: float
) -> dict[str, Any]:
    fingerprints = []
    normal_points: set[int] = set()
    first_cell_fractions: list[float] = []
    for index in template_indices:
        cgns, surface = _template_paths(index, template_root, eps_e)
        options = cgns.parent / "pyhyp_options.json"
        prepare = cgns.parent.parent / "prepare_manifest.json"
        if not all(path.is_file() for path in (cgns, surface, options, prepare)):
            raise FileNotFoundError(f"template {index} is incomplete")
        native_options = json.loads(options.read_text(encoding="utf-8"))
        prepare_manifest = json.loads(prepare.read_text(encoding="utf-8"))
        normal_points.add(int(native_options["N"]))
        characteristic_length = float(prepare_manifest["characteristic_length"])
        first_cell_fractions.append(float(native_options["s0"]) / characteristic_length)
        fingerprints.append(
            {
                "geometry_index": index,
                "cgns_sha256": sha256(cgns),
                "surface_npz_sha256": sha256(surface),
                "pyhyp_options_sha256": sha256(options),
            }
        )
    if len(normal_points) != 1:
        raise ValueError("development atlas mixes normal resolutions")
    if not np.allclose(
        first_cell_fractions,
        first_cell_fractions[0],
        rtol=1.0e-12,
        atol=0.0,
    ):
        raise ValueError("development atlas mixes first-cell-height laws")
    points = next(iter(normal_points))
    matches = [
        level for level in ("smoke", "fine", "production") if int(GRID_LEVELS[level]["N"]) == points
    ]
    if len(matches) != 1:
        raise ValueError(f"unsupported S6 normal resolution N={points}")
    return {
        "volume_level": matches[0],
        "normal_points": points,
        "first_cell_fraction_characteristic": first_cell_fractions[0],
        "eps_e": eps_e,
        "template_fingerprints": fingerprints,
    }


def validate(
    *,
    output: Path,
    template_indices: list[int],
    candidate_count: int = 0,
    geometry_indices: list[int] | None = None,
    template_root: Path = S1_ROOT,
    resume: bool = True,
    preferred_quality: float = 0.15,
    eps_e: float = 2.0,
    retain_written_meshes: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    if not template_indices or len(template_indices) != len(set(template_indices)):
        raise ValueError("template indices must be non-empty and unique")
    matrix, names = design_matrix("lhs100_seed42")
    normalized = normalize_matrix(matrix, names)
    template_configuration = _template_configuration(template_indices, Path(template_root), eps_e)
    if candidate_count < 0:
        raise ValueError("candidate count cannot be negative")
    candidate_count = (
        len(template_indices)
        if candidate_count == 0
        else min(candidate_count, len(template_indices))
    )
    if preferred_quality < 0.10:
        raise ValueError("preferred quality must be at least the production floor")
    distances = np.stack(
        [rms_distance(normalized, normalized[index]) for index in template_indices],
        axis=1,
    )
    if geometry_indices is None:
        geometry_indices = list(range(len(normalized)))
    if any(index < 0 or index >= len(normalized) for index in geometry_indices):
        raise ValueError("geometry indices must address the development set")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output / "atlas_validation_checkpoint.json"
    configuration = {
        "template_root": str(Path(template_root).resolve()),
        "template_indices": template_indices,
        "candidate_count": candidate_count,
        "preferred_quality": preferred_quality,
        "eps_e": eps_e,
        "retain_written_meshes": retain_written_meshes,
        "geometry_indices": geometry_indices,
        "template_configuration": template_configuration,
    }
    rows: list[dict[str, Any]] = []
    if resume and checkpoint_path.is_file():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint.get("configuration") != configuration:
            raise ValueError("existing checkpoint does not match this validation configuration")
        rows = list(checkpoint.get("rows", []))
    completed_indices = {int(row["geometry_index"]) for row in rows}

    for sequence, index in enumerate(geometry_indices, start=1):
        gid = geometry_id("lhs100_seed42", index)
        if index in completed_indices:
            print(
                f"{sequence:03d}/{len(geometry_indices):03d} {gid} RESUMED",
                flush=True,
            )
            continue
        ordered_slots = np.argsort(distances[index])[:candidate_count]
        attempts: list[dict[str, Any]] = []
        accepted_row: dict[str, Any] | None = None
        try:
            geometry_case = build_pygeo_case(
                "lhs100_seed42",
                index,
                output / "_geometry" / gid,
            )
            if geometry_case.pygeo_result is None:
                raise RuntimeError("canonical geometry did not produce pyGeo")
        except Exception as error:
            row = {
                "geometry_index": index,
                "geometry_id": gid,
                "state": "NEEDS_FALLBACK",
                "attempts": [
                    {
                        "state": "GEOMETRY_BUILD_ERROR",
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
                ],
                "accepted_template_index": None,
                "accepted_min_scaled_quality": None,
                "accepted_cgns": None,
                "accepted_cgns_sha256": None,
                "accepted_cgns_retained": False,
                "is_atlas_template_target": index in template_indices,
                "selected_identity_deformation": False,
            }
            rows.append(row)
            _write_json(
                checkpoint_path,
                {
                    "schema": CHECKPOINT_SCHEMA,
                    "configuration": configuration,
                    "rows": rows,
                },
            )
            print(
                f"{sequence:03d}/{len(geometry_indices):03d} {gid} NEEDS_FALLBACK template=None",
                flush=True,
            )
            continue
        for slot in ordered_slots:
            attempt_started = time.monotonic()
            template_index = template_indices[int(slot)]
            template_cgns, template_surface_path = _template_paths(
                template_index, template_root, eps_e
            )
            if not template_cgns.is_file() or not template_surface_path.is_file():
                attempts.append(
                    {
                        "template_index": template_index,
                        "state": "MISSING_TEMPLATE",
                        "elapsed_s": time.monotonic() - attempt_started,
                    }
                )
                continue

            template_surface = load_surface_blocks(template_surface_path)
            span_cells = int(next(iter(template_surface.values())).shape[1] - 1)
            try:
                blocks, surface_info = build_surface(
                    geometry_case.pygeo_result,
                    level="smoke",
                    span_cells=span_cells,
                )
            except Exception as error:
                attempts.append(
                    {
                        "template_index": template_index,
                        "distance_rms": float(distances[index, int(slot)]),
                        "state": "SURFACE_BUILD_ERROR",
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "elapsed_s": time.monotonic() - attempt_started,
                    }
                )
                continue
            surface_qc = surface_info["surface_qc"]
            fidelity = surface_info["fidelity"]
            if not surface_qc["accepted_pre_pyhyp"] or not fidelity["passed"]:
                attempts.append(
                    {
                        "template_index": template_index,
                        "distance_rms": float(distances[index, int(slot)]),
                        "state": "FAIL_SURFACE_GATE",
                        "surface_failure_reasons": surface_qc["failure_reasons"],
                        "surface_fidelity": fidelity,
                        "elapsed_s": time.monotonic() - attempt_started,
                    }
                )
                continue
            target_dir = output / "targets" / gid / f"from_{template_index:03d}"
            artifacts = write_surface_artifacts(blocks, target_dir)
            target_surface = load_surface_blocks(Path(artifacts["surface_npz"]["path"]))
            try:
                volume = read_volume_blocks(template_cgns)
                deformed, metadata = deform_volume_blocks(volume, template_surface, target_surface)
                acceptance = acceptance_report(deformed, metadata)
            except Exception as error:
                attempts.append(
                    {
                        "template_index": template_index,
                        "distance_rms": float(distances[index, int(slot)]),
                        "state": "DEFORMATION_ERROR",
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "elapsed_s": time.monotonic() - attempt_started,
                    }
                )
                volume = deformed = metadata = acceptance = None
                gc.collect()
                continue
            quality = acceptance["quality"]
            attempt = {
                "template_index": template_index,
                "distance_rms": float(distances[index, int(slot)]),
                "state": "FAIL",
                "surface_min_scaled_jacobian": surface_info["surface_qc"]["global"][
                    "min_scaled_jacobian"
                ],
                "surface_fidelity": fidelity,
                "wall_error_m": metadata["max_wall_error_m"],
                "inverted_cells": quality["inverted_cells"],
                "min_volume": quality["min_volume"],
                "min_scaled_quality": quality["min_scaled_quality"],
                "interface_pair_count": metadata["deformed_interfaces"]["paired_face_count"],
                "interface_max_mismatch_m": metadata["deformed_interfaces"]["max_mismatch_m"],
                "in_memory_acceptance": acceptance,
            }
            if not acceptance["production_floor_passed"]:
                attempt["elapsed_s"] = time.monotonic() - attempt_started
                attempts.append(attempt)
                volume = template_surface = target_surface = deformed = None
                gc.collect()
                continue

            candidate = target_dir / "wing_vol.cgns"
            try:
                write_volume_blocks(template_cgns, candidate, deformed)
                written = read_volume_blocks(candidate)
                written_metadata = written_deformation_metadata(written, target_surface, metadata)
                independent = acceptance_report(written, written_metadata)
            except Exception as error:
                candidate.unlink(missing_ok=True)
                attempt.update(
                    {
                        "state": "FAIL_WRITTEN_AUDIT",
                        "written_audit_error_type": type(error).__name__,
                        "written_audit_error": str(error),
                        "elapsed_s": time.monotonic() - attempt_started,
                    }
                )
                attempts.append(attempt)
                volume = template_surface = target_surface = deformed = None
                gc.collect()
                continue

            written_quality = independent["quality"]
            attempt.update(
                {
                    "state": (
                        "PASS" if independent["production_floor_passed"] else "FAIL_WRITTEN_AUDIT"
                    ),
                    "wall_error_m": written_metadata["max_wall_error_m"],
                    "inverted_cells": written_quality["inverted_cells"],
                    "min_volume": written_quality["min_volume"],
                    "min_scaled_quality": written_quality["min_scaled_quality"],
                    "interface_pair_count": written_metadata["deformed_interfaces"][
                        "paired_face_count"
                    ],
                    "interface_max_mismatch_m": written_metadata["deformed_interfaces"][
                        "max_mismatch_m"
                    ],
                    "first_layer_spacing": written_metadata["first_layer_spacing"],
                    "independent_written_acceptance": independent,
                    "candidate_cgns": str(candidate.resolve()),
                    "candidate_cgns_sha256": sha256(candidate),
                    "elapsed_s": time.monotonic() - attempt_started,
                }
            )
            attempts.append(attempt)
            if attempt["state"] != "PASS":
                candidate.unlink(missing_ok=True)
            elif (
                accepted_row is None
                or attempt["min_scaled_quality"] > accepted_row["min_scaled_quality"]
            ):
                if accepted_row is not None:
                    Path(accepted_row["candidate_cgns"]).unlink(missing_ok=True)
                accepted_row = attempt
            else:
                candidate.unlink(missing_ok=True)
            volume = template_surface = target_surface = deformed = written = None
            gc.collect()
            if accepted_row is not None and accepted_row["min_scaled_quality"] >= preferred_quality:
                break

        for attempt in attempts:
            attempt["selected"] = attempt is accepted_row

        row = {
            "geometry_index": index,
            "geometry_id": gid,
            "state": "PASS" if accepted_row is not None else "NEEDS_FALLBACK",
            "attempts": attempts,
            "accepted_template_index": (accepted_row["template_index"] if accepted_row else None),
            "accepted_min_scaled_quality": (
                accepted_row["min_scaled_quality"] if accepted_row else None
            ),
            "accepted_cgns": (accepted_row["candidate_cgns"] if accepted_row else None),
            "accepted_cgns_sha256": (
                accepted_row["candidate_cgns_sha256"] if accepted_row else None
            ),
            "accepted_cgns_retained": bool(accepted_row and retain_written_meshes),
            "is_atlas_template_target": index in template_indices,
            "selected_identity_deformation": bool(
                accepted_row and accepted_row["template_index"] == index
            ),
        }
        rows.append(row)
        _write_json(
            checkpoint_path,
            {
                "schema": CHECKPOINT_SCHEMA,
                "configuration": configuration,
                "rows": rows,
            },
        )
        if accepted_row is not None and not retain_written_meshes:
            Path(accepted_row["candidate_cgns"]).unlink(missing_ok=True)
        print(
            f"{sequence:03d}/{len(geometry_indices):03d} {gid} {row['state']} "
            f"template={row['accepted_template_index']}",
            flush=True,
        )

    passed = sum(row["state"] == "PASS" for row in rows)
    qualities = [row["accepted_min_scaled_quality"] for row in rows if row["state"] == "PASS"]
    identity_rows = [row for row in rows if row["is_atlas_template_target"]]
    nonidentity_rows = [row for row in rows if not row["is_atlas_template_target"]]

    def subset_summary(subset: list[dict[str, Any]]) -> dict[str, Any]:
        subset_passed = sum(row["state"] == "PASS" for row in subset)
        return {
            "attempted": len(subset),
            "passed": subset_passed,
            "pass_fraction": subset_passed / len(subset) if subset else None,
        }

    report = {
        "schema": REPORT_SCHEMA,
        "set_name": "lhs100_seed42",
        "geometry_indices": geometry_indices,
        "template_indices": template_indices,
        "candidate_count": candidate_count,
        "preferred_quality": preferred_quality,
        "template_root": str(Path(template_root).resolve()),
        "eps_e": eps_e,
        "campaign_equivalent_written_cgns_audit": True,
        "accepted_meshes_retained": retain_written_meshes,
        **template_configuration,
        "attempted": len(rows),
        "passed": passed,
        "pass_fraction": passed / len(rows),
        "worst_min_scaled_quality": min(qualities) if qualities else None,
        "identity_target_summary": subset_summary(identity_rows),
        "nonidentity_target_summary": subset_summary(nonidentity_rows),
        "elapsed_s": time.monotonic() - started,
        "rows": rows,
    }
    _write_json(output / "atlas_validation_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--template-indices", type=int, nargs="+")
    selection.add_argument("--atlas-manifest", type=Path)
    parser.add_argument(
        "--candidate-count",
        type=int,
        default=0,
        help="maximum templates per target; zero tries the complete atlas",
    )
    parser.add_argument("--preferred-quality", type=float, default=0.15)
    parser.add_argument("--indices", type=int, nargs="+")
    parser.add_argument("--template-root", type=Path, default=S1_ROOT)
    parser.add_argument("--eps-e", type=float, choices=EPSE_LADDER, default=2.0)
    parser.add_argument("--retain-written-meshes", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()
    if args.atlas_manifest is not None:
        atlas_manifest = json.loads(args.atlas_manifest.read_text(encoding="utf-8"))
        if atlas_manifest.get("schema") != ATLAS_SCHEMA:
            raise ValueError("not a current S6 atlas manifest")
        if atlas_manifest.get("set_name") != "lhs100_seed42":
            raise ValueError("atlas manifest uses the wrong development set")
        template_indices = [int(index) for index in atlas_manifest["template_indices"]]
    else:
        template_indices = args.template_indices
    report = validate(
        output=args.output,
        template_indices=template_indices,
        candidate_count=args.candidate_count,
        geometry_indices=args.indices,
        template_root=args.template_root,
        resume=not args.no_resume,
        preferred_quality=args.preferred_quality,
        eps_e=args.eps_e,
        retain_written_meshes=args.retain_written_meshes,
    )
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "attempted",
                    "passed",
                    "pass_fraction",
                    "worst_min_scaled_quality",
                    "elapsed_s",
                )
            },
            indent=2,
        )
    )
    return 0 if report["passed"] == report["attempted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
