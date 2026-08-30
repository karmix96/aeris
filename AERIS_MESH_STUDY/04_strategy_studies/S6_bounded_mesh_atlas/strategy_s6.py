"""S6: exact-pyGeo, fixed-topology surface meshes for a bounded mesh atlas.

The production idea is deliberately narrow: all campaign geometries come from the
same four-station BWB generator, so they should also share one mesh graph and one
set of block dimensions.  Node coordinates may adapt, but connectivity may not.

S6 keeps the S1/Openblademesh tip closure that has already marched successfully,
while replacing S1's straight interpolation between span stations with direct
evaluation of the pyGeo B-spline loft.  This closes the known fidelity gap without
giving up the topology that made S1 work.
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _path in (REPO_ROOT / "src", STUDIES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from S1_tip_first.strategy_s1 import (  # noqa: E402
    ARC_ORDER,
    NOSE_END_FRAC,
    section_geometry,
    tip_domains_2d,
)
from shared.geometry_sets import _config, geometry_id, sample  # noqa: E402
from shared.ingestion import SurfaceBlock  # noqa: E402
from shared.qc import orient_blocks_consistently, qc_blocks  # noqa: E402

Array = np.ndarray

STRATEGY_ID = "S6_BOUNDED_MESH_ATLAS"


@dataclass(frozen=True)
class LevelSpec:
    chord_points: int
    end_points: int
    collar_points: int
    span_cells: int
    dense_curve_points: int
    span_max_cell_m: float


LEVELS: dict[str, LevelSpec] = {
    "candidate_c01": LevelSpec(17, 3, 5, 42, 801, 0.025),
    "candidate_c02": LevelSpec(23, 4, 7, 56, 1001, 0.018),
    "candidate_c03": LevelSpec(29, 5, 9, 74, 1201, 0.014),
    "coarse": LevelSpec(25, 3, 5, 63, 801, 0.020),
    "smoke": LevelSpec(33, 3, 7, 89, 1001, 0.015),
    "medium": LevelSpec(49, 4, 9, 127, 1201, 0.010),
    "fine": LevelSpec(65, 5, 13, 179, 1601, 0.008),
}


@dataclass(frozen=True)
class SectionFrame:
    le: Array
    te: Array
    chord_axis: Array
    thickness_axis: Array
    chord: float
    target_te: float
    half_te_opening_m: float


def build_pygeo_case(set_name: str, index: int, output_dir: Path):
    """Build one locked geometry with pyGeo as the master realization."""
    from aeris.geometry.registry import get_geometry_generator

    smp = sample(set_name, index)
    return get_geometry_generator("bwb_segmented").run_full_case(
        sample=smp,
        config=_config(),
        output_dir=Path(output_dir),
        save_plot=False,
        build_aerosandbox=False,
    )


def _unit(vector: Array, label: str) -> Array:
    magnitude = float(np.linalg.norm(vector))
    if not np.isfinite(magnitude) or magnitude <= 1.0e-14:
        raise ValueError(f"degenerate {label}: {vector}")
    return np.asarray(vector, dtype=float) / magnitude


def _surface_points(surface: Any, u: Array, v: float) -> Array:
    vv = np.full_like(u, float(v), dtype=float)
    points = np.asarray(surface(u, vv), dtype=float)
    if points.shape != (len(u), 3):
        points = points.reshape(len(u), 3)
    return points


def _frame_and_opened_curves(
    pygeo: Any,
    v: float,
    *,
    dense_points: int,
    te_abs_m: float,
    te_floor_frac: float,
) -> tuple[Array, Array, Array, SectionFrame]:
    """Sample one exact pyGeo section and apply the declared CFD-safe TE law."""
    u = np.linspace(0.0, 1.0, dense_points)
    upper = _surface_points(pygeo.surfs[0], u, v)
    lower = _surface_points(pygeo.surfs[1], u, v)

    te = 0.5 * (upper[0] + lower[0])
    le = 0.5 * (upper[-1] + lower[-1])
    chord_axis = _unit(te - le, "section chord axis")
    chord = float(np.linalg.norm(te - le))

    separation = upper - lower
    thick_index = int(np.argmax(np.linalg.norm(separation, axis=1)))
    thickness_direction = separation[thick_index]
    thickness_direction = thickness_direction - (thickness_direction @ chord_axis) * chord_axis
    thickness_axis = _unit(thickness_direction, "section thickness axis")
    target_te = max(float(te_abs_m), float(te_floor_frac) * chord)
    current_te = float(np.linalg.norm(upper[0] - lower[0]))
    half_added = 0.5 * max(0.0, target_te - current_te)

    xhat = np.clip((upper - le) @ chord_axis / max(chord, 1.0e-14), 0.0, 1.0)
    upper = upper + half_added * xhat[:, None] * thickness_axis
    xhat_lower = np.clip((lower - le) @ chord_axis / max(chord, 1.0e-14), 0.0, 1.0)
    lower = lower - half_added * xhat_lower[:, None] * thickness_axis
    frame = SectionFrame(
        le,
        te,
        chord_axis,
        thickness_axis,
        chord,
        target_te,
        half_added,
    )
    return u, upper, lower, frame


def _opened_points_at_u(
    pygeo: Any,
    u: Array,
    v: float,
    *,
    frame: SectionFrame,
    upper: bool,
) -> Array:
    """Independently evaluate the declared CFD surface at exact parameters."""
    points = _surface_points(pygeo.surfs[0 if upper else 1], u, v)
    xhat = np.clip(
        (points - frame.le) @ frame.chord_axis / max(frame.chord, 1.0e-14),
        0.0,
        1.0,
    )
    sign = 1.0 if upper else -1.0
    return points + sign * frame.half_te_opening_m * xhat[:, None] * frame.thickness_axis


def _u_at_xfrac(points: Array, u: Array, frame: SectionFrame, xfrac: float) -> float:
    xhat = (points - frame.le) @ frame.chord_axis / frame.chord
    order = np.argsort(xhat)
    return float(np.interp(float(xfrac), xhat[order], u[order]))


def _point_at_u(points: Array, u: Array, value: float) -> Array:
    return np.array([np.interp(value, u, points[:, axis]) for axis in range(3)])


def _resample_polyline_with_parameter(
    points: Array, parameter: Array, count: int
) -> tuple[Array, Array, Array]:
    points = np.asarray(points, dtype=float)
    parameter = np.asarray(parameter, dtype=float)
    if count < 2 or len(points) < 2:
        raise ValueError("a curve needs at least two source and target points")
    if parameter.shape != (len(points),):
        raise ValueError("curve parameter must have one value per source point")
    distance = np.linalg.norm(np.diff(points, axis=0), axis=1)
    cumulative = np.concatenate([[0.0], np.cumsum(distance)])
    if cumulative[-1] <= 1.0e-14:
        raise ValueError("cannot resample a zero-length curve")
    target = np.linspace(0.0, cumulative[-1], count)
    sampled = np.column_stack([np.interp(target, cumulative, points[:, axis]) for axis in range(3)])
    sampled_parameter = np.interp(target, cumulative, parameter)
    return sampled, sampled_parameter, target


def surface_interface_report(
    blocks: list[SurfaceBlock], *, tolerance_m: float = 1.0e-8
) -> dict[str, Any]:
    """Verify the fixed S6 block graph before any volume work."""
    edges: list[dict[str, Any]] = []
    for block in blocks:
        xyz = np.asarray(block.xyz, dtype=float)
        for side, nodes in (
            ("i0", xyz[0]),
            ("i1", xyz[-1]),
            ("j0", xyz[:, 0]),
            ("j1", xyz[:, -1]),
        ):
            edges.append({"block": block.name, "side": side, "nodes": nodes})

    used: set[int] = set()
    pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(edges):
        if left_index in used:
            continue
        best: tuple[float, int, bool] | None = None
        for right_index in range(left_index + 1, len(edges)):
            if right_index in used or edges[right_index]["block"] == left["block"]:
                continue
            right_nodes = edges[right_index]["nodes"]
            if left["nodes"].shape != right_nodes.shape:
                continue
            direct = float(np.max(np.abs(left["nodes"] - right_nodes)))
            reverse = float(np.max(np.abs(left["nodes"] - right_nodes[::-1])))
            candidate = (direct, right_index, False)
            if reverse < direct:
                candidate = (reverse, right_index, True)
            if best is None or candidate[0] < best[0]:
                best = candidate
        if best is None or best[0] > tolerance_m:
            continue
        mismatch, right_index, reverse = best
        right = edges[right_index]
        used.update((left_index, right_index))
        pairs.append(
            {
                "left": f"{left['block']}:{left['side']}",
                "right": f"{right['block']}:{right['side']}",
                "reversed": reverse,
                "max_mismatch_m": mismatch,
            }
        )
    return {
        "paired_edge_count": len(pairs),
        "max_mismatch_m": max((pair["max_mismatch_m"] for pair in pairs), default=float("inf")),
        "pairs": pairs,
    }


def _segment_with_parameter(
    points: Array, u: Array, u0: float, u1: float, count: int
) -> tuple[Array, Array, Array]:
    lo, hi = min(u0, u1), max(u0, u1)
    mask = (u > lo) & (u < hi)
    interior = points[mask]
    interior_u = u[mask]
    if u1 < u0:
        interior = interior[::-1]
        interior_u = interior_u[::-1]
    curve = np.vstack([_point_at_u(points, u, u0), interior, _point_at_u(points, u, u1)])
    curve_u = np.concatenate([[u0], interior_u, [u1]])
    return _resample_polyline_with_parameter(curve, curve_u, count)


def _section_arcs(
    pygeo: Any,
    v: float,
    *,
    spec: LevelSpec,
    te_abs_m: float,
    te_floor_frac: float,
    end_scale: float,
) -> tuple[dict[str, Array], dict[str, Any]]:
    """Return the six S1-compatible OML arcs directly on the pyGeo loft."""
    u, upper, lower, frame = _frame_and_opened_curves(
        pygeo,
        v,
        dense_points=spec.dense_curve_points,
        te_abs_m=te_abs_m,
        te_floor_frac=te_floor_frac,
    )
    outer_nose_xfrac = 0.5 * float(end_scale) * NOSE_END_FRAC
    u_mid_upper = _u_at_xfrac(upper, u, frame, 0.5)
    u_mid_lower = _u_at_xfrac(lower, u, frame, 0.5)
    u_nose_upper = _u_at_xfrac(upper, u, frame, outer_nose_xfrac)
    u_nose_lower = _u_at_xfrac(lower, u, frame, outer_nose_xfrac)

    nose_source_count = max(41, spec.dense_curve_points // 8)
    upper_nose, upper_nose_u, upper_nose_distance = _segment_with_parameter(
        upper, u, u_nose_upper, 1.0, nose_source_count
    )
    lower_nose, lower_nose_u, _lower_nose_distance = _segment_with_parameter(
        lower, u, 1.0, u_nose_lower, nose_source_count
    )
    nose_source = np.vstack([upper_nose, lower_nose[1:]])
    nose_source_u = np.concatenate([upper_nose_u, lower_nose_u[1:]])
    nose, nose_u, nose_distance = _resample_polyline_with_parameter(
        nose_source, nose_source_u, spec.end_points
    )

    upper_aft, upper_aft_u, _ = _segment_with_parameter(
        upper, u, 0.0, u_mid_upper, spec.chord_points
    )
    upper_fore, upper_fore_u, _ = _segment_with_parameter(
        upper, u, u_mid_upper, u_nose_upper, spec.chord_points
    )
    lower_fore, lower_fore_u, _ = _segment_with_parameter(
        lower, u, u_nose_lower, u_mid_lower, spec.chord_points
    )
    lower_aft, lower_aft_u, _ = _segment_with_parameter(
        lower, u, u_mid_lower, 0.0, spec.chord_points
    )

    outer = {
        "upper_aft": upper_aft,
        "upper_fore": upper_fore,
        "nose": nose,
        "lower_fore": lower_fore,
        "lower_aft": lower_aft,
        "base": np.linspace(lower[0], upper[0], spec.end_points),
    }

    independent_reference = {
        "upper_aft": _opened_points_at_u(pygeo, upper_aft_u, v, frame=frame, upper=True),
        "upper_fore": _opened_points_at_u(pygeo, upper_fore_u, v, frame=frame, upper=True),
        "lower_fore": _opened_points_at_u(pygeo, lower_fore_u, v, frame=frame, upper=False),
        "lower_aft": _opened_points_at_u(pygeo, lower_aft_u, v, frame=frame, upper=False),
        "base": outer["base"].copy(),
    }
    nose_reference = np.empty_like(nose)
    nose_on_upper = nose_distance <= upper_nose_distance[-1] + 1.0e-14
    nose_reference[nose_on_upper] = _opened_points_at_u(
        pygeo,
        nose_u[nose_on_upper],
        v,
        frame=frame,
        upper=True,
    )
    nose_reference[~nose_on_upper] = _opened_points_at_u(
        pygeo,
        nose_u[~nose_on_upper],
        v,
        frame=frame,
        upper=False,
    )
    independent_reference["nose"] = nose_reference
    fidelity_by_arc_m = {
        key: float(np.max(np.linalg.norm(outer[key] - independent_reference[key], axis=1)))
        for key in ARC_ORDER
    }
    fidelity_max_m = max(fidelity_by_arc_m.values())
    return outer, {
        "frame": frame,
        "u": u,
        "upper": upper,
        "lower": lower,
        "outer_nose_xfrac": outer_nose_xfrac,
        "construction_fidelity_by_arc_m": fidelity_by_arc_m,
        "construction_fidelity_max_m": fidelity_max_m,
        "construction_fidelity_max_frac": fidelity_max_m / frame.chord,
    }


def _tip_clustered_parameters(
    pygeo: Any,
    *,
    n_cells: int,
    first_cell_m: float,
    max_cell_m: float,
) -> tuple[Array, float, float, float]:
    """Fixed-count span parameters with both tip matching and a size cap."""
    dense_v = np.linspace(0.0, 1.0, 4001)
    quarter = np.asarray(pygeo.surfs[0](np.full_like(dense_v, 0.5), dense_v), dtype=float).reshape(
        -1, 3
    )
    cumulative = np.concatenate(
        [[0.0], np.cumsum(np.linalg.norm(np.diff(quarter, axis=0), axis=1))]
    )
    span_length = float(cumulative[-1])
    if n_cells < 2 or max_cell_m <= 0.0:
        raise ValueError("span spacing needs at least two cells and a positive cap")
    if n_cells * max_cell_m < span_length:
        raise ValueError(
            f"{n_cells} span cells capped at {max_cell_m:g} m cannot cover "
            f"the {span_length:g} m quarter-chord line"
        )
    first_cell_m = float(np.clip(first_cell_m, 1.0e-6, span_length / n_cells))
    maximum_coverage = first_cell_m + (n_cells - 1) * max_cell_m
    if maximum_coverage <= span_length * (1.0 + 1.0e-12):
        raise ValueError(
            f"{n_cells} span cells with first={first_cell_m:g} m and "
            f"cap={max_cell_m:g} m cover at most {maximum_coverage:g} m, "
            f"below the {span_length:g} m quarter-chord line"
        )

    max_exponent = max(0.0, float(np.log(max_cell_m / first_cell_m)))

    def widths(log_ratio: float) -> Array:
        exponent = np.minimum(np.arange(n_cells) * log_ratio, max_exponent)
        return first_cell_m * np.exp(exponent)

    lo, hi = 0.0, max_exponent
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if float(widths(mid).sum()) < span_length:
            lo = mid
        else:
            hi = mid
    log_ratio = 0.5 * (lo + hi)
    ratio = float(np.exp(log_ratio))
    widths_tip_to_root = widths(log_ratio)
    widths_tip_to_root *= span_length / float(widths_tip_to_root.sum())
    arc_edges = np.concatenate([[0.0], np.cumsum(widths_tip_to_root[::-1])])
    arc_edges /= arc_edges[-1]
    v_edges = np.interp(arc_edges, cumulative / span_length, dense_v)
    v_edges[-1] = 1.0
    return v_edges, ratio, span_length, float(widths_tip_to_root.max())


def _tip_coordinates_2d(meta: dict[str, Any]) -> tuple[Array, int]:
    frame: SectionFrame = meta["frame"]

    def project(points: Array) -> Array:
        delta = points - frame.le
        return np.column_stack([delta @ frame.chord_axis, delta @ frame.thickness_axis])

    upper = project(meta["upper"])
    lower = project(meta["lower"])
    coords = np.vstack([upper, lower[-2::-1]])
    return coords, len(upper) - 1


def _map_tip_patch(patch: Array, frame: SectionFrame) -> Array:
    return (
        frame.le
        + patch[..., 0, None] * frame.chord_axis
        + patch[..., 1, None] * frame.thickness_axis
    )


def _attach_outer_edge(patch: Array, outer: Array) -> Array:
    """Replace whichever collar edge corresponds to the exact OML tip arc."""
    result = patch.copy()
    candidates = []
    for edge_index in (0, -1):
        edge = result[:, edge_index, :]
        candidates.append((float(np.max(np.linalg.norm(edge - outer, axis=1))), edge_index, False))
        candidates.append(
            (float(np.max(np.linalg.norm(edge - outer[::-1], axis=1))), edge_index, True)
        )
    _error, edge_index, reverse = min(candidates, key=lambda item: item[0])
    result[:, edge_index, :] = outer[::-1] if reverse else outer
    return result


def _smooth_tip_interiors(
    blocks: list[SurfaceBlock], *, iterations: int, relaxation: float = 0.35
) -> list[SurfaceBlock]:
    """Smooth tip-cap interiors while preserving every boundary/interface edge."""
    if iterations < 0:
        raise ValueError("tip smoothing iterations must be non-negative")
    if not 0.0 < relaxation <= 1.0:
        raise ValueError("tip smoothing relaxation must lie in (0, 1]")
    result = []
    for block in blocks:
        xyz = np.array(block.xyz, copy=True)
        if min(xyz.shape[:2]) > 2:
            for _ in range(iterations):
                old = xyz.copy()
                average = 0.25 * (
                    old[:-2, 1:-1]
                    + old[2:, 1:-1]
                    + old[1:-1, :-2]
                    + old[1:-1, 2:]
                )
                xyz[1:-1, 1:-1] = (
                    (1.0 - relaxation) * old[1:-1, 1:-1] + relaxation * average
                )
        result.append(SurfaceBlock(name=block.name, xyz=xyz, family=block.family))
    return result


def _tip_blocks(
    tip_meta: dict[str, Any],
    oml_arrays: dict[str, Array],
    *,
    spec: LevelSpec,
    end_scale: float,
) -> tuple[list[SurfaceBlock], dict[str, Any]]:
    coords, le_index = _tip_coordinates_2d(tip_meta)
    geom = section_geometry(
        coords,
        le_index,
        chord_points=spec.chord_points,
        end_points=spec.end_points,
        ratio=1.0,
        end_scale=end_scale,
    )
    frame: SectionFrame = tip_meta["frame"]
    for key in ARC_ORDER:
        exact = oml_arrays[key][:, -1, :]
        delta = exact - frame.le
        geom["outer"][key] = np.column_stack(
            [delta @ frame.chord_axis, delta @ frame.thickness_axis]
        )
    patches_2d, cap_info = tip_domains_2d(geom, collar_points=spec.collar_points)
    patches = [_map_tip_patch(patch, frame) for patch in patches_2d]
    blocks = [
        SurfaceBlock(name=name, xyz=patch, family="wall")
        for name, patch in zip(cap_info["block_names"], patches, strict=True)
    ]
    return blocks, cap_info


def build_surface(
    pygeo_result: Any,
    *,
    level: str = "smoke",
    te_abs_m: float = 0.001,
    te_floor_frac: float = 0.005,
    end_scale: float = 5.0,
    tip_first_cell_frac_of_tip_chord: float = 0.0045,
    span_cells: int | None = None,
    tip_surface_smoothing_iterations: int = 0,
) -> tuple[list[SurfaceBlock], dict[str, Any]]:
    """Build the exact-pyGeo S6 surface with fixed dimensions at each level."""
    if level not in LEVELS:
        raise KeyError(f"unknown level {level!r}; known: {sorted(LEVELS)}")
    spec = LEVELS[level]
    if span_cells is not None:
        if span_cells < 2:
            raise ValueError("span_cells must be at least 2")
        spec = replace(spec, span_cells=int(span_cells))
    pygeo = pygeo_result.pygeo.geometry

    _tip_arcs, tip_probe = _section_arcs(
        pygeo,
        1.0,
        spec=spec,
        te_abs_m=te_abs_m,
        te_floor_frac=te_floor_frac,
        end_scale=end_scale,
    )
    tip_frame: SectionFrame = tip_probe["frame"]
    first_cell_m = tip_first_cell_frac_of_tip_chord * tip_frame.chord
    span_fractions, span_ratio, span_length, realized_max_span_cell = _tip_clustered_parameters(
        pygeo,
        n_cells=spec.span_cells,
        first_cell_m=first_cell_m,
        max_cell_m=spec.span_max_cell_m,
    )

    columns: dict[str, list[Array]] = {key: [] for key in ARC_ORDER}
    tip_meta = None
    target_te_min = np.inf
    target_te_max = 0.0
    fidelity_max_m = 0.0
    fidelity_max_frac = 0.0
    fidelity_by_arc_m = {key: 0.0 for key in ARC_ORDER}
    for v in span_fractions:
        arcs, meta = _section_arcs(
            pygeo,
            float(v),
            spec=spec,
            te_abs_m=te_abs_m,
            te_floor_frac=te_floor_frac,
            end_scale=end_scale,
        )
        for key in ARC_ORDER:
            columns[key].append(arcs[key])
        target_te = float(meta["frame"].target_te)
        target_te_min = min(target_te_min, target_te)
        target_te_max = max(target_te_max, target_te)
        fidelity_max_m = max(fidelity_max_m, meta["construction_fidelity_max_m"])
        fidelity_max_frac = max(fidelity_max_frac, meta["construction_fidelity_max_frac"])
        for key, error_m in meta["construction_fidelity_by_arc_m"].items():
            fidelity_by_arc_m[key] = max(fidelity_by_arc_m[key], error_m)
        if v == span_fractions[-1]:
            tip_meta = meta

    oml_arrays = {key: np.stack(value, axis=1) for key, value in columns.items()}
    blocks = [
        SurfaceBlock(name=f"oml_{key}", xyz=oml_arrays[key], family="wall") for key in ARC_ORDER
    ]
    if tip_meta is None:
        raise RuntimeError("tip section was not built")
    tip_blocks, cap_info = _tip_blocks(tip_meta, oml_arrays, spec=spec, end_scale=end_scale)
    tip_blocks = _smooth_tip_interiors(
        tip_blocks, iterations=tip_surface_smoothing_iterations
    )
    cap_info["interior_smoothing"] = {
        "method": "constrained_laplacian_tip_cap_only",
        "iterations": int(tip_surface_smoothing_iterations),
        "relaxation": 0.35,
        "all_edges_fixed": True,
    }
    tip_normal = _unit(
        np.cross(tip_frame.chord_axis, tip_frame.thickness_axis),
        "tip-cap normal",
    )
    tip_planarity_max_m = max(
        float(np.max(np.abs((block.xyz - tip_frame.le) @ tip_normal))) for block in tip_blocks
    )
    fidelity_max_m = max(fidelity_max_m, tip_planarity_max_m)
    fidelity_max_frac = max(fidelity_max_frac, tip_planarity_max_m / tip_frame.chord)
    blocks.extend(tip_blocks)
    blocks, orientation = orient_blocks_consistently(blocks)
    qc = qc_blocks(blocks)
    interfaces = surface_interface_report(blocks)
    surface_failures: list[str] = []
    if interfaces["paired_edge_count"] != 20 or interfaces["max_mismatch_m"] > 1.0e-10:
        surface_failures.append("surface_block_interface_graph")
    if fidelity_max_frac > 1.0e-4:
        surface_failures.append("surface_fidelity")
    if surface_failures:
        qc["accepted_pre_pyhyp"] = False
        qc["failure_reasons"] = [
            *qc["failure_reasons"],
            *surface_failures,
        ]
    qc["surface_interfaces"] = interfaces

    info = {
        "strategy_id": STRATEGY_ID,
        "geometry_id": pygeo_result.geometry_id,
        "master_geometry": "direct pyGeo B-spline evaluation",
        "level": level,
        "level_spec": asdict(spec),
        "block_count": len(blocks),
        "dimension_signature": [(b.name, list(b.xyz.shape)) for b in blocks],
        "spanwise": {
            "cells": spec.span_cells,
            "first_cell_target_m": first_cell_m,
            "geometric_ratio_tip_to_root": span_ratio,
            "quarter_chord_length_m": span_length,
            "max_cell_target_m": spec.span_max_cell_m,
            "max_cell_realized_m": realized_max_span_cell,
            "fractions": span_fractions.tolist(),
        },
        "cfd_safe_te": {
            "law": "max(te_abs_m, te_floor_frac * local_chord)",
            "te_abs_m": te_abs_m,
            "te_floor_frac": te_floor_frac,
            "realized_min_m": target_te_min,
            "realized_max_m": target_te_max,
            "status": "declared numerical geometry; aerodynamic sensitivity required",
        },
        "tip": cap_info,
        "fidelity": {
            "reference": "CFD-safe pyGeo loft after the declared TE opening",
            "instrument": (
                "each OML node is independently re-evaluated on the pyGeo curve "
                "at its tracked parametric coordinate; the declared tip cap is "
                "checked against its exact plane"
            ),
            "span_columns_checked": len(span_fractions),
            "max_node_to_parametric_curve_m": fidelity_max_m,
            "max_fraction_of_local_chord": fidelity_max_frac,
            "oml_max_by_arc_m": fidelity_by_arc_m,
            "tip_planarity_max_m": tip_planarity_max_m,
            "limit_fraction_of_local_chord": 1.0e-4,
            "passed": fidelity_max_frac <= 1.0e-4,
        },
        "orientation": orientation,
        "surface_qc": qc,
    }
    return blocks, info


def build_locked_surface(
    set_name: str,
    index: int,
    output_dir: Path,
    *,
    level: str = "smoke",
    **kwargs: Any,
) -> tuple[list[SurfaceBlock], dict[str, Any], Any]:
    gid = geometry_id(set_name, index)
    case = build_pygeo_case(set_name, index, Path(output_dir) / gid / "geometry")
    if case.pygeo_result is None:
        raise RuntimeError("the canonical geometry config did not produce a pyGeo result")
    blocks, info = build_surface(case.pygeo_result, level=level, **kwargs)
    info["locked_set_id"] = gid
    info["design_sample"] = case.sample.to_dict()
    return blocks, info, case
