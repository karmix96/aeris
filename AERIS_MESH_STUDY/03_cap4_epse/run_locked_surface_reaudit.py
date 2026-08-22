#!/usr/bin/env python3
"""Re-audit locked Stage 01 surface reports under the current surface gate."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("AERIS_MESH_STUDY")
SURFACE_ROOT = ROOT / "artifacts/stage01/epse_calibration/surfaces"
PROBE_REPORT = ROOT / "03_cap4_epse/tip_topology_probe_report.json"


POLICY = {
    "min_shape_metric": 1.0e-6,
    "min_scaled_jacobian": 0.0,
    "max_adjacent_normal_angle_deg": 180.0,
}


def _failure_reasons(global_metrics: dict[str, float]) -> list[dict[str, object]]:
    reasons: list[dict[str, object]] = []
    if not float(global_metrics["min_shape_metric"]) > POLICY["min_shape_metric"]:
        reasons.append(
            {
                "check": "minimum_shape_metric",
                "value": float(global_metrics["min_shape_metric"]),
                "required": f"> {POLICY['min_shape_metric']}",
            }
        )
    if not float(global_metrics["min_scaled_jacobian"]) > POLICY["min_scaled_jacobian"]:
        reasons.append(
            {
                "check": "positive_scaled_jacobian",
                "value": float(global_metrics["min_scaled_jacobian"]),
                "required": f"> {POLICY['min_scaled_jacobian']}",
            }
        )
    if not (
        float(global_metrics["max_adjacent_normal_angle_deg"])
        <= POLICY["max_adjacent_normal_angle_deg"]
    ):
        reasons.append(
            {
                "check": "maximum_adjacent_normal_angle",
                "value": float(global_metrics["max_adjacent_normal_angle_deg"]),
                "required": f"<= {POLICY['max_adjacent_normal_angle_deg']}",
            }
        )
    return reasons


def _locked_surface_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for report_path in sorted(SURFACE_ROOT.glob("lhs7_*/surface/surface_report.json")):
        report = json.loads(report_path.read_text())
        global_metrics = report["global"]
        failures = _failure_reasons(global_metrics)
        rows.append(
            {
                "sample_id": report_path.parts[-3],
                "old_accepted_pre_pyhyp": bool(report.get("accepted_pre_pyhyp")),
                "current_accepted_pre_pyhyp": not failures,
                "min_shape_metric": float(global_metrics["min_shape_metric"]),
                "min_scaled_jacobian": float(global_metrics["min_scaled_jacobian"]),
                "max_adjacent_normal_angle_deg": float(
                    global_metrics["max_adjacent_normal_angle_deg"]
                ),
                "failure_reasons": failures,
                "surface_report": str(report_path),
            }
        )
    return rows


def _probe_rows() -> list[dict[str, object]]:
    if not PROBE_REPORT.is_file():
        return []
    report = json.loads(PROBE_REPORT.read_text())
    rows: list[dict[str, object]] = []
    for item in report.get("variants", report.get("results", [])):
        metrics = {
            "min_shape_metric": item["global_min_shape_metric"],
            "min_scaled_jacobian": item["global_min_scaled_jacobian"],
            "max_adjacent_normal_angle_deg": item["global_max_adjacent_normal_angle_deg"],
        }
        rows.append(
            {
                "variant": item["variant"],
                "topology_id": item["topology_id"],
                "accepted_under_current_policy": not _failure_reasons(metrics),
                **metrics,
                "failure_reasons": _failure_reasons(metrics),
            }
        )
    return rows


def _metric_range(rows: list[dict[str, object]], key: str) -> dict[str, float | None]:
    if not rows:
        return {"min": None, "max": None}
    values = [float(row[key]) for row in rows]
    return {"min": min(values), "max": max(values)}


def main() -> None:
    locked_rows = _locked_surface_rows()
    probe_rows = _probe_rows()
    failure_counts = Counter(
        reason["check"] for row in locked_rows for reason in row["failure_reasons"]
    )
    probe_failure_counts = Counter(
        reason["check"] for row in probe_rows for reason in row["failure_reasons"]
    )
    payload = {
        "schema": "aeris.mesh_study.stage01_locked_surface_reaudit.v2",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "policy": POLICY,
        "source": "existing locked L3 surface_report.json artifacts, no regeneration and no pyHyp",
        "surface_count": len(locked_rows),
        "old_accepted_count": sum(1 for row in locked_rows if row["old_accepted_pre_pyhyp"]),
        "current_accepted_count": sum(
            1 for row in locked_rows if row["current_accepted_pre_pyhyp"]
        ),
        "current_failed_count": sum(
            1 for row in locked_rows if not row["current_accepted_pre_pyhyp"]
        ),
        "failure_count_by_check": dict(failure_counts),
        "locked_metric_ranges": {
            key: _metric_range(locked_rows, key)
            for key in (
                "min_shape_metric",
                "min_scaled_jacobian",
                "max_adjacent_normal_angle_deg",
            )
        },
        "probe_variant_count": len(probe_rows),
        "probe_failure_count_by_check": dict(probe_failure_counts),
        "probe_metric_ranges": {
            key: _metric_range(probe_rows, key)
            for key in (
                "min_shape_metric",
                "min_scaled_jacobian",
                "max_adjacent_normal_angle_deg",
            )
        },
        "rows": locked_rows,
        "probe_rows": probe_rows,
        "supersedes": "locked_l3_surface_reaudit_fixed_gate.json",
        "supersedes_reason": (
            "The v1 report used unsupported post-hoc min_shape_metric and "
            "max_adjacent_normal_angle thresholds. v2 restores the prior study values "
            "and retains only the mathematical positive scaled-Jacobian floor."
        ),
    }

    json_path = ROOT / "03_cap4_epse/locked_l3_surface_reaudit_scaled_jac_only.json"
    md_path = ROOT / "03_cap4_epse/locked_l3_surface_reaudit_scaled_jac_only.md"
    json_path.write_text(json.dumps(payload, indent=2) + "\n")
    lines = [
        "# Locked L3 Surface Re-Audit, Corrected Gate",
        "",
        (
            "Result: "
            f"{payload['current_failed_count']} of {payload['surface_count']} locked "
            "surfaces fail the corrected Stage 01 surface gate."
        ),
        "",
        (
            "Policy: min_shape_metric > 1.0e-6, min_scaled_jacobian > 0.0, "
            "max_adjacent_normal_angle_deg <= 180.0."
        ),
        "",
        "This supersedes locked_l3_surface_reaudit_fixed_gate.* because the earlier "
        "3.0e-2 shape floor and 170 deg angle limit were not derived.",
        "",
        "| sample | old accepted | current accepted | min shape | min scaled jac | "
        "max normal angle | failures |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in locked_rows:
        failures = ",".join(reason["check"] for reason in row["failure_reasons"]) or "none"
        lines.append(
            f"| {row['sample_id']} | {row['old_accepted_pre_pyhyp']} | "
            f"{row['current_accepted_pre_pyhyp']} | {row['min_shape_metric']:.12g} | "
            f"{row['min_scaled_jacobian']:.12g} | "
            f"{row['max_adjacent_normal_angle_deg']:.12g} | {failures} |"
        )
    lines.extend(
        [
            "",
            "## Probe Variants",
            "",
            "| variant | accepted | min shape | min scaled jac | max normal angle | failures |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in probe_rows:
        failures = ",".join(reason["check"] for reason in row["failure_reasons"]) or "none"
        lines.append(
            f"| {row['variant']} | {row['accepted_under_current_policy']} | "
            f"{row['min_shape_metric']:.12g} | {row['min_scaled_jacobian']:.12g} | "
            f"{row['max_adjacent_normal_angle_deg']:.12g} | {failures} |"
        )
    md_path.write_text("\n".join(lines) + "\n")
    print(
        json.dumps(
            {
                "json": str(json_path),
                "md": str(md_path),
                "current_failed_count": payload["current_failed_count"],
                "probe_failure_count_by_check": payload["probe_failure_count_by_check"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
