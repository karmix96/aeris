"""Fail-closed staged FEA runner with chained provenance artifacts."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import yaml

from aeris.common.config import file_sha256
from aeris.fea.calculix import (
    run_calculix,
    write_calculix_deck,
    write_solve_report,
)
from aeris.fea.case.spec import CaseSpec
from aeris.fea.geometry import load_stations
from aeris.fea.governance import run_qualification
from aeris.fea.mesh import build_wingbox_mesh, write_mesh_artifacts
from aeris.fea.mission import load_mission_authority
from aeris.fea.openaerostruct import OpenAeroStructError, run_oas_validation
from aeris.fea.physics import run_physics_analyses

CASE_MANIFEST_SCHEMA_VERSION = "aeris.fea.case_manifest.v1"
STAGES = ("geometry", "validate", "mesh", "solve", "physics", "qualify", "post")


class CaseError(ValueError):
    """The requested structural case cannot be completed safely."""


@dataclass(frozen=True)
class StageResult:
    stage: str
    status: str
    artifacts: dict[str, str] = field(default_factory=dict)
    details: dict[str, object] = field(default_factory=dict)


def _stage_geometry(spec: CaseSpec, workdir: Path) -> StageResult:
    source = spec.geometry.stations_file
    if source is None:
        raise CaseError(
            "case.geometry.aeris_config must first be resolved by the AERIS CLI; "
            "the standalone FEA core consumes an aeris.fea.stations.v1 file"
        )
    source = source.expanduser().resolve()
    if not source.is_file():
        raise CaseError(f"structural stations file not found: {source}")
    try:
        payload = load_stations(source)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise CaseError(f"invalid structural stations file: {exc}") from exc
    target = workdir / "geometry" / "stations.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if source != target.resolve():
        shutil.copy2(source, target)
    return StageResult(
        stage="geometry",
        status="ok",
        artifacts={"stations": str(target)},
        details={
            "station_count": len(payload["stations"]),
            "source": str(source),
            "generator": payload.get("generator"),
            "seed": payload.get("seed"),
            "design_set": payload.get("design_set"),
            "design_index": payload.get("design_index"),
            "design_matrix_sha256": payload.get("design_matrix_sha256"),
        },
    )


def _build_mesh(spec: CaseSpec, workdir: Path):
    stations_path = workdir / "geometry" / "stations.json"
    if not stations_path.is_file():
        raise CaseError(f"mesh stage requires {stations_path}; run geometry first")
    try:
        stations = load_stations(stations_path)
        return build_wingbox_mesh(
            stations,
            spec.wingbox,
            spec.mesh,
            spec.section,
            spec.material.density_kg_m3,
        )
    except ValueError as exc:
        raise CaseError(f"structural mesh rejected: {exc}") from exc


def _stage_validate(spec: CaseSpec, workdir: Path) -> StageResult:
    if not spec.openaerostruct_validation.enabled:
        return StageResult(
            stage="validate",
            status="skipped",
            details={"reason": "OpenAeroStruct comparison is not enabled"},
        )
    if spec.mission is None:
        raise CaseError("OpenAeroStruct validation requires a mission authority")
    stations_path = workdir / "geometry" / "stations.json"
    if not stations_path.is_file():
        raise CaseError(f"validation stage requires {stations_path}; run geometry first")
    try:
        stations = load_stations(stations_path)
        mission = load_mission_authority(spec.mission.authority_file)
        report_path = workdir / "validation" / "openaerostruct_validation.json"
        report = run_oas_validation(
            stations, mission, spec.openaerostruct_validation, report_path
        )
    except (ValueError, OSError, json.JSONDecodeError, OpenAeroStructError) as exc:
        raise CaseError(f"OpenAeroStruct validation rejected: {exc}") from exc
    return StageResult(
        stage="validate",
        status="ok" if report["status"] == "pass" else "failed",
        artifacts={"openaerostruct_validation": str(report_path)},
        details={
            "status": report["status"],
            "checks": report["checks"],
            "lift_curve": report["lift_curve"],
        },
    )


def _stage_mesh(spec: CaseSpec, workdir: Path) -> StageResult:
    mesh = _build_mesh(spec, workdir)
    artifacts = write_mesh_artifacts(mesh, workdir / "mesh")
    return StageResult(
        stage="mesh",
        status="ok",
        artifacts=artifacts,
        details={"quality": mesh.quality, "full_structural_mass_kg": mesh.mass_kg},
    )


def _stage_solve(
    spec: CaseSpec,
    workdir: Path,
    *,
    dry_run: bool,
    echo: Callable[[str], None] | None,
) -> StageResult:
    mesh_include = workdir / "mesh" / "wingbox_mesh.inp"
    if not mesh_include.is_file():
        raise CaseError(f"solve stage requires {mesh_include}; run mesh first")
    mesh = _build_mesh(spec, workdir)
    artifacts: dict[str, str] = {}
    reports: dict[str, object] = {}
    for load in spec.loads:
        solve_dir = workdir / "solve" / load.name
        deck = write_calculix_deck(spec, load, mesh, mesh_include, solve_dir)
        artifacts[f"deck:{load.name}"] = str(deck)
        artifacts[f"input_manifest:{load.name}"] = str(solve_dir / "input_manifest.json")
        if dry_run:
            continue
        try:
            returncode = run_calculix(deck, executable=spec.solver.executable, echo=echo)
        except (FileNotFoundError, OSError) as exc:
            raise CaseError(str(exc)) from exc
        if returncode != 0:
            raise CaseError(
                f"CalculiX failed for load case {load.name!r} with exit code {returncode}; "
                f"see {solve_dir / 'calculix.log'}"
            )
        try:
            report = write_solve_report(spec, load, solve_dir, returncode=returncode)
        except (ValueError, FileNotFoundError) as exc:
            raise CaseError(f"could not parse load case {load.name!r}: {exc}") from exc
        reports[load.name] = report
        artifacts[f"solve_report:{load.name}"] = str(solve_dir / "solve_report.json")
    return StageResult(
        stage="solve",
        status="dry_run" if dry_run else "ok",
        artifacts=artifacts,
        details={"load_cases": reports, "solver": "calculix"},
    )


def _stage_physics(
    spec: CaseSpec,
    workdir: Path,
    *,
    dry_run: bool,
    echo: Callable[[str], None] | None,
) -> StageResult:
    enabled = any(
        (
            spec.analyses.modal.enabled,
            spec.analyses.buckling.enabled,
            spec.analyses.nonlinear.enabled,
        )
    )
    if not enabled:
        return StageResult(
            stage="physics", status="skipped", details={"reason": "no advanced analyses enabled"}
        )
    if dry_run:
        return StageResult(
            stage="physics",
            status="skipped",
            details={"reason": "dry run does not execute advanced solvers"},
        )
    mesh_include = workdir / "mesh" / "wingbox_mesh.inp"
    if not mesh_include.is_file():
        raise CaseError(f"physics stage requires {mesh_include}; run mesh first")
    for load in spec.loads:
        if not (workdir / "solve" / load.name / "solve_report.json").is_file():
            raise CaseError("physics stage requires completed linear-static load cases")
    mesh = _build_mesh(spec, workdir)
    physics_spec = spec
    physics_include = mesh_include
    reference_root: Path | None = None
    topology_note = "advanced analyses use the governed structural mesh"
    rich_topology = bool(
        spec.wingbox.rib_span_fractions
        or spec.wingbox.cutouts
        or spec.wingbox.hinge_from_design_vector
    )
    if rich_topology and spec.analyses.reduced_topology_for_advanced:
        clean_wingbox = replace(
            spec.wingbox,
            rib_span_fractions=(),
            cutouts=(),
            hinge_from_design_vector=False,
            hinge_span_start_fraction=0.0,
            hinge_span_end_fraction=0.0,
        )
        physics_spec = replace(spec, wingbox=clean_wingbox)
        physics_mesh = _build_mesh(physics_spec, workdir)
        clean_mesh_dir = workdir / "physics" / "reduced_mesh"
        mesh_artifacts = write_mesh_artifacts(physics_mesh, clean_mesh_dir)
        physics_mesh = _build_mesh(physics_spec, workdir)
        physics_include = Path(mesh_artifacts["calculix_mesh"])
        reference_root = workdir / "solve_reduced"
        for load in spec.loads:
            solve_dir = reference_root / load.name
            deck = write_calculix_deck(
                physics_spec, load, physics_mesh, physics_include, solve_dir
            )
            returncode = run_calculix(deck, executable=spec.solver.executable, echo=echo)
            if returncode != 0:
                raise CaseError(f"reduced-topology reference solve failed for {load.name!r}")
            write_solve_report(physics_spec, load, solve_dir, returncode=returncode)
        topology_note = (
            "advanced analyses use a reduced closed-box topology because CalculiX "
            "2.21 nonlinear/buckling shell MPCs are not qualified for intersecting "
            "rib/cut-out knots; primary static results remain on the rich mesh"
        )
    try:
        report = run_physics_analyses(
            physics_spec,
            physics_mesh if rich_topology and spec.analyses.reduced_topology_for_advanced else mesh,
            physics_include,
            workdir / "physics",
            echo=echo,
            reference_root=reference_root,
            topology_note=topology_note,
        )
    except (ValueError, OSError, FileNotFoundError) as exc:
        raise CaseError(f"advanced structural analysis rejected: {exc}") from exc
    path = workdir / "physics" / "physics_report.json"
    return StageResult(
        stage="physics",
        status="ok" if report["status"] == "pass" else "failed",
        artifacts={"physics_report": str(path)},
        details=report,
    )


def _stage_post(spec: CaseSpec, workdir: Path, *, dry_run: bool) -> StageResult:
    if dry_run:
        return StageResult(
            stage="post", status="skipped", details={"reason": "dry run has no solver results"}
        )
    mesh_report_path = workdir / "mesh" / "mesh_report.json"
    if not mesh_report_path.is_file():
        raise CaseError("post stage requires mesh_report.json")
    mesh_report = json.loads(mesh_report_path.read_text(encoding="utf-8"))
    mass = float(mesh_report["full_structural_mass_kg"])
    load_reports: dict[str, object] = {}
    failures: list[str] = []
    if spec.openaerostruct_validation.enabled:
        validation_path = workdir / "validation" / "openaerostruct_validation.json"
        if not validation_path.is_file():
            raise CaseError(f"post stage requires {validation_path}")
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        if validation.get("status") != "pass":
            failures.append("openaerostruct_validation")
    advanced_enabled = any(
        (
            spec.analyses.modal.enabled,
            spec.analyses.buckling.enabled,
            spec.analyses.nonlinear.enabled,
        )
    )
    if advanced_enabled:
        physics_path = workdir / "physics" / "physics_report.json"
        if not physics_path.is_file():
            raise CaseError(f"post stage requires {physics_path}")
        physics = json.loads(physics_path.read_text(encoding="utf-8"))
        if physics.get("status") != "pass":
            failures.append("advanced_physics")
    for load in spec.loads:
        report_path = workdir / "solve" / load.name / "solve_report.json"
        if not report_path.is_file():
            raise CaseError(f"post stage requires {report_path}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        safety = float(report["safety_factor_yield"])
        displacement = float(report["max_displacement_m"])
        checks = {
            "solver_converged": report.get("status") == "converged",
            "minimum_safety_factor": safety >= spec.verification.minimum_safety_factor,
            "maximum_displacement_m": (
                True
                if spec.verification.maximum_displacement_m is None
                else displacement <= spec.verification.maximum_displacement_m
            ),
        }
        for check, passed in checks.items():
            if not passed:
                failures.append(f"{load.name}:{check}")
        load_reports[load.name] = {"checks": checks, **report}
    mass_ok = (
        True
        if spec.verification.maximum_mass_kg is None
        else mass <= spec.verification.maximum_mass_kg
    )
    if not mass_ok:
        failures.append("maximum_mass_kg")
    payload = {
        "schema": "aeris.fea.verification.v1",
        "status": "pass" if not failures else "fail",
        "full_structural_mass_kg": mass,
        "mass_check": mass_ok,
        "loads": load_reports,
        "failures": failures,
    }
    path = workdir / "verification.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return StageResult(
        stage="post",
        status="ok" if not failures else "failed",
        artifacts={"verification": str(path)},
        details=payload,
    )


def _stage_qualify(spec: CaseSpec, workdir: Path) -> StageResult:
    try:
        payload = run_qualification(spec, workdir / "qualification_report.json")
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise CaseError(f"qualification gate rejected: {exc}") from exc
    return StageResult(
        stage="qualify",
        status="ok" if payload["status"] in {"pass", "not_applicable"} else "failed",
        artifacts={"qualification": str(workdir / "qualification_report.json")},
        details=payload,
    )


def _write_manifest(spec: CaseSpec, workdir: Path, results: list[StageResult]) -> Path:
    stages: dict[str, object] = {}
    for result in results:
        hashes = {
            label: file_sha256(path)
            for label, path in result.artifacts.items()
            if Path(path).is_file()
        }
        stages[result.stage] = {
            "status": result.status,
            "artifacts": result.artifacts,
            "sha256": hashes,
            "details": result.details,
        }
    payload = {
        "schema": CASE_MANIFEST_SCHEMA_VERSION,
        "case": spec.name,
        "case_yaml": str(spec.source_path) if spec.source_path else None,
        "case_yaml_sha256": (
            file_sha256(spec.source_path)
            if spec.source_path and Path(spec.source_path).is_file()
            else None
        ),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "open_source_stack": {
            "mesh_format": "Gmsh 2.2",
            "solver": "CalculiX",
            "aerodynamic_comparison": (
                "OpenAeroStruct" if spec.openaerostruct_validation.enabled else None
            ),
        },
        "stages": stages,
    }
    path = workdir / "case_manifest.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_case(
    spec: CaseSpec,
    *,
    workdir: Path,
    stages: tuple[str, ...] = STAGES,
    dry_run: bool = False,
    echo: Callable[[str], None] | None = None,
) -> dict[str, StageResult]:
    unknown = [stage for stage in stages if stage not in STAGES]
    if unknown:
        raise CaseError(f"unknown stages {unknown}; valid stages are {list(STAGES)}")
    ordered = [stage for stage in STAGES if stage in stages]
    say = echo or (lambda _message: None)
    run_dir = workdir.expanduser().resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    results: list[StageResult] = []
    for stage in ordered:
        say(f"[fea {spec.name}] {stage}{' (dry run)' if dry_run and stage == 'solve' else ''}")
        if stage == "geometry":
            results.append(_stage_geometry(spec, run_dir))
        elif stage == "validate":
            results.append(_stage_validate(spec, run_dir))
        elif stage == "mesh":
            results.append(_stage_mesh(spec, run_dir))
        elif stage == "solve":
            results.append(_stage_solve(spec, run_dir, dry_run=dry_run, echo=echo))
        elif stage == "physics":
            results.append(
                _stage_physics(spec, run_dir, dry_run=dry_run, echo=echo)
            )
        elif stage == "qualify":
            results.append(_stage_qualify(spec, run_dir))
        else:
            results.append(_stage_post(spec, run_dir, dry_run=dry_run))
    manifest = _write_manifest(spec, run_dir, results)
    say(f"[fea {spec.name}] manifest: {manifest}")
    return {result.stage: result for result in results}
