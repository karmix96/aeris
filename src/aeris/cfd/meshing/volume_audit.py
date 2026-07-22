"""
Geometric audit of a written pyHyp volume mesh (CGNS), independent of the
march log.

``parse_pyhyp_march_metrics`` reads the per-layer table pyHyp prints while
marching.  That table is accurate but it reports only *extrema* — a layer's
minimum volume — so it cannot say how many cells are bad, where they are,
or whether they form one small cluster at a known topological singularity
versus a wavefront collapsing across the whole block.  Those are exactly
the facts needed to classify a failure instead of merely detecting one, so
this module recomputes cell volumes from the file that was actually
written.

Cell volume uses a centroid decomposition (each of the 6 faces split into 4
triangles about the face centroid; each triangle plus the cell centroid
forms a tet).  Unlike a 5- or 6-tet split it does not depend on an
arbitrary face-diagonal choice, so the sign is meaningful for the warped
hexes that appear in a boundary layer.

pyHyp CGNS index convention: h5py returns the arrays transposed relative to
CGNS, so axis 0 of each block here is the *marching* direction (one entry
per marched layer), and axes 1 and 2 are the surface's j and i.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

VOLUME_AUDIT_SCHEMA_VERSION = "aeris.pyhyp_volume_audit.v1"

# An inverted-cell cluster is "localized" only if it is both a negligible
# share of the mesh and confined to a handful of surface points.  Both
# bounds are deliberately tight: this classification never makes a mesh
# usable, it only distinguishes a repairable corner defect from a mesh
# whose march genuinely collapsed.
LOCALIZED_MAX_FRACTION = 1e-4
LOCALIZED_MAX_SURFACE_POINTS = 64


def _iter_zone_coordinate_arrays(handle):
    """Yield (zone name, (X, Y, Z) datasets) for every structured zone.

    The datasets stay lazy so callers can read them in slabs.
    """
    bases = [k for k in handle if handle[k].attrs.get("label", b"") == b"CGNSBase_t"]
    for base in bases:
        for zone in sorted(handle[base]):
            node = handle[base][zone]
            if node.attrs.get("label", b"") != b"Zone_t":
                continue
            coords = node["GridCoordinates"]
            yield zone, tuple(coords[f"Coordinate{axis}"][" data"] for axis in "XYZ")


def read_volume_blocks(path: Path) -> dict[str, np.ndarray]:
    """Read structured block coordinates as {zone: (K, J, I, 3)} arrays.

    Loads whole blocks; ``audit_volume_cgns`` reads in slabs instead and
    should be preferred for production-sized meshes.
    """
    import h5py

    with h5py.File(str(path), "r") as handle:
        return {
            zone: np.stack([array[...] for array in arrays], axis=-1)
            for zone, arrays in _iter_zone_coordinate_arrays(handle)
        }


def signed_cell_volumes(nodes: np.ndarray) -> np.ndarray:
    """Signed hex volumes for an (K, J, I, 3) block, shape (K-1, J-1, I-1)."""
    c000 = nodes[:-1, :-1, :-1]
    c100 = nodes[1:, :-1, :-1]
    c010 = nodes[:-1, 1:, :-1]
    c110 = nodes[1:, 1:, :-1]
    c001 = nodes[:-1, :-1, 1:]
    c101 = nodes[1:, :-1, 1:]
    c011 = nodes[:-1, 1:, 1:]
    c111 = nodes[1:, 1:, 1:]

    centroid = (c000 + c100 + c010 + c110 + c001 + c101 + c011 + c111) / 8.0
    faces = (
        (c000, c010, c011, c001),
        (c100, c101, c111, c110),
        (c000, c001, c101, c100),
        (c010, c110, c111, c011),
        (c000, c100, c110, c010),
        (c001, c011, c111, c101),
    )

    volume = np.zeros(c000.shape[:-1], dtype=float)
    for f0, f1, f2, f3 in faces:
        face_centroid = (f0 + f1 + f2 + f3) / 4.0
        for a, b in ((f0, f1), (f1, f2), (f2, f3), (f3, f0)):
            volume += (
                np.einsum(
                    "...i,...i->...",
                    a - centroid,
                    np.cross(b - centroid, face_centroid - centroid),
                )
                / 6.0
            )
    return volume


def _cluster_report(
    zone: str,
    wall: np.ndarray,
    n_j: int,
    block_cells: int,
    layers: np.ndarray,
    j_idx: np.ndarray,
    i_idx: np.ndarray,
    volumes: np.ndarray,
) -> dict[str, Any]:
    surface_points = {(int(j), int(i)) for j, i in zip(j_idx, i_idx)}
    # Wall-surface footprint: where on the geometry the defect sits.
    wall_points = wall[j_idx, i_idx]
    return {
        "block": zone,
        "inverted_cells": int(layers.size),
        "block_cells": int(block_cells),
        "min_volume": float(volumes.min()),
        "first_layer": int(layers.min()) + 1,
        "last_layer": int(layers.max()) + 1,
        "surface_point_count": len(surface_points),
        "j_range": [int(j_idx.min()), int(j_idx.max())],
        "i_range": [int(i_idx.min()), int(i_idx.max())],
        # A defect touching j=0 or j=jmax sits on a spanwise extremity (root
        # symmetry plane or tip cap junction) rather than mid-span.
        "on_spanwise_edge": bool(j_idx.min() == 0 or j_idx.max() == n_j - 1),
        "wall_adjacent": bool(layers.min() == 0),
        "wall_bbox": {
            "x": [float(wall_points[:, 0].min()), float(wall_points[:, 0].max())],
            "y": [float(wall_points[:, 1].min()), float(wall_points[:, 1].max())],
            "z": [float(wall_points[:, 2].min()), float(wall_points[:, 2].max())],
        },
    }


def audit_volume_cgns(path: Path, *, chunk_layers: int = 32) -> dict[str, Any]:
    """Recompute cell volumes in a written mesh and classify any inversion.

    ``classification`` is one of:

    * ``clean`` — every cell has positive volume.
    * ``inverted_localized`` — a negligible, tightly confined cluster; the
      mesh is still unusable, but the cause is a corner defect that a
      surface-option or smoothing change can plausibly repair.
    * ``inverted_widespread`` — inversion spread over many surface points
      or a non-negligible share of cells; the march itself collapsed.

    Blocks are read and differenced in slabs of ``chunk_layers`` marched
    layers.  A production-level mesh is tens of millions of cells and the
    volume kernel allocates several temporaries per face, so materialising a
    whole block at once would cost gigabytes for what is meant to be a cheap
    post-march check.
    """
    import h5py

    clusters: list[dict[str, Any]] = []
    total_cells = 0
    total_inverted = 0
    block_count = 0
    min_volume: float | None = None

    with h5py.File(str(path), "r") as handle:
        for zone, arrays in _iter_zone_coordinate_arrays(handle):
            block_count += 1
            n_k, n_j, n_i = arrays[0].shape
            block_cells = (n_k - 1) * (n_j - 1) * (n_i - 1)
            total_cells += block_cells

            layer_parts: list[np.ndarray] = []
            j_parts: list[np.ndarray] = []
            i_parts: list[np.ndarray] = []
            volume_parts: list[np.ndarray] = []

            for k0 in range(0, n_k - 1, chunk_layers):
                k1 = min(k0 + chunk_layers + 1, n_k)
                nodes = np.stack([array[k0:k1] for array in arrays], axis=-1)
                volume = signed_cell_volumes(nodes)
                chunk_min = float(volume.min())
                min_volume = chunk_min if min_volume is None else min(min_volume, chunk_min)
                if chunk_min < 0.0:
                    layers, j_idx, i_idx = np.nonzero(volume < 0.0)
                    layer_parts.append(layers + k0)
                    j_parts.append(j_idx)
                    i_parts.append(i_idx)
                    volume_parts.append(volume[volume < 0.0])

            if layer_parts:
                wall = np.stack([array[0] for array in arrays], axis=-1)
                cluster = _cluster_report(
                    zone,
                    wall,
                    n_j,
                    block_cells,
                    np.concatenate(layer_parts),
                    np.concatenate(j_parts),
                    np.concatenate(i_parts),
                    np.concatenate(volume_parts),
                )
                total_inverted += cluster["inverted_cells"]
                clusters.append(cluster)

    fraction = (total_inverted / total_cells) if total_cells else 0.0
    surface_points = sum(c["surface_point_count"] for c in clusters)
    if total_inverted == 0:
        classification = "clean"
    elif fraction <= LOCALIZED_MAX_FRACTION and surface_points <= LOCALIZED_MAX_SURFACE_POINTS:
        classification = "inverted_localized"
    else:
        classification = "inverted_widespread"

    return {
        "schema": VOLUME_AUDIT_SCHEMA_VERSION,
        "classification": classification,
        "block_count": block_count,
        "total_cells": total_cells,
        "inverted_cells": total_inverted,
        "inverted_fraction": fraction,
        "inverted_surface_points": surface_points,
        "min_volume": min_volume,
        "clusters": clusters,
    }


def summarize_audit(audit: dict[str, Any]) -> str:
    """One-line human summary for logs and campaign output."""
    if audit["classification"] == "clean":
        return f"clean ({audit['total_cells']} cells, min volume {audit['min_volume']:.3e})"
    parts = [
        f"{audit['classification']}: {audit['inverted_cells']} of {audit['total_cells']} cells "
        f"({audit['inverted_fraction'] * 100:.5f}%) inverted, "
        f"min volume {audit['min_volume']:.3e}"
    ]
    for cluster in audit["clusters"]:
        bbox = cluster["wall_bbox"]
        parts.append(
            f"  {cluster['block']}: {cluster['inverted_cells']} cells, "
            f"layers {cluster['first_layer']}-{cluster['last_layer']}, "
            f"j{cluster['j_range']} i{cluster['i_range']}, "
            f"spanwise_edge={cluster['on_spanwise_edge']}, "
            f"wall_adjacent={cluster['wall_adjacent']}, "
            f"wall x[{bbox['x'][0]:.4f},{bbox['x'][1]:.4f}] "
            f"y[{bbox['y'][0]:.4f},{bbox['y'][1]:.4f}]"
        )
    return "\n".join(parts)
