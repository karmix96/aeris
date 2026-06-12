from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.errors import EmptyDataError

from aeris.aero.control_metadata import control_alias_row

REQUIRED_TARGET_COLUMNS = [
    "cl",
    "cd",
    "cm",
]

GROUP_KEY = "geometry_id"


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required CSV not found: {path}")
    try:
        return pd.read_csv(path)
    except EmptyDataError:
        return pd.DataFrame()


def _ensure_control_alias_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Backfill explicit control-alias columns for old and new aero datasets."""
    if df.empty or "control_input_deg" not in df.columns:
        return df

    out = df.copy()

    def _alias_row(row: "pd.Series") -> "pd.Series":
        sym = None if pd.isna(row["control_input_deg"]) else row["control_input_deg"]
        diff_col = "diff_input_deg"
        diff = (
            None
            if diff_col not in row.index or pd.isna(row[diff_col])
            else row[diff_col]
        )
        return pd.Series(control_alias_row(sym, diff_input_deg=diff))

    aliases = out.apply(_alias_row, axis=1)

    if "delta_e_sym_deg" not in out.columns:
        out["delta_e_sym_deg"] = aliases["delta_e_sym_deg"]
    if "delta_a_diff_deg" not in out.columns:
        out["delta_a_diff_deg"] = aliases["delta_a_diff_deg"]

    return out


def _is_finite_value(value: Any) -> bool:
    if pd.isna(value):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _expected_case_count(
    *,
    manifest: dict[str, Any] | None,
    treat_empty_rates_as_zero: bool = True,
) -> int | None:
    if manifest is None:
        return None

    lengths = [
        len(manifest.get("alpha_values", []) or []),
        len(manifest.get("beta_values", []) or []),
        len(manifest.get("velocity_values", []) or []),
        len(manifest.get("altitude_values", []) or []),
        len(manifest.get("p_values", []) or []),
        len(manifest.get("q_values", []) or []),
        len(manifest.get("r_values", []) or []),
        len(manifest.get("control_input_values", []) or []),
    ]

    _sweep_keys = [
        "alpha_values", "beta_values", "velocity_values", "altitude_values",
        "p_values", "q_values", "r_values", "control_input_values",
    ]
    zero_keys = [k for k, l in zip(_sweep_keys, lengths) if l == 0]
    if zero_keys:
        if treat_empty_rates_as_zero:
            # CUR-1: rate parameters like p_values/q_values/r_values default to []
            # in the CLI (not swept). Treat them as [0.0] — one point at zero rate.
            # This restores incomplete-group detection for standard single-rate sweeps.
            for i, key in enumerate(_sweep_keys):
                if key in zero_keys:
                    lengths[i] = 1  # equivalent to [0.0]
        else:
            import warnings as _warnings
            _warnings.warn(
                "_expected_case_count: manifest has zero-length sweep lists for "
                f"{zero_keys}. Incomplete-group rejection is DISABLED for this dataset. "
                "Verify aero_dataset_manifest.json is complete.",
                stacklevel=3,
            )
            return None

    total = 1
    diff_values = manifest.get("diff_input_values") or []
    for length in lengths:
        total *= length
    if diff_values:
        total *= len(diff_values)
    return total


def _extract_qc_context(dataset_root: Path) -> dict[str, Any]:
    manifest = _read_json_if_exists(dataset_root / "aero_dataset_manifest.json")
    final_summary = _read_json_if_exists(dataset_root / "final_run_summary.json")

    geometry_qc = None
    aero_qc = None
    qc_preset = None

    if final_summary is not None:
        geometry_qc = final_summary.get("geometry_qc")
        aero_qc = final_summary.get("aero_qc")
        qc_preset = final_summary.get("qc_preset")

    if manifest is not None:
        if geometry_qc is None:
            geometry_qc = manifest.get("geometry_qc")
        if aero_qc is None:
            aero_qc = manifest.get("aero_qc")

    geometry_qc_passed = None if geometry_qc is None else geometry_qc.get("passed")
    aero_qc_passed = None if aero_qc is None else aero_qc.get("passed")

    promotion_blockers: list[str] = []

    if geometry_qc_passed is False:
        promotion_blockers.append("geometry_qc_failed")
    if aero_qc_passed is False:
        promotion_blockers.append("aero_qc_failed")

    return {
        "qc_preset_used": qc_preset,
        "geometry_qc": geometry_qc,
        "aero_qc": aero_qc,
        "geometry_qc_passed": geometry_qc_passed,
        "aero_qc_passed": aero_qc_passed,
        "promotion_blockers_from_qc": promotion_blockers,
    }


def curate_aero_dataset(
    *,
    dataset_root: Path,
    reject_incomplete_groups: bool = True,
    reject_groups_with_failures: bool = True,
    reject_nonfinite_targets: bool = True,
    reject_control_diagnostic_failures: bool = True,
    strict_expected_count: bool = False,
) -> dict[str, Any]:
    dataset_root = dataset_root.expanduser().resolve()

    aero_dataset_csv = dataset_root / "aero_dataset.csv"
    aero_failures_csv = dataset_root / "aero_failures.csv"
    manifest_path = dataset_root / "aero_dataset_manifest.json"

    curated_csv_path = dataset_root / "curated_aero_dataset.csv"
    rejected_csv_path = dataset_root / "rejected_aero_rows.csv"
    report_path = dataset_root / "curation_report.json"

    manifest = _read_json_if_exists(manifest_path)
    df = _ensure_control_alias_columns(_load_csv(aero_dataset_csv))

    if GROUP_KEY not in df.columns:
        raise ValueError(f"Missing required grouping column: {GROUP_KEY}")

    failures_df = pd.DataFrame()
    if aero_failures_csv.exists():
        try:
            failures_df = pd.read_csv(aero_failures_csv)
        except EmptyDataError:
            failures_df = pd.DataFrame()

    qc_context = _extract_qc_context(dataset_root)
    expected_cases_per_geometry = _expected_case_count(manifest=manifest)
    if strict_expected_count and expected_cases_per_geometry is None:
        raise ValueError(
            "strict_expected_count=True but expected_cases_per_geometry could not be determined "
            "from aero_dataset_manifest.json. Ensure all sweep parameter lists are non-empty "
            "or disable strict mode to allow incomplete-group check bypass."
        )

    rejected_geometry_reasons: dict[str, set[str]] = {}

    def reject_geometry(geometry_id: str, reason: str) -> None:
        rejected_geometry_reasons.setdefault(str(geometry_id), set()).add(reason)

    grouped = df.groupby(GROUP_KEY, dropna=False)

    if reject_incomplete_groups and expected_cases_per_geometry is not None:
        counts = grouped.size()
        for geometry_id, count in counts.items():
            if int(count) != int(expected_cases_per_geometry):
                reject_geometry(str(geometry_id), "incomplete_sweep_group")

    if reject_groups_with_failures and not failures_df.empty and GROUP_KEY in failures_df.columns:
        failed_geometry_ids = failures_df[GROUP_KEY].dropna().astype(str).unique().tolist()
        for geometry_id in failed_geometry_ids:
            reject_geometry(geometry_id, "geometry_has_failed_aero_cases")

    if reject_nonfinite_targets:
        missing_target_cols = [c for c in REQUIRED_TARGET_COLUMNS if c not in df.columns]
        if missing_target_cols:
            raise ValueError(
                f"Dataset at {dataset_root} is missing required target columns: "
                f"{missing_target_cols}. "
                f"Available columns: {list(df.columns[:20])}{'...' if len(df.columns) > 20 else ''}"
            )

        nonfinite_mask = pd.Series(False, index=df.index)
        for column in REQUIRED_TARGET_COLUMNS:
            nonfinite_mask = nonfinite_mask | (~df[column].map(_is_finite_value))

        for geometry_id in df.loc[nonfinite_mask, GROUP_KEY].dropna().astype(str).unique().tolist():
            reject_geometry(geometry_id, "nonfinite_target_values")

    if reject_control_diagnostic_failures:
        diagnostic_columns = [
            "diag_airplane_has_control_surfaces",
            "diag_airplane_avl_has_control_blocks",
            # ISSUE-4: d2 architecture — check new column name first,
            # fall back to legacy d1 column for datasets generated before this patch.
            "diag_keystrokes_has_control_command",  # new (d2-safe) name
            "diag_keystrokes_has_d1_command",       # legacy fallback
        ]
        existing_diag_columns = [col for col in diagnostic_columns if col in df.columns]

        if existing_diag_columns:
            bad_diag_mask = pd.Series(False, index=df.index)
            for col in existing_diag_columns:
                bad_diag_mask = bad_diag_mask | (df[col].fillna(False).astype(bool) == False)

            for geometry_id in df.loc[bad_diag_mask, GROUP_KEY].dropna().astype(str).unique().tolist():
                reject_geometry(geometry_id, "failed_control_diagnostics")

    rejected_geometry_ids = set(rejected_geometry_reasons.keys())

    rejected_rows = df[df[GROUP_KEY].astype(str).isin(rejected_geometry_ids)].copy()
    curated_rows = df[~df[GROUP_KEY].astype(str).isin(rejected_geometry_ids)].copy()

    if rejected_rows.empty:
        rejected_rows = df.iloc[0:0].copy()

    # Add operator-facing QC / promotion columns to outputs
    curated_rows = curated_rows.copy()
    rejected_rows = rejected_rows.copy()

    curated_rows["geometry_qc_passed"] = qc_context["geometry_qc_passed"]
    curated_rows["aero_qc_passed"] = qc_context["aero_qc_passed"]
    curated_rows["qc_preset_used"] = qc_context["qc_preset_used"]
    curated_rows["promotion_ready"] = False  # assigned after report-level decision
    curated_rows["rejection_reason"] = ""

    rejected_rows["geometry_qc_passed"] = qc_context["geometry_qc_passed"]
    rejected_rows["aero_qc_passed"] = qc_context["aero_qc_passed"]
    rejected_rows["qc_preset_used"] = qc_context["qc_preset_used"]
    rejected_rows["promotion_ready"] = False
    rejected_rows["rejection_reason"] = rejected_rows[GROUP_KEY].astype(str).map(
        lambda gid: ";".join(sorted(rejected_geometry_reasons.get(gid, set())))
    )

    rejection_reason_counts: dict[str, int] = {}
    for reasons in rejected_geometry_reasons.values():
        for reason in reasons:
            rejection_reason_counts[reason] = rejection_reason_counts.get(reason, 0) + 1

    kept_geometry_count = curated_rows[GROUP_KEY].nunique() if not curated_rows.empty else 0
    rejected_geometry_count = len(rejected_geometry_ids)

    promotion_blockers = list(qc_context["promotion_blockers_from_qc"])

    if rejected_geometry_count > 0:
        promotion_blockers.append("curation_rejected_geometries")
    if not curated_rows.empty and kept_geometry_count == 0:
        promotion_blockers.append("no_kept_geometries")
    if curated_rows.empty:
        promotion_blockers.append("no_curated_rows")

    # Deduplicate while keeping order
    deduped_blockers: list[str] = []
    seen: set[str] = set()
    for blocker in promotion_blockers:
        if blocker not in seen:
            seen.add(blocker)
            deduped_blockers.append(blocker)
    promotion_blockers = deduped_blockers

    promotion_ready = len(promotion_blockers) == 0

    curated_rows["promotion_ready"] = promotion_ready

    curated_rows.to_csv(curated_csv_path, index=False)
    rejected_rows.to_csv(rejected_csv_path, index=False)

    report = {
        "dataset_root": str(dataset_root),
        "input_aero_dataset_csv": str(aero_dataset_csv),
        "input_aero_failures_csv": str(aero_failures_csv),
        "curated_aero_dataset_csv": str(curated_csv_path),
        "rejected_aero_rows_csv": str(rejected_csv_path),
        "expected_cases_per_geometry": expected_cases_per_geometry,
        "input_rows": int(len(df)),
        "kept_rows": int(len(curated_rows)),
        "rejected_rows": int(len(rejected_rows)),
        "kept_geometries": int(kept_geometry_count),
        "rejected_geometries": int(rejected_geometry_count),
        "rejection_reason_counts": rejection_reason_counts,
        "rejected_geometry_reasons": {
            geometry_id: sorted(reasons)
            for geometry_id, reasons in sorted(rejected_geometry_reasons.items())
        },
        "rules": {
            "reject_incomplete_groups": reject_incomplete_groups,
            "reject_groups_with_failures": reject_groups_with_failures,
            "reject_nonfinite_targets": reject_nonfinite_targets,
            "reject_control_diagnostic_failures": reject_control_diagnostic_failures,
        },
        "qc_preset_used": qc_context["qc_preset_used"],
        "geometry_qc_passed": qc_context["geometry_qc_passed"],
        "aero_qc_passed": qc_context["aero_qc_passed"],
        "promotion_ready": promotion_ready,
        "promotion_blockers": promotion_blockers,
    }

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report