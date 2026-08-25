"""Bounded, fail-closed SU2 8.5 execution for the S7 Gmsh strategy.

This module intentionally does not schedule a campaign or run anything at
import time.  It accepts an already-audited native ``.su2`` mesh and creates
immutable attempt directories.  A second (and final) solve is permitted only
when it uses the digest-verified restart emitted by the immediately preceding
attempt.  This is deliberately narrower than the general :mod:`aeris` SU2
adapter: S7's marker names, physics, numerical method, and convergence gates
are preregistered in ``POLICY.yaml``.
"""

from __future__ import annotations

import csv
import json
import math
import shutil
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .common import (
    ATTEMPT_SCHEMA,
    POLICY_PATH,
    atomic_write_text,
    canonical_json,
    digest_manifest,
    execution_environment,
    finite_float,
    load_policy,
    read_json,
    require_development_set,
    run_logged,
    sha256_file,
    source_digest,
    tool_versions,
    verify_digest_manifest,
    verify_pinned_versions,
    write_json,
)

SU2_PIPELINE_SCHEMA = "aeris.s7.su2_pipeline.v1"
PIPELINE_REQUEST_SCHEMA = "aeris.s7.su2_pipeline_request.v1"
ATTEMPT_RESULT_SCHEMA = "aeris.s7.su2_attempt_result.v1"
WALL_MARKERS = ("wall_upper", "wall_lower", "wall_te", "wall_tip")
FARFIELD_MARKER = "farfield"
SYMMETRY_MARKER = "symmetry"
HISTORY_NAME = "history.csv"
SURFACE_NAME = "surface_flow.csv"
SURFACE_VTK_NAME = "surface_flow.vtk"
RESTART_NAME = "restart_flow.dat"
MAX_TIMEOUT_S = 24.0 * 60.0 * 60.0


def _normalise_header(value: str) -> str:
    """Return a comparison key robust to SU2 CSV spelling and quoting."""
    return "".join(
        character.lower() for character in value.strip().strip('"') if character.isalnum()
    )


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    """Read a SU2 CSV while tolerating comments and a UTF-8 BOM.

    Rows with the wrong width are retained as invalid rows rather than silently
    discarded.  Required evidence that cannot be parsed must fail a gate.
    """
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = [row for row in csv.reader(stream) if row and not row[0].lstrip().startswith("%")]
    if not rows:
        return [], []
    return [item.strip().strip('"') for item in rows[0]], rows[1:]


def _column(headers: Sequence[str], aliases: Iterable[str]) -> int | None:
    wanted = {_normalise_header(alias) for alias in aliases}
    for index, name in enumerate(headers):
        if _normalise_header(name) in wanted:
            return index
    return None


def _parse_float_column(
    rows: Sequence[Sequence[str]], index: int | None
) -> tuple[list[float], int]:
    if index is None:
        return [], len(rows)
    values: list[float] = []
    invalid = 0
    for row in rows:
        if len(row) <= index:
            invalid += 1
            values.append(float("nan"))
            continue
        try:
            values.append(float(row[index]))
        except ValueError:
            invalid += 1
            values.append(float("nan"))
    return values, invalid


def parse_su2_history(path: Path) -> dict[str, Any]:
    """Parse residual and aerodynamic histories without assuming column order."""
    headers, rows = _read_csv(path)
    residual_index = _column(headers, ("rms[Rho]", "RMS_RHO", "RMS_DENSITY", "Res_Rho"))
    coefficient_indices = {
        "CL": _column(headers, ("CL", "C_L", "CLift", "Lift_Coefficient")),
        "CD": _column(headers, ("CD", "C_D", "CDrag", "Drag_Coefficient")),
        "CMy": _column(headers, ("CMy", "CM_Y", "CMOMENT_Y", "Moment_Y")),
    }
    residuals, residual_invalid = _parse_float_column(rows, residual_index)
    coefficients: dict[str, list[float]] = {}
    invalid_cells = residual_invalid
    for name, index in coefficient_indices.items():
        values, invalid = _parse_float_column(rows, index)
        coefficients[name] = values
        invalid_cells += invalid
    return {
        "path": str(Path(path).resolve()),
        "headers": headers,
        "row_count": len(rows),
        "residual_column": None if residual_index is None else headers[residual_index],
        "coefficient_columns": {
            name: None if index is None else headers[index]
            for name, index in coefficient_indices.items()
        },
        "residual_log10": residuals,
        "coefficients": coefficients,
        "invalid_cell_count": invalid_cells,
    }


def residual_gate(
    history: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    chain_initial_log10: float | None = None,
) -> dict[str, Any]:
    """Apply the frozen residual gate to one attempt or a restart chain."""
    limits = policy["su2"]["convergence"]
    values = np.asarray(history.get("residual_log10", []), dtype=float)
    row_count = int(history.get("row_count", 0))
    reasons: list[str] = []
    if row_count < int(limits["minimum_history_rows"]):
        reasons.append("fewer_than_minimum_history_rows")
    if history.get("residual_column") is None:
        reasons.append("missing_density_residual_column")
    if len(values) != row_count or not np.all(np.isfinite(values)):
        reasons.append("nonfinite_or_incomplete_density_residual")
    attempt_initial = float(values[0]) if len(values) and np.isfinite(values[0]) else None
    initial = attempt_initial
    initial_source = "attempt_history"
    if chain_initial_log10 is not None:
        if _finite(chain_initial_log10):
            initial = float(chain_initial_log10)
            initial_source = "freestream_chain_history"
        else:
            initial = None
            initial_source = "invalid_freestream_chain_history"
            reasons.append("nonfinite_chain_initial_residual")
    final = float(values[-1]) if len(values) and np.isfinite(values[-1]) else None
    orders = initial - final if initial is not None and final is not None else None
    if orders is None or orders < float(limits["residual_drop_orders_min"]):
        reasons.append("insufficient_residual_drop")
    if final is None or final > float(limits["residual_log10_final_max"]):
        reasons.append("final_residual_above_limit")
    return {
        "passed": not reasons,
        "row_count": row_count,
        "attempt_initial_log10": attempt_initial,
        "initial_log10": initial,
        "initial_source": initial_source,
        "final_log10": final,
        "orders_dropped": orders,
        "minimum_rows": int(limits["minimum_history_rows"]),
        "minimum_orders_dropped": float(limits["residual_drop_orders_min"]),
        "maximum_final_log10": float(limits["residual_log10_final_max"]),
        "failure_reasons": reasons,
    }


def force_tail_gate(history: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    """Require a finite, policy-sized CL/CD/CMy tail with bounded variation."""
    limits = policy["su2"]["convergence"]
    count = int(limits["force_tail_rows"])
    row_count = int(history.get("row_count", 0))
    ranges: dict[str, float | None] = {}
    relative_ranges: dict[str, float | None] = {}
    final_coefficients: dict[str, float | None] = {}
    reasons: list[str] = []
    if row_count < count:
        reasons.append("fewer_than_force_tail_rows")
    for name in ("CL", "CD", "CMy"):
        values = np.asarray(history.get("coefficients", {}).get(name, []), dtype=float)
        if history.get("coefficient_columns", {}).get(name) is None:
            reasons.append(f"missing_{name}_column")
            ranges[name] = None
            relative_ranges[name] = None
            final_coefficients[name] = None
            continue
        tail = values[-count:] if len(values) >= count else values
        if len(tail) != count or not np.all(np.isfinite(tail)):
            reasons.append(f"nonfinite_or_incomplete_{name}_tail")
            ranges[name] = None
            relative_ranges[name] = None
            final_coefficients[name] = None
            continue
        absolute_range = float(np.ptp(tail))
        denominator = max(
            abs(float(np.mean(tail))), float(limits["force_relative_denominator_floor"][name])
        )
        relative_range = absolute_range / denominator
        ranges[name] = absolute_range
        relative_ranges[name] = relative_range
        final_coefficients[name] = float(tail[-1])
        if relative_range > float(limits["force_tail_relative_range_max"][name]):
            reasons.append(f"unstable_{name}_tail")
    cd = final_coefficients.get("CD")
    if bool(limits["drag_must_be_positive"]) and (cd is None or cd <= 0.0):
        reasons.append("nonpositive_drag")
    return {
        "passed": not reasons,
        "tail_rows": count,
        "absolute_ranges": ranges,
        "relative_ranges": relative_ranges,
        "final_coefficients": final_coefficients,
        "relative_range_max": dict(limits["force_tail_relative_range_max"]),
        "denominator_floors": dict(limits["force_relative_denominator_floor"]),
        "failure_reasons": reasons,
    }


def read_surface_vtk_yplus(path: Path) -> dict[str, Any]:
    """Read per-point wall y+ from SU2's legacy-ASCII surface Paraview file.

    SU2 8.5 writes surface CSV without any PRIMITIVE field, so y+ is only
    available here.  The file holds wall points alone, so it stays small.  Point
    order matches the POINTS block, which is the same order the CSV uses, so the
    two can be cross-checked.
    """
    if not Path(path).is_file():
        # Absence must fail the gate closed, never raise: a solver that wrote no
        # surface file has produced no y+ evidence.
        return {
            "path": str(Path(path)),
            "point_count": None,
            "values": [],
            "complete": False,
            "missing": True,
        }
    text = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    point_count: int | None = None
    values: list[float] = []
    index = 0
    while index < len(text):
        line = text[index].strip()
        if line.upper().startswith("POINTS") and point_count is None:
            parts = line.split()
            if len(parts) >= 2:
                point_count = int(parts[1])
        # SCALARS <name> <type> [components]  then  LOOKUP_TABLE <name>
        if line.upper().startswith("SCALARS"):
            parts = line.split()
            if len(parts) >= 2 and _normalise_header(parts[1]) == "yplus":
                cursor = index + 1
                if cursor < len(text) and text[cursor].strip().upper().startswith(
                    "LOOKUP_TABLE"
                ):
                    cursor += 1
                while cursor < len(text) and len(values) < (point_count or 0):
                    stripped = text[cursor].strip()
                    if not stripped or stripped[0].isalpha():
                        break
                    for token in stripped.split():
                        try:
                            values.append(float(token))
                        except ValueError:
                            pass
                    cursor += 1
                break
        index += 1
    return {
        "path": str(Path(path).resolve()),
        "point_count": point_count,
        "values": values,
        "complete": point_count is not None and len(values) == point_count,
    }


def parse_surface_yplus(
    path: Path,
    *,
    expected_wall_point_indices: set[int] | None = None,
    vtk_path: Path | None = None,
) -> dict[str, Any]:
    """Read wall ``y+`` for the points the SU2 mesh declares as wall.

    SU2 8.5 omits every PRIMITIVE field from the surface CSV, so y+ is taken from
    the surface Paraview file when one is supplied.  The CSV still proves WHICH
    points were written, by native mesh point id, and the two must agree on
    count; the values are then aligned by row order, which is the order both
    writers use for the same marker set.
    """
    headers, rows = _read_csv(path)
    external = read_surface_vtk_yplus(vtk_path) if vtk_path is not None else None
    # "Y+" must NOT be listed: _normalise_header drops non-alphanumerics, so it
    # collapses to "y" and matches the y COORDINATE column.  Measured on the first
    # real run: wall y+ was reported as 1.135, which is the semi-span in metres.
    yplus_index = _column(headers, ("Y_PLUS", "YPLUS", "Wall_Y_Plus", "YPlus"))
    marker_index = _column(headers, ("MARKER", "MARKER_TAG", "BOUNDARY", "BOUNDARY_MARKER"))
    point_index = _column(
        headers,
        ("Global_Index", "GlobalIndex", "Point_ID", "PointID", "Node_ID", "NodeID"),
    )
    if yplus_index is None and not (external and external["complete"]):
        return {
            "path": str(Path(path).resolve()),
            "row_count": len(rows),
            "wall_row_count": 0,
            "yplus_column": None,
            "marker_column": None,
            "point_index_column": None,
            "values": [],
            "invalid_count": 0,
            "selection_proven": False,
        }
    if yplus_index is None:
        # y+ comes from the surface Paraview file; the CSV supplies the point
        # identity.  Both writers emit the same marker set in the same order, and
        # a count disagreement means that assumption broke, so fail closed.
        if external["point_count"] != len(rows):
            return {
                "path": str(Path(path).resolve()),
                "row_count": len(rows),
                "wall_row_count": 0,
                "yplus_column": None,
                "yplus_source": "surface_vtk",
                "marker_column": None,
                "point_index_column": None,
                "values": [],
                "invalid_count": len(rows),
                "selection_proven": False,
                "vtk_point_count": external["point_count"],
            }
    if marker_index is None and (point_index is None or expected_wall_point_indices is None):
        return {
            "path": str(Path(path).resolve()),
            "row_count": len(rows),
            "wall_row_count": 0,
            "yplus_column": headers[yplus_index],
            "marker_column": None,
            "point_index_column": None if point_index is None else headers[point_index],
            "values": [],
            "invalid_count": len(rows),
            "selection_proven": False,
        }
    values: list[float] = []
    invalid_count = 0
    wall_rows = 0
    observed_wall_points: set[int] = set()
    unexpected_wall_points = 0
    for row_position, row in enumerate(rows):
        required_indices = [] if yplus_index is None else [yplus_index]
        if expected_wall_point_indices is not None and point_index is not None:
            required_indices.append(point_index)
        elif marker_index is not None:
            required_indices.append(marker_index)
        if required_indices and len(row) <= max(required_indices):
            invalid_count += 1
            continue
        if expected_wall_point_indices is not None and point_index is not None:
            try:
                global_index = int(float(row[point_index]))
            except ValueError:
                invalid_count += 1
                continue
            if global_index not in expected_wall_point_indices:
                unexpected_wall_points += 1
                continue
            observed_wall_points.add(global_index)
        else:
            assert marker_index is not None
            marker = row[marker_index].strip().strip('"').lower()
            if marker not in WALL_MARKERS:
                continue
        wall_rows += 1
        if yplus_index is None:
            value = external["values"][row_position]
        else:
            try:
                value = float(row[yplus_index])
            except ValueError:
                invalid_count += 1
                continue
        if not math.isfinite(value) or value < 0.0:
            invalid_count += 1
            continue
        values.append(value)
    return {
        "path": str(Path(path).resolve()),
        "row_count": len(rows),
        "wall_row_count": wall_rows,
        "yplus_column": None if yplus_index is None else headers[yplus_index],
        "yplus_source": "surface_csv" if yplus_index is not None else "surface_vtk",
        "marker_column": None if marker_index is None else headers[marker_index],
        "point_index_column": None if point_index is None else headers[point_index],
        "values": values,
        "invalid_count": invalid_count,
        "selection_proven": True,
        "expected_wall_point_count": (
            None if expected_wall_point_indices is None else len(expected_wall_point_indices)
        ),
        "observed_wall_point_count": len(observed_wall_points),
        "wall_point_coverage_fraction": (
            None
            if expected_wall_point_indices is None
            else len(observed_wall_points) / len(expected_wall_point_indices)
        ),
        "unexpected_wall_point_count": unexpected_wall_points,
    }


def wall_yplus_gate(surface: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the frozen distribution gate; no missing CSV interpretation is benign."""
    limits = policy["su2"]["wall_y_plus"]
    values = np.asarray(surface.get("values", []), dtype=float)
    wall_rows = int(surface.get("wall_row_count", 0))
    valid_fraction = float(len(values) / wall_rows) if wall_rows else 0.0
    reasons: list[str] = []
    # y+ legitimately arrives from the surface Paraview file, because SU2 8.5
    # omits every PRIMITIVE field from the surface CSV.  Require a known source,
    # not a CSV column.
    if surface.get("yplus_column") is None and surface.get("yplus_source") != "surface_vtk":
        reasons.append("missing_yplus_source")
    if not surface.get("selection_proven", False):
        reasons.append("wall_row_selection_not_proven")
    expected_points = surface.get("expected_wall_point_count")
    if expected_points is not None:
        if surface.get("wall_point_coverage_fraction") != 1.0:
            reasons.append("incomplete_wall_point_coverage")
        if int(surface.get("unexpected_wall_point_count", 0)) != 0:
            reasons.append("unexpected_surface_points")
    if wall_rows == 0:
        reasons.append("no_required_wall_rows")
    if valid_fraction < float(limits["finite_wall_fraction_min"]):
        reasons.append("finite_wall_fraction_below_limit")
    statistics: dict[str, float] = {}
    if len(values):
        statistics = {
            "p95": float(np.percentile(values, 95)),
            "p99": float(np.percentile(values, 99)),
            "maximum": float(np.max(values)),
        }
        if statistics["p95"] > float(limits["p95_max"]):
            reasons.append("yplus_p95_above_limit")
        if statistics["p99"] > float(limits["p99_max"]):
            reasons.append("yplus_p99_above_limit")
        if statistics["maximum"] > float(limits["max_max"]):
            reasons.append("yplus_maximum_above_limit")
    else:
        reasons.append("no_finite_wall_yplus")
    return {
        "passed": not reasons,
        "wall_row_count": wall_rows,
        "finite_wall_count": len(values),
        "finite_wall_fraction": valid_fraction,
        "statistics": statistics,
        "limits": dict(limits),
        "failure_reasons": reasons,
    }


def _su2_mesh_markers(path: Path) -> list[str]:
    tags: list[str] = []
    with Path(path).open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if line.strip().upper().startswith("MARKER_TAG") and "=" in line:
                tags.append(line.split("=", 1)[1].strip())
    return tags


def _su2_wall_point_indices(path: Path) -> set[int]:
    """Return the exact native-mesh point IDs used by the four wall markers."""
    lines = [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines()]
    result: set[int] = set()
    cursor = 0
    while cursor < len(lines):
        if not lines[cursor].upper().startswith("MARKER_TAG"):
            cursor += 1
            continue
        marker = lines[cursor].split("=", 1)[1].strip()
        if cursor + 1 >= len(lines) or not lines[cursor + 1].upper().startswith("MARKER_ELEMS"):
            raise ValueError(f"malformed SU2 marker section for {marker!r}")
        count = int(lines[cursor + 1].split("=", 1)[1].strip())
        rows = lines[cursor + 2 : cursor + 2 + count]
        if len(rows) != count:
            raise ValueError(f"truncated SU2 marker section for {marker!r}")
        if marker in WALL_MARKERS:
            for row in rows:
                values = [int(value) for value in row.split()]
                if not values or values[0] != 5 or len(values) != 4:
                    raise ValueError(f"non-triangle wall row for {marker!r}: {row!r}")
                result.update(values[1:])
        cursor += 2 + count
    if not result:
        raise ValueError("SU2 mesh contains no wall points")
    return result


def fixed_su2_options(
    mesh_path: Path,
    *,
    flow: Mapping[str, Any],
    references: Mapping[str, Any],
    iterations: int,
    restart: bool,
) -> dict[str, Any]:
    """Resolve S7's fixed SU2 8.5 RANS-SA configuration.

    Values which vary by case are restricted to flow/reference quantities,
    mesh path, iteration budget, and the predeclared restart state.
    """
    policy = load_policy()
    numerical = policy["su2"]["numerical_method"]
    mesh_path = Path(mesh_path).resolve()
    # A mirrored mesh has no symmetry plane and a half mesh must have one; any
    # other marker set means the mesh is not what either domain produces.
    mirrored_markers = set((*WALL_MARKERS, FARFIELD_MARKER))
    half_markers = mirrored_markers | {SYMMETRY_MARKER}
    markers = _su2_mesh_markers(mesh_path)
    if set(markers) not in (mirrored_markers, half_markers):
        raise ValueError(
            "native SU2 mesh markers must equal "
            f"{sorted(mirrored_markers)} or {sorted(half_markers)}; "
            f"found {sorted(markers)}"
        )
    half_domain = SYMMETRY_MARKER in markers
    max_allowed = int(
        policy["su2"]["restart_extension_iterations"]
        if restart
        else policy["su2"]["max_iterations"]
    )
    if int(iterations) < 1 or int(iterations) > max_allowed:
        raise ValueError(f"iterations must be in [1, {max_allowed}] for this S7 solve")
    # Fail closed if the solver stop is ever moved back onto the acceptance bar.
    # A stop at the bar caps the achievable drop at initial + 8 and makes the
    # drop gate unsatisfiable, which is how two genuinely converged runs came to
    # be rejected.  See ADR-0017, residual-gate amendment 2026-08-25.
    convergence = policy["su2"]["convergence"]
    solver_stop = finite_float(
        convergence["solver_stop_residual_log10"], "su2.convergence.solver_stop_residual_log10"
    )
    required_stop = min(
        float(convergence["residual_log10_final_max"]),
        float(convergence["assumed_worst_initial_residual_log10"])
        - float(convergence["residual_drop_orders_min"]),
    )
    if solver_stop > required_stop:
        raise ValueError(
            "solver_stop_residual_log10 must sit at or below "
            f"{required_stop} so that both residual conditions remain reachable; "
            f"got {solver_stop}"
        )
    mach = finite_float(flow["mach"], "flow.mach")
    alpha = finite_float(flow["alpha"], "flow.alpha")
    reynolds = finite_float(flow["reynolds"], "flow.reynolds")
    temperature = finite_float(flow["temperature"], "flow.temperature")
    area = finite_float(references["area_ref"], "references.area_ref")
    if half_domain:
        # The reference values describe the whole wing regardless of what is
        # meshed - area_ref and span are identical for both domains - but SU2
        # integrates forces over the markers it is given, which on a half mesh is
        # half the wing. Dividing half the force by the whole area would report CL
        # and CD at exactly half their true value, and the run would look healthy
        # while doing it. Halving the reference here keeps the coefficients
        # comparable with the mirrored domain and with S6.
        area = 0.5 * area
    chord = finite_float(references["chord_ref"], "references.chord_ref")
    if mach <= 0.0 or reynolds <= 0.0 or temperature <= 0.0 or area <= 0.0 or chord <= 0.0:
        raise ValueError(
            "Mach, Reynolds, temperature, reference area, and reference chord must be > 0"
        )
    moment_origin = references.get("moment_origin", (0.0, 0.0, 0.0))
    if (
        not isinstance(moment_origin, Sequence)
        or isinstance(moment_origin, (str, bytes))
        or len(moment_origin) != 3
    ):
        raise ValueError("references.moment_origin must contain exactly three finite values")
    origin = tuple(finite_float(item, "references.moment_origin") for item in moment_origin)
    return {
        "SOLVER": "RANS",
        "KIND_TURB_MODEL": "SA",
        "MATH_PROBLEM": "DIRECT",
        "MESH_FORMAT": "SU2",
        "MESH_FILENAME": str(mesh_path),
        "RESTART_SOL": "YES" if restart else "NO",
        "RESTART_FILENAME": RESTART_NAME,
        "SOLUTION_FILENAME": RESTART_NAME,
        "MACH_NUMBER": mach,
        "AOA": alpha,
        "SIDESLIP_ANGLE": 0.0,
        "REYNOLDS_NUMBER": reynolds,
        "REYNOLDS_LENGTH": chord,
        "FREESTREAM_TEMPERATURE": temperature,
        "REF_AREA": area,
        "REF_LENGTH": chord,
        "REF_ORIGIN_MOMENT_X": origin[0],
        "REF_ORIGIN_MOMENT_Y": origin[1],
        "REF_ORIGIN_MOMENT_Z": origin[2],
        "MARKER_HEATFLUX": "( " + ", ".join(f"{name}, 0.0" for name in WALL_MARKERS) + " )",
        "MARKER_FAR": f"( {FARFIELD_MARKER} )",
        # Declared only when the mesh has one. SU2 treats an unlisted boundary as
        # a wall, so omitting this on a half mesh would put a viscous surface down
        # the centreline rather than a plane of symmetry.
        **({"MARKER_SYM": f"( {SYMMETRY_MARKER} )"} if half_domain else {}),
        "MARKER_MONITORING": "( " + ", ".join(WALL_MARKERS) + " )",
        "MARKER_PLOTTING": "( " + ", ".join(WALL_MARKERS) + " )",
        "CONV_NUM_METHOD_FLOW": str(numerical["conv_num_method_flow"]),
        "MUSCL_FLOW": "YES" if bool(numerical["muscl_flow"]) else "NO",
        "SLOPE_LIMITER_FLOW": str(numerical["slope_limiter_flow"]),
        "VENKAT_LIMITER_COEFF": finite_float(
            numerical["venkat_limiter_coeff"],
            "policy.su2.venkat_limiter_coeff",
        ),
        "TIME_DISCRE_FLOW": str(numerical["time_discre_flow"]),
        "CONV_NUM_METHOD_TURB": str(numerical["conv_num_method_turb"]),
        "MUSCL_TURB": "YES" if bool(numerical["muscl_turb"]) else "NO",
        "SLOPE_LIMITER_TURB": str(numerical["slope_limiter_turb"]),
        "TIME_DISCRE_TURB": str(numerical["time_discre_turb"]),
        "CFL_REDUCTION_TURB": finite_float(
            numerical["cfl_reduction_turb"], "policy.su2.cfl_reduction_turb"
        ),
        "LINEAR_SOLVER": str(numerical["linear_solver"]),
        "LINEAR_SOLVER_PREC": str(numerical["linear_solver_prec"]),
        "LINEAR_SOLVER_ERROR": finite_float(
            numerical["linear_solver_error"], "policy.su2.linear_solver_error"
        ),
        "LINEAR_SOLVER_ITER": int(numerical["linear_solver_iter"]),
        "CFL_NUMBER": finite_float(numerical["cfl_number"], "policy.su2.cfl_number"),
        "CFL_ADAPT": "YES" if bool(numerical["cfl_adapt"]) else "NO",
        "CFL_ADAPT_PARAM": "( "
        + ", ".join(
            str(finite_float(value, "policy.su2.cfl_adapt_param"))
            for value in numerical["cfl_adapt_param"]
        )
        + " )",
        "ITER": int(iterations),
        "CONV_FIELD": "RMS_DENSITY",
        # NOT residual_log10_final_max: stopping the solver at the acceptance bar
        # caps the achievable drop at initial + 8 and makes the drop gate
        # unsatisfiable.  See ADR-0017, residual-gate amendment 2026-08-25.
        "CONV_RESIDUAL_MINVAL": solver_stop,
        "CONV_STARTITER": int(policy["su2"]["convergence"]["minimum_history_rows"]),
        "TABULAR_FORMAT": "CSV",
        "HISTORY_OUTPUT": "( ITER, RMS_RES, AERO_COEFF )",
        # SU2 8.5's SURFACE_CSV writer emits only a restart-like field set:
        # measured, it carries COORDINATES and SOLUTION but no PRIMITIVE
        # fields, so no Y_PLUS.  The surface Paraview writer does carry them
        # and stays small because it holds wall points only (1 155 points,
        # 387 KB on the smoke mesh).  Both are written: the CSV keeps the
        # existing provenance, the VTK supplies wall y+.
        "OUTPUT_FILES": "( RESTART, SURFACE_CSV, SURFACE_PARAVIEW_ASCII )",
        "CONV_FILENAME": HISTORY_NAME.removesuffix(".csv"),
        "SURFACE_FILENAME": SURFACE_NAME.removesuffix(".csv"),
        # SU2 8.5 has no SURFACE_OUTPUT option; the surface CSV carries the
        # VOLUME_OUTPUT fields restricted to MARKER_PLOTTING.  Verified against
        # the v8.5.0 config template and rejected by the solver as an invalid
        # option name on the first real run.
        "VOLUME_OUTPUT": "( COORDINATES, SOLUTION, PRIMITIVE )",
        "OUTPUT_WRT_FREQ": f"( {int(iterations)}, {int(iterations)} )",
        "WRT_RESTART_OVERWRITE": "YES",
        "WRT_SURFACE_OVERWRITE": "YES",
    }


def render_su2_config(path: Path, options: Mapping[str, Any]) -> Path:
    """Write a deterministic native SU2 config, including option provenance."""
    lines = [
        "% S7 preregistered SU2 8.5 RANS-SA configuration.",
        "% Generated by su2_pipeline.py; do not hand-edit.",
    ]
    for key in sorted(options):
        lines.append(f"{key}= {options[key]}  % S7_POLICY")
    return atomic_write_text(Path(path), "\n".join(lines) + "\n")


def _next_attempt_dir(root: Path, phase: str) -> Path:
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    indices = []
    for candidate in root.glob("attempt_*"):
        pieces = candidate.name.split("_", 2)
        if len(pieces) >= 2 and pieces[1].isdigit():
            indices.append(int(pieces[1]))
    target = root / f"attempt_{max(indices, default=-1) + 1:03d}_{phase}"
    target.mkdir(exist_ok=False)
    return target


def _copy_input(source: Path, destination: Path) -> Path:
    source = Path(source).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    shutil.copy2(source, destination)
    if sha256_file(source) != sha256_file(destination):
        raise RuntimeError(f"copy digest mismatch: {source}")
    return destination


def _pipeline_request(
    *,
    mesh_path: Path,
    flow: Mapping[str, Any],
    references: Mapping[str, Any],
    geometry_set: str,
    evidence_tier: str,
    timeout_s: float,
    solver_command: Sequence[str],
    input_artifacts: Mapping[str, Path],
    initial_iterations: int,
) -> dict[str, Any]:
    """Canonical identity for a resumable solver root.

    Paths are intentionally excluded for copied scientific inputs: their
    content hashes make a campaign portable between desktop and HPC roots.
    The exact command and timeout remain part of the operational identity.
    """
    payload = {
        "schema": PIPELINE_REQUEST_SCHEMA,
        "source_digest": source_digest(),
        "policy_sha256": sha256_file(POLICY_PATH),
        "mesh_sha256": sha256_file(mesh_path),
        "flow": dict(flow),
        "references": dict(references),
        "geometry_set": geometry_set,
        "evidence_tier": evidence_tier,
        "timeout_s": float(timeout_s),
        "solver_command": [str(part) for part in solver_command],
        "initial_iterations": int(initial_iterations),
        "input_artifact_sha256": {
            name: sha256_file(Path(path)) for name, path in sorted(input_artifacts.items())
        },
    }
    # Round-trip through the canonical encoder so tuples/numpy scalars compare
    # identically after a JSON reload.
    value = json.loads(canonical_json(payload))
    assert isinstance(value, dict)
    return value


def _ensure_pipeline_request(root: Path, request: Mapping[str, Any]) -> Path:
    path = Path(root) / "pipeline_request.json"
    if path.is_file():
        stored = read_json(path)
        if canonical_json(stored) != canonical_json(dict(request)):
            raise RuntimeError("solver root belongs to a different mesh/flow/configuration request")
        return path
    occupied = any(Path(root).glob("attempt_*")) or any(
        (Path(root) / name).exists() for name in ("pipeline_result.json", "pipeline_terminal.json")
    )
    if occupied:
        raise RuntimeError("solver root has attempts/results but no immutable pipeline request")
    write_json(path, dict(request))
    return path


def _write_version_preflight(root: Path, report: Mapping[str, Any]) -> Path:
    directory = Path(root) / "software_preflights"
    directory.mkdir(parents=True, exist_ok=True)
    indices = [
        int(path.stem.rsplit("_", 1)[1])
        for path in directory.glob("preflight_*.json")
        if path.stem.rsplit("_", 1)[-1].isdigit()
    ]
    path = directory / f"preflight_{max(indices, default=-1) + 1:03d}.json"
    write_json(path, dict(report))
    return path


def _attempt_artifacts(
    attempt_dir: Path,
    *,
    input_artifacts: Mapping[str, Path],
) -> dict[str, Path]:
    return {
        "source_tree": attempt_dir / "source_tree.json",
        "policy": POLICY_PATH,
        "resolved_config": attempt_dir / "resolved_su2_config.json",
        "geometry": input_artifacts.get("geometry", attempt_dir / "MISSING_geometry"),
        "mesh": attempt_dir / "mesh.su2",
        "mesh_audit": input_artifacts.get("mesh_audit", attempt_dir / "MISSING_mesh_audit"),
        "su2_config": attempt_dir / "case.cfg",
        "su2_stdout": attempt_dir / "su2_stdout.log",
        "su2_history": attempt_dir / HISTORY_NAME,
        "su2_surface": attempt_dir / SURFACE_NAME,
        "restart": attempt_dir / RESTART_NAME,
        "result": attempt_dir / "attempt_result.json",
    }


def _run_one_attempt(
    *,
    root: Path,
    phase: str,
    source_mesh: Path,
    flow: Mapping[str, Any],
    references: Mapping[str, Any],
    iterations: int,
    timeout_s: float,
    solver_command: Sequence[str],
    input_artifacts: Mapping[str, Path] | None,
    restart_from: Path | None = None,
    restart_source_sha256: str | None = None,
    residual_chain_initial_log10: float | None = None,
) -> dict[str, Any]:
    policy = load_policy()
    if policy["su2"]["convergence"]["restart_file_required"] is not True:
        raise ValueError("S7 requires a restart artifact from every SU2 attempt")
    attempt = _next_attempt_dir(root, phase)
    mesh = _copy_input(source_mesh, attempt / "mesh.su2")
    copied_input_artifacts: dict[str, Path] = {}
    for name, source in (input_artifacts or {}).items():
        source = Path(source)
        suffix = "".join(source.suffixes)
        destination = attempt / f"input_{name}{suffix}"
        copied_input_artifacts[name] = _copy_input(source, destination)
    restart = restart_from is not None
    if restart:
        copied_restart = _copy_input(Path(restart_from), attempt / RESTART_NAME)
        if restart_source_sha256 is None or sha256_file(copied_restart) != restart_source_sha256:
            raise RuntimeError("restart digest verification failed before SU2 launch")
    options = fixed_su2_options(
        mesh, flow=flow, references=references, iterations=iterations, restart=restart
    )
    config = render_su2_config(attempt / "case.cfg", options)
    write_json(
        attempt / "resolved_su2_config.json",
        {
            "schema": SU2_PIPELINE_SCHEMA,
            "restart": restart,
            "options": options,
            "policy_sha256": sha256_file(POLICY_PATH),
        },
    )
    write_json(attempt / "source_tree.json", {"source_digest": source_digest()})
    command = [str(part) for part in solver_command] + [config.name]
    if not command or any(not part for part in command):
        raise ValueError("solver_command must be a nonempty sequence of nonempty arguments")
    run = run_logged(command, cwd=attempt, log_path=attempt / "su2_stdout.log", timeout_s=timeout_s)
    history_path = attempt / HISTORY_NAME
    surface_path = attempt / SURFACE_NAME
    parsed_history = parse_su2_history(history_path) if history_path.is_file() else None
    parsed_surface = (
        parse_surface_yplus(
            surface_path,
            expected_wall_point_indices=_su2_wall_point_indices(mesh),
            vtk_path=attempt / SURFACE_VTK_NAME,
        )
        if surface_path.is_file()
        else None
    )
    residual = (
        residual_gate(
            parsed_history,
            policy,
            chain_initial_log10=residual_chain_initial_log10,
        )
        if parsed_history is not None
        else {"passed": False, "failure_reasons": ["missing_history_csv"]}
    )
    forces = (
        force_tail_gate(parsed_history, policy)
        if parsed_history is not None
        else {"passed": False, "failure_reasons": ["missing_history_csv"]}
    )
    yplus = (
        wall_yplus_gate(parsed_surface, policy)
        if parsed_surface is not None
        else {"passed": False, "failure_reasons": ["missing_surface_csv"]}
    )
    restart_ok = (attempt / RESTART_NAME).is_file()
    process = {
        "passed": bool(
            run["return_code"] == int(policy["su2"]["convergence"]["process_exit_code"])
            and not run["timed_out"]
        ),
        "return_code": run["return_code"],
        "timed_out": run["timed_out"],
    }
    restart_gate = {
        "passed": restart_ok,
        "path": str((attempt / RESTART_NAME).resolve()),
        "sha256": sha256_file(attempt / RESTART_NAME) if restart_ok else None,
        "failure_reasons": [] if restart_ok else ["missing_restart"],
    }
    artifacts = _attempt_artifacts(attempt, input_artifacts=copied_input_artifacts)
    result = {
        "schema": ATTEMPT_RESULT_SCHEMA,
        "attempt_schema": ATTEMPT_SCHEMA,
        "phase": phase,
        "attempt_dir": str(attempt),
        "restart_input": None
        if restart_from is None
        else {
            "path": str(Path(restart_from).resolve()),
            "sha256": restart_source_sha256,
        },
        "run": run,
        "tool_versions": tool_versions(),
        "execution_environment": execution_environment(attempt),
        "gates": {
            "process": process,
            "residual": residual,
            "force_tail": forces,
            "wall_yplus": yplus,
            "restart": restart_gate,
        },
        "accepted_before_provenance": bool(
            process["passed"]
            and residual["passed"]
            and forces["passed"]
            and yplus["passed"]
            and restart_gate["passed"]
        ),
    }
    required = set(load_policy()["provenance"]["hash_required"])
    core_artifacts = {name: path for name, path in artifacts.items() if name != "result"}
    core_manifest = digest_manifest(core_artifacts, required=required - {"result"})
    core_verification = verify_digest_manifest(core_manifest)
    provenance = {
        "passed": bool(not core_manifest["missing_required"] and core_verification["passed"]),
        "scope": "all_required_attempt_artifacts_except_this_result_record",
        "manifest": core_manifest,
        "verification": core_verification,
    }
    result["artifact_provenance_gate"] = provenance
    result["accepted"] = bool(result["accepted_before_provenance"] and provenance["passed"])
    write_json(attempt / "attempt_result.json", result)
    manifest = digest_manifest(artifacts, required=required)
    verification = verify_digest_manifest(manifest)
    if not verification["passed"]:
        raise RuntimeError("final SU2 attempt artifact verification failed")
    write_json(
        attempt / "terminal_manifest.json",
        {
            "schema": ATTEMPT_SCHEMA,
            "source_digest": source_digest(),
            "policy_sha256": sha256_file(POLICY_PATH),
            "result": result,
            "artifact_manifest": manifest,
            "artifact_verification": verification,
        },
    )
    return result


def _load_completed_attempts(root: Path) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for attempt in sorted(Path(root).glob("attempt_*")):
        terminal_path = attempt / "terminal_manifest.json"
        if not terminal_path.is_file():
            raise RuntimeError(
                f"preserved incomplete SU2 attempt requires investigation: {attempt}"
            )
        terminal = read_json(terminal_path)
        if terminal.get("schema") != ATTEMPT_SCHEMA:
            raise ValueError(f"unsupported SU2 terminal manifest: {terminal_path}")
        if terminal.get("source_digest") != source_digest():
            raise RuntimeError(f"source digest changed since SU2 attempt: {attempt}")
        if terminal.get("policy_sha256") != sha256_file(POLICY_PATH):
            raise RuntimeError(f"policy digest changed since SU2 attempt: {attempt}")
        verification = verify_digest_manifest(terminal["artifact_manifest"])
        if not verification["passed"]:
            raise RuntimeError(
                f"SU2 attempt artifact verification failed for {attempt}: "
                f"{verification['mismatches']}"
            )
        result = terminal.get("result")
        if not isinstance(result, dict) or "accepted" not in result:
            raise ValueError(f"terminal SU2 result is incomplete: {terminal_path}")
        if Path(str(result.get("attempt_dir", ""))).resolve() != attempt.resolve():
            raise RuntimeError(f"SU2 terminal attempt path mismatch: {terminal_path}")
        attempts.append(result)
    return attempts


def _write_pipeline_result(
    root: Path,
    *,
    attempts: list[dict[str, Any]],
    evidence_tier: str,
    geometry_set: str,
    version_preflight: Mapping[str, Any],
    pipeline_request_path: Path,
    version_preflight_path: Path,
) -> dict[str, Any]:
    if not attempts:
        raise ValueError("cannot finalize an empty SU2 pipeline")
    final = attempts[-1]
    result = {
        "schema": SU2_PIPELINE_SCHEMA,
        "evidence_tier": evidence_tier,
        "geometry_set": geometry_set,
        "attempt_count": len(attempts),
        "automatic_restarts_used": sum(attempt.get("phase") == "restart" for attempt in attempts),
        "accepted": bool(final["accepted"]),
        "final_attempt": final,
        "attempts": attempts,
        "source_digest": source_digest(),
        "policy_sha256": sha256_file(POLICY_PATH),
        "pipeline_request_sha256": sha256_file(pipeline_request_path),
        "software_version_preflight": dict(version_preflight),
    }
    result_path = Path(root) / "pipeline_result.json"
    write_json(result_path, result)
    artifacts: dict[str, Path] = {
        "policy": POLICY_PATH,
        "pipeline_request": pipeline_request_path,
        "pipeline_result": result_path,
        "software_version_preflight": version_preflight_path,
    }
    for index, attempt in enumerate(attempts):
        artifacts[f"attempt_terminal_{index:03d}"] = (
            Path(str(attempt["attempt_dir"])) / "terminal_manifest.json"
        )
    manifest = digest_manifest(artifacts, required=artifacts)
    verification = verify_digest_manifest(manifest)
    if manifest["missing_required"] or not verification["passed"]:
        raise RuntimeError("pipeline terminal provenance verification failed")
    write_json(
        Path(root) / "pipeline_terminal.json",
        {
            "schema": SU2_PIPELINE_SCHEMA,
            "source_digest": source_digest(),
            "policy_sha256": sha256_file(POLICY_PATH),
            "pipeline_request_sha256": sha256_file(pipeline_request_path),
            "artifact_manifest": manifest,
            "artifact_verification": verification,
        },
    )
    return result


def run_su2_pipeline(
    *,
    attempts_root: Path,
    mesh_path: Path,
    flow: Mapping[str, Any],
    references: Mapping[str, Any],
    geometry_set: str,
    evidence_tier: str,
    timeout_s: float,
    solver_command: Sequence[str] = ("SU2_CFD",),
    input_artifacts: Mapping[str, Path] | None = None,
    initial_iterations: int | None = None,
) -> dict[str, Any]:
    """Run at most free-stream plus one verified-restart S7 SU2 attempt.

    ``production`` and ``holdout`` are intentionally rejected: this module is
    implementation plumbing and the preregistration authorizes no production
    solver launch.  Development calls remain subject to S7's holdout tripwire.
    """
    if evidence_tier not in {"unit", "laptop_smoke", "development"}:
        raise PermissionError(f"S7 SU2 pipeline refuses {evidence_tier!r} execution")
    require_development_set(geometry_set)
    timeout_s = finite_float(timeout_s, "timeout_s")
    if timeout_s <= 0.0 or timeout_s > MAX_TIMEOUT_S:
        raise ValueError(f"timeout_s must be in (0, {MAX_TIMEOUT_S}]")
    policy = load_policy()
    root = Path(attempts_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    artifacts = dict(input_artifacts or {})
    missing_inputs = sorted({"geometry", "mesh_audit"} - set(artifacts))
    if missing_inputs:
        raise ValueError(f"missing required SU2 input artifacts: {missing_inputs}")
    for name in ("geometry", "mesh_audit"):
        if not Path(artifacts[name]).is_file():
            raise FileNotFoundError(artifacts[name])
    mesh_path = Path(mesh_path).resolve()
    mesh_audit = read_json(Path(artifacts["mesh_audit"]))
    if mesh_audit.get("acceptance", {}).get("accepted") is not True:
        raise PermissionError("SU2 launch requires an accepted S7 mesh audit")
    if mesh_audit.get("mesh_su2_sha256") != sha256_file(mesh_path):
        raise RuntimeError("SU2 mesh digest does not match the accepted mesh audit")
    default_iterations = (
        int(policy["laptop_smoke"]["su2_iterations"])
        if evidence_tier in {"unit", "laptop_smoke"}
        else int(policy["su2"]["max_iterations"])
    )
    requested_initial_iterations = (
        default_iterations if initial_iterations is None else int(initial_iterations)
    )
    request_path = _ensure_pipeline_request(
        root,
        _pipeline_request(
            mesh_path=mesh_path,
            flow=flow,
            references=references,
            geometry_set=geometry_set,
            evidence_tier=evidence_tier,
            timeout_s=timeout_s,
            solver_command=solver_command,
            input_artifacts=artifacts,
            initial_iterations=requested_initial_iterations,
        ),
    )
    require_solver_identity = any(Path(str(part)).name == "SU2_CFD" for part in solver_command)
    version_preflight = verify_pinned_versions(
        require_su2=require_solver_identity,
        raise_on_mismatch=False,
    )
    version_preflight_path = _write_version_preflight(root, version_preflight)
    if not version_preflight["passed"]:
        raise RuntimeError(
            "software version preflight failed: " + "; ".join(version_preflight["mismatches"])
        )
    existing = _load_completed_attempts(root)
    summary_path = root / "pipeline_result.json"
    if summary_path.is_file():
        terminal_path = root / "pipeline_terminal.json"
        if not terminal_path.is_file():
            raise RuntimeError("stored SU2 pipeline result has no terminal manifest")
        terminal = read_json(terminal_path)
        if (
            terminal.get("source_digest") != source_digest()
            or terminal.get("policy_sha256") != sha256_file(POLICY_PATH)
            or terminal.get("pipeline_request_sha256") != sha256_file(request_path)
        ):
            raise RuntimeError("stored SU2 pipeline terminal is stale")
        terminal_verification = verify_digest_manifest(terminal.get("artifact_manifest", {}))
        if not terminal_verification["passed"]:
            raise RuntimeError(
                "stored SU2 pipeline provenance failed: "
                + ", ".join(terminal_verification["mismatches"])
            )
        summary = read_json(summary_path)
        if summary.get("source_digest") != source_digest() or summary.get(
            "policy_sha256"
        ) != sha256_file(POLICY_PATH):
            raise RuntimeError("stored SU2 pipeline result is stale")
        if int(summary.get("attempt_count", -1)) != len(existing):
            raise RuntimeError("stored SU2 pipeline attempt count is inconsistent")
        if summary.get("pipeline_request_sha256") != sha256_file(request_path):
            raise RuntimeError("stored SU2 pipeline request digest is inconsistent")
        return summary
    if len(existing) > 2:
        raise RuntimeError("SU2 attempt budget exceeded")
    if existing:
        attempts = existing
        first = attempts[0]
        if first.get("phase") != "freestream":
            raise RuntimeError("the first SU2 attempt is not a freestream attempt")
        if len(attempts) == 2:
            second = attempts[1]
            expected_restart_sha = first.get("gates", {}).get("restart", {}).get("sha256")
            if (
                first.get("accepted")
                or second.get("phase") != "restart"
                or second.get("restart_input", {}).get("sha256") != expected_restart_sha
            ):
                raise RuntimeError("stored SU2 restart chain is inconsistent")
    else:
        first = _run_one_attempt(
            root=root,
            phase="freestream",
            source_mesh=mesh_path,
            flow=flow,
            references=references,
            iterations=(requested_initial_iterations),
            timeout_s=timeout_s,
            solver_command=solver_command,
            input_artifacts=artifacts,
        )
        attempts = [first]
    can_restart = (
        not first["accepted"]
        and first["gates"]["process"]["passed"]
        and first["gates"]["restart"]["passed"]
        and int(policy["su2"]["max_automatic_restarts"]) == 1
    )
    if can_restart and len(attempts) == 1:
        restart_gate = first["gates"]["restart"]
        restart_iterations = (
            int(policy["laptop_smoke"]["su2_restart_iterations"])
            if evidence_tier in {"unit", "laptop_smoke"}
            else int(policy["su2"]["restart_extension_iterations"])
        )
        attempts.append(
            _run_one_attempt(
                root=root,
                phase="restart",
                source_mesh=mesh_path,
                flow=flow,
                references=references,
                iterations=restart_iterations,
                timeout_s=timeout_s,
                solver_command=solver_command,
                input_artifacts=artifacts,
                restart_from=Path(restart_gate["path"]),
                restart_source_sha256=str(restart_gate["sha256"]),
                residual_chain_initial_log10=first["gates"]["residual"].get("initial_log10"),
            )
        )
    return _write_pipeline_result(
        root,
        attempts=attempts,
        evidence_tier=evidence_tier,
        geometry_set=geometry_set,
        version_preflight=version_preflight,
        pipeline_request_path=request_path,
        version_preflight_path=version_preflight_path,
    )
