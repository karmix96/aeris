"""Shared, fail-closed utilities for the S7 unstructured campaign.

This module deliberately has no Gmsh, pyGeo or SU2 imports.  It is safe to use
from planning, collection and audit commands on machines that do not have the
production toolchain installed.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
MESH_STUDY = STUDIES.parent
REPO_ROOT = MESH_STUDY.parent
POLICY_PATH = HERE / "POLICY.yaml"
STRATEGY_ID = "S7_UNSTRUCTURED_GMSH_SU2"
SUMMARY_SCHEMA = "aeris.mesh_strategy_result.v1"
ATTEMPT_SCHEMA = "aeris.s7.attempt.v1"

for _path in (REPO_ROOT / "src", STUDIES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        default=_json_default,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def atomic_write_text(path: Path, text: str) -> Path:
    """Write one UTF-8 artifact atomically in its destination directory."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return path


def write_json(path: Path, value: Any) -> Path:
    text = json.dumps(
        value,
        default=_json_default,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    )
    return atomic_write_text(Path(path), text + "\n")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object in {path}")
    return value


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"S7 policy must be a mapping: {path}")
    if value.get("schema_version") != "aeris.s7.policy.v1":
        raise ValueError(f"unsupported S7 policy schema in {path}")
    return value


def sha256_file(path: Path, *, chunk_bytes: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def combined_sha256(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted({Path(p).resolve() for p in paths}, key=str):
        digest.update(str(path.relative_to(REPO_ROOT)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def source_paths() -> list[Path]:
    """All implementation inputs that define an S7 result fingerprint."""
    local = list(HERE.glob("*.py")) + list(HERE.glob("*.yaml"))
    # Use the complete in-repository AERIS Python tree rather than a manually
    # maintained import shortlist.  The latter can silently miss indirect
    # geometry dependencies such as the LHS sampler or generator registry.
    # Conservative invalidation is preferable to accepting stale CFD evidence.
    shared = [
        *list((STUDIES / "shared").glob("*.py")),
        *list((REPO_ROOT / "src/aeris").rglob("*.py")),
        REPO_ROOT / "configs/geometry/bwb.yaml",
        REPO_ROOT / "pyproject.toml",
    ]
    return sorted({path.resolve() for path in [*local, *shared] if path.is_file()})


def source_digest() -> str:
    return combined_sha256(source_paths())


def require_development_set(set_name: str) -> None:
    """Enforce the S7 hold-out quarantine in addition to the shared tripwire."""
    policy = load_policy()
    locked = str(policy["data"]["locked_holdout_set"])
    if set_name == locked:
        raise PermissionError(
            f"{locked} is forbidden by S7 POLICY.yaml. A superseding freeze/unlock "
            "decision and code change are required; this runner has no bypass flag."
        )
    allowed = str(policy["data"]["development_set"])
    if set_name != allowed:
        raise ValueError(f"S7 campaign evidence must use {allowed!r}; {set_name!r} is not in scope")


def finite_float(value: Any, label: str) -> float:
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{label} is not finite: {value!r}")
    return result


def tool_versions() -> dict[str, Any]:
    versions: dict[str, Any] = {
        "python": platform.python_version(),
        "python_executable": str(Path(sys.executable).resolve()),
        "platform": platform.platform(),
        "numpy": np.__version__,
    }
    try:
        import scipy

        versions["scipy"] = scipy.__version__
    except Exception as exc:  # pragma: no cover - diagnostic path
        versions["scipy_error"] = repr(exc)
    try:
        import gmsh

        versions["gmsh_python"] = gmsh.__version__
    except Exception as exc:  # pragma: no cover - diagnostic path
        versions["gmsh_error"] = repr(exc)
    for name in ("pygeo", "pyspline"):
        try:
            module = __import__(name)
            versions[name] = str(module.__version__)
        except Exception as exc:  # pragma: no cover - diagnostic path
            versions[f"{name}_error"] = repr(exc)

    for name, executable, version_args in (
        ("gmsh_cli", shutil.which("gmsh"), ["--version"]),
        ("su2_cfd", shutil.which("SU2_CFD"), ["--version"]),
        ("su2_sol", shutil.which("SU2_SOL"), ["--version"]),
        ("mpirun", shutil.which("mpirun"), ["--version"]),
    ):
        versions[f"{name}_path"] = executable
        if executable:
            try:
                completed = subprocess.run(
                    [executable, *version_args],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                versions[name] = (completed.stdout or completed.stderr).strip().splitlines()[0]
            except Exception as exc:  # pragma: no cover - diagnostic path
                versions[f"{name}_error"] = repr(exc)
    return versions


def verify_pinned_versions(
    *, require_su2: bool = False, raise_on_mismatch: bool = True
) -> dict[str, Any]:
    """Fail when the executing stack differs from the preregistered versions."""
    policy = load_policy()["software"]
    observed = tool_versions()
    mapping = {
        "python": "python",
        "gmsh_python": "gmsh_python",
        "gmsh_cli": "gmsh_cli",
        "numpy": "numpy",
        "scipy": "scipy",
        "pygeo": "pygeo",
        "pyspline": "pyspline",
    }
    mismatches: list[str] = []
    for policy_name, observed_name in mapping.items():
        expected = str(policy[policy_name])
        actual = observed.get(observed_name)
        if actual is None or str(actual).strip() != expected:
            mismatches.append(f"{policy_name}: expected {expected!r}, observed {actual!r}")
    expected_su2 = str(policy["su2_cfd"])
    actual_su2 = observed.get("su2_cfd")
    if require_su2 and (actual_su2 is None or expected_su2.lower() not in str(actual_su2).lower()):
        mismatches.append(
            f"su2_cfd: expected output containing {expected_su2!r}, observed {actual_su2!r}"
        )
    report = {
        "passed": not mismatches,
        "require_su2": require_su2,
        "expected": dict(policy),
        "observed": observed,
        "mismatches": mismatches,
    }
    if mismatches and raise_on_mismatch:
        raise RuntimeError("software version preflight failed: " + "; ".join(mismatches))
    return report


def peak_self_rss_bytes() -> int:
    """Return the process high-water RSS in bytes on the supported Linux hosts."""
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value * 1024 if sys.platform.startswith("linux") else value


def _process_tree_rss_bytes(root_pid: int) -> int:
    """Read aggregate resident memory for one Linux process tree."""
    pending = [int(root_pid)]
    visited: set[int] = set()
    total = 0
    while pending:
        pid = pending.pop()
        if pid in visited:
            continue
        visited.add(pid)
        try:
            status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
            for line in status.splitlines():
                if line.startswith("VmRSS:"):
                    total += int(line.split()[1]) * 1024
                    break
            children = Path(f"/proc/{pid}/task/{pid}/children").read_text(encoding="utf-8")
            pending.extend(int(value) for value in children.split())
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
            continue
    return total


def resource_snapshot(path: Path) -> dict[str, Any]:
    disk = shutil.disk_usage(Path(path).resolve())
    page_size = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 0
    physical_pages = os.sysconf("SC_PHYS_PAGES") if hasattr(os, "sysconf") else 0
    available_bytes: int | None = None
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                available_bytes = int(line.split()[1]) * 1024
                break
    total_ram = int(page_size * physical_pages) if page_size and physical_pages else None
    return {
        "captured_unix_s": time.time(),
        "cpu_count": os.cpu_count(),
        "total_ram_bytes": total_ram,
        "available_ram_bytes": available_bytes,
        "disk_total_bytes": disk.total,
        "disk_free_bytes": disk.free,
        "path": str(Path(path).resolve()),
    }


def execution_environment(path: Path) -> dict[str, Any]:
    """Record operationally relevant, non-secret execution context."""
    allowed = (
        "OMP_NUM_THREADS",
        "SLURM_JOB_ID",
        "SLURM_ARRAY_JOB_ID",
        "SLURM_ARRAY_TASK_ID",
        "SLURM_CPUS_PER_TASK",
        "SLURM_NTASKS",
        "SLURM_NODELIST",
    )
    return {
        "resource_snapshot": resource_snapshot(path),
        "selected_environment": {name: os.environ[name] for name in allowed if name in os.environ},
    }


def enforce_resource_safety(
    *,
    evidence_tier: str,
    output_path: Path,
    estimated_cells: int | None = None,
    raise_on_failure: bool = True,
) -> dict[str, Any]:
    snapshot = resource_snapshot(output_path)
    policy = load_policy()["resource_safety"]
    snapshot["evidence_tier"] = evidence_tier
    snapshot["estimated_cells"] = estimated_cells
    snapshot["estimated_memory_bytes"] = (
        None
        if estimated_cells is None
        else int(estimated_cells) * int(policy["memory_estimate_bytes_per_cell"])
    )
    failures: list[str] = []
    if evidence_tier == "laptop_smoke":
        available = snapshot["available_ram_bytes"]
        estimate = snapshot["estimated_memory_bytes"]
        if available is None:
            failures.append("available_ram_unknown")
        if estimate is None:
            failures.append("laptop_cell_estimate_unknown")
        elif (
            available is not None
            and estimate > float(policy["laptop_max_estimated_memory_fraction"]) * available
        ):
            failures.append("estimated_memory_exceeds_laptop_fraction")
        if snapshot["disk_free_bytes"] < float(policy["laptop_min_free_disk_gib"]) * 2**30:
            failures.append("free_disk_below_laptop_floor")
    if evidence_tier == "production":
        available = snapshot["available_ram_bytes"]
        disk_free = snapshot["disk_free_bytes"]
        if available is None and policy["refuse_production_if_unknown"]:
            failures.append("available_ram_unknown")
        elif (
            available is not None
            and available < float(policy["production_min_available_ram_gib"]) * 2**30
        ):
            failures.append("available_ram_below_production_floor")
        if disk_free < float(policy["production_min_free_disk_gib"]) * 2**30:
            failures.append("free_disk_below_production_floor")
        estimate = snapshot["estimated_memory_bytes"]
        if estimate is None and policy["refuse_production_if_unknown"]:
            failures.append("production_cell_estimate_unknown")
        elif estimate is not None and available is not None and estimate > 0.70 * available:
            failures.append("estimated_memory_exceeds_70_percent_available")
    snapshot["passed"] = not failures
    snapshot["failures"] = failures
    if failures and raise_on_failure:
        raise RuntimeError("resource preflight failed: " + ", ".join(failures))
    return snapshot


def run_logged(
    command: Sequence[str],
    *,
    cwd: Path,
    log_path: Path,
    timeout_s: float,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run a command without a shell and retain a complete combined log."""
    cwd = Path(cwd).resolve()
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    timed_out = False
    with log_path.open("w", encoding="utf-8", newline="") as stream:
        stream.write("COMMAND_JSON=" + canonical_json(list(command)) + "\n")
        stream.flush()
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=None if environment is None else {**os.environ, **dict(environment)},
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        deadline = started + float(timeout_s)
        peak_rss = 0
        while True:
            peak_rss = max(peak_rss, _process_tree_rss_bytes(process.pid))
            return_code = process.poll()
            if return_code is not None:
                break
            if time.time() >= deadline:
                timed_out = True
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    return_code = process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    return_code = process.wait(timeout=30)
                break
            time.sleep(0.25)
    ended = time.time()
    return {
        "command": list(command),
        "cwd": str(cwd),
        "return_code": int(return_code),
        "timed_out": timed_out,
        "started_unix_s": started,
        "ended_unix_s": ended,
        "wall_time_s": ended - started,
        "peak_process_tree_rss_bytes": int(peak_rss),
        "log": str(log_path.resolve()),
        "log_sha256": sha256_file(log_path),
    }


def digest_manifest(paths: Mapping[str, Path], *, required: Iterable[str] = ()) -> dict[str, Any]:
    required_names = set(required)
    result: dict[str, Any] = {}
    for name, path in sorted(paths.items()):
        path = Path(path)
        exists = path.is_file()
        result[name] = {
            "path": str(path.resolve()),
            "exists": exists,
            "bytes": path.stat().st_size if exists else None,
            "sha256": sha256_file(path) if exists else None,
            "required": name in required_names,
        }
    missing = [name for name in required_names if name not in result or not result[name]["exists"]]
    return {"algorithm": "sha256", "artifacts": result, "missing_required": sorted(missing)}


def verify_digest_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    mismatches: list[str] = []
    for name, record in manifest.get("artifacts", {}).items():
        path = Path(record["path"])
        if not path.is_file():
            if record.get("required"):
                mismatches.append(f"{name}:missing")
            continue
        actual = sha256_file(path)
        if actual != record.get("sha256"):
            mismatches.append(f"{name}:sha256")
    return {"passed": not mismatches, "mismatches": mismatches}
