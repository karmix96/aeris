"""
Aero sweep orchestration.

Executes solver evaluations across a set of sweep cases, manages per-case
directories, collects results, and writes a sweep manifest.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from typing import Any
import json
from .io import find_aero_result_json
from .models import AeroInput, AeroSolverSettings, AeroSweepResult, FlightCondition
from .registry import create_solver
from .sweep import expand_aero_sweep
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
    max_cases: int | None = None,
    print_progress: bool = True,
) -> AeroSweepResult:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    solver = create_solver(solver_id)
    provenance = provenance or {}

    base_control_input_deg = settings.solver_options.get("control_input_deg", None)

    sweep_cases = expand_aero_sweep(
        base=base_flight_condition,
        sweep=sweep,
        base_control_input_deg=base_control_input_deg,
        max_cases=max_cases,
    )

    n_total = len(sweep_cases)
    case_records: list[dict[str, Any]] = []

    for idx, sweep_case in enumerate(sweep_cases):
        fc = sweep_case.flight_condition
        control_input_deg = sweep_case.control_input_deg

        case_label = make_flight_condition_case_label(idx, fc)
        if control_input_deg is not None:
            ctrl_slug = f"{control_input_deg:+.2f}".replace("+", "p").replace("-", "m").replace(".", "d")
            case_label = f"{case_label}_u{ctrl_slug}"

        case_dir = output_dir / case_label
        case_dir.mkdir(parents=True, exist_ok=True)

        if print_progress:
            print(
                f"[AERIS][AERO_SWEEP] {idx + 1}/{n_total} -> {case_label} "
                f"(u={control_input_deg})"
            )

        case_settings = replace(
            settings,
            solver_options={
                **settings.solver_options,
                "control_input_deg": control_input_deg,
            },
        )

        aero_input = AeroInput(
            geometry=geometry,
            flight_condition=fc,
            settings=case_settings,
            case_id=case_label,
            provenance={
                **provenance,
                "solver": solver_id,
                "sweep_case_index": idx,
                "sweep_case_label": case_label,
                "control_input_deg": control_input_deg,
            },
        )

        result = solver.run_case(aero_input=aero_input, output_dir=case_dir)

        record = {
            "case_index": idx,
            "case_label": case_label,
            "status": result.status.value,
            "runtime_sec": result.runtime_sec,
            "flight_condition": asdict(fc),
            "control_input_deg": control_input_deg,
            "case_dir": str(case_dir),
            "aero_result_json": None,
            "aero_result": None,
        }

        try:
            aero_result_json = find_aero_result_json(case_dir)
            record["aero_result_json"] = str(aero_result_json)
            record["aero_result"] = json.loads(aero_result_json.read_text(encoding="utf-8"))
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
        flight_conditions=[case.flight_condition for case in sweep_cases],
        case_records=case_records,
    )
    summary["total_runtime_sec"] = sum(
        float(record["runtime_sec"])
        for record in case_records
        if record.get("runtime_sec") is not None
    )
    summary["control_input_deg_values"] = [
        case.control_input_deg for case in sweep_cases
    ]

    result = AeroSweepResult(cases=case_records, summary=summary)
    write_aero_sweep_manifest(output_dir / "aero_sweep_manifest.json", result)
    return result