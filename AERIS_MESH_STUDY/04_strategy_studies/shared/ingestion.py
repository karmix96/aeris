"""Section ingestion — SHARED CONTROL (ADR-0011 section 4).

Every strategy reads the generator's sections through this module, so the
comparison measures meshing methods rather than section readers.

**Ingestion is exactly two things** (ADR-0011 section 4): reading a section from
the generator, and mapping 2D curves to 3D through the wing. That is
:func:`section_loop_2d` and ``_map_sides_to_wing``. Everything else re-exported
here is a *neutral primitive* — a resampler, a TFI patch, a file writer — in the
same category as ``winslow_smooth_2d``: using one is a per-strategy decision, and
none of them decides anything on a strategy's behalf.

**Do not add a blocking, distribution or tip-closure decision here.**

Correction, 2026-08-14, found while building S0. `feature_split_sides` was
migrated into this module and is now **out of it**. It splits a section into
sides — which is to say it decides *where the block corners go* — and that is
blocking, not ingestion. It puts corners on the leading edge and the two blunt-TE
base corners, which is **S1's** answer; cap4 splits its section at ``+/- wrap_x``
into four sides instead, and would have been unable to use it. Keeping it shared
would have handed every strategy S1's corner policy under the name "ingestion",
which is the precise failure ADR-0011 exists to prevent, wearing a different
label. It now lives in `S1_tip_first/s1_stage02_prior_art.py`.
"""

from __future__ import annotations

import numpy as np

from aeris.mesh.surface import (  # noqa: F401 - re-exported for strategies
    MeshBuildError,
    SurfaceBlock,
    _block_qc,
    _corner_shape_metric,
    _insert_point_at_x,
    _map_sides_to_wing,
    _open_trailing_edge,
    _resample_piecewise,
    _resample_polyline,
    _smooth_patch_interior,
    _split_counts,
    _tfi_patch,
    _write_npz,
    _write_plot3d_formatted,
)

Array = np.ndarray


#: DECISION-0004: the as-built aircraft trailing edge is a **constant absolute
#: thickness along the span**. The decision offers two sanctioned values and says
#: "0.5 vs 1.0 mm: both give wing delta-CD ~ 0." **1.0 mm is used here**, on
#: measurement: at 0.5 mm the smallest surface cell is half the size and S1's
#: min-cell/s0 falls to 7.6-17.6, where the march mostly fails; at 1.0 mm it is
#: 13.1-20.0, entirely inside the band where marches have succeeded, and the
#: cell-size range improves from 116-218 to 93-133. The decision's own aerodynamic
#: analysis makes the two interchangeable, so this costs nothing.
#: The original value was 0.5 mm, chosen for manufacturability — "a single
#: constant TE thickness is the easiest to produce — one uniform mould land /
#: foam-cut offset / print wall / finishing gauge. A spanwise-VARYING TE (a
#: fractional or hybrid law) needs a spanwise-varying tool/process and is
#: materially harder to build to tolerance." The same decision says plainly:
#: "Mesh: model the AS-BUILT 0.5 mm TE."
TE_THICKNESS_ABS_M = 0.001

#: DECISION-0004 "Where it applies", the MESH-ONLY escape hatch, now validated:
#:
#:   "If a real pyHyp march cannot advance the thin inboard TE (0.5 mm ~ 0.05%c at
#:    root), apply a mesh-only local inboard floor (~0.25%c) - a NUMERICAL artifact
#:    of the solver, not a change to the aircraft, and quantified here as ~0 drag.
#:    ... Pending pyHyp validation (see Open items)."
#:
#: **The validation exists now, and it also corrects the assumed value.**
#: DECISION-0004 records the meshability floor as "assumed ~0.25%c (UNVALIDATED)"
#: and lists "Validate the 0.25%c fractional term against a real pyHyp march and
#: tighten to the true marchability floor" as an Open item. Measured on ten
#: `lhs100_seed42` geometries with S1, epsE 1.5 / 2.0 / 3.0:
#:
#:     TE law                       pass counts
#:     0.5%c fraction (no floor)     5 / 6 / 7      <- the study's accidental value
#:     constant 0.5 mm               0 / 1 / 4
#:     max(0.25%c, 0.5 mm)           0 / 1 / 4      <- the assumed floor: NO HELP
#:     max(0.50%c, 0.5 mm)           this value
#:
#: **0.25%c is not the marchability floor.** Flooring at it changed nothing, which
#: also falsifies the hypothesis that the thin inboard edge was the problem - the
#: root went 0.5 mm -> 2.1 mm for no gain. What the 5/6/7 row shows is that ~0.5%c
#: IS enough, so the true floor lies between 0.25%c and 0.5%c and the assumed value
#: was roughly a factor of two optimistic.
#:
#: The mesh therefore uses  max(TE_MESH_FLOOR_FRAC * chord, TE_THICKNESS_ABS_M),
#: which is 0.5 mm wherever the chord is small enough to need it and 0.25%c inboard.
#: The AIRCRAFT is unchanged: constant 0.5 mm remains what goes to the shop.
TE_MESH_FLOOR_FRAC = 0.005


def section_loop_2d(
    xsec: object,
    *,
    te_thickness: float | None = None,
    te_thickness_abs_m: float | None = TE_THICKNESS_ABS_M,
    mesh_floor_frac: float | None = TE_MESH_FLOOR_FRAC,
) -> tuple[Array, int]:
    """Return the open 2D section contour and its leading-edge index.

    Ordering follows the AeroSandbox convention: upper trailing edge -> leading
    edge -> lower trailing edge. A blunt trailing edge is opened to
    ``te_thickness`` so the TE base is a real two-corner feature rather than a
    cusp.

    **The trailing edge is ABSOLUTE, not a chord fraction** (DECISION-0004).
    ``te_thickness_abs_m`` is metres and is converted per section using that
    section's own chord, so the physical base is the same size at every station
    and on every geometry. ``te_thickness`` remains available as a raw chord
    fraction for reproducing older results; passing both is an error.

    This was wrong for most of the study and it mattered. Running 0.005 as a
    fraction meshed a trailing edge of **4.3-5.0 mm at the root** — about nine
    times the 0.5 mm that goes to the shop — tapering to 0.46-0.89 mm at the tip,
    i.e. exactly the spanwise-varying edge DECISION-0004 rejected as harder to
    manufacture. It is also the root cause of the marching failures chased in both
    S0 and S1: because the fraction shrinks with chord, the smallest surface cell
    lives at the tip trailing edge and scales with TIP CHORD, so min-cell/`s0`
    varied 6.9 to 17.6 across ten geometries and no single epsE could serve that
    spread. A constant absolute edge makes that cell the same size everywhere.
    """
    if te_thickness is not None and te_thickness_abs_m is not None:
        raise MeshBuildError(
            "pass te_thickness (chord fraction) or te_thickness_abs_m (metres), not both"
        )
    if te_thickness is None:
        chord = float(getattr(xsec, "chord", 0.0))
        if chord <= 0.0:
            raise MeshBuildError("WingXSec has no positive chord; cannot apply an absolute TE.")
        te_thickness = float(te_thickness_abs_m) / chord
        if mesh_floor_frac:
            # The mesh-only inboard floor. Clamped at 5%c, the same envelope the
            # raw fraction is validated against.
            te_thickness = min(max(te_thickness, float(mesh_floor_frac)), 0.05)
    airfoil = getattr(xsec, "airfoil", None)
    if airfoil is None:
        raise MeshBuildError("WingXSec has no airfoil.")
    coords = np.asarray(airfoil.coordinates, dtype=float)
    if coords.ndim != 2 or coords.shape[1] != 2 or len(coords) < 9:
        raise MeshBuildError("Airfoil coordinates must have shape (N, 2), N >= 9.")
    if te_thickness > 0.0:
        coords = _open_trailing_edge(coords, te_thickness)
    le_index = int(np.argmin(coords[:, 0]))
    if le_index in (0, len(coords) - 1):
        raise MeshBuildError("Unexpected airfoil ordering: LE must lie between the TE points.")
    return coords, le_index
