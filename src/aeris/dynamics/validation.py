"""Validation helpers for AERIS dynamics artifacts.

This module does not run AVL, does not solve trim, and does not recompute
state-space dynamics. It validates saved dynamics evidence so the CLI/GUI can
fail loudly when artifacts are missing, inconsistent, non-finite, or formula-
inconsistent.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "dynamics_validation_report_v0.1"


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _is_finite_number(value: Any) -> bool:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(x)


def _as_float(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _eigen_to_complex(item: Any) -> complex | None:
    if isinstance(item, dict):
        real = _as_float(item.get("real"))
        imag = _as_float(item.get("imag"))
        if real is None or imag is None:
            return None
        return complex(real, imag)
    if isinstance(item, (list, tuple)) and len(item) == 2:
        real = _as_float(item[0])
        imag = _as_float(item[1])
        if real is None or imag is None:
            return None
        return complex(real, imag)
    return None


def _check_matrix(matrix: Any, *, name: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if matrix is None:
        errors.append(f"{name}: missing a_matrix")
        return errors, warnings
    if not isinstance(matrix, list) or len(matrix) != 4:
        errors.append(f"{name}: a_matrix must be a 4x4 list")
        return errors, warnings
    for i, row in enumerate(matrix):
        if not isinstance(row, list) or len(row) != 4:
            errors.append(f"{name}: row {i} of a_matrix is not length 4")
            continue
        for j, value in enumerate(row):
            if not _is_finite_number(value):
                errors.append(f"{name}: a_matrix[{i}][{j}] is not finite")
    return errors, warnings


def _check_eigen_section(section: dict[str, Any], *, name: str) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    valid = section.get("valid") is True

    if not valid:
        reason = section.get("reason")
        warnings.append(f"{name}: section marked invalid: {reason or 'no reason'}")
        return {
            "valid": False,
            "eigenvalue_count": 0,
            "computed_unstable_eigenvalue_count": None,
            "computed_max_real_eigenvalue": None,
            "errors": errors,
            "warnings": warnings,
        }

    matrix_errors, matrix_warnings = _check_matrix(section.get("a_matrix"), name=name)
    errors.extend(matrix_errors)
    warnings.extend(matrix_warnings)

    raw_eigs = section.get("all_eigenvalues") or []
    if not isinstance(raw_eigs, list):
        errors.append(f"{name}: all_eigenvalues must be a list")
        raw_eigs = []

    eigs: list[complex] = []
    for idx, item in enumerate(raw_eigs):
        eig = _eigen_to_complex(item)
        if eig is None:
            errors.append(f"{name}: eigenvalue {idx} is not finite/complex-safe")
        else:
            eigs.append(eig)

    if len(eigs) != 4:
        errors.append(f"{name}: expected 4 eigenvalues, found {len(eigs)}")

    unstable = sum(1 for eig in eigs if eig.real > 0.0)
    max_real = max((eig.real for eig in eigs), default=None)

    return {
        "valid": len(errors) == 0,
        "eigenvalue_count": len(eigs),
        "computed_unstable_eigenvalue_count": unstable,
        "computed_max_real_eigenvalue": max_real,
        "errors": errors,
        "warnings": warnings,
    }


def _validate_state_space(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    status = data.get("overall_status")
    if status not in {"completed", "failed", "blocked_missing_inputs"}:
        errors.append(f"state_space: unexpected overall_status={status!r}")

    long_report = _check_eigen_section(data.get("longitudinal") or {}, name="longitudinal")
    lat_report = _check_eigen_section(data.get("lateral_directional") or {}, name="lateral_directional")
    errors.extend(f"state_space: {e}" for e in long_report["errors"])
    errors.extend(f"state_space: {e}" for e in lat_report["errors"])
    warnings.extend(f"state_space: {w}" for w in long_report["warnings"])
    warnings.extend(f"state_space: {w}" for w in lat_report["warnings"])

    summary = data.get("linear_stability_summary") or {}
    if not summary:
        errors.append("state_space: missing linear_stability_summary")
    elif summary.get("overall_known") is True:
        computed_total = None
        if (
            long_report.get("computed_unstable_eigenvalue_count") is not None
            and lat_report.get("computed_unstable_eigenvalue_count") is not None
        ):
            computed_total = int(long_report["computed_unstable_eigenvalue_count"]) + int(lat_report["computed_unstable_eigenvalue_count"])
        recorded_total = summary.get("total_unstable_eigenvalue_count")
        if computed_total is not None and recorded_total != computed_total:
            errors.append(
                "state_space: unstable eigenvalue count mismatch "
                f"recorded={recorded_total}, computed={computed_total}"
            )
        max_values = [
            v for v in (
                long_report.get("computed_max_real_eigenvalue"),
                lat_report.get("computed_max_real_eigenvalue"),
            )
            if v is not None
        ]
        if max_values:
            computed_max = max(max_values)
            recorded_max = _as_float(summary.get("max_real_eigenvalue"))
            if recorded_max is None or abs(recorded_max - computed_max) > 1e-9:
                errors.append(
                    "state_space: max_real_eigenvalue mismatch "
                    f"recorded={recorded_max}, computed={computed_max}"
                )

    limitations = data.get("limitations") or []
    if not limitations:
        warnings.append("state_space: missing limitations/disclaimer list")

    return {
        "artifact": "state_space_result.json",
        "present": True,
        "valid": len(errors) == 0,
        "status": status,
        "longitudinal": long_report,
        "lateral_directional": lat_report,
        "errors": errors,
        "warnings": warnings,
    }


def _validate_trim(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    longitudinal = data.get("longitudinal") or {}

    if longitudinal.get("valid") is not True:
        warnings.append(f"trim: longitudinal trim invalid: {longitudinal.get('reason')}")
        return {
            "artifact": "trim_result.json",
            "present": True,
            "valid": False,
            "errors": errors,
            "warnings": warnings,
        }

    cm = _as_float(longitudinal.get("cm_current"))
    cma = _as_float(longitudinal.get("cma_per_rad"))
    da_rad = _as_float(longitudinal.get("delta_alpha_rad"))
    da_deg = _as_float(longitudinal.get("delta_alpha_deg"))
    alpha0 = _as_float(longitudinal.get("alpha_current_deg"))
    alpha_trim = _as_float(longitudinal.get("alpha_trim_deg"))

    if cm is None or cma is None:
        errors.append("trim: missing cm_current or cma_per_rad")
    elif abs(cma) < 1e-12:
        errors.append("trim: cma_per_rad too close to zero")
    else:
        expected_da = -cm / cma
        if da_rad is None or abs(da_rad - expected_da) > 5e-6:
            errors.append(f"trim: delta_alpha_rad formula mismatch expected={expected_da}, got={da_rad}")
        expected_da_deg = math.degrees(expected_da)
        if da_deg is None or abs(da_deg - expected_da_deg) > 5e-3:
            errors.append(f"trim: delta_alpha_deg formula mismatch expected={expected_da_deg}, got={da_deg}")
        if alpha0 is not None and alpha_trim is not None:
            expected_alpha_trim = alpha0 + expected_da_deg
            if abs(alpha_trim - expected_alpha_trim) > 5e-3:
                errors.append(
                    "trim: alpha_trim_deg mismatch "
                    f"expected={expected_alpha_trim}, got={alpha_trim}"
                )

    cmde = _as_float(longitudinal.get("cmde_per_rad"))
    dde_rad = _as_float(longitudinal.get("delta_de_rad"))
    dde_deg = _as_float(longitudinal.get("delta_de_deg"))
    de0 = _as_float(longitudinal.get("control_input_deg"))
    de_trim = _as_float(longitudinal.get("de_trim_deg"))
    if cmde is not None:
        if abs(cmde) < 1e-12:
            warnings.append("trim: cmde_per_rad is too close to zero; elevon trim undefined")
        elif cm is not None:
            expected_dde = -cm / cmde
            if dde_rad is None or abs(dde_rad - expected_dde) > 5e-6:
                errors.append(f"trim: delta_de_rad formula mismatch expected={expected_dde}, got={dde_rad}")
            expected_dde_deg = math.degrees(expected_dde)
            if dde_deg is None or abs(dde_deg - expected_dde_deg) > 5e-3:
                errors.append(f"trim: delta_de_deg formula mismatch expected={expected_dde_deg}, got={dde_deg}")
            if de0 is not None and de_trim is not None and abs(de_trim - (de0 + expected_dde_deg)) > 5e-3:
                errors.append("trim: de_trim_deg does not equal control_input_deg + delta_de_deg")

    if longitudinal.get("alpha_trim_in_bounds") is False:
        warnings.append("trim: alpha trim is outside configured alpha bounds")
    if longitudinal.get("de_trim_in_bounds") is False:
        warnings.append("trim: elevon trim is outside configured control bounds")

    return {
        "artifact": "trim_result.json",
        "present": True,
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def _validate_foundation(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    sm = data.get("stability_metrics") or {}
    mp = data.get("mass_properties") or {}

    xnp = _as_float(sm.get("x_np_m"))
    xcg = _as_float(sm.get("x_cg_m") if sm.get("x_cg_m") is not None else mp.get("x_cg_m"))
    mac = _as_float(sm.get("mac_m"))
    recorded_sm = _as_float(sm.get("static_margin"))
    recorded_pct = _as_float(sm.get("static_margin_percent_mac"))
    cma = _as_float(sm.get("cma"))

    if xnp is None:
        errors.append("foundation: missing x_np_m")
    if xcg is None:
        errors.append("foundation: missing x_cg_m")
    if mac is None or mac <= 0:
        errors.append("foundation: missing or non-positive mac_m")

    if xnp is not None and xcg is not None and mac is not None and mac > 0:
        expected_sm = (xnp - xcg) / mac
        if recorded_sm is None or abs(recorded_sm - expected_sm) > 1e-9:
            errors.append(f"foundation: static_margin mismatch expected={expected_sm}, got={recorded_sm}")
        expected_pct = 100.0 * expected_sm
        if recorded_pct is None or abs(recorded_pct - expected_pct) > 1e-7:
            errors.append(f"foundation: static_margin_percent_mac mismatch expected={expected_pct}, got={recorded_pct}")
        if cma is not None:
            if expected_sm > 0 and cma >= 0:
                warnings.append("foundation: positive static margin but non-negative Cma")
            if expected_sm < 0 and cma <= 0:
                warnings.append("foundation: negative static margin but non-positive Cma")

    readiness = data.get("state_space_preparation") or {}
    if readiness.get("ready_for_eigenanalysis") is True:
        inertia = (mp.get("inertia") or {}) if isinstance(mp, dict) else {}
        for field in ("ixx_kg_m2", "iyy_kg_m2", "izz_kg_m2"):
            if not _is_finite_number(inertia.get(field)):
                errors.append(f"foundation: ready_for_eigenanalysis=True but missing {field}")

    return {
        "artifact": "dynamics_foundation.json",
        "present": True,
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def validate_dynamics_run(run_dir: str | Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    dyn_dir = run_dir / "dynamics"
    artifacts = {
        "foundation": dyn_dir / "dynamics_foundation.json",
        "cg_sweep": dyn_dir / "cg_sweep.json",
        "trim": dyn_dir / "trim_result.json",
        "state_space": dyn_dir / "state_space_result.json",
        "state_space_plots": dyn_dir / "plots" / "state_space_plot_manifest.json",
    }

    artifact_reports: dict[str, Any] = {}
    errors: list[str] = []
    warnings: list[str] = []

    foundation = _load_json(artifacts["foundation"])
    if foundation is None:
        warnings.append("foundation: dynamics_foundation.json not found; run `aeris dynamics build` first")
        artifact_reports["foundation"] = {"artifact": "dynamics_foundation.json", "present": False, "valid": None}
    else:
        report = _validate_foundation(foundation)
        artifact_reports["foundation"] = report
        errors.extend(report["errors"])
        warnings.extend(report["warnings"])

    trim = _load_json(artifacts["trim"])
    if trim is None:
        artifact_reports["trim"] = {"artifact": "trim_result.json", "present": False, "valid": None}
    else:
        report = _validate_trim(trim)
        artifact_reports["trim"] = report
        errors.extend(report["errors"])
        warnings.extend(report["warnings"])

    state_space = _load_json(artifacts["state_space"])
    if state_space is None:
        artifact_reports["state_space"] = {"artifact": "state_space_result.json", "present": False, "valid": None}
    else:
        report = _validate_state_space(state_space)
        artifact_reports["state_space"] = report
        errors.extend(report["errors"])
        warnings.extend(report["warnings"])

    for key in ("cg_sweep", "state_space_plots"):
        artifact_reports[key] = {
            "artifact": artifacts[key].name,
            "present": artifacts[key].exists(),
            "valid": None,
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "run_dir": str(run_dir),
        "passed": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "artifacts": artifact_reports,
        "notes": [
            "This validates saved dynamics artifacts only; it does not certify the aircraft.",
            "State-space eigenvalues are local linear diagnostics around one operating point.",
            "Trim checks validate first-order formulas, not full nonlinear trim equilibrium.",
        ],
    }


def write_dynamics_validation_report(report: dict[str, Any], output_dir: str | Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "dynamics_validation_report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path
