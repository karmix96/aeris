from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from aeris.common.paths import DATASETS_DIR, ensure_base_directories
from aeris.dataset.models import DatasetPaths


def ensure_dataset_paths(dataset_name: str) -> DatasetPaths:
    ensure_base_directories()

    root = DATASETS_DIR / dataset_name
    geometry_dir = root / "geometry"
    configs_dir = root / "configs"
    logs_dir = root / "logs"

    root.mkdir(parents=True, exist_ok=False)
    geometry_dir.mkdir(parents=True, exist_ok=False)
    configs_dir.mkdir(parents=True, exist_ok=False)
    logs_dir.mkdir(parents=True, exist_ok=False)

    return DatasetPaths(
        root=root,
        geometry_dir=geometry_dir,
        configs_dir=configs_dir,
        logs_dir=logs_dir,
        manifest_path=root / "dataset_manifest.json",
        metadata_csv_path=root / "metadata.csv",
        failures_csv_path=root / "failures.csv",
        input_config_path=configs_dir / "input_config.yaml",
        resolved_config_json_path=configs_dir / "resolved_dataset_config.json",
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def append_csv_row(path: Path, row: dict[str, Any], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()

    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def ensure_csv_with_header(path: Path, fieldnames: list[str]) -> None:
    """
    Create an empty CSV with header if it does not already exist.
    Useful for failures.csv so the dataset structure is predictable even when there are zero failures.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()