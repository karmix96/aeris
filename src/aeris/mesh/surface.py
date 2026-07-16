"""
Structured multiblock CGNS surface mesh builder for pyHyp.

Pipeline:
    AeroSandbox Wing
    -> 4 OML blocks + 4 tip-ring blocks + 1 tip-center block
    -> surface QC (connectivity, Jacobian, area, normal alignment)
    -> surface.cgns  (via cgnsUtilities)
    -> surface.fmt   (PLOT3D debug)
    -> surface.vtk   (ParaView preview)

Topology (mid-chord O-type):
    Block corners sit at x/c = split_x_fore and (1-split_x_fore) on both surfaces.
    The LE stagnation point and TE are inside block interiors, not at corners.
    This eliminates the degenerate-corner skewness that plagued the old split-at-LE design.

        oml_0  LE block   : upper x_fore → LE → lower x_fore
        oml_1  lower mid  : lower x_fore → lower x_aft
        oml_2  TE block   : lower x_aft  → TE  → upper x_aft
        oml_3  upper mid  : upper x_aft  → upper x_fore

    Half-wing, open root (symmetry boundary for pyHyp), blunt trailing edge required.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np

Array = np.ndarray

SURFACE_SCHEMA_VERSION = "aeris.asb_structured_surface.v2"


class MeshBuildError(RuntimeError):
    """Raised when the structured surface cannot be built safely."""


@dataclass(frozen=True)
class SurfaceBlock:
    name: str
    xyz: Array  # shape: (ni, nj, 3)
    family: str = "wall"


# ---------------------------------------------------------------------------
# Internal geometry helpers
# ---------------------------------------------------------------------------


def _as_numeric_xyz(values: object, *, label: str) -> Array:
    try:
        array = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise MeshBuildError(
            f"{label} is not purely numeric. Resolve all symbolic/CasADi values "
            "before CFD meshing."
        ) from exc
    if not np.all(np.isfinite(array)):
        raise MeshBuildError(f"{label} contains NaN or infinite coordinates.")
    return array


def _json_float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def select_wing(geometry: object, wing_index: int) -> object:
    """Return the AeroSandbox Wing at wing_index from an Airplane or Wing object."""
    if hasattr(geometry, "xsecs") and hasattr(geometry, "mesh_line"):
        if wing_index not in (0, -1):
            raise MeshBuildError("A Wing was returned, so wing_index must be 0.")
        return geometry

    wings = getattr(geometry, "wings", None)
    if wings is None:
        raise MeshBuildError(
            "Geometry must be an AeroSandbox Wing or Airplane-like object."
        )
    if not wings:
        raise MeshBuildError("The returned Airplane contains no wings.")
    try:
        return wings[wing_index]
    except IndexError as exc:
        raise MeshBuildError(
            f"wing_index {wing_index} is invalid; airplane has {len(wings)} wings."
        ) from exc


def airplane_summary(airplane: object, *, wing_index: int) -> dict[str, object]:
    wings = list(getattr(airplane, "wings", []) or [])
    if not wings:
        raise MeshBuildError("Generated AeroSandbox Airplane contains no wings.")
    try:
        wing = wings[wing_index]
    except IndexError as exc:
        raise MeshBuildError(
            f"wing_index {wing_index} is invalid; airplane has {len(wings)} wings."
        ) from exc

    xsecs = list(getattr(wing, "xsecs", []) or [])
    return {
        "name": str(getattr(airplane, "name", "unnamed")),
        "wing_count": len(wings),
        "selected_wing_index": int(wing_index),
        "selected_wing_name": str(getattr(wing, "name", f"wing_{wing_index}")),
        "selected_wing_symmetric": bool(getattr(wing, "symmetric", False)),
        "selected_wing_xsec_count": len(xsecs),
        "s_ref": _json_float_or_none(getattr(airplane, "s_ref", None)),
        "c_ref": _json_float_or_none(getattr(airplane, "c_ref", None)),
        "b_ref": _json_float_or_none(getattr(airplane, "b_ref", None)),
    }


def _polyline_arclength(points: Array) -> Array:
    delta = np.diff(points, axis=0)
    segment = np.linalg.norm(delta, axis=1)
    return np.concatenate(([0.0], np.cumsum(segment)))


def _resample_polyline(points: Array, n: int, *, cosine: bool = True) -> Array:
    points = _as_numeric_xyz(points, label="airfoil polyline")
    if points.ndim != 2 or points.shape[1] != 2:
        raise MeshBuildError("Airfoil polyline must have shape (N, 2).")
    if n < 2:
        raise MeshBuildError("Each structured side needs at least 2 points.")

    s = _polyline_arclength(points)
    keep = np.concatenate(([True], np.diff(s) > 1e-14))
    points = points[keep]
    s = s[keep]
    if len(points) < 2 or s[-1] <= 0:
        raise MeshBuildError("An airfoil boundary segment collapsed to zero length.")

    t = np.linspace(0.0, 1.0, n)
    if cosine:
        t = 0.5 * (1.0 - np.cos(np.pi * t))
    sample_s = t * s[-1]
    return np.column_stack(
        [np.interp(sample_s, s, points[:, axis]) for axis in range(2)]
    )


def _insert_point_at_x(surface: Array, x_target: float) -> tuple[Array, int]:
    x = surface[:, 0]
    candidates: list[tuple[int, float]] = []
    for i in range(len(surface) - 1):
        xa, xb = x[i], x[i + 1]
        if (xa - x_target) * (xb - x_target) <= 0 and not math.isclose(xa, xb):
            frac = (x_target - xa) / (xb - xa)
            if -1e-12 <= frac <= 1 + 1e-12:
                candidates.append((i, float(frac)))

    if candidates:
        i, frac = min(candidates, key=lambda item: abs(item[1] - 0.5))
        point = surface[i] + frac * (surface[i + 1] - surface[i])
        if np.linalg.norm(point - surface[i]) < 1e-13:
            return surface, i
        if np.linalg.norm(point - surface[i + 1]) < 1e-13:
            return surface, i + 1
        surface = np.insert(surface, i + 1, point, axis=0)
        return surface, i + 1

    idx = int(np.argmin(np.abs(x - x_target)))
    return surface, idx


def _airfoil_eight_sides(
    airfoil: object,
    *,
    points_per_side: int,
    dense_points_per_surface: int,
    split_x_fore: float,
    minimum_te_thickness: float,
) -> list[Array]:
    """Return 8 sides for a split LE/TE O-type topology.

    LE and TE remain inside block interiors, but the high-curvature wrap blocks
    are much narrower than the old 4-OML topology. This reduces the wall-normal
    fan seen by pyHyp without putting block corners exactly at the stagnation
    point.
    """
    split_x_aft = 1.0 - split_x_fore
    nose_x = max(0.02, 0.25 * split_x_fore)
    te_shoulder_x = 1.0 - nose_x

    try:
        working = airfoil.normalize().repanel(n_points_per_side=dense_points_per_surface)
    except AttributeError as exc:
        raise MeshBuildError(
            "Each WingXSec must contain an AeroSandbox Airfoil with normalize()/repanel()."
        ) from exc

    coords = _as_numeric_xyz(working.coordinates, label="airfoil coordinates")
    if coords.ndim != 2 or coords.shape[1] != 2 or len(coords) < 9:
        raise MeshBuildError("Airfoil coordinates must have shape (N, 2), N >= 9.")

    le_index = int(np.argmin(coords[:, 0]))
    if le_index == 0 or le_index == len(coords) - 1:
        raise MeshBuildError(
            "Unexpected airfoil ordering: leading edge must lie between upper and lower TE points."
        )

    upper_te_to_le = coords[: le_index + 1].copy()  # x: 1 -> 0
    lower_le_to_te = coords[le_index:].copy()       # x: 0 -> 1

    te_thickness = float(np.linalg.norm(upper_te_to_le[0] - lower_le_to_te[-1]))
    if te_thickness < minimum_te_thickness:
        raise MeshBuildError(
            f"Trailing edge thickness is {te_thickness:.3e} chord, below the required "
            f"{minimum_te_thickness:.3e}. Use a small blunt CFD trailing edge."
        )

    for x_target in (te_shoulder_x, split_x_aft, split_x_fore, nose_x):
        upper_te_to_le, _ = _insert_point_at_x(upper_te_to_le, x_target)
    for x_target in (nose_x, split_x_fore, split_x_aft, te_shoulder_x):
        lower_le_to_te, _ = _insert_point_at_x(lower_le_to_te, x_target)

    def idx_at_x(surface: Array, x_target: float) -> int:
        return int(np.argmin(np.abs(surface[:, 0] - x_target)))

    upper_te_shoulder_idx = idx_at_x(upper_te_to_le, te_shoulder_x)
    upper_aft_idx = idx_at_x(upper_te_to_le, split_x_aft)
    upper_fore_idx = idx_at_x(upper_te_to_le, split_x_fore)
    upper_nose_idx = idx_at_x(upper_te_to_le, nose_x)

    lower_nose_idx = idx_at_x(lower_le_to_te, nose_x)
    lower_fore_idx = idx_at_x(lower_le_to_te, split_x_fore)
    lower_aft_idx = idx_at_x(lower_le_to_te, split_x_aft)
    lower_te_shoulder_idx = idx_at_x(lower_le_to_te, te_shoulder_x)

    te_mid = 0.5 * (upper_te_to_le[0] + lower_le_to_te[-1])

    raw_sides = [
        upper_te_to_le[upper_fore_idx : upper_nose_idx + 1],
        np.vstack([
            upper_te_to_le[upper_nose_idx:],
            lower_le_to_te[1 : lower_nose_idx + 1],
        ]),
        lower_le_to_te[lower_nose_idx : lower_fore_idx + 1],
        lower_le_to_te[lower_fore_idx : lower_aft_idx + 1],
        lower_le_to_te[lower_aft_idx : lower_te_shoulder_idx + 1],
        np.vstack([
            lower_le_to_te[lower_te_shoulder_idx:],
            [te_mid],
            upper_te_to_le[: upper_te_shoulder_idx + 1],
        ]),
        upper_te_to_le[upper_te_shoulder_idx : upper_aft_idx + 1],
        upper_te_to_le[upper_aft_idx : upper_fore_idx + 1],
    ]

    sides = [_resample_polyline(side, points_per_side, cosine=False) for side in raw_sides]
    for k in range(len(sides)):
        nxt = (k + 1) % len(sides)
        if not np.allclose(sides[k][-1], sides[nxt][0], atol=1e-12):
            raise MeshBuildError("Internal error: airfoil side corners are disconnected.")
    return sides


def _airfoil_four_sides(
    airfoil: object,
    *,
    points_per_side: int,
    dense_points_per_surface: int,
    split_x_fore: float,
    minimum_te_thickness: float,
) -> list[Array]:
    split_x_aft = 1.0 - split_x_fore
    try:
        working = airfoil.normalize().repanel(n_points_per_side=dense_points_per_surface)
    except AttributeError as exc:
        raise MeshBuildError(
            "Each WingXSec must contain an AeroSandbox Airfoil with normalize()/repanel()."
        ) from exc
    coords = _as_numeric_xyz(working.coordinates, label="airfoil coordinates")
    if coords.ndim != 2 or coords.shape[1] != 2 or len(coords) < 9:
        raise MeshBuildError("Airfoil coordinates must have shape (N, 2), N >= 9.")
    le_index = int(np.argmin(coords[:, 0]))
    if le_index == 0 or le_index == len(coords) - 1:
        raise MeshBuildError(
            "Unexpected airfoil ordering: leading edge must lie between upper and lower TE points."
        )
    upper_te_to_le = coords[: le_index + 1].copy()
    lower_le_to_te = coords[le_index:].copy()
    te_thickness = float(np.linalg.norm(upper_te_to_le[0] - lower_le_to_te[-1]))
    if te_thickness < minimum_te_thickness:
        raise MeshBuildError(
            f"Trailing edge thickness is {te_thickness:.3e} chord, below the required "
            f"{minimum_te_thickness:.3e}. Use a small blunt CFD trailing edge."
        )
    upper_te_to_le, upper_aft_idx = _insert_point_at_x(upper_te_to_le, split_x_aft)
    upper_te_to_le, upper_fore_idx = _insert_point_at_x(upper_te_to_le, split_x_fore)
    lower_le_to_te, lower_fore_idx = _insert_point_at_x(lower_le_to_te, split_x_fore)
    lower_le_to_te, lower_aft_idx = _insert_point_at_x(lower_le_to_te, split_x_aft)
    te_mid = 0.5 * (upper_te_to_le[0] + lower_le_to_te[-1])
    raw_sides = [
        np.vstack([upper_te_to_le[upper_fore_idx:], lower_le_to_te[1 : lower_fore_idx + 1]]),
        lower_le_to_te[lower_fore_idx : lower_aft_idx + 1],
        np.vstack([lower_le_to_te[lower_aft_idx:], [te_mid], upper_te_to_le[: upper_aft_idx + 1]]),
        upper_te_to_le[upper_aft_idx : upper_fore_idx + 1],
    ]
    sides = [_resample_polyline(side, points_per_side, cosine=False) for side in raw_sides]
    for k in range(len(sides)):
        nxt = (k + 1) % len(sides)
        if not np.allclose(sides[k][-1], sides[nxt][0], atol=1e-12):
            raise MeshBuildError("Internal error: airfoil side corners are disconnected.")
    return sides

def _airfoil_cap4_sides(
    airfoil: object,
    *,
    wrap_points: int,
    chord_points: int,
    dense_points_per_surface: int,
    wrap_x: float,
    minimum_te_thickness: float,
) -> list[Array]:
    """Return 4 sides with per-side point counts for the cap4 topology.

    Corners sit near the LE and TE (x/c = wrap_x and 1-wrap_x): a narrow nose
    wrap and TE wrap carry ``wrap_points`` each, while the long upper/lower
    sides carry ``chord_points``.  This keeps surface cell size near-uniform
    around the airfoil — uniform-count topologies over-resolve the tiny LE/TE
    arcs, which is what makes the tip cap fold in pyHyp.
    """
    shoulder_x = 1.0 - wrap_x
    try:
        working = airfoil.normalize().repanel(n_points_per_side=dense_points_per_surface)
    except AttributeError as exc:
        raise MeshBuildError(
            "Each WingXSec must contain an AeroSandbox Airfoil with normalize()/repanel()."
        ) from exc
    coords = _as_numeric_xyz(working.coordinates, label="airfoil coordinates")
    if coords.ndim != 2 or coords.shape[1] != 2 or len(coords) < 9:
        raise MeshBuildError("Airfoil coordinates must have shape (N, 2), N >= 9.")
    le_index = int(np.argmin(coords[:, 0]))
    if le_index == 0 or le_index == len(coords) - 1:
        raise MeshBuildError(
            "Unexpected airfoil ordering: leading edge must lie between upper and lower TE points."
        )
    upper_te_to_le = coords[: le_index + 1].copy()
    lower_le_to_te = coords[le_index:].copy()
    te_thickness = float(np.linalg.norm(upper_te_to_le[0] - lower_le_to_te[-1]))
    if te_thickness < minimum_te_thickness:
        raise MeshBuildError(
            f"Trailing edge thickness is {te_thickness:.3e} chord, below the required "
            f"{minimum_te_thickness:.3e}. Use a small blunt CFD trailing edge."
        )
    upper_te_to_le, upper_shoulder_idx = _insert_point_at_x(upper_te_to_le, shoulder_x)
    upper_te_to_le, upper_nose_idx = _insert_point_at_x(upper_te_to_le, wrap_x)
    lower_le_to_te, lower_nose_idx = _insert_point_at_x(lower_le_to_te, wrap_x)
    lower_le_to_te, lower_shoulder_idx = _insert_point_at_x(lower_le_to_te, shoulder_x)
    te_mid = 0.5 * (upper_te_to_le[0] + lower_le_to_te[-1])
    raw_sides = [
        np.vstack([upper_te_to_le[upper_nose_idx:], lower_le_to_te[1 : lower_nose_idx + 1]]),
        lower_le_to_te[lower_nose_idx : lower_shoulder_idx + 1],
        np.vstack([lower_le_to_te[lower_shoulder_idx:], [te_mid], upper_te_to_le[: upper_shoulder_idx + 1]]),
        upper_te_to_le[upper_shoulder_idx : upper_nose_idx + 1],
    ]
    counts = [wrap_points, chord_points, wrap_points, chord_points]
    sides = [
        _resample_polyline(side, n, cosine=False)
        for side, n in zip(raw_sides, counts)
    ]
    for k in range(len(sides)):
        nxt = (k + 1) % len(sides)
        if not np.allclose(sides[k][-1], sides[nxt][0], atol=1e-12):
            raise MeshBuildError("Internal error: airfoil side corners are disconnected.")
    return sides


def _map_sides_to_wing(
    wing: object,
    sides_by_xsec: Sequence[Sequence[Array]],
) -> list[Array]:
    n_xsecs = len(sides_by_xsec)
    n_sides = len(sides_by_xsec[0])

    blocks: list[Array] = []
    for side_idx in range(n_sides):
        n_points = len(sides_by_xsec[0][side_idx])
        block = np.empty((n_points, n_xsecs, 3), dtype=float)
        for i in range(n_points):
            x_values = [sides_by_xsec[j][side_idx][i, 0] for j in range(n_xsecs)]
            z_values = [sides_by_xsec[j][side_idx][i, 1] for j in range(n_xsecs)]
            try:
                line = wing.mesh_line(x_nondim=x_values, z_nondim=z_values, add_camber=False)
            except Exception as exc:
                raise MeshBuildError(
                    f"AeroSandbox Wing.mesh_line() failed on side {side_idx}, point {i}."
                ) from exc
            line = _as_numeric_xyz(line, label="mapped wing line")
            if line.shape != (n_xsecs, 3):
                raise MeshBuildError(
                    f"Wing.mesh_line returned {line.shape}; expected {(n_xsecs, 3)}."
                )
            block[i, :, :] = line
        blocks.append(block)
    return blocks


def _coons_patch(
    bottom: Array,
    right: Array,
    top_q2_to_q3: Array,
    left_q3_to_q0: Array,
) -> Array:
    n = len(bottom)
    if not all(len(side) == n for side in (right, top_q2_to_q3, left_q3_to_q0)):
        raise MeshBuildError("Coons-patch sides must have equal point counts.")

    top = top_q2_to_q3[::-1]
    left = left_q3_to_q0[::-1]
    p00, p10, p11, p01 = bottom[0], bottom[-1], right[-1], left[-1]

    u = np.linspace(0.0, 1.0, n)
    v = np.linspace(0.0, 1.0, n)
    patch = np.empty((n, n, 3), dtype=float)

    for i, ui in enumerate(u):
        for j, vj in enumerate(v):
            blended_edges = (
                (1 - vj) * bottom[i]
                + vj * top[i]
                + (1 - ui) * left[j]
                + ui * right[j]
            )
            bilinear = (
                (1 - ui) * (1 - vj) * p00
                + ui * (1 - vj) * p10
                + ui * vj * p11
                + (1 - ui) * vj * p01
            )
            patch[i, j] = blended_edges - bilinear
    return patch


def _tfi_patch(bottom: Array, top: Array, left: Array, right: Array) -> Array:
    """General transfinite interpolation patch with rectangular index space.

    bottom/top run along the i-direction (nb points, same direction);
    left/right run along the j-direction (nm points, same direction).
    Consistency required: left[0]==bottom[0], left[-1]==top[0],
    right[0]==bottom[-1], right[-1]==top[-1].
    Returns an (nb, nm, 3) patch.
    """
    nb, nm = len(bottom), len(left)
    if len(top) != nb or len(right) != nm:
        raise MeshBuildError("TFI sides have inconsistent point counts.")
    for pair, name in (
        ((left[0], bottom[0]), "left/bottom"),
        ((left[-1], top[0]), "left/top"),
        ((right[0], bottom[-1]), "right/bottom"),
        ((right[-1], top[-1]), "right/top"),
    ):
        if not np.allclose(pair[0], pair[1], atol=1e-9):
            raise MeshBuildError(f"TFI corner mismatch at {name}.")

    u = np.linspace(0.0, 1.0, nb)[:, None, None]
    v = np.linspace(0.0, 1.0, nm)[None, :, None]
    b = bottom[:, None, :]
    t = top[:, None, :]
    lf = left[None, :, :]
    r = right[None, :, :]
    p00, p10, p01, p11 = bottom[0], bottom[-1], top[0], top[-1]
    patch = (
        (1 - v) * b + v * t + (1 - u) * lf + u * r
        - ((1 - u) * (1 - v) * p00 + u * (1 - v) * p10
           + (1 - u) * v * p01 + u * v * p11)
    )
    return patch


def _build_tip_cap4(
    oml_blocks: Sequence[Array],
    *,
    collar_points: int,
    width_frac: float,
) -> tuple[list[Array], list[Array], list[list[int]]]:
    """Camber-aligned tip cap for the cap4 topology.

    The OML tip edges are [nose wrap, lower, TE wrap, upper] with per-side
    point counts (wrap sides narrow, chord sides long).  The cap is:

    * an inner rectangle aligned with the tip-section camber line — a
      chordwise strip (n_chord x n_wrap) whose cell anisotropy matches the
      slender airfoil, and
    * four thin collar blocks of near-uniform width joining the rectangle to
      the tip edge (no long-side-to-short-side fans).
    """
    if len(oml_blocks) != 4:
        raise MeshBuildError("cap4 tip closure requires exactly 4 OML blocks.")
    if collar_points < 3:
        raise MeshBuildError("tip_radial_points (collar) must be at least 3.")
    if not (0.15 <= width_frac <= 0.85):
        raise MeshBuildError("cap_width_frac must lie between 0.15 and 0.85.")

    e_nose = oml_blocks[0][:, -1, :]   # upper corner -> LE -> lower corner
    e_low = oml_blocks[1][:, -1, :]    # nose -> shoulder (LE -> TE)
    e_te = oml_blocks[2][:, -1, :]     # lower shoulder -> te_mid -> upper shoulder
    e_up = oml_blocks[3][:, -1, :]     # shoulder -> nose (TE -> LE)
    n_wrap = len(e_nose)
    n_chord = len(e_low)
    if len(e_te) != n_wrap or len(e_up) != n_chord:
        raise MeshBuildError("cap4 tip edges have inconsistent point counts.")

    lower = e_low                       # nose -> te
    upper = e_up[::-1]                  # nose -> te

    # Inset the rectangle chordwise so the collar end edges slant from the
    # OML corners to the rectangle corners.  Without the inset, the end edges
    # are collinear with the rectangle's short sides (both at the wrap_x
    # station), which degenerates the corner cells to zero Jacobian.
    inset = 0.05
    idx = np.linspace(inset, 1.0 - inset, n_chord) * (n_chord - 1)
    lo_i = np.floor(idx).astype(int)
    hi_i = np.minimum(lo_i + 1, n_chord - 1)
    frac = (idx - lo_i)[:, None]

    def _at(arr: Array) -> Array:
        return (1.0 - frac) * arr[lo_i] + frac * arr[hi_i]

    lower_s = _at(lower)
    upper_s = _at(upper)
    camber = 0.5 * (upper_s + lower_s)
    rect_top = camber + width_frac * (upper_s - camber)
    rect_bot = camber + width_frac * (lower_s - camber)

    def straight(a: Array, b: Array, n: int) -> Array:
        t = np.linspace(0.0, 1.0, n)[:, None]
        return (1.0 - t) * a + t * b

    rect_left = straight(rect_top[0], rect_bot[0], n_wrap)     # upper -> lower
    rect_right = straight(rect_bot[-1], rect_top[-1], n_wrap)  # lower -> upper

    # Shared collar end edges (outer corner -> rectangle corner), collar_points each.
    end_up_nose = straight(e_nose[0], rect_top[0], collar_points)
    end_lo_nose = straight(e_nose[-1], rect_bot[0], collar_points)
    end_lo_te = straight(e_low[-1], rect_bot[-1], collar_points)
    end_up_te = straight(e_up[0], rect_top[-1], collar_points)

    # Collar blocks, indexed (along-edge, radial): [:, 0] = outer OML edge.
    collar_nose = _tfi_patch(end_up_nose, end_lo_nose, e_nose, rect_left)
    collar_nose = collar_nose.transpose(1, 0, 2)  # (n_wrap, collar_points, 3)
    collar_low = _tfi_patch(end_lo_nose, end_lo_te, e_low, rect_bot)
    collar_low = collar_low.transpose(1, 0, 2)
    collar_te = _tfi_patch(end_lo_te, end_up_te, e_te, rect_right)
    collar_te = collar_te.transpose(1, 0, 2)
    collar_up = _tfi_patch(end_up_te, end_up_nose, e_up, rect_top[::-1])
    collar_up = collar_up.transpose(1, 0, 2)

    center = _tfi_patch(rect_bot, rect_top, rect_left[::-1], rect_right)

    ring_blocks = [collar_nose, collar_low, collar_te, collar_up]
    center_patches = [center]
    tip_groups = [[0], [1], [2], [3]]
    return ring_blocks, center_patches, tip_groups


def _refine_spanwise(blocks: Sequence[Array], panels_per_section: int) -> list[Array]:
    if panels_per_section < 1:
        raise MeshBuildError("spanwise_panels_per_section must be at least 1.")
    refined: list[Array] = []
    for block in blocks:
        columns = []
        for j in range(block.shape[1] - 1):
            for k in range(panels_per_section):
                t = k / panels_per_section
                columns.append((1.0 - t) * block[:, j, :] + t * block[:, j + 1, :])
        columns.append(block[:, -1, :])
        refined.append(np.stack(columns, axis=1))
    return refined


def _apply_tip_dome(
    cap_blocks: Sequence[Array],
    boundary: Array,
    axis: Array,
    dome_scale: float,
) -> list[Array]:
    """Displace flat tip-cap points along the outward span axis into a dome.

    The displacement follows a quarter-circle profile h = R*sqrt(u*(2-u)) where
    u is the normalized inward distance from the cap boundary (u=0 on the OML
    tip edge, u=1 at the centroid).  The infinite slope at u=0 makes the cap
    G1-continuous (tangent) with the spanwise-running OML surface, eliminating
    the 90-degree normal discontinuity of a flat cap — the geometric feature
    that folds pyHyp's hyperbolic march when tip cells are small.

    R = dome_scale * (local cap half-thickness), estimated from the boundary's
    minor-axis extent in the tip plane, so the dome is geometry-adaptive.
    """
    axis = np.asarray(axis, dtype=float)
    axis = axis / np.linalg.norm(axis)
    center = np.mean(boundary, axis=0)

    # In-plane orthonormal basis (e1 = chordwise principal, e2 = thickness).
    q = boundary - center
    q_in = q - np.outer(q @ axis, axis)
    cov = q_in.T @ q_in
    eigvals, eigvecs = np.linalg.eigh(cov)
    e1 = eigvecs[:, -1]
    e2_dir = np.cross(axis, e1)
    e2_norm = np.linalg.norm(e2_dir)
    if e2_norm < 1e-14:
        return [block.copy() for block in cap_blocks]
    e2 = e2_dir / e2_norm

    xb = q_in @ e1
    zb = q_in @ e2
    half_thickness = 0.5 * float(np.ptp(zb))
    dome_height = dome_scale * half_thickness
    if dome_height <= 0.0:
        return [block.copy() for block in cap_blocks]

    # Polar boundary-radius table around the centroid (cap is star-shaped).
    phi_b = np.arctan2(zb, xb)
    r_b = np.hypot(xb, zb)
    order = np.argsort(phi_b)
    phi_sorted = phi_b[order]
    r_sorted = r_b[order]
    # wrap for periodic interpolation
    phi_ext = np.concatenate([phi_sorted - 2 * np.pi, phi_sorted, phi_sorted + 2 * np.pi])
    r_ext = np.concatenate([r_sorted, r_sorted, r_sorted])

    domed: list[Array] = []
    for block in cap_blocks:
        pts = block.reshape(-1, 3) - center
        p_in = pts - np.outer(pts @ axis, axis)
        px = p_in @ e1
        pz = p_in @ e2
        r = np.hypot(px, pz)
        phi = np.arctan2(pz, px)
        rb = np.interp(phi, phi_ext, r_ext)
        with np.errstate(divide="ignore", invalid="ignore"):
            u = np.clip(1.0 - np.divide(r, rb, out=np.ones_like(r), where=rb > 0), 0.0, 1.0)
        h = dome_height * np.sqrt(u * (2.0 - u))
        displaced = block.reshape(-1, 3) + h[:, None] * axis[None, :]
        domed.append(displaced.reshape(block.shape))
    return domed


def _build_tip_blocks(
    oml_blocks: Sequence[Array],
    *,
    radial_points: int,
    inner_scale: float,
    conformal_ring: bool = False,
) -> tuple[list[Array], list[Array], list[list[int]]]:
    if radial_points < 3:
        raise MeshBuildError("tip_radial_points must be at least 3.")
    if not (0.15 <= inner_scale <= 0.75):
        raise MeshBuildError("tip_inner_scale must be between 0.15 and 0.75.")
    if len(oml_blocks) not in (4, 8):
        raise MeshBuildError("Tip closure currently supports 4 or 8 OML blocks.")

    outer_sides = [block[:, -1, :].copy() for block in oml_blocks]
    unique_boundary = np.concatenate([side[:-1] for side in outer_sides], axis=0)
    center = np.mean(unique_boundary, axis=0)

    outer_corners = [side[0] for side in outer_sides]
    inner_corners = [center + inner_scale * (corner - center) for corner in outer_corners]
    inner_sides = []
    if conformal_ring:
        # Scaled copy of each curved outer side: the ring becomes a
        # uniform-width annulus (fan ratio = inner_scale everywhere), instead
        # of fanning a long curved LE/TE wrap down to a short straight chord —
        # the straight-chord fan produces collapsed sliver cells that fold
        # pyHyp at fine resolution.
        for outer in outer_sides:
            inner_sides.append(center + inner_scale * (outer - center))
    else:
        for k, outer in enumerate(outer_sides):
            q0 = inner_corners[k]
            q1 = inner_corners[(k + 1) % len(outer_sides)]
            side_t = np.linspace(0.0, 1.0, len(outer))[:, None]
            inner_sides.append((1.0 - side_t) * q0 + side_t * q1)

    radial_t = np.linspace(0.0, 1.0, radial_points)
    ring_blocks = []
    for outer, inner in zip(outer_sides, inner_sides):
        ring = np.empty((len(outer), radial_points, 3), dtype=float)
        for j, tj in enumerate(radial_t):
            ring[:, j, :] = (1 - tj) * outer + tj * inner
        ring_blocks.append(ring)

    if len(oml_blocks) == 4:
        center_patches = [
            _coons_patch(inner_sides[0], inner_sides[1], inner_sides[2], inner_sides[3])
        ]
        tip_groups = [[0], [1], [2], [3]]
        return ring_blocks, center_patches, tip_groups

    center_scale = 0.35
    center_corners = [
        center + center_scale * (inner_corners[idx] - center)
        for idx in (0, 2, 4, 6)
    ]

    center_patches = []
    tip_groups = [[idx] for idx in range(8)]
    for cap_idx in range(4):
        side_a = 2 * cap_idx
        side_b = (side_a + 1) % 8
        bottom = np.vstack([inner_sides[side_a], inner_sides[side_b][1:]])
        n = len(bottom)

        q0 = inner_corners[side_a]
        q1 = inner_corners[(side_a + 2) % 8]
        q2 = center_corners[(cap_idx + 1) % 4]
        q3 = center_corners[cap_idx]
        t = np.linspace(0.0, 1.0, n)[:, None]
        right = (1.0 - t) * q1 + t * q2
        top_q2_to_q3 = (1.0 - t) * q2 + t * q3
        left_q3_to_q0 = (1.0 - t) * q3 + t * q0
        center_patches.append(_coons_patch(bottom, right, top_q2_to_q3, left_q3_to_q0))

    return ring_blocks, center_patches, tip_groups

def _cell_geometry(block: Array) -> tuple[Array, Array, Array]:
    p00 = block[:-1, :-1]
    p10 = block[1:, :-1]
    p11 = block[1:, 1:]
    p01 = block[:-1, 1:]
    n1 = np.cross(p10 - p00, p11 - p00)
    n2 = np.cross(p11 - p00, p01 - p00)
    area = 0.5 * (np.linalg.norm(n1, axis=2) + np.linalg.norm(n2, axis=2))
    normal = n1 + n2
    center = 0.25 * (p00 + p10 + p11 + p01)
    return center, normal, area


def _orient_oml_blocks_outward(blocks: Sequence[Array]) -> list[Array]:
    section_centers = []
    for j in range(blocks[0].shape[1]):
        boundary = np.concatenate([block[:-1, j, :] for block in blocks], axis=0)
        section_centers.append(np.mean(boundary, axis=0))
    section_centers = np.asarray(section_centers)

    oriented = []
    for block in blocks:
        centers, normals, _ = _cell_geometry(block)
        reference = 0.5 * (section_centers[:-1] + section_centers[1:])
        radial = centers - reference[None, :, :]
        score = np.nanmedian(np.sum(normals * radial, axis=2))
        oriented.append(block[::-1, :, :].copy() if score < 0 else block.copy())
    return oriented


def _orient_tip_blocks_outward(
    blocks: Sequence[Array], outward_vector: Array
) -> list[Array]:
    outward_vector = outward_vector / np.linalg.norm(outward_vector)
    oriented = []
    for block in blocks:
        _, normals, _ = _cell_geometry(block)
        score = np.nanmedian(np.einsum("ijk,k->ij", normals, outward_vector))
        oriented.append(block[::-1, :, :].copy() if score < 0 else block.copy())
    return oriented


def _corner_scaled_jacobian(block: Array) -> Array:
    p00 = block[:-1, :-1]
    p10 = block[1:, :-1]
    p11 = block[1:, 1:]
    p01 = block[:-1, 1:]
    corners = [
        (p10 - p00, p01 - p00),
        (p11 - p10, p00 - p10),
        (p01 - p11, p10 - p11),
        (p00 - p01, p11 - p01),
    ]
    qualities = []
    for e1, e2 in corners:
        cross = np.linalg.norm(np.cross(e1, e2), axis=2)
        denom = np.sum(e1 * e1, axis=2) + np.sum(e2 * e2, axis=2)
        qualities.append(
            np.divide(2 * cross, denom, out=np.zeros_like(cross), where=denom > 0)
        )
    return np.min(np.stack(qualities, axis=0), axis=0)


def _block_qc(block: SurfaceBlock) -> dict[str, float | int | str]:
    xyz = block.xyz
    if xyz.ndim != 3 or xyz.shape[2] != 3:
        raise MeshBuildError(f"Block {block.name} must have shape (ni, nj, 3).")
    if xyz.shape[0] < 2 or xyz.shape[1] < 2:
        raise MeshBuildError(f"Block {block.name} has fewer than 2 points per direction.")

    _, normal, area = _cell_geometry(xyz)
    quality = _corner_scaled_jacobian(xyz)

    p00 = xyz[:-1, :-1]
    p10 = xyz[1:, :-1]
    p11 = xyz[1:, 1:]
    p01 = xyz[:-1, 1:]
    n1 = np.cross(p10 - p00, p11 - p00)
    n2 = np.cross(p11 - p00, p01 - p00)
    denom = np.linalg.norm(n1, axis=2) * np.linalg.norm(n2, axis=2)
    normal_alignment = np.divide(
        np.sum(n1 * n2, axis=2),
        denom,
        out=np.full_like(denom, -1.0),
        where=denom > 0,
    )

    normal_norm = np.linalg.norm(normal, axis=2)
    unit_normal = np.divide(
        normal,
        normal_norm[:, :, None],
        out=np.zeros_like(normal),
        where=normal_norm[:, :, None] > 0,
    )
    adjacent_normal_dot: list[Array] = []
    if unit_normal.shape[0] > 1:
        adjacent_normal_dot.append(
            np.sum(unit_normal[1:, :, :] * unit_normal[:-1, :, :], axis=2)
        )
    if unit_normal.shape[1] > 1:
        adjacent_normal_dot.append(
            np.sum(unit_normal[:, 1:, :] * unit_normal[:, :-1, :], axis=2)
        )
    if adjacent_normal_dot:
        min_adjacent_normal_dot = float(
            np.min([np.min(values) for values in adjacent_normal_dot])
        )
        max_adjacent_normal_angle_deg = float(
            np.degrees(np.arccos(np.clip(min_adjacent_normal_dot, -1.0, 1.0)))
        )
    else:
        max_adjacent_normal_angle_deg = 0.0

    return {
        "name": block.name,
        "ni": int(xyz.shape[0]),
        "nj": int(xyz.shape[1]),
        "nodes": int(xyz.shape[0] * xyz.shape[1]),
        "cells": int((xyz.shape[0] - 1) * (xyz.shape[1] - 1)),
        "min_area": float(np.min(area)),
        "median_area": float(np.median(area)),
        "min_scaled_corner_jacobian": float(np.min(quality)),
        "median_scaled_corner_jacobian": float(np.median(quality)),
        "min_triangle_normal_alignment": float(np.min(normal_alignment)),
        "median_triangle_normal_alignment": float(np.median(normal_alignment)),
        "max_adjacent_normal_angle_deg": max_adjacent_normal_angle_deg,
    }


def _edge_match(a: Array, b: Array, tol: float) -> bool:
    if a.shape != b.shape:
        return False
    return bool(
        np.allclose(a, b, atol=tol, rtol=0)
        or np.allclose(a, b[::-1], atol=tol, rtol=0)
    )


def _edge_contains_segment(edge: Array, segment: Array, tol: float) -> bool:
    if len(edge) < len(segment):
        return False
    candidates = [edge[: len(segment)], edge[-len(segment) :]]
    return any(_edge_match(candidate, segment, tol) for candidate in candidates)


def _connectivity_qc(
    oml: Sequence[SurfaceBlock],
    ring: Sequence[SurfaceBlock],
    center: Sequence[SurfaceBlock],
    tol: float,
    *,
    tip_groups: Sequence[Sequence[int]] | None = None,
) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    n_oml = len(oml)

    for k in range(n_oml):
        nxt = (k + 1) % n_oml
        a_edges = [oml[k].xyz[0, :, :], oml[k].xyz[-1, :, :]]
        b_edges = [oml[nxt].xyz[0, :, :], oml[nxt].xyz[-1, :, :]]
        matched = any(_edge_match(a, b, tol) for a in a_edges for b in b_edges)
        checks.append({"connection": f"oml_{k}_to_oml_{nxt}", "matched": matched})

    if tip_groups is None:
        tip_groups = [[i] for i in range(len(ring))]

    for ring_idx, group in enumerate(tip_groups):
        ring_outer_edges = [ring[ring_idx].xyz[:, 0, :], ring[ring_idx].xyz[::-1, 0, :]]
        for oml_idx in group:
            oml_tip_edges = [oml[oml_idx].xyz[:, -1, :], oml[oml_idx].xyz[::-1, -1, :]]
            matched = any(
                _edge_contains_segment(ring_edge, oml_edge, tol)
                for ring_edge in ring_outer_edges
                for oml_edge in oml_tip_edges
            )
            checks.append(
                {
                    "connection": f"oml_{oml_idx}_to_tip_ring_{ring_idx}",
                    "matched": matched,
                }
            )

    center_edges = []
    for block in center:
        center_edges.extend(
            [
                block.xyz[:, 0, :],
                block.xyz[-1, :, :],
                block.xyz[:, -1, :],
                block.xyz[0, :, :],
            ]
        )
    for k in range(len(ring)):
        ring_edges = [ring[k].xyz[:, 0, :], ring[k].xyz[:, -1, :]]
        matched = any(
            _edge_match(a, b, tol) or _edge_contains_segment(b, a, tol)
            for a in ring_edges
            for b in center_edges
        )
        checks.append({"connection": f"tip_ring_{k}_to_tip_center", "matched": matched})

    return {
        "tolerance": tol,
        "checks": checks,
        "all_matched": all(bool(item["matched"]) for item in checks),
    }

# ---------------------------------------------------------------------------
# File writers
# ---------------------------------------------------------------------------


def _write_plot3d_formatted(path: Path, blocks: Sequence[SurfaceBlock]) -> None:
    with path.open("w", encoding="ascii") as stream:
        stream.write(f"{len(blocks):12d}\n")
        dims: list[int] = []
        for block in blocks:
            ni, nj, _ = block.xyz.shape
            dims.extend([ni, nj, 1])
        for start in range(0, len(dims), 6):
            stream.write(
                "".join(f"{value:12d}" for value in dims[start : start + 6]) + "\n"
            )
        for block in blocks:
            for component in range(3):
                values = block.xyz[:, :, component].reshape(-1, order="F")
                for start in range(0, len(values), 3):
                    stream.write(
                        "".join(
                            f"{value:24.16E}" for value in values[start : start + 3]
                        )
                        + "\n"
                    )


def _write_cgns_structured_surface(
    path: Path, blocks: Sequence[SurfaceBlock]
) -> dict[str, object]:
    try:
        from cgnsutilities.cgnsutilities import Block, Grid, readGrid
    except (ImportError, ModuleNotFoundError) as exc:
        raise MeshBuildError(
            "CGNS export requires MDO Lab cgnsUtilities. "
            "Activate the mach-aero conda environment."
        ) from exc

    grid = Grid()
    grid.name = path.stem
    grid.cellDim = 2

    expected: list[dict[str, object]] = []
    for index, surface_block in enumerate(blocks, start=1):
        ni, nj, _ = surface_block.xyz.shape
        dims = np.asarray([ni, nj, 1], dtype=np.int32, order="F")
        coords = np.asfortranarray(
            surface_block.xyz[:, :, np.newaxis, :], dtype=np.float64
        )
        zone_name = f"{surface_block.name}.{index:05d}"
        grid.addBlock(Block(zone_name, dims, coords))
        expected.append({"name": zone_name, "dims": [int(ni), int(nj), 1]})

    grid.writeToCGNS(str(path))
    if not path.is_file() or path.stat().st_size == 0:
        raise MeshBuildError(f"cgnsUtilities did not create a valid file: {path}")

    check_grid = readGrid(str(path))
    if int(check_grid.cellDim) != 2:
        raise MeshBuildError(
            f"CGNS read-back reports cellDim={check_grid.cellDim}; expected 2."
        )
    if len(check_grid.blocks) != len(blocks):
        raise MeshBuildError(
            f"CGNS read-back block count {len(check_grid.blocks)} != {len(blocks)}."
        )

    # cgnsUtilities reads zones back sorted alphabetically, not in insertion
    # order, so verify by name lookup rather than by position.
    expected_by_name = {zone["name"]: zone["dims"] for zone in expected}
    readback = []
    for check_block in check_grid.blocks:
        dims = [int(value) for value in check_block.dims]
        expected_dims = expected_by_name.get(check_block.name)
        if expected_dims is None:
            raise MeshBuildError(
                f"CGNS read-back returned unexpected zone name {check_block.name!r}."
            )
        if dims != expected_dims:
            raise MeshBuildError(
                f"CGNS read-back dimensions for {check_block.name} are {dims}; "
                f"expected {expected_dims}."
            )
        readback.append({"name": check_block.name, "dims": dims})

    return {
        "cell_dimension": 2,
        "zone_count": len(blocks),
        "zones": readback,
        "connectivity_policy": "pyHyp autoConnect=True",
        "open_edge_policy": "pyHyp unattachedEdgesAreSymmetry=True",
    }


def _write_vtk(path: Path, blocks: Sequence[SurfaceBlock]) -> None:
    points: list[Array] = []
    faces: list[tuple[int, int, int, int]] = []
    offset = 0
    for block in blocks:
        ni, nj, _ = block.xyz.shape
        flat = block.xyz.reshape((-1, 3), order="F")
        points.append(flat)

        def idx(i: int, j: int, _ni: int = ni, _off: int = offset) -> int:
            return _off + i + _ni * j

        for j in range(nj - 1):
            for i in range(ni - 1):
                faces.append((idx(i, j), idx(i + 1, j), idx(i + 1, j + 1), idx(i, j + 1)))
        offset += len(flat)

    all_points = np.vstack(points)
    with path.open("w", encoding="ascii") as stream:
        stream.write("# vtk DataFile Version 3.0\n")
        stream.write("AeroSandbox structured surface blocks\n")
        stream.write("ASCII\nDATASET POLYDATA\n")
        stream.write(f"POINTS {len(all_points)} double\n")
        for point in all_points:
            stream.write(f"{point[0]:.16e} {point[1]:.16e} {point[2]:.16e}\n")
        stream.write(f"POLYGONS {len(faces)} {5 * len(faces)}\n")
        for face in faces:
            stream.write(f"4 {face[0]} {face[1]} {face[2]} {face[3]}\n")


def _write_npz(path: Path, blocks: Sequence[SurfaceBlock]) -> None:
    np.savez_compressed(path, **{block.name: block.xyz for block in blocks})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_surface_mesh(
    wing: object,
    *,
    points_per_block_side: int = 97,
    dense_airfoil_points_per_surface: int = 301,
    split_x_fore: float = 0.20,
    minimum_te_thickness: float = 2.0e-3,
    minimum_scaled_jacobian: float = 1.0e-2,
    maximum_adjacent_normal_angle_deg: float = 180.0,
    oml_topology: str = "mid4",
    spanwise_panels_per_section: int = 8,
    tip_radial_points: int = 9,
    tip_inner_scale: float = 0.60,
    tip_dome_scale: float = 0.0,
    tip_conformal_ring: bool = False,
    cap_wrap_points: int = 17,
    cap_wrap_x: float = 0.03,
    cap_width_frac: float = 0.5,
) -> tuple[list[SurfaceBlock], dict[str, object]]:
    """Build a 9-block structured surface mesh from an AeroSandbox Wing.

    split_x_fore sets the fore x/c split (aft = 1 - split_x_fore).  Block corners
    land on both surfaces at these two x/c values; the LE and TE sit in block
    interiors rather than at corners, eliminating degenerate-corner skewness.

    Returns (blocks, report). Raises MeshBuildError on QC failure.
    """
    xsecs = getattr(wing, "xsecs", None)
    if xsecs is None or len(xsecs) < 2:
        raise MeshBuildError("Wing must contain at least two WingXSec objects.")
    if points_per_block_side < 9:
        raise MeshBuildError("Use at least 9 points per block side.")
    if not (0.05 <= split_x_fore <= 0.45):
        raise MeshBuildError("split_x_fore must lie between 0.05 and 0.45.")
    if not (0.0 < minimum_scaled_jacobian < 1.0):
        raise MeshBuildError("minimum_scaled_jacobian must lie between 0 and 1.")
    if not (0.0 < maximum_adjacent_normal_angle_deg <= 180.0):
        raise MeshBuildError("maximum_adjacent_normal_angle_deg must lie between 0 and 180.")
    if oml_topology not in {"mid4", "split8", "cap4"}:
        raise MeshBuildError("oml_topology must be 'mid4', 'split8', or 'cap4'.")
    if not (0.0 <= tip_dome_scale <= 2.0):
        raise MeshBuildError("tip_dome_scale must lie between 0 (flat cap) and 2.")
    if oml_topology == "cap4":
        if cap_wrap_points < 5:
            raise MeshBuildError("cap_wrap_points must be at least 5.")
        if not (0.01 <= cap_wrap_x <= 0.15):
            raise MeshBuildError("cap_wrap_x must lie between 0.01 and 0.15.")

    if oml_topology == "cap4":
        sides_by_xsec = [
            _airfoil_cap4_sides(
                xsec.airfoil,
                wrap_points=cap_wrap_points,
                chord_points=points_per_block_side,
                dense_points_per_surface=dense_airfoil_points_per_surface,
                wrap_x=cap_wrap_x,
                minimum_te_thickness=minimum_te_thickness,
            )
            for xsec in xsecs
        ]
    else:
        side_builder = _airfoil_four_sides if oml_topology == "mid4" else _airfoil_eight_sides
        sides_by_xsec = [
            side_builder(
                xsec.airfoil,
                points_per_side=points_per_block_side,
                dense_points_per_surface=dense_airfoil_points_per_surface,
                split_x_fore=split_x_fore,
                minimum_te_thickness=minimum_te_thickness,
            )
            for xsec in xsecs
        ]

    raw_oml = _map_sides_to_wing(wing, sides_by_xsec)
    raw_oml = _refine_spanwise(raw_oml, spanwise_panels_per_section)

    # Snap root edge to an exact y-plane — pyHyp requires a genuinely planar
    # symmetry boundary, and AeroSandbox can leave floating-point noise on it.
    section_centers_refined = []
    for j in range(raw_oml[0].shape[1]):
        boundary = np.concatenate([block[:-1, j, :] for block in raw_oml], axis=0)
        section_centers_refined.append(np.mean(boundary, axis=0))
    section_centers_refined = np.asarray(section_centers_refined)
    root_j = int(np.argmin(np.abs(section_centers_refined[:, 1])))

    root_points_before = np.concatenate(
        [block[:, root_j, :] for block in raw_oml], axis=0
    )
    root_mean_y_before = float(np.mean(root_points_before[:, 1]))
    root_y_range_before = float(np.ptp(root_points_before[:, 1]))

    raw_points_for_scale = np.vstack([block.reshape(-1, 3) for block in raw_oml])
    raw_characteristic_length = float(np.linalg.norm(np.ptp(raw_points_for_scale, axis=0)))
    zero_snap_tol = max(1e-12, raw_characteristic_length * 1e-8)
    root_plane_y = 0.0 if abs(root_mean_y_before) <= zero_snap_tol else root_mean_y_before
    for block in raw_oml:
        block[:, root_j, 1] = root_plane_y

    root_points = np.concatenate([block[:, root_j, :] for block in raw_oml], axis=0)
    root_y_range = float(np.ptp(root_points[:, 1]))

    if oml_topology == "cap4":
        raw_ring, raw_center, tip_groups = _build_tip_cap4(
            raw_oml,
            collar_points=tip_radial_points,
            width_frac=cap_width_frac,
        )
    else:
        raw_ring, raw_center, tip_groups = _build_tip_blocks(
            raw_oml,
            radial_points=tip_radial_points,
            inner_scale=tip_inner_scale,
            conformal_ring=tip_conformal_ring,
        )

    oml_arrays = _orient_oml_blocks_outward(raw_oml)
    section_centers = np.array(
        [
            np.mean(
                np.concatenate([block[:-1, j, :] for block in raw_oml], axis=0),
                axis=0,
            )
            for j in range(len(xsecs))
        ]
    )
    tip_outward = section_centers[-1] - section_centers[-2]
    if np.linalg.norm(tip_outward) < 1e-12:
        raise MeshBuildError(
            "Cannot infer outward wingtip direction from the last two xsecs."
        )

    if tip_dome_scale > 0.0:
        tip_boundary = np.concatenate(
            [block[:-1, -1, :] for block in raw_oml], axis=0
        )
        domed = _apply_tip_dome(
            [*raw_ring, *raw_center], tip_boundary, tip_outward, tip_dome_scale
        )
        raw_ring = domed[: len(raw_ring)]
        raw_center = domed[len(raw_ring) :]
    tip_arrays = _orient_tip_blocks_outward([*raw_ring, *raw_center], tip_outward)

    oml = [SurfaceBlock(f"oml_{i}", block) for i, block in enumerate(oml_arrays)]
    ring = [SurfaceBlock(f"tip_ring_{i}", tip_arrays[i]) for i in range(len(raw_ring))]
    center = [
        SurfaceBlock(f"tip_center_{i}", tip_arrays[len(raw_ring) + i])
        for i in range(len(raw_center))
    ]
    blocks = [*oml, *ring, *center]

    qc_blocks = [_block_qc(block) for block in blocks]
    all_points = np.vstack([b.xyz.reshape(-1, 3) for b in blocks])
    extent = np.ptp(all_points, axis=0)
    characteristic_length = float(np.linalg.norm(extent))
    connection_tol = max(1e-10, characteristic_length * 1e-10)
    connectivity = _connectivity_qc(oml, ring, center, connection_tol, tip_groups=tip_groups)

    root_plane_ok = root_y_range <= connection_tol
    min_area = min(float(item["min_area"]) for item in qc_blocks)
    min_jacobian = min(float(item["min_scaled_corner_jacobian"]) for item in qc_blocks)
    min_alignment = min(float(item["min_triangle_normal_alignment"]) for item in qc_blocks)
    max_adjacent_normal_angle = max(
        float(item["max_adjacent_normal_angle_deg"]) for item in qc_blocks
    )
    area_floor = max(1e-20, characteristic_length**2 * 1e-14)
    jacobian_floor = float(minimum_scaled_jacobian)
    alignment_floor = -0.25

    failure_reasons: list[dict[str, object]] = []
    if not connectivity["all_matched"]:
        unmatched = [
            item["connection"]
            for item in connectivity["checks"]
            if not bool(item["matched"])
        ]
        failure_reasons.append(
            {
                "check": "block_connectivity",
                "message": "One or more structured block edges do not match.",
                "unmatched_connections": unmatched,
            }
        )
    if not root_plane_ok:
        failure_reasons.append(
            {
                "check": "symmetry_root_planarity",
                "message": "The detected root edge is not planar in y within tolerance.",
                "y_range": root_y_range,
                "tolerance": connection_tol,
            }
        )
    if not min_area > area_floor:
        worst = min(qc_blocks, key=lambda item: float(item["min_area"]))
        failure_reasons.append(
            {
                "check": "minimum_surface_cell_area",
                "message": "At least one surface cell is collapsed or nearly collapsed.",
                "block": worst["name"],
                "value": min_area,
                "required_greater_than": area_floor,
            }
        )
    if not min_jacobian > jacobian_floor:
        worst = min(qc_blocks, key=lambda item: float(item["min_scaled_corner_jacobian"]))
        failure_reasons.append(
            {
                "check": "minimum_scaled_corner_jacobian",
                "message": "At least one surface quad is excessively skewed or degenerate.",
                "block": worst["name"],
                "value": min_jacobian,
                "required_greater_than": jacobian_floor,
            }
        )
    if not min_alignment > alignment_floor:
        worst = min(
            qc_blocks, key=lambda item: float(item["min_triangle_normal_alignment"])
        )
        failure_reasons.append(
            {
                "check": "quad_triangle_normal_alignment",
                "message": "At least one quad is folded or strongly non-planar.",
                "block": worst["name"],
                "value": min_alignment,
                "required_greater_than": alignment_floor,
            }
        )
    if not max_adjacent_normal_angle <= maximum_adjacent_normal_angle_deg:
        worst = max(
            qc_blocks, key=lambda item: float(item["max_adjacent_normal_angle_deg"])
        )
        failure_reasons.append(
            {
                "check": "adjacent_surface_normal_rotation",
                "message": "At least one block has excessive wall-normal rotation between adjacent cells.",
                "block": worst["name"],
                "value": max_adjacent_normal_angle,
                "required_less_equal": maximum_adjacent_normal_angle_deg,
            }
        )

    accepted = len(failure_reasons) == 0

    report: dict[str, object] = {
        "schema": SURFACE_SCHEMA_VERSION,
        "topology": {
            "mid4": "mid-chord O-type: 4 OML + 4 tip-ring + 1 tip-center",
            "split8": "split LE/TE O-type: 8 OML + 8 tip-ring + 4 tip-center",
            "cap4": "camber-cap: 4 OML (narrow LE/TE wraps) + 4 collar + 1 camber-strip center",
        }[oml_topology],
        "oml_topology": oml_topology,
        "cap_wrap_points": cap_wrap_points,
        "cap_wrap_x": cap_wrap_x,
        "cap_width_frac": cap_width_frac,
        "block_count": len(blocks),
        "xsec_count": len(xsecs),
        "spanwise_panels_per_section": spanwise_panels_per_section,
        "spanwise_station_count": raw_oml[0].shape[1],
        "points_per_block_side": points_per_block_side,
        "tip_radial_points": tip_radial_points,
        "tip_inner_scale": tip_inner_scale,
        "tip_dome_scale": tip_dome_scale,
        "tip_conformal_ring": tip_conformal_ring,
        "split_x_fore": split_x_fore,
        "split_x_aft": 1.0 - split_x_fore,
        "minimum_te_thickness": minimum_te_thickness,
        "minimum_scaled_jacobian": jacobian_floor,
        "maximum_adjacent_normal_angle_deg": maximum_adjacent_normal_angle_deg,
        "characteristic_length": characteristic_length,
        "blocks": qc_blocks,
        "connectivity": connectivity,
        "symmetry_root": {
            "detected_spanwise_index": root_j,
            "mean_y_before_snap": root_mean_y_before,
            "y_range_before_snap": root_y_range_before,
            "snapped_plane_y": root_plane_y,
            "zero_snap_tolerance": zero_snap_tol,
            "mean_y": float(np.mean(root_points[:, 1])),
            "y_range": root_y_range,
            "planar_within_tolerance": root_plane_ok,
        },
        "global": {
            "min_area": min_area,
            "area_floor": area_floor,
            "min_scaled_corner_jacobian": min_jacobian,
            "jacobian_floor": jacobian_floor,
            "min_triangle_normal_alignment": min_alignment,
            "alignment_floor": alignment_floor,
            "max_adjacent_normal_angle_deg": max_adjacent_normal_angle,
        },
        "accepted_pre_pyhyp": accepted,
        "failure_reasons": failure_reasons,
    }
    return blocks, report


def export_surface_mesh(
    wing: object,
    output_dir: Path,
    *,
    require_cgns_export: bool = False,
    **build_kwargs: object,
) -> dict[str, object]:
    """Build, QC, and export the structured surface to output_dir.

    Always writes PLOT3D, VTK, and NPZ debug artifacts before attempting CGNS
    export. pyHyp uses the PLOT3D file, so CGNS surface export is optional unless
    require_cgns_export=True.

    Returns the surface report dict. Raises MeshBuildError on construction or QC failure.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / "surface_report.json"
    failure_path = output_dir / "surface_failure.json"
    cgns_path = output_dir / "surface.cgns"
    plot3d_path = output_dir / "surface.fmt"
    vtk_path = output_dir / "surface.vtk"
    npz_path = output_dir / "surface_blocks.npz"

    for stale in (report_path, failure_path, cgns_path):
        try:
            stale.unlink()
        except FileNotFoundError:
            pass

    try:
        blocks, report = build_surface_mesh(wing, **build_kwargs)
    except Exception as exc:
        failure_report = {
            "schema": SURFACE_SCHEMA_VERSION,
            "stage": "surface_build",
            "accepted_pre_pyhyp": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "build_parameters": {k: str(v) for k, v in build_kwargs.items()},
        }
        payload = json.dumps(failure_report, indent=2, sort_keys=True, default=str)
        failure_path.write_text(payload, encoding="utf-8")
        report_path.write_text(payload, encoding="utf-8")
        raise MeshBuildError(
            f"Surface construction failed: {exc}. Inspect {failure_path}."
        ) from exc

    _write_plot3d_formatted(plot3d_path, blocks)
    _write_vtk(vtk_path, blocks)
    _write_npz(npz_path, blocks)

    artifacts: dict[str, object] = {
        "plot3d_debug": {"path": str(plot3d_path), "sha256": _hash_file(plot3d_path)},
        "vtk": {"path": str(vtk_path), "sha256": _hash_file(vtk_path)},
        "npz": {"path": str(npz_path), "sha256": _hash_file(npz_path)},
    }
    report["artifacts"] = artifacts

    if not bool(report["accepted_pre_pyhyp"]):
        report["cgns"] = {"written": False, "status": "rejected_by_surface_qc"}
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )
        summaries = []
        for reason in report.get("failure_reasons", []):
            detail = str(reason.get("check", "unknown"))
            if reason.get("block"):
                detail += f" in {reason['block']}"
            if reason.get("value") is not None:
                detail += f" (value={float(reason['value']):.6e})"
            summaries.append(detail)
        raise MeshBuildError(
            "Surface mesh failed QC: "
            + ("; ".join(summaries) or "unknown")
            + f". Inspect {report_path} and {vtk_path}."
        )

    report["cgns"] = {"written": False, "status": "pending_export"}
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )

    try:
        cgns_metadata = _write_cgns_structured_surface(cgns_path, blocks)
    except Exception as exc:
        report["cgns"] = {
            "written": False,
            "status": "export_failed",
            "required": require_cgns_export,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )
        if require_cgns_export:
            raise
        return report

    artifacts["cgns_surface"] = {
        "path": str(cgns_path),
        "sha256": _hash_file(cgns_path),
    }
    report["cgns"] = cgns_metadata
    report["artifacts"] = artifacts
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report
