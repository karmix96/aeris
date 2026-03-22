from __future__ import annotations
from pathlib import Path

import json
from pathlib import Path
from typing import Any

from .models import AeroFailure, AeroResult, AeroStatus


def load_aero_result(path: str | Path) -> AeroResult:
    path = Path(path)
    data = json.loads(path.read_text())

    failure_data = data.get("failure")
    failure = None
    if failure_data is not None:
        failure = AeroFailure(
            status=AeroStatus(failure_data["status"]),
            reason=failure_data["reason"],
            message=failure_data["message"],
            exception_type=failure_data.get("exception_type"),
        )

    scalars = data.get("scalars", {})

    return AeroResult(
        status=AeroStatus(data["status"]),
        solver_id=data["solver_id"],
        cl=scalars.get("cl"),
        cd=scalars.get("cd"),
        cm=scalars.get("cm"),
        l_over_d=scalars.get("l_over_d"),
        cy=scalars.get("cy"),
        cl_roll=scalars.get("cl_roll"),
        cn=scalars.get("cn"),
        cd_ind=scalars.get("cd_ind"),
        cd_ff=scalars.get("cd_ff"),
        span_efficiency=scalars.get("span_efficiency"),
        x_np=scalars.get("x_np"),
        stability_axis_derivatives=data.get("stability_axis_derivatives", {}) or {},
        body_axis_derivatives=data.get("body_axis_derivatives", {}) or {},
        derived_metrics=data.get("derived_metrics", {}) or {},
        runtime_sec=data.get("runtime_sec"),
        warnings=data.get("warnings", []) or [],
        artifact_paths=data.get("artifact_paths", {}) or {},
        solver_metadata=data.get("solver_metadata", {}) or {},
        failure=failure,
    )


def find_aero_result_json(run_dir: str | Path) -> Path:
    run_dir = Path(run_dir)

    direct = run_dir / "aero_result.json"
    if direct.exists():
        return direct

    nested = run_dir / "aero" / "aero_result.json"
    if nested.exists():
        return nested

    raise FileNotFoundError(
        f"Could not find aero_result.json in '{run_dir}' or '{run_dir / 'aero'}'."
    )


def load_aero_result_from_run_dir(run_dir: str | Path) -> AeroResult:
    return load_aero_result(find_aero_result_json(run_dir))

def resolve_aero_result_path(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    candidates = [
        run_dir / "aero" / "aero_result.json",
        run_dir / "aero_result.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        f"Could not find aero_result.json under {run_dir}"
    )


def read_aero_result(run_dir: Path) -> dict:
    path = resolve_aero_result_path(Path(run_dir))
    return json.loads(path.read_text(encoding="utf-8"))