#!/usr/bin/env python3
"""CLI for constructing, marching, deforming, and auditing S6 meshes."""

from __future__ import annotations

import argparse
import json
import subprocess
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

from atlas import (  # noqa: E402
    build_atlas_manifest,
    enrich_atlas_manifest,
    qualify_atlas_seeds,
    write_manifest,
)
from deform import deform_cgns, sha256  # noqa: E402
from resolution import first_cell_fraction  # noqa: E402
from shared.pyhyp_runner import prepare, read_result  # noqa: E402
from shared.qc import write_surface_artifacts  # noqa: E402
from shared.volume_qc import equivalence_against_pyhyp  # noqa: E402
from strategy_s6 import STRATEGY_ID, build_locked_surface  # noqa: E402

from aeris.cfd.meshing.pyhyp_extrude import mach_aero_python  # noqa: E402


def _default(value: Any) -> Any:
    if isinstance(value, (np.ndarray,)):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def _write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=_default) + "\n",
        encoding="utf-8",
    )
    return path


def surface_command(args: argparse.Namespace) -> dict[str, Any]:
    root = args.output.resolve()
    blocks, info, _case = build_locked_surface(
        args.set_name, args.index, root / "_geometry", level=args.level
    )
    target = root / info["locked_set_id"]
    artifacts = write_surface_artifacts(blocks, target)
    report = _write_json(target / "surface_report.json", info)
    return {
        "geometry_id": info["locked_set_id"],
        "surface_report": str(report),
        "artifacts": artifacts,
        "accepted": bool(info["surface_qc"]["accepted_pre_pyhyp"])
        and bool(info["fidelity"]["passed"]),
    }


def atlas_command(args: argparse.Namespace) -> dict[str, Any]:
    manifest = build_atlas_manifest(
        set_name=args.set_name,
        template_count=args.template_count,
        trust_radius_rms=args.trust_radius,
    )
    path = write_manifest(args.output.resolve(), manifest)
    return {"manifest": str(path), **manifest["coverage"]}


def enrich_atlas_command(args: argparse.Namespace) -> dict[str, Any]:
    manifest = json.loads(args.atlas_manifest.read_text(encoding="utf-8"))
    development = json.loads(args.development_report.read_text(encoding="utf-8"))
    enriched = enrich_atlas_manifest(
        manifest,
        development,
        warning_quality=args.warning_quality,
        maximum_attempts=args.maximum_attempts,
        maximum_templates=args.maximum_templates,
    )
    enriched["quality_enrichment"]["source_atlas"] = {
        "path": str(args.atlas_manifest.resolve()),
        "sha256": sha256(args.atlas_manifest),
    }
    enriched["quality_enrichment"]["development_report"] = {
        "path": str(args.development_report.resolve()),
        "sha256": sha256(args.development_report),
    }
    path = write_manifest(args.output.resolve(), enriched)
    quality_enrichment = enriched["quality_enrichment"]
    return {
        "manifest": str(path),
        "template_count": enriched["template_count"],
        "added_indices": quality_enrichment["added_indices"],
        "candidate_count": quality_enrichment["candidate_count"],
        "requires_revalidation": quality_enrichment["requires_revalidation"],
        "requires_production_validation": quality_enrichment[
            "requires_production_validation"
        ],
        "freeze_ready": quality_enrichment["freeze_ready"],
    }


def qualify_atlas_seeds_command(args: argparse.Namespace) -> dict[str, Any]:
    manifest = json.loads(args.atlas_manifest.read_text(encoding="utf-8"))
    seed_report = json.loads(args.seed_report.read_text(encoding="utf-8"))
    qualified = qualify_atlas_seeds(
        manifest,
        seed_report,
        production_floor=args.production_floor,
        minimum_templates=args.minimum_templates,
    )
    qualification = qualified["seed_qualification"]
    qualification["source_atlas"] = {
        "path": str(args.atlas_manifest.resolve()),
        "sha256": sha256(args.atlas_manifest),
    }
    qualification["seed_report"] = {
        "path": str(args.seed_report.resolve()),
        "sha256": sha256(args.seed_report),
    }
    path = write_manifest(args.output.resolve(), qualified)
    return {
        "manifest": str(path),
        "source_template_count": len(qualification["source_template_indices"]),
        "qualified_template_count": len(qualification["qualified_indices"]),
        "rejected_indices": [
            row["geometry_index"] for row in qualification["rejected"]
        ],
        "freeze_ready": qualification["freeze_ready"],
    }


def march_command(args: argparse.Namespace) -> dict[str, Any]:
    root = args.output.resolve()
    blocks, info, _case = build_locked_surface(
        args.set_name, args.index, root / "_geometry", level=args.surface_level
    )
    manifest = prepare(
        strategy_id=STRATEGY_ID,
        geometry_id=info["locked_set_id"],
        blocks=blocks,
        out_dir=root,
        level=args.volume_level,
        epse_ladder=(args.eps_e,),
        s0_fraction_override=first_cell_fraction(args.volume_level),
    )
    run_dir = Path(manifest["runs"][0]["dir"]).resolve()
    runner = Path(manifest["runs"][0]["runner"]).resolve()
    with (run_dir / "run_stdout.log").open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            [str(mach_aero_python()), str(runner)],
            cwd=run_dir,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    cgns = run_dir / "wing_vol.cgns"
    result = read_result(run_dir) or {}
    quality = equivalence_against_pyhyp(cgns) if cgns.is_file() else None
    accepted = bool(
        completed.returncode == 0
        and result.get("march_completed")
        and quality
        and quality.get("inverted_cells") == 0
        and float(quality.get("min_scaled_quality", -1.0)) > 0.0
    )
    report = {
        "strategy_id": STRATEGY_ID,
        "geometry_id": info["locked_set_id"],
        "return_code": completed.returncode,
        "accepted": accepted,
        "cgns": str(cgns),
        "surface_npz": str(run_dir / "surface_blocks.npz"),
        "march_result": result,
        "direct_quality": quality,
    }
    _write_json(run_dir / "s6_template_report.json", report)
    return report


def deform_command(args: argparse.Namespace) -> dict[str, Any]:
    return deform_cgns(
        template_cgns=args.template_cgns.resolve(),
        template_surface_npz=args.template_surface.resolve(),
        target_surface_npz=args.target_surface.resolve(),
        output_cgns=args.output_cgns.resolve(),
        report_path=args.report.resolve(),
        production_floor=args.production_floor,
    )


def make_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="S6 bounded mesh-atlas workflow")
    commands = root.add_subparsers(dest="command", required=True)

    surface = commands.add_parser("surface")
    surface.add_argument("--set-name", default="lhs100_seed42")
    surface.add_argument("--index", type=int, required=True)
    surface.add_argument("--level", default="smoke")
    surface.add_argument("--output", type=Path, required=True)
    surface.set_defaults(function=surface_command)

    atlas = commands.add_parser("atlas")
    atlas.add_argument("--set-name", default="lhs100_seed42")
    atlas.add_argument("--template-count", type=int, default=16)
    atlas.add_argument("--trust-radius", type=float, default=0.40)
    atlas.add_argument("--output", type=Path, required=True)
    atlas.set_defaults(function=atlas_command)

    enrich = commands.add_parser("enrich-atlas")
    enrich.add_argument("--atlas-manifest", type=Path, required=True)
    enrich.add_argument("--development-report", type=Path, required=True)
    enrich.add_argument("--warning-quality", type=float, default=0.15)
    enrich.add_argument("--maximum-attempts", type=int, default=5)
    enrich.add_argument("--maximum-templates", type=int, default=32)
    enrich.add_argument("--output", type=Path, required=True)
    enrich.set_defaults(function=enrich_atlas_command)

    qualify = commands.add_parser("qualify-atlas-seeds")
    qualify.add_argument("--atlas-manifest", type=Path, required=True)
    qualify.add_argument("--seed-report", type=Path, required=True)
    qualify.add_argument("--production-floor", type=float, default=0.10)
    qualify.add_argument("--minimum-templates", type=int, required=True)
    qualify.add_argument("--output", type=Path, required=True)
    qualify.set_defaults(function=qualify_atlas_seeds_command)

    march = commands.add_parser("march-template")
    march.add_argument("--set-name", default="lhs100_seed42")
    march.add_argument("--index", type=int, required=True)
    march.add_argument("--surface-level", default="smoke")
    march.add_argument("--volume-level", default="smoke")
    march.add_argument("--eps-e", type=float, default=2.0)
    march.add_argument("--output", type=Path, required=True)
    march.set_defaults(function=march_command)

    deform = commands.add_parser("deform")
    deform.add_argument("--template-cgns", type=Path, required=True)
    deform.add_argument("--template-surface", type=Path, required=True)
    deform.add_argument("--target-surface", type=Path, required=True)
    deform.add_argument("--output-cgns", type=Path, required=True)
    deform.add_argument("--report", type=Path, required=True)
    deform.add_argument("--production-floor", type=float, default=0.10)
    deform.set_defaults(function=deform_command)
    return root


def main() -> int:
    args = make_parser().parse_args()
    try:
        result = args.function(args)
    except Exception as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}, indent=2))
        return 1
    print(json.dumps({"status": "OK", **result}, indent=2, default=_default))
    if args.command == "march-template":
        return 0 if result["accepted"] else 2
    if args.command == "deform":
        return 0 if result["acceptance"]["production_floor_passed"] else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
