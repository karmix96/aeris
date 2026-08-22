"""QC metric definitions, orientation and artifact writing — SHARED CONTROL.

ADR-0011 section 4: QC metric *definitions*, gate thresholds, and the verifier are
shared so that a comparison between strategies is a comparison between meshing
methods and not between quality metrics. **Migrated unchanged** from
`04_strategy_prototypes/stage02_common.py`, so every number recorded in `status`
remains directly comparable.

`winslow_smooth_2d` is a generic operator and is shared under ADR-0011 section 4.1;
using it is a per-strategy decision. COMMON_BRIEF section 1 records that it made
S1's Stage 02 tip cap **worse** (-0.0363 -> -0.0499), which is a measurement about
that cap, not about the operator.
"""

from __future__ import annotations

import numpy as np

from .ingestion import Array, SurfaceBlock, _block_qc, _write_npz, _write_plot3d_formatted


def winslow_smooth_2d(
    patch: Array,
    iterations: int = 200,
    relaxation: float = 1.0,
    fixed_edges: tuple[bool, bool, bool, bool] = (True, True, True, True),
) -> Array:
    """Elliptic (Winslow) smoothing of a structured 2D patch.

    Laplacian smoothing averages a node toward its neighbours in PHYSICAL space,
    which shrinks the grid and slides nodes along the boundary direction. Winslow
    instead solves for the mapping whose computational coordinates are harmonic
    functions of the physical ones,

        alpha * x_xi_xi - 2 * beta * x_xi_eta + gamma * x_eta_eta = 0

    with alpha = x_eta . x_eta, beta = x_xi . x_eta, gamma = x_xi . x_xi. For a
    convex domain the resulting map obeys a maximum principle and cannot fold,
    and in practice it strongly un-folds non-convex ones too. That is the
    property being tested here; Laplacian smoothing has no such guarantee, which
    is why every earlier attempt in this stage failed.

    ``fixed_edges`` holds (i=0, i=last, j=0, j=last). Edges left free are updated
    by one-sided extrapolation so a block interface can relax instead of pinning
    the fold in place.
    """
    p = patch.astype(float).copy()
    ni, nj, _ = p.shape
    if ni < 3 or nj < 3:
        return p
    for _ in range(max(0, int(iterations))):
        x_xi = 0.5 * (p[2:, 1:-1, :] - p[:-2, 1:-1, :])
        x_eta = 0.5 * (p[1:-1, 2:, :] - p[1:-1, :-2, :])
        alpha = np.sum(x_eta * x_eta, axis=2)[..., None]
        beta = np.sum(x_xi * x_eta, axis=2)[..., None]
        gamma = np.sum(x_xi * x_xi, axis=2)[..., None]
        cross = p[2:, 2:, :] - p[:-2, 2:, :] - p[2:, :-2, :] + p[:-2, :-2, :]
        num = (
            alpha * (p[2:, 1:-1, :] + p[:-2, 1:-1, :])
            + gamma * (p[1:-1, 2:, :] + p[1:-1, :-2, :])
            - 0.5 * beta * cross
        )
        den = 2.0 * (alpha + gamma)
        den = np.where(np.abs(den) < 1e-30, 1e-30, den)
        target = num / den
        p[1:-1, 1:-1, :] += relaxation * (target - p[1:-1, 1:-1, :])
        if not fixed_edges[0]:
            p[0, 1:-1, :] = 2.0 * p[1, 1:-1, :] - p[2, 1:-1, :]
        if not fixed_edges[1]:
            p[-1, 1:-1, :] = 2.0 * p[-2, 1:-1, :] - p[-3, 1:-1, :]
        if not fixed_edges[2]:
            p[1:-1, 0, :] = 2.0 * p[1:-1, 1, :] - p[1:-1, 2, :]
        if not fixed_edges[3]:
            p[1:-1, -1, :] = 2.0 * p[1:-1, -2, :] - p[1:-1, -3, :]
    return p


def orient_patches_2d(patches: list[Array]) -> tuple[list[Array], list[bool]]:
    """Give every 2D patch the same signed orientation.

    Assembling domains from independently ordered control edges leaves some
    patches wound the opposite way, which shows up as a uniformly negative
    scaled Jacobian even though the geometry is sound. Consistent normals are a
    hard requirement of the Stage 00 surface_validity gate, so this normalizes
    winding by flipping the j index of any patch that disagrees with positive
    orientation. Flipping an index reverses winding without moving a node.
    """
    out, flipped = [], []
    for patch in patches:
        a = patch[:-1, :-1]
        b = patch[1:, :-1]
        c = patch[1:, 1:]
        d = patch[:-1, 1:]

        def _cross(p, q):
            return p[..., 0] * q[..., 1] - p[..., 1] * q[..., 0]

        area = float((0.5 * (_cross(b - a, d - a) + _cross(d - c, b - c))).sum())
        if area < 0.0:
            out.append(patch[:, ::-1, :])
            flipped.append(True)
        else:
            out.append(patch)
            flipped.append(False)
    return out, flipped


def _boundary_edges(xyz: Array, decimals: int = 7):
    """Directed boundary edges of a structured patch, walked counter-clockwise.

    The walk direction is what carries orientation: two correctly oriented
    neighbours traverse their shared edge in OPPOSITE directions.
    """
    key = lambda p: tuple(np.round(p, decimals))  # noqa: E731
    loop = (
        [xyz[i, 0] for i in range(xyz.shape[0])]
        + [xyz[-1, j] for j in range(1, xyz.shape[1])]
        + [xyz[i, -1] for i in range(xyz.shape[0] - 2, -1, -1)]
        + [xyz[0, j] for j in range(xyz.shape[1] - 2, 0, -1)]
    )
    keys = [key(p) for p in loop]
    return [(keys[i], keys[(i + 1) % len(keys)]) for i in range(len(keys))]


def spanwise_interpolation_error(blocks: list[Array]) -> dict:
    """Measure the error introduced by interpolating between stations.

    Drops every other station, rebuilds those columns by linear interpolation
    from their neighbours, and compares against the true station. That is a
    direct measurement of what the loft curvature costs, on this geometry, in
    metres and as a fraction of local chord.
    """
    worst_abs = 0.0
    worst_frac = 0.0
    for blk in blocks:
        n = blk.shape[1]
        chord = float(np.ptp(blk[:, :, 0])) or 1.0
        for j in range(1, n - 1, 2):
            approx = 0.5 * (blk[:, j - 1, :] + blk[:, j + 1, :])
            d = float(np.linalg.norm(blk[:, j, :] - approx, axis=1).max())
            worst_abs = max(worst_abs, d)
            worst_frac = max(worst_frac, d / chord)
    return {"worst_abs_m": worst_abs, "worst_frac_of_chord": worst_frac}


def orient_blocks_consistently(blocks: list[SurfaceBlock]) -> tuple[list[SurfaceBlock], dict]:
    """Give every block a consistent outward normal across the whole surface.

    pyHyp rejects a surface whose block normals disagree - "ERROR: Normal
    directions may be wrong" - and refuses to march at all. The Stage 00
    surface_validity gate calls for "consistent normals", but per-block winding
    checks cannot see it: each block can be individually well-formed while its
    neighbour faces the other way.

    Orientation is propagated across shared edges instead. Two correctly
    oriented neighbours traverse their shared edge in opposite directions, so a
    breadth-first walk from a seed block fixes every relative orientation. The
    whole surface is then flipped if its enclosed signed volume is negative, so
    the normals end up pointing outward rather than merely agreeing.
    """
    n = len(blocks)
    edges = [_boundary_edges(b.xyz) for b in blocks]
    owner: dict = {}
    for bi, elist in enumerate(edges):
        for e in elist:
            owner.setdefault(frozenset(e), []).append((bi, e))

    flip = [False] * n
    seen = {0}
    queue = [0]
    while queue:
        bi = queue.pop(0)
        for e in edges[bi]:
            for bj, ej in owner.get(frozenset(e), []):
                if bj == bi or bj in seen:
                    continue
                same_direction = (e == ej)
                # After accounting for bi's own flip, a shared edge walked the
                # SAME way means bj is mirrored relative to bi.
                flip[bj] = (same_direction != flip[bi])
                seen.add(bj)
                queue.append(bj)

    oriented = [
        SurfaceBlock(name=b.name, xyz=(b.xyz[:, ::-1, :] if f else b.xyz), family=b.family)
        for b, f in zip(blocks, flip, strict=True)
    ]

    # Divergence theorem: 6V = sum over cells of (centroid . area-normal).
    total = 0.0
    for b in oriented:
        x = b.xyz
        p00, p10, p11, p01 = x[:-1, :-1], x[1:, :-1], x[1:, 1:], x[:-1, 1:]
        area_n = 0.5 * (np.cross(p11 - p00, p01 - p10))
        ctr = 0.25 * (p00 + p10 + p11 + p01)
        total += float(np.sum(ctr * area_n))
    if total < 0.0:
        oriented = [
            SurfaceBlock(name=b.name, xyz=b.xyz[:, ::-1, :], family=b.family) for b in oriented
        ]
        flip = [not f for f in flip]

    info = {
        "blocks_reached_by_edge_walk": len(seen),
        "block_count": n,
        "all_blocks_connected": len(seen) == n,
        "flipped": [b.name for b, f in zip(blocks, flip, strict=True) if f],
        "signed_volume_before_global_flip": total,
    }
    return oriented, info


def qc_blocks(blocks: list[SurfaceBlock]) -> dict:
    """Run the shared per-block QC and return normalized global metrics."""
    per_block = [_block_qc(b) for b in blocks]
    total_cells = sum(int(b["cells"]) for b in per_block)
    result = {
        "block_count": len(blocks),
        "total_cells": total_cells,
        "blocks": per_block,
        "global": {
            "min_shape_metric": min(float(b["min_shape_metric"]) for b in per_block),
            "min_scaled_jacobian": min(float(b["min_scaled_jacobian"]) for b in per_block),
            "max_equiangle_skewness": max(float(b["max_equiangle_skewness"]) for b in per_block),
            "max_aspect_ratio": max(float(b["max_aspect_ratio"]) for b in per_block),
            "min_area": min(float(b["min_area"]) for b in per_block),
            "max_adjacent_normal_angle_deg": max(
                float(b["max_adjacent_normal_angle_deg"]) for b in per_block
            ),
        },
    }
    # Smallest surface cell, which governs whether the first marching layer can
    # even fit. Nothing checked this before, and a cell smaller than s0 inverts
    # the march at layer 2 while every quality metric still looks healthy.
    #
    # ADDED at the ADR-0011 migration, 2026-08-14: `max_cell_edge_m`. It is a new
    # REPORTED metric, not a changed definition and not a new gate — ADR-0011
    # section 6.2 requires the staged cell-size range for every strategy, and
    # Stage 02 computed max/min ad hoc outside qc_blocks. No existing metric
    # changed, so every number recorded in `status` remains comparable.
    min_edge = float("inf")
    min_edge_block = None
    max_edge = 0.0
    max_edge_block = None
    for b in blocks:
        x = b.xyz
        di = np.linalg.norm(np.diff(x, axis=0), axis=2)
        dj = np.linalg.norm(np.diff(x, axis=1), axis=2)
        e = float(min(di.min(), dj.min()))
        if e < min_edge:
            min_edge, min_edge_block = e, b.name
        e_max = float(max(di.max(), dj.max()))
        if e_max > max_edge:
            max_edge, max_edge_block = e_max, b.name
    result["min_cell_edge_m"] = min_edge
    result["min_cell_edge_block"] = min_edge_block
    result["max_cell_edge_m"] = max_edge
    result["max_cell_edge_block"] = max_edge_block
    result["cell_size_range"] = max_edge / min_edge if min_edge > 0 else float("inf")

    g = result["global"]
    reasons = []
    if not g["min_scaled_jacobian"] > 0.0:
        reasons.append("positive_scaled_jacobian")
    if not g["min_area"] > 0.0:
        reasons.append("minimum_surface_cell_area")
    result["failure_reasons"] = reasons
    result["accepted_pre_pyhyp"] = not reasons
    return result


def worst_corner_angle_deg(patch: Array) -> float:
    """Largest interior corner angle in a structured patch, in degrees."""
    worst = 0.0
    ni, nj, _ = patch.shape
    for i in range(ni - 1):
        for j in range(nj - 1):
            quad = [patch[i, j], patch[i + 1, j], patch[i + 1, j + 1], patch[i, j + 1]]
            for k in range(4):
                a = quad[(k - 1) % 4] - quad[k]
                b = quad[(k + 1) % 4] - quad[k]
                na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
                if na < 1e-14 or nb < 1e-14:
                    continue
                ang = float(np.degrees(np.arccos(np.clip(float(a @ b) / (na * nb), -1.0, 1.0))))
                worst = max(worst, ang)
    return worst


def write_surface_artifacts(blocks: list[SurfaceBlock], out_dir) -> dict:
    """Write the shared surface artifact set and return their hashes."""
    import hashlib
    from pathlib import Path

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = out_dir / "surface.fmt"
    npz = out_dir / "surface_blocks.npz"
    _write_plot3d_formatted(fmt, blocks)
    _write_npz(npz, blocks)

    def _sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    return {
        "surface_fmt": {"path": str(fmt), "sha256": _sha(fmt)},
        "surface_npz": {"path": str(npz), "sha256": _sha(npz)},
    }
