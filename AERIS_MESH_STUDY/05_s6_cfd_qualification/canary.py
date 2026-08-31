"""One-shot, measurement-only M2 A/C03 CFD canary.

The independent review authorizes exactly one process launch.  This module
keeps that exception narrower than the repository-wide heavy-work block:
identity and resource checks run first, a consumed record is written before
the solver starts, a watchdog can terminate only for machine-safety reasons,
and the result can never be labelled ACCEPTED.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
S6 = REPO / "AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas"
for _path in (REPO / "src", S6):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from cfd_qc import wall_yplus_summary  # noqa: E402

from aeris.cfd.case.spec import FlowConditions, SolveSpec  # noqa: E402
from aeris.cfd.env import MACH_AERO_PREFIX_ENV  # noqa: E402
from aeris.cfd.solvers.base import get_solver_adapter  # noqa: E402

CANARY_POLICY = ROOT / "policies/m2_a_c03_canary_v2.yaml"
GIB = 2**30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_path(value: str) -> Path:
    path = (REPO / value).resolve()
    if not path.is_relative_to(REPO.resolve()):
        raise ValueError(f"governed path escapes the repository: {value}")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_new_json(path: Path, payload: dict[str, Any]) -> None:
    """Create an immutable JSON record and refuse any collision."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _load_policy() -> dict[str, Any]:
    policy = yaml.safe_load(CANARY_POLICY.read_text(encoding="utf-8"))
    if not isinstance(policy, dict):
        raise ValueError("canary policy must be a mapping")
    return policy


def _meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, raw = line.split(":", 1)
        values[key] = int(raw.strip().split()[0]) * 1024
    return values


def _oom_kills() -> int | None:
    try:
        for line in Path("/proc/vmstat").read_text(encoding="utf-8").splitlines():
            key, value = line.split()
            if key == "oom_kill":
                return int(value)
    except (OSError, ValueError):
        return None
    return None


def _process_group_rss_bytes(process_group: int | None) -> int:
    if process_group is None:
        return 0
    page_size = os.sysconf("SC_PAGE_SIZE")
    total_pages = 0
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="utf-8")
            tail = stat[stat.rfind(")") + 2 :].split()
            if int(tail[2]) != process_group:  # field 5 (pgrp)
                continue
            resident_pages = int((entry / "statm").read_text().split()[1])
            total_pages += resident_pages
        except (FileNotFoundError, PermissionError, IndexError, ValueError):
            continue
    return total_pages * page_size


def _resource_snapshot(*, process_group: int | None = None) -> dict[str, Any]:
    memory = _meminfo()
    disk = os.statvfs(REPO)
    return {
        "created_at": _now(),
        "mem_total_bytes": memory["MemTotal"],
        "mem_available_bytes": memory["MemAvailable"],
        "swap_total_bytes": memory["SwapTotal"],
        "swap_free_bytes": memory["SwapFree"],
        "swap_used_bytes": memory["SwapTotal"] - memory["SwapFree"],
        "free_disk_bytes": disk.f_bavail * disk.f_frsize,
        "process_group_rss_bytes": _process_group_rss_bytes(process_group),
        "oom_kill_count": _oom_kills(),
    }


def _hash_matches(path: Path, expected: str) -> bool:
    return path.is_file() and _sha256(path) == expected


def _git_blob_sha256(revision: str, path: str) -> str | None:
    completed = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=REPO,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return hashlib.sha256(completed.stdout).hexdigest()


def _git_is_ancestor(revision: str) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", revision, "HEAD"],
        cwd=REPO,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def _policy_identity_checks(policy: dict[str, Any]) -> dict[str, bool]:
    mesh_policy = policy["mesh"]
    authorization = policy["authorization"]
    flow_policy = policy["flow"]
    refs = policy["references"]
    solver_policy = policy["solver"]

    mesh_path = _repo_path(mesh_policy["path"])
    surface_path = _repo_path(mesh_policy["target_surface_path"])
    evidence_path = _repo_path(mesh_policy["evidence_path"])
    review_path = _repo_path(authorization["independent_review_path"])
    mission_path = _repo_path(flow_policy["authority_path"])
    moment_path = _repo_path(refs["authority_path"])
    reference_evidence_path = _repo_path(refs["evidence_path"])
    classification_path = _repo_path(policy["classification_policy"]["path"])
    preset_path = _repo_path(solver_policy["preset_path"])
    superseded_policy_path = _repo_path(policy["supersedes_path"])

    review = _read_json(review_path) if review_path.is_file() else {}
    decision = review.get("decision", {})
    bound = decision.get("bound_artifact", {})
    family = _read_json(evidence_path) if evidence_path.is_file() else {}
    a_c03 = [
        row
        for row in family.get("results", [])
        if row.get("level") == "C03" and row.get("geometry") == "A"
    ]
    mission = (
        yaml.safe_load(mission_path.read_text(encoding="utf-8")) if mission_path.is_file() else {}
    )
    high_load = mission.get("high_load_case", {}) if isinstance(mission, dict) else {}
    mission_flow = mission.get("flow", {}) if isinstance(mission, dict) else {}
    reference_evidence = (
        _read_json(reference_evidence_path) if reference_evidence_path.is_file() else {}
    )
    solver_refs = reference_evidence.get("solver_references_from_realized_pygeo", {})
    reference_case = reference_evidence.get("case", {})
    evidence_moments = reference_evidence.get("moment_references", {})
    source_manifest_value = solver_refs.get("source_manifest")
    source_manifest_path = (
        _repo_path(source_manifest_value) if isinstance(source_manifest_value, str) else None
    )

    derived_reynolds = (
        float(flow_policy["density_kg_m3"])
        * float(flow_policy["speed_mps"])
        * float(flow_policy["reynolds_length_m"])
        / float(flow_policy["dynamic_viscosity_Pa_s"])
    )
    expected_reynolds = float(flow_policy["reynolds"])
    classification = (
        yaml.safe_load(classification_path.read_text(encoding="utf-8"))
        if classification_path.is_file()
        else {}
    )
    yplus = classification.get("wall_y_plus", {}) if isinstance(classification, dict) else {}
    review_commit = str(authorization["independent_review_commit"])
    review_relative_path = str(authorization["independent_review_path"])

    return {
        "policy_immutable": policy.get("immutable") is True,
        "immutable_v1_supersession_chain": (
            policy.get("supersedes") == "m2_a_c03_measurement_canary_v1"
            and _hash_matches(superseded_policy_path, policy["supersedes_sha256"])
        ),
        "measurement_only": policy.get("scope", {}).get("purpose") == "measurement_only",
        "one_process_launch": policy.get("scope", {}).get("maximum_process_launches") == 1,
        "automatic_retry_forbidden": (
            policy.get("scope", {}).get("automatic_retry_allowed") is False
        ),
        "accepted_verdict_forbidden": (
            policy.get("scope", {}).get("accepted_classification_allowed") is False
        ),
        "development_set_only": policy.get("scope", {}).get("development_set_only") is True,
        "holdout_access_forbidden": policy.get("scope", {}).get("holdout_access_allowed") is False,
        "mesh_sha256": _hash_matches(mesh_path, mesh_policy["sha256"]),
        "surface_sha256": _hash_matches(surface_path, mesh_policy["target_surface_sha256"]),
        "family_evidence_sha256": _hash_matches(evidence_path, mesh_policy["evidence_sha256"]),
        "review_sha256": _hash_matches(review_path, authorization["independent_review_sha256"]),
        "review_commit_is_ancestor": _git_is_ancestor(review_commit),
        "review_commit_blob_sha256": (
            _git_blob_sha256(review_commit, review_relative_path)
            == authorization["independent_review_sha256"]
        ),
        "review_go": decision.get("verdict") == authorization["required_review_verdict"],
        "review_bound_mesh": bound.get("sha256") == mesh_policy["sha256"],
        "review_bound_cells": bound.get("cells") == mesh_policy["cells"],
        "family_row_unique": len(a_c03) == 1,
        "family_row_mesh": bool(a_c03 and a_c03[0].get("output_sha256") == mesh_policy["sha256"]),
        "family_row_valid": bool(
            a_c03
            and a_c03[0].get("inverted_cells") == 0
            and a_c03[0].get("production_floor_passed") is True
        ),
        "mission_sha256": _hash_matches(mission_path, flow_policy["authority_sha256"]),
        "moment_authority_sha256": _hash_matches(moment_path, refs["authority_sha256"]),
        "reference_evidence_sha256": _hash_matches(
            reference_evidence_path, refs["evidence_sha256"]
        ),
        "reference_geometry_identity": (
            reference_case.get("geometry_set") == policy["scope"]["geometry_set"]
            and reference_case.get("geometry_label") == policy["scope"]["geometry_label"]
            and reference_case.get("geometry_index") == policy["scope"]["geometry_index"]
        ),
        "reference_source_manifest_sha256": bool(
            source_manifest_path
            and _hash_matches(source_manifest_path, solver_refs["source_manifest_sha256"])
        ),
        "reference_area_matches": math.isclose(
            float(solver_refs.get("full_area_m2", math.nan)),
            float(refs["full_area_m2"]),
            rel_tol=0.0,
            abs_tol=1.0e-14,
        ),
        "reference_chord_matches": math.isclose(
            float(solver_refs.get("chord_ref_m", math.nan)),
            float(refs["chord_ref_m"]),
            rel_tol=0.0,
            abs_tol=1.0e-14,
        ),
        "reference_span_matches": math.isclose(
            float(solver_refs.get("full_span_m", math.nan)),
            float(refs["full_span_m"]),
            rel_tol=0.0,
            abs_tol=1.0e-14,
        ),
        "moment_references_match_evidence": (
            evidence_moments.get("primary", {}).get("xyz_m")
            == refs["primary_moment_reference_xyz_m"]
            and evidence_moments.get("secondary", {}).get("xyz_m")
            == refs["secondary_moment_reference_xyz_m"]
        ),
        "half_area_contract": math.isclose(
            2.0 * float(refs["solver_half_area_m2"]),
            float(refs["full_area_m2"]),
            rel_tol=0.0,
            abs_tol=1.0e-14,
        ),
        "mission_high_load_alpha": math.isclose(
            float(high_load.get("alpha_deg", math.nan)),
            float(flow_policy["alpha_deg"]),
            rel_tol=0.0,
            abs_tol=1.0e-14,
        ),
        "mission_reynolds": math.isclose(
            float(mission_flow.get("reynolds", math.nan)),
            expected_reynolds,
            rel_tol=1.0e-13,
        ),
        "mission_flow_values": all(
            math.isclose(
                float(mission_flow.get(authority_key, math.nan)),
                float(flow_policy[policy_key]),
                rel_tol=1.0e-13,
                abs_tol=1.0e-14,
            )
            for authority_key, policy_key in (
                ("mach", "mach"),
                ("temperature_K", "temperature_K"),
                ("speed_mps", "speed_mps"),
                ("density_kg_m3", "density_kg_m3"),
                ("dynamic_viscosity_Pa_s", "dynamic_viscosity_Pa_s"),
                ("reference_chord_m", "reynolds_length_m"),
            )
        ),
        "thermodynamic_reynolds_consistent": math.isclose(
            derived_reynolds, expected_reynolds, rel_tol=1.0e-13
        ),
        "classification_policy_immutable": classification.get("immutable") is True,
        "yplus_numeric_limits": all(
            isinstance(yplus.get(key), (int, float))
            for key in ("p95_max", "p99_max", "absolute_max")
        ),
        "yplus_centroid_convention": "cell centroid"
        in str(yplus.get("wall_distance_convention", "")),
        "yplus_global_and_regional": (
            yplus.get("threshold_scope") == "global_and_each_no_slip_wall_zone"
        ),
        "complete_log_retention": (
            policy.get("artifacts", {}).get("retention")
            == "retain_all_cfd_logs_and_measurement_evidence"
        ),
        "volume_output_matches_review": (
            policy.get("solver", {}).get("write_volume_solution") is False
            and policy.get("solver", {}).get("write_surface_solution") is True
            and policy.get("solver", {}).get("retain_surface_solution") is True
        ),
        "solver_scope_is_one_rank_rans_sa": (
            solver_policy.get("mpi_processes") == 1
            and solver_policy.get("equations") == "RANS"
            and solver_policy.get("turbulence_model") == "SA"
        ),
        "solver_preset_sha256": _hash_matches(preset_path, solver_policy["preset_sha256"]),
        "solver_history_and_output_controls": (
            solver_policy.get("store_convergence_history") is True
            and solver_policy.get("write_volume_solution") is False
            and solver_policy.get("write_surface_solution") is True
            and solver_policy.get("retain_surface_solution") is True
            and solver_policy.get("nk_subspace_size") == 20
            and set(solver_policy.get("surface_variables", []))
            == {"cp", "cf", "yplus", "vx", "vy", "vz"}
        ),
        "full_native_history_requested": {
            "resrho",
            "resmom",
            "resrhoe",
            "resturb",
            "cl",
            "cd",
            "cmy",
            "cdp",
            "cdv",
        }.issubset(set(policy.get("solver", {}).get("monitor_variables", []))),
    }


def _resource_preflight(policy: dict[str, Any]) -> dict[str, Any]:
    snapshot = _resource_snapshot()
    resource = policy["resource"]
    cells = int(policy["mesh"]["cells"])
    forecast_gib = float(resource["bytes_per_cell"]) * cells / GIB
    limit_gib = snapshot["mem_total_bytes"] / GIB
    available_gib = snapshot["mem_available_bytes"] / GIB
    free_disk_gib = snapshot["free_disk_bytes"] / GIB
    checks = {
        "anchored_forecast_matches_policy": math.isclose(
            forecast_gib, float(resource["forecast_peak_gib"]), rel_tol=1.0e-12
        ),
        "forecast_le_memory_fraction": forecast_gib
        <= float(resource["forecast_max_fraction_wsl_memory"]) * limit_gib,
        "forecast_plus_headroom_le_available": forecast_gib
        + float(resource["prelaunch_headroom_gib"])
        <= available_gib,
        "free_disk_pass": free_disk_gib >= float(resource["minimum_free_disk_gib"]),
        "preexisting_swap_within_limit": snapshot["swap_used_bytes"]
        <= float(resource["maximum_preexisting_swap_gib"]) * GIB,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "forecast_peak_gib": forecast_gib,
        "wsl_memory_limit_gib": limit_gib,
        "mem_available_gib": available_gib,
        "prelaunch_margin_gib": available_gib
        - forecast_gib
        - float(resource["prelaunch_headroom_gib"]),
        "free_disk_gib": free_disk_gib,
        "preexisting_swap_used_gib": snapshot["swap_used_bytes"] / GIB,
        "snapshot": snapshot,
    }


def _solver_environment_preflight(policy: dict[str, Any], *, run_mpi_probe: bool) -> dict[str, Any]:
    governed = policy["solver"]["environment"]
    paths = {
        key: Path(str(governed[key])).resolve()
        for key in (
            "prefix",
            "python",
            "python_realpath",
            "mpirun",
            "mpirun_realpath",
            "adflow_init",
            "adflow_python_source",
            "adflow_library",
        )
    }
    checks = {
        "policy_requires_non_cfd_mpi_probe": (
            governed.get("prelaunch_non_cfd_mpi_probe_required") is True
        ),
        "prefix_exists": paths["prefix"].is_dir(),
        "python_exists_and_executable": paths["python"].is_file()
        and os.access(paths["python"], os.X_OK),
        "python_realpath": paths["python"] == paths["python_realpath"],
        "python_sha256": _hash_matches(paths["python_realpath"], governed["python_sha256"]),
        "mpirun_exists_and_executable": paths["mpirun"].is_file()
        and os.access(paths["mpirun"], os.X_OK),
        "mpirun_realpath": paths["mpirun"] == paths["mpirun_realpath"],
        "mpirun_sha256": _hash_matches(paths["mpirun_realpath"], governed["mpirun_sha256"]),
        "adflow_init_sha256": _hash_matches(paths["adflow_init"], governed["adflow_init_sha256"]),
        "adflow_python_source_sha256": _hash_matches(
            paths["adflow_python_source"], governed["adflow_python_source_sha256"]
        ),
        "adflow_library_sha256": _hash_matches(
            paths["adflow_library"], governed["adflow_library_sha256"]
        ),
    }
    import_probe: dict[str, Any] = {}
    if checks["python_exists_and_executable"]:
        probe_source = (
            "import adflow,baseclasses,json,mpi4py,numpy,sys;"
            "print(json.dumps({"
            "'python_version':'.'.join(map(str,sys.version_info[:3])),"
            "'adflow_version':adflow.__version__,"
            "'baseclasses_version':baseclasses.__version__,"
            "'mpi4py_version':mpi4py.__version__,"
            "'numpy_version':numpy.__version__,"
            "'adflow_file':adflow.__file__}))"
        )
        try:
            completed = subprocess.run(
                [str(paths["python"]), "-c", probe_source],
                cwd=REPO,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            import_probe = {
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            }
            observed = json.loads(completed.stdout.strip()) if completed.returncode == 0 else {}
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
            import_probe = {"error_type": type(error).__name__, "error": str(error)}
            observed = {}
    else:
        observed = {}
    for key in (
        "python_version",
        "adflow_version",
        "baseclasses_version",
        "mpi4py_version",
        "numpy_version",
    ):
        checks[f"import_{key}"] = observed.get(key) == str(governed[key])
    checks["import_adflow_path"] = (
        Path(str(observed.get("adflow_file", "missing"))).resolve() == paths["adflow_init"]
    )

    mpirun_version: dict[str, Any] = {}
    if checks["mpirun_exists_and_executable"]:
        try:
            completed = subprocess.run(
                [str(paths["mpirun"]), "--version"],
                cwd=REPO,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            combined = f"{completed.stdout}\n{completed.stderr}"
            mpirun_version = {
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            }
            checks["openmpi_version"] = (
                completed.returncode == 0 and str(governed["openmpi_version"]) in combined
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            mpirun_version = {"error_type": type(error).__name__, "error": str(error)}
            checks["openmpi_version"] = False
    else:
        checks["openmpi_version"] = False

    mpi_probe: dict[str, Any] = {"executed": False, "kind": "non_cfd_readiness_probe"}
    if run_mpi_probe:
        probe_source = (
            "from mpi4py import MPI;"
            "print('AERIS_MPI_READY',MPI.COMM_WORLD.rank,MPI.COMM_WORLD.size)"
        )
        try:
            completed = subprocess.run(
                [str(paths["mpirun"]), "-np", "1", str(paths["python"]), "-c", probe_source],
                cwd=REPO,
                text=True,
                capture_output=True,
                timeout=60,
                check=False,
            )
            mpi_probe = {
                "executed": True,
                "kind": "non_cfd_readiness_probe",
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            }
            checks["one_rank_mpi_probe"] = (
                completed.returncode == 0 and "AERIS_MPI_READY 0 1" in completed.stdout
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            mpi_probe = {
                "executed": True,
                "kind": "non_cfd_readiness_probe",
                "error_type": type(error).__name__,
                "error": str(error),
            }
            checks["one_rank_mpi_probe"] = False

    return {
        "passed": all(checks.values()),
        "checks": checks,
        "governed": governed,
        "import_probe": import_probe,
        "mpirun_version_probe": mpirun_version,
        "mpi_probe": mpi_probe,
    }


def preflight(*, run_mpi_probe: bool = False) -> dict[str, Any]:
    policy = _load_policy()
    identity_checks = _policy_identity_checks(policy)
    environment = _solver_environment_preflight(policy, run_mpi_probe=run_mpi_probe)
    resources = _resource_preflight(policy)
    consumed = _repo_path(policy["attempt"]["consumed_record"])
    attempt_dir = _repo_path(policy["attempt"]["directory"])
    one_shot_checks = {
        "authorization_not_consumed": not consumed.exists(),
        "attempt_directory_absent": not attempt_dir.exists(),
    }
    return {
        "schema": "aeris.s6.m2_canary_preflight.v1",
        "created_at": _now(),
        "policy": str(CANARY_POLICY),
        "policy_sha256": _sha256(CANARY_POLICY),
        "identity_checks": identity_checks,
        "resource": resources,
        "solver_environment": environment,
        "one_shot_checks": one_shot_checks,
        "passed": all(identity_checks.values())
        and resources["passed"]
        and environment["passed"]
        and all(one_shot_checks.values()),
    }


def _governed_sources_clean() -> tuple[bool, list[str]]:
    paths = [
        ".gitignore",
        "src/aeris/cfd/case/spec.py",
        "src/aeris/cfd/env.py",
        "src/aeris/cfd/solvers/base.py",
        "src/aeris/cfd/solvers/adflow/adapter.py",
        "src/aeris/cfd/solvers/adflow/options_schema.py",
        "src/aeris/cfd/solvers/adflow/parse.py",
        "src/aeris/cfd/presets/data/adflow_rans_ank_nk_v1.yaml",
        "AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/cfd_qc.py",
        "AERIS_MESH_STUDY/05_s6_cfd_qualification/run.py",
        "AERIS_MESH_STUDY/05_s6_cfd_qualification/canary.py",
        "AERIS_MESH_STUDY/05_s6_cfd_qualification/POLICY.yaml",
        "AERIS_MESH_STUDY/05_s6_cfd_qualification/policies/convergence_v2.yaml",
        "AERIS_MESH_STUDY/05_s6_cfd_qualification/policies/m2_a_c03_canary_v1.yaml",
        "AERIS_MESH_STUDY/05_s6_cfd_qualification/policies/m2_a_c03_canary_v2.yaml",
        "AERIS_MESH_STUDY/05_s6_cfd_qualification/grid_family_candidate_v1.yaml",
        "AERIS_MESH_STUDY/05_s6_cfd_qualification/reports/m2_a_c03_reference_contract_20260831.json",
    ]
    completed = subprocess.run(
        ["git", "status", "--short", "--", *paths],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )
    dirty = [line for line in completed.stdout.splitlines() if line.strip()]
    return completed.returncode == 0 and not dirty, dirty


def _git_head() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True, capture_output=True, check=False
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _solver_source_hashes() -> dict[str, str]:
    paths = [
        REPO / "src/aeris/cfd/case/spec.py",
        REPO / "src/aeris/cfd/env.py",
        REPO / "src/aeris/cfd/solvers/base.py",
        REPO / "src/aeris/cfd/solvers/adflow/adapter.py",
        REPO / "src/aeris/cfd/solvers/adflow/options_schema.py",
        REPO / "src/aeris/cfd/solvers/adflow/parse.py",
        REPO / "src/aeris/cfd/presets/data/adflow_rans_ank_nk_v1.yaml",
        S6 / "cfd_qc.py",
        Path(__file__),
    ]
    return {str(path.relative_to(REPO)): _sha256(path) for path in paths}


def _prepared_artifacts(prepared: Any) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for name, value in prepared.artifacts.items():
        path = Path(value)
        output[name] = {
            "path": str(path),
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
    return output


def _terminate_process_group(process: subprocess.Popen[Any], grace_seconds: float) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace_seconds
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.25)
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _run_with_watchdog(
    command: list[str],
    *,
    workdir: Path,
    log_path: Path,
    samples_path: Path,
    watchdog_policy: dict[str, Any],
) -> dict[str, Any]:
    baseline = _resource_snapshot()
    started_wall = _now()
    started_monotonic = time.monotonic()
    interval = float(watchdog_policy["poll_interval_seconds"])
    heartbeat = float(watchdog_policy["heartbeat_interval_seconds"])
    next_heartbeat = started_monotonic
    stop_reason: str | None = None
    sample_count = 0
    maximum_rss = 0
    minimum_available = baseline["mem_available_bytes"]
    maximum_swap_growth = 0
    minimum_free_disk = baseline["free_disk_bytes"]
    process: subprocess.Popen[Any] | None = None
    launch_error: dict[str, str] | None = None

    with (
        log_path.open("x", encoding="utf-8") as solver_log,
        samples_path.open("x", encoding="utf-8", buffering=1) as samples,
    ):
        try:
            process = subprocess.Popen(
                command,
                cwd=workdir,
                stdout=solver_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as error:
            launch_error = {"type": type(error).__name__, "message": str(error)}
            solver_log.write(json.dumps({"launch_error": launch_error}) + "\n")
            solver_log.flush()
            os.fsync(solver_log.fileno())
        if process is not None:
            print(f"canary process group {process.pid} started", flush=True)
            try:
                while process.poll() is None:
                    snapshot = _resource_snapshot(process_group=process.pid)
                    elapsed = time.monotonic() - started_monotonic
                    snapshot["elapsed_seconds"] = elapsed
                    samples.write(json.dumps(snapshot, sort_keys=True) + "\n")
                    sample_count += 1
                    if sample_count % 5 == 0:
                        samples.flush()
                        os.fsync(samples.fileno())

                    maximum_rss = max(maximum_rss, snapshot["process_group_rss_bytes"])
                    minimum_available = min(minimum_available, snapshot["mem_available_bytes"])
                    swap_growth = max(0, snapshot["swap_used_bytes"] - baseline["swap_used_bytes"])
                    maximum_swap_growth = max(maximum_swap_growth, swap_growth)
                    minimum_free_disk = min(minimum_free_disk, snapshot["free_disk_bytes"])

                    if (
                        snapshot["mem_available_bytes"]
                        < float(watchdog_policy["minimum_mem_available_gib"]) * GIB
                    ):
                        stop_reason = "mem_available_below_watchdog_floor"
                    elif swap_growth > float(watchdog_policy["maximum_swap_growth_gib"]) * GIB:
                        stop_reason = "swap_growth_above_watchdog_limit"
                    elif (
                        snapshot["free_disk_bytes"]
                        < float(watchdog_policy["minimum_runtime_free_disk_gib"]) * GIB
                    ):
                        stop_reason = "free_disk_below_watchdog_floor"
                    elif (
                        baseline["oom_kill_count"] is not None
                        and snapshot["oom_kill_count"] is not None
                        and snapshot["oom_kill_count"] > baseline["oom_kill_count"]
                    ):
                        stop_reason = "kernel_oom_kill_detected"

                    if stop_reason is not None:
                        print(f"memory watchdog stopping canary: {stop_reason}", flush=True)
                        _terminate_process_group(
                            process, float(watchdog_policy["terminate_grace_seconds"])
                        )
                        break

                    if time.monotonic() >= next_heartbeat:
                        print(
                            "canary heartbeat "
                            f"elapsed={elapsed:.0f}s "
                            f"rss={snapshot['process_group_rss_bytes'] / GIB:.2f}GiB "
                            f"available={snapshot['mem_available_bytes'] / GIB:.2f}GiB "
                            f"swap_growth={swap_growth / GIB:.2f}GiB",
                            flush=True,
                        )
                        next_heartbeat = time.monotonic() + heartbeat
                    time.sleep(interval)
            except Exception as error:
                stop_reason = "watchdog_internal_error"
                launch_error = {"type": type(error).__name__, "message": str(error)}
                _terminate_process_group(process, float(watchdog_policy["terminate_grace_seconds"]))

        returncode = process.wait() if process is not None else None
        samples.flush()
        os.fsync(samples.fileno())

    ended = _resource_snapshot()
    return {
        "started_at": started_wall,
        "ended_at": _now(),
        "elapsed_seconds": time.monotonic() - started_monotonic,
        "returncode": returncode,
        "process_launched": process is not None,
        "launch_or_watchdog_error": launch_error,
        "watchdog_stopped": stop_reason is not None,
        "watchdog_stop_reason": stop_reason,
        "sample_count": sample_count,
        "maximum_sampled_process_group_rss_bytes": maximum_rss,
        "minimum_mem_available_bytes": minimum_available,
        "maximum_swap_growth_bytes": maximum_swap_growth,
        "minimum_free_disk_bytes": minimum_free_disk,
        "baseline": baseline,
        "ended": ended,
    }


def _parse_time_verbose(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"present": False}
    text = path.read_text(encoding="utf-8", errors="replace")
    fields: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"\s*([^:]+):\s*(.*)$", line)
        if match:
            fields[match.group(1).strip()] = match.group(2).strip()
    maximum_rss_kib = fields.get("Maximum resident set size (kbytes)")
    return {
        "present": True,
        "path": str(path),
        "sha256": _sha256(path),
        "maximum_resident_set_kib": (
            int(maximum_rss_kib) if maximum_rss_kib and maximum_rss_kib.isdigit() else None
        ),
        "fields": fields,
    }


def _normalized_functions(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    return {
        (str(key).split("_")[-1] if "_" in str(key) else str(key)).casefold(): float(value)
        for key, value in raw.items()
        if isinstance(value, (int, float))
    }


def _force_tail(raw_run: dict[str, Any], classification: dict[str, Any]) -> dict[str, Any]:
    history = raw_run.get("convergence_history", {})
    normalized = {str(key).casefold().replace(" ", ""): value for key, value in history.items()}
    policy = classification["force_tail"]
    window = int(policy["sample_window"])
    limit = float(policy["maximum_relative_range"])
    floors = {key: float(value) for key, value in policy["denominator_floors"].items()}
    rows: dict[str, Any] = {}
    failures: list[str] = []
    history_names = {
        "cl": ("cl", "coeflift"),
        "cd": ("cd", "coefdrag"),
        "cmy": ("cmy", "coefmomenty"),
    }
    for coefficient in policy["coefficients"]:
        aliases = history_names.get(str(coefficient).casefold(), (str(coefficient),))
        values = next(
            (
                normalized[name.casefold().replace(" ", "")]
                for name in aliases
                if name.casefold().replace(" ", "") in normalized
            ),
            None,
        )
        if not isinstance(values, list) or len(values) < window:
            rows[coefficient] = {"samples": len(values) if isinstance(values, list) else 0}
            failures.append(f"{coefficient}_fewer_than_{window}_samples")
            continue
        tail = [float(value) for value in values[-window:]]
        if not all(math.isfinite(value) for value in tail):
            rows[coefficient] = {"samples": window, "finite": False}
            failures.append(f"{coefficient}_nonfinite_tail")
            continue
        absolute_range = max(tail) - min(tail)
        denominator = max(abs(sum(tail) / len(tail)), floors[coefficient])
        relative_range = absolute_range / denominator
        rows[coefficient] = {
            "samples": window,
            "finite": True,
            "minimum": min(tail),
            "maximum": max(tail),
            "mean": sum(tail) / len(tail),
            "absolute_range": absolute_range,
            "denominator_floor": floors[coefficient],
            "relative_range": relative_range,
            "maximum_relative_range": limit,
            "passed": relative_range <= limit,
        }
        if relative_range > limit:
            failures.append(f"{coefficient}_relative_range_above_limit")
    return {"passed": not failures, "failure_reasons": failures, "coefficients": rows}


def _surface_field_presence(surface: Path | None) -> dict[str, Any]:
    if surface is None or not surface.is_file():
        return {"passed": False, "failure_reasons": ["missing_surface_solution"]}
    import h5py
    import numpy as np

    aliases = {
        "cp": {"cp", "coefpressure"},
        "cf": {"cf", "skinfrictionmagnitude"},
        "yplus": {"yplus"},
    }
    counts = {field: 0 for field in aliases}
    nonfinite = {field: 0 for field in aliases}
    with h5py.File(surface, "r") as handle:

        def collect(name: str, obj: Any) -> None:
            if not isinstance(obj, h5py.Dataset):
                return
            parts = {part.casefold() for part in name.split("/")}
            for field, names in aliases.items():
                if parts.intersection(names):
                    values = np.asarray(obj[()]).reshape(-1)
                    counts[field] += int(values.size)
                    nonfinite[field] += int(values.size - np.count_nonzero(np.isfinite(values)))

        handle.visititems(collect)
    failures = [f"missing_{field}" for field, count in counts.items() if count == 0]
    failures.extend(f"nonfinite_{field}" for field, count in nonfinite.items() if count > 0)
    field_presence_passed = not failures
    failures.append("interface_discontinuity_not_evaluated")
    return {
        "passed": False,
        "field_presence_passed": field_presence_passed,
        "failure_reasons": failures,
        "sample_counts": counts,
        "nonfinite_counts": nonfinite,
        "interface_discontinuity_check": "not_evaluated_in_measurement_canary",
    }


def _artifact(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.is_file(),
        "sha256": _sha256(path) if path.is_file() else None,
        "size_bytes": path.stat().st_size if path.is_file() else None,
    }


def _postprocess(
    *,
    policy: dict[str, Any],
    prepared: Any,
    runtime: dict[str, Any],
    preflight_report: dict[str, Any],
    launch_record: dict[str, Any],
    time_path: Path,
    samples_path: Path,
) -> dict[str, Any]:
    adapter = get_solver_adapter("adflow")
    parse_error = None
    try:
        solve_report = adapter.parse(prepared.workdir)
        solve_status = solve_report.status
        solve_convergence = solve_report.convergence
        solve_forces = solve_report.forces
    except Exception as error:  # preserve a failed measurement rather than hiding it
        parse_error = {"type": type(error).__name__, "message": str(error)}
        solve_status = "failed"
        solve_convergence = {}
        solve_forces = {}

    raw_run_path = prepared.workdir / "adflow_run.json"
    raw_run = _read_json(raw_run_path) if raw_run_path.is_file() else {}
    classification_path = _repo_path(policy["classification_policy"]["path"])
    classification = yaml.safe_load(classification_path.read_text(encoding="utf-8"))
    yplus_policy = classification["wall_y_plus"]
    surface_candidates = sorted(prepared.workdir.glob("aeris_cfd*_surf.cgns"))
    surface_solution = surface_candidates[0] if len(surface_candidates) == 1 else None
    if surface_solution is None:
        yplus = {
            "passed": False,
            "failure_reasons": [
                "missing_surface_solution"
                if not surface_candidates
                else "multiple_surface_solutions"
            ],
            "candidate_count": len(surface_candidates),
            "wall_distance_convention": yplus_policy["wall_distance_convention"],
        }
    else:
        try:
            yplus = wall_yplus_summary(
                surface_solution,
                target=float(yplus_policy["target"]),
                p95_max=float(yplus_policy["p95_max"]),
                p99_max=float(yplus_policy["p99_max"]),
                absolute_max=float(yplus_policy["absolute_max"]),
                wall_distance_convention=str(yplus_policy["wall_distance_convention"]),
                enforce_each_region=True,
            )
        except Exception as error:
            yplus = {
                "passed": False,
                "failure_reasons": ["wall_yplus_read_error"],
                "error_type": type(error).__name__,
                "error": str(error),
                "wall_distance_convention": yplus_policy["wall_distance_convention"],
            }

    residuals = raw_run.get("residual_components_final", {})
    residual_checks: dict[str, bool] = {}
    for name, definition in classification["residuals"].items():
        value = residuals.get(name)
        residual_checks[name] = bool(
            value is not None
            and math.isfinite(float(value))
            and float(value) <= float(definition["max_final"])
        )
    force_tail = (
        _force_tail(raw_run, classification)
        if raw_run
        else {
            "passed": False,
            "failure_reasons": ["missing_convergence_history"],
            "coefficients": {},
        }
    )
    mass_definition = raw_run.get("mass_imbalance_definition")
    required_mass_definition = classification["mass_imbalance_normalized"]["required_definition"]
    mass_value = raw_run.get("mass_imbalance_normalized")
    conservation = {
        "passed": bool(
            mass_definition == required_mass_definition
            and mass_value is not None
            and float(mass_value) <= float(classification["mass_imbalance_normalized"]["max"])
        ),
        "measured_value": mass_value,
        "measured_definition": mass_definition,
        "required_definition": required_mass_definition,
        "note": (
            "The current runner metric is retained but cannot substitute for the "
            "governed signed boundary-flux balance."
        ),
    }
    surface_fields = _surface_field_presence(surface_solution)
    time_report = _parse_time_verbose(time_path)
    time_rss = time_report.get("maximum_resident_set_kib")
    time_rss_bytes = int(time_rss) * 1024 if isinstance(time_rss, int) else 0
    system_available_drop_bytes = max(
        0,
        int(runtime["baseline"]["mem_available_bytes"])
        - int(runtime["minimum_mem_available_bytes"]),
    )
    measured_peak_bytes = max(
        int(runtime["maximum_sampled_process_group_rss_bytes"]),
        time_rss_bytes,
        system_available_drop_bytes,
    )
    forecast_bytes = float(policy["resource"]["forecast_peak_gib"]) * GIB
    baseline_oom = runtime["baseline"].get("oom_kill_count")
    ended_oom = runtime["ended"].get("oom_kill_count")
    no_new_oom = baseline_oom is None or ended_oom is None or ended_oom <= baseline_oom
    resource_checks = {
        "watchdog_not_triggered": not runtime["watchdog_stopped"],
        "measured_peak_le_forecast": measured_peak_bytes <= forecast_bytes,
        "minimum_mem_available_ge_2_gib": runtime["minimum_mem_available_bytes"]
        >= float(policy["watchdog"]["minimum_mem_available_gib"]) * GIB,
        "swap_growth_within_limit": runtime["maximum_swap_growth_bytes"]
        <= float(policy["watchdog"]["maximum_swap_growth_gib"]) * GIB,
        "no_kernel_oom_kill": no_new_oom,
    }
    resource_passed = all(resource_checks.values())

    if runtime["watchdog_stopped"]:
        terminal_state = "resource"
        execution_status = "RESOURCE_BLOCKED_HOST"
    elif runtime["returncode"] != 0 or solve_status != "converged":
        terminal_state = "solver"
        execution_status = "SOLVER_MEASUREMENT_FAILED"
    else:
        terminal_state = "solver"
        execution_status = "MEASUREMENT_COMPLETE"

    artifacts = {
        "solver_log": _artifact(prepared.workdir / prepared.log_name),
        "adflow_run": _artifact(raw_run_path),
        "solve_report": _artifact(prepared.workdir / "solve_report.json"),
        "surface_solution": _artifact(surface_solution) if surface_solution else None,
        "time_verbose": _artifact(time_path),
        "watchdog_samples": _artifact(samples_path),
    }
    return {
        "schema_version": 1,
        "schema": "aeris.s6.execution_result.v1",
        "execution_id": policy["attempt"]["id"],
        "created_at": _now(),
        "terminal_state": terminal_state,
        "status": execution_status,
        "measurement_only": True,
        "accepted_classification_allowed": False,
        "automatic_retry_allowed": False,
        "holdout_accessed": False,
        "inputs": {
            "geometry_sha256": policy["mesh"]["target_surface_sha256"],
            "mesh_identity": policy["mesh"]["sha256"],
            "mesh_sha256": policy["mesh"]["sha256"],
            "policy_sha256": _sha256(CANARY_POLICY),
            "classification_policy_sha256": _sha256(classification_path),
            "git_head": launch_record["git_head"],
            "flow": policy["flow"],
            "references": policy["references"],
            "solver": policy["solver"],
            "solver_source_sha256": launch_record["solver_source_sha256"],
        },
        "preflight": preflight_report,
        "runtime": runtime,
        "resource": {
            "passed": resource_passed,
            "checks": resource_checks,
            "forecast_peak_gib": float(policy["resource"]["forecast_peak_gib"]),
            "measured_peak_bytes": measured_peak_bytes,
            "measured_peak_gib": measured_peak_bytes / GIB,
            "system_mem_available_drop_bytes": system_available_drop_bytes,
            "time_verbose": time_report,
            "watchdog_classification": (
                "resource_outcome_not_mesh_verdict"
                if runtime["watchdog_stopped"]
                else "not_triggered"
            ),
        },
        "solver": {
            "returncode": runtime["returncode"],
            "status": solve_status,
            "parse_error": parse_error,
            "forces_at_mission_cg": _normalized_functions(raw_run.get("functions", solve_forces)),
            "forces_at_geometry_quarter_mac": _normalized_functions(
                raw_run.get("secondary_reference_functions")
            ),
            "normalized_solve_report_convergence": solve_convergence,
        },
        "classification_measurements": {
            "residuals": {
                "passed": bool(residual_checks) and all(residual_checks.values()),
                "checks": residual_checks,
                "values": residuals,
                "definition": raw_run.get("residual_components_definition"),
                "component_monitor_values": raw_run.get("residual_component_monitor_final", {}),
            },
            "force_tail": force_tail,
            "conservation": conservation,
            "y_plus": yplus,
            "surface_fields": surface_fields,
            "accepted": False,
            "verdict": "MEASUREMENT_ONLY_NOT_ACCEPTED",
            "reason": (
                "The independent GO expressly forbids an ACCEPTED verdict for this one-shot canary."
            ),
        },
        "convergence": {
            "residual_components_final": residuals,
            "residual_components_definition": raw_run.get("residual_components_definition"),
            "mass_imbalance_normalized": mass_value,
            "mass_imbalance_definition": mass_definition,
        },
        "artifacts": {"hashes_only": True, **artifacts},
        "prepared_artifacts": launch_record["prepared_artifacts"],
    }


def _build_solve_spec(policy: dict[str, Any]) -> SolveSpec:
    refs = policy["references"]
    flow = policy["flow"]
    solver = policy["solver"]
    return SolveSpec(
        solver="adflow",
        preset=str(solver["preset"]),
        flow=FlowConditions(
            alpha=float(flow["alpha_deg"]),
            mach=float(flow["mach"]),
            reynolds=float(flow["reynolds"]),
            temperature=float(flow["temperature_K"]),
        ),
        area_ref=float(refs["solver_half_area_m2"]),
        chord_ref=float(refs["chord_ref_m"]),
        reynolds_length_ref=float(flow["reynolds_length_m"]),
        moment_reference=tuple(float(value) for value in refs["primary_moment_reference_xyz_m"]),
        secondary_moment_reference=tuple(
            float(value) for value in refs["secondary_moment_reference_xyz_m"]
        ),
        mpi_np=int(solver["mpi_processes"]),
        raw_options={
            "equationType": str(solver["equations"]),
            "turbulenceModel": str(solver["turbulence_model"]),
            "writeVolumeSolution": bool(solver["write_volume_solution"]),
            "writeSurfaceSolution": bool(solver["write_surface_solution"]),
            "storeConvHist": bool(solver["store_convergence_history"]),
            "monitorVariables": list(solver["monitor_variables"]),
            "surfaceVariables": list(solver["surface_variables"]),
            "NKSubspaceSize": int(solver["nk_subspace_size"]),
        },
    )


def execute_canary(*, dry_run: bool, execute_token: str | None) -> dict[str, Any]:
    policy = _load_policy()
    preflight_report = preflight(run_mpi_probe=False)
    if dry_run:
        return {
            "status": "DRY_RUN" if preflight_report["passed"] else "BLOCKED",
            "details": {
                "preflight": preflight_report,
                "process_launched": False,
                "scope": "exactly one measurement-only A/C03 canary",
            },
        }

    expected_token_hash = policy["authorization"]["execute_token_sha256"]
    supplied_hash = hashlib.sha256((execute_token or "").encode("utf-8")).hexdigest()
    if supplied_hash != expected_token_hash:
        return {
            "status": "BLOCKED",
            "details": {
                "reason": "missing or incorrect one-shot execute token",
                "process_launched": False,
                "preflight": preflight_report,
            },
        }
    governed_clean, dirty = _governed_sources_clean()
    if not governed_clean:
        return {
            "status": "BLOCKED",
            "details": {
                "reason": "governed canary sources must be committed before launch",
                "dirty_governed_paths": dirty,
                "process_launched": False,
                "preflight": preflight_report,
            },
        }
    if not preflight_report["passed"]:
        return {
            "status": "BLOCKED",
            "details": {
                "reason": "identity, one-shot, or resource preflight failed",
                "process_launched": False,
                "preflight": preflight_report,
            },
        }
    preflight_report = preflight(run_mpi_probe=True)
    if not preflight_report["passed"]:
        return {
            "status": "BLOCKED",
            "details": {
                "reason": "non-CFD one-rank MPI readiness probe failed",
                "process_launched": False,
                "authorization_consumed": False,
                "preflight": preflight_report,
            },
        }

    attempt_dir = _repo_path(policy["attempt"]["directory"])
    attempt_dir.mkdir(parents=True, exist_ok=False)
    mesh_path = _repo_path(policy["mesh"]["path"])
    solver = policy["solver"]
    os.environ[MACH_AERO_PREFIX_ENV] = str(solver["environment"]["prefix"])
    solve_spec = _build_solve_spec(policy)
    adapter = get_solver_adapter("adflow")
    prepared = adapter.prepare(solve_spec, mesh_path, attempt_dir)
    time_path = attempt_dir / "time_verbose.txt"
    samples_path = attempt_dir / "resource_watchdog.jsonl"
    timed_command = ["/usr/bin/time", "-v", "-o", str(time_path), "--", *prepared.command]
    launch_record = {
        "schema": "aeris.s6.m2_canary_launch.v1",
        "attempt_id": policy["attempt"]["id"],
        "created_at": _now(),
        "git_head": _git_head(),
        "policy_path": str(CANARY_POLICY),
        "policy_sha256": _sha256(CANARY_POLICY),
        "mesh_path": str(mesh_path),
        "mesh_sha256": _sha256(mesh_path),
        "command": timed_command,
        "prepared_artifacts": _prepared_artifacts(prepared),
        "solver_source_sha256": _solver_source_hashes(),
        "process_launch_limit": 1,
        "automatic_retry_allowed": False,
        "accepted_classification_allowed": False,
    }
    _write_new_json(attempt_dir / "launch_record.json", launch_record)
    consumed_path = _repo_path(policy["attempt"]["consumed_record"])
    _write_new_json(
        consumed_path,
        {
            "schema": "aeris.s6.m2_canary_authorization_consumed.v1",
            "attempt_id": policy["attempt"]["id"],
            "created_at": _now(),
            "git_head": launch_record["git_head"],
            "mesh_sha256": policy["mesh"]["sha256"],
            "policy_sha256": launch_record["policy_sha256"],
            "maximum_process_launches": 1,
            "launch_record": str(attempt_dir / "launch_record.json"),
            "no_automatic_retry": True,
        },
    )

    runtime = _run_with_watchdog(
        timed_command,
        workdir=attempt_dir,
        log_path=attempt_dir / prepared.log_name,
        samples_path=samples_path,
        watchdog_policy=policy["watchdog"],
    )
    execution = _postprocess(
        policy=policy,
        prepared=prepared,
        runtime=runtime,
        preflight_report=preflight_report,
        launch_record=launch_record,
        time_path=time_path,
        samples_path=samples_path,
    )
    execution_path = _repo_path(policy["attempt"]["execution_record"])
    _write_new_json(execution_path, execution)
    return {
        "status": ("CONDITIONAL" if execution["status"] == "MEASUREMENT_COMPLETE" else "FAIL"),
        "details": {
            "execution_status": execution["status"],
            "execution_record": str(execution_path),
            "execution_record_sha256": _sha256(execution_path),
            "process_launched": runtime["process_launched"],
            "accepted": False,
            "automatic_retry_allowed": False,
        },
    }
