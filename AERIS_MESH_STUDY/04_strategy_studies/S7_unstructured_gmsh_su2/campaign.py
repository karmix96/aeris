"""Fail-closed orchestration for the preregistered S7 Gmsh/SU2 study.

This module deliberately owns scheduling only: geometry, meshing, auditing and
SU2 remain independent artifact-producing stages.  It never launches production
or holdout work, and it never mutates an existing attempt directory.
"""

from __future__ import annotations

import math
import os
import re
import resource
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from .common import (
    POLICY_PATH,
    SUMMARY_SCHEMA,
    canonical_json,
    digest_manifest,
    enforce_resource_safety,
    load_policy,
    read_json,
    require_development_set,
    sha256_bytes,
    sha256_file,
    source_digest,
    verify_digest_manifest,
    verify_pinned_versions,
    write_json,
)
from .geometry import build_and_write_surface, load_surface
from .gmsh_pipeline import estimate_cells, generate_mesh, resolved_mesh_spec
from .mesh_audit import audit_mesh
from .su2_pipeline import run_su2_pipeline

CAMPAIGN_SCHEMA = "aeris.s7.campaign.v1"
CASE_TERMINAL_SCHEMA = "aeris.s7.case_terminal.v1"
MESH_FLOW_ID = "mesh"
BASELINE_FLOW_ID = "cruise"


def _safe(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._")
    if not result:
        raise ValueError(f"unsafe identifier: {value!r}")
    return result


def case_id(index: int, level: str, te_variant: str, flow_id: str = MESH_FLOW_ID) -> str:
    if index < 0:
        raise ValueError("index must be non-negative")
    return f"dev_{index:03d}__{_safe(level)}__{_safe(te_variant)}__{_safe(flow_id)}"


def plan_case(
    *,
    set_name: str,
    index: int,
    level: str,
    te_variant: str,
    output: Path,
    flow_id: str = MESH_FLOW_ID,
) -> dict[str, Any]:
    """Return a toolchain-free plan.  This is safe on laptops and CI."""
    require_development_set(set_name)
    policy = load_policy()
    development_count = int(policy["campaign_readiness"]["development_meshes_total"])
    if index < 0 or index >= development_count:
        raise IndexError(f"development index must be in [0, {development_count})")
    if level != "laptop_smoke" and level not in policy["grid_family"]["levels"]:
        raise KeyError(f"unknown S7 level: {level}")
    if te_variant not in policy["geometry"]["trailing_edge_variants"]:
        raise KeyError(f"unknown S7 TE variant: {te_variant}")
    evidence = "laptop_smoke" if level == "laptop_smoke" else "development"
    target = Path(output).resolve() / case_id(index, level, te_variant, flow_id)
    return {
        "schema": CAMPAIGN_SCHEMA,
        "mode": "plan_only",
        "case_id": case_id(index, level, te_variant, flow_id),
        "geometry_set": set_name,
        "method": "unstructured",
        "grid_level": level,
        "te_variant": te_variant,
        "flow_id": _safe(flow_id),
        "evidence_tier": evidence,
        "output": str(target),
        "mesh_retry_order": [item["id"] for item in policy["gmsh"]["retries"]],
        "cfd_policy": "only_after_accepted_mesh_audit",
        "holdout_guard": "enforced",
        "source_digest": source_digest(),
        "policy_sha256": sha256_file(POLICY_PATH),
    }


def _attempt_dir(root: Path, index: int, candidate_id: str) -> Path:
    return root / "mesh_attempts" / f"attempt_{index:03d}_{_safe(candidate_id)}"


def _write_attempt_terminal(attempt: Path, payload: Mapping[str, Any]) -> None:
    payload = dict(payload)
    write_json(attempt / "source_tree.json", {"source_digest": source_digest()})
    case_root = attempt.parents[1]
    paths = {
        "source_tree": attempt / "source_tree.json",
        "policy": POLICY_PATH,
        "resolved_config": attempt / "resolved_mesh_config.json",
        "geometry": case_root / "geometry" / "source_surface.npz",
        "geometry_report": case_root / "geometry" / "source_surface_report.json",
        "gmsh_report": attempt / "gmsh_build_report.json",
        "gmsh_log": attempt / "gmsh.log",
        "mesh_msh": attempt / "mesh.msh",
        "mesh": attempt / "mesh.su2",
        "mesh_audit": attempt / "mesh_audit.json",
    }
    required = {"source_tree", "policy", "resolved_config", "geometry", "gmsh_report", "gmsh_log"}
    if payload.get("state") in {"MESH_ACCEPTED", "MESH_REJECTED"}:
        required.update({"mesh_msh", "mesh", "mesh_audit"})
    manifest = digest_manifest(paths, required=required)
    verification = verify_digest_manifest(manifest)
    payload.update(
        {
            "schema": CAMPAIGN_SCHEMA,
            "source_digest": source_digest(),
            "policy_sha256": sha256_file(POLICY_PATH),
            "artifact_manifest": manifest,
            "artifact_verification": verification,
        }
    )
    write_json(attempt / "campaign_terminal.json", payload)


def _load_mesh_attempt(
    attempt: Path, expected_spec: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    terminal_path = attempt / "campaign_terminal.json"
    if not terminal_path.is_file():
        raise RuntimeError(f"preserved incomplete mesh attempt: {attempt}")
    terminal = read_json(terminal_path)
    if terminal.get("source_digest") != source_digest():
        raise RuntimeError(f"source digest changed since mesh attempt: {attempt}")
    if terminal.get("policy_sha256") != sha256_file(POLICY_PATH):
        raise RuntimeError(f"policy digest changed since mesh attempt: {attempt}")
    verification = verify_digest_manifest(terminal["artifact_manifest"])
    if not verification["passed"]:
        raise RuntimeError(
            f"mesh attempt artifact verification failed for {attempt}: {verification['mismatches']}"
        )
    resolved = read_json(attempt / "resolved_mesh_config.json")
    if canonical_json(resolved) != canonical_json(expected_spec):
        raise RuntimeError(f"mesh attempt resolved specification differs from case plan: {attempt}")
    build = read_json(attempt / "gmsh_build_report.json")
    audit = (
        read_json(attempt / "mesh_audit.json")
        if (attempt / "mesh_audit.json").is_file()
        else terminal.get("audit", {"acceptance": {"accepted": False}})
    )
    return build, audit


def _validate_existing_geometry(surface_path: Path, plan: Mapping[str, Any]) -> Any:
    report_path = surface_path.with_name("source_surface_report.json")
    if not report_path.is_file():
        raise RuntimeError(f"existing geometry lacks report: {surface_path}")
    surface = load_surface(surface_path, report_path)
    metadata = surface.metadata
    expected = {
        "geometry_set": plan["geometry_set"],
        "development_index": int(plan["case_id"].split("__", 1)[0].removeprefix("dev_")),
        "level": plan["grid_level"],
        "te_variant": plan["te_variant"],
    }
    observed = {name: metadata.get(name) for name in expected}
    if observed != expected:
        raise RuntimeError(
            f"existing geometry identity differs from case plan: {observed!r} != {expected!r}"
        )
    if not metadata.get("accepted_pre_gmsh", False):
        raise RuntimeError("existing geometry did not pass the pre-Gmsh gates")
    if metadata.get("source_digest") != source_digest():
        raise RuntimeError("existing geometry source digest differs from current implementation")
    if metadata.get("policy_sha256") != sha256_file(POLICY_PATH):
        raise RuntimeError("existing geometry policy digest differs from current policy")
    return surface


def _resource_preflight(attempt: Path, *, tier: str, estimated_cells: int) -> dict[str, Any]:
    """Persist a preflight report even when the policy deliberately refuses it."""
    attempt.parent.mkdir(parents=True, exist_ok=True)
    path = attempt.with_name(f"{attempt.name}.resource_preflight.json")
    if path.is_file():
        report = read_json(path)
        identity = {
            "evidence_tier": tier,
            "estimated_cells": int(estimated_cells),
            "source_digest": source_digest(),
            "policy_sha256": sha256_file(POLICY_PATH),
        }
        if any(report.get(name) != value for name, value in identity.items()):
            raise RuntimeError(f"stale resource preflight: {path}")
    else:
        report = enforce_resource_safety(
            evidence_tier=tier,
            output_path=attempt.parent,
            estimated_cells=estimated_cells,
            raise_on_failure=False,
        )
        report.update(
            {
                "source_digest": source_digest(),
                "policy_sha256": sha256_file(POLICY_PATH),
            }
        )
        write_json(path, report)
    if not report.get("passed", False):
        # S7_RESOURCE_PREFLIGHT_OVERRIDE runs the case anyway on an operator's
        # explicit instruction, to measure what a machine below the floor actually
        # does rather than assume it.  It moves no threshold: the written report
        # still carries passed=false and the full failure list, and gains an
        # explicit evidence_valid_for_campaign=false, so anything produced under
        # it is self-evidently outside the declared resource scope and cannot be
        # presented as campaign evidence.  Absent the variable, this still raises.
        if os.environ.get("S7_RESOURCE_PREFLIGHT_OVERRIDE") != "1":
            raise RuntimeError(
                "resource preflight failed: " + ", ".join(report.get("failures", []))
            )
        report["override_acknowledged"] = True
        report["evidence_valid_for_campaign"] = False
        write_json(path, report)
    return report


def _write_case_terminal(root: Path, result: Mapping[str, Any]) -> None:
    paths = {
        "case_result": root / "case_result.json",
        "geometry": root / "geometry" / "source_surface.npz",
        "geometry_report": root / "geometry" / "source_surface_report.json",
        "policy": POLICY_PATH,
        "software_version_preflight": Path(str(result["provenance"]["software_version_preflight"])),
    }
    for index, attempt in enumerate(result["gate_results"]["mesh_attempts"]):
        paths[f"mesh_attempt_terminal_{index:03d}"] = (
            Path(str(attempt["path"])) / "campaign_terminal.json"
        )
    if result["gate_results"].get("cfd") is not None:
        paths["su2_pipeline_terminal"] = root / "su2_attempts" / "pipeline_terminal.json"
    manifest = digest_manifest(paths, required=paths)
    terminal = {
        "schema": CASE_TERMINAL_SCHEMA,
        "case_id": result["case_id"],
        "source_digest": source_digest(),
        "policy_sha256": sha256_file(POLICY_PATH),
        "accepted": result["accepted"],
        "acceptance_scope": result["acceptance_scope"],
        "artifact_manifest": manifest,
        "artifact_verification": verify_digest_manifest(manifest),
    }
    write_json(root / "case_terminal.json", terminal)


def _load_case_terminal(root: Path, plan: Mapping[str, Any]) -> dict[str, Any] | None:
    path = root / "case_terminal.json"
    if not path.is_file():
        if (root / "case_result.json").is_file():
            raise RuntimeError("case result exists without a terminal manifest")
        return None
    terminal = read_json(path)
    if terminal.get("schema") != CASE_TERMINAL_SCHEMA or terminal.get("case_id") != plan["case_id"]:
        raise RuntimeError(f"case terminal identity mismatch: {path}")
    if terminal.get("source_digest") != source_digest() or terminal.get(
        "policy_sha256"
    ) != sha256_file(POLICY_PATH):
        raise RuntimeError("existing case terminal is not compatible with current source/policy")
    verification = verify_digest_manifest(terminal.get("artifact_manifest", {}))
    if not verification["passed"]:
        raise RuntimeError(
            f"case terminal digest verification failed: {verification['mismatches']}"
        )
    result = read_json(root / "case_result.json")
    if result.get("case_id") != plan["case_id"]:
        raise RuntimeError("case result identity differs from terminal/plan")
    return result


def _resolved_flow(
    policy: Mapping[str, Any],
    *,
    requested: Mapping[str, Any] | None,
    flow_id: str,
    run_cfd: bool,
) -> dict[str, Any]:
    if not run_cfd:
        if flow_id != MESH_FLOW_ID:
            raise ValueError(f"mesh-only cases must use flow_id={MESH_FLOW_ID!r}")
        if requested is not None:
            raise ValueError("mesh-only execution must not supply a flow mapping")
        return {}
    baseline = dict(policy["flow_conditions"]["baseline"])
    if flow_id not in {MESH_FLOW_ID, str(baseline["flow_id"])}:
        raise ValueError(f"S7 CFD is frozen to flow_id={baseline['flow_id']!r}; got {flow_id!r}")
    candidate = baseline if requested is None else dict(requested)
    required = set(policy["flow_conditions"]["required_fields"])
    if set(candidate) != required:
        raise ValueError(
            f"flow mapping must contain exactly {sorted(required)}; got {sorted(candidate)}"
        )
    for name in required:
        expected = baseline[name]
        actual = candidate[name]
        if isinstance(expected, str):
            matched = str(actual) == expected
        else:
            matched = math.isfinite(float(actual)) and float(actual) == float(expected)
        if not matched:
            raise ValueError(f"flow.{name} is frozen to {expected!r}; got {actual!r}")
    return candidate


def _software_preflight(root: Path, *, require_su2: bool) -> tuple[dict[str, Any], Path]:
    report = verify_pinned_versions(require_su2=require_su2, raise_on_mismatch=False)
    directory = root / "software_preflights"
    directory.mkdir(parents=True, exist_ok=True)
    indices = [
        int(path.stem.rsplit("_", 1)[1])
        for path in directory.glob("preflight_*.json")
        if path.stem.rsplit("_", 1)[-1].isdigit()
    ]
    path = directory / f"preflight_{max(indices, default=-1) + 1:03d}.json"
    write_json(
        path,
        {
            "schema": CAMPAIGN_SCHEMA,
            "source_digest": source_digest(),
            "policy_sha256": sha256_file(POLICY_PATH),
            "report": report,
        },
    )
    if not report["passed"]:
        raise RuntimeError("software version preflight failed: " + "; ".join(report["mismatches"]))
    return report, path


def _references(surface: Any, supplied: Mapping[str, Any] | None) -> dict[str, Any]:
    values = surface.metadata["reference_values"]
    area = values.get(
        "area_m2",
        values.get("reference_area_m2", values.get("wing_area_m2")),
    )
    chord = values.get("mean_aerodynamic_chord_m")
    if area is None or chord is None:
        raise ValueError("references must supply area_ref and chord_ref for this geometry")
    canonical = {
        "area_ref": float(area),
        "chord_ref": float(chord),
        "moment_origin": (0.0, 0.0, 0.0),
    }
    if supplied is None:
        return canonical
    candidate = dict(supplied)
    if set(candidate) != set(canonical):
        raise ValueError("references must contain exactly area_ref, chord_ref, and moment_origin")
    try:
        normalized = {
            "area_ref": float(candidate["area_ref"]),
            "chord_ref": float(candidate["chord_ref"]),
            "moment_origin": tuple(float(value) for value in candidate["moment_origin"]),
        }
    except (TypeError, ValueError) as exc:
        raise ValueError("references must contain finite numeric values") from exc
    if len(normalized["moment_origin"]) != 3 or not all(
        math.isfinite(value)
        for value in (
            normalized["area_ref"],
            normalized["chord_ref"],
            *normalized["moment_origin"],
        )
    ):
        raise ValueError("references must contain finite area/chord and three origin values")
    if normalized != canonical:
        raise ValueError(
            f"S7 reference quantities are frozen to the pyGeo full-wing values {canonical!r}"
        )
    return canonical


def run_case(
    *,
    set_name: str,
    index: int,
    level: str,
    te_variant: str,
    output: Path,
    flow: Mapping[str, Any] | None = None,
    references: Mapping[str, Any] | None = None,
    run_cfd: bool = False,
    timeout_s: float = 3600.0,
    solver_command: Sequence[str] = ("SU2_CFD",),
    flow_id: str = MESH_FLOW_ID,
) -> dict[str, Any]:
    """Execute a development/laptop case, preserving every retry and failure."""
    policy = load_policy()
    if not run_cfd and references is not None:
        raise ValueError("mesh-only execution must not supply CFD reference quantities")
    resolved_flow = _resolved_flow(policy, requested=flow, flow_id=flow_id, run_cfd=run_cfd)
    effective_flow_id = str(resolved_flow["flow_id"]) if run_cfd else MESH_FLOW_ID
    plan = plan_case(
        set_name=set_name,
        index=index,
        level=level,
        te_variant=te_variant,
        output=output,
        flow_id=effective_flow_id,
    )
    root = Path(plan["output"])
    root.mkdir(parents=True, exist_ok=True)
    completed = _load_case_terminal(root, plan)
    if completed is not None:
        return completed
    require_su2 = run_cfd and any(Path(str(part)).name == "SU2_CFD" for part in solver_command)
    software_report, software_preflight_path = _software_preflight(root, require_su2=require_su2)
    surface_path = root / "geometry" / "source_surface.npz"
    if surface_path.is_file():
        surface = _validate_existing_geometry(surface_path, plan)
    else:
        geometry_dir = root / "geometry"
        if (root / "geometry_failure.json").is_file():
            raise RuntimeError(f"preserved failed geometry attempt requires investigation: {root}")
        if geometry_dir.exists() and any(geometry_dir.iterdir()):
            raise RuntimeError(
                f"preserved incomplete geometry attempt requires investigation: {geometry_dir}"
            )
        try:
            _case, surface, _artifacts = build_and_write_surface(
                set_name=set_name,
                index=index,
                level=level,
                te_variant=te_variant,
                output_dir=geometry_dir,
            )
        except Exception as exc:
            write_json(
                root / "geometry_failure.json",
                {
                    "schema": CAMPAIGN_SCHEMA,
                    "state": "GEOMETRY_FAILED",
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                    "source_digest": source_digest(),
                    "policy_sha256": sha256_file(POLICY_PATH),
                },
            )
            raise
    geometry_digest = sha256_file(surface_path)
    resolved_references = (
        _references(surface, references) if run_cfd else _references(surface, None)
    )
    mesh_attempts: list[dict[str, Any]] = []
    mesh_wall_time_s = 0.0
    peak_rss_candidates: list[int] = []
    accepted_mesh: tuple[Path, Path] | None = None
    for candidate_index, candidate in enumerate(policy["gmsh"]["retries"]):
        attempt = _attempt_dir(root, candidate_index, candidate["id"])
        spec = resolved_mesh_spec(
            surface, level=level, candidate_index=candidate_index, policy=policy
        )
        resource_tier = (
            "production" if level in policy["grid_family"]["levels"] else plan["evidence_tier"]
        )
        preflight = _resource_preflight(
            attempt, tier=resource_tier, estimated_cells=estimate_cells(surface, spec, policy)
        )
        audit_path = attempt / "mesh_audit.json"
        existing_attempt = attempt.exists()
        terminal_written = False
        if existing_attempt:
            build, audit = _load_mesh_attempt(attempt, spec)
        else:
            try:
                build = generate_mesh(
                    surface,
                    output_dir=attempt,
                    level=level,
                    candidate_index=candidate_index,
                    policy=policy,
                )
                audit = audit_mesh(
                    msh_path=attempt / "mesh.msh",
                    su2_path=attempt / "mesh.su2",
                    surface=surface,
                    level=level,
                    candidate_index=candidate_index,
                    output_path=audit_path,
                    policy=policy,
                )
            except Exception as exc:
                build = (
                    read_json(attempt / "gmsh_build_report.json")
                    if (attempt / "gmsh_build_report.json").is_file()
                    else {"status": "failed"}
                )
                audit = {
                    "acceptance": {
                        "accepted": False,
                        "failures": [f"exception:{type(exc).__name__}"],
                    },
                    "exception": str(exc),
                }
                _write_attempt_terminal(
                    attempt,
                    {
                        "state": "MESH_FAILED",
                        "build": build,
                        "audit": audit,
                        "preflight": preflight,
                    },
                )
                terminal_written = True
        mesh_wall_time_s += float(build.get("wall_time_s", 0.0) or 0.0)
        if build.get("peak_process_rss_bytes") is not None:
            peak_rss_candidates.append(int(build["peak_process_rss_bytes"]))
        accepted = bool(audit.get("acceptance", {}).get("accepted", False))
        if accepted:
            if not existing_attempt:
                _write_attempt_terminal(
                    attempt,
                    {
                        "state": "MESH_ACCEPTED",
                        "build": build,
                        "audit": audit,
                        "preflight": preflight,
                    },
                )
            mesh_attempts.append(
                {
                    "path": str(attempt),
                    "candidate": candidate["id"],
                    "accepted": True,
                    "audit": audit,
                }
            )
            accepted_mesh = (attempt / "mesh.su2", audit_path)
            break
        state = "MESH_FAILED" if "exception" in audit else "MESH_REJECTED"
        if not existing_attempt and not terminal_written:
            _write_attempt_terminal(
                attempt, {"state": state, "build": build, "audit": audit, "preflight": preflight}
            )
        mesh_attempts.append(
            {"path": str(attempt), "candidate": candidate["id"], "accepted": False, "audit": audit}
        )
    cfd: dict[str, Any] | None = None
    if run_cfd and accepted_mesh is not None:
        cfd = run_su2_pipeline(
            attempts_root=root / "su2_attempts",
            mesh_path=accepted_mesh[0],
            flow=resolved_flow,
            references=resolved_references,
            geometry_set=set_name,
            evidence_tier=plan["evidence_tier"],
            timeout_s=timeout_s,
            solver_command=solver_command,
            input_artifacts={"geometry": surface_path, "mesh_audit": accepted_mesh[1]},
        )
    final = cfd.get("final_attempt", {}) if cfd else {}
    acceptance_scope = "mesh_and_cfd" if run_cfd else "mesh_only"
    cfd_attempts = cfd.get("attempts", []) if cfd else []
    cfd_wall_time_s = sum(
        float(attempt.get("run", {}).get("wall_time_s", 0.0) or 0.0) for attempt in cfd_attempts
    )
    peak_rss_candidates.extend(
        int(attempt["run"]["peak_process_tree_rss_bytes"])
        for attempt in cfd_attempts
        if attempt.get("run", {}).get("peak_process_tree_rss_bytes") is not None
    )
    peak_rss_candidates.append(int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024)
    su2_forces = final.get("gates", {}).get("force_tail", {}).get("final_coefficients")
    compatible_forces = (
        None
        if not isinstance(su2_forces, Mapping)
        else {
            "cl": su2_forces.get("CL"),
            "cd": su2_forces.get("CD"),
            "cmy": su2_forces.get("CMy"),
        }
    )
    result = {
        "schema": SUMMARY_SCHEMA,
        "campaign_schema": CAMPAIGN_SCHEMA,
        "case_id": plan["case_id"],
        "geometry_set": set_name,
        "development_index": int(index),
        "geometry_id": surface.metadata["geometry_id"],
        "geometry_digest": geometry_digest,
        "flow_condition": resolved_flow,
        "flow_id": plan["flow_id"],
        "reference_quantities": resolved_references,
        "method": "unstructured",
        "grid_level": level,
        "te_variant": te_variant,
        "technical_accepted": bool(cfd["accepted"]) if cfd else bool(accepted_mesh is not None),
        "accepted": bool(cfd["accepted"]) if cfd else bool(accepted_mesh is not None),
        "acceptance_scope": acceptance_scope,
        "campaign_ready": False,
        "review_status": "technical_gate_only_claude_acceptance_review_required",
        "gate_results": {"mesh_attempts": mesh_attempts, "cfd": cfd},
        "cell_counts": (
            next((row["audit"].get("counts") for row in mesh_attempts if row["accepted"]), None)
        ),
        "runtime": {
            "reported_unix_s": time.time(),
            "mesh_wall_time_s": mesh_wall_time_s,
            "cfd_wall_time_s": cfd_wall_time_s,
            "total_measured_wall_time_s": mesh_wall_time_s + cfd_wall_time_s,
        },
        "peak_memory": {
            "rss_bytes": max(peak_rss_candidates),
            "scope": "maximum_reported_mesh_or_solver_process_tree_or_orchestrator",
        },
        "y_plus": final.get("gates", {}).get("wall_yplus"),
        "forces": compatible_forces,
        "provenance": {
            "policy_sha256": sha256_file(POLICY_PATH),
            "source_digest": source_digest(),
            "tool_versions": software_report["observed"],
            "pinned_versions": software_report,
            "software_version_preflight": str(software_preflight_path.resolve()),
        },
    }
    write_json(root / "case_result.json", result)
    _write_case_terminal(root, result)
    return result


def run_cases(
    *,
    set_name: str,
    indices: Sequence[int],
    level: str,
    te_variant: str,
    output: Path,
    flow: Mapping[str, Any] | None = None,
    references: Mapping[str, Any] | None = None,
    run_cfd: bool = False,
    timeout_s: float = 3600.0,
    solver_command: Sequence[str] = ("SU2_CFD",),
    flow_id: str = MESH_FLOW_ID,
) -> dict[str, Any]:
    """Run a deterministic development batch and continue after case failures."""
    require_development_set(set_name)
    normalized_indices = sorted({int(value) for value in indices})
    if not normalized_indices:
        raise ValueError("campaign indices must not be empty")
    if len(normalized_indices) != len(indices):
        raise ValueError("campaign indices must be unique")
    policy = load_policy()
    resolved_flow = _resolved_flow(policy, requested=flow, flow_id=flow_id, run_cfd=run_cfd)
    effective_flow_id = str(resolved_flow["flow_id"]) if run_cfd else MESH_FLOW_ID
    request = {
        "schema": "aeris.s7.batch_request.v1",
        "geometry_set": set_name,
        "indices": normalized_indices,
        "grid_level": level,
        "te_variant": te_variant,
        "flow_id": effective_flow_id,
        "flow": resolved_flow,
        "references": None if references is None else dict(references),
        "run_cfd": bool(run_cfd),
        "timeout_s": float(timeout_s),
        "solver_command": [str(part) for part in solver_command],
        "source_digest": source_digest(),
        "policy_sha256": sha256_file(POLICY_PATH),
    }
    token = sha256_bytes(canonical_json(request).encode("utf-8"))[:16]
    root = Path(output).resolve() / "campaign_runs" / f"campaign_{token}"
    root.mkdir(parents=True, exist_ok=True)
    request_path = root / "campaign_request.json"
    if request_path.is_file():
        if canonical_json(read_json(request_path)) != canonical_json(request):
            raise RuntimeError("batch request identity mismatch")
    else:
        write_json(request_path, request)
    terminal_path = root / "campaign_terminal.json"
    result_path = root / "campaign_result.json"
    if terminal_path.is_file():
        terminal = read_json(terminal_path)
        if terminal.get("source_digest") != source_digest() or terminal.get(
            "policy_sha256"
        ) != sha256_file(POLICY_PATH):
            raise RuntimeError("stored batch terminal is stale")
        verification = verify_digest_manifest(terminal["artifact_manifest"])
        if not verification["passed"]:
            raise RuntimeError(f"stored batch provenance failed: {verification['mismatches']}")
        return read_json(result_path)
    if result_path.is_file():
        raise RuntimeError("batch result exists without a terminal manifest")

    cases: list[dict[str, Any]] = []
    for development_index in normalized_indices:
        plan = plan_case(
            set_name=set_name,
            index=development_index,
            level=level,
            te_variant=te_variant,
            output=root / "cases",
            flow_id=effective_flow_id,
        )
        try:
            case_result = run_case(
                set_name=set_name,
                index=development_index,
                level=level,
                te_variant=te_variant,
                output=root / "cases",
                flow=resolved_flow if run_cfd else None,
                references=references,
                run_cfd=run_cfd,
                timeout_s=timeout_s,
                solver_command=solver_command,
                flow_id=effective_flow_id,
            )
            cases.append(
                {
                    "index": development_index,
                    "case_id": case_result["case_id"],
                    "case_root": plan["output"],
                    "status": "technical_pass" if case_result["accepted"] else "rejected",
                    "accepted": bool(case_result["accepted"]),
                }
            )
        except Exception as exc:
            cases.append(
                {
                    "index": development_index,
                    "case_id": plan["case_id"],
                    "case_root": plan["output"],
                    "status": "failed",
                    "accepted": False,
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                }
            )
    passed = sum(case["accepted"] for case in cases)
    result = {
        "schema": "aeris.s7.batch_result.v1",
        "campaign_id": f"campaign_{token}",
        "request_sha256": sha256_file(request_path),
        "case_count": len(cases),
        "technical_pass_count": passed,
        "technical_all_passed": passed == len(cases),
        "campaign_ready": False,
        "review_status": "claude_acceptance_review_required",
        "cases": cases,
        "source_digest": source_digest(),
        "policy_sha256": sha256_file(POLICY_PATH),
    }
    write_json(result_path, result)
    artifacts: dict[str, Path] = {
        "policy": POLICY_PATH,
        "campaign_request": request_path,
        "campaign_result": result_path,
    }
    for case in cases:
        case_root = Path(str(case["case_root"]))
        case_terminal = case_root / "case_terminal.json"
        if case_terminal.is_file():
            artifacts[f"case_{case['index']:03d}_terminal"] = case_terminal
        geometry_failure = case_root / "geometry_failure.json"
        if geometry_failure.is_file():
            artifacts[f"case_{case['index']:03d}_geometry_failure"] = geometry_failure
        for preflight_index, path in enumerate(
            sorted((case_root / "mesh_attempts").glob("*.resource_preflight.json"))
        ):
            artifacts[f"case_{case['index']:03d}_resource_{preflight_index:03d}"] = path
    manifest = digest_manifest(
        artifacts,
        required={"policy", "campaign_request", "campaign_result"},
    )
    verification = verify_digest_manifest(manifest)
    if not verification["passed"]:
        raise RuntimeError("batch terminal provenance verification failed")
    write_json(
        terminal_path,
        {
            "schema": "aeris.s7.batch_terminal.v1",
            "source_digest": source_digest(),
            "policy_sha256": sha256_file(POLICY_PATH),
            "artifact_manifest": manifest,
            "artifact_verification": verification,
        },
    )
    return result
