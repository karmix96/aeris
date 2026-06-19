"""
Persistence and readback helpers for saved aerodynamic results.

This module locates saved aero_result.json files, loads them either as raw JSON
dictionaries or reconstructed AeroResult objects, and provides a stable readback
path for CLI inspection and replay workflows.
"""

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
        cd_profile=scalars.get("cd_profile"),
        cd_total=scalars.get("cd_total"),
        l_over_d_viscous=scalars.get("l_over_d_viscous"),
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
    """Load AeroResult from an existing run directory.

    Delegates path resolution to resolve_aero_result_path (single source of truth).
    find_aero_result_json is retained for callers that need it directly.
    """
    return load_aero_result(resolve_aero_result_path(Path(run_dir)))

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

# ---------------------------------------------------------------------------
# 3.11 — moved from aerosandbox_avl.py to break solver→pipeline upward dep
# ---------------------------------------------------------------------------

AERO_RESULT_SCHEMA_VERSION = "aero_result_v1"


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    try:
        return float(value)
    except Exception:
        return str(value)


def _write_aero_result_json(result: AeroResult, output_dir: Path) -> Path:
    """Serialize AeroResult to aero_result.json.

    Lives in io.py so pipeline and solver can both import it without
    creating a solver -> pipeline upward dependency.
    """
    payload = {
        "schema_version": AERO_RESULT_SCHEMA_VERSION,
        "status": result.status.value,
        "solver_id": result.solver_id,
        "scalars": {
            "cl": result.cl,
            "cd": result.cd,
            "cm": result.cm,
            "l_over_d": result.l_over_d,
            "cy": result.cy,
            "cl_roll": result.cl_roll,
            "cn": result.cn,
            "cd_ind": result.cd_ind,
            "cd_ff": result.cd_ff,
            "span_efficiency": result.span_efficiency,
            "x_np": result.x_np,
            "cd_profile": result.cd_profile,
            "cd_total": result.cd_total,
            "l_over_d_viscous": result.l_over_d_viscous,
        },
        "stability_axis_derivatives": result.stability_axis_derivatives,
        "body_axis_derivatives": result.body_axis_derivatives,
        "derived_metrics": result.derived_metrics,
        "runtime_sec": result.runtime_sec,
        "warnings": result.warnings,
        "artifact_paths": result.artifact_paths,
        "solver_metadata": result.solver_metadata,
        "failure": (
            {
                "status": result.failure.status.value,
                "reason": result.failure.reason,
                "message": result.failure.message,
                "exception_type": result.failure.exception_type,
            }
            if result.failure is not None
            else None
        ),
    }
    out_path = output_dir / "aero_result.json"
    out_path.write_text(json.dumps(_json_safe(payload), indent=2))
    return out_path