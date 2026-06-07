"""State-space run orchestration for saved AERIS aero runs."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from aeris.dynamics.analysis import load_geometry_summary
from aeris.dynamics.models import MassProperties
from aeris.dynamics.state_space import DimDerivatives, compute_full_lateral, compute_full_longitudinal

STATE_SPACE_RESULT_SCHEMA_VERSION = "state_space_result_v0.2"


def _json_safe(value: Any) -> Any:
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else float(value)
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    try:
        return float(value)
    except Exception:
        return str(value)


def _resolve_aero_result_path(run_dir: Path) -> Path:
    for candidate in (run_dir / "aero_result.json", run_dir / "aero" / "aero_result.json"):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Could not find aero_result.json under {run_dir}")


def _read_aero_result(run_dir: Path) -> dict[str, Any]:
    return json.loads(_resolve_aero_result_path(Path(run_dir)).read_text(encoding="utf-8"))


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) or math.isinf(out) else out


def _first_float(*values: Any) -> float | None:
    for value in values:
        out = _as_float(value)
        if out is not None:
            return out
    return None


def _nested_get(data: Any, *names: str) -> Any:
    if not isinstance(data, dict):
        return None
    for k, v in data.items():
        if k in names and v is not None:
            return v
        if isinstance(v, dict):
            found = _nested_get(v, *names)
            if found is not None:
                return found
    return None


def _reference_values(run_dir: Path, *, sref_m2: float | None, mac_m: float | None, span_m: float | None) -> dict[str, Any]:
    geo = load_geometry_summary(run_dir) or {}
    ref = geo.get("reference_values", {}) if isinstance(geo, dict) else {}
    return {
        "sref_m2": _first_float(sref_m2, ref.get("area_m2"), ref.get("reference_area_m2"), geo.get("area_m2"), geo.get("approx_area_m2")),
        "mac_m": _first_float(mac_m, ref.get("mean_aerodynamic_chord_m"), ref.get("mac_m"), geo.get("mean_aerodynamic_chord_m"), geo.get("mac_m")),
        "span_m": _first_float(span_m, ref.get("span_m"), ref.get("full_span_m"), geo.get("span_m"), geo.get("full_span_m")),
        "geometry_summary_found": bool(geo),
    }


def build_dim_derivatives_from_saved_run(
    *,
    run_dir: Path,
    mass_properties: MassProperties,
    sref_m2: float | None = None,
    mac_m: float | None = None,
    span_m: float | None = None,
    ixz_kg_m2: float = 0.0,
) -> tuple[DimDerivatives | None, dict[str, Any]]:
    run_dir = Path(run_dir)
    aero = _read_aero_result(run_dir)
    scalars = aero.get("scalars", {}) or aero
    sad = aero.get("stability_axis_derivatives", {}) or {}
    meta = aero.get("solver_metadata", {}) or {}
    fc = meta.get("flight_condition") or aero.get("flight_condition") or {}
    fc = fc if isinstance(fc, dict) else {}
    refs = _reference_values(run_dir, sref_m2=sref_m2, mac_m=mac_m, span_m=span_m)

    required = {
        "CL0/cl": _first_float(scalars.get("cl"), scalars.get("CL")),
        "CD0/cd": _first_float(scalars.get("cd"), scalars.get("CD")),
        "CLa": _first_float(sad.get("CLa"), sad.get("cla"), _nested_get(aero, "CLa", "cla")),
        "Cma": _first_float(sad.get("Cma"), sad.get("cma"), _nested_get(aero, "Cma", "cma")),
        "CYb": _first_float(sad.get("CYb"), sad.get("cyb"), _nested_get(aero, "CYb", "cyb")),
        "Clb": _first_float(sad.get("Clb"), sad.get("clb"), _nested_get(aero, "Clb", "clb")),
        "Cnb": _first_float(sad.get("Cnb"), sad.get("cnb"), _nested_get(aero, "Cnb", "cnb")),
        "Clp": _first_float(sad.get("Clp"), sad.get("clp"), _nested_get(aero, "Clp", "clp")),
        "Cmq": _first_float(sad.get("Cmq"), sad.get("cmq"), _nested_get(aero, "Cmq", "cmq")),
        "Cnr": _first_float(sad.get("Cnr"), sad.get("cnr"), _nested_get(aero, "Cnr", "cnr")),
        "Clr": _first_float(sad.get("Clr"), sad.get("clr"), _nested_get(aero, "Clr", "clr")),
        "Cnp": _first_float(sad.get("Cnp"), sad.get("cnp"), _nested_get(aero, "Cnp", "cnp")),
        "alpha_deg": _first_float(fc.get("alpha_deg")),
        "velocity_mps": _first_float(fc.get("velocity_mps")),
        "altitude_m": _first_float(fc.get("altitude_m"), 0.0),
        "sref_m2": refs["sref_m2"],
        "mac_m": refs["mac_m"],
        "span_m": refs["span_m"],
        "mass_kg": mass_properties.mass_kg,
        "ixx_kg_m2": mass_properties.inertia.ixx_kg_m2,
        "iyy_kg_m2": mass_properties.inertia.iyy_kg_m2,
        "izz_kg_m2": mass_properties.inertia.izz_kg_m2,
    }
    missing = [k for k, v in required.items() if _as_float(v) is None]
    diagnostic = {
        "required_inputs": _json_safe(required),
        "missing_inputs": missing,
        "reference_values": refs,
        "flight_condition": fc,
        "solver_id": aero.get("solver_id"),
    }
    if missing:
        return None, diagnostic

    dd = DimDerivatives(
        CLa=float(required["CLa"]), Cma=float(required["Cma"]),
        CYb=float(required["CYb"]), Clb=float(required["Clb"]), Cnb=float(required["Cnb"]),
        Clp=float(required["Clp"]), Cmq=float(required["Cmq"]), Cnr=float(required["Cnr"]),
        Clr=float(required["Clr"]), Cnp=float(required["Cnp"]),
        CLu=_first_float(sad.get("CLu"), _nested_get(aero, "CLu")) or 0.0,
        Cmu=_first_float(sad.get("Cmu"), _nested_get(aero, "Cmu")) or 0.0,
        CLq=_first_float(sad.get("CLq"), _nested_get(aero, "CLq")) or 0.0,
        CLp=_first_float(sad.get("CLp"), _nested_get(aero, "CLp")) or 0.0,
        CLr=_first_float(sad.get("CLr"), _nested_get(aero, "CLr")) or 0.0,
        CYp=_first_float(sad.get("CYp"), _nested_get(aero, "CYp")) or 0.0,
        CYr=_first_float(sad.get("CYr"), _nested_get(aero, "CYr")) or 0.0,
        CDa=_first_float(sad.get("CDa"), _nested_get(aero, "CDa")) or 0.0,
        CD0=float(required["CD0/cd"]),
        Cmad=_first_float(sad.get("Cmad"), sad.get("CMad"), _nested_get(aero, "Cmad", "CMad")) or 0.0,
        CL0=float(required["CL0/cl"]), CD0_trim=float(required["CD0/cd"]),
        alpha0_rad=math.radians(float(required["alpha_deg"])),
        velocity_mps=float(required["velocity_mps"]), altitude_m=float(required["altitude_m"]),
        sref_m2=float(required["sref_m2"]), mac_m=float(required["mac_m"]), span_m=float(required["span_m"]),
        mass_kg=float(required["mass_kg"]),
        ixx_kg_m2=float(required["ixx_kg_m2"]), iyy_kg_m2=float(required["iyy_kg_m2"]), izz_kg_m2=float(required["izz_kg_m2"]), ixz_kg_m2=ixz_kg_m2,
    )
    return dd, diagnostic



def _eigenvalue_real_parts(section: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for item in section.get("all_eigenvalues", []) or []:
        if not isinstance(item, dict):
            continue
        real = _as_float(item.get("real"))
        if real is not None:
            values.append(real)
    return values


def _section_stability_summary(section: dict[str, Any]) -> dict[str, Any]:
    """Summarize full-matrix eigenvalue stability without trusting mode labels.

    Mode classifiers are useful, but they can hide an unassigned positive real
    eigenvalue. This summary scans every eigenvalue in the 4x4 system.
    """
    if not section.get("valid"):
        return {
            "valid": False,
            "eigenvalue_count": 0,
            "max_real_eigenvalue": None,
            "unstable_eigenvalue_count": None,
            "has_unstable_eigenvalue": None,
            "all_eigenvalues_stable": None,
            "reason": section.get("reason") or "section_invalid",
        }

    real_parts = _eigenvalue_real_parts(section)
    if not real_parts:
        return {
            "valid": False,
            "eigenvalue_count": 0,
            "max_real_eigenvalue": None,
            "unstable_eigenvalue_count": None,
            "has_unstable_eigenvalue": None,
            "all_eigenvalues_stable": None,
            "reason": "missing_eigenvalues",
        }

    unstable_count = sum(1 for real in real_parts if real > 0.0)
    max_real = max(real_parts)
    return {
        "valid": True,
        "eigenvalue_count": len(real_parts),
        "max_real_eigenvalue": max_real,
        "unstable_eigenvalue_count": unstable_count,
        "has_unstable_eigenvalue": unstable_count > 0,
        "all_eigenvalues_stable": unstable_count == 0,
        "reason": None,
    }


def build_linear_stability_summary(
    *,
    longitudinal: dict[str, Any],
    lateral_directional: dict[str, Any],
) -> dict[str, Any]:
    """Build explicit full-eigenvalue stability flags for D5/D5.1 reports."""
    longitudinal_summary = _section_stability_summary(longitudinal)
    lateral_summary = _section_stability_summary(lateral_directional)

    section_summaries = {
        "longitudinal": longitudinal_summary,
        "lateral_directional": lateral_summary,
    }
    valid_sections = [summary for summary in section_summaries.values() if summary.get("valid") is True]
    known_sections = [
        summary
        for summary in section_summaries.values()
        if summary.get("all_eigenvalues_stable") is not None
    ]
    total_unstable = sum(
        int(summary.get("unstable_eigenvalue_count") or 0)
        for summary in known_sections
    )
    max_values = [
        summary["max_real_eigenvalue"]
        for summary in known_sections
        if summary.get("max_real_eigenvalue") is not None
    ]

    overall_known = len(known_sections) == 2
    overall_stable = (total_unstable == 0) if overall_known else None

    return {
        "method": "full_eigenvalue_real_part_scan",
        "overall_known": overall_known,
        "overall_linear_stable": overall_stable,
        "total_unstable_eigenvalue_count": total_unstable if overall_known else None,
        "max_real_eigenvalue": max(max_values) if max_values else None,
        "valid_section_count": len(valid_sections),
        "sections": section_summaries,
        "notes": [
            "This summary scans all eigenvalues, not only named mode summaries.",
            "A positive real eigenvalue means local linear instability for this operating point.",
        ],
    }

def _limitations() -> list[str]:
    return [
        "Full 4x4 linear state-space diagnostic around one operating point.",
        "Uses AVL/AERIS linear derivatives and supplied mass/inertia values.",
        "Not a nonlinear flight simulator.",
        "Not a trim solver and not a MIL-STD compliance claim.",
        "Mode naming is automated and should be reviewed for unusual eigenvalue patterns.",
    ]


def compute_state_space_result(
    *,
    run_dir: Path,
    mass_properties: MassProperties,
    sref_m2: float | None = None,
    mac_m: float | None = None,
    span_m: float | None = None,
    ixz_kg_m2: float = 0.0,
) -> dict[str, Any]:
    dd, diagnostic = build_dim_derivatives_from_saved_run(run_dir=run_dir, mass_properties=mass_properties, sref_m2=sref_m2, mac_m=mac_m, span_m=span_m, ixz_kg_m2=ixz_kg_m2)
    if dd is None:
        longitudinal = {"valid": False, "reason": "missing_required_inputs"}
        lateral = {"valid": False, "reason": "missing_required_inputs"}
        return {
            "schema_version": STATE_SPACE_RESULT_SCHEMA_VERSION,
            "overall_status": "blocked_missing_inputs",
            "source_run_dir": str(Path(run_dir)),
            "input_summary": diagnostic,
            "longitudinal": longitudinal,
            "lateral_directional": lateral,
            "linear_stability_summary": build_linear_stability_summary(
                longitudinal=longitudinal,
                lateral_directional=lateral,
            ),
            "limitations": _limitations(),
        }
    longitudinal = _json_safe(compute_full_longitudinal(dd))
    lateral = _json_safe(compute_full_lateral(dd))
    return _json_safe({
        "schema_version": STATE_SPACE_RESULT_SCHEMA_VERSION,
        "overall_status": "completed" if longitudinal.get("valid") or lateral.get("valid") else "failed",
        "source_run_dir": str(Path(run_dir)),
        "input_summary": diagnostic,
        "longitudinal": longitudinal,
        "lateral_directional": lateral,
        "linear_stability_summary": build_linear_stability_summary(
            longitudinal=longitudinal,
            lateral_directional=lateral,
        ),
        "limitations": _limitations(),
    })


def write_state_space_result(result: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "state_space_result.json"
    path.write_text(json.dumps(_json_safe(result), indent=2), encoding="utf-8")
    return path


def read_state_space_result(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find_state_space_result(run_dir: str | Path) -> Path | None:
    run_dir = Path(run_dir)
    for candidate in (run_dir / "dynamics" / "state_space_result.json", run_dir / "state_space_result.json"):
        if candidate.exists():
            return candidate
    return None
