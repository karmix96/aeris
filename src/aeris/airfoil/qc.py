"""
2D airfoil dataset QC.

Checks:
  1. Convergence rate per airfoil  (warn if < MIN_CONVERGENCE_RATE)
  2. cd > 0 on all converged rows
  3. All target columns finite on converged rows
  4. No duplicate (airfoil_id, alpha_deg, reynolds, mach, ncrit) keys
  5. Warn if fewer than MIN_USABLE_ROWS converged rows per (airfoil_id, Re, Mach) group
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

MIN_CONVERGENCE_RATE = 0.40   # warn below this per-airfoil rate
MIN_USABLE_ROWS = 3

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
    per_group_coverage_failures: list[dict[str, Any]] = []

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
        key_cols = [c for c in ["airfoil_id", "alpha_deg", "reynolds", "mach", "ncrit"]
                    if c in df.columns]
        n_dup = df.duplicated(subset=key_cols).sum()
        if n_dup > 0:
            issues.append(f"{n_dup} duplicate (airfoil_id, alpha, Re, Mach, ncrit) rows")

        # 5. Per-condition coverage
        group_cols = ["airfoil_id", "reynolds", "mach"]
        for name, grp in df.groupby(group_cols, dropna=False):
            converged_count = int((grp["converged"] == True).sum())  # noqa: E712
            if converged_count < MIN_USABLE_ROWS:
                airfoil_id, reynolds, mach = name
                per_group_coverage_failures.append(
                    {
                        "airfoil_id": str(airfoil_id),
                        "reynolds": None if pd.isna(reynolds) else float(reynolds),
                        "mach": None if pd.isna(mach) else float(mach),
                        "converged_rows": converged_count,
                        "min_usable_rows": MIN_USABLE_ROWS,
                        "total_rows": int(len(grp)),
                    }
                )
        if per_group_coverage_failures:
            preview = ", ".join(
                f"{item['airfoil_id']} Re={item['reynolds']} Mach={item['mach']} "
                f"({item['converged_rows']}/{MIN_USABLE_ROWS})"
                for item in per_group_coverage_failures[:5]
            )
            warnings_list.append(
                f"{len(per_group_coverage_failures)} (airfoil_id, Re, Mach) groups have "
                f"fewer than {MIN_USABLE_ROWS} converged rows: {preview}"
            )

        # 6. Per-airfoil convergence rate
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
        "min_usable_rows_per_group": MIN_USABLE_ROWS,
        "per_group_coverage_failures": per_group_coverage_failures if not df.empty and not missing_cols else [],
    }
    report_path = dataset_root / "airfoil_qc_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
