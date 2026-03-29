from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def require_promoted_aero_dataset(
    *,
    dataset_root: Path,
    allow_forced: bool = False,
) -> dict[str, Any]:
    """
    Validate that a dataset is promoted and safe for downstream trusted use.

    Returns a small resolved context bundle containing:
    - dataset_root
    - promotion_manifest
    - curated_aero_dataset_csv path
    - curation_report path
    - final_run_summary path

    Rules:
    - promotion_manifest.json must exist
    - curated_aero_dataset.csv must exist
    - if promotion was forced, caller must explicitly allow it
    """
    dataset_root = dataset_root.expanduser().resolve()

    promotion_manifest_path = dataset_root / "promotion_manifest.json"
    curation_report_path = dataset_root / "curation_report.json"
    final_run_summary_path = dataset_root / "final_run_summary.json"

    promotion_manifest = _read_json(promotion_manifest_path)

    curated_csv_value = (
        promotion_manifest.get("artifacts", {}) or {}
    ).get("curated_aero_dataset_csv")
    if not curated_csv_value:
        raise ValueError(
            "promotion_manifest.json is missing artifacts.curated_aero_dataset_csv"
        )

    curated_csv_path = Path(curated_csv_value).expanduser().resolve()
    if not curated_csv_path.exists():
        raise FileNotFoundError(
            f"Promoted curated dataset CSV not found: {curated_csv_path}"
        )

    promotion_forced = bool(promotion_manifest.get("promotion_forced", False))
    if promotion_forced and not allow_forced:
        raise ValueError(
            "Dataset was force-promoted. "
            "Set allow_forced=True only if downstream use explicitly permits that."
        )

    return {
        "dataset_root": str(dataset_root),
        "promotion_manifest_path": str(promotion_manifest_path),
        "curation_report_path": str(curation_report_path),
        "final_run_summary_path": str(final_run_summary_path),
        "curated_aero_dataset_csv": str(curated_csv_path),
        "promotion_manifest": promotion_manifest,
    }


def load_promoted_aero_dataset(
    *,
    dataset_root: Path,
    allow_forced: bool = False,
):
    """
    Convenience wrapper around require_promoted_aero_dataset() that also loads the curated CSV.
    """
    import pandas as pd

    context = require_promoted_aero_dataset(
        dataset_root=dataset_root,
        allow_forced=allow_forced,
    )
    df = pd.read_csv(context["curated_aero_dataset_csv"])
    context["dataframe"] = df
    return context