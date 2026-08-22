#!/usr/bin/env python3
"""Governed S6 grid/TE qualification and laptop-safe CFD smoke pilots."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _path in (HERE, REPO_ROOT / "src", STUDIES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import campaign  # noqa: E402
import strategy_s6  # noqa: E402
from deform import (  # noqa: E402
    WALL_TOLERANCE_M,
    deform_cgns,
    load_surface_blocks,
    sha256,
    validate_template_correspondence,
    volume_interface_report,
)
from shared.pyhyp_runner import read_result  # noqa: E402
from shared.qc import write_surface_artifacts  # noqa: E402
from shared.volume_qc import volume_report  # noqa: E402

from aeris.cfd.case.spec import FlowConditions, SolveSpec  # noqa: E402
from aeris.cfd.meshing.pyhyp_extrude import (  # noqa: E402
    mach_aero_python,
    write_pyhyp_run_inputs,
)
from aeris.cfd.meshing.pyhyp_options import build_pyhyp_options  # noqa: E402
from aeris.cfd.meshing.volume_audit import read_volume_blocks  # noqa: E402
from aeris.cfd.solvers.base import get_solver_adapter  # noqa: E402

PLAN_SCHEMA = "aeris.mesh.s6_qualification_plan.v3"
LAPTOP_MESH_SCHEMA = "aeris.mesh.s6_laptop_mesh.v2"
LAPTOP_TEMPLATE_SCHEMA = "aeris.mesh.s6_laptop_template.v2"
LAPTOP_CFD_SCHEMA = "aeris.mesh.s6_laptop_cfd.v2"
LAPTOP_SUMMARY_SCHEMA = "aeris.mesh.s6_laptop_summary.v2"
LEGACY_AUDIT_SCHEMA = "aeris.mesh.s6_legacy_pilot_audit.v2"

DEVELOPMENT_SET = "lhs100_seed42"
GRID_GEOMETRIES = (42, 7, 95, 89, 96)
TE_GEOMETRIES = (42, 7, 95)
LAPTOP_GEOMETRIES = (42, 95, 7)
LAPTOP_TEMPLATE_ROUTES = {42: 42, 95: 95, 7: 95}
FLOW = {
    "alpha": 2.0,
    "mach": 0.2,
    "reynolds": 1.0e6,
    "temperature": 288.15,
}
DEFAULT_REGISTRY = (
    REPO_ROOT
    / "artifacts/s6_bounded_mesh_atlas"
    / "template_registry_qualified21_production_portable_v9.json"
)
PRODUCTION_FLOOR = 0.10
LAPTOP_SOLVER_PRESET = "rans_ank_nk_v1"
LAPTOP_RESIDUAL_ORDERS_MIN = 6.0
LAPTOP_FORCE_TAIL_RELATIVE_RANGE_MAX = 0.001
PLANNED_LAPTOP_MPI_PROCESSES = 4


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def _write_json(path: Path, value: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _reported_file_matches(report: dict[str, Any], path_field: str, hash_field: str) -> bool:
    path_value = report.get(path_field)
    expected = report.get(hash_field)
    if not isinstance(path_value, str) or not isinstance(expected, str):
        return False
    path = Path(path_value)
    return path.is_file() and sha256(path) == expected


def _laptop_raw_options() -> dict[str, Any]:
    return {
        "writeVolumeSolution": False,
        "writeSurfaceSolution": True,
        "monitorVariables": ["resrho", "resturb", "cl", "cd"],
        "NKSubspaceSize": campaign.NK_SUBSPACE_SIZE,
    }


def _laptop_solver_protocol() -> dict[str, Any]:
    return {
        "campaign_solver_implementation_sha256": (campaign._solver_implementation_sha256()),
        "qualification_sha256": sha256(Path(__file__)),
        "flow": FLOW,
        "preset": LAPTOP_SOLVER_PRESET,
        "raw_options": _laptop_raw_options(),
        "residual_orders_min": LAPTOP_RESIDUAL_ORDERS_MIN,
        "force_tail_relative_range_max": LAPTOP_FORCE_TAIL_RELATIVE_RANGE_MAX,
    }


def _laptop_solver_implementation_sha256() -> str:
    encoded = json.dumps(_laptop_solver_protocol(), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _laptop_mesh_implementation_sha256() -> str:
    inputs = {
        "campaign_mesh_implementation_sha256": campaign._mesh_implementation_sha256(),
        "qualification_sha256": sha256(Path(__file__)),
        "pyhyp_extrude_sha256": sha256(REPO_ROOT / "src/aeris/cfd/meshing/pyhyp_extrude.py"),
        "pyhyp_options_sha256": sha256(REPO_ROOT / "src/aeris/cfd/meshing/pyhyp_options.py"),
        "volume_audit_sha256": sha256(REPO_ROOT / "src/aeris/cfd/meshing/volume_audit.py"),
    }
    encoded = json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _primary_span_cells(surface_blocks: dict[str, np.ndarray]) -> int:
    counts = {int(nodes.shape[1] - 1) for nodes in surface_blocks.values()}
    if not counts or min(counts) < 1:
        raise ValueError("surface blocks do not contain a valid j-cell count")
    return max(counts)


def _grid_family() -> list[dict[str, Any]]:
    definitions = (
        ("G1_coarse", "smoke", 129, 7.2e-6),
        ("G2_medium", "medium", 193, 5.1e-6),
        ("G3_fine", "fine", 257, 3.6e-6),
    )
    rows = []
    for name, surface_level, normal_points, first_cell_fraction in definitions:
        spec = strategy_s6.LEVELS[surface_level]
        rows.append(
            {
                "name": name,
                "surface_level": surface_level,
                "chord_points": spec.chord_points,
                "end_points": spec.end_points,
                "collar_points": spec.collar_points,
                "span_cells": spec.span_cells,
                "normal_points": normal_points,
                "first_cell_fraction_characteristic": first_cell_fraction,
            }
        )
    return rows


def _te_variants() -> list[dict[str, Any]]:
    return [
        {
            "name": "TE_small",
            "te_abs_m": 0.0005,
            "te_floor_frac_local_chord": 0.0025,
        },
        {
            "name": "TE_baseline",
            "te_abs_m": 0.0010,
            "te_floor_frac_local_chord": 0.0050,
        },
        {
            "name": "TE_large",
            "te_abs_m": 0.0015,
            "te_floor_frac_local_chord": 0.0075,
        },
    ]


def build_qualification_plan() -> dict[str, Any]:
    """Return the governed development-only qualification experiment."""
    grid = _grid_family()
    for left, right in zip(grid[:-1], grid[1:], strict=True):
        for field in (
            "chord_points",
            "end_points",
            "collar_points",
            "span_cells",
            "normal_points",
        ):
            if int(right[field]) <= int(left[field]):
                raise RuntimeError(f"grid family does not refine {field}")
        if float(right["first_cell_fraction_characteristic"]) >= float(
            left["first_cell_fraction_characteristic"]
        ):
            raise RuntimeError("grid family does not refine first-cell spacing")

    te_variants = _te_variants()
    registry_hash = sha256(DEFAULT_REGISTRY)
    registry = _read_json(DEFAULT_REGISTRY)
    p0_span_cells = {
        str(int(template["geometry_index"])): int(template["span_cells"])
        for template in registry["templates"]
    }
    coefficient_floors = {"cl": 0.10, "cd": 0.01, "cmy": 0.05}
    maximum_relative_change = {"cl": 0.01, "cd": 0.03, "cmy": 0.02}
    grid_force_metric = {
        "formula": "abs(fine-medium)/max(abs(fine), coefficient_floor)",
        "coefficient_floors": coefficient_floors.copy(),
        "maximum_relative_change": maximum_relative_change.copy(),
    }
    te_force_metric = {
        "formula": "abs(variant-baseline)/max(abs(baseline), coefficient_floor)",
        "reference_variant": "TE_baseline",
        "coefficient_floors": coefficient_floors.copy(),
        "maximum_relative_change": maximum_relative_change.copy(),
    }
    return {
        "schema": PLAN_SCHEMA,
        "strategy": strategy_s6.STRATEGY_ID,
        "purpose": "freeze wall, trailing-edge, and true grid policy before hold-out",
        "development_set": DEVELOPMENT_SET,
        "holdout_accessed": False,
        "implementation_provenance": {
            "qualification_sha256": sha256(Path(__file__)),
            "strategy_s6_sha256": sha256(HERE / "strategy_s6.py"),
            "campaign_mesh_implementation_sha256": (campaign._mesh_implementation_sha256()),
            "campaign_solver_implementation_sha256": (campaign._solver_implementation_sha256()),
        },
        "preregistration_evidence": False,
        "history_note": (
            "the preserved v1 plan file was written after the laptop pilot; it records "
            "the earlier policy content but does not prove advance registration"
        ),
        "fixed_flow": FLOW,
        "execution_order": [
            "current_P0_candidate_yplus_on_development_cases",
            "calibrate_P0_wall_spacing_only_if_production_yplus_fails",
            "TE_sensitivity_on_G2",
            "three_grid_GCI_with_selected_TE",
            "confirm_selected_grid_TE_and_yplus",
            "freeze_policy_then_open_holdout_once",
        ],
        "current_candidate_wall_test": {
            "name": "P0_existing_atlas_candidate",
            "surface_level": "smoke",
            "chord_points": strategy_s6.LEVELS["smoke"].chord_points,
            "span_cells": {
                "mode": "geometry_dependent_from_selected_registry_template",
                "minimum": min(p0_span_cells.values()),
                "maximum": max(p0_span_cells.values()),
                "by_template_geometry": p0_span_cells,
            },
            "normal_points": 257,
            "first_cell_fraction_characteristic": 3.6e-6,
            "registry": DEFAULT_REGISTRY.relative_to(REPO_ROOT).as_posix(),
            "registry_sha256": registry_hash,
            "purpose": (
                "test the current 21-template candidate wall law and solver path; "
                "this is not a grid-convergence level"
            ),
            "limitations": [
                "P0 refines wall-normal points but retains smoke tangential resolution",
                "a P0 yplus pass does not establish force or drag grid convergence",
                "repeat yplus on the selected final tangential grid before policy freeze",
            ],
            "production_resolution_scope": (
                "wall_normal_candidate_only_at_smoke_tangential_resolution"
            ),
        },
        "grid_study": {
            "geometry_indices": list(GRID_GEOMETRIES),
            "levels": grid,
            "same_between_levels": [
                "master_geometry",
                "farfield_extent",
                "flow",
                "solver_and_turbulence_model",
                "convergence_and_acceptance_gates",
                "selected_TE_law",
            ],
            "outputs": ["cl", "cd", "cmy"],
            "method": "Richardson_extrapolation_and_GCI_using_effective_cell_size",
            "medium_to_fine_gate": grid_force_metric,
            "minimum_complete_geometries_for_100_case_campaign": 5,
        },
        "trailing_edge_study": {
            "geometry_indices": list(TE_GEOMETRIES),
            "screening_grid": "G2_medium",
            "confirmation_grid": "G3_fine",
            "variants": te_variants,
            "decision_rule": (
                "choose the smallest opening that passes every mesh and CFD hard gate; "
                "report force sensitivity, especially drag, and confirm it on G3"
            ),
            "material_change_metric": te_force_metric,
        },
        "laptop_smoke": {
            "geometry_indices": list(LAPTOP_GEOMETRIES),
            "template_routes": {
                str(index): template for index, template in LAPTOP_TEMPLATE_ROUTES.items()
            },
            "surface_level": "smoke",
            "normal_points": 65,
            "planned_mpi_processes": PLANNED_LAPTOP_MPI_PROCESSES,
            "purpose": "solver_path_and_rejection_logic_only",
            "production_claim_allowed": False,
            "production_wall_law_conclusion": "NOT_TESTED_AT_PRODUCTION_RESOLUTION",
            "limitations": [
                "N65 is coarser than G1 in the wall-normal direction",
                "the production first-cell height and march distance are reused on a coarse grid",
                "smoke tangential spacing can change the resolved wall shear",
                "yplus here is a rejection-logic screen, not wall-law calibration evidence",
            ],
        },
        "gci_validity_rule": (
            "use actual cell counts and unequal refinement ratios; report GCI only "
            "for finite, monotonic, asymptotic-looking sequences, otherwise report "
            "the raw grid envelope and mark the case non-asymptotic"
        ),
        "revision_note": (
            "v3 adds complete tip-grid refinement and machine-readable P0 limits; "
            "the preserved v1/v2 files were written after the pilot and are not "
            "preregistration evidence"
        ),
        "freeze_rule": (
            "do not access the locked holdout until wall yplus, TE, grid, solver, "
            "fallback, and acceptance policies are fixed"
        ),
    }


def write_plan(output: Path) -> dict[str, Any]:
    plan = build_qualification_plan()
    plan["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    _write_json(output, plan)
    return plan


def _case_id(index: int) -> str:
    if index < 0 or index >= 100:
        raise ValueError("laptop pilots must use development indices in [0, 100)")
    return f"{DEVELOPMENT_SET}_{index:03d}"


def _accepted_existing_template(
    path: Path,
    *,
    expected_registry_sha256: str,
    expected_implementation_sha256: str,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    report = _read_json(path)
    if (
        report.get("schema") == LAPTOP_TEMPLATE_SCHEMA
        and report.get("state") == "PASS"
        and report.get("source_registry_sha256") == expected_registry_sha256
        and report.get("mesh_implementation_sha256") == expected_implementation_sha256
        and _reported_file_matches(report, "cgns", "cgns_sha256")
        and _reported_file_matches(report, "source_cgns", "source_cgns_sha256")
        and _reported_file_matches(report, "surface_npz", "surface_npz_sha256")
        and _reported_file_matches(report, "source_pyhyp_options", "source_pyhyp_options_sha256")
        and _reported_file_matches(report, "source_surface_fmt", "source_surface_fmt_sha256")
    ):
        return report
    return None


def prepare_laptop_template(
    *,
    geometry_index: int,
    registry_path: Path,
    output: Path,
    timeout_s: float,
) -> dict[str, Any]:
    """Remarch one frozen production template at N=65 without changing s0."""
    template_dir = Path(output).resolve() / "_templates" / _case_id(geometry_index)
    report_path = template_dir / "template_report.json"
    registry_path = Path(registry_path).resolve()
    if not registry_path.is_file():
        raise FileNotFoundError(registry_path)
    registry_hash = sha256(registry_path)
    implementation_hash = _laptop_mesh_implementation_sha256()
    if existing := _accepted_existing_template(
        report_path,
        expected_registry_sha256=registry_hash,
        expected_implementation_sha256=implementation_hash,
    ):
        return existing

    registry = campaign._materialize_registry_assets(
        _read_json(registry_path),
        registry_path,
    )
    template = next(
        (row for row in registry["templates"] if int(row["geometry_index"]) == geometry_index),
        None,
    )
    if template is None:
        raise ValueError(f"production registry has no template {geometry_index}")
    campaign._verify_template_assets(template)
    native = _read_json(Path(template["pyhyp_options"]))
    surface_fmt = Path(template["surface_npz"]).with_name("surface.fmt")
    if not surface_fmt.is_file():
        raise FileNotFoundError(surface_fmt)
    characteristic_length = float(template["first_cell_height_m"]) / float(
        template["first_cell_fraction_characteristic"]
    )
    cgns = template_dir / "wing_vol_n65.cgns"
    template_dir.mkdir(parents=True, exist_ok=True)
    effective = build_pyhyp_options(
        surface_fmt.resolve(),
        level="production",
        characteristic_length=characteristic_length,
        output_file=cgns.resolve(),
        s0=float(native["s0"]),
        march_dist_factor=float(native["marchDist"]) / characteristic_length,
        n_grid=65,
        n_coarsen=int(native["coarsen"]),
        c_max=float(native["cMax"]),
        theta=float(native["theta"]),
        vol_coef=float(native["volCoef"]),
        eps_e_far=float(native["epsE"]),
        eps_i_far=float(native["epsI"]),
        vol_smooth_iter=int(native["volSmoothIter"]),
        vol_blend=float(native["volBlend"]),
        n_constant_start=int(native["nConstantStart"]),
        ksp_rel_tol=float(native["kspRelTol"]),
        ksp_max_its=int(native["kspMaxIts"]),
    )
    runner = write_pyhyp_run_inputs(template_dir, effective)
    returncode = campaign._run_with_timeout(
        [str(mach_aero_python()), str(runner)],
        template_dir,
        template_dir / "run_stdout.log",
        timeout_s,
    )
    march = read_result(template_dir) or {}
    if not cgns.is_file():
        raise RuntimeError(f"N=65 template {geometry_index} did not write CGNS")
    volume = read_volume_blocks(cgns)
    surface = load_surface_blocks(Path(template["surface_npz"]))
    correspondence = validate_template_correspondence(volume, surface)
    quality = volume_report(volume)
    interfaces = volume_interface_report(volume)
    passed = bool(
        returncode == 0
        and march.get("march_completed")
        and quality["inverted_cells"] == 0
        and float(quality["min_volume"]) > 0.0
        and float(quality["min_scaled_quality"]) >= PRODUCTION_FLOOR
        and correspondence["max_wall_error_m"] <= WALL_TOLERANCE_M
        and interfaces["paired_face_count"] == 20
        and interfaces["max_mismatch_m"] <= WALL_TOLERANCE_M
    )
    report = {
        "schema": LAPTOP_TEMPLATE_SCHEMA,
        "state": "PASS" if passed else "FAIL",
        "purpose": "N65_solver_smoke_template_with_production_wall_spacing",
        "production_claim_allowed": False,
        "source_registry": str(registry_path),
        "source_registry_sha256": registry_hash,
        "mesh_implementation_sha256": implementation_hash,
        "source_template_id": template["template_id"],
        "source_geometry_index": geometry_index,
        "source_cgns": template["cgns"],
        "source_cgns_sha256": template["cgns_sha256"],
        "surface_npz": template["surface_npz"],
        "surface_npz_sha256": template["surface_npz_sha256"],
        "source_pyhyp_options": template["pyhyp_options"],
        "source_pyhyp_options_sha256": template["pyhyp_options_sha256"],
        "source_surface_fmt": str(surface_fmt.resolve()),
        "source_surface_fmt_sha256": sha256(surface_fmt),
        "normal_points": 65,
        "first_cell_height_m": float(native["s0"]),
        "first_cell_fraction_characteristic": float(template["first_cell_fraction_characteristic"]),
        "eps_e": float(native["epsE"]),
        "return_code": returncode,
        "march": march,
        "correspondence": correspondence,
        "interfaces": interfaces,
        "quality": quality,
        "cgns": str(cgns.resolve()),
        "cgns_sha256": sha256(cgns),
    }
    _write_json(report_path, report)
    if not passed:
        raise RuntimeError(f"N=65 production-wall template {geometry_index} failed its gates")
    return report


def prepare_laptop_templates(
    *,
    indices: list[int],
    registry_path: Path,
    output: Path,
    timeout_s: float,
) -> dict[int, dict[str, Any]]:
    reports = {}
    for index in sorted(set(indices)):
        report = prepare_laptop_template(
            geometry_index=index,
            registry_path=registry_path,
            output=output,
            timeout_s=timeout_s,
        )
        reports[index] = report
        print(
            f"template {_case_id(index)} {report['state']} "
            f"qmin={report['quality']['min_scaled_quality']:.6f}",
            flush=True,
        )
    return reports


def _accepted_existing_mesh(
    path: Path,
    *,
    expected_template_sha256: str | None = None,
    expected_template_surface_sha256: str | None = None,
    expected_implementation_sha256: str | None = None,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    report = _read_json(path)
    mesh_path = Path(report.get("mesh_cgns", ""))
    if (
        report.get("schema") == LAPTOP_MESH_SCHEMA
        and report.get("state") == "MESH_ACCEPTED"
        and mesh_path.is_file()
        and report.get("mesh_cgns_sha256") == sha256(mesh_path)
        and (
            expected_template_sha256 is None
            or report.get("template_cgns_sha256") == expected_template_sha256
        )
        and (
            expected_template_surface_sha256 is None
            or report.get("template_surface_sha256") == expected_template_surface_sha256
        )
        and (
            expected_implementation_sha256 is None
            or report.get("mesh_implementation_sha256") == expected_implementation_sha256
        )
    ):
        return report
    return None


def prepare_laptop_case(
    *,
    index: int,
    output: Path,
    template_cgns: Path,
    template_surface: Path,
) -> dict[str, Any]:
    """Create and independently audit one exact-wall N=65 smoke mesh."""
    geometry_id = _case_id(index)
    case_dir = Path(output).resolve() / geometry_id
    report_path = case_dir / "mesh_report.json"
    template_cgns = Path(template_cgns).resolve()
    template_surface = Path(template_surface).resolve()
    if not template_cgns.is_file() or not template_surface.is_file():
        raise FileNotFoundError("the governed N=65 template assets are missing")
    template_hash = sha256(template_cgns)
    template_surface_hash = sha256(template_surface)
    implementation_hash = _laptop_mesh_implementation_sha256()
    if existing := _accepted_existing_mesh(
        report_path,
        expected_template_sha256=template_hash,
        expected_template_surface_sha256=template_surface_hash,
        expected_implementation_sha256=implementation_hash,
    ):
        return existing
    template_blocks = read_volume_blocks(template_cgns)
    normal_counts = {int(nodes.shape[0]) for nodes in template_blocks.values()}
    if normal_counts != {65}:
        raise ValueError(f"laptop template must have N=65, found {sorted(normal_counts)}")
    template_quality = volume_report(template_blocks)
    if (
        template_quality["inverted_cells"] != 0
        or float(template_quality["min_scaled_quality"]) < PRODUCTION_FLOOR
    ):
        raise ValueError("the N=65 template fails the fixed volume screen")
    surface_template_blocks = load_surface_blocks(template_surface)
    span_cells = _primary_span_cells(surface_template_blocks)

    geometry_case = strategy_s6.build_pygeo_case(
        DEVELOPMENT_SET,
        index,
        case_dir / "geometry_source",
    )
    if geometry_case.pygeo_result is None:
        raise RuntimeError("pyGeo did not produce the master geometry")
    surface_blocks, surface_info = strategy_s6.build_surface(
        geometry_case.pygeo_result,
        level="smoke",
        span_cells=span_cells,
    )
    if (
        not surface_info["surface_qc"]["accepted_pre_pyhyp"]
        or not surface_info["fidelity"]["passed"]
    ):
        raise RuntimeError(f"{geometry_id} failed the exact surface gates")
    surface_dir = case_dir / "surface"
    surface_artifacts = write_surface_artifacts(surface_blocks, surface_dir)
    _write_json(surface_dir / "surface_report.json", surface_info)

    mesh_path = case_dir / "mesh" / "wing_vol_n65.cgns"
    deformation_path = case_dir / "mesh" / "deformation_report.json"
    deformation = deform_cgns(
        template_cgns=template_cgns,
        template_surface_npz=template_surface,
        target_surface_npz=Path(surface_artifacts["surface_npz"]["path"]),
        output_cgns=mesh_path,
        report_path=deformation_path,
        production_floor=PRODUCTION_FLOOR,
    )
    accepted = bool(deformation["acceptance"]["production_floor_passed"])
    report = {
        "schema": LAPTOP_MESH_SCHEMA,
        "state": "MESH_ACCEPTED" if accepted else "MESH_REJECTED",
        "purpose": "laptop_solver_smoke_not_production_grid_validation",
        "production_claim_allowed": False,
        "development_set": DEVELOPMENT_SET,
        "holdout_accessed": False,
        "geometry_index": index,
        "geometry_id": geometry_id,
        "normal_points": 65,
        "span_cells": span_cells,
        "surface_level": "smoke",
        "te_law": surface_info["cfd_safe_te"],
        "template_cgns": str(template_cgns),
        "template_cgns_sha256": template_hash,
        "template_surface": str(template_surface),
        "template_surface_sha256": template_surface_hash,
        "mesh_implementation_sha256": implementation_hash,
        "mesh_cgns": str(mesh_path.resolve()),
        "mesh_cgns_sha256": sha256(mesh_path),
        "surface_artifacts": surface_artifacts,
        "surface_fidelity": surface_info["fidelity"],
        "acceptance": deformation["acceptance"],
        "deformation_report": str(deformation_path.resolve()),
        "reference_values": geometry_case.pygeo_result.reference_values,
    }
    _write_json(report_path, report)
    return report


def prepare_laptop_cases(
    *,
    indices: list[int],
    output: Path,
    registry_path: Path,
    timeout_s: float,
) -> list[dict[str, Any]]:
    missing_routes = [index for index in indices if index not in LAPTOP_TEMPLATE_ROUTES]
    if missing_routes:
        raise ValueError(f"no governed laptop template routes for {missing_routes}")
    routes = {index: LAPTOP_TEMPLATE_ROUTES[index] for index in indices}
    templates = prepare_laptop_templates(
        indices=list(routes.values()),
        registry_path=registry_path,
        output=output,
        timeout_s=timeout_s,
    )
    reports = []
    for index in indices:
        template_index = routes[index]
        template = templates[template_index]
        reports.append(
            prepare_laptop_case(
                index=index,
                output=output,
                template_cgns=Path(template["cgns"]),
                template_surface=Path(template["surface_npz"]),
            )
        )
        print(
            f"{_case_id(index)} via {_case_id(template_index)} "
            f"{reports[-1]['state']} "
            f"qmin={reports[-1]['acceptance']['quality']['min_scaled_quality']:.6f}",
            flush=True,
        )
    return reports


def _local_solver_path_passed(
    *,
    returncode: int,
    solver_status: str,
    residual_orders: float | None,
    force_plausibility: dict[str, Any],
    force_tail: dict[str, Any],
) -> bool:
    return bool(
        returncode == 0
        and solver_status == "converged"
        and residual_orders is not None
        and math.isfinite(float(residual_orders))
        and float(residual_orders) >= LAPTOP_RESIDUAL_ORDERS_MIN
        and force_plausibility["passed"]
        and force_tail["passed"]
    )


def _reported_yplus_surface_matches(report: dict[str, Any]) -> bool:
    gate = report.get("wall_yplus_gate")
    if not isinstance(gate, dict):
        return False
    surface = gate.get("surface_cgns")
    expected = gate.get("surface_cgns_sha256")
    if not isinstance(surface, str) or not isinstance(expected, str):
        return False
    path = Path(surface)
    return path.is_file() and sha256(path) == expected


def _existing_laptop_cfd_result(
    path: Path,
    *,
    mesh_sha256: str,
    implementation_sha256: str,
    mpi_np: int,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    report = _read_json(path)
    return (
        report
        if report.get("schema") == LAPTOP_CFD_SCHEMA
        and report.get("state") in {"LOCAL_SOLVER_PATH_PASSED", "LOCAL_SOLVER_PATH_FAILED"}
        and report.get("mesh_cgns_sha256") == mesh_sha256
        and report.get("solver_implementation_sha256") == implementation_sha256
        and report.get("mpi_processes") == mpi_np
        and _reported_file_matches(report, "solve_report", "solve_report_sha256")
        and _reported_file_matches(report, "solver_log", "solver_log_sha256")
        and _reported_yplus_surface_matches(report)
        else None
    )


def solve_laptop_case(
    *,
    index: int,
    output: Path,
    mpi_np: int,
    force: bool,
) -> dict[str, Any]:
    """Run one N=65 ADflow case and apply both smoke and production gates."""
    if mpi_np < 1:
        raise ValueError("mpi process count must be positive")
    geometry_id = _case_id(index)
    case_dir = Path(output).resolve() / geometry_id
    mesh_report = _accepted_existing_mesh(
        case_dir / "mesh_report.json",
        expected_implementation_sha256=_laptop_mesh_implementation_sha256(),
    )
    if mesh_report is None:
        raise RuntimeError(f"{geometry_id} has no accepted laptop mesh")
    cfd_dir = case_dir / "cfd"
    acceptance_path = cfd_dir / "laptop_cfd_report.json"
    solver_implementation_hash = _laptop_solver_implementation_sha256()
    if not force and (
        existing := _existing_laptop_cfd_result(
            acceptance_path,
            mesh_sha256=mesh_report["mesh_cgns_sha256"],
            implementation_sha256=solver_implementation_hash,
            mpi_np=mpi_np,
        )
    ):
        return existing

    campaign._archive_previous_solver_outputs(cfd_dir)
    acceptance_path.unlink(missing_ok=True)
    refs = mesh_report["reference_values"]
    solve = SolveSpec(
        solver="adflow",
        preset=LAPTOP_SOLVER_PRESET,
        flow=FlowConditions(**FLOW),
        area_ref=0.5 * float(refs["area_m2"]),
        chord_ref=float(refs["mean_aerodynamic_chord_m"]),
        mpi_np=mpi_np,
        raw_options=_laptop_raw_options(),
    )
    adapter = get_solver_adapter("adflow")
    prepared = adapter.prepare(solve, Path(mesh_report["mesh_cgns"]), cfd_dir)
    started = time.monotonic()
    returncode = adapter.run(prepared)
    solver_report = adapter.parse(prepared.workdir)
    orders_value = solver_report.convergence.get("orders_dropped")
    orders = float(orders_value) if orders_value is not None else None
    force_plausibility = campaign._force_plausibility_gate(solver_report.forces)
    force_tail = campaign._force_tail_gate(
        prepared.workdir / prepared.log_name,
        relative_range_max=LAPTOP_FORCE_TAIL_RELATIVE_RANGE_MAX,
    )
    yplus, _surface_solution = campaign._wall_yplus_gate(prepared.workdir)
    _write_json(prepared.workdir / "wall_yplus_summary.json", yplus)
    solver_path_passed = _local_solver_path_passed(
        returncode=returncode,
        solver_status=solver_report.status,
        residual_orders=orders,
        force_plausibility=force_plausibility,
        force_tail=force_tail,
    )
    production_gates_passed = bool(solver_path_passed and yplus["passed"])
    solve_report_path = prepared.workdir / "solve_report.json"
    solver_log_path = prepared.workdir / prepared.log_name
    report = {
        "schema": LAPTOP_CFD_SCHEMA,
        "state": ("LOCAL_SOLVER_PATH_PASSED" if solver_path_passed else "LOCAL_SOLVER_PATH_FAILED"),
        "purpose": "laptop_solver_smoke_not_production_grid_validation",
        "production_claim_allowed": False,
        "production_gates_passed_on_coarse_mesh": production_gates_passed,
        "production_wall_law_conclusion": "NOT_TESTED_AT_PRODUCTION_RESOLUTION",
        "n65_limitations": [
            "coarser than G1 in the wall-normal direction",
            "production first-cell height and march distance reused on N65",
            "smoke tangential resolution can alter resolved wall shear",
        ],
        "development_set": DEVELOPMENT_SET,
        "holdout_accessed": False,
        "geometry_index": index,
        "geometry_id": geometry_id,
        "mesh_cgns": mesh_report["mesh_cgns"],
        "mesh_cgns_sha256": mesh_report["mesh_cgns_sha256"],
        "normal_points": 65,
        "span_cells": mesh_report.get("span_cells"),
        "mpi_processes": mpi_np,
        "flow": FLOW,
        "solver_preset": LAPTOP_SOLVER_PRESET,
        "solver_protocol": _laptop_solver_protocol(),
        "solver_implementation_sha256": solver_implementation_hash,
        "solver_return_code": returncode,
        "solver_status": solver_report.status,
        "residual_orders_dropped": orders,
        "force_plausibility_gate": force_plausibility,
        "force_tail_gate": force_tail,
        "wall_yplus_gate": yplus,
        "forces": solver_report.forces,
        "solve_report": str(solve_report_path),
        "solve_report_sha256": sha256(solve_report_path),
        "solver_log": str(solver_log_path),
        "solver_log_sha256": sha256(solver_log_path),
        "elapsed_s": time.monotonic() - started,
    }
    _write_json(acceptance_path, report)
    return report


def _validate_current_laptop_cfd_report(
    path: Path, *, expected_index: int
) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.is_file():
        return None, ["report_missing"]
    try:
        report = _read_json(path)
    except (OSError, ValueError, TypeError) as error:
        return None, [f"report_unreadable:{type(error).__name__}"]

    reasons: list[str] = []
    if report.get("schema") != LAPTOP_CFD_SCHEMA:
        reasons.append("schema_mismatch")
    if report.get("state") not in {
        "LOCAL_SOLVER_PATH_PASSED",
        "LOCAL_SOLVER_PATH_FAILED",
    }:
        reasons.append("invalid_state")
    if report.get("geometry_index") != expected_index:
        reasons.append("geometry_index_mismatch")
    if report.get("holdout_accessed") is not False:
        reasons.append("holdout_flag_not_false")

    mpi_np = report.get("mpi_processes")
    if not isinstance(mpi_np, int) or mpi_np < 1:
        reasons.append("invalid_mpi_processes")
    expected_solver_hash = _laptop_solver_implementation_sha256()
    if report.get("solver_implementation_sha256") != expected_solver_hash:
        reasons.append("solver_implementation_mismatch")
    if report.get("flow") != FLOW:
        reasons.append("flow_mismatch")

    case_dir = path.parents[1]
    mesh_report = _accepted_existing_mesh(
        case_dir / "mesh_report.json",
        expected_implementation_sha256=_laptop_mesh_implementation_sha256(),
    )
    if mesh_report is None:
        reasons.append("mesh_report_stale_or_invalid")
    elif report.get("mesh_cgns_sha256") != mesh_report.get("mesh_cgns_sha256"):
        reasons.append("mesh_hash_mismatch")

    if not _reported_file_matches(report, "solve_report", "solve_report_sha256"):
        reasons.append("solve_report_stale_or_missing")
    if not _reported_file_matches(report, "solver_log", "solver_log_sha256"):
        reasons.append("solver_log_stale_or_missing")
    if not _reported_yplus_surface_matches(report):
        reasons.append("surface_solution_stale_or_missing")
    return report, reasons


def _mpi_deviation_reason(actual: Any, planned: int) -> str:
    if not isinstance(actual, int):
        return "actual_rank_count_missing_or_invalid"
    if actual < planned:
        return "actual_below_plan_reason_not_recorded_in_case_report"
    if actual > planned:
        return "actual_above_plan_reason_not_recorded_in_case_report"
    return "no_deviation"


def collect_laptop(*, indices: list[int], output: Path) -> dict[str, Any]:
    rows = []
    root = Path(output).resolve()
    for index in indices:
        path = root / _case_id(index) / "cfd/laptop_cfd_report.json"
        report, reasons = _validate_current_laptop_cfd_report(path, expected_index=index)
        if report is None and reasons == ["report_missing"]:
            rows.append({"geometry_index": index, "state": "NOT_RUN"})
            continue
        if reasons:
            rows.append(
                {
                    "geometry_index": index,
                    "state": "STALE_OR_INVALID_PROVENANCE",
                    "failure_reasons": reasons,
                    "report": str(path),
                    "report_sha256": sha256(path) if path.is_file() else None,
                    "mpi_processes": report.get("mpi_processes") if report else None,
                }
            )
            continue
        assert report is not None
        rows.append(
            {
                "geometry_index": index,
                "state": report["state"],
                "solver_status": report["solver_status"],
                "residual_orders_dropped": report["residual_orders_dropped"],
                "forces": report["forces"],
                "wall_yplus_passed": report["wall_yplus_gate"]["passed"],
                "wall_yplus_statistics": report["wall_yplus_gate"].get("statistics"),
                "mpi_processes": report["mpi_processes"],
                "normal_points": report["normal_points"],
                "span_cells": report["span_cells"],
                "mesh_cgns_sha256": report["mesh_cgns_sha256"],
                "solver_implementation_sha256": report["solver_implementation_sha256"],
                "report": str(path),
                "report_sha256": sha256(path),
                "elapsed_s": report["elapsed_s"],
            }
        )

    valid_states = {"LOCAL_SOLVER_PATH_PASSED", "LOCAL_SOLVER_PATH_FAILED"}
    completed = [row for row in rows if row["state"] in valid_states]
    stale = [row for row in rows if row["state"] == "STALE_OR_INVALID_PROVENANCE"]
    planned_mpi = PLANNED_LAPTOP_MPI_PROCESSES
    protocol_deviations = [
        {
            "geometry_index": row["geometry_index"],
            "row_state": row["state"],
            "field": "mpi_processes",
            "planned": planned_mpi,
            "actual": row.get("mpi_processes"),
            "reason": _mpi_deviation_reason(row.get("mpi_processes"), planned_mpi),
        }
        for row in rows
        if isinstance(row.get("mpi_processes"), int) and row.get("mpi_processes") != planned_mpi
    ]
    summary = {
        "schema": LAPTOP_SUMMARY_SCHEMA,
        "purpose": "laptop_solver_smoke_not_production_grid_validation",
        "production_claim_allowed": False,
        "campaign_ready": False,
        "development_set": DEVELOPMENT_SET,
        "holdout_accessed": False,
        "requested": len(indices),
        "completed": len(completed),
        "stale_or_invalid": len(stale),
        "solver_path_passed": (
            sum(row["state"] == "LOCAL_SOLVER_PATH_PASSED" for row in completed)
            if completed
            else None
        ),
        "wall_yplus_passed": (
            sum(bool(row["wall_yplus_passed"]) for row in completed) if completed else None
        ),
        "mesh_implementation_sha256": _laptop_mesh_implementation_sha256(),
        "solver_implementation_sha256": _laptop_solver_implementation_sha256(),
        "production_wall_law_status": "NOT_TESTED_AT_PRODUCTION_RESOLUTION",
        "scientific_interpretation": {
            "can_conclude": [
                "the mesh-to-ADflow path and rejection logic run locally",
                "the residual and force-stability gates pass on these N65 cases",
            ],
            "cannot_conclude": [
                "production-grid yplus adequacy",
                "production-grid force accuracy",
                "trailing-edge sensitivity",
                "grid convergence",
            ],
            "n65_yplus_result": (
                "coarse rejection-screen evidence only; do not calibrate or reject "
                "the production wall law from these values"
            ),
        },
        "protocol_deviations": protocol_deviations,
        "rows": rows,
    }
    summary_path = root / "laptop_summary_current.json"
    summary["summary_path"] = str(summary_path)
    summary["historical_summary_preserved"] = str(root / "laptop_summary.json")
    _write_json(summary_path, summary)
    return summary


def _legacy_asset(path_value: Any) -> dict[str, Any]:
    if not isinstance(path_value, str) or not path_value:
        return {"path": path_value, "exists": False, "sha256": None}
    path = Path(path_value)
    return {
        "path": str(path.resolve()),
        "exists": path.is_file(),
        "sha256": sha256(path) if path.is_file() else None,
    }


def audit_legacy_laptop(*, indices: list[int], output: Path, audit_output: Path) -> dict[str, Any]:
    root = Path(output).resolve()
    rows = []
    for index in indices:
        geometry_id = _case_id(index)
        case_dir = root / geometry_id
        mesh_report_path = case_dir / "mesh_report.json"
        cfd_report_path = case_dir / "cfd/laptop_cfd_report.json"
        mesh_report = _read_json(mesh_report_path)
        cfd_report = _read_json(cfd_report_path)

        surface_artifacts = mesh_report.get("surface_artifacts", {})
        surface_npz_record = surface_artifacts.get("surface_npz", {})
        surface_fmt_record = surface_artifacts.get("surface_fmt", {})
        yplus_gate = cfd_report.get("wall_yplus_gate", {})
        asset_values = {
            "mesh_report": str(mesh_report_path),
            "mesh_cgns": mesh_report.get("mesh_cgns"),
            "deformation_report": mesh_report.get("deformation_report"),
            "surface_npz": surface_npz_record.get("path"),
            "surface_fmt": surface_fmt_record.get("path"),
            "cfd_report": str(cfd_report_path),
            "solve_report": cfd_report.get("solve_report"),
            "solver_log": str(case_dir / "cfd/adflow_run.log"),
            "solver_script": str(case_dir / "cfd/run_adflow.py"),
            "wall_yplus_summary": str(case_dir / "cfd/wall_yplus_summary.json"),
            "surface_solution": yplus_gate.get("surface_cgns"),
        }
        assets = {name: _legacy_asset(path_value) for name, path_value in asset_values.items()}

        surface_path = Path(surface_npz_record["path"])
        surface_blocks = load_surface_blocks(surface_path)
        span_counts = sorted({int(nodes.shape[1] - 1) for nodes in surface_blocks.values()})
        declared_checks = {
            "mesh_cgns": (assets["mesh_cgns"]["sha256"] == mesh_report.get("mesh_cgns_sha256")),
            "surface_npz": (assets["surface_npz"]["sha256"] == surface_npz_record.get("sha256")),
            "surface_fmt": (assets["surface_fmt"]["sha256"] == surface_fmt_record.get("sha256")),
            "cfd_mesh_reference": (
                cfd_report.get("mesh_cgns_sha256") == mesh_report.get("mesh_cgns_sha256")
            ),
            "surface_solution": (
                assets["surface_solution"]["sha256"] == yplus_gate.get("surface_cgns_sha256")
            ),
        }
        _current_report, current_reasons = _validate_current_laptop_cfd_report(
            cfd_report_path, expected_index=index
        )
        rows.append(
            {
                "geometry_index": index,
                "geometry_id": geometry_id,
                "template_geometry_index": LAPTOP_TEMPLATE_ROUTES[index],
                "legacy_cfd_state": cfd_report.get("state"),
                "surface_block_j_cell_counts": span_counts,
                "realized_primary_span_cells": _primary_span_cells(surface_blocks),
                "all_assets_present": all(asset["exists"] for asset in assets.values()),
                "declared_hash_checks": declared_checks,
                "declared_hashes_match": all(declared_checks.values()),
                "current_cache_compatible": not current_reasons,
                "current_cache_rejection_reasons": current_reasons,
                "assets": assets,
            }
        )

    operator_notes = {}
    if 7 in indices:
        operator_notes["7"] = (
            "case 007 was launched with two MPI ranks after case 095 exhausted "
            "laptop swap; this note is not generated by the case report"
        )

    source_summary = root / "laptop_summary.json"
    report = {
        "schema": LEGACY_AUDIT_SCHEMA,
        "state": (
            "LEGACY_EVIDENCE_INTEGRITY_PASSED"
            if all(row["all_assets_present"] and row["declared_hashes_match"] for row in rows)
            else "LEGACY_EVIDENCE_INTEGRITY_FAILED"
        ),
        "purpose": "bind_pre_fingerprint_N65_pilot_bytes_without_rewriting_history",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "pilot_generated_by_current_code": False,
        "audit_generated_by_current_code": True,
        "current_cache_compatible": all(row["current_cache_compatible"] for row in rows),
        "rerun_required_for_current_provenance": True,
        "production_claim_allowed": False,
        "campaign_ready": False,
        "development_set": DEVELOPMENT_SET,
        "holdout_accessed": False,
        "claim_scope": [
            "historical local mesh-to-ADflow execution evidence",
            "historical residual, force-stability, and rejection-path evidence",
        ],
        "excluded_claims": [
            "current-code reproducibility",
            "production-grid yplus adequacy",
            "production-grid force accuracy",
            "trailing-edge sensitivity",
            "grid convergence",
        ],
        "operator_notes": operator_notes,
        "source_summary": _legacy_asset(str(source_summary)),
        "audit_implementation_sha256": sha256(Path(__file__)),
        "audit_provenance": {
            "qualification_sha256": sha256(Path(__file__)),
            "mesh_implementation_sha256": _laptop_mesh_implementation_sha256(),
            "solver_implementation_sha256": _laptop_solver_implementation_sha256(),
        },
        "rows": rows,
    }
    _write_json(audit_output, report)
    return report


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    plan = commands.add_parser("write-plan")
    plan.add_argument("--output", type=Path, required=True)

    prepare = commands.add_parser("prepare-laptop")
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--indices", type=int, nargs="+", default=list(LAPTOP_GEOMETRIES))
    prepare.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    prepare.add_argument("--template-timeout-s", type=float, default=3600.0)

    solve = commands.add_parser("solve-laptop")
    solve.add_argument("--output", type=Path, required=True)
    solve.add_argument("--index", type=int, required=True)
    solve.add_argument("--np", type=int, default=4)
    solve.add_argument("--force", action="store_true")

    collect = commands.add_parser("collect-laptop")
    collect.add_argument("--output", type=Path, required=True)
    collect.add_argument("--indices", type=int, nargs="+", default=list(LAPTOP_GEOMETRIES))

    legacy = commands.add_parser("audit-legacy-laptop")
    legacy.add_argument("--output", type=Path, required=True)
    legacy.add_argument("--audit-output", type=Path, required=True)
    legacy.add_argument("--indices", type=int, nargs="+", default=list(LAPTOP_GEOMETRIES))
    return parser


def main() -> int:
    args = make_parser().parse_args()
    if args.command == "write-plan":
        result = write_plan(args.output)
    elif args.command == "prepare-laptop":
        rows = prepare_laptop_cases(
            indices=args.indices,
            output=args.output,
            registry_path=args.registry,
            timeout_s=args.template_timeout_s,
        )
        result = {
            "prepared": len(rows),
            "accepted": sum(row["state"] == "MESH_ACCEPTED" for row in rows),
        }
    elif args.command == "solve-laptop":
        result = solve_laptop_case(
            index=args.index,
            output=args.output,
            mpi_np=args.np,
            force=args.force,
        )
    elif args.command == "collect-laptop":
        result = collect_laptop(indices=args.indices, output=args.output)
    elif args.command == "audit-legacy-laptop":
        result = audit_legacy_laptop(
            indices=args.indices,
            output=args.output,
            audit_output=args.audit_output,
        )
    else:
        raise RuntimeError("unhandled command: " + str(args.command))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
