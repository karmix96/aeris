from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from aeris.quality.base import DatasetValidator
from aeris.quality.models import QCCheckResult, QCMessage
from aeris.quality.profiles import resolve_aero_profile
from aeris.quality.registry import AERO_VALIDATOR_REGISTRY
from aeris.quality.runners import qc_report_to_legacy_dict, run_validators


def _load_aero_dataset(dataset_root: Path) -> tuple[pd.DataFrame, dict]:
    csv_path = dataset_root / "aero_dataset.csv"
    manifest_path = dataset_root / "aero_dataset_manifest.json"

    if not csv_path.exists():
        raise FileNotFoundError(f"Missing aero dataset CSV: {csv_path}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing aero dataset manifest: {manifest_path}")

    df = pd.read_csv(csv_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return df, manifest


def _base_report() -> dict:
    return {
        "passed": True,
        "errors": [],
        "warnings": [],
        "metrics": {},
    }


def _append_error(report: dict, message: str) -> None:
    report["passed"] = False
    report["errors"].append(message)


def _append_warning(report: dict, message: str) -> None:
    report["warnings"].append(message)


def _report_to_check_result(validator_id: str, report: dict) -> QCCheckResult:
    messages: list[QCMessage] = []

    for msg in report["errors"]:
        messages.append(QCMessage(code=f"{validator_id}:error", level="error", message=msg))
    for msg in report["warnings"]:
        messages.append(QCMessage(code=f"{validator_id}:warning", level="warning", message=msg))

    return QCCheckResult(
        validator_id=validator_id,
        passed=report["passed"],
        messages=messages,
        metrics=report["metrics"],
    )


def _with_loaded_dataset(dataset_root: Path, fn) -> dict:
    report = _base_report()
    try:
        df, manifest = _load_aero_dataset(dataset_root)
    except Exception as exc:
        _append_error(report, str(exc))
        return report

    fn(df, manifest, report)
    return report


def _check_manifest_consistency(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    expected = manifest.get("successful_aero_rows")
    actual = len(df)

    report["metrics"]["csv_rows"] = int(actual)
    report["metrics"]["manifest_successful_aero_rows"] = None if expected is None else int(expected)

    if expected != actual:
        _append_error(
            report,
            f"Mismatch between manifest successful_aero_rows ({expected}) and CSV rows ({actual})",
        )


def _check_targets_finite(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    bad_counts: dict[str, int] = {}

    for col in ["cl", "cd", "cm"]:
        if col not in df.columns:
            _append_error(report, f"Missing required aero column: {col}")
            continue

        values = pd.to_numeric(df[col], errors="coerce")
        bad = int((~np.isfinite(values)).sum())
        bad_counts[col] = bad

        if bad > 0:
            _append_error(report, f"Non-finite values detected in {col}: {bad}")

    report["metrics"]["non_finite_target_counts"] = bad_counts


def _check_control_diagnostics(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    diag_cols = [
        "geometry_declares_controls",
        "airplane_has_controls",
        "diag_airplane_has_control_surfaces",
        "diag_airplane_avl_has_control_blocks",
        "diag_keystrokes_has_d1_command",
    ]

    diag_summary: dict[str, int] = {}

    for col in diag_cols:
        if col not in df.columns:
            _append_error(report, f"Missing control diagnostic column: {col}")
            continue

        normalized = df[col].astype(str).str.strip().str.lower()
        bad = int((~normalized.isin(["true", "1"])).sum())
        diag_summary[col] = bad

        if bad > 0:
            _append_error(report, f"Control diagnostic failed in {col}: {bad} bad rows")

    if "diag_stdout_control_variables" not in df.columns:
        _append_error(report, "Missing control diagnostic column: diag_stdout_control_variables")
    else:
        vals = pd.to_numeric(df["diag_stdout_control_variables"], errors="coerce")
        bad = int(((~np.isfinite(vals)) | (vals <= 0)).sum())
        diag_summary["diag_stdout_control_variables"] = bad
        if bad > 0:
            _append_error(
                report,
                f"AVL stdout reported invalid/non-positive control variable count in {bad} rows",
            )

    report["metrics"]["control_diagnostic_bad_counts"] = diag_summary


def _check_control_effectiveness(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    required = ["geometry_id", "alpha_deg", "velocity_mps", "altitude_m", "control_input_deg", "cl", "cm"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        _append_error(report, f"Missing required columns for control effectiveness check: {missing}")
        return

    group_cols = ["geometry_id", "alpha_deg", "velocity_mps", "altitude_m"]
    bad_groups: list[str] = []

    for name, g in df.groupby(group_cols):
        ctrls = sorted(pd.to_numeric(g["control_input_deg"], errors="coerce").tolist())
        if ctrls != [-5.0, 0.0, 5.0]:
            continue

        g = g.sort_values("control_input_deg")
        cl_vals = np.round(pd.to_numeric(g["cl"], errors="coerce").to_numpy(), 8)
        cm_vals = np.round(pd.to_numeric(g["cm"], errors="coerce").to_numpy(), 8)

        if len(set(cl_vals.tolist())) == 1:
            bad_groups.append(f"CL collapsed for group {name}")
        if len(set(cm_vals.tolist())) == 1:
            bad_groups.append(f"Cm collapsed for group {name}")

    report["metrics"]["collapsed_control_group_count"] = len(bad_groups)

    if bad_groups:
        for msg in bad_groups[:10]:
            _append_error(report, msg)


def _check_basic_ranges(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    issues = {
        "cd_non_positive": 0,
        "cl_abs_gt_5": 0,
        "cm_abs_gt_5": 0,
    }

    if "cd" in df.columns:
        cd = pd.to_numeric(df["cd"], errors="coerce")
        issues["cd_non_positive"] = int((cd <= 0).sum())
        if issues["cd_non_positive"] > 0:
            _append_error(report, f"Non-positive CD values detected: {issues['cd_non_positive']}")

    if "cl" in df.columns:
        cl = pd.to_numeric(df["cl"], errors="coerce")
        issues["cl_abs_gt_5"] = int((cl.abs() > 5).sum())
        if issues["cl_abs_gt_5"] > 0:
            _append_error(report, f"Absurd |CL| > 5 values detected: {issues['cl_abs_gt_5']}")

    if "cm" in df.columns:
        cm = pd.to_numeric(df["cm"], errors="coerce")
        issues["cm_abs_gt_5"] = int((cm.abs() > 5).sum())
        if issues["cm_abs_gt_5"] > 0:
            _append_error(report, f"Absurd |Cm| > 5 values detected: {issues['cm_abs_gt_5']}")

    report["metrics"]["basic_range_issues"] = issues


def _check_grid_complete(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    required = ["geometry_id", "alpha_deg", "velocity_mps", "altitude_m", "control_input_deg"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        _append_error(report, f"Missing required columns for grid completeness check: {missing}")
        return

    expected_per_geom = (
        df["alpha_deg"].nunique()
        * df["velocity_mps"].nunique()
        * df["altitude_m"].nunique()
        * df["control_input_deg"].nunique()
    )

    counts = df.groupby("geometry_id").size()
    bad = counts[counts != expected_per_geom]

    report["metrics"]["expected_rows_per_geometry"] = int(expected_per_geom)
    report["metrics"]["geometry_row_counts"] = {str(k): int(v) for k, v in counts.to_dict().items()}
    report["metrics"]["incomplete_geometry_count"] = int(len(bad))

    if len(bad) > 0:
        _append_error(
            report,
            f"Incomplete per-geometry sweep grid detected for {len(bad)} geometries",
        )


def _check_zero_control_once(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    required = ["geometry_id", "alpha_deg", "velocity_mps", "altitude_m", "control_input_deg"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        _append_error(report, f"Missing required columns for zero-control check: {missing}")
        return

    group_cols = ["geometry_id", "alpha_deg", "velocity_mps", "altitude_m"]
    zero_counts = (
        df.assign(is_zero=(pd.to_numeric(df["control_input_deg"], errors="coerce") == 0.0))
        .groupby(group_cols)["is_zero"]
        .sum()
    )

    bad = zero_counts[zero_counts != 1]
    report["metrics"]["bad_zero_control_group_count"] = int(len(bad))

    if len(bad) > 0:
        _append_error(
            report,
            f"Expected exactly one zero-control row per condition group; found {len(bad)} bad groups",
        )


def _check_cl_alpha_trend(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    required = ["geometry_id", "velocity_mps", "altitude_m", "control_input_deg", "alpha_deg", "cl"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        _append_error(report, f"Missing required columns for CL-alpha trend check: {missing}")
        return

    group_cols = ["geometry_id", "velocity_mps", "altitude_m", "control_input_deg"]
    bad: list[str] = []

    for name, g in df.groupby(group_cols):
        g = g.sort_values("alpha_deg")
        dcl = np.diff(pd.to_numeric(g["cl"], errors="coerce").to_numpy())
        if np.any(dcl < -1e-6):
            bad.append(str(name))

    report["metrics"]["non_monotonic_cl_alpha_group_count"] = len(bad)

    if bad:
        for group in bad[:10]:
            _append_error(report, f"CL does not increase monotonically with alpha for group {group}")


def _check_cm_control_trend(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    required = ["geometry_id", "alpha_deg", "velocity_mps", "altitude_m", "control_input_deg", "cm"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        _append_error(report, f"Missing required columns for Cm-control trend check: {missing}")
        return

    group_cols = ["geometry_id", "alpha_deg", "velocity_mps", "altitude_m"]
    bad: list[str] = []

    for name, g in df.groupby(group_cols):
        g = g.sort_values("control_input_deg")
        x = pd.to_numeric(g["control_input_deg"], errors="coerce").to_numpy()
        y = pd.to_numeric(g["cm"], errors="coerce").to_numpy()

        if len(x) < 2:
            continue

        slope = float(np.polyfit(x, y, deg=1)[0])
        if abs(slope) < 1e-5:
            bad.append(str(name))

    report["metrics"]["near_zero_cm_control_slope_group_count"] = len(bad)

    if bad:
        for group in bad[:10]:
            _append_error(report, f"Cm response to control is too weak for group {group}")


def _check_outliers(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    outlier_counts: dict[str, int] = {}

    for col in ["cl", "cd", "cm"]:
        if col not in df.columns:
            _append_error(report, f"Missing required column for outlier scan: {col}")
            continue

        vals = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
        finite = np.isfinite(vals)

        if not finite.any():
            _append_error(report, f"No finite values available for outlier scan in {col}")
            continue

        mu = float(np.mean(vals[finite]))
        sd = float(np.std(vals[finite]))

        if sd <= 0.0:
            outlier_counts[col] = 0
            continue

        z = np.abs((vals - mu) / sd)
        bad = int((np.isfinite(z) & (z > 5.0)).sum())
        outlier_counts[col] = bad

        if bad > 0:
            _append_error(report, f"Outliers detected in {col}: {bad} rows beyond 5 sigma")

    report["metrics"]["outlier_counts"] = outlier_counts


def _check_ld_sanity(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    if "cl" not in df.columns or "cd" not in df.columns:
        _append_warning(report, "Skipping L/D sanity check because cl/cd columns are missing")
        return

    cl = pd.to_numeric(df["cl"], errors="coerce")
    cd = pd.to_numeric(df["cd"], errors="coerce")

    ld = cl / cd.replace(0.0, np.nan)
    bad_non_finite = int((~np.isfinite(ld)).sum())
    bad_too_large = int((np.isfinite(ld) & (ld.abs() > 200.0)).sum())
    bad_negative = int((np.isfinite(ld) & (ld <= 0.0)).sum())

    report["metrics"]["ld_sanity"] = {
        "non_finite_ld_count": bad_non_finite,
        "abs_ld_gt_200_count": bad_too_large,
        "non_positive_ld_count": bad_negative,
    }

    if bad_non_finite > 0:
        _append_error(report, f"Non-finite L/D detected in {bad_non_finite} rows")
    if bad_too_large > 0:
        _append_error(report, f"Suspiciously large |L/D| detected in {bad_too_large} rows")
    if bad_negative > 0:
        _append_error(report, f"Non-positive L/D detected in {bad_negative} rows")


def _check_beta_zero_lateral_sanity(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    required = ["beta_deg", "cy", "cl_roll", "cn"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        _append_warning(
            report,
            f"Skipping beta=0 lateral sanity check because columns are missing: {missing}",
        )
        return

    subset = df[pd.to_numeric(df["beta_deg"], errors="coerce") == 0.0].copy()
    if subset.empty:
        _append_warning(report, "Skipping beta=0 lateral sanity check because no beta=0 rows exist")
        return

    counts = {
        "abs_cy_gt_0_25": int((pd.to_numeric(subset["cy"], errors="coerce").abs() > 0.25).sum()),
        "abs_cl_roll_gt_0_25": int((pd.to_numeric(subset["cl_roll"], errors="coerce").abs() > 0.25).sum()),
        "abs_cn_gt_0_25": int((pd.to_numeric(subset["cn"], errors="coerce").abs() > 0.25).sum()),
    }

    report["metrics"]["beta_zero_lateral_sanity"] = counts

    for key, count in counts.items():
        if count > 0:
            _append_error(report, f"beta=0 lateral sanity violation {key}: {count}")


def _check_target_variation(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    counts: dict[str, int] = {}
    for col in ["cl", "cd", "cm"]:
        if col not in df.columns:
            _append_warning(report, f"Skipping target-variation check for missing column: {col}")
            continue

        rounded = pd.to_numeric(df[col], errors="coerce").round(8)
        unique_count = int(rounded.nunique(dropna=True))
        counts[f"{col}_unique_count"] = unique_count

        if unique_count <= 1:
            _append_error(report, f"Aero target '{col}' is globally collapsed (<= 1 unique value)")

    report["metrics"]["target_variation"] = counts


@AERO_VALIDATOR_REGISTRY.register
class AeroManifestConsistencyValidator(DatasetValidator):
    VALIDATOR_ID = "aero_manifest_consistency_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_manifest_consistency)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@AERO_VALIDATOR_REGISTRY.register
class AeroTargetsFiniteValidator(DatasetValidator):
    VALIDATOR_ID = "aero_targets_finite_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_targets_finite)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@AERO_VALIDATOR_REGISTRY.register
class AeroGridCompleteValidator(DatasetValidator):
    VALIDATOR_ID = "aero_grid_complete_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_grid_complete)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@AERO_VALIDATOR_REGISTRY.register
class AeroZeroControlOnceValidator(DatasetValidator):
    VALIDATOR_ID = "aero_zero_control_once_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_zero_control_once)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@AERO_VALIDATOR_REGISTRY.register
class AeroControlDiagnosticsValidator(DatasetValidator):
    VALIDATOR_ID = "aero_control_diagnostics_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_control_diagnostics)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@AERO_VALIDATOR_REGISTRY.register
class AeroControlEffectivenessValidator(DatasetValidator):
    VALIDATOR_ID = "aero_control_effectiveness_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_control_effectiveness)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@AERO_VALIDATOR_REGISTRY.register
class AeroBasicRangesValidator(DatasetValidator):
    VALIDATOR_ID = "aero_basic_ranges_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_basic_ranges)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@AERO_VALIDATOR_REGISTRY.register
class AeroCLAlphaTrendValidator(DatasetValidator):
    VALIDATOR_ID = "aero_cl_alpha_trend_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_cl_alpha_trend)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@AERO_VALIDATOR_REGISTRY.register
class AeroCMControlTrendValidator(DatasetValidator):
    VALIDATOR_ID = "aero_cm_control_trend_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_cm_control_trend)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@AERO_VALIDATOR_REGISTRY.register
class AeroOutlierScanValidator(DatasetValidator):
    VALIDATOR_ID = "aero_outlier_scan_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_outliers)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@AERO_VALIDATOR_REGISTRY.register
class AeroLDSanityValidator(DatasetValidator):
    VALIDATOR_ID = "aero_ld_sanity_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_ld_sanity)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@AERO_VALIDATOR_REGISTRY.register
class AeroBetaZeroLateralSanityValidator(DatasetValidator):
    VALIDATOR_ID = "aero_beta_zero_lateral_sanity_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_beta_zero_lateral_sanity)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@AERO_VALIDATOR_REGISTRY.register
class AeroTargetVariationValidator(DatasetValidator):
    VALIDATOR_ID = "aero_target_variation_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_target_variation)
        return _report_to_check_result(self.VALIDATOR_ID, report)


def run_aero_checks(dataset_root: Path, profile: str = "basic") -> dict:
    """
    Backward-compatible legacy wrapper.

    Old callers still get a dict-shaped report, but execution is now registry/profile-based.
    """
    resolved_profile, validator_ids = resolve_aero_profile(profile)
    validators = AERO_VALIDATOR_REGISTRY.create_many(validator_ids)
    report = run_validators(domain="aero", dataset_root=dataset_root, validators=validators)
    payload = qc_report_to_legacy_dict(report)
    payload["metrics"]["profile"] = resolved_profile
    return payload