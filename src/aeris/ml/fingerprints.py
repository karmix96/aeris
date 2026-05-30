"""
Reproducibility fingerprints for AERIS ML runs.

This module is deliberately small and dependency-light. It provides stable file
hashes and dataset artifact fingerprints so every trained model can be traced
back to the exact curated/promotion inputs that produced it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def file_sha256(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return SHA256 for a file using bounded memory."""
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"Cannot fingerprint missing file: {file_path}")
    if not file_path.is_file():
        raise ValueError(f"Can only fingerprint files, got: {file_path}")

    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_sha256(payload: Any) -> str:
    """Return SHA256 for JSON-serializable content with stable key ordering."""
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def optional_file_fingerprint(path: str | Path | None) -> dict[str, Any]:
    """Fingerprint a file if present; otherwise return an explicit missing record."""
    if path is None:
        return {"path": None, "exists": False, "sha256": None, "size_bytes": None}

    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        return {
            "path": str(file_path),
            "exists": False,
            "sha256": None,
            "size_bytes": None,
        }

    return {
        "path": str(file_path),
        "exists": True,
        "sha256": file_sha256(file_path),
        "size_bytes": int(file_path.stat().st_size),
    }


def build_dataset_fingerprints(
    *,
    dataset_path: str | Path,
    curated_csv_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    Build the core dataset fingerprints used by ML manifests.

    The curated CSV and promotion manifest are the load-bearing inputs for ML.
    Additional files are included when present, but they are not required for
    baseline tabular training.
    """
    dataset_root = Path(dataset_path).expanduser().resolve()
    curated_path = (
        Path(curated_csv_path).expanduser().resolve()
        if curated_csv_path is not None
        else dataset_root / "curated_aero_dataset.csv"
    )

    files = {
        "curated_aero_dataset_csv": curated_path,
        "promotion_manifest_json": dataset_root / "promotion_manifest.json",
        "curation_report_json": dataset_root / "curation_report.json",
        "aero_dataset_manifest_json": dataset_root / "aero_dataset_manifest.json",
        "final_run_summary_json": dataset_root / "final_run_summary.json",
    }

    return {
        "dataset_root": str(dataset_root),
        "files": {
            name: optional_file_fingerprint(path)
            for name, path in files.items()
        },
    }
