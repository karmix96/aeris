"""
Gmsh unstructured 2-D airfoil topology (``airfoil_gmsh_tri_v1``).

Gmsh is the de-facto open-source mesher; this backend complements the
structured pyHyp O-grid with an unstructured triangle mesh + quad boundary
layer, written natively as a **true 2-D** ``.su2`` mesh (SU2 solves it
directly; ADflow is structured-only, so this topology is SU2-territory —
recorded in the surface report).

Role in the suite: (a) method-sensitivity companion to the O-grid
(structured-vs-unstructured on the same airfoil/conditions), (b) the
beachhead for the full 3-D Gmsh path (CAD/STEP intake, prism BL + tets)
that unlocks geometry beyond structured wings.

Boundary-layer sizing follows the same wall-spacing logic as the O-grid
(``hwall`` ≈ the s0 the structured family would use); markers are Gmsh
physical names (``wall``, ``farfield``) which SU2 consumes as MARKER tags.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import numpy as np

from aeris.cfd.meshing.airfoil_geometry import (
    load_airfoil_dat,
    naca4_coordinates,
    resample_selig_loop,
)
from aeris.cfd.meshing.base import MeshTopologyGenerator
from aeris.cfd.meshing.registry import register_topology

GMSH_SURFACE_REPORT_SCHEMA_VERSION = "aeris.cfd.gmsh_surface_report.v1"

KNOWN_PARAMS = frozenset(
    {
        "n_per_surface",
        "farfield_radius",
        "wall_size",
        "farfield_size",
        "bl_hwall",
        "bl_ratio",
        "bl_thickness",
    }
)


def _resolve_loop(geometry: object, n_per_surface: int) -> tuple[np.ndarray, str]:
    if isinstance(geometry, str) and geometry.lower().startswith("naca"):
        return naca4_coordinates(geometry[4:].strip(), n_per_surface), geometry.lower()
    if isinstance(geometry, (str, Path)):
        return resample_selig_loop(load_airfoil_dat(Path(geometry)), n_per_surface), str(geometry)
    coords = np.asarray(geometry, dtype=float)
    if coords.ndim != 2 or coords.shape[1] != 2:
        raise ValueError("geometry must be (N, 2) Selig coordinates, a .dat path, or 'naca####'")
    return resample_selig_loop(coords, n_per_surface), "array"


@register_topology
class AirfoilGmshTriV1(MeshTopologyGenerator):
    TOPOLOGY_ID = "airfoil_gmsh_tri_v1"
    DIMENSION = 2
    DESCRIPTION = (
        "Unstructured Gmsh triangle mesh with quad boundary layer around an "
        "airfoil; true 2-D .su2 output (SU2 solver only — ADflow is "
        "structured-only)."
    )

    def generate(
        self,
        geometry: object,
        output_dir: Path,
        params: Mapping[str, object],
    ) -> dict[str, object]:
        unknown = set(params) - KNOWN_PARAMS
        if unknown:
            raise ValueError(
                f"[{self.TOPOLOGY_ID}] unknown params {sorted(unknown)}. "
                f"Known: {sorted(KNOWN_PARAMS)}"
            )
        try:
            import gmsh
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "gmsh is required for the unstructured backend (pip install gmsh)."
            ) from exc

        n_per_surface = int(params.get("n_per_surface", 129))
        farfield_radius = float(params.get("farfield_radius", 100.0))
        wall_size = float(params.get("wall_size", 0.01))
        farfield_size = float(params.get("farfield_size", farfield_radius / 8.0))
        bl_hwall = float(params.get("bl_hwall", 5.0e-6))
        bl_ratio = float(params.get("bl_ratio", 1.2))
        bl_thickness = float(params.get("bl_thickness", 0.03))

        loop, source = _resolve_loop(geometry, n_per_surface)
        # drop the duplicated closing point; gmsh closes the spline itself
        if np.allclose(loop[0], loop[-1]):
            loop = loop[:-1]
        chord = float(loop[:, 0].max() - loop[:, 0].min())

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        su2_path = output_dir / "mesh.su2"

        gmsh.initialize()
        try:
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.model.add("airfoil")
            occ = gmsh.model.occ

            point_tags = [occ.addPoint(x, y, 0.0, wall_size) for x, y in loop]
            airfoil = occ.addSpline(point_tags + [point_tags[0]])
            wall_loop = occ.addCurveLoop([airfoil])

            circle = occ.addCircle(0.5 * chord, 0.0, 0.0, farfield_radius * chord)
            far_loop = occ.addCurveLoop([circle])

            surface = occ.addPlaneSurface([far_loop, wall_loop])
            occ.synchronize()

            gmsh.model.addPhysicalGroup(1, [airfoil], name="wall")
            gmsh.model.addPhysicalGroup(1, [circle], name="farfield")
            gmsh.model.addPhysicalGroup(2, [surface], name="fluid")

            # mesh sizing: fine on the wall, coarse at the farfield
            gmsh.model.mesh.setSize([(0, tag) for tag in point_tags], wall_size)
            gmsh.model.mesh.setSize(
                gmsh.model.getBoundary([(1, circle)], recursive=True), farfield_size
            )

            # quad boundary layer marching off the wall (viscous resolution)
            bl_field = gmsh.model.mesh.field.add("BoundaryLayer")
            gmsh.model.mesh.field.setNumbers(bl_field, "CurvesList", [airfoil])
            gmsh.model.mesh.field.setNumber(bl_field, "Size", bl_hwall)
            gmsh.model.mesh.field.setNumber(bl_field, "Ratio", bl_ratio)
            gmsh.model.mesh.field.setNumber(bl_field, "Thickness", bl_thickness)
            gmsh.model.mesh.field.setNumber(bl_field, "Quads", 1)
            gmsh.model.mesh.field.setAsBoundaryLayer(bl_field)

            gmsh.model.mesh.generate(2)
            gmsh.write(str(su2_path))

            node_count = len(gmsh.model.mesh.getNodes()[0])
            element_types = gmsh.model.mesh.getElements(dim=2)
            element_count = int(sum(len(tags) for tags in element_types[1]))
        finally:
            gmsh.finalize()

        report: dict[str, object] = {
            "schema": GMSH_SURFACE_REPORT_SCHEMA_VERSION,
            "topology": self.TOPOLOGY_ID,
            "source": source,
            "characteristic_length": chord,
            "mesh_file": str(su2_path),
            "mesh_format": "SU2",
            "true_2d": True,
            "n_nodes": int(node_count),
            "n_elements_2d": element_count,
            "boundary_layer": {
                "hwall": bl_hwall,
                "ratio": bl_ratio,
                "thickness": bl_thickness,
            },
            "farfield_radius_chords": farfield_radius,
            # this topology produces the FINAL mesh: no pyHyp volume stage
            "final_mesh": True,
            "solver_compatibility": ["su2"],
        }
        (output_dir / "surface_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return report
