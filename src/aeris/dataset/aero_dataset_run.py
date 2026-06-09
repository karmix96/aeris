"""
Unified aero-dataset generation pipeline for AERIS.

This pipeline does, in one command:
1. generate a geometry dataset from a geometry config
2. run an aero/control sweep for every generated geometry
3. collect all successful and failed aero cases into ML-ready CSV tables
4. write a compact dataset manifest

Design intent:
- one user command
- deterministic geometry sampling
- robust per-geometry / per-case failure isolation
- ML-ready tabular output
"""

from __future__ import annotations

import csv
import json
import platform
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aeris.aero.control_metadata import control_alias_row, default_control_metadata
from aeris.common.config import load_yaml_config
from aeris.dataset.dataset_run import run_dataset_generation
from aeris.pipeline.aero_workflows import execute_aero_sweep
from aeris.quality.pipeline_api import (
    run_aero_dataset_qc,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATASETS_DIR = PROJECT_ROOT / "data" / "datasets"


def _compute_reynolds_number(velocity_mps, altitude_m, chord_m):
    """Chord Reynolds number: Re = rho(h)*V*c/mu(h). ISA + Sutherland."""
    if velocity_mps is None or altitude_m is None or chord_m is None:
        return None
    try:
        V, h, c = float(velocity_mps), float(altitude_m), float(chord_m)
    except (TypeError, ValueError):
        return None
    if V <= 0.0 or c <= 0.0:
        return None
    T = max(288.15 - 0.0065 * h, 216.65)
    p = 101325.0 * (T / 288.15) ** 5.2561
    rho = p / (287.058 * T)
    mu = 1.716e-5 * (T / 288.15) ** 1.5 * (288.15 + 110.4) / (T + 110.4)
    return max(rho * V * c / mu, 1.0)

def _write_final_summary(
    *,
    final_root: Path,
    manifest: dict[str, Any],
    exit_code: int,
    qc_preset: str | None = None,
    geometry_qc_profile: str | None = None,
    aero_qc_profile: str | None = None,
    fail_on_geometry_qc_error: bool | None = None,
    fail_on_aero_qc_error: bool | None = None,
) -> None:
    summary = {
        "dataset_name": manifest.get("dataset_name"),
        "config_path": manifest.get("config_path"),
        "dataset_root": str(final_root.resolve()),
        "geometry_dataset_root": manifest.get("geometry_dataset_root"),
        "requested_geometry_n": manifest.get("requested_geometry_n"),
        "attempted_geometry_sweeps": manifest.get("attempted_geometry_sweeps"),
        "completed_geometry_sweeps": manifest.get("completed_geometry_sweeps"),
        "successful_aero_rows": manifest.get("successful_aero_rows"),
        "failed_aero_rows": manifest.get("failed_aero_rows"),
        "generator_id": manifest.get("generator_id"),
        "solver": manifest.get("solver"),
        "geometry_qc": manifest.get("geometry_qc"),
        "aero_qc": manifest.get("aero_qc"),
        "qc_preset": qc_preset,
        "geometry_qc_profile": geometry_qc_profile,
        "aero_qc_profile": aero_qc_profile,
        "fail_on_geometry_qc_error": fail_on_geometry_qc_error,
        "fail_on_aero_qc_error": fail_on_aero_qc_error,
        "final_status": manifest.get("status"),
        "exit_code": exit_code,
        "created_at_utc": _utc_now_iso(),
        "retention": manifest.get("retention"),
    }

    _write_json(final_root / "final_run_summary.json", summary)

def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))

def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write("")
        return

    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _add_control_alias_columns(row: dict[str, Any]) -> dict[str, Any]:
    """Attach explicit control aliases while preserving the legacy column.

    Passes both sym (control_input_deg) and diff (diff_input_deg) values
    so delta_a_diff_deg is correctly populated for differential sweep rows.
    """
    row.update(control_alias_row(
        row.get("control_input_deg"),
        diff_input_deg=row.get("diff_input_deg"),
    ))
    return row


def _unique_float_values(rows: list[dict[str, Any]], column: str) -> list[float]:
    values: set[float] = set()
    for row in rows:
        value = row.get(column)
        if value is None or value == "":
            continue
        try:
            values.add(float(value))
        except (TypeError, ValueError):
            continue
    return sorted(values)


def _validate_retain_aero_runs(retain_aero_runs: str) -> str:
    value = retain_aero_runs.strip().lower()
    valid = {"all", "failures_only", "none"}
    if value not in valid:
        raise ValueError(
            f"Invalid retain_aero_runs={retain_aero_runs!r}. "
            f"Valid values: {sorted(valid)}"
        )
    return value


def _prune_aero_run_artifacts(
    *,
    copied_sweep_roots_by_geometry: dict[str, Path],
    geometry_ids_with_failures: set[str],
    retain_aero_runs: str,
) -> dict[str, Any]:
    retain_mode = _validate_retain_aero_runs(retain_aero_runs)

    deleted_roots: list[str] = []
    kept_roots: list[str] = []

    for geometry_id, run_root in copied_sweep_roots_by_geometry.items():
        keep = False

        if retain_mode == "all":
            keep = True
        elif retain_mode == "failures_only":
            keep = geometry_id in geometry_ids_with_failures
        elif retain_mode == "none":
            keep = False

        if keep:
            kept_roots.append(str(run_root.resolve()))
            continue

        if run_root.exists():
            shutil.rmtree(run_root)
        deleted_roots.append(str(run_root.resolve()))

    return {
        "retain_aero_runs": retain_mode,
        "kept_run_count": len(kept_roots),
        "deleted_run_count": len(deleted_roots),
        "kept_run_roots": kept_roots,
        "deleted_run_roots": deleted_roots,
    }

def _infer_generator_id_from_config(raw_config: dict[str, Any]) -> str:
    """Infer the generator ID from a raw config dict.
 
    Handles both the preferred 'id:' schema and the legacy 'family + version'
    schema. Mirrors the logic in geometry/config_resolver.py so both paths
    resolve identically.
    """
    geometry = raw_config.get("geometry", {}) or {}
    generator = geometry.get("generator", {}) or {}
 
    # Preferred schema: geometry.generator.id (e.g. 'bwb_segmented_v1')
    explicit_id = str(generator.get("id", "")).strip()
    if explicit_id:
        return explicit_id
 
    # Legacy schema: geometry.generator.family + version
    family = str(generator.get("family", "")).strip()
    version = str(generator.get("version", "")).strip()
 
    if family == "bwb_segmented" and version == "v1":
        return "bwb_segmented_v1"
 
    if family and version:
        return f"{family}_{version}"
 
    raise ValueError(
        "Could not infer generator_id from config. "
        "Provide 'geometry.generator.id: bwb_segmented_v1' (preferred) "
        "or both 'family' and 'version'."
    )


def _find_aero_result_json(case_dir: Path) -> Path:
    candidates = [
        case_dir / "aero_result.json",
        case_dir / "aero" / "aero_result.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    recursive = list(case_dir.rglob("aero_result.json"))
    if recursive:
        return recursive[0]

    raise FileNotFoundError(f"No aero_result.json found under {case_dir}")


def _load_sweep_manifest(run_root: Path) -> dict[str, Any]:
    candidates = [
        run_root / "aero_sweep_manifest.json",
        run_root / "aero_sweep" / "aero_sweep_manifest.json",
    ]

    for path in candidates:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if "aero_sweep_result" in data:
                return data["aero_sweep_result"]
            return data

    raise FileNotFoundError(f"No aero sweep manifest found under {run_root}")


def _flatten_success_row(
    *,
    geometry_row: dict[str, str],
    sweep_case: dict[str, Any],
    aero_payload: dict[str, Any],
) -> dict[str, Any]:
    scalars = aero_payload.get("scalars", {}) or {}
    solver_metadata = aero_payload.get("solver_metadata", {}) or {}
    failure = aero_payload.get("failure", None)

    row: dict[str, Any] = {}

    # Geometry metadata first
    row.update(geometry_row)

    # Sweep/aero identifiers
    row["aero_case_label"] = sweep_case.get("case_label")
    row["aero_case_index"] = sweep_case.get("case_index")
    row["aero_status"] = aero_payload.get("status")
    row["aero_runtime_sec"] = aero_payload.get("runtime_sec")
    row["control_input_deg"] = sweep_case.get("control_input_deg")
    row["diff_input_deg"] = sweep_case.get("diff_input_deg")   # populated by sweep_run.py
    _add_control_alias_columns(row)

    # Flight condition
    fc = sweep_case.get("flight_condition", {}) or {}
    row["alpha_deg"] = fc.get("alpha_deg")
    row["beta_deg"] = fc.get("beta_deg")
    row["velocity_mps"] = fc.get("velocity_mps")
    row["altitude_m"] = fc.get("altitude_m")
    row["p_rad_s"] = fc.get("p_rad_s")
    row["q_rad_s"] = fc.get("q_rad_s")
    row["r_rad_s"] = fc.get("r_rad_s")

    # Scalars
    row["cl"] = scalars.get("cl")
    row["cd"] = scalars.get("cd")
    row["cm"] = scalars.get("cm")
    row["cy"] = scalars.get("cy")
    row["cl_roll"] = scalars.get("cl_roll")
    row["cn"] = scalars.get("cn")
    row["l_over_d"] = scalars.get("l_over_d")
    row["cd_ind"] = scalars.get("cd_ind")
    row["cd_ff"] = scalars.get("cd_ff")
    row["span_efficiency"] = scalars.get("span_efficiency")
    row["x_np"] = scalars.get("x_np")

    # Compact solver/control diagnostics
    row["geometry_declares_controls"] = solver_metadata.get("geometry_declares_controls")
    row["airplane_has_controls"] = solver_metadata.get("airplane_has_controls")
    row["geometry_control_surface_names"] = json.dumps(
        solver_metadata.get("geometry_control_surface_names", [])
    )

    diag = solver_metadata.get("control_diagnostics", {}) or {}
    row["diag_airplane_has_control_surfaces"] = diag.get("airplane_has_control_surfaces")
    row["diag_airplane_avl_has_control_blocks"] = diag.get("airplane_avl_has_control_blocks")
    row["diag_keystrokes_has_d1_command"] = diag.get("keystrokes_has_d1_command")
    row["diag_stdout_control_variables"] = diag.get("stdout_control_variables")

    # Failure columns kept for schema stability
    row["failure_reason"] = None if failure is None else failure.get("reason")
    row["failure_message"] = None if failure is None else failure.get("message")

    # SCI.5 — Computed: chord Reynolds number (ISA atmosphere, chord=c1_m)
    row["re_number"] = _compute_reynolds_number(
        velocity_mps=row.get("velocity_mps"),
        altitude_m=row.get("altitude_m"),
        chord_m=row.get("c1_m"),
    )

    return row


def _flatten_failure_row(
    *,
    geometry_row: dict[str, str],
    geometry_id: str,
    sweep_case: dict[str, Any] | None,
    error_type: str,
    error_message: str,
) -> dict[str, Any]:
    row: dict[str, Any] = {}
    row.update(geometry_row)

    row["geometry_id"] = geometry_id
    row["aero_case_label"] = None if sweep_case is None else sweep_case.get("case_label")
    row["aero_case_index"] = None if sweep_case is None else sweep_case.get("case_index")
    row["control_input_deg"] = None if sweep_case is None else sweep_case.get("control_input_deg")
    _add_control_alias_columns(row)

    fc = {} if sweep_case is None else (sweep_case.get("flight_condition", {}) or {})
    row["alpha_deg"] = fc.get("alpha_deg")
    row["beta_deg"] = fc.get("beta_deg")
    row["velocity_mps"] = fc.get("velocity_mps")
    row["altitude_m"] = fc.get("altitude_m")
    row["p_rad_s"] = fc.get("p_rad_s")
    row["q_rad_s"] = fc.get("q_rad_s")
    row["r_rad_s"] = fc.get("r_rad_s")

    row["error_type"] = error_type
    row["error_message"] = error_message
    row["re_number"] = None  # schema stability
    return row


def run_aero_dataset_generation(
    *,
    config_path: Path,
    n_samples: int,
    sampler: str | None,
    sampler_seed: int | None,
    dataset_name: str,
    save_plot: bool | None,
    build_aerosandbox: bool | None,
    alpha_values: list[float],
    beta_values: list[float],
    velocity_values: list[float],
    altitude_values: list[float],
    p_values: list[float],
    q_values: list[float],
    r_values: list[float],
    control_input_values: list[float],
    diff_input_values: list[float] | None = None,
    solver: str,
    avl_command: str,
    timeout_sec: int,
    spanwise_resolution: int,
    chordwise_resolution: int,
    spanwise_spacing: str,
    chordwise_spacing: str,
    save_surface_forces: bool,
    save_element_forces: bool,
    max_cases: int | None,
    keep_geometry_dataset: bool,
    retain_aero_runs: str = "all",
    qc_preset: str | None = None,
    run_geometry_qc: bool = False,
    geometry_qc_profile: str = "basic",
    fail_on_geometry_qc_error: bool = False,
    run_aero_qc: bool = False,
    aero_qc_profile: str = "basic",
    fail_on_aero_qc_error: bool = False,
) -> int:
    raw_config = load_yaml_config(config_path)
    retain_aero_runs = _validate_retain_aero_runs(retain_aero_runs)
    generator_id = _infer_generator_id_from_config(raw_config)

    final_root = DATASETS_DIR / dataset_name
    geometry_dataset_name = f"{dataset_name}__geometry"
    geometry_dataset_root = DATASETS_DIR / geometry_dataset_name
    sweep_runs_root = final_root / "aero_runs"

    if final_root.exists():
        shutil.rmtree(final_root)
    _ensure_dir(final_root)
    _ensure_dir(sweep_runs_root)

    # 1) Generate geometry dataset first, internally
    rc = run_dataset_generation(
    config_path=config_path,
    n_samples=n_samples,
    sampler=sampler,
    sampler_seed=sampler_seed,
    dataset_name=geometry_dataset_name,
    save_plot=save_plot,
    build_aerosandbox=build_aerosandbox,
    run_qc=run_geometry_qc,
    qc_profile=geometry_qc_profile,
    fail_on_qc_error=fail_on_geometry_qc_error,
)

    # 🔴 NEW: Always load geometry QC summary if exists
    geometry_manifest = _read_json_if_exists(geometry_dataset_root / "dataset_manifest.json")
    geometry_qc_summary = None
    if geometry_manifest is not None:
        geometry_qc_summary = geometry_manifest.get("qc")

    # 🔴 CASE 1: geometry generation failed
    if rc != 0:
        manifest = {
            "status": "failed",
            "config_path": str(config_path.resolve()),
            "dataset_name": dataset_name,
            "geometry_dataset_name": geometry_dataset_name,
            "geometry_dataset_root": str(geometry_dataset_root.resolve()),
            "requested_geometry_n": n_samples,
            "attempted_geometry_sweeps": 0,
            "completed_geometry_sweeps": 0,
            "successful_aero_rows": 0,
            "failed_aero_rows": 0,
            "generator_id": generator_id,
            "solver": solver,
            "geometry_qc": geometry_qc_summary,
            "aero_qc": None,
            "retention": {},
        }

        _write_final_summary(
            final_root=final_root,
            manifest=manifest,
            exit_code=1,
            qc_preset=qc_preset,
            geometry_qc_profile=geometry_qc_profile,
            aero_qc_profile=aero_qc_profile,
            fail_on_geometry_qc_error=fail_on_geometry_qc_error,
            fail_on_aero_qc_error=fail_on_aero_qc_error,
        )

        return 1

    # 🔴 CASE 2: geometry QC failed (STRICT STOP)
    if (
        run_geometry_qc
        and fail_on_geometry_qc_error
        and geometry_qc_summary is not None
        and not geometry_qc_summary.get("passed", True)
    ):
        manifest = {
            "status": "failed",
            "config_path": str(config_path.resolve()),
            "dataset_name": dataset_name,
            "geometry_dataset_name": geometry_dataset_name,
            "geometry_dataset_root": str(geometry_dataset_root.resolve()),
            "requested_geometry_n": n_samples,
            "attempted_geometry_sweeps": n_samples,
            "completed_geometry_sweeps": n_samples,
            "successful_aero_rows": 0,
            "failed_aero_rows": 0,
            "generator_id": generator_id,
            "solver": solver,
            "geometry_qc": geometry_qc_summary,
            "aero_qc": None,
            "retention": {},
        }

        _write_final_summary(
            final_root=final_root,
            manifest=manifest,
            exit_code=1,
            qc_preset=qc_preset,
            geometry_qc_profile=geometry_qc_profile,
            aero_qc_profile=aero_qc_profile,
            fail_on_geometry_qc_error=fail_on_geometry_qc_error,
            fail_on_aero_qc_error=fail_on_aero_qc_error,
        )

        return 1

    geometry_manifest = _read_json_if_exists(geometry_dataset_root / "dataset_manifest.json")
    geometry_qc_summary = None
    if geometry_manifest is not None:
        geometry_qc_summary = geometry_manifest.get("qc")


    geometry_metadata_rows = _read_csv_rows(geometry_dataset_root / "metadata.csv")
    geometry_by_id = {
        str(row["geometry_id"]): row
        for row in geometry_metadata_rows
        if row.get("geometry_id")
    }

    success_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    copied_sweep_roots_by_geometry: dict[str, Path] = {}
    geometry_ids_with_failures: set[str] = set()

    requested_geometry_n = len(geometry_by_id)
    attempted_sweeps = 0
    completed_sweeps = 0

    for geometry_id, geometry_row in geometry_by_id.items():
        attempted_sweeps += 1

        try:
            sweep_run_root, sweep_result = execute_aero_sweep(
                config=None,
                run_dir=None,
                dataset=geometry_dataset_root,
                geometry_id=geometry_id,
                geometry_source="reconstruct",
                generator_id=generator_id,
                control_input_deg=None,
                control_input_values=control_input_values,
                diff_input_values=diff_input_values,
                alpha=alpha_values[0] if alpha_values else 0.0,
                velocity=velocity_values[0] if velocity_values else 28.0,
                altitude=altitude_values[0] if altitude_values else 0.0,
                beta=beta_values[0] if beta_values else 0.0,
                mach=None,
                p=p_values[0] if p_values else 0.0,
                q=q_values[0] if q_values else 0.0,
                r=r_values[0] if r_values else 0.0,
                alpha_values=alpha_values,
                beta_values=beta_values,
                velocity_values=velocity_values,
                altitude_values=altitude_values,
                p_values=p_values,
                q_values=q_values,
                r_values=r_values,
                solver=solver,
                avl_command=avl_command,
                timeout_sec=timeout_sec,
                spanwise_resolution=spanwise_resolution,
                chordwise_resolution=chordwise_resolution,
                spanwise_spacing=spanwise_spacing,
                chordwise_spacing=chordwise_spacing,
                save_surface_forces=save_surface_forces,
                save_element_forces=save_element_forces,
                seed=0,
                output_name=f"{geometry_id}_aero",
                max_cases=max_cases,
            )

            # Copy / preserve sweep run under final dataset root for traceability
            copied_sweep_root = sweep_runs_root / sweep_run_root.name
            if copied_sweep_root.exists():
                shutil.rmtree(copied_sweep_root)
            shutil.copytree(sweep_run_root, copied_sweep_root)
            copied_sweep_roots_by_geometry[geometry_id] = copied_sweep_root

            manifest = _load_sweep_manifest(copied_sweep_root)
            cases = manifest.get("cases", []) or []

            for case in cases:
                case_dir = Path(case["case_dir"])
                try:
                    aero_json = _find_aero_result_json(case_dir)
                    aero_payload = json.loads(aero_json.read_text(encoding="utf-8"))
                except Exception as exc:
                    geometry_ids_with_failures.add(geometry_id)
                    failure_rows.append(
                        _flatten_failure_row(
                            geometry_row=geometry_row,
                            geometry_id=geometry_id,
                            sweep_case=case,
                            error_type=type(exc).__name__,
                            error_message=str(exc),
                        )
                    )
                    continue

                if str(aero_payload.get("status")) == "success":
                    success_rows.append(
                        _flatten_success_row(
                            geometry_row=geometry_row,
                            sweep_case=case,
                            aero_payload=aero_payload,
                        )
                    )
                else:
                    failure = aero_payload.get("failure", {}) or {}
                    geometry_ids_with_failures.add(geometry_id)
                    failure_rows.append(
                        _flatten_failure_row(
                            geometry_row=geometry_row,
                            geometry_id=geometry_id,
                            sweep_case=case,
                            error_type=str(failure.get("reason", "aero_case_failed")),
                            error_message=str(failure.get("message", "unknown aero failure")),
                        )
                    )

            completed_sweeps += 1

        except Exception as exc:
            geometry_ids_with_failures.add(geometry_id)
            failure_rows.append(
                _flatten_failure_row(
                    geometry_row=geometry_row,
                    geometry_id=geometry_id,
                    sweep_case=None,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )

    # Write ML-ready outputs
    _write_csv(final_root / "aero_dataset.csv", success_rows)
    _write_csv(final_root / "aero_failures.csv", failure_rows)
    aero_run_retention = _prune_aero_run_artifacts(
    copied_sweep_roots_by_geometry=copied_sweep_roots_by_geometry,
    geometry_ids_with_failures=geometry_ids_with_failures,
    retain_aero_runs=retain_aero_runs,
    )

    manifest = {
        "status": (
            "success"
            if not failure_rows
            else ("partial_success" if success_rows else "failed")
        ),
        "created_at_utc": _utc_now_iso(),
        "platform": {
            "python": sys.version,
            "platform": platform.platform(),
        },
        "config_path": str(config_path.resolve()),
        "dataset_name": dataset_name,
        "geometry_dataset_name": geometry_dataset_name,
        "geometry_dataset_root": str(geometry_dataset_root.resolve()),
        "requested_geometry_n": requested_geometry_n,
        "attempted_geometry_sweeps": attempted_sweeps,
        "completed_geometry_sweeps": completed_sweeps,
        "successful_aero_rows": len(success_rows),
        "failed_aero_rows": len(failure_rows),
        "generator_id": generator_id,
        "solver": solver,
        "control_input_values": control_input_values,
        "control_metadata": default_control_metadata(),
        "control_alias_columns": [
            "control_input_deg",
            "delta_e_sym_deg",
            "delta_a_diff_deg",
        ],
        "delta_e_sym_values": _unique_float_values(success_rows, "delta_e_sym_deg"),
        "delta_a_diff_values": _unique_float_values(success_rows, "delta_a_diff_deg"),
        "alpha_values": alpha_values,
        "beta_values": beta_values,
        "velocity_values": velocity_values,
        "altitude_values": altitude_values,
        "p_values": p_values,
        "q_values": q_values,
        "r_values": r_values,
        "geometry_qc": geometry_qc_summary,
        "artifacts": {
            "aero_dataset_csv": str((final_root / "aero_dataset.csv").resolve()),
            "aero_failures_csv": str((final_root / "aero_failures.csv").resolve()),
            "aero_runs_root": str(sweep_runs_root.resolve()),
        },
        "retention": {
        "keep_geometry_dataset": keep_geometry_dataset,
        "retain_aero_runs": aero_run_retention["retain_aero_runs"],
        "kept_aero_run_count": aero_run_retention["kept_run_count"],
        "deleted_aero_run_count": aero_run_retention["deleted_run_count"],
    },
    }

    if not keep_geometry_dataset:
        manifest["geometry_dataset_deleted_after_run"] = True
        if geometry_dataset_root.exists():
            shutil.rmtree(geometry_dataset_root)
    else:
        manifest["geometry_dataset_deleted_after_run"] = False

    manifest_path = final_root / "aero_dataset_manifest.json"

    # Write base manifest first so integrated aero QC can validate against it.
    _write_json(manifest_path, manifest)

    aero_qc_report = None
    if run_aero_qc:
        aero_qc_report = run_aero_dataset_qc(
            dataset_root=final_root,
            profile=aero_qc_profile,
        )

        qc_dir = final_root / "qc"
        qc_dir.mkdir(parents=True, exist_ok=True)
        aero_qc_report_path = qc_dir / "aero_qc_report.json"
        _write_json(aero_qc_report_path, aero_qc_report)

        manifest["aero_qc"] = {
            "run_qc": True,
            "profile": aero_qc_profile,
            "passed": aero_qc_report["passed"],
            "error_count": len(aero_qc_report["errors"]),
            "warning_count": len(aero_qc_report["warnings"]),
            "report_path": str(aero_qc_report_path),
        }
    else:
        manifest["aero_qc"] = {
            "run_qc": False,
            "report_path": None,
        }

    # Rewrite manifest with aero_qc summary included.
    _write_json(manifest_path, manifest)

    exit_code = 0 if success_rows else 1

    if (
        aero_qc_report is not None
        and not aero_qc_report["passed"]
        and fail_on_aero_qc_error
    ):
        exit_code = 1

    _write_final_summary(
        final_root=final_root,
        manifest=manifest,
        exit_code=exit_code,
        qc_preset=qc_preset,
        geometry_qc_profile=geometry_qc_profile,
        aero_qc_profile=aero_qc_profile,
        fail_on_geometry_qc_error=fail_on_geometry_qc_error,
        fail_on_aero_qc_error=fail_on_aero_qc_error,
    )

    return exit_code