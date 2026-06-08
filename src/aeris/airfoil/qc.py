"""
2D airfoil dataset QC.

Checks:
  1. Convergence rate per airfoil  (warn if < MIN_CONVERGENCE_RATE)
  2. cd > 0 on all converged rows
  3. All target columns finite on converged rows
  4. No duplicate (airfoil_id, alpha_deg, reynolds, mach) keys
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

MIN_CONVERGENCE_RATE = 0.40   # warn below this per-airfoil rate

REQUIRED_TARGETS = ["cl", "cd", "cm"]
REQUIRED_COLUMNS = [
    "airfoil_id", "alpha_deg", "reynolds", "mach", "ncrit",
    "cl", "cd", "cm", "converged",
]


def run_airfoil_dataset_qc(
    *,
    dataset_root: Path,
) -> dict[str, Any]:
    """Run QC on the raw airfoil_dataset.csv.

    Writes airfoil_qc_report.json and returns the report dict.
    """
    dataset_root = dataset_root.expanduser().resolve()
    csv_path = dataset_root / "airfoil_dataset.csv"
    if not csv_path.exists():
        raise FileNotFoundError(
            f"airfoil_dataset.csv not found at {csv_path}. "
            "Run 'aeris airfoil dataset generate' first."
        )

    df = pd.read_csv(csv_path)
    issues: list[str] = []
    warnings_list: list[str] = []

    # 1. Required columns
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        issues.append(f"Missing required columns: {missing_cols}")

    if not df.empty and not missing_cols:
        converged = df[df["converged"] == True]  # noqa: E712

        # 2. cd > 0
        bad_cd = converged[converged["cd"] <= 0]
        if len(bad_cd) > 0:
            issues.append(f"{len(bad_cd)} converged rows have cd <= 0")

        # 3. Non-finite targets
        for col in REQUIRED_TARGETS:
            if col in converged.columns:
                n_bad = converged[col].apply(
                    lambda v: not math.isfinite(float(v)) if pd.notna(v) else True
                ).sum()
                if n_bad > 0:
                    issues.append(f"{n_bad} converged rows have non-finite {col}")

        # 4. Duplicates
        key_cols = [c for c in ["airfoil_id", "alpha_deg", "reynolds", "mach"]
                    if c in df.columns]
        n_dup = df.duplicated(subset=key_cols).sum()
        if n_dup > 0:
            issues.append(f"{n_dup} duplicate (airfoil_id, alpha, Re, Mach) rows")

        # 5. Per-airfoil convergence rate
        low_conv: list[str] = []
        for aid, grp in df.groupby("airfoil_id"):
            rate = grp["converged"].sum() / max(len(grp), 1)
            if rate < MIN_CONVERGENCE_RATE:
                low_conv.append(f"{aid} ({rate:.0%})")
        if low_conv:
            warnings_list.append(
                f"{len(low_conv)} airfoils below {MIN_CONVERGENCE_RATE:.0%} convergence: "
                + ", ".join(low_conv[:5])
                + ("..." if len(low_conv) > 5 else "")
            )

    passed = len(issues) == 0
    report: dict[str, Any] = {
        "schema_version": "airfoil_qc_v1",
        "dataset_root": str(dataset_root),
        "passed": passed,
        "total_rows": len(df),
        "converged_rows": int(df["converged"].sum()) if "converged" in df.columns else 0,
        "issues": issues,
        "warnings": warnings_list,
    }
    report_path = dataset_root / "airfoil_qc_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
