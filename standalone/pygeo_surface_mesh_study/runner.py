"""pyGeo-native geometry construction and adaptive surface-mesh execution."""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import math
import platform
import sys
import time
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import yaml

from aeris.generators.bwb_segmented_v1.params import (
    BWBDesignSample,
    BWBGeneratorConfig,
    build_bwb_generator_config,
)
from aeris.generators.bwb_segmented_v1.planform import (
    generate_bwb_planform_from_sample,
)
from aeris.generators.bwb_segmented_v1.pygeo_adapter import (
    PyGeoBuild,
    build_pygeo,
    extract_sections,
    realised_reference_metrics,
    resolve_airfoil_path,
    stations_from_records,
)
from aeris.generators.bwb_segmented_v1.sections import (
    build_section_geometry_from_sample,
)
from aeris.generators.bwb_segmented_v1.validation import (
    validate_bwb_generator_config,
    validate_planform_result,
    validate_section_geometry,
)
from aeris.mesh.surface import (
    PyGeoSurfaceGeometry,
    export_surface_mesh,
)

from .spec import MeshLevel, MetricLimit, StudyCase, StudySpec

RESULT_SCHEMA = "aeris.pygeo_surface_mesh_case.v1"
REPORT_SCHEMA = "aeris.pygeo_surface_mesh_report.v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def write_json(path: Path, payload: object) -> None:
    """Atomically replace one JSON output owned by this study."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError(f"{path}: expected a JSON object")
    return loaded


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=_json_default
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_generator_config(spec: StudySpec) -> BWBGeneratorConfig:
    raw = yaml.safe_load(spec.geometry_config.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"{spec.geometry_config}: expected a YAML mapping")
    config = build_bwb_generator_config(raw)
    validate_bwb_generator_config(config)
    if not config.pygeo.enabled:
        raise ValueError("The study geometry definition must enable geometry.pygeo")
    if config.pygeo.physical_cad.enabled:
        raise ValueError(
            "The surface-mesh geometry definition must disable physical CAD; "
            "this study isolates the neutral pyGeo outer mold line."
        )
    active = set(config.active_design_variable_names())
    varied = {variable.sample_field for variable in spec.variables}
    fixed = set(spec.fixed_sample_values)
    covered = varied | fixed
    if not varied <= active or not active <= covered:
        raise ValueError(
            "Study varied/fixed fields do not cover the geometry definition: "
            f"active_not_covered={sorted(active - covered)}, "
            f"varied_not_active={sorted(varied - active)}"
        )
    return config


def study_provenance(spec: StudySpec) -> dict[str, Any]:
    repo_root = next(
        (
            parent
            for parent in (spec.path.parent, *spec.path.parents)
            if (parent / "pyproject.toml").is_file()
        ),
        Path.cwd(),
    )
    source_candidates = [spec.path, spec.geometry_config]
    source_roots = (
        repo_root / "src/aeris/mesh",
        repo_root / "src/aeris/cfd/meshing",
        repo_root / "src/aeris/generators/bwb_segmented_v1",
        Path(__file__).resolve().parent,
    )
    for root in source_roots:
        if root.is_file():
            source_candidates.append(root)
        elif root.is_dir():
            source_candidates.extend(sorted(root.rglob("*.py")))
    generator_config = load_generator_config(spec)
    airfoil_names = {generator_config.section_bounds.airfoil_name}
    station_airfoils = generator_config.section_bounds.station_airfoils
    if station_airfoils is not None:
        airfoil_names.update(station_airfoils.to_dict().values())
    airfoil_candidates = tuple(
        resolve_airfoil_path(name, spec.airfoil_database) for name in sorted(airfoil_names)
    )
    sources = {
        str(path.resolve()): file_sha256(path.resolve())
        for path in dict.fromkeys((*source_candidates, *airfoil_candidates))
        if path.is_file()
    }
    package_versions = {}
    for package in ("numpy", "scipy", "pyyaml", "pygeo", "pyspline"):
        try:
            package_versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            package_versions[package] = None
    payload = {
        "study_schema": spec.raw.get("schema"),
        "study_fingerprint": spec.fingerprint,
        "sources": sources,
        "python": sys.version,
        "platform": platform.platform(),
        "package_versions": package_versions,
    }
    payload["run_fingerprint"] = canonical_hash(payload)
    return payload


def initialize_workdir(spec: StudySpec, workdir: Path) -> dict[str, Any]:
    workdir = Path(workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    provenance = study_provenance(spec)
    manifest_path = workdir / "study_manifest.json"
    if manifest_path.is_file():
        existing = read_json(manifest_path)
        if existing.get("run_fingerprint") != provenance["run_fingerprint"]:
            raise RuntimeError(
                f"{workdir} belongs to a different source/config state. "
                "Use a new work directory so results from unlike studies are not mixed."
            )
        return existing

    manifest = {
        "schema": REPORT_SCHEMA,
        "study": spec.name,
        "created_at": utc_now(),
        "config_path": str(spec.path),
        "geometry_config_path": str(spec.geometry_config),
        **provenance,
    }
    write_json(manifest_path, manifest)
    write_json(workdir / "case_plan.json", spec.initial_plan())
    return manifest


def make_sample(spec: StudySpec, case: StudyCase) -> BWBDesignSample:
    sample_values = spec.sample_values(case.public_values)
    return BWBDesignSample(**sample_values)


def _geometry_quality(
    build: PyGeoBuild,
    extracted: Sequence[object],
    *,
    config: BWBGeneratorConfig,
    source_fractions: np.ndarray,
) -> dict[str, Any]:
    y = np.asarray([float(section.y_m) for section in extracted], dtype=float)
    y_span = float(y[-1] - y[0])
    spacing_fraction = float(np.min(np.diff(y)) / y_span) if len(y) > 1 and y_span > 0.0 else 0.0
    max_warp = max(float(section.plane_warp_max_chord) for section in extracted)
    max_cst_rms = max(float(section.cst_rms_chord) for section in extracted)
    max_cst = max(float(section.cst_max_chord) for section in extracted)
    all_cst_valid = all(bool(section.cst_valid) for section in extracted)
    limits = config.pygeo.quality
    return {
        **realised_reference_metrics(extracted, symmetric=True),
        "n_extracted_sections": len(extracted),
        "source_span_fractions": source_fractions.tolist(),
        "minimum_source_spacing_fraction": spacing_fraction,
        "max_plane_warp_chord": max_warp,
        "max_cst_rms_chord": max_cst_rms,
        "max_cst_error_chord": max_cst,
        "all_cst_valid": all_cst_valid,
        "frame_reconstruction_error": float(build.frame_reconstruction_error),
        "quality_limits": {
            "max_plane_warp_chord": float(limits.max_plane_warp_chord),
            "max_cst_rms_chord": float(limits.max_cst_rms_chord),
        },
        "quality_passed": bool(
            max_warp <= limits.max_plane_warp_chord
            and max_cst_rms <= limits.max_cst_rms_chord
            and all_cst_valid
        ),
    }


def _polyline_turning_angle_deg(x: np.ndarray, y: np.ndarray) -> float:
    points = np.column_stack([np.asarray(x, dtype=float), np.asarray(y, dtype=float)])
    segments = np.diff(points, axis=0)
    lengths = np.linalg.norm(segments, axis=1)
    valid = lengths > 1.0e-14
    segments = segments[valid]
    lengths = lengths[valid]
    if len(segments) < 2:
        return 0.0
    unit = segments / lengths[:, None]
    cosine = np.sum(unit[:-1] * unit[1:], axis=1)
    return float(np.max(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))))


def _max_abs_rate(values: np.ndarray, coordinate: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    coordinate = np.asarray(coordinate, dtype=float)
    if len(values) < 2 or np.ptp(coordinate) <= 1.0e-14:
        return 0.0
    return float(np.max(np.abs(np.gradient(values, coordinate, edge_order=1))))


def _max_abs_second_rate(values: np.ndarray, coordinate: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    coordinate = np.asarray(coordinate, dtype=float)
    if len(values) < 3 or np.ptp(coordinate) <= 1.0e-14:
        return 0.0
    first = np.gradient(values, coordinate, edge_order=1)
    return float(np.max(np.abs(np.gradient(first, coordinate, edge_order=1))))


def geometry_descriptors(
    planform: object,
    section_geometry: object,
    extracted: Sequence[object],
) -> dict[str, Any]:
    """Return portable, realised descriptors for attribution and law guards.

    Independent controls remain the statistically valid attribution variables.
    These descriptors expose the geometry seen by the mesher and are suitable
    for applicability checks by a future autonomous meshing agent.
    """

    semispan = max(float(planform.semi_span_m), 1.0e-15)
    root_chord = max(float(planform.c1), 1.0e-15)
    boundary_eta = np.asarray(planform.group_boundary_y, dtype=float) / semispan
    panel_eta = np.diff(boundary_eta)
    twist = np.asarray(section_geometry.twist_boundaries_deg, dtype=float)
    dihedral = np.asarray(section_geometry.dihedral_boundaries_deg, dtype=float)
    twist_rates = np.diff(twist) / panel_eta
    dihedral_rates = np.diff(dihedral) / panel_eta

    span_fraction = np.asarray([float(section.span_fraction) for section in extracted], dtype=float)
    thickness_ratio = np.asarray(
        [float(section.thickness_ratio) for section in extracted], dtype=float
    )
    camber_ratio = np.asarray(
        [float(section.max_camber_ratio) for section in extracted], dtype=float
    )
    chord_m = np.asarray([float(section.chord_m) for section in extracted], dtype=float)
    thickness_m = thickness_ratio * chord_m

    fine_eta = np.asarray(planform.front_y_fine, dtype=float) / semispan
    le_x_cref = np.asarray(planform.front_x_fine, dtype=float) / root_chord
    te_x_cref = np.asarray(planform.rear_x_fine, dtype=float) / root_chord
    fine_chord_cref = te_x_cref - le_x_cref

    return {
        "scale": {
            "root_chord_m": float(planform.c1),
            "mean_aerodynamic_scale_m": float(
                planform.approx_area_m2 / max(planform.full_span_m, 1.0e-15)
            ),
            "semi_span_m": float(planform.semi_span_m),
            "full_span_m": float(planform.full_span_m),
            "area_m2": float(planform.approx_area_m2),
            "aspect_ratio": float(planform.approx_aspect_ratio),
            "semi_span_to_root_chord": float(planform.semi_span_m / root_chord),
        },
        "planform": {
            "tip_taper_ratio": float(planform.c4 / root_chord),
            "panel_taper_ratios": [
                float(planform.c2 / root_chord),
                float(planform.c3 / max(planform.c2, 1.0e-15)),
                float(planform.c4 / max(planform.c3, 1.0e-15)),
            ],
            "panel_span_fractions": panel_eta.tolist(),
            "break_span_fractions": boundary_eta.tolist(),
            "le_sweep_magnitudes_deg": [
                abs(float(planform.sw1_deg)),
                abs(float(planform.sw2_deg)),
                abs(float(planform.sw3_deg)),
            ],
            "sweep_jumps_deg": [
                abs(float(planform.sw2_deg - planform.sw1_deg)),
                abs(float(planform.sw3_deg - planform.sw2_deg)),
            ],
            "max_chord_rate_per_semispan": _max_abs_rate(fine_chord_cref, fine_eta),
            "max_chord_curvature_per_semispan2": _max_abs_second_rate(fine_chord_cref, fine_eta),
            "max_le_curvature_per_semispan2": _max_abs_second_rate(le_x_cref, fine_eta),
            "max_te_curvature_per_semispan2": _max_abs_second_rate(te_x_cref, fine_eta),
            "max_le_polyline_turn_deg": _polyline_turning_angle_deg(
                planform.front_x_fine, planform.front_y_fine
            ),
            "max_te_polyline_turn_deg": _polyline_turning_angle_deg(
                planform.rear_x_fine, planform.rear_y_fine
            ),
        },
        "section_kinematics": {
            "twist_stations_deg": twist.tolist(),
            "twist_panel_rates_deg_per_semispan": twist_rates.tolist(),
            "max_abs_twist_rate_deg_per_semispan": float(np.max(np.abs(twist_rates))),
            "dihedral_stations_deg": dihedral.tolist(),
            "dihedral_panel_rates_deg_per_semispan": dihedral_rates.tolist(),
            "max_abs_dihedral_rate_deg_per_semispan": float(np.max(np.abs(dihedral_rates))),
        },
        "airfoil_shape": {
            "policy": "fixed_station_profiles",
            "thickness_ratio_min": float(np.min(thickness_ratio)),
            "thickness_ratio_max": float(np.max(thickness_ratio)),
            "thickness_ratio_range": float(np.ptp(thickness_ratio)),
            "max_abs_thickness_ratio_rate_per_semispan": _max_abs_rate(
                thickness_ratio, span_fraction
            ),
            "dimensional_thickness_m_min": float(np.min(thickness_m)),
            "dimensional_thickness_m_max": float(np.max(thickness_m)),
            "camber_ratio_min": float(np.min(camber_ratio)),
            "camber_ratio_max": float(np.max(camber_ratio)),
            "max_abs_camber_ratio_rate_per_semispan": _max_abs_rate(camber_ratio, span_fraction),
            "independent_thickness_effect_identifiable": False,
        },
    }


def build_geometry(
    spec: StudySpec,
    generator_config: BWBGeneratorConfig,
    case: StudyCase,
) -> tuple[PyGeoSurfaceGeometry, PyGeoBuild, dict[str, Any]]:
    """Build the authoritative pyGeo loft and a uniform realised-section carrier."""

    sample = make_sample(spec, case)
    planform = generate_bwb_planform_from_sample(sample, generator_config)
    validate_planform_result(planform)
    section_geometry = build_section_geometry_from_sample(planform, sample, generator_config)
    validate_section_geometry(section_geometry)
    stations = stations_from_records(section_geometry.sections, spec.airfoil_database)
    pygeo_config = generator_config.pygeo
    bridge_frame = (
        "asb_frame" if pygeo_config.frame_mode == "aeris_frame" else pygeo_config.frame_mode
    )
    build = build_pygeo(
        stations,
        k_span=pygeo_config.k_span,
        frame_mode=bridge_frame,
        n_ctl=pygeo_config.n_ctl,
        tip=pygeo_config.tip,
        tip_scale=pygeo_config.tip_scale,
    )
    source_fractions = np.linspace(0.0, 1.0, spec.source_sections)
    extracted = extract_sections(
        build,
        source_fractions,
        cst_order=spec.extraction_cst_order,
        chordwise_points=spec.extraction_chordwise_points,
    )
    quality = _geometry_quality(
        build,
        extracted,
        config=generator_config,
        source_fractions=source_fractions,
    )
    if quality["minimum_source_spacing_fraction"] < spec.minimum_source_spacing_fraction:
        raise ValueError(
            "Uniform pyGeo mesh-source lattice collapsed: minimum physical span "
            f"spacing fraction={quality['minimum_source_spacing_fraction']:.6e}, "
            f"required={spec.minimum_source_spacing_fraction:.6e}"
        )
    carrier = PyGeoSurfaceGeometry(
        sections=tuple(extracted),
        name=f"{spec.name}_{case.case_id}",
        symmetric=True,
    )
    geometry = {
        "sample": sample.to_dict(),
        "public_values": dict(case.public_values),
        "descriptors": geometry_descriptors(planform, section_geometry, extracted),
        "airfoils": {
            "configured_stations": (
                generator_config.section_bounds.station_airfoils.to_dict()
                if generator_config.section_bounds.station_airfoils is not None
                else {
                    station: generator_config.section_bounds.airfoil_name
                    for station in ("b0", "b1", "b2", "b3")
                }
            ),
            "authored_unique": list(
                dict.fromkeys(section.airfoil_name for section in section_geometry.sections)
            ),
        },
        "planform": {
            "semi_span_m": float(planform.semi_span_m),
            "full_span_m": float(planform.full_span_m),
            "approx_area_m2": float(planform.approx_area_m2),
            "approx_aspect_ratio": float(planform.approx_aspect_ratio),
            "authored_section_count": len(stations),
            "segment_station_counts": [int(planform.N1), int(planform.N2), int(planform.N3)],
        },
        "pygeo": {
            "k_span": int(build.k_span),
            "frame_mode": str(build.frame_mode),
            "frame_reconstruction_error": float(build.frame_reconstruction_error),
        },
        "realised": quality,
    }
    return carrier, build, geometry


_MINIMUM_METRICS = {
    "min_area",
    "min_shape_metric",
    "min_scaled_jacobian",
    "min_triangle_normal_alignment",
}
_MAXIMUM_METRICS = {
    "max_adjacent_normal_angle_deg",
    "max_equiangle_skewness",
    "max_aspect_ratio",
    "max_growth_ratio",
}
_WEIGHTED_MEAN_METRICS = {
    "mean_equiangle_skewness",
}


def group_block_metrics(blocks: Sequence[Mapping[str, Any]], prefix: str) -> dict[str, float | int]:
    """Aggregate per-block QC into one OML or tip metric group."""

    members = [block for block in blocks if str(block.get("name", "")).startswith(prefix)]
    if not members:
        return {}
    result: dict[str, float | int] = {}
    for metric in _MINIMUM_METRICS:
        values = [float(block[metric]) for block in members if metric in block]
        if values:
            result[metric] = min(values)
    for metric in _MAXIMUM_METRICS:
        values = [float(block[metric]) for block in members if metric in block]
        if values:
            result[metric] = max(values)
    cells = [max(1, int(block.get("cells", 1))) for block in members]
    for metric in _WEIGHTED_MEAN_METRICS:
        values_and_weights = [
            (float(block[metric]), weight)
            for block, weight in zip(members, cells, strict=False)
            if metric in block
        ]
        if values_and_weights:
            numerator = sum(value * weight for value, weight in values_and_weights)
            denominator = sum(weight for _, weight in values_and_weights)
            result[metric] = numerator / denominator
    result["nodes"] = sum(int(block.get("nodes", 0)) for block in members)
    result["cells"] = sum(int(block.get("cells", 0)) for block in members)
    result["block_count"] = len(members)
    return result


def report_metrics(report: Mapping[str, Any]) -> dict[str, Any]:
    blocks_raw = report.get("blocks", [])
    blocks = list(blocks_raw) if isinstance(blocks_raw, list) else []
    global_raw = report.get("global", {})
    return {
        "global": dict(global_raw) if isinstance(global_raw, Mapping) else {},
        "oml": group_block_metrics(blocks, "oml_"),
        "tip": group_block_metrics(blocks, "tip_"),
    }


def flatten_metrics(metrics: Mapping[str, Any], prefix: str = "") -> dict[str, float]:
    flattened: dict[str, float] = {}
    for key, value in metrics.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            flattened.update(flatten_metrics(value, path))
        elif isinstance(value, (int, float, np.number)) and not isinstance(value, bool):
            flattened[path] = float(value)
    return flattened


def evaluate_acceptance(
    report: Mapping[str, Any],
    metric_limits: Sequence[MetricLimit],
    *,
    allow_unset_limits: bool,
) -> dict[str, Any]:
    """Apply immutable topology gates plus the user-authored metric limits."""

    connectivity = report.get("connectivity", {})
    free_edges = report.get("free_edges", {})
    symmetry = report.get("symmetry_root", {})
    global_metrics = report.get("global", {})
    structural = {
        "mesher_pre_pyhyp_accepted": bool(report.get("accepted_pre_pyhyp", False)),
        "all_block_connections_matched": bool(
            isinstance(connectivity, Mapping) and connectivity.get("all_matched", False)
        ),
        "closed_except_root": bool(
            isinstance(free_edges, Mapping) and free_edges.get("closed_except_root", False)
        ),
        "root_planar": bool(
            isinstance(symmetry, Mapping) and symmetry.get("planar_within_tolerance", False)
        ),
        "positive_cell_area": bool(
            isinstance(global_metrics, Mapping)
            and float(global_metrics.get("min_area", -math.inf))
            > float(global_metrics.get("area_floor", math.inf))
        ),
        "nonfolded_quads": bool(
            isinstance(global_metrics, Mapping)
            and float(global_metrics.get("min_triangle_normal_alignment", -math.inf))
            > float(global_metrics.get("alignment_floor", -0.25))
        ),
    }
    grouped = report_metrics(report)
    flattened = flatten_metrics(grouped)
    checks: list[dict[str, Any]] = []
    thresholds_passed = True
    for metric in metric_limits:
        value = flattened.get(metric.path)
        if not metric.enabled:
            status = "disabled"
            passed: bool | None = None
        elif metric.limit is None:
            status = "unset_allowed" if allow_unset_limits else "unset"
            passed = True if allow_unset_limits else False
        elif value is None or not math.isfinite(value):
            status = "missing"
            passed = False
        else:
            passed = bool(metric.passes(value))
            status = "pass" if passed else "fail"
        if metric.enabled and passed is not True:
            thresholds_passed = False
        checks.append(
            {
                "path": metric.path,
                "operator": metric.operator,
                "limit": metric.limit,
                "value": value,
                "enabled": metric.enabled,
                "status": status,
                "passed": passed,
            }
        )
    structural_passed = all(structural.values())
    return {
        "structural": structural,
        "structural_passed": structural_passed,
        "metric_checks": checks,
        "metric_limits_passed": thresholds_passed,
        "passed": bool(structural_passed and thresholds_passed),
        "metrics": grouped,
        "flat_metrics": flattened,
    }


def _mesh_parameters(spec: StudySpec, level: MeshLevel) -> dict[str, Any]:
    parameters = dict(spec.mesh_common)
    parameters.update(
        {
            "points_per_block_side": level.points_per_block_side,
            "spanwise_panels_per_section": level.spanwise_panels_per_section,
            "cap_wrap_points": level.cap_wrap_points,
            "tip_radial_points": level.tip_radial_points,
        }
    )
    return parameters


def run_mesh_attempt(
    spec: StudySpec,
    carrier: PyGeoSurfaceGeometry,
    level: MeshLevel,
    output_dir: Path,
    *,
    allow_unset_limits: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    parameters = _mesh_parameters(spec, level)
    report: dict[str, Any] = {}
    error: dict[str, str] | None = None
    try:
        report = export_surface_mesh(
            carrier,
            output_dir,
            require_cgns_export=False,
            **parameters,
        )
    except Exception as exc:  # one bad geometry must not stop the campaign
        error = {"type": type(exc).__name__, "message": str(exc)}
        report_path = output_dir / "surface_report.json"
        if report_path.is_file():
            try:
                report = read_json(report_path)
            except (OSError, ValueError, TypeError):
                report = {}

    acceptance = evaluate_acceptance(
        report,
        spec.metric_limits,
        allow_unset_limits=allow_unset_limits,
    )
    attempt = {
        "level": level.name,
        "level_order": level.order,
        "parameters": parameters,
        "seconds": time.perf_counter() - started,
        "surface_report": str((output_dir / "surface_report.json").resolve()),
        "error": error,
        "acceptance": acceptance,
    }
    write_json(output_dir / "attempt_result.json", attempt)
    return attempt


def _attempt_by_level(
    attempts: Sequence[Mapping[str, Any]], level_name: str
) -> Mapping[str, Any] | None:
    return next((attempt for attempt in attempts if attempt.get("level") == level_name), None)


def _resolution_monotonicity(
    attempts: Sequence[Mapping[str, Any]], levels: Sequence[MeshLevel]
) -> dict[str, Any]:
    pass_by_level = {
        str(attempt.get("level")): bool(
            isinstance(attempt.get("acceptance"), Mapping)
            and attempt["acceptance"].get("passed", False)
        )
        for attempt in attempts
    }
    observed = [
        (level.name, pass_by_level[level.name])
        for level in sorted(levels, key=lambda item: item.order)
        if level.name in pass_by_level
    ]
    seen_pass = False
    reversals: list[str] = []
    for name, passed in observed:
        if passed:
            seen_pass = True
        elif seen_pass:
            reversals.append(name)
    return {
        "observed": [{"level": name, "passed": passed} for name, passed in observed],
        "monotone_pass_after_first_success": not reversals,
        "failures_after_success": reversals,
    }


def projection_fidelity(
    build: PyGeoBuild,
    mesh_npz: Path,
    *,
    sample_nodes: int,
    c_ref_m: float,
) -> dict[str, Any]:
    """Project selected OML nodes to the exact upper/lower pySpline patches."""

    with np.load(mesh_npz) as archive:
        arrays = [
            np.asarray(archive[name], dtype=float)
            for name in archive.files
            if name.startswith("oml_")
        ]
    if not arrays:
        raise ValueError(f"{mesh_npz}: no oml_* blocks found")
    nodes = np.vstack([array.reshape(-1, 3) for array in arrays])
    count = min(int(sample_nodes), len(nodes))
    indices = np.linspace(0, len(nodes) - 1, count, dtype=int)
    sampled = nodes[indices]

    distances: list[np.ndarray] = []
    for surface in build.geometry.surfs[:2]:
        _u, _v, displacement = surface.projectPoint(sampled, nIter=40, eps=1.0e-12)
        displacement_array = np.asarray(displacement, dtype=float)
        if displacement_array.ndim == 1:
            if displacement_array.shape == (3,) and count == 1:
                distance = np.asarray([np.linalg.norm(displacement_array)])
            else:
                distance = np.abs(displacement_array)
        else:
            distance = np.linalg.norm(displacement_array, axis=-1)
        distances.append(distance.reshape(-1))
    nearest = np.minimum(distances[0], distances[1])
    c_ref = max(float(c_ref_m), 1.0e-15)
    return {
        "method": "pySpline Surface.projectPoint; minimum of exact upper/lower patches",
        "scope": "deterministic sample of selected-mesh OML nodes",
        "sample_nodes": int(count),
        "available_oml_nodes_with_seam_duplicates": int(len(nodes)),
        "rms_m": float(np.sqrt(np.mean(nearest**2))),
        "p95_m": float(np.percentile(nearest, 95.0)),
        "max_m": float(np.max(nearest)),
        "rms_mm": float(1.0e3 * np.sqrt(np.mean(nearest**2))),
        "p95_mm": float(1.0e3 * np.percentile(nearest, 95.0)),
        "max_mm": float(1.0e3 * np.max(nearest)),
        "rms_cref": float(np.sqrt(np.mean(nearest**2)) / c_ref),
        "p95_cref": float(np.percentile(nearest, 95.0) / c_ref),
        "max_cref": float(np.max(nearest) / c_ref),
        "includes_deliberate_blunt_te_offset": True,
        "note": (
            "The cap4 mesher opens the trailing edge according to te_thickness, "
            "so this diagnostic includes both section-planarization error and the "
            "deliberate CFD trailing-edge geometry offset."
        ),
    }


def _result_is_reusable(
    result: Mapping[str, Any],
    *,
    run_fingerprint: str,
    case: StudyCase,
    rerun_failed: bool,
) -> bool:
    if result.get("run_fingerprint") != run_fingerprint:
        return False
    if result.get("case_identity_hash") != case.identity_hash:
        return False
    if rerun_failed and result.get("status") != "complete":
        return False
    return result.get("status") in {
        "complete",
        "limits_unresolved",
        "geometry_rejected",
        "geometry_failed",
    }


def run_case(
    spec: StudySpec,
    generator_config: BWBGeneratorConfig,
    case: StudyCase,
    workdir: Path,
    manifest: Mapping[str, Any],
    *,
    allow_unset_limits: bool = False,
    rerun_failed: bool = False,
    smoke_level: str | None = None,
) -> dict[str, Any]:
    case_dir = Path(workdir) / "cases" / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    result_path = case_dir / "result.json"
    if result_path.is_file():
        existing = read_json(result_path)
        if _result_is_reusable(
            existing,
            run_fingerprint=str(manifest["run_fingerprint"]),
            case=case,
            rerun_failed=rerun_failed,
        ):
            return existing
        if existing.get("run_fingerprint") != manifest["run_fingerprint"]:
            raise RuntimeError(f"{case_dir} contains a case from a different study source state")

    case_payload = {
        **case.to_dict(),
        "sample_values": spec.sample_values(case.public_values),
        "run_fingerprint": manifest["run_fingerprint"],
    }
    write_json(case_dir / "case.json", case_payload)
    started = time.perf_counter()
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "study": spec.name,
        "run_fingerprint": manifest["run_fingerprint"],
        "case_identity_hash": case.identity_hash,
        "case": case.to_dict(),
        "started_at": utc_now(),
        "status": "running",
        "geometry": None,
        "attempts": [],
        "reference_level": smoke_level or spec.reference_level,
        "selected_level": None,
        "limits_satisfied": False,
        "projection_diagnostic": None,
    }
    write_json(result_path, result)

    try:
        carrier, build, geometry = build_geometry(spec, generator_config, case)
        result["geometry"] = geometry
        write_json(case_dir / "geometry.json", geometry)
    except Exception as exc:  # campaign-level fault containment
        result.update(
            {
                "status": "geometry_failed",
                "error": {"type": type(exc).__name__, "message": str(exc)},
                "traceback": traceback.format_exc(),
                "finished_at": utc_now(),
                "seconds": time.perf_counter() - started,
            }
        )
        write_json(result_path, result)
        return result

    if not bool(geometry["realised"]["quality_passed"]):
        result.update(
            {
                "status": "geometry_rejected",
                "error": {
                    "type": "GeometryQualityRejection",
                    "message": (
                        "The realised pyGeo section extraction exceeded its "
                        "plane-warp/CST quality limits."
                    ),
                },
                "finished_at": utc_now(),
                "seconds": time.perf_counter() - started,
            }
        )
        write_json(result_path, result)
        return result

    levels = list(spec.levels)
    if smoke_level is not None:
        if smoke_level not in spec.level_map:
            raise ValueError(f"Unknown smoke level {smoke_level!r}")
        execution_levels = [spec.level_map[smoke_level]]
    elif spec.complete_ladder:
        execution_levels = list(levels)
    else:
        reference = spec.reference_level_spec
        execution_levels = [reference]
        execution_levels.extend(level for level in levels if level.order < reference.order)
        execution_levels.extend(level for level in levels if level.order > reference.order)

    attempts: list[dict[str, Any]] = []
    reference_attempt: dict[str, Any] | None = None
    for index, level in enumerate(execution_levels):
        # Standard adaptive protocol always measures the common reference first.
        # It then searches from the coarsest level upward and stops at the first
        # passing level. Fine levels are needed only when L1..reference fail.
        if smoke_level is None and not spec.complete_ladder and index > 0:
            coarser = [
                attempt
                for attempt in attempts
                if int(attempt["level_order"]) < level.order and attempt["acceptance"]["passed"]
            ]
            if coarser:
                break
            if level.order > spec.reference_level_spec.order:
                reference_attempt = _attempt_by_level(attempts, spec.reference_level)
                lower_fail = all(
                    not attempt["acceptance"]["passed"]
                    for attempt in attempts
                    if int(attempt["level_order"]) <= spec.reference_level_spec.order
                )
                if reference_attempt is not None and not lower_fail:
                    break

        attempt_dir = case_dir / "attempts" / level.name
        attempt = run_mesh_attempt(
            spec,
            carrier,
            level,
            attempt_dir,
            allow_unset_limits=allow_unset_limits,
        )
        attempts.append(attempt)
        result["attempts"] = attempts
        write_json(result_path, result)

    passing = sorted(
        (attempt for attempt in attempts if attempt["acceptance"]["passed"]),
        key=lambda attempt: int(attempt["level_order"]),
    )
    selected = passing[0] if passing else None
    reference_attempt = _attempt_by_level(attempts, spec.reference_level)
    if smoke_level is not None:
        reference_attempt = _attempt_by_level(attempts, smoke_level)

    projection: dict[str, Any] | None = None
    if selected is not None and spec.projection_enabled:
        selected_dir = case_dir / "attempts" / str(selected["level"])
        mesh_npz = selected_dir / "surface_blocks.npz"
        if mesh_npz.is_file():
            try:
                projection = projection_fidelity(
                    build,
                    mesh_npz,
                    sample_nodes=spec.projection_sample_nodes,
                    c_ref_m=float(geometry["realised"]["c_ref_m"]),
                )
            except Exception as exc:
                projection = {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }

    result.update(
        {
            "status": "complete" if selected is not None else "limits_unresolved",
            "selected_level": None if selected is None else selected["level"],
            "selected_level_order": None if selected is None else selected["level_order"],
            "limits_satisfied": selected is not None,
            "reference_passed": bool(
                reference_attempt
                and isinstance(reference_attempt.get("acceptance"), Mapping)
                and reference_attempt["acceptance"].get("passed", False)
            ),
            "reference_metrics": (
                None
                if reference_attempt is None
                else reference_attempt["acceptance"].get("flat_metrics", {})
            ),
            "selected_metrics": (
                None if selected is None else selected["acceptance"].get("flat_metrics", {})
            ),
            "resolution_monotonicity": _resolution_monotonicity(attempts, levels),
            "projection_diagnostic": projection,
            "finished_at": utc_now(),
            "seconds": time.perf_counter() - started,
        }
    )
    write_json(result_path, result)
    return result


def collect_results(workdir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cases_dir = Path(workdir) / "cases"
    if not cases_dir.is_dir():
        return results
    for path in sorted(cases_dir.glob("*/result.json")):
        try:
            results.append(read_json(path))
        except (OSError, ValueError, TypeError):
            continue
    return results


def _csv_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, sort_keys=True, default=_json_default)


def assemble_report(
    spec: StudySpec,
    workdir: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    results = collect_results(workdir)
    status_counts: dict[str, int] = {}
    stage_counts: dict[str, int] = {}
    for result in results:
        status = str(result.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
        case = result.get("case", {})
        stage = str(case.get("stage", "unknown")) if isinstance(case, Mapping) else "unknown"
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
    report = {
        "schema": REPORT_SCHEMA,
        "study": spec.name,
        "updated_at": utc_now(),
        "run_fingerprint": manifest["run_fingerprint"],
        "result_count": len(results),
        "status_counts": status_counts,
        "stage_counts": stage_counts,
        "unset_enabled_limits": spec.unset_enabled_limits(),
        "results": results,
    }
    write_json(Path(workdir) / "study_report.json", report)

    variable_names = [variable.name for variable in spec.variables]
    metric_paths = [metric.path for metric in spec.metric_limits]
    fields = [
        "case_id",
        "stage",
        "status",
        "limits_satisfied",
        "reference_passed",
        "reference_level",
        "selected_level",
        "seconds",
        *variable_names,
        *(f"reference.{path}" for path in metric_paths),
        *(f"selected.{path}" for path in metric_paths),
    ]
    csv_path = Path(workdir) / "study_report.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for result in results:
            case = result.get("case", {})
            public = case.get("public_values", {}) if isinstance(case, Mapping) else {}
            reference_metrics = result.get("reference_metrics") or {}
            selected_metrics = result.get("selected_metrics") or {}
            row: dict[str, Any] = {
                "case_id": case.get("case_id") if isinstance(case, Mapping) else None,
                "stage": case.get("stage") if isinstance(case, Mapping) else None,
                "status": result.get("status"),
                "limits_satisfied": result.get("limits_satisfied"),
                "reference_passed": result.get("reference_passed"),
                "reference_level": result.get("reference_level"),
                "selected_level": result.get("selected_level"),
                "seconds": result.get("seconds"),
            }
            row.update({name: public.get(name) for name in variable_names})
            row.update({f"reference.{path}": reference_metrics.get(path) for path in metric_paths})
            row.update({f"selected.{path}": selected_metrics.get(path) for path in metric_paths})
            writer.writerow({key: _csv_value(value) for key, value in row.items()})
    return report


def validate_ready(spec: StudySpec, *, allow_unset_limits: bool) -> None:
    if not spec.geometry_config.is_file():
        raise FileNotFoundError(spec.geometry_config)
    if not spec.airfoil_database.is_dir():
        raise FileNotFoundError(spec.airfoil_database)
    load_generator_config(spec)
    unset = spec.unset_enabled_limits()
    if spec.require_limits_for_run and unset and not allow_unset_limits:
        joined = "\n  - ".join(unset)
        raise ValueError(
            "Insert limits for every enabled acceptance metric before a campaign run:\n"
            f"  - {joined}\n"
            "Use --allow-unset-limits only for planning or the baseline smoke check."
        )


def _run_cases(
    spec: StudySpec,
    generator_config: BWBGeneratorConfig,
    cases: Iterable[StudyCase],
    workdir: Path,
    manifest: Mapping[str, Any],
    *,
    allow_unset_limits: bool,
    rerun_failed: bool,
) -> list[dict[str, Any]]:
    results = []
    for case in cases:
        print(f"[{case.stage}] {case.case_id}", flush=True)
        result = run_case(
            spec,
            generator_config,
            case,
            workdir,
            manifest,
            allow_unset_limits=allow_unset_limits,
            rerun_failed=rerun_failed,
        )
        print(
            f"  {result['status']}; selected={result.get('selected_level')}; "
            f"{float(result.get('seconds', 0.0)):.2f}s",
            flush=True,
        )
        results.append(result)
    return results


def run_stage(
    spec: StudySpec,
    workdir: Path,
    *,
    stage: str,
    allow_unset_limits: bool = False,
    rerun_failed: bool = False,
) -> dict[str, Any]:
    """Run one stage or the complete pre-registered campaign."""

    valid = {
        "baseline",
        "ofat",
        "pairwise",
        "global_train",
        "validation",
        "all",
    }
    if stage not in valid:
        raise ValueError(f"stage must be one of {sorted(valid)}")
    validate_ready(spec, allow_unset_limits=allow_unset_limits)
    generator_config = load_generator_config(spec)
    manifest = initialize_workdir(spec, workdir)

    baseline = [spec.baseline_case(sequence_index=0)]
    ofat = spec.ofat_cases(sequence_start=1)
    pairwise = spec.pairwise_cases(sequence_start=1 + len(ofat))
    global_train = spec.global_train_cases(sequence_start=1 + len(ofat) + len(pairwise))
    validation = spec.validation_cases(
        sequence_start=1 + len(ofat) + len(pairwise) + len(global_train)
    )
    groups = {
        "baseline": baseline,
        "ofat": ofat,
        "pairwise": pairwise,
        "global_train": global_train,
        "validation": validation,
    }
    selected_stages = list(groups) if stage == "all" else [stage]
    for stage_name in selected_stages:
        _run_cases(
            spec,
            generator_config,
            groups[stage_name],
            workdir,
            manifest,
            allow_unset_limits=allow_unset_limits,
            rerun_failed=rerun_failed,
        )
    return assemble_report(spec, workdir, manifest)


def run_smoke(
    spec: StudySpec,
    workdir: Path,
    *,
    level: str = "L1",
) -> dict[str, Any]:
    """Exercise one baseline geometry and one mesh without requiring limits."""

    validate_ready(spec, allow_unset_limits=True)
    generator_config = load_generator_config(spec)
    manifest = initialize_workdir(spec, workdir)
    result = run_case(
        spec,
        generator_config,
        spec.baseline_case(),
        workdir,
        manifest,
        allow_unset_limits=True,
        rerun_failed=True,
        smoke_level=level,
    )
    assemble_report(spec, workdir, manifest)
    return result
