from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from aeris.quality.base import DatasetValidator
from aeris.quality.models import QCCheckResult, QCMessage
from aeris.quality.profiles import resolve_geometry_profile
from aeris.quality.registry import GEOMETRY_VALIDATOR_REGISTRY
from aeris.quality.runners import qc_report_to_legacy_dict, run_validators


def _load_geometry_dataset(dataset_root: Path) -> tuple[pd.DataFrame, dict]:
    manifest_path = dataset_root / "dataset_manifest.json"
    metadata_path = dataset_root / "metadata.csv"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing dataset manifest: {manifest_path}")
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing metadata CSV: {metadata_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    df = pd.read_csv(metadata_path)
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
        messages.append(
            QCMessage(
                code=f"{validator_id}:error",
                level="error",
                message=msg,
            )
        )

    for msg in report["warnings"]:
        messages.append(
            QCMessage(
                code=f"{validator_id}:warning",
                level="warning",
                message=msg,
            )
        )

    return QCCheckResult(
        validator_id=validator_id,
        passed=report["passed"],
        messages=messages,
        metrics=report["metrics"],
    )


def _with_loaded_dataset(dataset_root: Path, fn) -> dict:
    report = _base_report()
    try:
        df, manifest = _load_geometry_dataset(dataset_root)
    except Exception as exc:
        _append_error(report, str(exc))
        return report

    fn(df, manifest, report)
    return report


def _check_manifest_consistency(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    expected = manifest.get("succeeded_n")
    actual = len(df)

    report["metrics"]["metadata_rows"] = int(actual)
    report["metrics"]["manifest_successful_cases"] = None if expected is None else int(expected)

    if expected != actual:
        _append_error(
            report,
            f"Mismatch between manifest succeeded_n ({expected}) and metadata rows ({actual})",
        )


def _check_required_columns(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    required = [
        "geometry_id",
        "c1_m",
        "c2_ratio",
        "c3_ratio",
        "c4_ratio",
        "b_total_m",
        "b3_ratio",
        "split_ratio",
        "full_span_m",
        "approx_area_m2",
        "summary_path",
        "control_points_path",
        "planform_sections_path",
        "section_3d_path",
    ]
    missing = [c for c in required if c not in df.columns]
    report["metrics"]["missing_required_columns"] = missing

    if missing:
        _append_error(report, f"Missing required geometry metadata columns: {missing}")


def _check_duplicate_geometry_ids(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    if "geometry_id" not in df.columns:
        _append_error(report, "metadata.csv missing geometry_id column")
        return

    dupes = df["geometry_id"][df["geometry_id"].duplicated()].tolist()
    report["metrics"]["duplicate_geometry_id_count"] = len(dupes)

    if dupes:
        _append_error(report, f"Duplicate geometry_id values detected: {dupes[:10]}")


def _check_no_nan(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    required_numeric = [
        "c1_m",
        "c2_ratio",
        "c3_ratio",
        "c4_ratio",
        "b_total_m",
        "b3_ratio",
        "split_ratio",
        "full_span_m",
        "approx_area_m2",
    ]
    missing = [c for c in required_numeric if c not in df.columns]
    if missing:
        _append_error(report, f"Missing numeric columns for NaN check: {missing}")
        return

    bad_counts: dict[str, int] = {}
    for col in required_numeric:
        vals = pd.to_numeric(df[col], errors="coerce")
        bad = int(vals.isna().sum())
        bad_counts[col] = bad
        if bad > 0:
            _append_error(report, f"NaN/invalid numeric values detected in {col}: {bad}")

    report["metrics"]["nan_like_numeric_counts"] = bad_counts


def _check_basic_ranges(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    checks = {
        "full_span_m_non_positive": 0,
        "approx_area_m2_non_positive": 0,
        "c1_m_non_positive": 0,
        "b_total_m_non_positive": 0,
        "split_ratio_out_of_bounds": 0,
        "b3_ratio_out_of_bounds": 0,
    }

    if "full_span_m" in df.columns:
        vals = pd.to_numeric(df["full_span_m"], errors="coerce")
        checks["full_span_m_non_positive"] = int((vals <= 0).sum())

    if "approx_area_m2" in df.columns:
        vals = pd.to_numeric(df["approx_area_m2"], errors="coerce")
        checks["approx_area_m2_non_positive"] = int((vals <= 0).sum())

    if "c1_m" in df.columns:
        vals = pd.to_numeric(df["c1_m"], errors="coerce")
        checks["c1_m_non_positive"] = int((vals <= 0).sum())

    if "b_total_m" in df.columns:
        vals = pd.to_numeric(df["b_total_m"], errors="coerce")
        checks["b_total_m_non_positive"] = int((vals <= 0).sum())

    if "split_ratio" in df.columns:
        vals = pd.to_numeric(df["split_ratio"], errors="coerce")
        checks["split_ratio_out_of_bounds"] = int(((vals <= 0) | (vals >= 1)).sum())

    if "b3_ratio" in df.columns:
        vals = pd.to_numeric(df["b3_ratio"], errors="coerce")
        checks["b3_ratio_out_of_bounds"] = int(((vals <= 0) | (vals >= 1)).sum())

    report["metrics"]["basic_range_issues"] = checks

    for key, count in checks.items():
        if count > 0:
            _append_error(report, f"Geometry basic range violation {key}: {count}")


def _check_required_files_exist(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    path_cols = [
        "summary_path",
        "control_points_path",
        "planform_sections_path",
        "section_3d_path",
    ]
    missing_cols = [c for c in path_cols if c not in df.columns]
    if missing_cols:
        _append_error(report, f"Missing path columns for artifact existence check: {missing_cols}")
        return

    bad = 0
    for _, row in df.iterrows():
        for col in path_cols:
            value = row.get(col)
            if pd.isna(value) or not str(value).strip():
                bad += 1
                continue
            if not Path(str(value)).exists():
                bad += 1

    report["metrics"]["missing_required_artifact_count"] = bad

    if bad > 0:
        _append_error(report, f"Missing required geometry artifact paths detected: {bad}")


def _check_scalar_consistency(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    required = ["full_span_m", "approx_area_m2", "approx_aspect_ratio_planform"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        _append_error(report, f"Missing required columns for scalar consistency check: {missing}")
        return

    ar_mismatch = 0
    absurd_ar = 0
    semi_span_mismatch = 0
    asb_delta_bad = 0

    for _, row in df.iterrows():
        span = float(pd.to_numeric(row["full_span_m"], errors="coerce"))
        area = float(pd.to_numeric(row["approx_area_m2"], errors="coerce"))
        ar = float(pd.to_numeric(row["approx_aspect_ratio_planform"], errors="coerce"))

        if not all(math.isfinite(v) for v in [span, area, ar]) or area <= 0.0:
            continue

        recomputed_ar = (span ** 2) / area
        if abs(recomputed_ar - ar) > 0.20:
            ar_mismatch += 1

        if ar < 1.0 or ar > 20.0:
            absurd_ar += 1

        if "semi_span_m" in df.columns:
            semi = float(pd.to_numeric(row["semi_span_m"], errors="coerce"))
            if math.isfinite(semi) and abs(span - 2.0 * semi) > 1e-6:
                semi_span_mismatch += 1

        if "aspect_ratio_aerosandbox" in df.columns:
            ar_asb = float(pd.to_numeric(row["aspect_ratio_aerosandbox"], errors="coerce"))
            if math.isfinite(ar_asb) and abs(ar_asb - ar) > 0.35:
                asb_delta_bad += 1

    report["metrics"]["strict_scalar_consistency"] = {
        "ar_recompute_mismatch_count": ar_mismatch,
        "absurd_ar_count": absurd_ar,
        "semi_span_mismatch_count": semi_span_mismatch,
        "aerosandbox_ar_delta_bad_count": asb_delta_bad,
    }

    if ar_mismatch > 0:
        _append_error(report, f"Aspect-ratio recompute mismatch detected in {ar_mismatch} rows")
    if absurd_ar > 0:
        _append_error(report, f"Suspicious planform aspect ratio detected in {absurd_ar} rows")
    if semi_span_mismatch > 0:
        _append_error(report, f"full_span_m != 2 * semi_span_m in {semi_span_mismatch} rows")
    if asb_delta_bad > 0:
        _append_error(report, f"Planform-vs-AeroSandbox AR mismatch too large in {asb_delta_bad} rows")


def _check_chord_ratio_sanity(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    required = ["c2_ratio", "c3_ratio", "c4_ratio"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        _append_error(report, f"Missing required columns for chord-ratio sanity check: {missing}")
        return

    counts = {
        "ratio_non_positive": 0,
        "ratio_gt_one": 0,
        "non_monotonic_taper": 0,
    }

    for _, row in df.iterrows():
        c2 = float(pd.to_numeric(row["c2_ratio"], errors="coerce"))
        c3 = float(pd.to_numeric(row["c3_ratio"], errors="coerce"))
        c4 = float(pd.to_numeric(row["c4_ratio"], errors="coerce"))

        vals = [c2, c3, c4]
        if any((not math.isfinite(v)) for v in vals):
            continue

        if any(v <= 0.0 for v in vals):
            counts["ratio_non_positive"] += 1
        if any(v > 1.0 for v in vals):
            counts["ratio_gt_one"] += 1
        if not (c2 >= c3 >= c4):
            counts["non_monotonic_taper"] += 1

    report["metrics"]["strict_chord_ratio_sanity"] = counts

    for key, count in counts.items():
        if count > 0:
            _append_error(report, f"Geometry strict chord-ratio violation {key}: {count}")


def _check_planform_parameter_sanity(df: pd.DataFrame, manifest: dict, report: dict) -> None:
    counts = {
        "split_ratio_too_extreme": 0,
        "b3_ratio_too_extreme": 0,
        "sweep_out_of_bounds": 0,
    }

    for _, row in df.iterrows():
        split_ratio = float(pd.to_numeric(row.get("split_ratio"), errors="coerce"))
        b3_ratio = float(pd.to_numeric(row.get("b3_ratio"), errors="coerce"))

        if math.isfinite(split_ratio) and not (0.05 <= split_ratio <= 0.95):
            counts["split_ratio_too_extreme"] += 1
        if math.isfinite(b3_ratio) and not (0.05 <= b3_ratio <= 0.95):
            counts["b3_ratio_too_extreme"] += 1

        for key in ["sw1_deg", "sw2_deg", "sw3_deg"]:
            if key in df.columns:
                sweep = float(pd.to_numeric(row.get(key), errors="coerce"))

                # Allow signed sweep. Only reject physically absurd values.
                if math.isfinite(sweep) and not (-85.0 <= sweep <= 85.0):
                    counts["sweep_out_of_bounds"] += 1

    report["metrics"]["strict_planform_parameter_sanity"] = counts

    for key, count in counts.items():
        if count > 0:
            _append_error(report, f"Geometry strict planform-parameter violation {key}: {count}")


@GEOMETRY_VALIDATOR_REGISTRY.register
class GeometryManifestConsistencyValidator(DatasetValidator):
    VALIDATOR_ID = "geometry_manifest_consistency_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_manifest_consistency)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@GEOMETRY_VALIDATOR_REGISTRY.register
class GeometryRequiredColumnsValidator(DatasetValidator):
    VALIDATOR_ID = "geometry_required_columns_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_required_columns)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@GEOMETRY_VALIDATOR_REGISTRY.register
class GeometryNoDuplicateIdsValidator(DatasetValidator):
    VALIDATOR_ID = "geometry_no_duplicate_ids_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_duplicate_geometry_ids)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@GEOMETRY_VALIDATOR_REGISTRY.register
class GeometryMetadataNoNaNValidator(DatasetValidator):
    VALIDATOR_ID = "geometry_metadata_no_nan_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_no_nan)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@GEOMETRY_VALIDATOR_REGISTRY.register
class GeometryBasicRangesValidator(DatasetValidator):
    VALIDATOR_ID = "geometry_basic_ranges_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_basic_ranges)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@GEOMETRY_VALIDATOR_REGISTRY.register
class GeometryRequiredFilesValidator(DatasetValidator):
    VALIDATOR_ID = "geometry_required_files_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_required_files_exist)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@GEOMETRY_VALIDATOR_REGISTRY.register
class GeometryScalarConsistencyValidator(DatasetValidator):
    VALIDATOR_ID = "geometry_scalar_consistency_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_scalar_consistency)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@GEOMETRY_VALIDATOR_REGISTRY.register
class GeometryChordRatioSanityValidator(DatasetValidator):
    VALIDATOR_ID = "geometry_chord_ratio_sanity_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_chord_ratio_sanity)
        return _report_to_check_result(self.VALIDATOR_ID, report)


@GEOMETRY_VALIDATOR_REGISTRY.register
class GeometryPlanformParameterSanityValidator(DatasetValidator):
    VALIDATOR_ID = "geometry_planform_parameter_sanity_v1"

    def validate(self, dataset_root: Path) -> QCCheckResult:
        report = _with_loaded_dataset(dataset_root, _check_planform_parameter_sanity)
        return _report_to_check_result(self.VALIDATOR_ID, report)


def run_geometry_checks(dataset_root: Path, profile: str = "basic") -> dict:
    """
    Backward-compatible legacy wrapper.

    Old callers still get a dict-shaped report, but the actual execution path is now the
    registry/profile-based modular QC system.
    """
    resolved_profile, validator_ids = resolve_geometry_profile(profile)
    validators = GEOMETRY_VALIDATOR_REGISTRY.create_many(validator_ids)
    report = run_validators(domain="geometry", dataset_root=dataset_root, validators=validators)
    payload = qc_report_to_legacy_dict(report)
    payload["metrics"]["profile"] = resolved_profile
    return payload