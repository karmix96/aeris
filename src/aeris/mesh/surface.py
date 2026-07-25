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
from typing import Protocol, Sequence

import numpy as np

# aeris.mesh may depend on aeris.cfd (the plugin direction); the reverse is
# what the import-boundary test forbids.
from aeris.cfd.meshing.quality import block_quality_metrics

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
            f"{label} is not purely numeric. Resolve all symbolic/CasADi values before CFD meshing."
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

    if getattr(geometry, "sections", None) is not None:
        # A pyGeo surface carrier is itself a single meshable "wing".
        if wing_index not in (0, -1):
            raise MeshBuildError("A pyGeo surface carrier was passed, so wing_index must be 0.")
        return geometry

    wings = getattr(geometry, "wings", None)
    if wings is None:
        raise MeshBuildError("Geometry must be an AeroSandbox Wing or Airplane-like object.")
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


DISTRIBUTIONS = (
    "uniform",
    "cosine",
    "cluster_start",
    "cluster_end",
    "tanh",
    # dense at the side's midpoint -- mid4/split8 put the LE and TE in block
    # interiors, so end-clustering cannot reach them
    "cluster_center",
    # continuous uniform <-> cosine blend (pyGeo createMidsurfaceMesh's
    # chordCosSpacing): beta in [0, 1] sets the clustering strength
    "cosine_blend",
    # topology-aware: each side builder decides per side (cap4 only)
    "junction",
)


def _distribution(n: int, mode: str = "uniform", *, beta: float = 2.0) -> Array:
    """Parametric node positions in [0, 1] for one structured direction.

    Controls where points bunch up.  ``uniform`` spaces by arc length, which
    is what this module did everywhere before 2026-07-22 and which
    under-resolves the leading and trailing edges — the two places a RANS
    surface mesh most needs points.

    * ``cosine`` — clusters at *both* ends (standard airfoil distribution).
    * ``cluster_start`` / ``cluster_end`` — clusters at one end, for sides
      whose far end is already refined by a neighbouring block.
    * ``tanh`` — symmetric clustering whose strength is set by ``beta``;
      higher is tighter.  Approaches ``uniform`` as beta -> 0.
    """
    if n < 2:
        raise MeshBuildError("A structured direction needs at least 2 points.")
    if mode == "junction":
        raise MeshBuildError(
            "'junction' is resolved per side by the topology, not a raw distribution"
        )
    if mode not in DISTRIBUTIONS:
        raise MeshBuildError(f"distribution must be one of {DISTRIBUTIONS}, got {mode!r}")

    t = np.linspace(0.0, 1.0, n)
    if mode == "uniform":
        return t
    if mode == "cosine":
        return 0.5 * (1.0 - np.cos(np.pi * t))
    if mode == "cluster_start":
        # dense at t=0: quarter-cosine, zero slope at the far end
        return 1.0 - np.cos(0.5 * np.pi * t)
    if mode == "cluster_end":
        return np.sin(0.5 * np.pi * t)
    if mode == "cosine_blend":
        weight = float(np.clip(beta, 0.0, 1.0))
        return weight * 0.5 * (1.0 - np.cos(np.pi * t)) + (1.0 - weight) * t
    if mode == "cluster_center":
        # t + (a/2pi) sin(2 pi t): spacing ~ 1 + a cos(2 pi t), so cells are
        # widest at the ends and tightest at t=0.5.  a < 1 keeps it monotone.
        a = min(0.95, max(0.0, 0.45 * beta))
        return t + (a / (2.0 * np.pi)) * np.sin(2.0 * np.pi * t)
    if beta <= 0.0:
        return t
    stretched = np.tanh(beta * (t - 0.5)) / np.tanh(0.5 * beta)
    return 0.5 * (1.0 + stretched)


def _resample_polyline(
    points: Array,
    n: int,
    *,
    cosine: bool = True,
    distribution: str | None = None,
    beta: float = 2.0,
) -> Array:
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

    mode = distribution if distribution is not None else ("cosine" if cosine else "uniform")
    sample_s = _distribution(n, mode, beta=beta) * s[-1]
    return np.column_stack([np.interp(sample_s, s, points[:, axis]) for axis in range(2)])


def _te_fraction_with_floor(base_frac: float, chord: float, abs_floor: float) -> float:
    """Per-section blunt-TE fraction, floored to an absolute thickness.

    A blunt TE given as a chord *fraction* shrinks in absolute size toward the
    tip (0.5%c is 8 mm at a 1.6 m root but ~1 mm at a 0.2 m tip).  ``abs_floor``
    (metres) raises the fraction so the physical base never drops below the
    floor -- real aircraft do exactly this, you cannot build a 0.5 mm edge, and
    the extra outboard thickness dents the tip-collar skewness (law 10).  The
    result is clamped to 5%c, the same envelope the raw fraction is validated
    against: a floor exceeding 5%c of some chord means the floor is too big for
    that section, not that a grossly thick TE should be built there.
    """
    frac = base_frac
    if abs_floor > 0.0 and chord > 0.0:
        frac = max(frac, abs_floor / chord)
    return min(frac, 0.05)


def _open_trailing_edge(coords: Array, target_thickness: float) -> Array:
    """Thicken a normalized airfoil's trailing edge to ``target_thickness`` chord.

    Structured meshing needs a blunt trailing edge: the TE block has to wrap
    the base, and the thinner that base, the sharper the turn it must make.
    AeroSandbox's NACA sections come out at ~0.25% chord, which is 2-4x
    thinner than the 0.5-1.0% normally used for a CFD blunt TE, and at the
    tip of a tapered wing that is a few tenths of a millimetre.

    Points are displaced perpendicular to the chord line by a half-gap that
    grows linearly from zero at the leading edge to the full half-gap at the
    trailing edge, so the leading edge and the forward shape are untouched
    and only the aft camber/thickness distribution shifts.  This is the
    classic airfoil TE-opening operation.

    Returns the coordinates unchanged if they are already thick enough.
    """
    coords = np.asarray(coords, dtype=float)
    le_index = int(np.argmin(coords[:, 0]))
    current = float(np.linalg.norm(coords[0] - coords[-1]))
    if target_thickness <= current:
        return coords

    half_gap = 0.5 * (target_thickness - current)
    x = coords[:, 0]
    x_le = float(x[le_index])
    # Normalize against the actual trailing-edge station, not 1.0: after
    # normalize() the TE can sit a fraction short of x=1 and the blend would
    # then stop just below the requested gap.
    span = max(float(x.max()) - x_le, 1e-12)
    blend = np.clip((x - x_le) / span, 0.0, 1.0)

    opened = coords.copy()
    # coords run upper TE -> LE -> lower TE, so the split at le_index gives
    # the sign of the displacement.
    sign = np.where(np.arange(len(coords)) <= le_index, 1.0, -1.0)
    opened[:, 1] = coords[:, 1] + sign * half_gap * blend
    return opened


def _resample_piecewise(
    segments: Sequence[Array],
    counts: Sequence[int],
    *,
    distribution: str | Sequence[str] = "uniform",
    beta: float = 2.0,
) -> Array:
    """Resample consecutive polyline segments independently and join them.

    Resampling a composite side in one pass distributes nodes by arc length
    over the whole side, which silently discards the *corners* between
    segments.  On a blunt trailing edge those corners are the two ~90 deg
    turns onto the base — losing them smears the base over whatever nodes
    arc length happens to land there and leaves the midpoint protruding aft
    of its neighbours.  Resampling per segment pins every corner to a node.

    Shared endpoints are emitted once.
    """
    if len(segments) != len(counts):
        raise MeshBuildError("_resample_piecewise needs one count per segment.")
    modes = [distribution] * len(segments) if isinstance(distribution, str) else list(distribution)
    pieces: list[Array] = []
    for index, (segment, count) in enumerate(zip(segments, counts, strict=False)):
        if count < 2:
            raise MeshBuildError("each piecewise segment needs at least 2 points.")
        sampled = _resample_polyline(segment, count, distribution=modes[index], beta=beta)
        pieces.append(sampled if index == 0 else sampled[1:])
    return np.vstack(pieces)


def _split_counts(segments: Sequence[Array], total: int, fixed: dict[int, int]) -> list[int]:
    """Allocate ``total`` unique nodes across segments, honouring fixed counts.

    Joined segments share their endpoints, so N segments holding ``counts``
    nodes each yield ``sum(counts) - (N - 1)`` unique nodes.  Segments
    without a fixed count share what remains in proportion to arc length, so
    the free part of the side keeps a uniform node density.
    """
    n_seg = len(segments)
    lengths = [float(_polyline_arclength(np.asarray(seg, dtype=float))[-1]) for seg in segments]
    free = [i for i in range(n_seg) if i not in fixed]
    if not free:
        raise MeshBuildError("_split_counts needs at least one free segment.")

    budget = total + n_seg - 1 - sum(fixed.values())
    if budget < 2 * len(free):
        raise MeshBuildError(
            f"too few points ({total}) to give every segment 2 nodes with "
            f"{sum(fixed.values())} pinned."
        )

    counts = [0] * n_seg
    for index, value in fixed.items():
        counts[index] = value

    free_length = sum(lengths[i] for i in free) or 1.0
    assigned = 0
    for position, index in enumerate(free):
        if position == len(free) - 1:
            counts[index] = budget - assigned
        else:
            share = max(2, int(round(budget * lengths[index] / free_length)))
            counts[index] = share
            assigned += share
    if min(counts[i] for i in free) < 2:
        raise MeshBuildError("segment allocation produced fewer than 2 nodes.")
    return counts


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
    te_thickness: float = 0.0,
    te_base_points: int = 0,
    chordwise_distribution: str = "uniform",
    chordwise_beta: float = 2.0,
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

    if te_thickness > 0.0:
        coords = _open_trailing_edge(coords, te_thickness)
    le_index = int(np.argmin(coords[:, 0]))
    if le_index == 0 or le_index == len(coords) - 1:
        raise MeshBuildError(
            "Unexpected airfoil ordering: leading edge must lie between upper and lower TE points."
        )

    upper_te_to_le = coords[: le_index + 1].copy()  # x: 1 -> 0
    lower_le_to_te = coords[le_index:].copy()  # x: 0 -> 1

    te_thickness_actual = float(np.linalg.norm(upper_te_to_le[0] - lower_le_to_te[-1]))
    if te_thickness_actual < minimum_te_thickness:
        raise MeshBuildError(
            f"Trailing edge thickness is {te_thickness_actual:.3e} chord, below the required "
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
        np.vstack(
            [
                upper_te_to_le[upper_nose_idx:],
                lower_le_to_te[1 : lower_nose_idx + 1],
            ]
        ),
        lower_le_to_te[lower_nose_idx : lower_fore_idx + 1],
        lower_le_to_te[lower_fore_idx : lower_aft_idx + 1],
        lower_le_to_te[lower_aft_idx : lower_te_shoulder_idx + 1],
        np.vstack(
            [
                lower_le_to_te[lower_te_shoulder_idx:],
                [te_mid],
                upper_te_to_le[: upper_te_shoulder_idx + 1],
            ]
        ),
        upper_te_to_le[upper_te_shoulder_idx : upper_aft_idx + 1],
        upper_te_to_le[upper_aft_idx : upper_fore_idx + 1],
    ]

    # mid4/split8 have no narrow wrap blocks -- every side runs between two
    # block splits, so the topology-aware "junction" mode is plain cosine.
    mode = "cosine" if chordwise_distribution == "junction" else chordwise_distribution
    sides = [
        _resample_polyline(side, points_per_side, distribution=mode, beta=chordwise_beta)
        for side in raw_sides
    ]
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
    te_thickness: float = 0.0,
    te_base_points: int = 0,
    chordwise_distribution: str = "uniform",
    chordwise_beta: float = 2.0,
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
    if te_thickness > 0.0:
        coords = _open_trailing_edge(coords, te_thickness)
    le_index = int(np.argmin(coords[:, 0]))
    if le_index == 0 or le_index == len(coords) - 1:
        raise MeshBuildError(
            "Unexpected airfoil ordering: leading edge must lie between upper and lower TE points."
        )
    upper_te_to_le = coords[: le_index + 1].copy()
    lower_le_to_te = coords[le_index:].copy()
    te_thickness_actual = float(np.linalg.norm(upper_te_to_le[0] - lower_le_to_te[-1]))
    if te_thickness_actual < minimum_te_thickness:
        raise MeshBuildError(
            f"Trailing edge thickness is {te_thickness_actual:.3e} chord, below the required "
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
    # mid4/split8 have no narrow wrap blocks -- every side runs between two
    # block splits, so the topology-aware "junction" mode is plain cosine.
    mode = "cosine" if chordwise_distribution == "junction" else chordwise_distribution
    sides = [
        _resample_polyline(side, points_per_side, distribution=mode, beta=chordwise_beta)
        for side in raw_sides
    ]
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
    te_thickness: float = 0.0,
    te_base_points: int = 0,
    chordwise_distribution: str = "uniform",
    chordwise_beta: float = 2.0,
    coords: Array | None = None,
) -> list[Array]:
    """Return 4 sides with per-side point counts for the cap4 topology.

    Corners sit near the LE and TE (x/c = wrap_x and 1-wrap_x): a narrow nose
    wrap and TE wrap carry ``wrap_points`` each, while the long upper/lower
    sides carry ``chord_points``.  This keeps surface cell size near-uniform
    around the airfoil — uniform-count topologies over-resolve the tiny LE/TE
    arcs, which is what makes the tip cap fold in pyHyp.

    ``coords`` lets a caller supply a normalised (N, 2) airfoil loop
    (upper-TE -> LE -> lower-TE) directly, bypassing the AeroSandbox
    normalize()/repanel() path.  The pyGeo source uses this to split a
    surface-sampled section without AeroSandbox; ``airfoil`` is ignored then.
    """
    shoulder_x = 1.0 - wrap_x
    if coords is None:
        try:
            working = airfoil.normalize().repanel(n_points_per_side=dense_points_per_surface)
        except AttributeError as exc:
            raise MeshBuildError(
                "Each WingXSec must contain an AeroSandbox Airfoil with normalize()/repanel()."
            ) from exc
        coords = _as_numeric_xyz(working.coordinates, label="airfoil coordinates")
    else:
        coords = _as_numeric_xyz(coords, label="airfoil coordinates")
    if coords.ndim != 2 or coords.shape[1] != 2 or len(coords) < 9:
        raise MeshBuildError("Airfoil coordinates must have shape (N, 2), N >= 9.")
    if te_thickness > 0.0:
        coords = _open_trailing_edge(coords, te_thickness)
    le_index = int(np.argmin(coords[:, 0]))
    if le_index == 0 or le_index == len(coords) - 1:
        raise MeshBuildError(
            "Unexpected airfoil ordering: leading edge must lie between upper and lower TE points."
        )
    upper_te_to_le = coords[: le_index + 1].copy()
    lower_le_to_te = coords[le_index:].copy()
    te_thickness_actual = float(np.linalg.norm(upper_te_to_le[0] - lower_le_to_te[-1]))
    if te_thickness_actual < minimum_te_thickness:
        raise MeshBuildError(
            f"Trailing edge thickness is {te_thickness_actual:.3e} chord, below the required "
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
        np.vstack(
            [
                lower_le_to_te[lower_shoulder_idx:],
                [te_mid],
                upper_te_to_le[: upper_shoulder_idx + 1],
            ]
        ),
        upper_te_to_le[upper_shoulder_idx : upper_nose_idx + 1],
    ]
    counts = [wrap_points, chord_points, wrap_points, chord_points]
    # cap4's four sides are LE-wrap, lower chord, TE-wrap, upper chord.  A
    # single distribution applied to all four is wrong: the wrap sides are
    # narrow bands whose *middle* is the leading (or trailing) edge, so
    # clustering their ends coarsens exactly the point that needs
    # resolution.  "junction" therefore clusters only the two long chord
    # sides, whose ends are the wrap-block junctions, and leaves the wraps
    # uniform.
    if chordwise_distribution == "junction":
        per_side = ["uniform", "cosine", "uniform", "cosine"]
    else:
        per_side = [chordwise_distribution] * 4
    sides = []
    for index, (side, n, mode) in enumerate(zip(raw_sides, counts, per_side, strict=False)):
        if index == 2 and te_base_points >= 2:
            # The TE wrap side is (lower arc | blunt base | upper arc).  Pin
            # both base corners by resampling the three pieces separately,
            # otherwise arc-length resampling smears the two ~90 deg turns
            # and the base midpoint protrudes aft of its neighbours.
            base = np.vstack([lower_le_to_te[-1], te_mid, upper_te_to_le[0]])
            pieces = [
                lower_le_to_te[lower_shoulder_idx:],
                base,
                upper_te_to_le[: upper_shoulder_idx + 1],
            ]
            allocation = _split_counts(pieces, n, {1: te_base_points})
            # Taper each surface arc into the base corner.  Pinning the
            # corner makes the turn exact but leaves short base cells beside
            # long surface cells; clustering the arcs against the corner is
            # what keeps the size transition smooth.
            sides.append(
                _resample_piecewise(
                    pieces,
                    allocation,
                    distribution=["cluster_end", "uniform", "cluster_start"],
                    beta=chordwise_beta,
                )
            )
        else:
            sides.append(_resample_polyline(side, n, distribution=mode, beta=chordwise_beta))
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


@dataclass(frozen=True)
class OmlTopologyParams:
    """The topology/resolution knobs an OML geometry source needs to emit blocks.

    Deliberately geometry-source-agnostic: an AeroSandbox wing and a pyGeo loft
    build the SAME structured topology from different point sources.
    """

    oml_topology: str
    points_per_block_side: int
    cap_wrap_points: int
    cap_wrap_x: float
    split_x_fore: float
    dense_airfoil_points_per_surface: int
    minimum_te_thickness: float
    te_thickness: float
    te_thickness_abs_floor: float
    te_base_points: int
    chordwise_distribution: str
    chordwise_beta: float


class _OmlGeometrySource(Protocol):
    """Emits the raw (pre-spanwise-refinement) OML blocks in 3D.

    The mesher's spanwise refinement, root-plane snap, tip closure and QC are
    all geometry-source-agnostic; only the OML surface points come from here.
    An implementation MUST return one block per side, in the exact side order
    the tip closure and QC expect (cap4: LE-wrap, lower chord, TE-wrap, upper
    chord), each of shape ``(n_side_points, n_stations, 3)``.
    """

    def raw_oml_blocks(self, params: OmlTopologyParams) -> list[Array]: ...


class AeroSandboxOmlSource:
    """OML blocks from an AeroSandbox Wing -- the original, validated path.

    Each section's airfoil is split into 2D sides and lofted to 3D through
    ``Wing.mesh_line``.  This is the ONLY source that uses AeroSandbox; the
    pyGeo source samples its own realised surface instead.  The logic here is
    a verbatim move of the former in-line block in ``build_surface_mesh`` and
    must stay behaviourally identical.
    """

    def __init__(self, wing: object) -> None:
        self._wing = wing
        self._xsecs = list(getattr(wing, "xsecs", []) or [])

    def raw_oml_blocks(self, p: OmlTopologyParams) -> list[Array]:
        def te_frac_for(xsec: object) -> float:
            chord = float(getattr(xsec, "chord", 0.0) or 0.0)
            return _te_fraction_with_floor(p.te_thickness, chord, p.te_thickness_abs_floor)

        if p.oml_topology == "cap4":
            sides_by_xsec = [
                _airfoil_cap4_sides(
                    xsec.airfoil,
                    wrap_points=p.cap_wrap_points,
                    chord_points=p.points_per_block_side,
                    dense_points_per_surface=p.dense_airfoil_points_per_surface,
                    wrap_x=p.cap_wrap_x,
                    minimum_te_thickness=p.minimum_te_thickness,
                    te_thickness=te_frac_for(xsec),
                    te_base_points=p.te_base_points,
                    chordwise_distribution=p.chordwise_distribution,
                    chordwise_beta=p.chordwise_beta,
                )
                for xsec in self._xsecs
            ]
        else:
            side_builder = _airfoil_four_sides if p.oml_topology == "mid4" else _airfoil_eight_sides
            sides_by_xsec = [
                side_builder(
                    xsec.airfoil,
                    points_per_side=p.points_per_block_side,
                    dense_points_per_surface=p.dense_airfoil_points_per_surface,
                    split_x_fore=p.split_x_fore,
                    minimum_te_thickness=p.minimum_te_thickness,
                    te_thickness=te_frac_for(xsec),
                    te_base_points=p.te_base_points,
                    chordwise_distribution=p.chordwise_distribution,
                    chordwise_beta=p.chordwise_beta,
                )
                for xsec in self._xsecs
            ]
        return _map_sides_to_wing(self._wing, sides_by_xsec)


@dataclass(frozen=True)
class PyGeoSurfaceGeometry:
    """Carrier for a realised pyGeo loft's surface-sampled section slices.

    Lets ``build_surface_mesh`` mesh the pyGeo surface with no ``asb.Wing``.
    ``sections`` are ordered root -> tip and must expose (duck-typed, so this
    module never imports pyGeo): ``direct_coordinates`` (N, 2 normalised loop,
    upper-TE -> LE -> lower-TE), ``chord_m``, ``le_xyz_m``, ``chord_axis``,
    ``thickness_axis``.  ``xsecs`` mirrors ``sections`` for the mesher's
    section-count validation and report bookkeeping.
    """

    sections: tuple
    name: str = "pygeo_wing"
    symmetric: bool = True

    @property
    def xsecs(self) -> tuple:
        return self.sections


class PyGeoSectionOmlSource:
    """OML blocks from realised-surface section slices -- AeroSandbox-free.

    Each section already carries its airfoil sampled on the pyGeo surface plus
    the local frame (LE, chord/thickness axes, chord).  The cap4 split runs on
    the section's 2D coordinates and the result maps straight back to 3D through
    that frame -- no ``Wing.mesh_line``, no ``asb.Airfoil``.  The manufacturable
    TE floor is enforced here identically to the AeroSandbox source, so both
    paths mesh the same aircraft.
    """

    def __init__(self, sections: Sequence[object]) -> None:
        self._sections = list(sections)
        if len(self._sections) < 2:
            raise MeshBuildError("A pyGeo surface geometry needs at least two sections.")

    def raw_oml_blocks(self, p: OmlTopologyParams) -> list[Array]:
        if p.oml_topology != "cap4":
            raise MeshBuildError(
                "The pyGeo OML source currently supports only oml_topology='cap4'."
            )
        sides_by_station: list[list[Array]] = []
        for sec in self._sections:
            coords2d = np.asarray(sec.direct_coordinates, dtype=float)
            chord_m = float(sec.chord_m)
            te_frac = _te_fraction_with_floor(p.te_thickness, chord_m, p.te_thickness_abs_floor)
            sides2d = _airfoil_cap4_sides(
                None,
                wrap_points=p.cap_wrap_points,
                chord_points=p.points_per_block_side,
                dense_points_per_surface=p.dense_airfoil_points_per_surface,
                wrap_x=p.cap_wrap_x,
                minimum_te_thickness=p.minimum_te_thickness,
                te_thickness=te_frac,
                te_base_points=p.te_base_points,
                chordwise_distribution=p.chordwise_distribution,
                chordwise_beta=p.chordwise_beta,
                coords=coords2d,
            )
            le = np.asarray(sec.le_xyz_m, dtype=float).reshape(3)
            chord_axis = np.asarray(sec.chord_axis, dtype=float).reshape(3)
            thick_axis = np.asarray(sec.thickness_axis, dtype=float).reshape(3)
            # Inverse of extract_section's projection: exact for the planarised
            # slice (span_axis component is the tiny discarded plane-warp).
            sides3d = [
                le[None, :]
                + chord_m * (s[:, 0:1] * chord_axis[None, :] + s[:, 1:2] * thick_axis[None, :])
                for s in sides2d
            ]
            sides_by_station.append(sides3d)

        n_sides = len(sides_by_station[0])
        return [
            np.stack([station[side_idx] for station in sides_by_station], axis=1)
            for side_idx in range(n_sides)
        ]


def _oml_source_for(geometry: object) -> _OmlGeometrySource:
    """Pick the OML geometry source for ``geometry``.

    AeroSandbox Wing (xsecs + mesh_line) -> AeroSandbox source; a pyGeo surface
    carrier (``sections``) -> the AeroSandbox-free pyGeo source.  Anything else
    is a clear error rather than a downstream ``mesh_line`` failure.
    """
    if hasattr(geometry, "xsecs") and hasattr(geometry, "mesh_line"):
        return AeroSandboxOmlSource(geometry)
    sections = getattr(geometry, "sections", None)
    if sections is not None:
        return PyGeoSectionOmlSource(sections)
    raise MeshBuildError(
        "Unsupported geometry for surface meshing: expected an AeroSandbox Wing "
        "(xsecs + mesh_line) or a pyGeo surface carrier (sections)."
    )


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
            blended_edges = (1 - vj) * bottom[i] + vj * top[i] + (1 - ui) * left[j] + ui * right[j]
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
        (1 - v) * b
        + v * t
        + (1 - u) * lf
        + u * r
        - ((1 - u) * (1 - v) * p00 + u * (1 - v) * p10 + (1 - u) * v * p01 + u * v * p11)
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

    e_nose = oml_blocks[0][:, -1, :]  # upper corner -> LE -> lower corner
    e_low = oml_blocks[1][:, -1, :]  # nose -> shoulder (LE -> TE)
    e_te = oml_blocks[2][:, -1, :]  # lower shoulder -> te_mid -> upper shoulder
    e_up = oml_blocks[3][:, -1, :]  # shoulder -> nose (TE -> LE)
    n_wrap = len(e_nose)
    n_chord = len(e_low)
    if len(e_te) != n_wrap or len(e_up) != n_chord:
        raise MeshBuildError("cap4 tip edges have inconsistent point counts.")

    lower = e_low  # nose -> te
    upper = e_up[::-1]  # nose -> te

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

    def edge_fraction(edge: Array) -> Array:
        lengths = np.linalg.norm(np.diff(edge, axis=0), axis=1)
        total = float(np.sum(lengths))
        if total <= 1.0e-14:
            return np.linspace(0.0, 1.0, len(edge))
        cumulative = np.concatenate(([0.0], np.cumsum(lengths)))
        return cumulative / total

    def straight_like_edge(a: Array, b: Array, edge: Array) -> Array:
        t = edge_fraction(edge)[:, None]
        return (1.0 - t) * a + t * b

    # Match the inner strip parameterization to the corresponding curved OML
    # wrap edge.  A uniform inner edge is harmless for synthetic thick tips but
    # folds the first TE-collar row on thin pyGeo BWB tips when the radial
    # resolution is increased: the outer wrap points are strongly non-uniform,
    # so the radial grid lines cross near the blunt TE.  Using the same
    # cumulative arc-length coordinate preserves block correspondence without
    # changing the topology or point counts.
    rect_left = straight_like_edge(rect_top[0], rect_bot[0], e_nose)  # upper -> lower
    rect_right = straight_like_edge(rect_bot[-1], rect_top[-1], e_te)  # lower -> upper

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


def _refine_spanwise(
    blocks: Sequence[Array],
    panels_per_section: int,
    *,
    distribution: str = "uniform",
    beta: float = 2.0,
    allocation: str = "uniform",
) -> list[Array]:
    """Subdivide each geometry section into panels along the span.

    ``distribution`` shapes the spacing *within* each section, so a
    clustering mode bunches points against every section boundary — which on
    a segmented BWB is exactly where the kinks, and the resulting surface
    slope discontinuities, live.
    """
    if panels_per_section < 1:
        raise MeshBuildError("spanwise_panels_per_section must be at least 1.")
    if allocation not in ("uniform", "proportional"):
        raise MeshBuildError("spanwise_allocation must be 'uniform' or 'proportional'.")

    n_intervals = blocks[0].shape[1] - 1
    if allocation == "proportional":
        # Geometry sections are not equally spaced along the span, so giving
        # every one the same panel count makes the cell size jump wherever
        # the section spacing changes -- on the baseline BWB that is a 1.50x
        # step at one kink, which was the whole of the mesh's growth ratio.
        # Allocate the same total budget in proportion to each interval's
        # spanwise extent instead (the per-segment nSpan idea from pyGeo's
        # createMidsurfaceMesh).
        centroids = np.stack(
            [
                np.mean(np.concatenate([b[:, j, :] for b in blocks], axis=0), axis=0)
                for j in range(n_intervals + 1)
            ]
        )
        lengths = np.linalg.norm(np.diff(centroids, axis=0), axis=1)
        total = float(lengths.sum()) or 1.0
        budget = panels_per_section * n_intervals
        counts = [max(1, int(round(budget * length / total))) for length in lengths]
    else:
        counts = [panels_per_section] * n_intervals

    # One extra sample then drop the endpoint: each interval contributes its
    # own columns and the next interval supplies the shared one.
    samples = {n: _distribution(n + 1, distribution, beta=beta)[:-1] for n in set(counts)}
    refined: list[Array] = []
    for block in blocks:
        columns = []
        for j in range(n_intervals):
            for t in samples[counts[j]]:
                columns.append((1.0 - t) * block[:, j, :] + t * block[:, j + 1, :])
        columns.append(block[:, -1, :])
        refined.append(np.stack(columns, axis=1))
    return refined


def _smooth_patch_interior(patch: Array, iterations: int, relaxation: float = 0.5) -> Array:
    """Laplacian-smooth a structured patch's interior, boundary held fixed.

    The tip collar's worst cells are rhombi -- similar edge lengths but ~8
    deg corners -- because the inner loop's node correspondence is not
    radial: point i of the inner loop is displaced along the loop rather
    than inward from point i of the outer loop.  No amount of resolution or
    uniform scaling fixes that, because it is a parameterisation mismatch,
    not a spacing one.  Relaxing interior nodes toward the average of their
    structured neighbours pulls the grid lines back toward orthogonality.

    Only interior (i, j) nodes move, so every block boundary -- and
    therefore all block-to-block connectivity -- is preserved exactly.
    """
    if iterations <= 0 or min(patch.shape[:2]) < 3:
        return patch
    out = patch.copy()
    for _ in range(int(iterations)):
        neighbour_mean = 0.25 * (
            out[:-2, 1:-1, :] + out[2:, 1:-1, :] + out[1:-1, :-2, :] + out[1:-1, 2:, :]
        )
        out[1:-1, 1:-1, :] += relaxation * (neighbour_mean - out[1:-1, 1:-1, :])
    return out


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


def _build_tip_single(
    oml_blocks: Sequence[Array],
) -> tuple[list[Array], list[Array], list[list[int]]]:
    """Close the tip with ONE transfinite patch on the four OML tip edges.

    The collar approach introduces a *radial* grid family that has to map a
    closed loop onto a rectangle; where the loop is sharply curved (nose) or
    nearly zero-thickness (blunt TE) that mapping rotates the radial
    direction until it is almost tangent, producing rhombic cells with ~8
    deg corners.  Refinement cannot change an angle and smoothing cannot
    move the outer loop, so the defect is structural.

    The chordwise-aligned rectangular patch, by contrast, is the best-shaped
    block in the mesh (skewness 0.085).  This closure keeps only that
    family: the four OML tip edges become the four sides of a single patch,
    so the cap carries no radial family at all.  Distortion concentrates at
    the four corners where the arcs meet instead of around a whole ring.

    Requires opposite OML tip edges to have matching point counts, which the
    cap4 layout ([nose wrap, lower, TE wrap, upper]) already satisfies.
    """
    if len(oml_blocks) != 4:
        raise MeshBuildError("single-patch tip closure requires exactly 4 OML blocks.")

    e_nose = oml_blocks[0][:, -1, :]
    e_low = oml_blocks[1][:, -1, :]
    e_te = oml_blocks[2][:, -1, :]
    e_up = oml_blocks[3][:, -1, :]
    if len(e_te) != len(e_nose) or len(e_up) != len(e_low):
        raise MeshBuildError("single-patch tip closure needs matching opposite edge counts.")

    # Walk the loop nose -> lower -> TE -> upper and use the two chord arcs
    # as the i-direction sides, the two wrap arcs as the j-direction sides.
    bottom = e_low  # nose corner -> TE corner (lower surface)
    top = e_up[::-1]  # nose corner -> TE corner (upper surface)
    left = e_nose[::-1]  # lower nose corner -> upper nose corner
    right = e_te  # lower TE corner -> upper TE corner

    if not np.allclose(left[0], bottom[0], atol=1e-9):
        left = left[::-1]
    if not np.allclose(right[0], bottom[-1], atol=1e-9):
        right = right[::-1]
    if not np.allclose(top[0], left[-1], atol=1e-9):
        top = top[::-1]

    patch = _tfi_patch(bottom, top, left, right)
    # No ring blocks: every OML tip edge attaches straight to the patch.
    return [], [patch], [[0], [1], [2], [3]]


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
    for outer, inner in zip(outer_sides, inner_sides, strict=False):
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
    center_corners = [center + center_scale * (inner_corners[idx] - center) for idx in (0, 2, 4, 6)]

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


def _orient_tip_blocks_outward(blocks: Sequence[Array], outward_vector: Array) -> list[Array]:
    outward_vector = outward_vector / np.linalg.norm(outward_vector)
    oriented = []
    for block in blocks:
        _, normals, _ = _cell_geometry(block)
        score = np.nanmedian(np.einsum("ijk,k->ij", normals, outward_vector))
        oriented.append(block[::-1, :, :].copy() if score < 0 else block.copy())
    return oriented


def _corner_shape_metric(block: Array) -> Array:
    """Per-quad Verdict *Shape* metric: min over corners of 2|e1 x e2|/(|e1|^2+|e2|^2).

    Named `scaled Jacobian` in this module until 2026-07-23, which was
    wrong.  The scaled Jacobian is |e1 x e2|/(|e1||e2|) = sin(theta) and
    depends on the corner angle alone; this quantity uses the sum of squared
    edge lengths in the denominator, so by AM-GM it is always <= the scaled
    Jacobian, with equality only for square cells.  It therefore penalises
    aspect ratio as well as angle -- a stricter, combined shape measure.

    Keeping it as the QC gate is deliberate (it is the stricter bar and
    every existing threshold was calibrated against it); only the name and
    the citation were wrong.  `min_scaled_jacobian` is reported alongside
    for comparison with published thresholds.
    """
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
        qualities.append(np.divide(2 * cross, denom, out=np.zeros_like(cross), where=denom > 0))
    return np.min(np.stack(qualities, axis=0), axis=0)


def _block_qc(block: SurfaceBlock) -> dict[str, float | int | str]:
    xyz = block.xyz
    if xyz.ndim != 3 or xyz.shape[2] != 3:
        raise MeshBuildError(f"Block {block.name} must have shape (ni, nj, 3).")
    if xyz.shape[0] < 2 or xyz.shape[1] < 2:
        raise MeshBuildError(f"Block {block.name} has fewer than 2 points per direction.")

    _, normal, area = _cell_geometry(xyz)
    quality = _corner_shape_metric(xyz)

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
        adjacent_normal_dot.append(np.sum(unit_normal[1:, :, :] * unit_normal[:-1, :, :], axis=2))
    if unit_normal.shape[1] > 1:
        adjacent_normal_dot.append(np.sum(unit_normal[:, 1:, :] * unit_normal[:, :-1, :], axis=2))
    if adjacent_normal_dot:
        min_adjacent_normal_dot = float(np.min([np.min(values) for values in adjacent_normal_dot]))
        max_adjacent_normal_angle_deg = float(
            np.degrees(np.arccos(np.clip(min_adjacent_normal_dot, -1.0, 1.0)))
        )
    else:
        max_adjacent_normal_angle_deg = 0.0

    # Skewness / aspect ratio / growth ratio come from the shared industry
    # metric set (aeris.cfd.meshing.quality) rather than a second local
    # implementation.  Until 2026-07-22 those were computed only for the 2D
    # airfoil O-grid, so the 3D wing surface was accepted on Jacobian and
    # normal-rotation alone — the two metrics least able to spot the coarse,
    # unclustered LE/TE cells this topology actually produces.
    industry = block_quality_metrics(xyz)

    return {
        "name": block.name,
        "ni": int(xyz.shape[0]),
        "nj": int(xyz.shape[1]),
        "nodes": int(xyz.shape[0] * xyz.shape[1]),
        "cells": int((xyz.shape[0] - 1) * (xyz.shape[1] - 1)),
        "min_area": float(np.min(area)),
        "median_area": float(np.median(area)),
        "min_shape_metric": float(np.min(quality)),
        "median_shape_metric": float(np.median(quality)),
        # True Verdict scaled Jacobian = sin(worst corner angle).  Note it
        # is an exact restatement of equiangle skewness for a quad
        # (jac == cos(90 * skew)), so the two are one measurement, not two.
        "min_scaled_jacobian": industry["min_scaled_jacobian"],
        "min_triangle_normal_alignment": float(np.min(normal_alignment)),
        "median_triangle_normal_alignment": float(np.median(normal_alignment)),
        "max_adjacent_normal_angle_deg": max_adjacent_normal_angle_deg,
        "max_equiangle_skewness": industry["max_equiangle_skewness"],
        "mean_equiangle_skewness": industry["mean_equiangle_skewness"],
        "max_aspect_ratio": industry["max_aspect_ratio"],
        "max_growth_ratio": industry["max_growth_ratio"],
    }


def _edge_match(a: Array, b: Array, tol: float) -> bool:
    if a.shape != b.shape:
        return False
    return bool(np.allclose(a, b, atol=tol, rtol=0) or np.allclose(a, b[::-1], atol=tol, rtol=0))


def _edge_contains_segment(edge: Array, segment: Array, tol: float) -> bool:
    if len(edge) < len(segment):
        return False
    candidates = [edge[: len(segment)], edge[-len(segment) :]]
    return any(_edge_match(candidate, segment, tol) for candidate in candidates)


def _free_edge_audit(
    blocks: Sequence[SurfaceBlock], tol: float, root_plane_y: float = 0.0
) -> dict[str, object]:
    """Find block edges shared by no other block, and where they sit.

    pyHyp is normally run with ``unattachedEdgesAreSymmetry=True``, which
    silently reinterprets *any* open boundary as a symmetry plane.  On a
    half-model the root plane is legitimately open — but so is a tip that
    failed to close, and that one would be extruded as though a mirror
    plane sat across the wingtip.  Auditing free edges here, against the
    surface we can still inspect, is the only place that lie is catchable.

    Returns the free-edge count and how many of them lie off the root
    plane; a closed half-model surface has zero of the latter.

    ``root_plane_y`` is the *detected* symmetry plane, not necessarily y=0:
    the builder snaps the root to its own mean plane when that mean is
    outside the zero-snap tolerance, so a legitimate half-model can sit at
    y = -2.9e-4.  Comparing against 0.0 instead would fail every such
    geometry.
    """
    edges: list[tuple[str, str, Array]] = []
    for block in blocks:
        xyz = block.xyz
        edges.append((block.name, "i0", xyz[0, :, :]))
        edges.append((block.name, "i1", xyz[-1, :, :]))
        edges.append((block.name, "j0", xyz[:, 0, :]))
        edges.append((block.name, "j1", xyz[:, -1, :]))

    free: list[dict[str, object]] = []
    for index, (name, side, edge) in enumerate(edges):
        shared = any(
            other_index != index and _edge_match(edge, other_edge, tol)
            for other_index, (_n, _s, other_edge) in enumerate(edges)
        )
        if shared:
            continue
        y_span = float(np.ptp(edge[:, 1]))
        mean_y = float(np.mean(edge[:, 1]))
        free.append(
            {
                "block": name,
                "side": side,
                "mean_y": mean_y,
                "y_range": y_span,
                # A root-plane edge is flat in y and sits on the detected
                # symmetry plane.
                "on_root_plane": bool(y_span <= tol and abs(mean_y - root_plane_y) <= tol),
            }
        )
    off_root = [item for item in free if not item["on_root_plane"]]
    return {
        "free_edge_count": len(free),
        "off_root_free_edges": len(off_root),
        "closed_except_root": not off_root,
        "edges": free,
    }


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

    if not ring:
        # Collar-free closure: every OML tip edge attaches straight to the
        # single cap patch, so check against the patch boundary instead.
        cap_edges = []
        for block in center:
            cap_edges.extend(
                [
                    block.xyz[:, 0, :],
                    block.xyz[-1, :, :],
                    block.xyz[:, -1, :],
                    block.xyz[0, :, :],
                ]
            )
        for oml_idx in range(n_oml):
            oml_tip_edges = [oml[oml_idx].xyz[:, -1, :], oml[oml_idx].xyz[::-1, -1, :]]
            matched = any(
                _edge_match(cap_edge, oml_edge, tol)
                or _edge_contains_segment(cap_edge, oml_edge, tol)
                for cap_edge in cap_edges
                for oml_edge in oml_tip_edges
            )
            checks.append({"connection": f"oml_{oml_idx}_to_tip_cap", "matched": matched})
        return {
            "checks": checks,
            "all_matched": all(bool(item["matched"]) for item in checks),
        }

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
            stream.write("".join(f"{value:12d}" for value in dims[start : start + 6]) + "\n")
        for block in blocks:
            for component in range(3):
                values = block.xyz[:, :, component].reshape(-1, order="F")
                for start in range(0, len(values), 3):
                    stream.write(
                        "".join(f"{value:24.16E}" for value in values[start : start + 3]) + "\n"
                    )


def _write_cgns_structured_surface(path: Path, blocks: Sequence[SurfaceBlock]) -> dict[str, object]:
    try:
        from cgnsutilities.cgnsutilities import Block, Grid, readGrid
    except (ImportError, ModuleNotFoundError) as exc:
        raise MeshBuildError(
            "CGNS export requires MDO Lab cgnsUtilities. Activate the mach-aero conda environment."
        ) from exc

    grid = Grid()
    grid.name = path.stem
    grid.cellDim = 2

    expected: list[dict[str, object]] = []
    for index, surface_block in enumerate(blocks, start=1):
        ni, nj, _ = surface_block.xyz.shape
        dims = np.asarray([ni, nj, 1], dtype=np.int32, order="F")
        coords = np.asfortranarray(surface_block.xyz[:, :, np.newaxis, :], dtype=np.float64)
        zone_name = f"{surface_block.name}.{index:05d}"
        grid.addBlock(Block(zone_name, dims, coords))
        expected.append({"name": zone_name, "dims": [int(ni), int(nj), 1]})

    grid.writeToCGNS(str(path))
    if not path.is_file() or path.stat().st_size == 0:
        raise MeshBuildError(f"cgnsUtilities did not create a valid file: {path}")

    check_grid = readGrid(str(path))
    if int(check_grid.cellDim) != 2:
        raise MeshBuildError(f"CGNS read-back reports cellDim={check_grid.cellDim}; expected 2.")
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
    te_thickness: float = 0.0,
    te_thickness_abs_floor: float = 0.0,
    te_base_points: int = 0,
    minimum_shape_metric: float = 1.0e-2,
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
    chordwise_distribution: str = "uniform",
    chordwise_beta: float = 2.0,
    spanwise_distribution: str = "uniform",
    spanwise_beta: float = 2.0,
    spanwise_allocation: str = "uniform",
    tip_smooth_iters: int = 0,
    tip_topology: str = "auto",
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
    if not (0.0 < minimum_shape_metric < 1.0):
        raise MeshBuildError("minimum_shape_metric must lie between 0 and 1.")
    if not (0.0 < maximum_adjacent_normal_angle_deg <= 180.0):
        raise MeshBuildError("maximum_adjacent_normal_angle_deg must lie between 0 and 180.")
    if oml_topology not in {"mid4", "split8", "cap4"}:
        raise MeshBuildError("oml_topology must be 'mid4', 'split8', or 'cap4'.")
    if not (0.0 <= tip_dome_scale <= 2.0):
        raise MeshBuildError("tip_dome_scale must lie between 0 (flat cap) and 2.")
    for label, mode in (
        ("chordwise_distribution", chordwise_distribution),
        ("spanwise_distribution", spanwise_distribution),
    ):
        if mode not in DISTRIBUTIONS:
            raise MeshBuildError(f"{label} must be one of {DISTRIBUTIONS}, got {mode!r}")
    if te_thickness and not (0.0 < te_thickness <= 0.05):
        raise MeshBuildError("te_thickness must lie between 0 and 0.05 chord (0 = leave as-is).")
    if te_thickness_abs_floor < 0.0:
        raise MeshBuildError("te_thickness_abs_floor must be >= 0 (metres, 0 = disabled).")
    if tip_topology not in ("auto", "cap4", "ring", "single"):
        raise MeshBuildError("tip_topology must be 'auto', 'cap4', 'ring', or 'single'.")
    if spanwise_distribution == "junction":
        raise MeshBuildError(
            "spanwise_distribution cannot be 'junction' -- that mode is a "
            "per-side chordwise rule; use 'cosine' to cluster at section kinks."
        )
    if oml_topology == "cap4":
        if cap_wrap_points < 5:
            raise MeshBuildError("cap_wrap_points must be at least 5.")
        # Upper bound raised from 0.15 to 0.45 on 2026-07-22.  The original
        # limit assumed cap_wrap_x meant a razor-thin band hugging the LE/TE
        # crown; used instead as a mid-chord seam it improves both the tip
        # cap and the OML monotonically (see SURFACE_MESH_LAWS.md).  0.45
        # matches split_x_fore's range -- past that the wrap and chord blocks
        # swap roles and the topology stops meaning what its name says.
        if not (0.01 <= cap_wrap_x <= 0.45):
            raise MeshBuildError("cap_wrap_x must lie between 0.01 and 0.45.")

    # OML surface points come from a geometry source behind a seam; the rest of
    # the mesher (spanwise refine, root snap, tip closure, QC) is source-
    # agnostic.  AeroSandboxOmlSource reproduces the former in-line path exactly.
    raw_oml = _oml_source_for(wing).raw_oml_blocks(
        OmlTopologyParams(
            oml_topology=oml_topology,
            points_per_block_side=points_per_block_side,
            cap_wrap_points=cap_wrap_points,
            cap_wrap_x=cap_wrap_x,
            split_x_fore=split_x_fore,
            dense_airfoil_points_per_surface=dense_airfoil_points_per_surface,
            minimum_te_thickness=minimum_te_thickness,
            te_thickness=te_thickness,
            te_thickness_abs_floor=te_thickness_abs_floor,
            te_base_points=te_base_points,
            chordwise_distribution=chordwise_distribution,
            chordwise_beta=chordwise_beta,
        )
    )
    raw_oml = _refine_spanwise(
        raw_oml,
        spanwise_panels_per_section,
        distribution=spanwise_distribution,
        beta=spanwise_beta,
        allocation=spanwise_allocation,
    )

    # Snap root edge to an exact y-plane — pyHyp requires a genuinely planar
    # symmetry boundary, and AeroSandbox can leave floating-point noise on it.
    section_centers_refined = []
    for j in range(raw_oml[0].shape[1]):
        boundary = np.concatenate([block[:-1, j, :] for block in raw_oml], axis=0)
        section_centers_refined.append(np.mean(boundary, axis=0))
    section_centers_refined = np.asarray(section_centers_refined)
    root_j = int(np.argmin(np.abs(section_centers_refined[:, 1])))

    root_points_before = np.concatenate([block[:, root_j, :] for block in raw_oml], axis=0)
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

    # The tip closure is independent of the OML blocking: both builders
    # consume only the four OML tip edges, and mid4/cap4 order those edges
    # identically ([LE wrap, lower, TE wrap, upper]).  Decoupling them lets
    # a mid4 wing use the camber-aligned cap4 cap, which avoids the
    # square-patch-on-a-postage-stamp problem of the ring+Coons closure
    # (that cap put points_per_side^2 nodes on ~0.1% of the wing area).
    resolved_tip = oml_topology if tip_topology == "auto" else tip_topology
    # (smoothing is applied to the returned cap blocks below)
    if resolved_tip == "single":
        raw_ring, raw_center, tip_groups = _build_tip_single(raw_oml)
    elif resolved_tip == "cap4":
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

    if tip_smooth_iters > 0:
        raw_ring = [_smooth_patch_interior(b, tip_smooth_iters) for b in raw_ring]
        raw_center = [_smooth_patch_interior(b, tip_smooth_iters) for b in raw_center]

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
        raise MeshBuildError("Cannot infer outward wingtip direction from the last two xsecs.")

    if tip_dome_scale > 0.0:
        tip_boundary = np.concatenate([block[:-1, -1, :] for block in raw_oml], axis=0)
        domed = _apply_tip_dome([*raw_ring, *raw_center], tip_boundary, tip_outward, tip_dome_scale)
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
    free_edges = _free_edge_audit(blocks, connection_tol, root_plane_y=root_plane_y)

    root_plane_ok = root_y_range <= connection_tol
    min_area = min(float(item["min_area"]) for item in qc_blocks)
    min_shape = min(float(item["min_shape_metric"]) for item in qc_blocks)
    min_scaled_jac = min(float(item["min_scaled_jacobian"]) for item in qc_blocks)
    min_alignment = min(float(item["min_triangle_normal_alignment"]) for item in qc_blocks)
    max_adjacent_normal_angle = max(
        float(item["max_adjacent_normal_angle_deg"]) for item in qc_blocks
    )
    area_floor = max(1e-20, characteristic_length**2 * 1e-14)
    shape_floor = float(minimum_shape_metric)
    alignment_floor = -0.25

    failure_reasons: list[dict[str, object]] = []
    if not connectivity["all_matched"]:
        unmatched = [
            item["connection"] for item in connectivity["checks"] if not bool(item["matched"])
        ]
        failure_reasons.append(
            {
                "check": "block_connectivity",
                "message": "One or more structured block edges do not match.",
                "unmatched_connections": unmatched,
            }
        )
    if not free_edges["closed_except_root"]:
        failure_reasons.append(
            {
                "check": "open_boundary_off_root_plane",
                "message": (
                    "Surface has free edges away from the root plane. pyHyp's "
                    "unattachedEdgesAreSymmetry would silently extrude these as "
                    "symmetry planes -- e.g. an unclosed wingtip."
                ),
                "off_root_free_edges": free_edges["off_root_free_edges"],
                "edges": [e for e in free_edges["edges"] if not e["on_root_plane"]],
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
    if not min_shape > shape_floor:
        worst = min(qc_blocks, key=lambda item: float(item["min_shape_metric"]))
        failure_reasons.append(
            {
                "check": "minimum_shape_metric",
                "message": "At least one surface quad is excessively skewed or stretched.",
                "block": worst["name"],
                "value": min_shape,
                "required_greater_than": shape_floor,
            }
        )
    if not min_alignment > alignment_floor:
        worst = min(qc_blocks, key=lambda item: float(item["min_triangle_normal_alignment"]))
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
        worst = max(qc_blocks, key=lambda item: float(item["max_adjacent_normal_angle_deg"]))
        failure_reasons.append(
            {
                "check": "adjacent_surface_normal_rotation",
                "message": (
                    "At least one block has excessive wall-normal rotation between adjacent cells."
                ),
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
        "tip_topology": resolved_tip,
        "tip_smooth_iters": tip_smooth_iters,
        "chordwise_distribution": chordwise_distribution,
        "chordwise_beta": chordwise_beta,
        "spanwise_distribution": spanwise_distribution,
        "spanwise_allocation": spanwise_allocation,
        "spanwise_beta": spanwise_beta,
        "minimum_te_thickness": minimum_te_thickness,
        "te_thickness_requested": te_thickness,
        "te_base_points": te_base_points,
        "minimum_shape_metric": shape_floor,
        "maximum_adjacent_normal_angle_deg": maximum_adjacent_normal_angle_deg,
        "characteristic_length": characteristic_length,
        "blocks": qc_blocks,
        "connectivity": connectivity,
        "free_edges": free_edges,
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
            "min_shape_metric": min_shape,
            "shape_floor": shape_floor,
            "min_scaled_jacobian": min_scaled_jac,
            "min_triangle_normal_alignment": min_alignment,
            "alignment_floor": alignment_floor,
            "max_adjacent_normal_angle_deg": max_adjacent_normal_angle,
            # Reported, not gated: these are the metrics a strategy
            # comparison is scored on, and gating them would reject the
            # existing validated recipes before there is anything better.
            "max_equiangle_skewness": max(
                float(item["max_equiangle_skewness"]) for item in qc_blocks
            ),
            "mean_equiangle_skewness": float(
                np.mean([float(item["mean_equiangle_skewness"]) for item in qc_blocks])
            ),
            "max_aspect_ratio": max(float(item["max_aspect_ratio"]) for item in qc_blocks),
            "max_growth_ratio": max(float(item["max_growth_ratio"]) for item in qc_blocks),
            "total_cells": int(sum(int(item["cells"]) for item in qc_blocks)),
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
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
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
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

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
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        if require_cgns_export:
            raise
        return report

    artifacts["cgns_surface"] = {
        "path": str(cgns_path),
        "sha256": _hash_file(cgns_path),
    }
    report["cgns"] = cgns_metadata
    report["artifacts"] = artifacts
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
