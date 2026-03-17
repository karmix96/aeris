from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatasetPaths:
    root: Path
    geometry_dir: Path
    configs_dir: Path
    logs_dir: Path
    manifest_path: Path
    metadata_csv_path: Path
    failures_csv_path: Path
    input_config_path: Path
    resolved_config_json_path: Path


@dataclass(frozen=True)
class DatasetRunStats:
    requested_n: int
    attempted_n: int
    succeeded_n: int
    failed_n: int