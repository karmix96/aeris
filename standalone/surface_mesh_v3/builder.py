"""Surface mesh v3 — an all-quad structured OML for the AERIS BWB.

The geometry this meshes (verified, not assumed)
------------------------------------------------
``configs/geometry/bwb.yaml`` sets ``pygeo.tip: none`` and
``build_pygeo`` passes ``squareTeTip=True, bluntTe=False, roundedTe=False``.
So the master loft is exactly two B-spline patches:

* ``surfs[0]`` upper, ``surfs[1]`` lower;
* ``u`` runs TE (0) -> LE (1), ``v`` runs root (0) -> tip (1);
* they meet EXACTLY at u=0 and u=1 (measured gap 0.0 at every v);
* the tip (v=1) is **flat and open** — a square cut. There is no tip surface
  in the master geometry.
* the TE is **sharp** in the master; DECISION-0004's constant 0.5 mm blunt TE
  is a downstream transform applied here.

The closed half-model surface therefore needs four families of quads, and the
blocking below is a direct consequence of that geometry rather than a choice:

    upper     the upper OML                    TE shoulder -> LE, root -> tip
    lower     the lower OML                    TE shoulder -> LE, root -> tip
    te_base   the blunt-TE base strip          lower shoulder -> upper, root -> tip
    tip_cap   the flat square-cut tip face     (built by tipcap.py)

The root (v=0) stays open: it is the symmetry plane.

Why the trailing edge is its own block
--------------------------------------
The first v3 prototype folded the base into the OML blocks and sized the OML's
aft cell to match the base cell so the size transition would be 1.0. It does
achieve that, but a 0.5 mm base resolved with 3 nodes forces 0.125 mm cells
into a block whose spanwise cells are 72 mm — measured aspect ratio 375 spread
across the whole aft OML. Giving the base its own two-cell-wide strip confines
that anisotropy to the strip, where it is unavoidable and harmless, and lets
the OML be sized by the surface's own curvature. The OML and the base are
different features and they get different blocks.

Spacing
-------
Every distribution comes from a gradation-limited size field built out of
measured geometry (leading-edge radius, base thickness, local curvature) — see
``spacing.py``. There is no tuned clustering exponent anywhere in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from standalone.surface_mesh_v3.spacing import (
    cells_for,
    curvature_spacing,
    grade,
    leading_edge_radius,
    place,
    resample_by_arclength,
)

Array = np.ndarray


class BuildError(RuntimeError):
    """The requested surface cannot be built as specified."""


# ------------------------------------------------------------------ spec ---
@dataclass(frozen=True)
class SurfaceSpec:
    """Everything the builder needs, in physical units wherever possible."""

    # --- resolution ---------------------------------------------------------
    h_scale: float = 1.0
    """THE resolution control. Multiplies every target cell size, so 1/1.4
    is one finer rung of the fidelity ladder. Node counts are DERIVED from the
    resulting size field, not specified.

    This is the architectural point of v3. Specifying ``chord_points`` instead
    forces the placement routine to rescale the whole size field to hit that
    count, which silently discards the geometric spacing law: measured at 49
    chordwise points, the leading-edge cell came out 1.0 mm where the curvature
    law asked for 3.2 mm, over-refining the nose 3x and driving surface aspect
    ratio to 102. Sizing the mesh from geometry and letting the count follow is
    also what makes the structured and unstructured families comparable, since
    the unstructured mesher is driven by the same field."""
    chord_points: int | None = None
    """Override the derived chordwise count. Leave None for the law."""
    span_points: int | None = None
    """Override the derived spanwise count. Leave None for the law."""
    te_base_points: int = 5
    """Nodes ACROSS the full blunt base, lower shoulder to upper shoulder."""

    # --- geometry policy (physical) -----------------------------------------
    te_thickness_m: float = 5.0e-4
    """Constant absolute blunt-TE thickness — DECISION-0004. Note this
    SUPERSEDES the 0.5 %c figure in configs/cfd/SURFACE_MESH_LAWS.md laws 9-10,
    which predates the ADR. At the 0.9 m root the two differ by 9x."""

    # --- spacing law --------------------------------------------------------
    le_radius_cells: float = 6.0
    """Cells across the leading-edge radius. The LE cell size is
    ``le_radius / le_radius_cells``, so the nose is resolved by a fixed number
    of cells whatever the section or the chord."""
    max_turn_deg: float = 8.0
    """The surface may not turn more than this across one chordwise cell."""
    gradation: float = 0.15
    """Maximum change in target cell size per unit length: a growth-ratio bound
    of about 1 + this. Enforced inside node placement, so the realised growth
    ratio is bounded by construction."""
    target_aspect_ratio: float = 8.0
    """Spanwise cell / median chordwise cell. The one place a preference rather
    than a measurement enters the spacing."""
    span_law: str = "chord_proportional"
    """``chord_proportional`` holds surface aspect ratio roughly constant along
    a wing that tapers 7:1; ``arclength`` spaces uniformly along the span."""

    # --- sampling -----------------------------------------------------------
    dense_chord: int = 801
    dense_span: int = 401

    def validate(self) -> None:
        if self.h_scale <= 0:
            raise BuildError("h_scale must be positive")
        if self.chord_points is not None and self.chord_points < 9:
            raise BuildError("chord_points must be at least 9")
        if self.span_points is not None and self.span_points < 3:
            raise BuildError("span_points must be at least 3")
        if self.te_base_points < 2:
            raise BuildError("te_base_points must be at least 2")
        if self.te_thickness_m <= 0:
            raise BuildError("te_thickness_m must be positive (DECISION-0004: 0.5 mm)")
        if self.span_law not in ("chord_proportional", "arclength"):
            raise BuildError("span_law must be chord_proportional or arclength")


# ------------------------------------------------------- master sampling ---
class MasterSurface:
    """The pyGeo loft, sampled directly — no planarisation, no slice interpolation."""

    def __init__(self, build: Any) -> None:
        surfs = build.geometry.surfs
        if len(surfs) < 2:
            raise BuildError("expected an upper and a lower master patch")
        self.upper = surfs[0]
        self.lower = surfs[1]

    def station(self, v: float, u: Array) -> tuple[Array, Array]:
        vv = np.full_like(u, float(v))
        return (
            np.asarray(self.upper(u, vv), dtype=float),
            np.asarray(self.lower(u, vv), dtype=float),
        )

    def edge(self, u_value: float, v: Array) -> Array:
        return np.asarray(self.upper(np.full_like(v, u_value), v), dtype=float)


@dataclass
class Station:
    """One spanwise station: the blunted section and its local frame."""

    v: float
    upper: Array  # (n, 3) TE shoulder -> LE
    lower: Array  # (n, 3) TE shoulder -> LE
    chord_m: float
    chord_axis: Array
    thickness_axis: Array
    span_axis: Array
    te_thickness_m: float
    le_radius_m: float


def _unit(vector: Array) -> Array:
    norm = float(np.linalg.norm(vector))
    if norm < 1e-14:
        raise BuildError("degenerate direction vector")
    return vector / norm


def blunt_station(master: MasterSurface, v: float, u_dense: Array, te_thickness_m: float) -> Station:
    """Sample a station and open its sharp TE to the registered thickness.

    The opening is the classical one: each surface moves along the section's own
    thickness axis by half the required gap, ramped linearly in chordwise
    fraction from zero at the LE to full at the TE. Doing it in the station
    frame keeps the opening perpendicular to the chord line at every twist and
    dihedral angle, which a global-axis offset would not.
    """
    dv = 2.5e-4
    v_lo, v_hi = max(0.0, v - dv), min(1.0, v + dv)
    one = np.array([1.0])
    q_lo = 0.5 * (
        np.asarray(master.upper(one, np.array([v_lo])), float).ravel()
        + np.asarray(master.upper(np.array([0.0]), np.array([v_lo])), float).ravel()
    )
    q_hi = 0.5 * (
        np.asarray(master.upper(one, np.array([v_hi])), float).ravel()
        + np.asarray(master.upper(np.array([0.0]), np.array([v_hi])), float).ravel()
    )
    span_axis = _unit(np.array([0.0, (q_hi - q_lo)[1], (q_hi - q_lo)[2]]))

    up, lo = master.station(v, u_dense)
    le, te = up[-1].copy(), up[0].copy()
    raw_chord = te - le
    chord_axis = _unit(raw_chord - span_axis * float(raw_chord @ span_axis))
    if chord_axis[0] < 0:
        chord_axis = -chord_axis
    chord_m = float(raw_chord @ chord_axis)
    thickness_axis = _unit(np.cross(chord_axis, span_axis))
    if thickness_axis[2] < 0:
        thickness_axis = -thickness_axis

    existing = float(np.linalg.norm(up[0] - lo[0]))
    half_gap = max(0.0, 0.5 * (te_thickness_m - existing))
    if half_gap > 0.0:
        fu = np.clip(((up - le) @ chord_axis) / chord_m, 0.0, 1.0)
        fl = np.clip(((lo - le) @ chord_axis) / chord_m, 0.0, 1.0)
        up = up + half_gap * fu[:, None] * thickness_axis[None, :]
        lo = lo - half_gap * fl[:, None] * thickness_axis[None, :]

    loop = np.column_stack(
        [
            np.concatenate([(up[::-1] - le) @ chord_axis, (lo[1:] - le) @ chord_axis]) / chord_m,
            np.concatenate(
                [(up[::-1] - le) @ thickness_axis, (lo[1:] - le) @ thickness_axis]
            )
            / chord_m,
        ]
    )
    try:
        le_radius = leading_edge_radius(loop) * chord_m
    except Exception:
        le_radius = 0.01 * chord_m

    return Station(
        v=float(v),
        upper=up,
        lower=lo,
        chord_m=chord_m,
        chord_axis=chord_axis,
        thickness_axis=thickness_axis,
        span_axis=span_axis,
        te_thickness_m=float(np.linalg.norm(up[0] - lo[0])),
        le_radius_m=float(le_radius),
    )


# --------------------------------------------------------------- spacing ---
def chordwise_field(station: Station, spec: SurfaceSpec) -> list[tuple[Array, Array]]:
    """``(arc, target size)`` for the upper and lower surfaces of one station.

    Two physical requirements, combined as a pointwise minimum:

    * the LE cell is ``le_radius / le_radius_cells`` — a fixed number of cells
      across the nose, whatever the chord;
    * no cell may turn the surface by more than ``max_turn_deg``.

    The trailing edge deliberately does NOT appear. The base is a separate
    block, so the OML aft cell is set by the surface's own curvature instead of
    being dragged down to the 0.125 mm base cell — which is what produced
    aspect ratio 375 across the aft OML in an earlier prototype.
    """
    s_le = station.le_radius_m / max(spec.le_radius_cells, 1e-9)
    out = []
    for surface in (station.upper, station.lower):
        seg = np.linalg.norm(np.diff(surface, axis=0), axis=1)
        s = np.concatenate(([0.0], np.cumsum(seg)))
        h = np.minimum(curvature_spacing(surface, spec.max_turn_deg), s[-1])
        h[-1] = min(h[-1], s_le)
        out.append((s, grade(s, h * spec.h_scale, spec.gradation)))
    return out


def chordwise_positions(
    station: Station, spec: SurfaceSpec, n: int
) -> tuple[Array, Array]:
    """Normalised arc positions along each surface, TE shoulder (0) to LE (1)."""
    return tuple(  # type: ignore[return-value]
        place(s, h, n, spec.gradation) / s[-1] for s, h in chordwise_field(station, spec)
    )


def chordwise_count(master: MasterSurface, spec: SurfaceSpec, u_dense: Array) -> int:
    """Chordwise node count implied by the size law.

    A structured block needs ONE count for every station, but each station's
    field asks for its own. The maximum is taken, so no station is coarser than
    its geometry requires; inboard stations then carry slightly more resolution
    than they asked for, which is the correct direction to err.
    """
    worst = 0.0
    for v in np.linspace(0.0, 1.0, 9):
        st = blunt_station(master, v, u_dense, spec.te_thickness_m)
        for s, h in chordwise_field(st, spec):
            worst = max(worst, cells_for(s, h))
    return max(9, int(np.ceil(worst)) + 1)


def spanwise_field(
    master: MasterSurface, spec: SurfaceSpec, u_dense: Array, n_chord: int
) -> tuple[Array, Array, Array]:
    """``(arc, target size, v)`` along the quarter-chord line.

    ``chord_proportional`` is the aspect-ratio-equalising law: surface aspect
    ratio is (spanwise cell)/(chordwise cell), and the chordwise cell scales
    with the local chord, so setting the spanwise cell to
    ``target_aspect_ratio`` times the LOCAL median chordwise cell holds the
    aspect ratio roughly constant on a wing that tapers 7:1. The median
    chordwise cell is measured at sample stations, not modelled.
    """
    v_dense = np.linspace(0.0, 1.0, spec.dense_span)
    le = master.edge(1.0, v_dense)
    te = master.edge(0.0, v_dense)
    quarter = le + 0.25 * (te - le)
    s = np.concatenate(([0.0], np.cumsum(np.linalg.norm(np.diff(quarter, axis=0), axis=1))))

    if spec.span_law == "arclength":
        h = np.full_like(s, spec.h_scale * float(np.median(np.diff(s))) * 20.0)
    else:
        sample_v = np.linspace(0.0, 1.0, 9)
        median_cell = []
        for v in sample_v:
            st = blunt_station(master, v, u_dense, spec.te_thickness_m)
            pos_u, _ = chordwise_positions(st, spec, n_chord)
            pts = resample_by_arclength(st.upper, pos_u)
            median_cell.append(float(np.median(np.linalg.norm(np.diff(pts, axis=0), axis=1))))
        h = spec.target_aspect_ratio * np.interp(v_dense, sample_v, median_cell)
    return s, grade(s, h, spec.gradation), v_dense


def spanwise_parameters(
    master: MasterSurface, spec: SurfaceSpec, u_dense: Array, n_chord: int
) -> tuple[Array, int]:
    """Span parameters ``v``, with the count derived from the size field."""
    s, h, v_dense = spanwise_field(master, spec, u_dense, n_chord)
    n = spec.span_points if spec.span_points is not None else max(3, int(np.ceil(cells_for(s, h))) + 1)
    nodes = place(s, h, n, spec.gradation)
    v_out = np.interp(nodes, s, v_dense)
    v_out[0], v_out[-1] = 0.0, 1.0
    return v_out, n


# -------------------------------------------------------------- assembly ---
def build_oml(build: Any, spec: SurfaceSpec) -> tuple[dict[str, Array], dict[str, Any]]:
    """Build the three OML blocks. The tip cap is added by ``tipcap.py``.

    Index convention, shared by all three blocks: ``j`` runs root (0) to tip.
    For ``upper``/``lower`` ``i`` runs from the TE shoulder to the LE. For
    ``te_base`` ``i`` runs from the LOWER shoulder to the UPPER shoulder, so
    it shares its two edges exactly with the two OML blocks.
    """
    spec.validate()
    master = MasterSurface(build)
    u_dense = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, spec.dense_chord)))

    n_chord = spec.chord_points or chordwise_count(master, spec, u_dense)
    v_values, n_span = spanwise_parameters(master, spec, u_dense, n_chord)
    stations = [blunt_station(master, v, u_dense, spec.te_thickness_m) for v in v_values]

    upper_cols, lower_cols, base_cols = [], [], []
    for st in stations:
        pos_u, pos_l = chordwise_positions(st, spec, n_chord)
        col_u = resample_by_arclength(st.upper, pos_u)
        col_l = resample_by_arclength(st.lower, pos_l)
        upper_cols.append(col_u)
        lower_cols.append(col_l)
        # The base is a straight segment between the two shoulders, so the two
        # OML blocks and the base block share their edges node-for-node.
        t = np.linspace(0.0, 1.0, spec.te_base_points)[:, None]
        base_cols.append((1.0 - t) * col_l[0][None, :] + t * col_u[0][None, :])

    _ = n_span
    blocks = {
        "upper": np.stack(upper_cols, axis=1),
        "lower": np.stack(lower_cols, axis=1),
        "te_base": np.stack(base_cols, axis=1),
    }
    return blocks, _report(stations, spec, blocks)


def _report(stations: list[Station], spec: SurfaceSpec, blocks: dict[str, Array]) -> dict[str, Any]:
    te = np.array([s.te_thickness_m for s in stations])
    chord = np.array([s.chord_m for s in stations])
    return {
        "topology": "oml3 (upper + lower + te_base), flat open tip",
        "master_geometry": "pyGeo tip=none, squareTeTip=True — flat square-cut tip, sharp TE",
        "blocks": {k: [int(v.shape[0]), int(v.shape[1])] for k, v in blocks.items()},
        "cells": int(sum((v.shape[0] - 1) * (v.shape[1] - 1) for v in blocks.values())),
        "spec": {k: getattr(spec, k) for k in spec.__dataclass_fields__},
        "stations": len(stations),
        "te_thickness_m": {"min": float(te.min()), "max": float(te.max())},
        "te_thickness_frac_chord": {
            "root": float(te[0] / chord[0]),
            "tip": float(te[-1] / chord[-1]),
        },
        "chord_m": {"root": float(chord[0]), "tip": float(chord[-1])},
        "le_radius_m": {"root": stations[0].le_radius_m, "tip": stations[-1].le_radius_m},
    }
