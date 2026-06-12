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
    # IO-1: reject names that would create path-traversal or shell-unsafe directories
    if not dataset_name or dataset_name.strip() != dataset_name:
        raise ValueError(f"dataset_name must be non-empty and have no leading/trailing whitespace: {dataset_name!r}")
    _bad_chars = set("/\\ \t\n\r\x00")
    if any(c in _bad_chars for c in dataset_name) or dataset_name in (".", ".."):
        raise ValueError(
            f"dataset_name contains invalid characters or is a reserved name: {dataset_name!r}. "
            "Use only alphanumeric characters, hyphens, and underscores."
        )
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
    # IO-2: atomic write — write to temp file then replace to avoid
    # corrupt JSON if the process is interrupted mid-write.
    import tempfile, os
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        os.write(fd, text.encode("utf-8"))
        os.close(fd)
        os.replace(tmp, path)
    except Exception:
        os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


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
        # IO-3: warn if existing header does not match expected schema
        try:
            import csv as _csv
            with path.open("r", encoding="utf-8", newline="") as _fh:
                existing_header = next(_csv.reader(_fh), None)
            if existing_header is not None and existing_header != fieldnames:
                import warnings as _w
                _w.warn(
                    f"ensure_csv_with_header: existing header in {path} does not match "
                    f"expected schema. Expected {len(fieldnames)} columns, "
                    f"found {len(existing_header)}. Will not overwrite.",
                    stacklevel=2,
                )
        except StopIteration:
            pass
        return

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()