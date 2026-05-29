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

Environment variables:
    AERIS_PROJECT_ROOT:
        Optional project/workspace root. Useful when AERIS is installed as a
        package but you still want project-local configs and paths.

    AERIS_CONFIGS_DIR or AERIS_CONFIG_ROOT:
        Optional explicit configs directory.

    AERIS_DATA_DIR or AERIS_DATA_ROOT:
        Optional explicit generated-data/output directory. Strongly recommended
        on clusters/cloud systems, e.g. $SCRATCH/aeris_data.

    AERIS_USE_CLUSTER_SCRATCH:
        If set to 1/true/yes/on and no explicit data dir is provided, AERIS will
        prefer SLURM_TMPDIR, SCRATCH, or TMPDIR for generated outputs.

Guarantees:
    - Uses pathlib for cross-platform paths.
    - Existing legacy constants remain available: CONFIGS_DIR, DATA_DIR, RUNS_DIR, etc.
    - Run folders are timestamped and collision-resistant.
    - Run prefixes are sanitized to avoid path traversal and ugly folder names.
    - RunPaths includes the standard manifest path.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_hex

_MAX_PREFIX_LEN = 80
_UNSAFE_PREFIX_CHARS = re.compile(r"[^A-Za-z0-9_-]+")

_TRUE_VALUES = {"1", "true", "yes", "on", "y"}


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
    """Walk upward from this file and look for pyproject.toml."""
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

    Uses platformdirs if available. Falls back to ~/.aeris/data without adding a
    hard runtime dependency.
    """
    try:
        from platformdirs import user_data_dir  # type: ignore

        return Path(user_data_dir("aeris", "AERIS")).expanduser().resolve()
    except Exception:
        return (Path.home() / ".aeris" / "data").expanduser().resolve()


def _platform_user_config_dir() -> Path:
    """Return an OS-appropriate user config directory.

    Uses platformdirs if available. Falls back to ~/.aeris/configs without adding
    a hard runtime dependency.
    """
    try:
        from platformdirs import user_config_dir  # type: ignore

        return Path(user_config_dir("aeris", "AERIS")).expanduser().resolve()
    except Exception:
        return (Path.home() / ".aeris" / "configs").expanduser().resolve()


def _detect_project_root() -> Path:
    """Resolve the AERIS project/workspace root.

    Resolution order:
        1. AERIS_PROJECT_ROOT
        2. Nearest pyproject.toml ancestor from this file
        3. Nearest pyproject.toml ancestor from current working directory
        4. Current working directory

    The current-working-directory fallback is deliberate. In packaged/cloud
    usage, code may live in site-packages, while the user launches AERIS from a
    project/workspace directory.
    """
    env_root = _resolve_existing_env_dir("AERIS_PROJECT_ROOT")
    if env_root is not None:
        return env_root

    source_root = _find_project_root_from_file()
    if source_root is not None:
        return source_root

    cwd_root = _find_project_root_from_cwd()
    if cwd_root is not None:
        return cwd_root

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
    """Resolve the configs directory."""
    env_dir = _resolve_existing_env_dir("AERIS_CONFIGS_DIR", "AERIS_CONFIG_ROOT")
    if env_dir is not None:
        return env_dir

    project_configs = project_root / "configs"
    if project_configs.exists():
        return project_configs

    # Packaged install fallback.
    return _platform_user_config_dir()


def _resolve_data_dir(project_root: Path) -> Path:
    """Resolve the generated data/output directory."""
    env_dir = _resolve_existing_env_dir("AERIS_DATA_DIR", "AERIS_DATA_ROOT")
    if env_dir is not None:
        return env_dir

    scratch_dir = _cluster_scratch_data_dir()
    if scratch_dir is not None:
        return scratch_dir.expanduser().resolve()

    project_data = project_root / "data"

    # In source-tree/editable workflows, keep the familiar project/data default.
    if (project_root / "pyproject.toml").exists():
        return project_data

    # Packaged install fallback.
    return _platform_user_data_dir()


COMMON_DIR = Path(__file__).resolve().parent
AERIS_PACKAGE_DIR = COMMON_DIR.parent
SRC_DIR = AERIS_PACKAGE_DIR.parent

PROJECT_ROOT = _detect_project_root()

CONFIGS_DIR = _resolve_configs_dir(PROJECT_ROOT)
DATA_DIR = _resolve_data_dir(PROJECT_ROOT)

RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
DEBUG_DIR = DATA_DIR / "debug"
RUNS_DIR = DATA_DIR / "runs"
DATASETS_DIR = DATA_DIR / "datasets"


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
    """Verify that generated-output directories can be written."""
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

    The root directory is created with exist_ok=False, so accidental reuse of an
    existing run folder fails instead of silently mixing outputs. Retry attempts
    add a short random suffix, so uniqueness does not depend only on clock
    precision.
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


def describe_path_environment() -> dict[str, str]:
    """Return a small diagnostic snapshot of resolved AERIS paths."""
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
    }