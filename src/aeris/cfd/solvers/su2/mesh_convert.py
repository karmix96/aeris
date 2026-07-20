"""
Structured CGNS → native ``.su2`` mesh conversion.

SU2's CGNS reader supports unstructured zones only (SU2 8.5.0 aborts on
pyHyp's structured multiblock output — measured 2026-07-20).  This
converter bridges the gap while preserving the cross-solver verification
claim: the **node set is kept identical** (hexahedra are the structured
cells re-expressed as unstructured connectivity), so ADflow and SU2 solve
on the same grid in the ASME V&V 20 sense.

Handles:
* CGNS/HDF5 files (pyHyp writes HDF5; datasets store dims reversed, C
  order ``(nk, nj, ni)``).
* Coincident-node merging (rounded-coordinate hash) — pyHyp closes O-grid
  seams with 1-to-1 connectivity between coincident point planes, which
  must become shared nodes in an unstructured mesh.
* Boundary markers from ZoneBC point ranges, tagged by CGNS FamilyName
  (pyHyp families: ``wall``, ``Far``, ``Sym``); multiple BCs sharing a
  family merge into one marker.

SU2 element types are VTK codes: hexahedron 12, quadrilateral 9.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

CONVERT_REPORT_SCHEMA_VERSION = "aeris.cfd.su2_mesh_convert.v1"

VTK_QUAD = 9
VTK_HEXA = 12


@dataclass(frozen=True)
class StructuredZone:
    name: str
    # coordinates in CGNS index order (ni, nj, nk)
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    bcs: list[dict[str, object]] = field(default_factory=list)


def _read_string(dataset: np.ndarray) -> str:
    return bytes(np.asarray(dataset, dtype=np.uint8)).decode(errors="replace").strip("\x00 ")


def read_structured_cgns(path: Path) -> list[StructuredZone]:
    """Read zones + BC point ranges from a CGNS/HDF5 file."""
    try:
        import h5py
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "h5py is required for CGNS -> SU2 mesh conversion (pip install h5py)."
        ) from exc

    zones: list[StructuredZone] = []
    with h5py.File(path, "r") as handle:
        bases = [
            key
            for key, group in handle.items()
            if getattr(group, "attrs", {}).get("label", b"") == b"CGNSBase_t"
        ]
        if not bases:
            raise ValueError(f"{path}: no CGNSBase_t found (not a CGNS/HDF5 file?)")
        for base_name in bases:
            base = handle[base_name]
            for zone_name, zone in base.items():
                if zone.attrs.get("label", b"") != b"Zone_t":
                    continue
                coordinates = zone["GridCoordinates"]
                # HDF5 stores (nk, nj, ni); transpose to CGNS (ni, nj, nk)
                x = np.asarray(coordinates["CoordinateX"][" data"]).transpose(2, 1, 0)
                y = np.asarray(coordinates["CoordinateY"][" data"]).transpose(2, 1, 0)
                z = np.asarray(coordinates["CoordinateZ"][" data"]).transpose(2, 1, 0)

                bcs: list[dict[str, object]] = []
                if "ZoneBC" in zone:
                    for bc_name, bc in zone["ZoneBC"].items():
                        if bc.attrs.get("label", b"") != b"BC_t":
                            continue
                        point_range = np.asarray(bc["PointRange"][" data"])
                        family = (
                            _read_string(bc["FamilyName"][" data"])
                            if "FamilyName" in bc
                            else bc_name
                        )
                        bc_type = _read_string(bc[" data"]) if " data" in bc else ""
                        bcs.append(
                            {
                                "name": bc_name,
                                "family": family,
                                "type": bc_type,
                                # 1-based CGNS [[i1,j1,k1],[i2,j2,k2]]
                                "point_range": point_range.tolist(),
                            }
                        )
                zones.append(StructuredZone(name=zone_name, x=x, y=y, z=z, bcs=bcs))
    if not zones:
        raise ValueError(f"{path}: no structured zones found")
    return zones


def _merge_nodes(points: np.ndarray, decimals: int = 10) -> tuple[np.ndarray, np.ndarray]:
    """Merge coincident nodes; returns (unique_points, index_map)."""
    rounded = np.round(points, decimals=decimals)
    _, unique_index, inverse = np.unique(
        rounded.view([("x", float), ("y", float), ("z", float)]).reshape(-1),
        return_index=True,
        return_inverse=True,
    )
    return points[unique_index], inverse


def _face_quads(index_grid: np.ndarray, point_range: list[list[int]]) -> np.ndarray:
    """Quad connectivity for one BC face given the global node index grid."""
    (i1, j1, k1), (i2, j2, k2) = point_range
    face = index_grid[i1 - 1 : i2, j1 - 1 : j2, k1 - 1 : k2]
    # squeeze the constant index direction to a 2-D grid of node ids
    squeezed = face.squeeze()
    if squeezed.ndim != 2:
        raise ValueError(f"BC point range {point_range} is not a face")
    a = squeezed[:-1, :-1].ravel()
    b = squeezed[1:, :-1].ravel()
    c = squeezed[1:, 1:].ravel()
    d = squeezed[:-1, 1:].ravel()
    return np.stack([a, b, c, d], axis=1)


def convert_structured_cgns_to_su2(cgns_path: Path, su2_path: Path) -> dict[str, object]:
    """Convert a single-zone structured CGNS volume mesh to native .su2.

    Returns a conversion report (also written next to the .su2 file).
    """
    zones = read_structured_cgns(Path(cgns_path))
    if len(zones) != 1:
        raise ValueError(
            f"{cgns_path}: {len(zones)} zones — the converter currently supports "
            "single-zone meshes (2-D airfoil O-grids). Multiblock wing meshes "
            "need per-block merging (planned with the Gmsh backend milestone)."
        )
    zone = zones[0]
    ni, nj, nk = zone.x.shape

    # Axis convention: SU2's 3-D angle of attack rotates the freestream in
    # the x-z plane (lift = z); pyHyp's 2-D strips have the airfoil in x-y
    # with z the unit extrusion (lift = y) — measured 2026-07-20: solving
    # the unswapped strip at alpha=10 gives CL ~ 0.  For one-cell-deep
    # strips the y and z axes are therefore swapped (a relabeling isometry:
    # identical grid, recorded in the conversion report).
    z_values = np.unique(np.round(zone.z, 8))
    swap_yz = nj == 2 and len(z_values) == 2
    if swap_yz:
        # Swapping y<->z alone is a reflection (flips handedness -> negated
        # force coefficients, measured: CL=-2.0 at +10 deg).  Reversing the
        # j traversal restores a right-handed frame (reflection x
        # reflection = rotation) without changing the node set.
        x_arr = zone.x[:, ::-1, :]
        y_arr = zone.z[:, ::-1, :]
        z_arr = zone.y[:, ::-1, :]
    else:
        x_arr, y_arr, z_arr = zone.x, zone.y, zone.z

    points = np.stack(
        [x_arr.ravel(order="C"), y_arr.ravel(order="C"), z_arr.ravel(order="C")], axis=1
    )
    unique_points, inverse = _merge_nodes(points)
    index_grid = inverse.reshape(ni, nj, nk)

    corners = (
        index_grid[:-1, :-1, :-1],
        index_grid[1:, :-1, :-1],
        index_grid[1:, 1:, :-1],
        index_grid[:-1, 1:, :-1],
        index_grid[:-1, :-1, 1:],
        index_grid[1:, :-1, 1:],
        index_grid[1:, 1:, 1:],
        index_grid[:-1, 1:, 1:],
    )
    hexas = np.stack([corner.ravel() for corner in corners], axis=1)

    markers: dict[str, list[np.ndarray]] = {}
    for bc in zone.bcs:
        family = str(bc["family"])
        markers.setdefault(family, []).append(
            _face_quads(index_grid, bc["point_range"])  # type: ignore[arg-type]
        )

    su2_path = Path(su2_path)
    with su2_path.open("w", encoding="utf-8") as out:
        out.write("NDIME= 3\n")
        out.write(f"NELEM= {len(hexas)}\n")
        for row, cell in enumerate(hexas):
            out.write(f"{VTK_HEXA} " + " ".join(map(str, cell)) + f" {row}\n")
        out.write(f"NPOIN= {len(unique_points)}\n")
        for row, (px, py, pz) in enumerate(unique_points):
            out.write(f"{px:.16e} {py:.16e} {pz:.16e} {row}\n")
        out.write(f"NMARK= {len(markers)}\n")
        for family, quad_groups in markers.items():
            quads = np.concatenate(quad_groups, axis=0)
            out.write(f"MARKER_TAG= {family}\n")
            out.write(f"MARKER_ELEMS= {len(quads)}\n")
            for quad in quads:
                out.write(f"{VTK_QUAD} " + " ".join(map(str, quad)) + "\n")

    report = {
        "schema": CONVERT_REPORT_SCHEMA_VERSION,
        "source_cgns": str(cgns_path),
        "su2_mesh": str(su2_path),
        "zone_dims": [int(ni), int(nj), int(nk)],
        "n_points_structured": int(ni * nj * nk),
        "n_points_merged": int(len(unique_points)),
        "n_merged_duplicates": int(ni * nj * nk - len(unique_points)),
        "n_hexa": int(len(hexas)),
        "swapped_yz": bool(swap_yz),
        "markers": {family: int(sum(len(g) for g in groups)) for family, groups in markers.items()},
    }
    su2_path.with_suffix(".convert.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report
