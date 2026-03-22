from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .io import find_aero_result_json
from .models import (
    AeroInput,
    AeroSolverSettings,
    AeroSweepResult,
    FlightCondition,
)
from .registry import create_solver
from .sweep import expand_flight_condition_sweep
from .sweep_io import (
    build_aero_sweep_summary,
    make_flight_condition_case_label,
    write_aero_sweep_manifest,
)


def run_aero_sweep(
    *,
    geometry,
    base_flight_condition: FlightCondition,
    sweep,
    solver_id: str,
    settings: AeroSolverSettings,
    output_dir: str | Path,
    provenance: dict[str, Any] | None = None,
) -> AeroSweepResult:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    solver = create_solver(solver_id)
    provenance = provenance or {}

    flight_conditions = expand_flight_condition_sweep(
        base=base_flight_condition,
        sweep=sweep,
    )

    case_records: list[dict[str, Any]] = []

    for idx, fc in enumerate(flight_conditions):
        case_label = make_flight_condition_case_label(idx, fc)
        case_dir = output_dir / case_label
        case_dir.mkdir(parents=True, exist_ok=True)

        aero_input = AeroInput(
            geometry=geometry,
            flight_condition=fc,
            settings=settings,
            case_id=case_label,
            provenance={
                **provenance,
                "solver": solver_id,
                "sweep_case_index": idx,
                "sweep_case_label": case_label,
            },
        )

        result = solver.run_case(aero_input=aero_input, output_dir=case_dir)

        record = {
            "case_index": idx,
            "case_label": case_label,
            "status": result.status.value,
            "flight_condition": asdict(fc),
            "case_dir": str(case_dir),
            "aero_result_json": None,
        }

        try:
            aero_result_json = find_aero_result_json(case_dir)
            record["aero_result_json"] = str(aero_result_json)
        except Exception:
            pass

        if result.failure is not None:
            record["failure"] = {
                "status": result.failure.status.value,
                "reason": result.failure.reason,
                "message": result.failure.message,
                "exception_type": result.failure.exception_type,
            }

        case_records.append(record)

    summary = build_aero_sweep_summary(
        flight_conditions=flight_conditions,
        case_records=case_records,
    )

    result = AeroSweepResult(
        cases=case_records,
        summary=summary,
    )

    write_aero_sweep_manifest(output_dir / "aero_sweep_manifest.json", result)
    return result