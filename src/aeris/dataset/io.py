"""
Filesystem and persistence helpers for AERIS datasets.

This module creates the canonical dataset directory layout and provides simple
JSON/CSV write utilities used by dataset generation and inspection code.
The functions are intentionally minimal and avoid embedding business logic.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from aeris.common.paths import DATASETS_DIR, ensure_base_directories
from aeris.dataset.models import DatasetPaths


def _validate_csv_row_keys(row: dict[str, Any], fieldnames: list[str]) -> None:
    row_keys = set(row.keys())
    expected_keys = set(fieldnames)

    extra = sorted(row_keys - expected_keys)
    missing = sorted(expected_keys - row_keys)

    if extra or missing:
        problems: list[str] = []
        if extra:
            problems.append(f"extra keys: {extra}")
        if missing:
            problems.append(f"missing keys: {missing}")
        raise ValueError("CSV row does not match declared schema: " + "; ".join(problems))


def ensure_dataset_paths(dataset_name: str) -> DatasetPaths:
    ensure_base_directories()

    root = DATASETS_DIR / dataset_name
    geometry_dir = root / "geometry"
    configs_dir = root / "configs"
    logs_dir = root / "logs"

    try:
        root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise FileExistsError(
            f"Dataset root already exists: {root}. "
            "Choose a different dataset name or remove the existing dataset first."
        ) from exc

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
    _validate_csv_row_keys(row, fieldnames)

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