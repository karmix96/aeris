"""
Module: paths

Purpose:
    Defines filesystem structure and run directory management.

Responsibilities:
    - Resolve project data directories
    - Create reproducible run folders
    - Generate unique run identifiers

Guarantees:
    - Run folders are unique (microsecond precision + retry)
    - Logs and artifacts directories always exist

Caveats:
    - Project root resolution assumes fixed repo structure

Future Improvements:
    - Add dataset-specific folder abstraction
    - Improve project root detection robustness
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
SRC_DIR = PACKAGE_DIR.parent
PROJECT_ROOT = SRC_DIR.parent.parent

CONFIGS_DIR = PROJECT_ROOT / "configs"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
DEBUG_DIR = DATA_DIR / "debug"
RUNS_DIR = DATA_DIR / "runs"
DATASETS_DIR = DATA_DIR / "datasets"


@dataclass(frozen=True)
class RunPaths:
    run_id: str
    root: Path
    logs: Path
    artifacts: Path


def ensure_base_directories() -> None:
    """Ensure the expected project data directories exist."""
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


def make_run_id(prefix: str = "run") -> str:
    """Create a UTC timestamped run ID with microseconds."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S_%f")
    return f"{timestamp}_{prefix}"


def create_run_folder(prefix: str = "run") -> RunPaths:
    ensure_base_directories()

    for _ in range(3):  # retry mechanism
        run_id = make_run_id(prefix=prefix)
        root = RUNS_DIR / run_id
        logs = root / "logs"
        artifacts = root / "artifacts"

        try:
            logs.mkdir(parents=True, exist_ok=False)
            artifacts.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            continue
    else:
        raise RuntimeError("Failed to create unique run directory")

    return RunPaths(run_id=run_id, root=root, logs=logs, artifacts=artifacts)