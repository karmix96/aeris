"""Deterministic parameter-space atlas selection for S6."""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

Array = np.ndarray


HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _path in (REPO_ROOT / "src", STUDIES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from shared.geometry_sets import _config, design_matrix, geometry_id  # noqa: E402

ATLAS_SCHEMA = "aeris.mesh.s6_bounded_atlas.v2"
MESH_DISTANCE_EXCLUDED = frozenset({"elevon_start_frac", "elevon_end_frac", "elevon_hinge_frac"})


def _range_pair(value: Any, *, sweep: bool = False) -> tuple[float, float]:
    low, high = float(value.min), float(value.max)
    return (-high, -low) if sweep else (low, high)


def design_bounds() -> tuple[list[str], Array, Array]:
    """Return active design names and their exact canonical bounds."""
    config = _config()
    names = config.active_design_variable_names()
    lows: list[float] = []
    highs: list[float] = []
    for name in names:
        if hasattr(config.planform_bounds, name):
            pair = _range_pair(
                getattr(config.planform_bounds, name),
                sweep=name.startswith("sw") and name.endswith("_deg"),
            )
        elif hasattr(config.section_bounds, name):
            pair = _range_pair(getattr(config.section_bounds, name))
        elif config.elevon_bounds is not None and hasattr(config.elevon_bounds, name):
            pair = _range_pair(getattr(config.elevon_bounds, name))
        else:
            raise KeyError(f"no canonical bounds found for active variable {name!r}")
        lows.append(pair[0])
        highs.append(pair[1])
    return names, np.asarray(lows), np.asarray(highs)


def mesh_distance_variable_names() -> list[str]:
    names, low, high = design_bounds()
    return [
        name
        for name, lo, hi in zip(names, low, high, strict=True)
        if hi > lo and name not in MESH_DISTANCE_EXCLUDED
    ]


def normalize_matrix(matrix: Array, names: Iterable[str]) -> Array:
    """Normalize the OML-active variables used for mesh-template distance."""
    expected, low, high = design_bounds()
    names = list(names)
    if names != expected:
        raise ValueError(f"design columns differ from canonical order: {names} != {expected}")
    matrix = np.asarray(matrix, dtype=float)
    if matrix.shape[-1] != len(expected):
        raise ValueError(f"design matrix has {matrix.shape[-1]} columns; expected {len(expected)}")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("design matrix contains non-finite values")
    span = high - low
    varying = span > 0.0
    metric = np.asarray(
        [
            is_varying and name not in MESH_DISTANCE_EXCLUDED
            for name, is_varying in zip(names, varying, strict=True)
        ]
    )
    if not np.any(metric):
        raise ValueError("the S6 design space has no varying design variables")
    tolerance = 1.0e-10
    normalized_varying = (matrix[..., varying] - low[varying]) / span[varying]
    if np.any(normalized_varying < -tolerance) or np.any(normalized_varying > 1.0 + tolerance):
        raise ValueError("design matrix contains values outside the canonical bounds")
    fixed_tolerance = tolerance * np.maximum(1.0, np.abs(low[~varying]))
    if np.any(np.abs(matrix[..., ~varying] - low[~varying]) > fixed_tolerance):
        raise ValueError("design matrix changes a fixed canonical variable")
    normalized = (matrix[..., metric] - low[metric]) / span[metric]
    return np.clip(normalized, 0.0, 1.0)


def rms_distance(left: Array, right: Array) -> Array:
    """Root-mean-square distance per design variable."""
    delta = np.asarray(left) - np.asarray(right)
    return np.linalg.norm(delta, axis=-1) / math.sqrt(delta.shape[-1])


def farthest_point_indices(points: Array, count: int) -> list[int]:
    """Deterministic maximin template selection, seeded nearest the cube center."""
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or not len(points):
        raise ValueError("points must be a non-empty (n, d) matrix")
    if not 1 <= count <= len(points):
        raise ValueError(f"template count must be within [1, {len(points)}]")
    center = np.full(points.shape[1], 0.5)
    first = int(np.argmin(rms_distance(points, center)))
    selected = [first]
    nearest = rms_distance(points, points[first])
    while len(selected) < count:
        nearest[np.asarray(selected)] = -1.0
        candidate = int(np.argmax(nearest))
        selected.append(candidate)
        nearest = np.minimum(nearest, rms_distance(points, points[candidate]))
    return selected


def build_atlas_manifest(
    *,
    set_name: str = "lhs100_seed42",
    template_count: int = 16,
    trust_radius_rms: float = 0.25,
) -> dict[str, Any]:
    """Select templates and assign every development geometry to its nearest one."""
    matrix, names = design_matrix(set_name)
    normalized = normalize_matrix(matrix, names)
    templates = farthest_point_indices(normalized, template_count)
    return build_manifest_for_indices(
        set_name=set_name,
        template_indices=templates,
        trust_radius_rms=trust_radius_rms,
        template_selection=("deterministic farthest-point maximin from cube-center seed"),
    )


def build_manifest_for_indices(
    *,
    set_name: str,
    template_indices: Iterable[int],
    trust_radius_rms: float,
    template_selection: str,
    enrichment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a complete atlas manifest from an explicit ordered template set."""
    matrix, names = design_matrix(set_name)
    normalized = normalize_matrix(matrix, names)
    metric_names = mesh_distance_variable_names()
    templates = [int(index) for index in template_indices]
    if not templates or len(templates) != len(set(templates)):
        raise ValueError("template indices must be non-empty and unique")
    if any(index < 0 or index >= len(normalized) for index in templates):
        raise ValueError("template indices must address the development set")
    template_points = normalized[templates]
    distances = np.stack([rms_distance(normalized, point) for point in template_points], axis=1)
    assignment = np.argmin(distances, axis=1)
    nearest = distances[np.arange(len(normalized)), assignment]

    rows = []
    for index in range(len(normalized)):
        slot = int(assignment[index])
        rows.append(
            {
                "geometry_index": index,
                "geometry_id": geometry_id(set_name, index),
                "template_slot": slot,
                "template_index": int(templates[slot]),
                "template_geometry_id": geometry_id(set_name, int(templates[slot])),
                "distance_rms": float(nearest[index]),
                "inside_trust_radius": bool(nearest[index] <= trust_radius_rms),
            }
        )

    manifest = {
        "schema": ATLAS_SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "set_name": set_name,
        "design_variables": names,
        "distance_variables": metric_names,
        "distance": "euclidean distance divided by sqrt(number of active variables)",
        "template_selection": template_selection,
        "template_count": len(templates),
        "template_indices": templates,
        "template_geometry_ids": [geometry_id(set_name, index) for index in templates],
        "trust_radius_rms": trust_radius_rms,
        "coverage": {
            "geometries": len(normalized),
            "inside_radius": int(np.count_nonzero(nearest <= trust_radius_rms)),
            "fraction_inside_radius": float(np.mean(nearest <= trust_radius_rms)),
            "max_nearest_distance_rms": float(nearest.max()),
            "mean_nearest_distance_rms": float(nearest.mean()),
            "p95_nearest_distance_rms": float(np.quantile(nearest, 0.95)),
        },
        "assignments": rows,
    }
    if enrichment is not None:
        manifest["quality_enrichment"] = enrichment
    return manifest


def qualify_atlas_seeds(
    manifest: dict[str, Any],
    seed_report: dict[str, Any],
    *,
    production_floor: float = 0.10,
    minimum_templates: int,
) -> dict[str, Any]:
    """Prune failed production seeds without claiming atlas validation."""
    if manifest.get("schema") != ATLAS_SCHEMA:
        raise ValueError("atlas manifest schema is not current")
    if seed_report.get("schema") != "aeris.mesh.s6_seed_build.v1":
        raise ValueError("seed report schema is not current")
    if seed_report.get("level") != "production":
        raise ValueError("only a production seed report can qualify atlas seeds")
    if not 0.0 < production_floor <= 1.0:
        raise ValueError("production floor must be within (0, 1]")

    source = [int(index) for index in manifest["template_indices"]]
    reported = [int(index) for index in seed_report.get("indices", [])]
    if reported != source:
        raise ValueError("seed report was not produced from this atlas")
    rows = seed_report.get("rows", [])
    row_indices = [int(row["geometry_index"]) for row in rows]
    if row_indices != source or len(row_indices) != len(set(row_indices)):
        raise ValueError("seed report does not contain the complete ordered atlas")
    if int(seed_report.get("attempted", -1)) != len(source):
        raise ValueError("seed report attempted count is incomplete")
    if not 1 <= minimum_templates <= len(source):
        raise ValueError("minimum templates must be within the source atlas size")

    qualified: list[int] = []
    rejected: list[dict[str, Any]] = []
    for row in rows:
        index = int(row["geometry_index"])
        audit = row.get("audit", {})
        quality = audit.get("quality", {})
        minimum = quality.get("min_scaled_quality")
        minimum_value = float(minimum) if minimum is not None else None
        reasons = list(audit.get("failure_reasons", []))
        valid = bool(
            row.get("state") == "PASS"
            and audit.get("state") == "PASS"
            and not reasons
            and minimum_value is not None
            and math.isfinite(minimum_value)
            and minimum_value >= production_floor
            and int(quality.get("inverted_cells", -1)) == 0
            and float(quality.get("min_volume", -1.0)) > 0.0
        )
        if valid:
            qualified.append(index)
            continue
        march_quality = audit.get("march_result", {}).get("march_metrics", {}).get("min_quality")
        rejected.append(
            {
                "geometry_index": index,
                "geometry_id": row.get("geometry_id"),
                "state": row.get("state"),
                "failure_reasons": reasons,
                "independent_min_scaled_quality": minimum_value,
                "pyhyp_min_quality": (float(march_quality) if march_quality is not None else None),
                "inverted_cells": quality.get("inverted_cells"),
            }
        )

    if len(qualified) < minimum_templates:
        raise ValueError(
            f"only {len(qualified)} production seeds qualify; minimum is {minimum_templates}"
        )
    qualification = {
        "method": "complete production seed report qualification",
        "volume_level": "production",
        "normal_points": seed_report.get("normal_points"),
        "eps_e": seed_report.get("eps_e"),
        "first_cell_fraction_characteristic": seed_report.get("first_cell_fraction_characteristic"),
        "wall_spacing_source": seed_report.get("wall_spacing_source"),
        "production_floor": production_floor,
        "source_template_indices": source,
        "qualified_indices": qualified,
        "qualified_seed_evidence": [
            {
                "geometry_index": int(row["geometry_index"]),
                "geometry_id": row.get("geometry_id"),
                "independent_min_scaled_quality": float(
                    row["audit"]["quality"]["min_scaled_quality"]
                ),
                "inverted_cells": int(row["audit"]["quality"]["inverted_cells"]),
                "cgns_sha256": row["audit"].get("cgns_sha256"),
                "surface_npz_sha256": row["audit"].get("surface_npz_sha256"),
            }
            for row in rows
            if int(row["geometry_index"]) in qualified
        ],
        "rejected": rejected,
        "requires_complete_development_revalidation": True,
        "freeze_ready": False,
    }
    result = build_manifest_for_indices(
        set_name=str(manifest["set_name"]),
        template_indices=qualified,
        trust_radius_rms=float(manifest["trust_radius_rms"]),
        template_selection=(
            "deterministic maximin pruned by complete production seed qualification"
        ),
    )
    if "quality_enrichment" in manifest:
        result["prior_quality_enrichment"] = manifest["quality_enrichment"]
    result["seed_qualification"] = qualification
    return result


def enrich_atlas_manifest(
    manifest: dict[str, Any],
    development_report: dict[str, Any],
    *,
    warning_quality: float = 0.15,
    maximum_attempts: int = 5,
    maximum_templates: int = 32,
    required_freeze_level: str = "production",
) -> dict[str, Any]:
    """Add deterministic seed cases for weak development-set atlas routes."""
    if manifest.get("schema") != ATLAS_SCHEMA:
        raise ValueError("atlas manifest schema is not current")
    if development_report.get("set_name") != manifest.get("set_name"):
        raise ValueError("development report and atlas use different geometry sets")
    if warning_quality <= 0.0 or maximum_attempts < 1:
        raise ValueError("quality and attempt thresholds must be positive")
    validation_level = development_report.get("volume_level")
    allowed_levels = {"smoke", "fine", "production"}
    if validation_level not in allowed_levels:
        raise ValueError("development report has no supported volume level")
    if required_freeze_level != "production":
        raise ValueError("S6 atlas freeze is permanently pinned to production")

    original = [int(index) for index in manifest["template_indices"]]
    if maximum_templates < len(original):
        raise ValueError("maximum templates is below the current atlas size")
    report_templates = [int(index) for index in development_report.get("template_indices", [])]
    if report_templates != original:
        raise ValueError("development report was not produced with this atlas")
    if int(development_report.get("candidate_count", 0)) < len(original):
        raise ValueError("development report did not try the complete atlas when needed")
    if float(development_report.get("preferred_quality", 0.0)) < warning_quality:
        raise ValueError("development routing quality target is below the warning quality")
    rows = development_report.get("rows", [])
    row_indices = [int(row["geometry_index"]) for row in rows]
    expected_indices = [int(row["geometry_index"]) for row in manifest["assignments"]]
    if len(row_indices) != len(set(row_indices)) or set(row_indices) != set(expected_indices):
        raise ValueError("development report does not cover the complete development set")

    candidates: list[dict[str, Any]] = []
    accepted_existing_warnings: list[dict[str, Any]] = []
    unresolved_existing: list[dict[str, Any]] = []
    seed_rejections = {
        int(row["geometry_index"]): row
        for row in manifest.get("seed_qualification", {}).get("rejected", [])
    }
    accepted_unbuildable_warnings: list[dict[str, Any]] = []
    unresolved_unbuildable: list[dict[str, Any]] = []
    for row in rows:
        index = int(row["geometry_index"])
        attempts = len(row.get("attempts", []))
        quality = row.get("accepted_min_scaled_quality")
        quality_value = float(quality) if quality is not None else None
        failed = row.get("state") != "PASS"
        weak_quality = (
            quality_value is None
            or not math.isfinite(quality_value)
            or quality_value < warning_quality
        )
        slow_route = attempts > maximum_attempts
        if not (failed or weak_quality or slow_route):
            continue
        candidate = {
            "geometry_index": index,
            "state": row.get("state"),
            "accepted_min_scaled_quality": quality_value,
            "attempt_count": attempts,
            "reasons": [
                reason
                for reason, active in (
                    ("no_accepted_template", failed),
                    ("quality_below_warning", weak_quality),
                    ("too_many_template_attempts", slow_route),
                )
                if active
            ],
        }
        if index in original:
            identity_considered = any(
                attempt.get("template_index") == index for attempt in row.get("attempts", [])
            )
            candidate["identity_fallback_considered"] = identity_considered
            candidate["all_templates_considered"] = attempts >= len(original)
            if failed or not identity_considered or (weak_quality and attempts < len(original)):
                unresolved_existing.append(candidate)
            else:
                accepted_existing_warnings.append(candidate)
        elif index in seed_rejections:
            candidate["seed_qualification_rejection"] = seed_rejections[index]
            candidate["all_templates_considered"] = attempts >= len(original)
            if failed or (weak_quality and attempts < len(original)):
                unresolved_unbuildable.append(candidate)
            else:
                accepted_unbuildable_warnings.append(candidate)
        else:
            candidates.append(candidate)

    def priority(row: dict[str, Any]) -> tuple[float, float, int, int]:
        quality = row["accepted_min_scaled_quality"]
        finite_quality = float(quality) if quality is not None and math.isfinite(quality) else -1.0
        return (
            0.0 if row["state"] != "PASS" else 1.0,
            finite_quality,
            -int(row["attempt_count"]),
            int(row["geometry_index"]),
        )

    candidates.sort(key=priority)
    capacity = maximum_templates - len(original)
    selected_candidates = candidates[:capacity]
    additions = [int(row["geometry_index"]) for row in selected_candidates]
    quality_ready = not candidates and not unresolved_existing and not unresolved_unbuildable
    enrichment = {
        "method": "development weak-case deterministic enrichment",
        "warning_quality": warning_quality,
        "maximum_attempts": maximum_attempts,
        "maximum_templates": maximum_templates,
        "validation_level": validation_level,
        "required_freeze_level": required_freeze_level,
        "source_template_indices": original,
        "candidate_count": len(candidates),
        "added_indices": additions,
        "selected_candidates": selected_candidates,
        "omitted_due_to_capacity": candidates[capacity:],
        "accepted_existing_template_warnings": accepted_existing_warnings,
        "unresolved_existing_template_cases": unresolved_existing,
        "known_unbuildable_seed_indices": sorted(seed_rejections),
        "accepted_known_unbuildable_warnings": accepted_unbuildable_warnings,
        "unresolved_known_unbuildable_cases": unresolved_unbuildable,
        "requires_revalidation": bool(additions),
        "quality_enrichment_complete": quality_ready,
        "requires_production_validation": bool(quality_ready and validation_level != "production"),
        "freeze_ready": bool(quality_ready and validation_level == "production"),
    }
    result = build_manifest_for_indices(
        set_name=str(manifest["set_name"]),
        template_indices=[*original, *additions],
        trust_radius_rms=float(manifest["trust_radius_rms"]),
        template_selection=(
            "initial deterministic maximin plus deterministic development weak-case enrichment"
        ),
        enrichment=enrichment,
    )
    for key in ("seed_qualification", "prior_quality_enrichment"):
        if key in manifest:
            result[key] = manifest[key]
    return result


def write_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def default(value: Any) -> Any:
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        if is_dataclass(value):
            return asdict(value)
        raise TypeError(type(value).__name__)

    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=default) + "\n",
        encoding="utf-8",
    )
    return path
