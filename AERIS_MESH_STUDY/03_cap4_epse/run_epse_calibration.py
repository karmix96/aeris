#!/usr/bin/env python3
"""Stage 01 cap4 surface freeze and epsE calibration runner.

The production campaign CLI samples by seed. Stage 01 is governed by a frozen
LHS CSV, so this study-local runner consumes explicit rows, builds cap4
surfaces from those exact design vectors, and optionally re-marches each
byte-identical surface under the declared epsE variants.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from aeris.cfd.case.runner import run_case  # noqa: E402
from aeris.cfd.case.spec import CaseSpec, GeometryInput, VolumeMeshSpec  # noqa: E402
from aeris.cfd.meshing.registry import get_topology  # noqa: E402
from aeris.cfd.presets.registry import get_preset  # noqa: E402
from aeris.common.config import file_sha256, load_yaml_config  # noqa: E402
from aeris.generators.bwb_segmented_v1.params import BWBDesignSample  # noqa: E402
from aeris.geometry.config_resolver import resolve_generator_and_config  # noqa: E402
from aeris.geometry.registry import get_geometry_generator  # noqa: E402

EXPECTED_SAMPLE_COLUMNS = [
    "c1_m",
    "c2_ratio",
    "c3_ratio",
    "c4_ratio",
    "b_total_m",
    "b3_ratio",
    "split_ratio",
    "sw1_deg",
    "sw2_deg",
    "sw3_deg",
    "twist_b0_deg",
    "twist_b1_deg",
    "twist_b2_deg",
    "twist_b3_deg",
    "dihedral_b1_deg",
    "dihedral_b2_deg",
    "dihedral_b3_deg",
    "elevon_start_frac",
    "elevon_end_frac",
    "elevon_hinge_frac",
]


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _stable_hash(payload: Any) -> str:
    import hashlib

    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git_value(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip()


def _env() -> dict[str, Any]:
    return {
        "python": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "git_head": _git_value("rev-parse", "HEAD"),
        "git_branch": _git_value("rev-parse", "--abbrev-ref", "HEAD"),
    }


def _load_samples(csv_path: Path) -> list[tuple[int, BWBDesignSample]]:
    rows: list[tuple[int, BWBDesignSample]] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [
            name for name in EXPECTED_SAMPLE_COLUMNS if name not in (reader.fieldnames or [])
        ]
        if missing:
            raise ValueError(f"{csv_path} is missing columns: {missing}")
        for ordinal, row in enumerate(reader):
            sample_index = int(row.get("sample_index") or ordinal)
            sample_values = {name: float(row[name]) for name in EXPECTED_SAMPLE_COLUMNS}
            rows.append((sample_index, BWBDesignSample(**sample_values)))
    if not rows:
        raise ValueError(f"{csv_path} contains no samples")
    return rows


def _load_geometry(config_path: Path) -> tuple[str, Any, Any]:
    raw = load_yaml_config(config_path)
    generator_id, generator_config = resolve_generator_and_config(raw)
    generator = get_geometry_generator(generator_id)
    return generator_id, generator_config, generator


MESH_FAMILY_V2_RECIPES: dict[str, dict[str, object]] = {
    "mesh_family_v2_l1_coarse": {
        "points_per_side": 25,
        "spanwise_panels": 8,
        "cap_wrap_points": 11,
        "tip_radial_points": 5,
    },
    "mesh_family_v2_l2_smoke": {
        "points_per_side": 33,
        "spanwise_panels": 12,
        "cap_wrap_points": 15,
        "tip_radial_points": 7,
    },
    "mesh_family_v2_l3_medium": {
        "points_per_side": 49,
        "spanwise_panels": 16,
        "cap_wrap_points": 21,
        "tip_radial_points": 9,
    },
}
PYGEO_STUDY_RECIPES: dict[str, dict[str, object]] = {
    "pygeo_study_l1_reference": {
        "points_per_side": 25,
        "spanwise_panels": 8,
        "cap_wrap_points": 5,
        "tip_radial_points": 5,
        "cap_wrap_x": 0.40,
        "tip_topology": "airfoil_face",
        "tip_smooth_iters": 0,
        "te_thickness": 0.005,
        "te_thickness_abs_floor": 0.0,
        "te_base_points": 0,
        "min_shape_metric": 1.0e-6,
        "max_adjacent_normal_angle": 180.0,
        "chordwise_distribution": "uniform",
        "chordwise_beta": 2.0,
        "spanwise_distribution": "uniform",
        "spanwise_beta": 2.0,
        "spanwise_allocation": "proportional",
    },
    "pygeo_study_l2_reference": {
        "points_per_side": 33,
        "spanwise_panels": 12,
        "cap_wrap_points": 7,
        "tip_radial_points": 5,
        "cap_wrap_x": 0.40,
        "tip_topology": "airfoil_face",
        "tip_smooth_iters": 0,
        "te_thickness": 0.005,
        "te_thickness_abs_floor": 0.0,
        "te_base_points": 0,
        "min_shape_metric": 1.0e-6,
        "max_adjacent_normal_angle": 180.0,
        "chordwise_distribution": "uniform",
        "chordwise_beta": 2.0,
        "spanwise_distribution": "uniform",
        "spanwise_beta": 2.0,
        "spanwise_allocation": "proportional",
    },
    "pygeo_study_l3_reference": {
        "points_per_side": 49,
        "spanwise_panels": 16,
        "cap_wrap_points": 9,
        "tip_radial_points": 7,
        "cap_wrap_x": 0.40,
        "tip_topology": "airfoil_face",
        "tip_smooth_iters": 0,
        "te_thickness": 0.005,
        "te_thickness_abs_floor": 0.0,
        "te_base_points": 0,
        "min_shape_metric": 1.0e-6,
        "max_adjacent_normal_angle": 180.0,
        "chordwise_distribution": "uniform",
        "chordwise_beta": 2.0,
        "spanwise_distribution": "uniform",
        "spanwise_beta": 2.0,
        "spanwise_allocation": "proportional",
    },
}


def _surface_params(
    preset_name: str, recipe_name: str
) -> tuple[str, dict[str, object], dict[str, Any]]:
    preset = get_preset(preset_name)
    params = dict(preset.surface)
    recipe_source: dict[str, Any] = {
        "recipe": recipe_name,
        "base_preset": preset_name,
        "base_preset_source": "src/aeris/cfd/presets/data/mesh_family_smoke.yaml",
    }
    if recipe_name == "legacy_smoke_preset":
        pass
    elif recipe_name in PYGEO_STUDY_RECIPES:
        params.update(PYGEO_STUDY_RECIPES[recipe_name])
        params["oml_topology"] = "cap4"
        study_config = REPO_ROOT / "configs/cfd/pygeo_surface_mesh_study.yaml"
        recipe_source.update(
            {
                "overlay_source": "configs/cfd/pygeo_surface_mesh_study.yaml",
                "overlay_source_sha256": file_sha256(study_config),
                "reference_level": recipe_name.split("_")[2].upper()
                if recipe_name.startswith("pygeo_study_l")
                else "L3",
            }
        )
    elif recipe_name in MESH_FAMILY_V2_RECIPES:
        params.update(MESH_FAMILY_V2_RECIPES[recipe_name])
        params.update(
            {
                "oml_topology": "cap4",
                "spanwise_allocation": "proportional",
                "cap_wrap_x": 0.15,
                "tip_smooth_iters": 20,
                "te_thickness": 0.005,
            }
        )
        mesh_family = REPO_ROOT / "configs/cfd/MESH_FAMILY_V2.md"
        surface_laws = REPO_ROOT / "configs/cfd/SURFACE_MESH_LAWS.md"
        recipe_source.update(
            {
                "overlay_source": "configs/cfd/MESH_FAMILY_V2.md",
                "overlay_source_sha256": file_sha256(mesh_family),
                "surface_law_source": "configs/cfd/SURFACE_MESH_LAWS.md",
                "surface_law_source_sha256": file_sha256(surface_laws),
            }
        )
    else:
        valid = [
            "legacy_smoke_preset",
            *sorted(PYGEO_STUDY_RECIPES),
            *sorted(MESH_FAMILY_V2_RECIPES),
        ]
        raise ValueError(f"unknown surface recipe {recipe_name!r}; valid: {valid}")
    oml = str(params.pop("oml_topology", "cap4"))
    if oml != "cap4":
        raise ValueError(
            f"Stage 01 S0 control must use cap4, got {oml!r} from preset {preset_name}"
        )
    return "wing_cap4_v1", params, recipe_source


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _surface_hashes(surface_dir: Path) -> dict[str, str | None]:
    names = [
        "surface.fmt",
        "surface_report.json",
        "surface.vtk",
        "surface_blocks.npz",
    ]
    return {
        name: file_sha256(surface_dir / name) if (surface_dir / name).is_file() else None
        for name in names
    }


def _build_surface(
    *,
    sample_index: int,
    sample: BWBDesignSample,
    generator_id: str,
    generator_config: Any,
    generator: Any,
    topology_id: str,
    surface_params: dict[str, object],
    surface_recipe: str,
    sample_dir: Path,
    reuse_existing: bool,
) -> dict[str, Any]:
    surface_dir = sample_dir / "surface"
    surface_report_path = surface_dir / "surface_report.json"
    surface_fmt_path = surface_dir / "surface.fmt"
    source = "reused_existing"
    error = None
    t0 = time.perf_counter()

    if not reuse_existing or not (surface_report_path.is_file() and surface_fmt_path.is_file()):
        source = "generated"
        try:
            case = generator.run_full_case(
                sample=sample,
                config=generator_config,
                output_dir=sample_dir / "geometry",
                save_plot=False,
                build_aerosandbox=True,
            )
            wing = getattr(case, "wing", None)
            if wing is None:
                raise RuntimeError("geometry case did not produce an AeroSandbox wing")
            get_topology(topology_id).generate(wing, surface_dir, surface_params)
        except Exception as exc:  # noqa: BLE001 - report per-sample failure
            error = f"{type(exc).__name__}: {exc}"

    seconds = time.perf_counter() - t0
    report = _read_json(surface_report_path) or {}
    sample_payload = asdict(sample)
    sample_hash = _stable_hash(sample_payload)
    connectivity = report.get("connectivity") or {}
    surface_qc = {
        "accepted_pre_pyhyp": report.get("accepted_pre_pyhyp"),
        "global": report.get("global"),
        "symmetry_root": report.get("symmetry_root"),
        "failure_reasons": report.get("failure_reasons"),
        "block_count": report.get("block_count"),
        "blocks": report.get("blocks"),
    }

    _write_json(
        sample_dir / "connectivity.json",
        {
            "schema": "aeris.mesh_study.stage01_connectivity.v1",
            "sample_index": sample_index,
            "topology_id": topology_id,
            "connectivity_hash": _stable_hash(connectivity),
            "connectivity": connectivity,
        },
    )
    _write_json(
        sample_dir / "surface_qc.json",
        {
            "schema": "aeris.mesh_study.stage01_surface_qc.v1",
            "sample_index": sample_index,
            "topology_id": topology_id,
            "surface_qc": surface_qc,
        },
    )

    manifest = {
        "schema": "aeris.mesh_study.stage01_surface_manifest.v1",
        "sample_index": sample_index,
        "sample_id": f"lhs7_{sample_index:02d}",
        "sample_hash": sample_hash,
        "design_sample": sample_payload,
        "generator_id": generator_id,
        "topology_id": topology_id,
        "volume_preset": "smoke",
        "surface_recipe": surface_recipe,
        "surface_params": surface_params,
        "surface_dir": str(surface_dir),
        "surface_source": source,
        "seconds": seconds,
        "artifact_sha256": _surface_hashes(surface_dir),
        "connectivity_json": str(sample_dir / "connectivity.json"),
        "surface_qc_json": str(sample_dir / "surface_qc.json"),
        "status": "surface_ok"
        if error is None and surface_fmt_path.is_file()
        else "surface_failed",
        "error": error,
    }
    _write_json(sample_dir / "manifest.json", manifest)
    return manifest


def _copy_surface_reference(source_surface: Path, target_surface: Path) -> None:
    target_surface.mkdir(parents=True, exist_ok=True)
    for name in ("surface.fmt", "surface_report.json"):
        source = source_surface / name
        if not source.is_file():
            raise FileNotFoundError(f"missing surface reference: {source}")
        shutil.copy2(source, target_surface / name)


def _run_variant(
    *,
    sample_manifest: dict[str, Any],
    eps_e: float,
    preset: str,
    volume_level: str,
    workdir: Path,
    dry_run: bool,
    keep_meshes: bool,
) -> dict[str, Any]:
    sample_id = str(sample_manifest["sample_id"])
    variant_id = f"eps{str(eps_e).replace('.', '')}"
    case_dir = workdir / variant_id / sample_id
    source_surface = Path(str(sample_manifest["surface_dir"]))
    t0 = time.perf_counter()
    error = None
    stage_status = None

    try:
        spec = CaseSpec(
            name=f"stage01_{variant_id}_{sample_id}",
            geometry=GeometryInput(surface_dir=source_surface),
            volume_mesh=VolumeMeshSpec(
                preset=preset,
                level=volume_level,
                raw_options={"epsE": eps_e, "epsI": 2.0 * eps_e},
            ),
        )
        results = run_case(
            spec,
            workdir=case_dir,
            stages=("surface", "volume"),
            dry_run=dry_run,
            echo=print,
        )
        stage_status = results.get("volume").status if "volume" in results else None
    except Exception as exc:  # noqa: BLE001 - classify every row
        error = f"{type(exc).__name__}: {exc}"

    seconds = time.perf_counter() - t0
    surface_dir = case_dir / "surface"
    volume_report = _read_json(surface_dir / "volume_report.json") or {}
    effective_options = _read_json(surface_dir / "pyhyp_effective_options.json") or {}
    march = volume_report.get("march_metrics") or {}
    audit = volume_report.get("volume_audit") or {}
    layer_count = march.get("layer_count")
    low_quality_layers = march.get("low_quality_layers")
    low_quality_layer_fraction = None
    if layer_count not in (None, 0) and low_quality_layers is not None:
        low_quality_layer_fraction = float(low_quality_layers) / float(layer_count)
    clean = (
        not dry_run
        and error is None
        and volume_report.get("status") == "valid"
        and audit.get("classification") == "clean"
        and int(march.get("low_quality_layers") or 0) == 0
        and float(march.get("min_volume") or 0.0) > 0.0
        and float(march.get("min_quality") or 0.0) > 0.0
    )

    if not keep_meshes:
        for mesh in surface_dir.glob("wing_vol_*.cgns"):
            mesh.unlink()

    return {
        "variant": variant_id,
        "epsE": eps_e,
        "epsI": 2.0 * eps_e,
        "sample_id": sample_id,
        "sample_index": sample_manifest["sample_index"],
        "source_surface_fmt_sha256": sample_manifest["artifact_sha256"].get("surface.fmt"),
        "workdir": str(case_dir),
        "dry_run": dry_run,
        "stage_status": stage_status,
        "volume_report_status": volume_report.get("status"),
        "volume_audit_classification": audit.get("classification"),
        "inverted_cells": audit.get("inverted_cells"),
        "layer_count": layer_count,
        "low_quality_layers": low_quality_layers,
        "low_quality_layer_fraction": low_quality_layer_fraction,
        "min_quality": march.get("min_quality"),
        "min_volume": march.get("min_volume"),
        "seconds": seconds,
        "clean_for_stage01": clean if not dry_run else None,
        "effective_options_sha256": (
            file_sha256(surface_dir / "pyhyp_effective_options.json")
            if (surface_dir / "pyhyp_effective_options.json").is_file()
            else None
        ),
        "pyhyp_options_sha256": (
            file_sha256(surface_dir / "pyhyp_options.json")
            if (surface_dir / "pyhyp_options.json").is_file()
            else None
        ),
        "volume_report_sha256": (
            file_sha256(surface_dir / "volume_report.json")
            if (surface_dir / "volume_report.json").is_file()
            else None
        ),
        "effective_options_summary": {
            "options": {
                key: (effective_options.get("options") or {}).get(key)
                for key in ("epsE", "epsI", "cMax", "N", "s0", "coarsen")
            }
        },
        "error": error,
    }


def _select_common_start(rows: list[dict[str, Any]], eps_values: list[float]) -> float | None:
    for eps_e in sorted(eps_values, reverse=True):
        subset = [row for row in rows if float(row["epsE"]) == eps_e]
        if subset and all(row.get("clean_for_stage01") is True for row in subset):
            return eps_e
    return None


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Stage 01 cap4 / epsE Calibration Report",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Status: `{report['status']}`",
        f"- Geometry config: `{report['geometry_config']}`",
        f"- Sample CSV: `{report['sample_csv']}`",
        f"- Surface count: {len(report['surfaces'])}",
        f"- epsE common start: `{report.get('epsE_common_start')}`",
        "",
        "## Surface References",
    ]
    for surface in report["surfaces"]:
        lines.append(
            f"- {surface['sample_id']}: {surface['status']}, "
            f"surface.fmt `{surface['artifact_sha256'].get('surface.fmt')}`"
        )
    if report["remarch_rows"]:
        lines.extend(["", "## Remarch Rows"])
        for row in report["remarch_rows"]:
            state = row.get("clean_for_stage01")
            lines.append(
                f"- {row['variant']} {row['sample_id']}: clean={state}, "
                f"audit={row.get('volume_audit_classification')}, "
                f"low_quality_layers={row.get('low_quality_layers')}, "
                f"error={row.get('error')}"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    csv_path = (REPO_ROOT / args.sample_csv).resolve()
    config_path = (REPO_ROOT / args.geometry_config).resolve()
    workdir = (REPO_ROOT / args.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    samples = _load_samples(csv_path)
    if args.limit is not None:
        samples = samples[: args.limit]
    generator_id, generator_config, generator = _load_geometry(config_path)
    topology_id, params, recipe_source = _surface_params(args.preset, args.surface_recipe)

    surfaces: list[dict[str, Any]] = []
    for sample_index, sample in samples:
        sample_dir = workdir / "surfaces" / f"lhs7_{sample_index:02d}"
        manifest = _build_surface(
            sample_index=sample_index,
            sample=sample,
            generator_id=generator_id,
            generator_config=generator_config,
            generator=generator,
            topology_id=topology_id,
            surface_params=params,
            surface_recipe=args.surface_recipe,
            sample_dir=sample_dir,
            reuse_existing=args.reuse_existing,
        )
        surfaces.append(manifest)
        print(f"[epse] surface {manifest['sample_id']}: {manifest['status']}")

    surface_manifest = {
        "schema": "aeris.mesh_study.stage01_surface_reference_manifest.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "geometry_config": str(config_path),
        "geometry_config_sha256": file_sha256(config_path),
        "sample_csv": str(csv_path),
        "sample_csv_sha256": file_sha256(csv_path),
        "preset": args.preset,
        "surface_recipe": args.surface_recipe,
        "surface_recipe_source": recipe_source,
        "topology_id": topology_id,
        "surface_params": params,
        "environment": _env(),
        "surfaces": surfaces,
    }
    _write_json(workdir / "surface_reference_manifest.json", surface_manifest)

    remarch_rows: list[dict[str, Any]] = []
    eps_values = [float(item) for item in args.eps]
    if args.mode in {"dry-run", "full"}:
        for eps_e in eps_values:
            for surface in surfaces:
                if surface.get("status") != "surface_ok":
                    continue
                row = _run_variant(
                    sample_manifest=surface,
                    eps_e=eps_e,
                    preset=args.preset,
                    volume_level=args.volume_level,
                    workdir=workdir / "remarch",
                    dry_run=args.mode == "dry-run",
                    keep_meshes=args.keep_meshes,
                )
                remarch_rows.append(row)
                print(
                    f"[epse] {row['variant']} {row['sample_id']}: "
                    f"clean={row['clean_for_stage01']} error={row['error']}"
                )

    eps_common = _select_common_start(remarch_rows, eps_values) if args.mode == "full" else None
    surface_failures = [item for item in surfaces if item.get("status") != "surface_ok"]
    if args.mode == "full":
        status = "PASS" if eps_common is not None and not surface_failures else "FAIL"
    else:
        status = "INCOMPLETE" if not surface_failures else "FAIL"

    report = {
        "schema": "aeris.mesh_study.stage01_epse_calibration_report.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "status": status,
        "geometry_config": str(config_path),
        "geometry_config_sha256": file_sha256(config_path),
        "sample_csv": str(csv_path),
        "sample_csv_sha256": file_sha256(csv_path),
        "workdir": str(workdir),
        "preset": args.preset,
        "surface_recipe": args.surface_recipe,
        "surface_recipe_source": recipe_source,
        "volume_level": args.volume_level,
        "eps_values": eps_values,
        "epsE_common_start": eps_common,
        "selection_rule": "highest epsE with all locked samples clean and zero low-quality layers",
        "surface_reference_manifest": str(workdir / "surface_reference_manifest.json"),
        "surfaces": surfaces,
        "remarch_rows": remarch_rows,
        "environment": _env(),
    }
    report_path = (REPO_ROOT / args.report_json).resolve()
    _write_json(report_path, report)
    _write_markdown(report, report_path.with_suffix(".md"))
    print(f"[epse] report: {report_path}")
    return 1 if status == "FAIL" else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample-csv",
        default="AERIS_MESH_STUDY/00_governance/epse_calibration_lhs10_seed7_samples.csv",
    )
    parser.add_argument("--geometry-config", default="configs/geometry/bwb.yaml")
    parser.add_argument(
        "--workdir",
        default="AERIS_MESH_STUDY/artifacts/stage01/epse_calibration",
    )
    parser.add_argument(
        "--report-json",
        default="AERIS_MESH_STUDY/03_cap4_epse/epse_calibration_report.json",
    )
    parser.add_argument("--preset", default="smoke")
    parser.add_argument(
        "--surface-recipe",
        default="pygeo_study_l3_reference",
        choices=(
            "legacy_smoke_preset",
            *PYGEO_STUDY_RECIPES.keys(),
            *MESH_FAMILY_V2_RECIPES.keys(),
        ),
        help="Explicit cap4 surface-control recipe for the locked Stage 01 surfaces.",
    )
    parser.add_argument("--volume-level", default="smoke")
    parser.add_argument("--eps", nargs="+", default=["1.5", "2.0", "3.0"])
    parser.add_argument(
        "--mode",
        choices=("surfaces", "dry-run", "full"),
        default="dry-run",
        help="surfaces builds references only; dry-run writes pyHyp inputs; full runs pyHyp.",
    )
    parser.add_argument("--limit", type=int, default=None, help="First N samples only.")
    parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Reuse existing surface.fmt/surface_report.json when present.",
    )
    parser.add_argument(
        "--keep-meshes",
        action="store_true",
        help="Keep generated CGNS volume meshes after audit.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
