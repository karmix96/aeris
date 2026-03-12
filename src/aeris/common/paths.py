from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
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
    ):
        path.mkdir(parents=True, exist_ok=True)


def make_run_id(prefix: str = "run") -> str:
    """Create a UTC timestamped run ID."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    return f"{timestamp}_{prefix}"


def create_run_folder(prefix: str = "run") -> RunPaths:
    """Create a run folder with standard subdirectories."""
    ensure_base_directories()
    run_id = make_run_id(prefix=prefix)
    root = RUNS_DIR / run_id
    logs = root / "logs"
    artifacts = root / "artifacts"

    logs.mkdir(parents=True, exist_ok=False)
    artifacts.mkdir(parents=True, exist_ok=False)

    return RunPaths(
        run_id=run_id,
        root=root,
        logs=logs,
        artifacts=artifacts,
    )
