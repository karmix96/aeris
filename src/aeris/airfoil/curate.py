"""
2D airfoil dataset curation.

Mirrors curate_aero.py exactly:
  - reads airfoil_dataset.csv
  - applies rejection rules
  - writes curated_airfoil_dataset.csv + rejected_airfoil_rows.csv
  - writes curation_report.json with promotion_ready flag
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

REQUIRED_TARGETS = ["cl", "cd", "cm"]
GROUP_KEY = "airfoil_id"


def _is_finite(v: Any) -> bool:
    if pd.isna(v):
        return False
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def curate_airfoil_dataset(
    *,
    dataset_root: Path,
    reject_unconverged: bool = True,
    reject_nonfinite_targets: bool = True,
    reject_negative_cd: bool = True,
) -> dict[str, Any]:
    """Curate the raw 2D airfoil dataset.

    Returns a report dict. Mirrors the 3D curate_aero_dataset() contract.
    """
    dataset_root = dataset_root.expanduser().resolve()
    csv_path = dataset_root / "airfoil_dataset.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"airfoil_dataset.csv not found at {csv_path}")

    df = pd.read_csv(csv_path)
    rejection_reasons: list[str] = []
    rejected_masks: dict[str, pd.Series] = {}

    if reject_unconverged and "converged" in df.columns:
        mask = df["converged"] != True  # noqa: E712
        if mask.any():
            rejected_masks["unconverged"] = mask
            rejection_reasons.extend(["unconverged"] * int(mask.sum()))

    if reject_negative_cd and "cd" in df.columns:
        mask = (df["cd"].notna()) & (df["cd"] <= 0)
        if mask.any():
            rejected_masks["negative_cd"] = mask

    if reject_nonfinite_targets:
        for col in REQUIRED_TARGETS:
            if col in df.columns:
                mask = ~df[col].apply(_is_finite)
                if mask.any():
                    rejected_masks[f"nonfinite_{col}"] = mask

    # Union of all rejection masks
    if rejected_masks:
        combined = pd.concat(list(rejected_masks.values()), axis=1).any(axis=1)
    else:
        combined = pd.Series(False, index=df.index)

    kept_df     = df[~combined].copy()
    rejected_df = df[combined].copy()

    # Rejection reason column
    if not rejected_df.empty:
        reasons_per_row = []
        for idx in rejected_df.index:
            r = [name for name, mask in rejected_masks.items() if mask.loc[idx]]
            reasons_per_row.append("|".join(r) if r else "unknown")
        rejected_df = rejected_df.copy()
        rejected_df["rejection_reason"] = reasons_per_row

    kept_airfoils     = set(kept_df[GROUP_KEY].unique()) if GROUP_KEY in kept_df.columns else set()
    rejected_airfoils = set(rejected_df[GROUP_KEY].unique()) if GROUP_KEY in rejected_df.columns else set()

    reason_counts: dict[str, int] = {}
    for name, mask in rejected_masks.items():
        reason_counts[name] = int(mask.sum())

    # QC pass — check airfoil_qc_report.json if it exists
    qc_report_path = dataset_root / "airfoil_qc_report.json"
    qc_passed = None
    qc_report_found = qc_report_path.exists()
    if qc_report_found:  # AERIS_PATCH_C12_APPLIED
        try:
            qc = json.loads(qc_report_path.read_text(encoding="utf-8"))
            qc_passed = bool(qc.get("passed", None))
        except Exception:
            pass

    promotion_blockers: list[str] = []
    if not qc_report_found:
        # QC was never run — fail loud so operator cannot silently promote
        # unverified data. Use `aeris airfoil dataset qc` first.
        promotion_blockers.append("airfoil_qc_not_run")
    elif qc_passed is False:
        promotion_blockers.append("airfoil_qc_failed")
    if kept_df.empty:
        promotion_blockers.append("no_rows_after_curation")

    promotion_ready = len(promotion_blockers) == 0

    curated_csv  = dataset_root / "curated_airfoil_dataset.csv"
    rejected_csv = dataset_root / "rejected_airfoil_rows.csv"
    kept_df.to_csv(curated_csv, index=False)
    rejected_df.to_csv(rejected_csv, index=False)

    report: dict[str, Any] = {  # AERIS_PATCH_C5_APPLIED: added generated_at_utc
        "schema_version": "airfoil_curation_v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "dataset_root": str(dataset_root),
        "kept_rows": len(kept_df),
        "rejected_rows": len(rejected_df),
        "kept_airfoils": len(kept_airfoils),
        "rejected_airfoils": len(rejected_airfoils),
        "rejection_reason_counts": reason_counts,
        "qc_passed": qc_passed,
        "promotion_ready": promotion_ready,
        "promotion_blockers": promotion_blockers,
        "curated_airfoil_dataset_csv": str(curated_csv),
        "rejected_airfoil_rows_csv": str(rejected_csv),
    }
    report_path = dataset_root / "curation_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
