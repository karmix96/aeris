"""
I/O utilities for aerodynamic sweep runs.

Handles case labeling, summary generation, and manifest persistence.
"""

from __future__ import annotations

import json
import re
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
    }


def write_aero_sweep_manifest(
    output_path: str | Path,
    result: AeroSweepResult,
) -> Path:
    output_path = Path(output_path)
    output_path.write_text(
        json.dumps({"cases": result.cases, "summary": result.summary}, indent=2)
    )
    return output_path