"""
Case execution: per-stage runs with per-stage artifact manifests.

Runs are isolated: input surface meshes are copied into the case workdir
before extrusion, so reference meshes are never mutated and every artifact
a run produced sits under one directory with a chained manifest
(``case_manifest.json``, schema ``aeris.cfd.case_manifest.v1``) linking
stage outputs by sha256 — the audit trail for the thesis.

``dry_run=True`` prepares everything a real run would need (resolved
options JSON, provenance manifest, static runner script) without touching
external tools — this is what unit tests and ``aeris cfd run --dry-run``
exercise.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from aeris.cfd.case.spec import CaseSpec, VolumeMeshSpec
from aeris.cfd.meshing.pyhyp_extrude import (
    resolve_characteristic_length,
    run_pyhyp_subprocess,
    write_pyhyp_run_inputs,
)
from aeris.cfd.meshing.pyhyp_options import DEFAULT_LEVEL, build_pyhyp_options
from aeris.cfd.options.layers import OptionLayer
from aeris.cfd.presets.registry import get_preset
from aeris.common.config import file_sha256

CASE_MANIFEST_SCHEMA_VERSION = "aeris.cfd.case_manifest.v1"

STAGES = ("surface", "volume", "solve", "post")

SURFACE_INPUT_FILES = ("surface.fmt", "surface_report.json")


@dataclass(frozen=True)
class StageResult:
    stage: str
    status: str  # "ok" | "dry_run" | "skipped"
    artifacts: dict[str, str] = field(default_factory=dict)
    details: dict[str, object] = field(default_factory=dict)


class CaseError(ValueError):
    """A case cannot be executed as specified."""


def _stage_surface(spec: CaseSpec, workdir: Path) -> StageResult:
    """Stage the surface mesh into the case workdir.

    2-D airfoil cases are generated in-core (pure numpy topologies); wing
    surfaces are geometry-coupled and must be pre-built (standalone
    ``surface_dir`` or the AERIS CLI layer resolving ``aeris_config``) —
    the core copies them in isolated.
    """
    core_source = spec.geometry.airfoil or spec.geometry.cad
    if core_source is not None:
        # local import: registry loads topology plugins lazily
        from aeris.cfd.meshing.registry import get_topology

        surface_spec = spec.surface_mesh
        default_topology = (
            "airfoil_ogrid_v1" if spec.geometry.airfoil is not None else "cad_gmsh_tet_v1"
        )
        topology_id = (
            surface_spec.topology
            if surface_spec is not None and surface_spec.topology
            else default_topology
        )
        params = dict(surface_spec.overrides) if surface_spec is not None else {}
        generator = get_topology(topology_id)
        surface_dir = workdir / "surface"
        try:
            report = generator.generate(core_source, surface_dir, params)
        except (ValueError, FileNotFoundError) as exc:
            raise CaseError(f"surface stage ({topology_id}): {exc}") from exc
        artifacts = {"surface_report.json": str(surface_dir / "surface_report.json")}
        for name in ("surface.fmt", "mesh.su2"):
            if (surface_dir / name).is_file():
                artifacts[name] = str(surface_dir / name)
        return StageResult(
            stage="surface",
            status="ok",
            artifacts=artifacts,
            details={
                "topology": topology_id,
                "source": str(core_source),
                "mode": "generated",
                "final_mesh": bool(report.get("final_mesh", False)),
                "quality": report.get("quality", {}),
            },
        )

    source = spec.geometry.surface_dir
    if source is None:
        raise CaseError(
            "case.geometry.aeris_config requires the AERIS CLI layer "
            "(aeris cfd run) to build the surface mesh first — the aeris.cfd "
            "core only consumes pre-built surface directories."
        )
    source = source.expanduser().resolve()
    missing = [name for name in SURFACE_INPUT_FILES if not (source / name).is_file()]
    if missing:
        raise CaseError(f"case.geometry.surface_dir {source} is missing {missing}")

    surface_dir = workdir / "surface"
    surface_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}
    for name in SURFACE_INPUT_FILES:
        target = surface_dir / name
        if source / name != target:
            shutil.copy2(source / name, target)
        artifacts[name] = str(target)
    return StageResult(
        stage="surface",
        status="ok",
        artifacts=artifacts,
        details={"source": str(source), "mode": "staged_copy"},
    )


def _volume_layers(volume: VolumeMeshSpec) -> tuple[str, list[OptionLayer]]:
    """Resolve grid level and preset/config layers for the volume stage."""
    extra_layers: list[OptionLayer] = []
    level = volume.level
    if volume.preset is not None:
        preset = get_preset(volume.preset)
        policy = {k: v for k, v in preset.volume.items() if k != "level"}
        if policy:
            extra_layers.append(OptionLayer(f"preset:{preset.name}", policy))
        if level is None:
            preset_level = preset.volume.get("level")
            level = str(preset_level) if preset_level is not None else None
    if level is None:
        level = DEFAULT_LEVEL
    if volume.overrides:
        extra_layers.append(OptionLayer("config", dict(volume.overrides)))
    return level, extra_layers


def _stage_volume(spec: CaseSpec, workdir: Path, *, dry_run: bool) -> StageResult:
    volume = spec.volume_mesh
    if volume is None:
        return StageResult(stage="volume", status="skipped", details={"reason": "not specified"})

    surface_dir = (workdir / "surface").resolve()
    if not (surface_dir / "surface.fmt").is_file():
        raise CaseError(
            f"volume stage requires a staged surface mesh in {surface_dir} — "
            "run the surface stage first."
        )

    level, extra_layers = _volume_layers(volume)

    # Topology-required options (e.g. dimension: 2d for airfoil O-grids) come
    # from the surface report as a provenance-tracked layer below preset/config.
    report_path = surface_dir / "surface_report.json"
    if report_path.is_file():
        surface_report = json.loads(report_path.read_text(encoding="utf-8"))
        hints = surface_report.get("pyhyp_hints")
        if isinstance(hints, dict) and hints:
            extra_layers.insert(0, OptionLayer("topology", dict(hints)))

    characteristic_length = resolve_characteristic_length(surface_dir)
    effective = build_pyhyp_options(
        surface_dir / "surface.fmt",
        level=level,
        characteristic_length=characteristic_length,
        output_file=surface_dir / f"wing_vol_{level}.cgns",
        march_dist_factor=(
            volume.march_dist_factor if volume.march_dist_factor is not None else 25.0
        ),
        extra_layers=extra_layers,
        pyhyp_options=volume.raw_options or None,
    )

    if dry_run:
        runner = write_pyhyp_run_inputs(surface_dir, effective)
        return StageResult(
            stage="volume",
            status="dry_run",
            artifacts={
                "pyhyp_options": str(surface_dir / "pyhyp_options.json"),
                "effective_options": str(surface_dir / "pyhyp_effective_options.json"),
                "runner": str(runner),
            },
            details={"level": level, "provenance_warnings": list(effective.warnings)},
        )

    report = run_pyhyp_subprocess(surface_dir, effective)
    return StageResult(
        stage="volume",
        status="ok",
        artifacts={
            "volume_cgns": str(report["output_cgns"]),
            "volume_report": str(surface_dir / "volume_report.json"),
            "effective_options": str(report["effective_options"]),
        },
        details={
            "level": level,
            "quality_warning": report.get("quality_warning"),
            "elapsed_seconds": report.get("elapsed_seconds"),
        },
    )


def _find_volume_mesh(surface_dir: Path) -> Path:
    """Newest solvable mesh: pyHyp CGNS volumes first, else final .su2 meshes.

    Unstructured topologies (Gmsh backend) produce the final mesh directly
    in the surface stage — there is no volume stage for them.
    """
    candidates = sorted(
        (path for path in surface_dir.glob("wing_vol_*.cgns") if ".invalid" not in path.name),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        candidates = sorted(
            surface_dir.glob("*.su2"), key=lambda p: p.stat().st_mtime, reverse=True
        )
    if not candidates:
        raise CaseError(
            f"solve stage requires a mesh (wing_vol_*.cgns or *.su2) in "
            f"{surface_dir} — run the surface/volume stages first."
        )
    return candidates[0]


# back-compat alias (pre-Gmsh-backend name)
_find_volume_cgns = _find_volume_mesh


def _stage_solve(
    spec: CaseSpec,
    workdir: Path,
    *,
    dry_run: bool,
    echo: Callable[[str], None] | None = None,
) -> StageResult:
    solve = spec.solve
    if solve is None:
        return StageResult(stage="solve", status="skipped", details={"reason": "not specified"})

    # local import: keeps case loading independent of solver modules
    import dataclasses

    from aeris.cfd.solvers.base import get_solver_adapter

    mesh_cgns = _find_volume_cgns(workdir / "surface")

    # Topology-required solver options (e.g. lift_index=2 for x-y airfoil
    # strips) come from the surface report; explicit case overrides win.
    report_path = workdir / "surface" / "surface_report.json"
    if report_path.is_file():
        surface_report = json.loads(report_path.read_text(encoding="utf-8"))
        hints = surface_report.get(f"{solve.solver}_hints")
        if isinstance(hints, dict) and hints:
            solve = dataclasses.replace(solve, overrides={**hints, **solve.overrides})

    adapter = get_solver_adapter(solve.solver)
    try:
        prepared = adapter.prepare(solve, mesh_cgns, workdir / "solve")
    except (ValueError, FileNotFoundError) as exc:
        raise CaseError(f"solve stage: {exc}") from exc

    if dry_run:
        return StageResult(
            stage="solve",
            status="dry_run",
            artifacts=dict(prepared.artifacts),
            details={"solver": solve.solver, "command": list(prepared.command)},
        )

    returncode = adapter.run(prepared, stream=echo)
    report = adapter.parse(prepared.workdir)
    status = report.status if returncode == 0 else "failed"
    verification = _write_verification_block(
        workdir, prepared.workdir, mesh_cgns, report, returncode
    )
    return StageResult(
        stage="solve",
        status=status,
        artifacts={
            "solve_report": str(prepared.workdir / "solve_report.json"),
            "verification": str(verification),
            "log": str(prepared.workdir / prepared.log_name),
            **dict(prepared.artifacts),
        },
        details={
            "solver": solve.solver,
            "returncode": returncode,
            "forces": dict(report.forces),
            "final_resrho": report.convergence.get("final_resrho"),
        },
    )


def _write_verification_block(
    workdir: Path,
    solve_dir: Path,
    mesh_cgns: Path,
    report: object,
    returncode: int,
) -> Path:
    """Solution-verification metadata (schema aeris.cfd.verification.v1).

    The quality tag a CFD-derived training row carries into the ML trust
    chain: iterative-convergence evidence, mesh QC summary, and the sha256
    chain (mesh -> solve report) — so surrogate datasets can gate/weight on
    verification status instead of trusting every solve equally (NASA CFD
    Vision 2030 ML+UQ integration; AIAA V&V practice).
    """
    volume_report_path = workdir / "surface" / "volume_report.json"
    mesh_block: dict[str, object] = {"cgns_sha256": None, "march_status": None}
    if mesh_cgns.is_file():
        mesh_block["cgns_sha256"] = file_sha256(mesh_cgns)
    if volume_report_path.is_file():
        volume_report = json.loads(volume_report_path.read_text(encoding="utf-8"))
        march = volume_report.get("march_metrics", {}) or {}
        mesh_block.update(
            {
                "march_status": volume_report.get("status"),
                "min_quality": march.get("min_quality"),
                "quality_warning": march.get("quality_warning"),
                "low_quality_layers": march.get("low_quality_layers"),
            }
        )
    convergence = getattr(report, "convergence", {}) or {}
    payload = {
        "schema": "aeris.cfd.verification.v1",
        "iterative": {
            "status": getattr(report, "status", None),
            "returncode": returncode,
            "iterations": convergence.get("iterations"),
            "orders_dropped": convergence.get("orders_dropped"),
            "final_resrho": convergence.get("final_resrho", convergence.get("final_resrho_log10")),
        },
        "mesh": mesh_block,
        "solve_report_sha256": (
            file_sha256(solve_dir / "solve_report.json")
            if (solve_dir / "solve_report.json").is_file()
            else None
        ),
    }
    path = solve_dir / "verification.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _stage_post(spec: CaseSpec, workdir: Path) -> StageResult:
    """Summarize the solve into post/solve_summary.json (+ mesh QC echo)."""
    # local import keeps case loading light
    from aeris.cfd.post.reports import solve_summary

    solve_report = workdir / "solve" / "solve_report.json"
    if not solve_report.is_file():
        raise CaseError(f"post stage requires {solve_report} — run the solve stage first.")
    post_dir = workdir / "post"
    post_dir.mkdir(parents=True, exist_ok=True)
    summary = solve_summary([solve_report], labels=[spec.name])
    summary_path = post_dir / "solve_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    row = summary["rows"][0]
    return StageResult(
        stage="post",
        status="ok",
        artifacts={"solve_summary": str(summary_path)},
        details={"status": row["status"], "forces": row["forces"]},
    )


def _write_case_manifest(spec: CaseSpec, workdir: Path, results: list[StageResult]) -> Path:
    stages_payload: dict[str, object] = {}
    for result in results:
        fingerprints = {
            label: file_sha256(path) if Path(path).is_file() else None
            for label, path in result.artifacts.items()
        }
        stages_payload[result.stage] = {
            "status": result.status,
            "artifacts": result.artifacts,
            "artifact_sha256": fingerprints,
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
        "stages": stages_payload,
    }
    path = workdir / "case_manifest.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_case(
    spec: CaseSpec,
    *,
    workdir: Path,
    stages: tuple[str, ...] = ("surface", "volume"),
    dry_run: bool = False,
    echo: Callable[[str], None] | None = None,
) -> dict[str, StageResult]:
    """Execute the requested stages in canonical order; write the manifest."""
    say = echo or (lambda _msg: None)
    unknown = [s for s in stages if s not in STAGES]
    if unknown:
        raise CaseError(f"unknown stages {unknown}; valid: {list(STAGES)}")
    ordered = [s for s in STAGES if s in stages]

    workdir = workdir.expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    results: list[StageResult] = []
    for stage in ordered:
        if stage == "surface":
            say(f"[case {spec.name}] surface: staging input mesh ...")
            results.append(_stage_surface(spec, workdir))
        elif stage == "volume":
            say(f"[case {spec.name}] volume: pyHyp extrusion{' (dry run)' if dry_run else ''} ...")
            results.append(_stage_volume(spec, workdir, dry_run=dry_run))
        elif stage == "solve":
            say(
                f"[case {spec.name}] solve: {spec.solve.solver if spec.solve else 'skipped'}"
                f"{' (dry run)' if dry_run else ''} ..."
            )
            results.append(_stage_solve(spec, workdir, dry_run=dry_run, echo=echo))
        elif stage == "post":
            say(f"[case {spec.name}] post: summarizing ...")
            results.append(_stage_post(spec, workdir))

    manifest = _write_case_manifest(spec, workdir, results)
    say(f"[case {spec.name}] manifest: {manifest}")
    return {result.stage: result for result in results}
