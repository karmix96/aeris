"""Deterministic wall-normal redistribution for valid S6 volume meshes.

pyHyp can locally distort its nominal first-cell distance where several small
tip-cap blocks meet.  This module does not change the surface graph, wall,
farfield, cell count, or column paths.  It measures one dimensionless layer
distribution on explicitly selected, healthy reference blocks and samples every
connected wall-normal column at that common distribution.  Written CGNS remains
the acceptance authority.

The operation is deliberately separate from :mod:`deform`: bounded atlas
deformation moves a proven template onto an exact aerodynamic wall, whereas this
operation repairs the *realized wall-normal parameterization* of an already
valid volume.  It is a candidate method until a governed report and independent
review accept it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from deform import (
    PRODUCTION_MIN_SCALED_QUALITY,
    WALL_TOLERANCE_M,
    _characteristic_length,
    _read_volume_blocks_any,
    acceptance_report,
    first_layer_spacing_report,
    sha256,
    volume_interface_report,
    write_volume_blocks,
)

Array = np.ndarray
SCHEMA = "aeris.mesh.s6_wall_normal_redistribution.v1"
YPLUS_PROJECTION_SCHEMA = "aeris.mesh.s6_wall_normal_yplus_projection.v1"


def reference_layer_fraction(
    blocks: dict[str, Array], reference_zones: Iterable[str]
) -> tuple[Array, dict[str, Any]]:
    """Return a robust common cumulative-distance law from selected zones.

    Every reference column contributes equally.  Taking the median at each
    layer prevents a few corner columns from defining the law while retaining
    pyHyp's measured constant-start and growth behavior.
    """
    selected = tuple(reference_zones)
    if not selected:
        raise ValueError("at least one reference zone is required")
    missing = [zone for zone in selected if zone not in blocks]
    if missing:
        raise ValueError(f"reference zones not present: {missing}")

    layer_count: int | None = None
    samples: list[Array] = []
    per_zone_columns: dict[str, int] = {}
    for zone in selected:
        nodes = np.asarray(blocks[zone], dtype=float)
        if nodes.ndim != 4 or nodes.shape[-1] != 3 or nodes.shape[0] < 2:
            raise ValueError(f"{zone}: expected KJI coordinates, got {nodes.shape}")
        if layer_count is None:
            layer_count = int(nodes.shape[0])
        elif nodes.shape[0] != layer_count:
            raise ValueError("all reference zones must have the same layer count")
        spacing = np.linalg.norm(np.diff(nodes, axis=0), axis=-1)
        if not np.all(np.isfinite(spacing)) or np.any(spacing <= 0.0):
            raise ValueError(f"{zone}: reference columns contain invalid spacing")
        samples.append(spacing.reshape(spacing.shape[0], -1))
        per_zone_columns[zone] = int(np.prod(nodes.shape[1:3]))

    combined = np.concatenate(samples, axis=1)
    median_spacing = np.median(combined, axis=1)
    column_total = np.sum(combined, axis=0)
    if not np.all(np.isfinite(column_total)) or np.any(column_total <= 0.0):
        raise ValueError("reference column distances must be finite and positive")
    normalized_cumulative = (
        np.vstack([np.zeros(combined.shape[1]), np.cumsum(combined, axis=0)])
        / column_total[None, :]
    )
    fraction = np.median(normalized_cumulative, axis=1)
    fraction[0] = 0.0
    fraction[-1] = 1.0
    if np.any(np.diff(fraction) <= 0.0):
        raise ValueError("reference layer fractions must be strictly increasing")
    return fraction, {
        "reference_zones": list(selected),
        "reference_column_count": int(combined.shape[1]),
        "layer_point_count": int(len(fraction)),
        "fraction_estimator": "median_per_column_normalized_cumulative_distance",
        "median_layer_spacing_m": median_spacing.tolist(),
        "column_total_distance_m": {
            "minimum": float(np.min(column_total)),
            "p50": float(np.quantile(column_total, 0.50)),
            "p95": float(np.quantile(column_total, 0.95)),
            "maximum": float(np.max(column_total)),
        },
        "cumulative_fraction": fraction.tolist(),
        "per_zone_column_count": per_zone_columns,
    }


def redistribute_volume_columns(
    blocks: dict[str, Array], cumulative_fraction: Array
) -> dict[str, Array]:
    """Resample every existing column at one common cumulative-distance law."""
    fraction = np.asarray(cumulative_fraction, dtype=float)
    if (
        fraction.ndim != 1
        or len(fraction) < 2
        or not np.all(np.isfinite(fraction))
        or fraction[0] != 0.0
        or fraction[-1] != 1.0
        or np.any(np.diff(fraction) <= 0.0)
    ):
        raise ValueError("cumulative_fraction must increase strictly from 0 to 1")

    redistributed: dict[str, Array] = {}
    for zone, source in blocks.items():
        nodes = np.asarray(source, dtype=float)
        if nodes.ndim != 4 or nodes.shape[-1] != 3:
            raise ValueError(f"{zone}: expected KJI coordinates, got {nodes.shape}")
        if nodes.shape[0] != len(fraction):
            raise ValueError(f"{zone}: {nodes.shape[0]} layer points != law length {len(fraction)}")

        flat = nodes.reshape(nodes.shape[0], -1, 3)
        segment = np.linalg.norm(np.diff(flat, axis=0), axis=-1)
        if not np.all(np.isfinite(segment)) or np.any(segment <= 0.0):
            raise ValueError(f"{zone}: columns contain invalid spacing")
        old_distance = np.concatenate(
            [np.zeros((1, flat.shape[1])), np.cumsum(segment, axis=0)], axis=0
        )
        total = old_distance[-1]
        target_distance = fraction[:, None] * total[None, :]
        target = np.empty_like(flat)
        for column in range(flat.shape[1]):
            for axis in range(3):
                target[:, column, axis] = np.interp(
                    target_distance[:, column],
                    old_distance[:, column],
                    flat[:, column, axis],
                )

        # Make the two protected boundaries bit-identical to the input even if
        # interpolation lands a few ulps away from an endpoint.
        target[0] = flat[0]
        target[-1] = flat[-1]
        redistributed[zone] = target.reshape(nodes.shape)
    return redistributed


def coordinate_payload_sha256(blocks: dict[str, Array]) -> str:
    """Hash ordered names, shapes, and little-endian float64 coordinates."""
    digest = hashlib.sha256()
    for zone, nodes in blocks.items():
        values = np.ascontiguousarray(nodes, dtype="<f8")
        digest.update(zone.encode("utf-8"))
        digest.update(b"\0")
        digest.update(np.asarray(values.shape, dtype="<i8").tobytes())
        digest.update(values.tobytes())
    return digest.hexdigest()


def _wall_cell_first_height(nodes: Array) -> Array:
    """Approximate cell-centroid wall distance from the four wall-node edges."""
    edge = np.linalg.norm(nodes[1] - nodes[0], axis=-1)
    return 0.25 * (edge[:-1, :-1] + edge[1:, :-1] + edge[:-1, 1:] + edge[1:, 1:])


def _numeric_suffix(value: str) -> int:
    match = re.search(r"(\d+)$", value)
    if match is None:
        raise ValueError(f"wall solution zone has no numeric suffix: {value}")
    return int(match.group(1))


def _yplus_statistics(
    values: Array, *, target: float, p95_max: float, p99_max: float, absolute_max: float
) -> dict[str, Any]:
    finite = values[np.isfinite(values)]
    failures: list[str] = []
    if finite.size != values.size:
        failures.append("nonfinite_yplus")
    if np.any(finite < 0.0):
        failures.append("negative_yplus")
    if not finite.size:
        failures.append("no_finite_yplus")
        statistics = {key: None for key in ("minimum", "mean", "p50", "p95", "p99", "maximum")}
        statistics["fraction_at_or_below_target"] = None
    else:
        statistics = {
            "minimum": float(np.min(finite)),
            "mean": float(np.mean(finite)),
            "p50": float(np.quantile(finite, 0.50)),
            "p95": float(np.quantile(finite, 0.95)),
            "p99": float(np.quantile(finite, 0.99)),
            "maximum": float(np.max(finite)),
            "fraction_at_or_below_target": float(np.mean(finite <= target)),
        }
        if statistics["p95"] > p95_max:
            failures.append("p95_above_limit")
        if statistics["p99"] > p99_max:
            failures.append("p99_above_limit")
        if statistics["maximum"] > absolute_max:
            failures.append("maximum_above_limit")
    return {
        "passed": not failures,
        "failure_reasons": failures,
        "sample_count": int(values.size),
        "nonfinite_count": int(values.size - finite.size),
        "negative_count": int(np.count_nonzero(finite < 0.0)),
        "statistics": statistics,
    }


def projected_wall_yplus(
    *,
    source_surface_cgns: Path,
    source_blocks: dict[str, Array],
    candidate_blocks: dict[str, Array],
) -> dict[str, Any]:
    """Scale measured y+ by the exact local first-cell-height ratio.

    This is a screening projection with the attempt's flow field held fixed.  It
    cannot replace y+ measured by a converged CFD solution on the candidate.
    """
    from cfd_qc import (
        YPLUS_ABSOLUTE_MAX,
        YPLUS_P95_MAX,
        YPLUS_P99_MAX,
        YPLUS_TARGET,
        YPLUS_WALL_DISTANCE_CONVENTION,
        read_surface_field_arrays,
    )

    if list(source_blocks) != list(candidate_blocks):
        raise ValueError("source and candidate volume zone order/names differ")
    source_surface_cgns = Path(source_surface_cgns).resolve()
    fields, reader = read_surface_field_arrays(source_surface_cgns, ["YPlus"])
    wall_fields = sorted(
        (
            (zone, zone_fields)
            for zone, zone_fields in fields.items()
            if "nswall"
            in "".join(character for character in zone.casefold() if character.isalnum())
        ),
        key=lambda item: _numeric_suffix(item[0]),
    )
    if len(wall_fields) != len(source_blocks):
        raise ValueError(
            f"{len(wall_fields)} wall solution zones != {len(source_blocks)} volume zones"
        )

    thresholds = {
        "target": YPLUS_TARGET,
        "p95_max": YPLUS_P95_MAX,
        "p99_max": YPLUS_P99_MAX,
        "absolute_max": YPLUS_ABSOLUTE_MAX,
    }
    regions: dict[str, Any] = {}
    projected_values: list[Array] = []
    for (surface_zone, zone_fields), (volume_zone, source_nodes) in zip(
        wall_fields, source_blocks.items(), strict=True
    ):
        candidate_nodes = candidate_blocks[volume_zone]
        yplus_arrays = [
            array
            for field_name, arrays in zone_fields.items()
            if field_name.casefold() == "yplus"
            for array in arrays
        ]
        if not yplus_arrays:
            raise ValueError(f"{surface_zone}: no YPlus field")
        measured = np.concatenate(yplus_arrays)
        source_height = _wall_cell_first_height(source_nodes).reshape(-1)
        candidate_height = _wall_cell_first_height(candidate_nodes).reshape(-1)
        if measured.size != source_height.size or measured.size != candidate_height.size:
            raise ValueError(
                f"{surface_zone}/{volume_zone}: YPlus count {measured.size} does not match "
                f"wall-cell count {source_height.size}/{candidate_height.size}"
            )
        if np.any(source_height <= 0.0) or np.any(candidate_height <= 0.0):
            raise ValueError(f"{volume_zone}: nonpositive wall-cell height")
        height_ratio = candidate_height / source_height
        projected = measured * height_ratio
        projected_values.append(projected)
        regions[surface_zone] = {
            "volume_zone": volume_zone,
            "source": _yplus_statistics(measured, **thresholds),
            "projected": _yplus_statistics(projected, **thresholds),
            "first_cell_height_ratio": {
                "minimum": float(np.min(height_ratio)),
                "p50": float(np.quantile(height_ratio, 0.50)),
                "p95": float(np.quantile(height_ratio, 0.95)),
                "maximum": float(np.max(height_ratio)),
            },
        }

    global_projection = _yplus_statistics(np.concatenate(projected_values), **thresholds)
    failed_regions = [zone for zone, result in regions.items() if not result["projected"]["passed"]]
    return {
        "schema": YPLUS_PROJECTION_SCHEMA,
        "status": "diagnostic_projection_not_cfd_acceptance",
        "method": "measured_yplus_times_candidate_over_source_local_first_cell_height",
        "assumption": (
            "attempt flow and wall shear held fixed; local y+ scales linearly with wall distance"
        ),
        "wall_distance_convention": YPLUS_WALL_DISTANCE_CONVENTION,
        "source_surface_cgns": str(source_surface_cgns),
        "source_surface_cgns_sha256": sha256(source_surface_cgns),
        "surface_reader": reader,
        "thresholds": thresholds,
        "global": global_projection,
        "regions": regions,
        "failed_regions": failed_regions,
        "projected_gate_passed": global_projection["passed"] and not failed_regions,
        "accepted_classification_allowed": False,
    }


def redistribute_cgns(
    *,
    input_cgns: Path,
    output_cgns: Path,
    report_path: Path,
    reference_zones: Iterable[str],
    source_surface_cgns: Path | None = None,
    production_floor: float = PRODUCTION_MIN_SCALED_QUALITY,
) -> dict[str, Any]:
    """Redistribute, write, reopen, and independently audit one volume CGNS."""
    input_cgns = Path(input_cgns).resolve()
    output_cgns = Path(output_cgns).resolve()
    report_path = Path(report_path).resolve()
    if report_path.exists():
        raise FileExistsError(f"refusing to overwrite report: {report_path}")
    if output_cgns.exists():
        raise FileExistsError(f"refusing to overwrite CGNS: {output_cgns}")

    source = _read_volume_blocks_any(input_cgns)
    reference_fraction, reference = reference_layer_fraction(source, reference_zones)
    candidate = redistribute_volume_columns(source, reference_fraction)
    characteristic_length = _characteristic_length(
        {name: nodes[0].transpose(1, 0, 2) for name, nodes in source.items()}
    )

    source_interfaces = volume_interface_report(source)
    candidate_interfaces = volume_interface_report(candidate)
    wall_error = max(float(np.max(np.abs(candidate[zone][0] - source[zone][0]))) for zone in source)
    farfield_error = max(
        float(np.max(np.abs(candidate[zone][-1] - source[zone][-1]))) for zone in source
    )
    metadata = {
        "max_wall_error_m": wall_error,
        "max_farfield_error_m": farfield_error,
        "template_interfaces": source_interfaces,
        "deformed_interfaces": candidate_interfaces,
        "first_layer_spacing": {
            "source": first_layer_spacing_report(
                source, characteristic_length_m=characteristic_length
            ),
            "deformed": first_layer_spacing_report(
                candidate, characteristic_length_m=characteristic_length
            ),
        },
    }
    in_memory_acceptance = acceptance_report(candidate, metadata, production_floor=production_floor)
    if farfield_error > WALL_TOLERANCE_M:
        in_memory_acceptance["hard_gate_passed"] = False
        in_memory_acceptance["production_floor_passed"] = False
        in_memory_acceptance["hard_gate_failure_reasons"].append("farfield_fidelity")

    write_volume_blocks(input_cgns, output_cgns, candidate)
    written = _read_volume_blocks_any(output_cgns)
    written_interfaces = volume_interface_report(written)
    written_wall_error = max(
        float(np.max(np.abs(written[zone][0] - source[zone][0]))) for zone in source
    )
    written_farfield_error = max(
        float(np.max(np.abs(written[zone][-1] - source[zone][-1]))) for zone in source
    )
    written_metadata = {
        **metadata,
        "max_wall_error_m": written_wall_error,
        "max_farfield_error_m": written_farfield_error,
        "deformed_interfaces": written_interfaces,
        "first_layer_spacing": {
            **metadata["first_layer_spacing"],
            "deformed": first_layer_spacing_report(
                written, characteristic_length_m=characteristic_length
            ),
        },
    }
    acceptance = acceptance_report(written, written_metadata, production_floor=production_floor)
    if written_farfield_error > WALL_TOLERANCE_M:
        acceptance["hard_gate_passed"] = False
        acceptance["production_floor_passed"] = False
        acceptance["hard_gate_failure_reasons"].append("farfield_fidelity")

    source_acceptance = acceptance_report(
        source,
        {
            **metadata,
            "max_wall_error_m": 0.0,
            "deformed_interfaces": source_interfaces,
            "first_layer_spacing": {"deformed": metadata["first_layer_spacing"]["source"]},
        },
        production_floor=production_floor,
    )
    projection = (
        projected_wall_yplus(
            source_surface_cgns=source_surface_cgns,
            source_blocks=source,
            candidate_blocks=written,
        )
        if source_surface_cgns is not None
        else None
    )
    source_cells = int(source_acceptance["quality"]["total_cells"])
    output_cells = int(acceptance["quality"]["total_cells"])
    report = {
        "schema": SCHEMA,
        "candidate_only": True,
        "cfd_run": False,
        "input_cgns": str(input_cgns),
        "input_cgns_sha256": sha256(input_cgns),
        "input_coordinate_payload_sha256": coordinate_payload_sha256(source),
        "output_cgns": str(output_cgns),
        "output_cgns_sha256": sha256(output_cgns),
        "output_coordinate_payload_sha256": coordinate_payload_sha256(written),
        "cell_counts": {"source": source_cells, "output": output_cells},
        "cell_count_changed": output_cells != source_cells,
        "reference_layer_law": reference,
        "redistribution": written_metadata,
        "source_acceptance": source_acceptance,
        "in_memory_acceptance": in_memory_acceptance,
        "acceptance": acceptance,
        "yplus_projection": projection,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-cgns", type=Path, required=True)
    parser.add_argument("--output-cgns", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--reference-zone", action="append", required=True)
    parser.add_argument("--source-surface-solution", type=Path)
    parser.add_argument("--production-floor", type=float, default=PRODUCTION_MIN_SCALED_QUALITY)
    args = parser.parse_args()
    report = redistribute_cgns(
        input_cgns=args.input_cgns,
        output_cgns=args.output_cgns,
        report_path=args.report,
        reference_zones=args.reference_zone,
        source_surface_cgns=args.source_surface_solution,
        production_floor=args.production_floor,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["acceptance"]["production_floor_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
