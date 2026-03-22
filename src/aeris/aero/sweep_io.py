from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import AeroSweepResult, FlightCondition


def make_flight_condition_case_label(index: int, fc: FlightCondition) -> str:
    return (
        f"case_{index:04d}"
        f"_a{fc.alpha_deg:+.3f}"
        f"_b{fc.beta_deg:+.3f}"
        f"_V{fc.velocity_mps:.3f}"
        f"_alt{fc.altitude_m:.1f}"
        f"_p{fc.p_rad_s:+.4f}"
        f"_q{fc.q_rad_s:+.4f}"
        f"_r{fc.r_rad_s:+.4f}"
    )


def build_aero_sweep_summary(
    flight_conditions: list[FlightCondition],
    case_records: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "requested_n_cases": len(flight_conditions),
        "completed_n_cases": len(case_records),
        "case_labels": [record.get("case_label") for record in case_records],
        "flight_conditions": [asdict(fc) for fc in flight_conditions],
    }


def write_aero_sweep_manifest(
    output_path: str | Path,
    result: AeroSweepResult,
) -> Path:
    output_path = Path(output_path)
    output_path.write_text(
        json.dumps(
            {
                "cases": result.cases,
                "summary": result.summary,
            },
            indent=2,
        )
    )
    return output_path