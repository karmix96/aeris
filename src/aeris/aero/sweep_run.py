"""
Aero sweep orchestration.

Executes solver evaluations across a set of sweep cases, manages per-case
directories, collects results, and writes a sweep manifest.
"""

from __future__ import annotations

from aeris.aero.control_metadata import control_alias_row

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
from aeris.aero.io import _write_aero_result_json

def _should_retry_with_finer_paneling(result: Any) -> tuple[bool, str | None]:
    if getattr(result, "status", None) is not None:
        status_value = getattr(result.status, "value", str(result.status))
        if status_value == "invalid_input":
            return False, None

    cd = getattr(result, "cd", None)
    ld = getattr(result, "l_over_d", None)

    try:
        if cd is None:
            return True, "missing_cd"
        if float(cd) <= 0.0:
            return True, f"non_positive_cd:{cd}"
    except Exception:
        return True, "invalid_cd"

    if ld is None:
        return True, "missing_l_over_d"

    if not result.is_success():
        return True, f"status={result.status.value}"

    return False, None


def _inject_retry_metadata(
    final_result: Any,
    *,
    used: bool,
    reason: str | None,
    initial_paneling: dict[str, Any],
    fallback_paneling: dict[str, Any] | None,
    initial_result: Any,
) -> None:
    meta = final_result.solver_metadata or {}
    meta["fallback_retry"] = {
        "used": used,
        "reason": reason,
        "initial_paneling": initial_paneling,
        "fallback_paneling": fallback_paneling,
        "initial_status": initial_result.status.value,
        "initial_cd": initial_result.cd,
        "initial_l_over_d": initial_result.l_over_d,
    }
    final_result.solver_metadata = meta

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
        diff_input_deg = getattr(sweep_case, 'diff_input_deg', None)
        sweep_type = getattr(sweep_case, 'sweep_type', 'sym')

        case_label = make_flight_condition_case_label(idx, fc)
        if control_input_deg is not None:
            ctrl_slug = f"{control_input_deg:+.2f}".replace("+", "p").replace("-", "m").replace(".", "d")
            case_label = f"{case_label}_u{ctrl_slug}"
        diff_input_deg = sweep_case.diff_input_deg
        if diff_input_deg is not None:
            diff_slug = f"{diff_input_deg:+.2f}".replace("+", "p").replace("-", "m").replace(".", "d")
            case_label = f"{case_label}_da{diff_slug}"

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
                "diff_input_deg": diff_input_deg,
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
                "diff_input_deg": diff_input_deg,
                "sweep_type": sweep_case.sweep_type,
            },
        )

        initial_paneling = dict(case_settings.solver_options.get("paneling", {}) or {})

        result = solver.run_case(aero_input=aero_input, output_dir=case_dir)

        should_retry, retry_reason = _should_retry_with_finer_paneling(result)

        if should_retry:
            retry_settings = replace(
                case_settings,
                solver_options={
                    **case_settings.solver_options,
                    "paneling": {
                        "spanwise_resolution": 8,
                        "chordwise_resolution": 12,
                        "spanwise_spacing": initial_paneling.get("spanwise_spacing", "equal"),
                        "chordwise_spacing": initial_paneling.get("chordwise_spacing", "cosine"),
                    },
                    "control_input_deg": control_input_deg,
                    "diff_input_deg": diff_input_deg,
                },
            )

            retry_input = AeroInput(
                geometry=geometry,
                flight_condition=fc,
                settings=retry_settings,
                case_id=case_label,
                provenance={
                    **provenance,
                    "solver": solver_id,
                    "sweep_case_index": idx,
                    "sweep_case_label": case_label,
                    "control_input_deg": control_input_deg,
                    "diff_input_deg": diff_input_deg,
                    "sweep_type": sweep_case.sweep_type,
                },
            )

            retry_result = solver.run_case(aero_input=retry_input, output_dir=case_dir)
            retry_bad, _ = _should_retry_with_finer_paneling(retry_result)

            if not retry_bad:
                _inject_retry_metadata(
                    retry_result,
                    used=True,
                    reason=retry_reason,
                    initial_paneling=initial_paneling,
                    fallback_paneling=retry_settings.solver_options["paneling"],
                    initial_result=result,
                )
                result = retry_result
            else:
                _inject_retry_metadata(
                    result,
                    used=True,
                    reason=retry_reason,
                    initial_paneling=initial_paneling,
                    fallback_paneling=retry_settings.solver_options["paneling"],
                    initial_result=result,
                )
        else:
            _inject_retry_metadata(
                result,
                used=False,
                reason=None,
                initial_paneling=initial_paneling,
                fallback_paneling=None,
                initial_result=result,
            )

        result.artifact_paths["aero_result_json"] = str(case_dir / "aero_result.json")
        _write_aero_result_json(result, case_dir)

        record = {
            "case_index": idx,
            "case_label": case_label,
            "status": result.status.value,
            "runtime_sec": result.runtime_sec,
            "flight_condition": asdict(fc),
            "control_input_deg": control_input_deg,
            "diff_input_deg": diff_input_deg,
            "sweep_type": sweep_case.sweep_type,
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

        record.update(control_alias_row(
            record.get("control_input_deg"),
            diff_input_deg=record.get("diff_input_deg"),
        ))
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