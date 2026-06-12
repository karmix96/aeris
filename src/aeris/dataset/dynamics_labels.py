from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from aeris.dataset.control_derivatives import compute_control_derivatives
from aeris.dataset.flyability_labels import compute_flyability_labels

DEFAULT_OUTPUT_REPORT = "dynamics_label_run_report.json"


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _path_exists_text(path_like: str | None) -> str | None:
    if not path_like:
        return None
    return str(Path(path_like).expanduser().resolve())


def _artifact_status(paths: list[Path]) -> dict[str, bool]:
    return {str(path): path.exists() for path in paths}


def _value_counts_from_csv(csv_path: Path, column: str) -> dict[str, int]:
    if not csv_path.exists():
        return {}
    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return {}
    if column not in df.columns:
        return {}
    return {str(value): int(count) for value, count in df[column].value_counts(dropna=False).items()}


def compute_dynamics_labels(
    *,
    dataset_root: Path,
    source: str = "auto",
    control_column: str | None = None,
    group_columns: list[str] | None = None,
    target_columns: list[str] | None = None,
    cm_column: str = "cm",
    recompute_control_derivatives: bool = True,
    max_abs_trim_delta_e_deg: float = 25.0,
    min_abs_cm_delta_e: float = 0.10,
    alpha_min_deg: float = -5.0,
    alpha_max_deg: float = 15.0,
    output_report_name: str = DEFAULT_OUTPUT_REPORT,
) -> dict[str, Any]:
    """Run the D2 -> D3 dynamics/flyability label chain for one aero dataset.

    This D4 runner is deliberately an orchestrator, not a new physics model. It
    produces a single evidence report that a workflow stage can depend on while
    keeping the derivative and flyability computations in their own modules.
    """
    dataset_root = dataset_root.expanduser().resolve()
    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset root does not exist: {dataset_root}")

    output_report = dataset_root / output_report_name
    control_csv = dataset_root / "control_derivatives.csv"
    control_report_path = dataset_root / "control_derivatives_report.json"
    flyability_csv = dataset_root / "flyability_labels.csv"
    flyability_report_path = dataset_root / "flyability_labels_report.json"

    stages: dict[str, Any] = {}

    if recompute_control_derivatives:
        control_report = compute_control_derivatives(
            dataset_root=dataset_root,
            source=source,
            control_column=control_column,
            group_columns=group_columns,
            target_columns=target_columns,
            min_abs_cm_delta_e=min_abs_cm_delta_e,
        )
        stages["control_derivatives"] = {
            "status": "completed",
            "mode": "computed",
            "computed_group_count": control_report.get("computed_group_count"),
            "skipped_group_count": control_report.get("skipped_group_count"),
            "control_column": control_report.get("control_column"),
            "used_legacy_control_alias": control_report.get("used_legacy_control_alias"),
            "output_csv": control_report.get("output_csv"),
            "output_report": control_report.get("output_report"),
        }
    else:
        if not control_csv.exists():
            raise FileNotFoundError(
                f"Missing control derivatives CSV: {control_csv}. "
                "Run compute-control-derivatives first or omit --no-recompute-control-derivatives."
            )
        control_report = _read_json_if_exists(control_report_path)
        stages["control_derivatives"] = {
            "status": "completed",
            "mode": "reused_existing",
            "computed_group_count": control_report.get("computed_group_count"),
            "skipped_group_count": control_report.get("skipped_group_count"),
            "control_column": control_report.get("control_column"),
            "used_legacy_control_alias": control_report.get("used_legacy_control_alias"),
            "output_csv": str(control_csv),
            "output_report": str(control_report_path) if control_report_path.exists() else None,
        }

    flyability_report = compute_flyability_labels(
        dataset_root=dataset_root,
        source=source,
        control_column=control_column,
        group_columns=group_columns,
        cm_column=cm_column,
        control_derivatives_csv=control_csv,
        max_abs_trim_delta_e_deg=max_abs_trim_delta_e_deg,
        min_abs_cm_delta_e=min_abs_cm_delta_e,
        alpha_min_deg=alpha_min_deg,
        alpha_max_deg=alpha_max_deg,
    )
    stages["flyability_labels"] = {
        "status": "completed",
        "mode": "computed",
        "label_row_count": flyability_report.get("label_row_count"),
        "computed_label_count": flyability_report.get("computed_label_count"),
        "skipped_label_count": flyability_report.get("skipped_label_count"),
        "longitudinal_basic_flyable_counts": flyability_report.get("longitudinal_basic_flyable_counts", {}),
        "control_column": flyability_report.get("control_column"),
        "used_legacy_control_alias": flyability_report.get("used_legacy_control_alias"),
        "output_csv": flyability_report.get("output_csv"),
        "output_report": flyability_report.get("output_report"),
    }

    artifacts = [
        control_csv,
        control_report_path,
        flyability_csv,
        flyability_report_path,
        output_report,
    ]

    flyable_counts = flyability_report.get("longitudinal_basic_flyable_counts", {}) or {}
    label_false_count = int(flyable_counts.get("False", 0) or flyable_counts.get("False.0", 0) or 0)
    label_true_count = int(flyable_counts.get("True", 0) or flyable_counts.get("True.0", 0) or 0)
    label_nan_count = int(flyable_counts.get("nan", 0) or flyable_counts.get("NaN", 0) or 0)

    if not flyable_counts:
        # Defensive fallback if a caller changes flyability report formatting later.
        counts = _value_counts_from_csv(flyability_csv, "label_longitudinal_basic_flyable")
        label_false_count = int(counts.get("False", 0) or counts.get("False.0", 0) or 0)
        label_true_count = int(counts.get("True", 0) or counts.get("True.0", 0) or 0)
        label_nan_count = int(counts.get("nan", 0) or counts.get("NaN", 0) or 0)

    completed_label_count = int(flyability_report.get("computed_label_count", 0) or 0)
    skipped_label_count = int(flyability_report.get("skipped_label_count", 0) or 0)
    red_flag_count = int(
        flyability_report.get("red_flag_count", label_false_count + label_nan_count + skipped_label_count)
        or 0
    )
    red_flag_reason_counts = flyability_report.get("red_flag_reason_counts", {}) or {}
    trim_failure_reason_counts = flyability_report.get("trim_failure_reason_counts", {}) or {}
    label_failure_stage_counts = flyability_report.get("label_failure_stage_counts", {}) or {}

    report = {
        "schema_version": "d4_dynamics_label_batch_v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "dataset_root": str(dataset_root),
        "source": flyability_report.get("source", source),
        # DYN-1: overall_status reflects actual label outcome so operators can
        # distinguish "completed but all non-flyable" from a pipeline failure.
        "overall_status": (
            "completed_all_non_flyable" if (label_true_count == 0 and completed_label_count > 0)
            else "completed_partial" if (skipped_label_count > 0 and completed_label_count > 0)
            else "completed_all_skipped" if (completed_label_count == 0 and skipped_label_count > 0)
            else "completed"
        ),
        "design_status": (
            "non_flyable" if (label_true_count == 0 and completed_label_count > 0)
            else "partially_flyable" if (0 < label_true_count < completed_label_count)
            else "flyable" if (label_true_count == completed_label_count and completed_label_count > 0)
            else "unknown"
        ),
        "runner": "aeris.dataset.dynamics_labels.compute_dynamics_labels",
        "stages": stages,
        "label_summary": {
            "computed_label_count": completed_label_count,
            "skipped_label_count": skipped_label_count,
            "longitudinal_basic_flyable_true_count": label_true_count,
            "longitudinal_basic_flyable_false_count": label_false_count,
            "longitudinal_basic_flyable_unknown_count": label_nan_count,
            "red_flag_count": red_flag_count,
            "red_flag_reason_counts": red_flag_reason_counts,
            "trim_failure_reason_counts": trim_failure_reason_counts,
            "label_failure_stage_counts": label_failure_stage_counts,
            "longitudinal_basic_flyable_counts": flyable_counts,
        },
        # DYN-2: trim summary for quick operator sanity check without opening CSV
        "trim_summary": flyability_report.get("trim_summary", {}),
        "thresholds": flyability_report.get("thresholds", {}),
        "artifacts": {
            "control_derivatives_csv": str(control_csv),
            "control_derivatives_report_json": str(control_report_path),
            "flyability_labels_csv": str(flyability_csv),
            "flyability_labels_report_json": str(flyability_report_path),
            "dynamics_label_run_report_json": str(output_report),
        },
        "artifact_exists": _artifact_status(artifacts),
        "limitations": [
            "batch_orchestration_only_not_new_physics",
            "uses_d2_symmetric_elevon_finite_difference_derivatives",
            "uses_d3_first_order_trim_control_flyability_labels",
            "differential_elevon_not_computed_until_solver_wiring_exists",
            "not_a_full_nonlinear_trim_solver",
            "not_a_mil_std_compliance_claim",
        ],
    }
    _write_json(output_report, report)
    return report
