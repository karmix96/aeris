"""
I/O utilities for aerodynamic sweep runs.

Handles case labeling, summary generation, and manifest persistence.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import AeroSweepResult, FlightCondition


def _slug_numeric(value: float, *, ndigits: int) -> str:
    rounded = f"{value:+.{ndigits}f}"
    rounded = rounded.replace("+", "p").replace("-", "m").replace(".", "d")
    return rounded


def make_flight_condition_case_label(index: int, fc: FlightCondition) -> str:
    return (
        f"case_{index:04d}"
        f"_a{_slug_numeric(fc.alpha_deg, ndigits=2)}"
        f"_b{_slug_numeric(fc.beta_deg, ndigits=2)}"
        f"_V{_slug_numeric(fc.velocity_mps, ndigits=2)}"
        f"_alt{_slug_numeric(fc.altitude_m, ndigits=1)}"
        f"_p{_slug_numeric(fc.p_rad_s, ndigits=3)}"
        f"_q{_slug_numeric(fc.q_rad_s, ndigits=3)}"
        f"_r{_slug_numeric(fc.r_rad_s, ndigits=3)}"
    )


def _successful_case_rows(case_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for record in case_records:
        if str(record.get("status", "")) != "success":
            continue

        aero_result = record.get("aero_result", {}) or {}
        scalars = aero_result.get("scalars", {}) or {}
        solver_metadata = aero_result.get("solver_metadata", {}) or {}

        row = {
            "case_index": record.get("case_index"),
            "case_label": record.get("case_label"),
            "control_input_deg": record.get("control_input_deg"),
            "alpha_deg": record.get("flight_condition", {}).get("alpha_deg"),
            "beta_deg": record.get("flight_condition", {}).get("beta_deg"),
            "velocity_mps": record.get("flight_condition", {}).get("velocity_mps"),
            "altitude_m": record.get("flight_condition", {}).get("altitude_m"),
            "p_rad_s": record.get("flight_condition", {}).get("p_rad_s"),
            "q_rad_s": record.get("flight_condition", {}).get("q_rad_s"),
            "r_rad_s": record.get("flight_condition", {}).get("r_rad_s"),
            "cl": scalars.get("cl"),
            "cd": scalars.get("cd"),
            "cm": scalars.get("cm"),
            "l_over_d": scalars.get("l_over_d"),
            "x_np": scalars.get("x_np"),
            "geometry_declares_controls": solver_metadata.get("geometry_declares_controls"),
            "airplane_has_controls": solver_metadata.get("airplane_has_controls"),
        }
        rows.append(row)

    return rows


def _find_zero_control_reference(
    rows: list[dict[str, Any]],
) -> dict[tuple[Any, ...], dict[str, Any]]:
    """
    Build a reference lookup keyed by flight condition tuple, using rows with u=0.
    """
    refs: dict[tuple[Any, ...], dict[str, Any]] = {}

    for row in rows:
        u = row.get("control_input_deg")
        if u is None or float(u) != 0.0:
            continue

        key = (
            row.get("alpha_deg"),
            row.get("beta_deg"),
            row.get("velocity_mps"),
            row.get("altitude_m"),
            row.get("p_rad_s"),
            row.get("q_rad_s"),
            row.get("r_rad_s"),
        )
        refs[key] = row

    return refs


def _build_control_effectiveness_rows(
    case_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = _successful_case_rows(case_records)
    zero_refs = _find_zero_control_reference(rows)

    out: list[dict[str, Any]] = []

    for row in rows:
        key = (
            row.get("alpha_deg"),
            row.get("beta_deg"),
            row.get("velocity_mps"),
            row.get("altitude_m"),
            row.get("p_rad_s"),
            row.get("q_rad_s"),
            row.get("r_rad_s"),
        )
        ref = zero_refs.get(key)

        cl = row.get("cl")
        cd = row.get("cd")
        cm = row.get("cm")

        cl0 = None if ref is None else ref.get("cl")
        cd0 = None if ref is None else ref.get("cd")
        cm0 = None if ref is None else ref.get("cm")

        out.append(
            {
                **row,
                "reference_case_label": None if ref is None else ref.get("case_label"),
                "reference_control_input_deg": None if ref is None else ref.get("control_input_deg"),
                "dcl_from_u0": None if cl is None or cl0 is None else float(cl) - float(cl0),
                "dcd_from_u0": None if cd is None or cd0 is None else float(cd) - float(cd0),
                "dcm_from_u0": None if cm is None or cm0 is None else float(cm) - float(cm0),
            }
        )

    return out


def build_aero_sweep_summary(
    flight_conditions: list[FlightCondition],
    case_records: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for record in case_records:
        status = str(record.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1

    failed_total = sum(
        status_counts.get(key, 0)
        for key in ("invalid_input", "invalid_output", "solver_failed")
    )

    control_effectiveness_rows = _build_control_effectiveness_rows(case_records)
    control_values = sorted(
        {
            float(row["control_input_deg"])
            for row in control_effectiveness_rows
            if row.get("control_input_deg") is not None
        }
    )

    return {
        "requested_n_cases": len(flight_conditions),
        "completed_n_cases": len(case_records),
        "n_success": status_counts.get("success", 0),
        "n_invalid_input": status_counts.get("invalid_input", 0),
        "n_invalid_output": status_counts.get("invalid_output", 0),
        "n_solver_failed": status_counts.get("solver_failed", 0),
        "n_failed_total": failed_total,
        "case_labels": [record.get("case_label") for record in case_records],
        "flight_conditions": [asdict(fc) for fc in flight_conditions],
        "status_counts": status_counts,
        "control_input_deg_values": control_values,
        "control_effectiveness_rows": control_effectiveness_rows,
    }


def write_aero_sweep_manifest(
    output_path: str | Path,
    result: AeroSweepResult,
) -> Path:
    output_path = Path(output_path)
    output_path.write_text(
        json.dumps(
            {
                "aero_sweep_result": {
                    "cases": result.cases,
                    "summary": result.summary,
                }
            },
            indent=2,
        )
    )
    return output_path