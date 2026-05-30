"""
Module: paths

Purpose:
    Filesystem structure and run directory management for AERIS.

This module is intentionally domain-neutral. It does not know about geometry,
aero, ML, dynamics, QC, or solver internals.

Design goals:
    - Work in editable installs:       pip install -e .
    - Work in normal package installs: pip install aeris.whl
    - Work on Windows/Linux/cloud/cluster environments
    - Keep source/config/data locations separable
    - Create safe, reproducible, collision-resistant run folders
    - Produce a reproducibility manifest per run

Environment variables:
    AERIS_PROJECT_ROOT:
        Optional project/workspace root. Highest priority. Useful when AERIS
        is installed as a package but you still want project-local configs and
        paths, or when a job scheduler supplies an explicit workspace.

    AERIS_CONFIGS_DIR or AERIS_CONFIG_ROOT:
        Optional explicit configs directory.

    AERIS_DATA_DIR or AERIS_DATA_ROOT:
        Optional explicit generated-data/output directory. Strongly recommended
        on clusters/cloud systems, e.g. $SCRATCH/aeris_data.

    AERIS_USE_CLUSTER_SCRATCH:
        If set to 1/true/yes/on and no explicit data dir is provided, AERIS will
        prefer SLURM_TMPDIR, SCRATCH, or TMPDIR for generated outputs.

Project-root resolution order:
    1. AERIS_PROJECT_ROOT environment variable
    2. Nearest pyproject.toml ancestor of the current working directory
    3. Nearest pyproject.toml ancestor of this source file
    4. Current working directory (fallback)

    Step 2 is intentionally checked before step 3. This makes a single
    pip-installed AERIS work correctly across many user workspaces: the user's
    workspace wins over the AERIS source tree.

Guarantees:
    - Uses pathlib for cross-platform paths.
    - Module-level constants (PROJECT_ROOT, CONFIGS_DIR, DATA_DIR, etc.) are
      resolved once at import time, for backwards compatibility.
    - Live resolvers (get_project_root, get_configs_dir, get_data_dir,
      get_runs_dir, get_datasets_dir) re-resolve at call time. Use these in
      long-running processes (cloud workers, tests) where environment may
      change after import.
    - Run folders are timestamped and collision-resistant (token_hex retry).
    - Run prefixes are sanitized to avoid path traversal and ugly folder names.
    - RunPaths exposes a standard manifest path.
    - write_run_manifest captures git commit, package version, platform, and
      env snapshot for reproducibility.
"""

from __future__ import annotations

import json
import os
import platform
import re
import socket
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_hex
from typing import Any

__all__ = [
    # Package-location constants
    "AERIS_PACKAGE_DIR",
    "SRC_DIR",
    # Resolved project layout (import-time)
    "PROJECT_ROOT",
    "CONFIGS_DIR",
    "DATA_DIR",
    "RAW_DIR",
    "INTERIM_DIR",
    "PROCESSED_DIR",
    "DEBUG_DIR",
    "RUNS_DIR",
    "DATASETS_DIR",
    # Dataclass
    "RunPaths",
    # Live resolvers
    "get_project_root",
    "get_configs_dir",
    "get_data_dir",
    "get_runs_dir",
    "get_datasets_dir",
    # Core utilities
    "ensure_base_directories",
    "ensure_output_directories_writable",
    "make_run_id",
    "create_run_folder",
    # Manifest + diagnostics
    "write_run_manifest",
    "describe_path_environment",
]

_MAX_PREFIX_LEN = 80
_UNSAFE_PREFIX_CHARS = re.compile(r"[^A-Za-z0-9_-]+")

_TRUE_VALUES = {"1", "true", "yes", "on", "y"}


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def _env_truthy(var_name: str) -> bool:
    value = os.getenv(var_name, "")
    return value.strip().lower() in _TRUE_VALUES


def _resolve_existing_env_dir(*var_names: str) -> Path | None:
    """Resolve the first set environment variable as an existing directory."""
    for var_name in var_names:
        raw = os.getenv(var_name)
        if raw is None or not raw.strip():
            continue

        path = Path(raw).expanduser().resolve()

        if not path.exists():
            raise FileNotFoundError(f"{var_name} does not exist: {path}")
        if not path.is_dir():
            raise NotADirectoryError(f"{var_name} is not a directory: {path}")

        return path

    return None


def _find_project_root_from_file() -> Path | None:
    """Walk upward from this source file and look for pyproject.toml."""
    here = Path(__file__).resolve()

    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent

    return None


def _find_project_root_from_cwd() -> Path | None:
    """Walk upward from the current working directory and look for pyproject.toml."""
    here = Path.cwd().resolve()

    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate

    return None


def _platform_user_data_dir() -> Path:
    """Return an OS-appropriate user data directory.

    Uses platformdirs if available. Falls back to ~/.aeris/data without adding
    a hard runtime dependency.
    """
    try:
        from platformdirs import user_data_dir  # type: ignore

        return Path(user_data_dir("aeris", "AERIS")).expanduser().resolve()
    except Exception:
        return (Path.home() / ".aeris" / "data").expanduser().resolve()


def _platform_user_config_dir() -> Path:
    """Return an OS-appropriate user config directory.

    Uses platformdirs if available. Falls back to ~/.aeris/configs without
    adding a hard runtime dependency.
    """
    try:
        from platformdirs import user_config_dir  # type: ignore

        return Path(user_config_dir("aeris", "AERIS")).expanduser().resolve()
    except Exception:
        return (Path.home() / ".aeris" / "configs").expanduser().resolve()


def _detect_project_root() -> Path:
    """Resolve the AERIS project/workspace root.

    Resolution order:
        1. AERIS_PROJECT_ROOT environment variable
        2. Nearest pyproject.toml ancestor from current working directory
           (user-workspace context wins for the GUI/cloud/multi-workspace case)
        3. Nearest pyproject.toml ancestor from this source file
           (AERIS source tree fallback, useful for pure dev work)
        4. Current working directory (final fallback)
    """
    env_root = _resolve_existing_env_dir("AERIS_PROJECT_ROOT")
    if env_root is not None:
        return env_root

    cwd_root = _find_project_root_from_cwd()
    if cwd_root is not None:
        return cwd_root

    source_root = _find_project_root_from_file()
    if source_root is not None:
        return source_root

    return Path.cwd().resolve()


def _cluster_scratch_data_dir() -> Path | None:
    """Return a cluster scratch data directory if explicitly enabled."""
    if not _env_truthy("AERIS_USE_CLUSTER_SCRATCH"):
        return None

    scratch_root = _resolve_existing_env_dir("SLURM_TMPDIR", "SCRATCH", "TMPDIR")
    if scratch_root is None:
        return None

    return scratch_root / "aeris_data"


def _resolve_configs_dir(project_root: Path) -> Path:
    """Resolve the configs directory.

    Resolution order:
        1. AERIS_CONFIGS_DIR or AERIS_CONFIG_ROOT env var
        2. project_root/configs if project_root looks like a source tree
           (i.e. contains pyproject.toml) — even if the directory does not
           yet exist
        3. Platform user config dir (packaged-install fallback)
    """
    env_dir = _resolve_existing_env_dir("AERIS_CONFIGS_DIR", "AERIS_CONFIG_ROOT")
    if env_dir is not None:
        return env_dir

    if (project_root / "pyproject.toml").exists():
        return project_root / "configs"

    return _platform_user_config_dir()


def _resolve_data_dir(project_root: Path) -> Path:
    """Resolve the generated data/output directory.

    Resolution order:
        1. AERIS_DATA_DIR or AERIS_DATA_ROOT env var
        2. Cluster scratch dir if AERIS_USE_CLUSTER_SCRATCH is enabled
        3. project_root/data if project_root looks like a source tree
        4. Platform user data dir (packaged-install fallback)
    """
    env_dir = _resolve_existing_env_dir("AERIS_DATA_DIR", "AERIS_DATA_ROOT")
    if env_dir is not None:
        return env_dir

    scratch_dir = _cluster_scratch_data_dir()
    if scratch_dir is not None:
        return scratch_dir.expanduser().resolve()

    if (project_root / "pyproject.toml").exists():
        return project_root / "data"

    return _platform_user_data_dir()


# ---------------------------------------------------------------------------
# Package directory constants (file-derived, env-independent)
# ---------------------------------------------------------------------------

COMMON_DIR = Path(__file__).resolve().parent          # .../aeris/common
AERIS_PACKAGE_DIR = COMMON_DIR.parent                 # .../aeris
SRC_DIR = AERIS_PACKAGE_DIR.parent                    # .../src


# ---------------------------------------------------------------------------
# Resolved project layout (import-time; for backwards compatibility)
# ---------------------------------------------------------------------------

PROJECT_ROOT = _detect_project_root()

CONFIGS_DIR = _resolve_configs_dir(PROJECT_ROOT)
DATA_DIR = _resolve_data_dir(PROJECT_ROOT)

RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
DEBUG_DIR = DATA_DIR / "debug"
RUNS_DIR = DATA_DIR / "runs"
DATASETS_DIR = DATA_DIR / "datasets"


# ---------------------------------------------------------------------------
# Live resolvers (call-time; for long-running workers, tests, GUI/cloud)
# ---------------------------------------------------------------------------


def get_project_root() -> Path:
    """Resolve the AERIS project root at call time.

    Unlike the module-level PROJECT_ROOT constant, this function re-evaluates
    environment variables on each call. Use this in long-running processes
    (cloud workers, tests) where the environment may change after import.
    """
    return _detect_project_root()


def get_configs_dir() -> Path:
    """Resolve the configs directory at call time."""
    return _resolve_configs_dir(get_project_root())


def get_data_dir() -> Path:
    """Resolve the generated data/output directory at call time."""
    return _resolve_data_dir(get_project_root())


def get_runs_dir() -> Path:
    """Resolve the runs directory at call time."""
    return get_data_dir() / "runs"


def get_datasets_dir() -> Path:
    """Resolve the datasets directory at call time."""
    return get_data_dir() / "datasets"


# ---------------------------------------------------------------------------
# Run paths
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunPaths:
    """Standard per-run filesystem paths."""

    run_id: str
    root: Path
    logs: Path
    artifacts: Path

    @property
    def manifest(self) -> Path:
        """Default manifest path for this run."""
        return self.root / "manifest.json"


def ensure_base_directories() -> None:
    """Ensure the expected AERIS base directories exist."""
    for path in (
        CONFIGS_DIR,
        DATA_DIR,
        RAW_DIR,
        INTERIM_DIR,
        PROCESSED_DIR,
        DEBUG_DIR,
        RUNS_DIR,
        DATASETS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _ensure_writable_dir(path: Path) -> None:
    """Create and verify that a directory is writable."""
    path.mkdir(parents=True, exist_ok=True)

    probe = path / f".aeris_write_test_{os.getpid()}_{token_hex(4)}"
    try:
        probe.write_text("ok", encoding="utf-8")
    except OSError as exc:
        raise PermissionError(f"AERIS directory is not writable: {path}") from exc
    finally:
        try:
            probe.unlink()
        except FileNotFoundError:
            pass


def ensure_output_directories_writable() -> None:
    """Verify that generated-output directories can be written.

    Call this once at CLI/worker startup. Raises PermissionError early with a
    clear message if a target directory is on a read-only filesystem.
    """
    for path in (DATA_DIR, RUNS_DIR, DATASETS_DIR):
        _ensure_writable_dir(path)


def _sanitize_run_prefix(prefix: str) -> str:
    """Return a filesystem-safe run prefix.

    This prevents path traversal, spaces/slashes/dots from user-facing labels,
    and extremely long folder names.
    """
    clean = str(prefix).strip()
    clean = _UNSAFE_PREFIX_CHARS.sub("_", clean)
    clean = clean.strip("_")

    if not clean:
        raise ValueError("Run prefix must contain at least one valid character.")

    return clean[:_MAX_PREFIX_LEN]


def make_run_id(prefix: str = "run") -> str:
    """Create a UTC timestamped run ID with a filesystem-safe prefix."""
    safe_prefix = _sanitize_run_prefix(prefix)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S_%f")
    return f"{timestamp}_{safe_prefix}"


def create_run_folder(prefix: str = "run") -> RunPaths:
    """Create a unique run folder with logs and artifacts directories.

    The root directory is created with exist_ok=False, so accidental reuse of
    an existing run folder fails instead of silently mixing outputs. Retry
    attempts add a short random suffix, so uniqueness does not depend only on
    clock precision (important for parallel workers and low-resolution clocks
    on Windows).
    """
    ensure_base_directories()
    _ensure_writable_dir(RUNS_DIR)

    last_root: Path | None = None

    for attempt in range(10):
        run_id = make_run_id(prefix=prefix)

        if attempt > 0:
            run_id = f"{run_id}_{token_hex(3)}"

        root = RUNS_DIR / run_id
        logs = root / "logs"
        artifacts = root / "artifacts"
        last_root = root

        try:
            root.mkdir(parents=True, exist_ok=False)
            logs.mkdir(parents=False, exist_ok=False)
            artifacts.mkdir(parents=False, exist_ok=False)
            return RunPaths(
                run_id=run_id,
                root=root,
                logs=logs,
                artifacts=artifacts,
            )
        except FileExistsError:
            continue

    raise RuntimeError(
        f"Failed to create unique run directory under {RUNS_DIR}. "
        f"Last attempted path: {last_root}"
    )


# ---------------------------------------------------------------------------
# Reproducibility manifest
# ---------------------------------------------------------------------------


def _get_git_commit() -> str | None:
    """Return the AERIS source-tree git commit SHA if available.

    Uses AERIS_PACKAGE_DIR as the git cwd so the command resolves the AERIS
    code commit, not the user's workspace commit. Returns None if git is not
    installed, the working tree is not a git repo (packaged install), or the
    call times out.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(AERIS_PACKAGE_DIR),
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return None


def _get_package_version() -> str:
    """Return the installed AERIS package version, or 'unknown'."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("aeris")
        except PackageNotFoundError:
            return "unknown"
    except Exception:
        return "unknown"


def write_run_manifest(
    run: RunPaths,
    *,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Write a JSON manifest with reproducibility metadata for a run.

    The manifest captures the minimum information needed to reproduce or audit
    the run later: timestamp, hostname, platform, Python version, AERIS
    package version, git commit (if available), resolved AERIS paths, command
    line, and a snapshot of AERIS_* and cluster scratch env vars.

    Domain layers can pass additional fields via `extra` (e.g. dataset name,
    solver, model type, config file path + sha256). These are merged into the
    top-level manifest dictionary. Keys in `extra` override built-in keys.

    Returns:
        The manifest file path (run.manifest).
    """
    manifest: dict[str, Any] = {
        "run_id": run.run_id,
        "run_root": str(run.root),
        "created_at_utc": datetime.now(UTC).isoformat(),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "aeris_version": _get_package_version(),
        "git_commit": _get_git_commit(),
        "command_line": " ".join(sys.argv),
        "paths": describe_path_environment(),
    }

    if extra:
        manifest.update(extra)

    run.manifest.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return run.manifest


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def describe_path_environment() -> dict[str, str]:
    """Return a diagnostic snapshot of resolved AERIS paths and env vars.

    Uses the module-level constants (import-time resolution). For live values,
    call the get_* resolvers separately.
    """
    return {
        "python_executable": sys.executable,
        "project_root": str(PROJECT_ROOT),
        "configs_dir": str(CONFIGS_DIR),
        "data_dir": str(DATA_DIR),
        "runs_dir": str(RUNS_DIR),
        "datasets_dir": str(DATASETS_DIR),
        "aeris_project_root_env": os.getenv("AERIS_PROJECT_ROOT", ""),
        "aeris_configs_dir_env": os.getenv("AERIS_CONFIGS_DIR", ""),
        "aeris_config_root_env": os.getenv("AERIS_CONFIG_ROOT", ""),
        "aeris_data_dir_env": os.getenv("AERIS_DATA_DIR", ""),
        "aeris_data_root_env": os.getenv("AERIS_DATA_ROOT", ""),
        "aeris_use_cluster_scratch_env": os.getenv("AERIS_USE_CLUSTER_SCRATCH", ""),
        "slurm_tmpdir_env": os.getenv("SLURM_TMPDIR", ""),
        "scratch_env": os.getenv("SCRATCH", ""),
        "tmpdir_env": os.getenv("TMPDIR", ""),
    }