"""
Pipeline/orchestration helpers for aerodynamic runs and sweeps.

This module keeps workflow orchestration out of the CLI layer:
- geometry source preparation
- run folder creation
- manifest assembly
- delegation to aero solver / sweep execution
"""

from __future__ import annotations

import json
import shutil

import numpy as np
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from aeris.aero import AeroInput, AeroSolverSettings, FlightCondition, create_solver
from aeris.aero.models import FlightConditionSweep
from aeris.aero.sweep_run import run_aero_sweep
from aeris.aero.views import (
    geometry_view_from_case,
    geometry_view_from_dataset_case,
    geometry_view_from_run_dir,
)
from aeris.common.config import file_sha256, load_yaml_config
from aeris.common.logging_utils import setup_logger
from aeris.common.paths import create_run_folder, write_run_manifest
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator
from aeris.aero.io import _write_aero_result_json


def create_aero_run_root(output_name: str, label: str, prefix: str) -> tuple[Any, Path, Path]:
    suffix = output_name.strip() or label.strip()
    run_paths = create_run_folder(prefix=f"{prefix}_{suffix}")
    run_root = run_paths.root
    geometry_dir = run_root / "geometry"
    aero_dir = run_root / "aero"
    geometry_dir.mkdir(parents=True, exist_ok=True)
    aero_dir.mkdir(parents=True, exist_ok=True)
    return run_paths, geometry_dir, aero_dir


def _copy_standard_input_config(config: Path | None, run_root: Path) -> Path | None:
    """Copy the input config to the standard run-root input_config.yaml path."""
    if config is None:
        return None

    resolved = Path(config).expanduser().resolve()
    if not resolved.exists():
        return None

    copied = run_root / "input_config.yaml"
    shutil.copy2(resolved, copied)
    return copied


def _config_manifest_fields(config: Path | None, copied_config_path: Path | None) -> dict[str, Any]:
    """Return generic manifest fields for the source config, if available."""
    fields: dict[str, Any] = {}

    if config is not None:
        resolved = Path(config).expanduser().resolve()
        fields["config_path"] = str(resolved)
        if resolved.exists():
            fields["config_sha256"] = file_sha256(resolved)

    if copied_config_path is not None:
        fields["copied_config_path"] = str(copied_config_path)

    return fields


def sample_one(generator_id: str, typed_config: Any, seed: int) -> Any:
    generator = get_geometry_generator(generator_id)
    return generator.sample_one(typed_config, seed=seed)


def run_full_case(
    generator_id: str,
    sample: Any,
    typed_config: Any,
    output_dir: Path,
    save_plot: bool,
    build_aerosandbox: bool,
) -> Any:
    generator = get_geometry_generator(generator_id)
    return generator.run_full_case(
        sample=sample,
        config=typed_config,
        output_dir=output_dir,
        save_plot=save_plot,
        build_aerosandbox=build_aerosandbox,
    )


def summarize_case(generator_id: str, case: Any) -> Any:
    generator = get_geometry_generator(generator_id)
    return generator.summarize_case(case)


def prepare_geometry_for_aero(
    *,
    config: Path | None,
    run_dir: Path | None,
    dataset: Path | None,
    geometry_id: str,
    source_policy: str,
    seed: int,
    geometry_dir: Path,
    generator_id: str | None = None,
    copy_config_to: Path | None = None,
) -> tuple[Any, str, Any]:
    """
    Prepare an AeroGeometryView from one of the supported source modes.

    Returns:
        geometry_view, resolved_generator_id, summary
    """
    summary: Any = {}
    geometry_view = None

    if config is not None:
        raw_config = load_yaml_config(config)
        resolved_generator_id, typed_config = resolve_generator_and_config(raw_config)

        sample = sample_one(
            generator_id=resolved_generator_id,
            typed_config=typed_config,
            seed=seed,
        )
        case = run_full_case(
            generator_id=resolved_generator_id,
            sample=sample,
            typed_config=typed_config,
            output_dir=geometry_dir,
            save_plot=False,
            build_aerosandbox=True,
        )
        summary = summarize_case(generator_id=resolved_generator_id, case=case)

        geometry_view = geometry_view_from_case(
            case=case,
            generator_id=resolved_generator_id,
            case_dir=geometry_dir,
            source_policy=source_policy,
        )

        if copy_config_to is not None and config.exists():
            shutil.copy2(config, copy_config_to / config.name)

        return geometry_view, resolved_generator_id, summary

    # Default to bwb_segmented_v1 when not provided — mirrors the default in
    # geometry_view_from_run_dir and geometry_view_from_dataset_case so that
    # `aeris aero sweep --dataset ...` works without --generator-id.
    _resolved_gen_id = (generator_id or "").strip() or "bwb_segmented_v1"
    if not (generator_id or "").strip():
        import logging as _logging
        _logging.getLogger("aeris").warning(
            "prepare_geometry_for_aero: --generator-id not supplied; "
            "defaulting to bwb_segmented_v1. Pass --generator-id explicitly "
            "when using a non-default generator family."
        )

    if run_dir is not None:
        geometry_view = geometry_view_from_run_dir(
            run_dir=run_dir,
            generator_id=_resolved_gen_id,
        )
        summary = {
            "source_mode": "run_dir",
            "run_dir": str(run_dir.resolve()),
        }
        return geometry_view, _resolved_gen_id, summary

    geometry_view = geometry_view_from_dataset_case(
        dataset_root=dataset,
        geometry_id=geometry_id,
        generator_id=_resolved_gen_id,
    )
    summary = {
        "source_mode": "dataset",
        "dataset_root": str(dataset.resolve()),
        "geometry_id": geometry_id,
    }
    return geometry_view, _resolved_gen_id, summary


def dataclass_or_value(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return value


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, np.generic):
        return value.item()
    return str(value)

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

def execute_aero_run(
    *,
    config: Path | None,
    run_dir: Path | None,
    dataset: Path | None,
    geometry_id: str,
    geometry_source: str,
    generator_id: str | None,
    control_input_deg: float | None,
    diff_input_deg: float | None = None,
    alpha: float = 0.0,
    velocity: float = 28.0,
    altitude: float = 0.0,
    beta: float = 0.0,
    mach: float = 0.0,
    p: float = 0.0,
    q: float = 0.0,
    r: float = 0.0,
    solver: str = "aerosandbox_avl",
    avl_command: str = "",
    timeout_sec: int = 180,
    spanwise_resolution: int = 4,
    chordwise_resolution: int = 8,
    spanwise_spacing: str = "equal",
    chordwise_spacing: str = "cosine",
    save_surface_forces: bool = False,
    save_element_forces: bool = False,
    seed: int = 0,
    output_name: str = "",
    viscous_polar_source: str = "none",
    viscous_polar_re_grid: list[float] | None = None,
) -> tuple[Path, Any]:
    label = (
        config.stem if config is not None
        else run_dir.name if run_dir is not None
        else geometry_id
    )

    run_paths, geometry_dir, aero_dir = create_aero_run_root(
        output_name=output_name,
        label=label,
        prefix="aero",
    )
    run_root = run_paths.root
    logger = setup_logger(run_paths.logs / "app.log")
    logger.info("Starting aero run")
    logger.info("Run root: %s", run_root)
    copied_config_path = _copy_standard_input_config(config, run_root)

    geometry_view, resolved_generator_id, summary = prepare_geometry_for_aero(
        config=config,
        run_dir=run_dir,
        dataset=dataset,
        geometry_id=geometry_id,
        source_policy=geometry_source,
        seed=seed,
        geometry_dir=geometry_dir,
        generator_id=generator_id,
        copy_config_to=None,  # standard copy is input_config.yaml via _copy_standard_input_config()
    )

    # Polar bridge wiring for single-run mode (mirrors execute_aero_sweep).
    _bridge_section_map = None
    _bridge_polar_store = None
    _bridge_status: dict[str, Any] = {
        "requested_source": viscous_polar_source,
        "active": False,
        "backend": None,
        "reason": "not_requested",
    }
    _source_key = str(viscous_polar_source or "none").strip().lower()
    if _source_key in {"neuralfoil", "neural-foil"}:
        try:
            from aeris.airfoil.neuralfoil_polar_source import (
                build_neuralfoil_polar_store_for_segments,
            )
            _segment_coords, _semispan_m = _extract_neuralfoil_segment_coords_from_airplane(
                geometry_view.airplane
            )
            _bridge_mach = 0.0 if mach is None else float(mach)
            _bridge_section_map, _bridge_polar_store = build_neuralfoil_polar_store_for_segments(
                _segment_coords,
                semispan_m=float(_semispan_m),
                model_size="large",
                re_grid=viscous_polar_re_grid,
                mach=_bridge_mach,
            )
            _bridge_status.update({
                "active": True,
                "backend": "neuralfoil",
                "reason": "ok",
                "segment_count": len(_segment_coords),
                "semispan_m": float(_semispan_m),
            })
        except Exception as _bridge_exc:
            import logging as _logging
            _logging.getLogger("aeris").warning(
                "NeuralFoil polar bridge setup failed in aero_run (%s); "
                "continuing with inviscid AVL.", _bridge_exc,
            )
            _bridge_section_map = None
            _bridge_polar_store = None
            _bridge_status.update({"active": False, "backend": "neuralfoil",
                                   "reason": "setup_failed: " + str(_bridge_exc)})
    elif _source_key in {"none", "off", "inviscid"}:
        _bridge_status["reason"] = "disabled_by_user"
    else:
        _bridge_status["reason"] = "not_configured"

    aero_input = AeroInput(
        geometry=geometry_view,
        flight_condition=FlightCondition(
            alpha_deg=alpha,
            beta_deg=beta,
            mach=mach,
            velocity_mps=velocity,
            altitude_m=altitude,
            p_rad_s=p,
            q_rad_s=q,
            r_rad_s=r,
        ),
        settings=AeroSolverSettings(
            avl_command=avl_command or None,
            timeout_sec=timeout_sec,
            verbose=False,
            solver_options={
                "paneling": {
                    "spanwise_resolution": spanwise_resolution,
                    "chordwise_resolution": chordwise_resolution,
                    "spanwise_spacing": spanwise_spacing,
                    "chordwise_spacing": chordwise_spacing,
                },
                "save_surface_forces": save_surface_forces,
                "save_element_forces": save_element_forces,
                "control_input_deg": control_input_deg,
                "diff_input_deg": diff_input_deg,
                "section_map": _bridge_section_map,
                "polar_store": _bridge_polar_store,
            },
        ),
        provenance={
            "solver": solver,
            "seed": seed,
            "geometry_source": geometry_source,
            "source_label": label,
            "resolved_generator_id": resolved_generator_id,
            "polar_bridge": to_jsonable(_bridge_status),
        },
    )

    solver_instance = create_solver(solver)

    initial_paneling = {
        "spanwise_resolution": spanwise_resolution,
        "chordwise_resolution": chordwise_resolution,
        "spanwise_spacing": spanwise_spacing,
        "chordwise_spacing": chordwise_spacing,
    }

    result = solver_instance.run_case(
        aero_input=aero_input,
        output_dir=aero_dir,
    )

    should_retry, retry_reason = _should_retry_with_finer_paneling(result)

    if should_retry:
        retry_input = AeroInput(
            geometry=aero_input.geometry,
            flight_condition=aero_input.flight_condition,
            settings=AeroSolverSettings(
                avl_command=avl_command or None,
                timeout_sec=timeout_sec,
                verbose=False,
                solver_options={
                    "paneling": {
                        "spanwise_resolution": 8,
                        "chordwise_resolution": 12,
                        "spanwise_spacing": spanwise_spacing,
                        "chordwise_spacing": chordwise_spacing,
                    },
                    "save_surface_forces": save_surface_forces,
                    "save_element_forces": save_element_forces,
                    "control_input_deg": control_input_deg,
                    "diff_input_deg": diff_input_deg,
                    "section_map": _bridge_section_map,
                    "polar_store": _bridge_polar_store,
                },
            ),
            provenance=dict(aero_input.provenance),
        )

        retry_result = solver_instance.run_case(
            aero_input=retry_input,
            output_dir=aero_dir,
        )

        retry_ok, _ = _should_retry_with_finer_paneling(retry_result)

        if not retry_ok:
            _inject_retry_metadata(
                retry_result,
                used=True,
                reason=retry_reason,
                initial_paneling=initial_paneling,
                fallback_paneling=retry_input.settings.solver_options["paneling"],
                initial_result=result,
            )
            result = retry_result
        else:
            # Retry also produced a bad result — keep original, mark retry as not useful.
            _inject_retry_metadata(
                result,
                used=False,
                reason=f"retry_also_failed:{retry_reason}",
                initial_paneling=initial_paneling,
                fallback_paneling=retry_input.settings.solver_options["paneling"],
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

    # Persist the final post-processed result chosen by the pipeline.
    # The solver writes aero_result.json during each run_case() call, but the
    # pipeline may later inject fallback metadata and/or replace the initial
    # result with a successful retry result. Rewrite the final chosen result so
    # aero_result.json matches what the pipeline is actually returning.
    result.artifact_paths["aero_result_json"] = str(aero_dir / "aero_result.json")
    _write_aero_result_json(result, aero_dir)
    
    manifest = {
        "run_name": run_root.name,
        "solver": solver,
        "geometry_source": geometry_source,
        "resolved_generator_id": resolved_generator_id,
        "control_input_deg": control_input_deg,
        "diff_input_deg": diff_input_deg,
        "flight_condition": to_jsonable(asdict(aero_input.flight_condition)),
        "geometry_summary": to_jsonable(dataclass_or_value(summary)),
        "aero_result": to_jsonable(dataclass_or_value(result)),
    }
    aero_manifest_path = run_root / "aero_manifest.json"
    aero_manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    generic_manifest_extra: dict[str, Any] = {
        "phase": "aero_run",
        "status": getattr(result.status, "value", str(result.status)),
        "domain_manifest": str(aero_manifest_path),
        "aero_result_json": str(aero_dir / "aero_result.json"),
        "solver": solver,
        "geometry_source": geometry_source,
        "resolved_generator_id": resolved_generator_id,
        "control_input_deg": control_input_deg,
        "run_artifacts": {
            "geometry_dir": str(geometry_dir),
            "aero_dir": str(aero_dir),
        },
    }
    generic_manifest_extra.update(_config_manifest_fields(config, copied_config_path))
    write_run_manifest(run_paths, extra=generic_manifest_extra)
    logger.info("Aero run completed with status=%s", generic_manifest_extra["status"])

    return run_root, result



def _extract_neuralfoil_segment_coords_from_airplane(airplane) -> tuple[list[tuple[Any, float]], float]:
    """Build NeuralFoil segment coordinates from the current AeroSandbox airplane.

    Conservative first implementation:
    - uses the first wing;
    - reads each positive-half wing section airfoil coordinates;
    - creates spanwise segment end fractions from section midpoints;
    - returns [(coords, y_frac_end), ...], semispan_m.

    This is enough to replace all-zero CDCL placeholders with real NeuralFoil
    polar fits for the current generated BWB geometry.
    """
    wing = airplane.wings[0]
    xsecs = list(getattr(wing, "xsecs", []) or [])
    if len(xsecs) < 2:
        raise ValueError("Need at least two wing sections for NeuralFoil bridge.")

    raw: list[tuple[float, Any]] = []
    for xsec in xsecs:
        y = abs(float(xsec.xyz_le[1]))
        airfoil = getattr(xsec, "airfoil", None)
        coords = getattr(airfoil, "coordinates", None)
        if coords is None:
            continue
        raw.append((y, coords))

    if len(raw) < 2:
        raise ValueError("No usable AeroSandbox airfoil coordinates found on wing sections.")

    raw = sorted(raw, key=lambda item: item[0])
    semispan_m = max(y for y, _ in raw)
    if semispan_m <= 0.0:
        raise ValueError("Could not resolve positive semispan for NeuralFoil bridge.")

    # Keep one section per unique y station.
    unique: list[tuple[float, Any]] = []
    for y, coords in raw:
        if not unique or abs(y - unique[-1][0]) > 1e-9:
            unique.append((y, coords))

    ys = [y for y, _ in unique]
    segment_coords: list[tuple[Any, float]] = []

    for i, (y, coords) in enumerate(unique):
        if i == 0:
            # Root section covers root -> midpoint to next station.
            if len(unique) == 1:
                y_end = semispan_m
            else:
                y_end = 0.5 * (ys[0] + ys[1])
        elif i == len(unique) - 1:
            y_end = semispan_m
        else:
            y_end = 0.5 * (ys[i] + ys[i + 1])

        y_frac_end = min(1.0, max(1e-9, float(y_end) / semispan_m))
        segment_coords.append((coords, y_frac_end))

    # Ensure the last segment exactly reaches the tip.
    last_coords, _ = segment_coords[-1]
    segment_coords[-1] = (last_coords, 1.0)

    return segment_coords, float(semispan_m)


def execute_aero_sweep(
    *,
    config: Path | None,
    run_dir: Path | None,
    dataset: Path | None,
    geometry_id: str,
    geometry_source: str,
    generator_id: str | None,
    control_input_deg: float | None,
    control_input_values: list[float],
    diff_input_values: list[float] | None = None,
    alpha: float,
    velocity: float,
    altitude: float,
    beta: float,
    mach: float,
    p: float,
    q: float,
    r: float,
    alpha_values: list[float],
    beta_values: list[float],
    velocity_values: list[float],
    altitude_values: list[float],
    p_values: list[float],
    q_values: list[float],
    r_values: list[float],
    solver: str,
    avl_command: str,
    timeout_sec: int,
    spanwise_resolution: int,
    chordwise_resolution: int,
    spanwise_spacing: str,
    chordwise_spacing: str,
    save_surface_forces: bool,
    save_element_forces: bool,
    seed: int,
    output_name: str,
    max_cases: int | None = None,
    # --- AVL polar bridge (BRIDGE.1) -- all optional, default = inviscid AVL ---
    airfoil_curated_csv: Path | None = None,
    airfoil_library_id: str | None = None,
    segment_airfoils: list | None = None,  # list[SegmentAirfoilConfig]-like
    airfoil_library_root: Path | None = None,
    viscous_polar_source: str = "curated-xfoil",
    viscous_polar_re_grid: list[float] | None = None,
) -> tuple[Path, Any]:
    label = (
        config.stem if config is not None
        else run_dir.name if run_dir is not None
        else geometry_id
    )

    run_paths, geometry_dir, sweep_dir = create_aero_run_root(
        output_name=output_name,
        label=label,
        prefix="aero_sweep",
    )
    run_root = run_paths.root
    logger = setup_logger(run_paths.logs / "app.log")
    logger.info("Starting aero sweep")
    logger.info("Run root: %s", run_root)
    copied_config_path = _copy_standard_input_config(config, run_root)

    geometry_view, resolved_generator_id, summary = prepare_geometry_for_aero(
        config=config,
        run_dir=run_dir,
        dataset=dataset,
        geometry_id=geometry_id,
        source_policy=geometry_source,
        seed=seed,
        geometry_dir=geometry_dir,
        generator_id=generator_id,
        copy_config_to=None,  # standard copy is input_config.yaml via _copy_standard_input_config()
    )

    base_fc = FlightCondition(
        alpha_deg=alpha,
        beta_deg=beta,
        mach=mach,
        velocity_mps=velocity,
        altitude_m=altitude,
        p_rad_s=p,
        q_rad_s=q,
        r_rad_s=r,
    )

    # --- AVL polar bridge (BRIDGE.1): build section_map/polar_store when configured ---
    _bridge_section_map = None
    _bridge_polar_store = None
    _bridge_status: dict[str, Any] = {
        "requested_source": viscous_polar_source,
        "active": False,
        "backend": None,
        "reason": "not_requested",
    }

    _source_key = str(viscous_polar_source or "curated-xfoil").strip().lower()

    if _source_key in {"none", "off", "inviscid"}:
        _bridge_status["reason"] = "disabled_by_user"

    elif _source_key in {"neuralfoil", "neural-foil"}:
        try:
            from aeris.airfoil.neuralfoil_polar_source import build_neuralfoil_polar_store_for_segments

            _segment_coords, _semispan_m = _extract_neuralfoil_segment_coords_from_airplane(
                geometry_view.airplane
            )
            _bridge_mach = 0.0 if mach is None else float(mach)
            _bridge_section_map, _bridge_polar_store = build_neuralfoil_polar_store_for_segments(
                _segment_coords,
                semispan_m=float(_semispan_m),
                model_size="large",
                re_grid=viscous_polar_re_grid,
                mach=_bridge_mach,
            )
            _bridge_status.update(
                {
                    "active": True,
                    "backend": "neuralfoil",
                    "reason": "ok",
                    "segment_count": len(_segment_coords),
                    "semispan_m": float(_semispan_m),
                    "re_grid": viscous_polar_re_grid or [],
                    "mach": _bridge_mach,
                }
            )
            logger.info(
                "Polar bridge active: backend=neuralfoil segments=%s semispan=%.6f",
                len(_segment_coords),
                float(_semispan_m),
            )
        except Exception as _bridge_exc:
            logger.warning(
                "NeuralFoil polar bridge setup failed (%s); continuing without it (inviscid AVL).",
                _bridge_exc,
            )
            _bridge_section_map = None
            _bridge_polar_store = None
            _bridge_status.update(
                {
                    "active": False,
                    "backend": "neuralfoil",
                    "reason": f"setup_failed: {_bridge_exc}",
                }
            )

    elif airfoil_curated_csv is not None and (airfoil_library_id or segment_airfoils):
        from aeris.airfoil.polar_store import AirfoilPolarStore
        from aeris.airfoil.section_map import SectionAirfoilMap

        _semispan_m = None
        try:
            _airplane_for_span = geometry_view.airplane
            _wing_for_span = _airplane_for_span.wings[0]
            _y_stations = [
                abs(float(_xsec.xyz_le[1])) for _xsec in _wing_for_span.xsecs
            ]
            if _y_stations:
                _semispan_m = max(_y_stations)
        except Exception as _span_exc:
            logger.warning(
                "Polar bridge: could not derive semispan from geometry_view.airplane "
                "(%s); falling back to summary lookup.",
                _span_exc,
            )
        if (_semispan_m is None or _semispan_m <= 0.0) and isinstance(summary, dict):
            _semispan_m = summary.get("semi_span_m")
        if _semispan_m is None or _semispan_m <= 0.0:
            logger.warning(
                "Polar bridge requested but semispan could not be resolved from "
                "geometry_view or summary; bridge disabled for this case."
            )
            _bridge_status.update(
                {
                    "active": False,
                    "backend": "curated-xfoil",
                    "reason": "semispan_unresolved",
                }
            )
        else:
            try:
                _bridge_polar_store = AirfoilPolarStore(airfoil_curated_csv)
                if segment_airfoils:
                    _bridge_section_map = SectionAirfoilMap.from_segments(
                        segments=segment_airfoils,
                        library_root=airfoil_library_root,
                        semispan_m=float(_semispan_m),
                    )
                elif airfoil_library_id:
                    _bridge_section_map = SectionAirfoilMap.from_single(
                        airfoil_id=airfoil_library_id,
                        library_root=airfoil_library_root,
                        semispan_m=float(_semispan_m),
                    )
                _bridge_status.update(
                    {
                        "active": _bridge_section_map is not None and _bridge_polar_store is not None,
                        "backend": "curated-xfoil",
                        "reason": "ok",
                        "semispan_m": float(_semispan_m),
                    }
                )
            except Exception as _bridge_exc:
                logger.warning(
                    "Polar bridge setup failed (%s); continuing without it (inviscid AVL).",
                    _bridge_exc,
                )
                _bridge_section_map = None
                _bridge_polar_store = None
                _bridge_status.update(
                    {
                        "active": False,
                        "backend": "curated-xfoil",
                        "reason": f"setup_failed: {_bridge_exc}",
                    }
                )
    else:
        _bridge_status["reason"] = "no_curated_csv_or_segment_mapping"

    sweep = FlightConditionSweep(
        alpha_deg_values=alpha_values,
        beta_deg_values=beta_values,
        velocity_mps_values=velocity_values,
        altitude_m_values=altitude_values,
        p_rad_s_values=p_values,
        q_rad_s_values=q_values,
        r_rad_s_values=r_values,
        control_input_deg_values=control_input_values,
        diff_input_deg_values=diff_input_values or [],
    )

    settings = AeroSolverSettings(
        avl_command=avl_command or None,
        timeout_sec=timeout_sec,
        verbose=False,
        solver_options={
            "paneling": {
                "spanwise_resolution": spanwise_resolution,
                "chordwise_resolution": chordwise_resolution,
                "spanwise_spacing": spanwise_spacing,
                "chordwise_spacing": chordwise_spacing,
            },
            "save_surface_forces": save_surface_forces,
            "save_element_forces": save_element_forces,
            "control_input_deg": control_input_deg,
            "section_map": _bridge_section_map,
            "polar_store": _bridge_polar_store,
        },
    )

    sweep_result = run_aero_sweep(
        geometry=geometry_view,
        base_flight_condition=base_fc,
        sweep=sweep,
        solver_id=solver,
        settings=settings,
        output_dir=sweep_dir,
        provenance={
            "solver": solver,
            "seed": seed,
            "geometry_source": geometry_source,
            "source_label": label,
            "resolved_generator_id": resolved_generator_id,
            "polar_bridge": to_jsonable(_bridge_status),
        },
        max_cases=max_cases,
    )

    manifest = {
        "run_name": run_root.name,
        "solver": solver,
        "geometry_source": geometry_source,
        "resolved_generator_id": resolved_generator_id,
        "control_input_deg": control_input_deg,
        "diff_input_values": diff_input_values or [],
        "base_flight_condition": to_jsonable(asdict(base_fc)),
        "flight_condition_sweep": to_jsonable(asdict(sweep)),
        "geometry_summary": to_jsonable(dataclass_or_value(summary)),
        "aero_sweep_result": to_jsonable(dataclass_or_value(sweep_result)),
        "polar_bridge": to_jsonable(_bridge_status),
    }
    aero_sweep_manifest_path = run_root / "aero_sweep_manifest.json"
    aero_sweep_manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    sweep_summary = manifest.get("aero_sweep_result", {}).get("summary", {})
    n_failed_total = int(sweep_summary.get("n_failed_total", 0) or 0)
    sweep_status = "success" if n_failed_total == 0 else "completed_with_failures"

    generic_manifest_extra: dict[str, Any] = {
        "phase": "aero_sweep",
        "status": sweep_status,
        "domain_manifest": str(aero_sweep_manifest_path),
        "solver": solver,
        "geometry_source": geometry_source,
        "resolved_generator_id": resolved_generator_id,
        "control_input_deg": control_input_deg,
        "requested_n_cases": sweep_summary.get("requested_n_cases"),
        "completed_n_cases": sweep_summary.get("completed_n_cases"),
        "n_success": sweep_summary.get("n_success"),
        "n_failed_total": sweep_summary.get("n_failed_total"),
        "polar_bridge": to_jsonable(_bridge_status),
        "run_artifacts": {
            "geometry_dir": str(geometry_dir),
            "aero_dir": str(sweep_dir),
        },
    }
    generic_manifest_extra.update(_config_manifest_fields(config, copied_config_path))
    write_run_manifest(run_paths, extra=generic_manifest_extra)
    logger.info("Aero sweep completed with status=%s", sweep_status)

    return run_root, sweep_result
