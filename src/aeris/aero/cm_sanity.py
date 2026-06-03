"""Cm-vs-alpha sign-convention sanity checks for AERIS aero datasets.

This module performs one narrow, high-value diagnostic:

    for fixed geometry/condition/control groups, fit Cm = a*alpha_deg + b
    and check whether dCm/dalpha is negative.

For the current BWB convention, a negative Cma is the expected static-stability
sign. If this check fails on known baseline cases, moment reference conventions,
axis definitions, or solver parsing should be audited before trusting Cm-driven
trim/dynamics/ML outputs.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

CM_SANITY_SCHEMA_VERSION = "aeris.cm_sign_sanity.v1"

DEFAULT_GROUP_COLUMNS = [
    "geometry_id",
    "control_input_deg",
    "velocity_mps",
    "altitude_m",
    "beta_deg",
    "p_rad_s",
    "q_rad_s",
    "r_rad_s",
]


@dataclass(frozen=True)
class CmSignGroupResult:
    group: dict[str, object]
    n_rows: int
    n_unique_alpha: int
    alpha_min_deg: float
    alpha_max_deg: float
    cm_min: float
    cm_max: float
    cma_per_deg: float
    cma_per_rad: float
    passed: bool
    status: str
    reason: str | None = None


@dataclass(frozen=True)
class CmSignSanityReport:
    schema_version: str
    source_csv: str
    alpha_column: str
    cm_column: str
    group_columns_requested: list[str]
    group_columns_used: list[str]
    expected_cma_sign: str
    min_abs_cma_per_rad: float
    n_rows: int
    n_groups_total: int
    n_groups_evaluable: int
    n_groups_passed: int
    n_groups_failed: int
    n_groups_skipped: int
    passed: bool
    groups: list[CmSignGroupResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["groups"] = [asdict(g) for g in self.groups]
        return payload


def _resolve_dataset_csv(dataset: Path) -> Path:
    dataset = Path(dataset)
    candidates = [
        dataset / "curated_aero_dataset.csv",
        dataset / "aero_dataset.csv",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"Could not find curated_aero_dataset.csv or aero_dataset.csv under {dataset}"
    )


def _parse_group_columns(group_columns: str | Iterable[str] | None) -> list[str]:
    if group_columns is None:
        return list(DEFAULT_GROUP_COLUMNS)
    if isinstance(group_columns, str):
        return [c.strip() for c in group_columns.split(",") if c.strip()]
    return [str(c).strip() for c in group_columns if str(c).strip()]


def run_cm_sign_sanity(
    *,
    csv_path: Path | None = None,
    dataset: Path | None = None,
    output_dir: Path | None = None,
    alpha_column: str = "alpha_deg",
    cm_column: str = "cm",
    group_columns: str | Iterable[str] | None = None,
    expected_negative: bool = True,
    min_abs_cma_per_rad: float = 1.0e-8,
) -> CmSignSanityReport:
    """Run Cm-alpha sign sanity on a scalar aero CSV or dataset root."""
    if (csv_path is None) == (dataset is None):
        raise ValueError("Provide exactly one of csv_path or dataset.")

    source_csv = Path(csv_path) if csv_path is not None else _resolve_dataset_csv(Path(dataset))
    if not source_csv.exists():
        raise FileNotFoundError(f"Aero CSV not found: {source_csv}")

    df = pd.read_csv(source_csv)
    missing = [c for c in [alpha_column, cm_column] if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in {source_csv}: {missing}")

    requested_groups = _parse_group_columns(group_columns)
    used_groups = [c for c in requested_groups if c in df.columns]

    work = df.copy()
    work[alpha_column] = pd.to_numeric(work[alpha_column], errors="coerce")
    work[cm_column] = pd.to_numeric(work[cm_column], errors="coerce")
    work = work[np.isfinite(work[alpha_column]) & np.isfinite(work[cm_column])].copy()

    if work.empty:
        report = CmSignSanityReport(
            schema_version=CM_SANITY_SCHEMA_VERSION,
            source_csv=str(source_csv),
            alpha_column=alpha_column,
            cm_column=cm_column,
            group_columns_requested=requested_groups,
            group_columns_used=used_groups,
            expected_cma_sign="negative" if expected_negative else "positive",
            min_abs_cma_per_rad=float(min_abs_cma_per_rad),
            n_rows=0,
            n_groups_total=0,
            n_groups_evaluable=0,
            n_groups_passed=0,
            n_groups_failed=0,
            n_groups_skipped=0,
            passed=False,
            groups=[],
        )
        if output_dir is not None:
            _write_report(report, Path(output_dir))
        return report

    if used_groups:
        grouped_iter = work.groupby(used_groups, dropna=False)
    else:
        grouped_iter = [((), work)]

    results: list[CmSignGroupResult] = []
    n_pass = n_fail = n_skip = 0

    for key, sub in grouped_iter:
        if not isinstance(key, tuple):
            key = (key,)
        group_dict = {col: _jsonable(val) for col, val in zip(used_groups, key)}

        alpha = sub[alpha_column].to_numpy(dtype=float)
        cm = sub[cm_column].to_numpy(dtype=float)
        unique_alpha = np.unique(alpha)

        if len(unique_alpha) < 2 or len(sub) < 2:
            n_skip += 1
            results.append(CmSignGroupResult(
                group=group_dict,
                n_rows=int(len(sub)),
                n_unique_alpha=int(len(unique_alpha)),
                alpha_min_deg=float(np.min(alpha)) if len(alpha) else float("nan"),
                alpha_max_deg=float(np.max(alpha)) if len(alpha) else float("nan"),
                cm_min=float(np.min(cm)) if len(cm) else float("nan"),
                cm_max=float(np.max(cm)) if len(cm) else float("nan"),
                cma_per_deg=float("nan"),
                cma_per_rad=float("nan"),
                passed=False,
                status="skipped",
                reason="fewer_than_two_unique_alpha_values",
            ))
            continue

        slope_per_deg, _intercept = np.polyfit(alpha, cm, 1)
        slope_per_rad = float(slope_per_deg * (180.0 / np.pi))

        magnitude_ok = abs(slope_per_rad) >= min_abs_cma_per_rad
        sign_ok = slope_per_rad < 0.0 if expected_negative else slope_per_rad > 0.0
        passed = bool(magnitude_ok and sign_ok)
        status = "passed" if passed else "failed"
        reason = None
        if not magnitude_ok:
            reason = "near_zero_cma"
        elif not sign_ok:
            reason = "unexpected_cma_sign"

        if passed:
            n_pass += 1
        else:
            n_fail += 1

        results.append(CmSignGroupResult(
            group=group_dict,
            n_rows=int(len(sub)),
            n_unique_alpha=int(len(unique_alpha)),
            alpha_min_deg=float(np.min(alpha)),
            alpha_max_deg=float(np.max(alpha)),
            cm_min=float(np.min(cm)),
            cm_max=float(np.max(cm)),
            cma_per_deg=float(slope_per_deg),
            cma_per_rad=slope_per_rad,
            passed=passed,
            status=status,
            reason=reason,
        ))

    report = CmSignSanityReport(
        schema_version=CM_SANITY_SCHEMA_VERSION,
        source_csv=str(source_csv),
        alpha_column=alpha_column,
        cm_column=cm_column,
        group_columns_requested=requested_groups,
        group_columns_used=used_groups,
        expected_cma_sign="negative" if expected_negative else "positive",
        min_abs_cma_per_rad=float(min_abs_cma_per_rad),
        n_rows=int(len(work)),
        n_groups_total=len(results),
        n_groups_evaluable=n_pass + n_fail,
        n_groups_passed=n_pass,
        n_groups_failed=n_fail,
        n_groups_skipped=n_skip,
        passed=bool(n_fail == 0 and n_pass > 0),
        groups=results,
    )

    if output_dir is not None:
        _write_report(report, Path(output_dir))

    return report


def _jsonable(value: object) -> object:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if pd.isna(value):
        return None
    return value


def _write_report(report: CmSignSanityReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "cm_sign_sanity_report.json"
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return path
