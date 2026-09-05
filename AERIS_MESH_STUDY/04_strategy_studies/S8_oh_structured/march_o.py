"""In-plane O-march: wall ring -> far-field circle, one section plane.

This is the "O" of the O-H grid, and it is built here rather than handed to
pyHyp on purpose.  pyHyp's hyperbolic march is what segmentation-faulted through
25 attempts on the D family, it is tuned to one exact surface, and its failure
mode is a crash with no diagnosis.  An algebraic march with an explicit
orthogonality condition at the wall cannot crash: every node is a closed-form
function of the wall ring, and the cell areas can be checked afterwards.

Construction, per ring node:

  1. an in-plane outward normal, smoothed along the ring so the two blunt
     trailing-edge corners do not fire two neighbouring normals across each
     other;
  2. a matching point on the far-field circle;
  3. an explicit layer-by-layer march along a direction that blends from the
     wall normal to the radial, with the normals recomputed on the layer just
     built;
  4. Laplacian smoothing of each new layer along the ring, with a strength that
     grows as the layer leaves the wall.

Step 4 is not cosmetic and step 3 does not work without it.  The first version
of this file drew a cubic Hermite from the wall to the circle, which is exact at
both ends and folds in the middle: on the tip section's concave lower-aft
surface the neighbouring curves crossed at about 50 mm out, 113 cells, at layers
35 to 51 of 65.  Converging normals off a concave wall are what smoothing exists
to relax, and no amount of end-point exactness substitutes for it.

The result is verified, not assumed: `march_section` returns the signed area of
every cell and the wall orthogonality angle.
"""

from __future__ import annotations

import numpy as np

Array = np.ndarray


#: How the marching plane is chosen.  "svd" best-fits the section ring, which is
#: the original behaviour and is kept selectable; "span_normal" forces the plane
#: normal to the spanwise axis.
#:
#: Why the choice exists.  A swept, tapered, twisted section's best-fit plane sits
#: up to 8 degrees off perpendicular-to-span.  The march then has to blend that
#: tilt away before the far field, and it does not finish in time: at eta 0.83 the
#: blend is 51 per cent complete, leaving 3.89 degrees, which at a 29 m radius is a
#: 1.97 m excursion in y against a local spanwise cell of 0.02 to 0.05 m.
#: Neighbouring rings interleave, the spanwise edges reverse, and 15 of 100 designs
#: fold.  A plane that is square to the span by construction has no tilt to blend.
#:
#: The risk this trades against is recorded rather than assumed: the section ring
#: is a genuine 3-D curve, so forcing a plane it does not lie in throws its nodes
#: out of plane, and the comment on the blend below records that tilting cells out
#: of the section plane once inverted 7522 of them near the WALL.  Far-field
#: folding and near-wall folding pull in opposite directions.
FRAME_MODE_DEFAULT = "span_normal"


def plane_frame(ring: Array, mode: str = FRAME_MODE_DEFAULT
                ) -> tuple[Array, Array, Array, Array, float]:
    """The plane a section is marched in: origin, two in-plane axes, normal, residual.

    `residual` is the largest out-of-plane distance of a ring node, so it measures
    directly what the chosen plane costs the wall: for "svd" it is the smallest
    possible by construction, and for "span_normal" it is how far the section
    genuinely departs from square-to-span.
    """
    origin = ring.mean(axis=0)
    centred = ring - origin
    if mode == "span_normal":
        normal = np.array([0.0, 1.0, 0.0])
        # e1 along the chord: the ring's longest in-plane extent, which puts the
        # frame in the same place the SVD would have and keeps the two modes
        # comparable rather than arbitrarily rotated against each other.
        flat = centred - np.outer(centred @ normal, normal)
        _u, _s, vt = np.linalg.svd(flat, full_matrices=False)
        e1 = vt[0] - (vt[0] @ normal) * normal
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(normal, e1)
        residual = float(np.abs(centred @ normal).max())
        return origin, e1, e2, normal, residual
    if mode != "svd":
        raise ValueError(f"unknown frame mode {mode!r}; expected 'svd' or 'span_normal'")
    _u, _s, vt = np.linalg.svd(centred, full_matrices=False)
    e1, e2, normal = vt[0], vt[1], vt[2]
    # SVD fixes the plane but not its handedness, and the handedness decides the
    # sign of every cell area.  Pin the plane normal to the spanwise axis so the
    # sign means "folded" rather than "this station came out mirrored".
    if normal[1] < 0.0:
        normal = -normal
    e2 = np.cross(normal, e1)
    residual = float(np.abs(centred @ normal).max())
    return origin, e1, e2, normal, residual


def geometric_distribution(n: int, first: float, total: float) -> tuple[Array, float]:
    """`n` positions on [0, total] with first interval `first` and constant growth.

    A tanh stretching is the usual choice and is wrong here.  The far field is
    40 root chords out and the first cell is 4.7 um, a ratio of 7.4e6, and over
    that range `tanh(b*s)/tanh(b)` saturates: the solver cannot find a `b` that
    places the first cell, and silently returns a distribution whose first cell
    is metres.  Constant geometric growth spans any ratio and reports the growth
    itself, which is the number a boundary layer is judged on.
    """
    if not 0.0 < first < total:
        raise ValueError(f"first cell {first} must be inside (0, {total})")
    target = total / first
    lo, hi = 1.0 + 1.0e-9, 3.0
    for _ in range(300):
        r = 0.5 * (lo + hi)
        got = (r ** (n - 1) - 1.0) / (r - 1.0)
        if got < target:
            lo = r
        else:
            hi = r
    r = 0.5 * (lo + hi)
    steps = first * (r ** np.arange(n) - 1.0) / (r - 1.0)
    steps *= total / steps[-1]
    return steps, float(r)


def _outward_normals(pts2: Array, smoothing: int) -> Array:
    """Unit outward normals of a closed 2D polygon, smoothed along the ring."""
    nxt = np.roll(pts2, -1, axis=0)
    prv = np.roll(pts2, 1, axis=0)
    tangent = nxt - prv
    tangent /= np.maximum(np.linalg.norm(tangent, axis=1, keepdims=True), 1.0e-30)
    normal = np.column_stack([tangent[:, 1], -tangent[:, 0]])

    # orient outward against the polygon's own signed area
    area = 0.5 * np.sum(pts2[:, 0] * nxt[:, 1] - nxt[:, 0] * pts2[:, 1])
    if area > 0:
        normal = -normal
    centroid = pts2.mean(axis=0)
    if np.sum(normal * (pts2 - centroid)) < 0:
        normal = -normal

    for _ in range(smoothing):
        normal = 0.5 * normal + 0.25 * (np.roll(normal, 1, axis=0) + np.roll(normal, -1, axis=0))
        normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1.0e-30)
    return normal


def march_section(
    ring: Array,
    *,
    n_normal: int,
    first_cell: float,
    farfield_radius: float,
    normal_smoothing: int = 4,
    layer_smoothing: float = 0.30,
    smoothing_growth: float = 6.0,
    radial_blend_power: float = 2.0,
    global_origin_xz: tuple[float, float] | None = None,
    frame_mode: str = FRAME_MODE_DEFAULT,
) -> tuple[Array, dict]:
    """March one closed ring out to a circle.  Returns (n_ring+1, n_normal, 3)."""
    origin, e1, e2, plane_normal, residual = plane_frame(ring, frame_mode)
    # Defect 21.  The march works in 2-D in-plane coordinates, so the wall layer
    # it produces is the ring PROJECTED onto the marching plane, not the ring.
    # With the SVD frame that costs nothing -- the plane is the best fit, so the
    # residual is ~1e-16 -- but a span-normal plane deliberately does not fit,
    # and projecting onto it moved the wing surface by up to 1.194e-03 m, about
    # 1100 ppm of root chord and the same order as the 1.0 mm blunt trailing
    # edge itself.  A fold fix that deforms the aircraft is not a fix.
    #
    # The plane has two jobs and only one of them needs to be span-normal:
    # WHERE THE SURFACE IS (eta 0) must be the exact loft, and WHICH WAY WE
    # MARCH (eta > 0) is what has to be square to the span.  So each node keeps
    # its own out-of-plane displacement and that displacement is decayed to zero
    # by the far field, where a true cylinder of parallel circles is what stops
    # neighbouring stations crossing.
    #
    # This cannot reintroduce the fold: the offset is at most 1.2 mm and
    # shrinking, against the ~2 m excursions that caused it.
    out_of_plane = (ring - origin) @ plane_normal
    basis = np.column_stack([e1, e2])
    pts2 = (ring - origin) @ basis
    centre2 = pts2.mean(axis=0)

    steps, growth = geometric_distribution(n_normal, first_cell, farfield_radius)
    # Blend parameter is the LAYER FRACTION, not the distance fraction.  With
    # geometric growth the distance fraction is under 1 percent until the last
    # three layers, so every blend keyed to it does nothing at all and then
    # everything at once, right where the cells are kilometres wide.  That
    # abruptness was the last source of negative cells.
    eta = np.arange(n_normal) / (n_normal - 1)

    # Monotone far-field angles: cumulative arc length relaxed toward uniform.
    # Each node's own polar angle is NOT monotone on a thin section near the
    # blunt base, so it cannot be used here.
    closed_ring = np.vstack([pts2, pts2[:1]])
    seg_len = np.linalg.norm(np.diff(closed_ring, axis=0), axis=1)
    arc_frac = np.concatenate([[0.0], np.cumsum(seg_len)[:-1]]) / seg_len.sum()
    uniform_frac = np.arange(len(pts2)) / len(pts2)
    frac = 0.85 * uniform_frac + 0.15 * arc_frac
    delta0 = pts2[0] - centre2
    theta0 = float(np.arctan2(delta0[1], delta0[0]))
    winding = np.sign(
        np.sum(closed_ring[:-1, 0] * closed_ring[1:, 1] - closed_ring[1:, 0] * closed_ring[:-1, 1])
    ) or 1.0
    theta_out = theta0 + winding * 2.0 * np.pi * frac
    unit_out = np.column_stack([np.cos(theta_out), np.sin(theta_out)])
    wall_radius_mean = float(np.linalg.norm(pts2 - centre2, axis=1).mean())

    layers = [pts2]
    current = pts2.copy()
    for k in range(1, n_normal):
        normals = _outward_normals(current, normal_smoothing)
        radial = current - centre2
        radial /= np.maximum(np.linalg.norm(radial, axis=1, keepdims=True), 1.0e-30)
        # weight toward radial: quick early turn keeps the march from focusing
        # inside a concave region, then it is essentially radial in the far field
        w = float(eta[k]) ** radial_blend_power
        direction = (1.0 - w) * normals + w * radial
        direction /= np.maximum(np.linalg.norm(direction, axis=1, keepdims=True), 1.0e-30)
        # Smooth the STEP, never the coordinates.  Relaxing absolute positions
        # drags the first layers along the wall -- it drove the median wall
        # orthogonality error from 0.2 degrees to 75 -- because one Laplacian
        # pass moves a node by the ring's curvature times its spacing squared,
        # which dwarfs a 4.7 um first cell.  Smoothing the increment leaves the
        # wall exactly where it is and relaxes only the direction field, which
        # is what a hyperbolic marcher's dissipation term actually does.
        step_vector = (steps[k] - steps[k - 1]) * direction
        passes = 1 + int(8.0 * float(eta[k]))
        for _ in range(passes):
            step_vector = step_vector + layer_smoothing * (
                np.roll(step_vector, 1, axis=0)
                - 2.0 * step_vector
                + np.roll(step_vector, -1, axis=0)
            )
        current = current + step_vector

        # Blend onto an explicitly uniform far-field circle over the outer
        # 60 percent of the march.
        #
        # Rescaling the radius alone is not enough and was the second cause of
        # negative cells: the march carries the wall's angular distribution
        # outward, so the leading edge's 76 um clustering is still a hairline
        # angular sector 35 m out.  Forcing those nodes onto a common radius
        # makes their cells vanish and lets their order flip -- 3085 folded
        # cells, every one of them in the outermost four layers.  Blending onto
        # a circle whose angles are monotone by construction fixes the order,
        # and doing it gradually leaves the boundary layer untouched.
        blend = float(np.clip((eta[k] - 0.50) / 0.50, 0.0, 1.0)) ** 2
        if blend > 0.0:
            target_ring = centre2 + (wall_radius_mean + steps[k]) * unit_out
            current = (1.0 - blend) * current + blend * target_ring
        layers.append(current.copy())

    out2 = np.stack(layers, axis=1)
    # decay the wall out-of-plane offset to zero over the same range the frame
    # blend uses, so the surface is exact at eta 0 and the far field is clean
    offset_decay = np.clip((1.0 - eta) / 0.60, 0.0, 1.0) ** 2

    if global_origin_xz is None:
        grid = origin[None, None, :] + out2 @ basis.T
        grid = grid + (out_of_plane[:, None, None] * offset_decay[None, :, None]
                       * plane_normal[None, None, :])
    else:
        # Rotate the marching plane from the section's own best-fit plane at the
        # wall to the global x-z plane at the far field, and slide its centre to
        # a common x-z point.
        #
        # Without this the block self-intersects.  Each station's far-field
        # circle inherits that station's plane, and on a swept wing neighbouring
        # planes are tilted relative to each other; two nearly coincident
        # 35 m circles at different tilts cross.  Every section marched
        # fold-free in 2D and the assembled block still carried 590 negative
        # cells, all of them out in the far field where the section frames
        # disagree.  Blending to a common frame makes the outer boundary a true
        # cylinder of parallel circles, which cannot intersect.
        # The global frame must be the LOCAL frame rotated, not a fresh pair of
        # world axes.  Picking (x, z) looks harmless and silently reverses the
        # handedness -- cross(x, z) is -y while the local frame's normal is +y --
        # so the xi-eta-zeta triad inverts partway through the blend and every
        # cell in the outer layers comes out negative.  That reads exactly like
        # a fold in the volume report and is not one.  Rodrigues rotation of the
        # local frame onto the spanwise axis preserves handedness by
        # construction.
        axis = np.cross(plane_normal, np.array([0.0, 1.0, 0.0]))
        sin_a = float(np.linalg.norm(axis))
        cos_a = float(plane_normal @ np.array([0.0, 1.0, 0.0]))
        if sin_a < 1.0e-12:
            e1g, e2g = e1.copy(), e2.copy()
        else:
            axis = axis / sin_a
            kx = np.array([[0.0, -axis[2], axis[1]],
                           [axis[2], 0.0, -axis[0]],
                           [-axis[1], axis[0], 0.0]])
            rot = np.eye(3) + sin_a * kx + (1.0 - cos_a) * (kx @ kx)
            e1g, e2g = rot @ e1, rot @ e2
        origin_g = np.array([global_origin_xz[0], origin[1], global_origin_xz[1]])
        n_layers = out2.shape[1]
        grid = np.empty((out2.shape[0], n_layers, 3))
        for k in range(n_layers):
            # Hold the exact section plane through the boundary layer.  Rotating
            # the frame by layer index everywhere tilts the first cells out of
            # the section plane and inverted 7522 of them, all near the wall.
            # The rotation is only needed where neighbouring stations' planes
            # disagree enough to cross, which is far outside the boundary layer.
            # Defect 20, MECHANISM IDENTIFIED, FIX NOT YET FOUND.
            #
            # This squared ramp reaches 1 only at the far field.  At eta 0.83 it
            # is 51 per cent blended, leaving 3.89 degrees of residual tilt, and
            # at a 29 m radius that is a 1.97 m excursion in y against a local
            # spanwise cell of 0.02 to 0.05 m.  Neighbouring rings interleave and
            # the spanwise edges REVERSE: on lhs100_seed42[65], 643 of them ran
            # backwards in y (most negative dy -0.036 m), which is exactly the
            # 644 folded cells that design reports.
            #
            # The obvious repair -- finish the blend earlier, linear to eta 0.70
            # -- was tried and is WORSE: 644 folds become 8429 on that design,
            # and 2813 to 8325 on four others.  Rotating the frame over a shorter
            # eta range turns it faster per layer and tilts cells out of the
            # section plane, which is the failure recorded above at 7522 cells
            # near the wall.  The two failure modes pull in opposite directions.
            #
            # The tilt exists because `plane_frame` best-fits each section ring
            # by SVD, and a swept, tapered, twisted section's best-fit plane is
            # not perpendicular to the span.  A march in a plane whose normal IS
            # the span direction would have no tilt to blend away at all; that is
            # the next thing to try, and it is a larger change than a ramp.
            w = float(np.clip((eta[k] - 0.40) / 0.60, 0.0, 1.0)) ** 2
            a1 = (1.0 - w) * e1 + w * e1g
            a1 /= np.linalg.norm(a1)
            a2 = (1.0 - w) * e2 + w * e2g
            a2 = a2 - (a2 @ a1) * a1
            a2 /= np.linalg.norm(a2)
            org = (1.0 - w) * origin + w * origin_g
            grid[:, k, :] = (org + out2[:, k, 0:1] * a1 + out2[:, k, 1:2] * a2
                             + out_of_plane[:, None] * offset_decay[k] * plane_normal)
    grid = np.concatenate([grid, grid[:1]], axis=0)  # explicit periodic closure

    p = np.concatenate([out2, out2[:1]], axis=0)
    a = p[:-1, :-1]
    b = p[1:, :-1]
    c = p[1:, 1:]
    d = p[:-1, 1:]

    def cross2(u: Array, w: Array) -> Array:
        # NumPy 2 removed the 2-D form of np.cross
        return u[..., 0] * w[..., 1] - u[..., 1] * w[..., 0]

    area = 0.5 * (cross2(b - a, d - a) + cross2(d - c, b - c))
    tang = np.roll(p[:-1, 0], -1, axis=0) - np.roll(p[:-1, 0], 1, axis=0)
    up = p[:-1, 1] - p[:-1, 0]
    cosang = np.sum(tang * up, axis=1) / np.maximum(
        np.linalg.norm(tang, axis=1) * np.linalg.norm(up, axis=1), 1e-30
    )
    ortho = np.degrees(np.arccos(np.clip(cosang, -1.0, 1.0)))
    first = np.linalg.norm(p[:, 1] - p[:, 0], axis=1)
    outer_r = np.linalg.norm(p[:, -1] - centre2, axis=1)

    report = {
        "shape": list(grid.shape),
        "planarity_residual_m": residual,
        "min_cell_area_m2": float(area.min()),
        "negative_cells": int((area <= 0.0).sum()),
        "wall_orthogonality_worst_deg": float(np.abs(ortho - 90.0).max()),
        "wall_orthogonality_p99_deg": float(np.percentile(np.abs(ortho - 90.0), 99)),
        "wall_orthogonality_median_deg": float(np.median(np.abs(ortho - 90.0))),
        "wall_orthogonality_worst_index": int(np.argmax(np.abs(ortho - 90.0))),
        "first_cell_min_m": float(first.min()),
        "first_cell_max_m": float(first.max()),
        "farfield_radius_m": float(farfield_radius),
        "outer_radius_min_m": float(outer_r.min()),
        "outer_radius_max_m": float(outer_r.max()),
        "normal_growth_ratio": float(growth),
    }
    return grid, report


#: Smoothing ladder.  More smoothing removes folds and costs wall orthogonality,
#: so the march climbs it only as far as it has to.  This is the same idea as
#: S6's governed epsE ladder, except it is chosen by measurement rather than by
#: hand, and a failure here is a reported number rather than a segmentation fault.
SMOOTHING_LADDER = (4, 8, 15, 25, 40, 60)


def march_section_auto(ring: Array, min_smoothing: int = 0, **kwargs) -> tuple[Array, dict]:
    """March a ring, climbing the smoothing ladder until no cell is folded.

    The fold test here is the IN-PLANE one: signed areas of the quads inside a
    single section.  It cannot see a fold that lives BETWEEN two neighbouring
    sections, because it never looks at more than one.  On lhs100_seed42[65] the
    in-plane test is clean on every section and the assembled hexes carry 645
    folds, so the ladder stopped at its first rung with an invalid grid.

    `min_smoothing` is how the caller raises the floor after seeing the
    assembled volume: `build_volume` climbs the same ladder on the 3D hex
    volumes and re-marches every section at the higher floor.  Defect 19.
    """
    attempts = []
    for smoothing in SMOOTHING_LADDER:
        if smoothing < min_smoothing:
            continue
        grid, report = march_section(ring, normal_smoothing=smoothing, **kwargs)
        attempts.append({
            "normal_smoothing": smoothing,
            "negative_cells": report["negative_cells"],
            "wall_orthogonality_median_deg": report["wall_orthogonality_median_deg"],
        })
        if report["negative_cells"] == 0:
            report["normal_smoothing"] = smoothing
            report["ladder_attempts"] = attempts
            report["converged"] = True
            return grid, report
    report["normal_smoothing"] = SMOOTHING_LADDER[-1]
    report["ladder_attempts"] = attempts
    report["converged"] = False
    return grid, report
