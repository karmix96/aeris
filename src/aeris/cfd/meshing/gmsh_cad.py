"""
3-D CAD → tetrahedral fluid mesh (``cad_gmsh_tet_v1``).

The geometry-unlock tier of the Gmsh backend: import a CAD solid
(STEP/BREP/IGES), enclose it in a spherical farfield, boolean-subtract the
body, and mesh the fluid domain with curvature-adaptive tetrahedra.
Output is a native 3-D ``.su2`` with ``wall`` / ``farfield`` markers
(classified geometrically: the enclosing sphere's boundary is the largest
surface by bounding-box diagonal).

Scope notes (honest tiering, recorded in the report):
* tet-only for now — the prism/hex boundary layer for wall-resolved RANS
  is the next tier (gmsh's 3-D BoundaryLayer field needs per-geometry
  care); until then this topology targets Euler/wall-function studies and
  geometry pipeline validation.
* SU2-only (ADflow is structured multiblock).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from aeris.cfd.meshing.base import MeshTopologyGenerator
from aeris.cfd.meshing.registry import register_topology

CAD_REPORT_SCHEMA_VERSION = "aeris.cfd.gmsh_cad_report.v1"

CAD_SUFFIXES = {".step", ".stp", ".brep", ".iges", ".igs"}

KNOWN_PARAMS = frozenset(
    {
        "farfield_factor",
        "wall_size_rel",
        "farfield_size_rel",
        "curvature_points",
    }
)


@register_topology
class CadGmshTetV1(MeshTopologyGenerator):
    TOPOLOGY_ID = "cad_gmsh_tet_v1"
    DIMENSION = 3
    DESCRIPTION = (
        "CAD solid (STEP/BREP/IGES) -> spherical farfield boolean-cut fluid "
        "domain, curvature-adaptive tets; 3-D .su2 output (SU2 only; "
        "tet-only tier — prism BL is the next tier)."
    )

    def generate(
        self,
        geometry: object,
        output_dir: Path,
        params: Mapping[str, object],
    ) -> dict[str, object]:
        """geometry: path to a CAD file (.step/.stp/.brep/.iges/.igs)."""
        unknown = set(params) - KNOWN_PARAMS
        if unknown:
            raise ValueError(
                f"[{self.TOPOLOGY_ID}] unknown params {sorted(unknown)}. "
                f"Known: {sorted(KNOWN_PARAMS)}"
            )
        cad_path = Path(str(geometry)).expanduser()
        if cad_path.suffix.lower() not in CAD_SUFFIXES:
            raise ValueError(
                f"[{self.TOPOLOGY_ID}] geometry must be a CAD file "
                f"({sorted(CAD_SUFFIXES)}), got {cad_path.name!r}"
            )
        if not cad_path.is_file():
            raise FileNotFoundError(f"CAD file not found: {cad_path}")
        try:
            import gmsh
        except ImportError as exc:  # pragma: no cover
            raise ImportError("gmsh is required for the CAD backend (pip install gmsh).") from exc

        farfield_factor = float(params.get("farfield_factor", 25.0))
        wall_size_rel = float(params.get("wall_size_rel", 0.02))
        farfield_size_rel = float(params.get("farfield_size_rel", 0.5))
        curvature_points = int(params.get("curvature_points", 24))

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        su2_path = output_dir / "mesh.su2"

        gmsh.initialize()
        try:
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.model.add("cad_fluid")
            occ = gmsh.model.occ

            body_dimtags = occ.importShapes(str(cad_path))
            occ.synchronize()
            solids = [tag for dim, tag in body_dimtags if dim == 3]
            if not solids:
                raise ValueError(
                    f"[{self.TOPOLOGY_ID}] {cad_path.name} contains no solid "
                    "(3-D) shapes — surface-only CAD cannot be volume-meshed."
                )

            xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(-1, -1)
            center = (0.5 * (xmin + xmax), 0.5 * (ymin + ymax), 0.5 * (zmin + zmax))
            diagonal = ((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2) ** 0.5
            radius = farfield_factor * diagonal

            sphere = occ.addSphere(*center, radius)
            fluid, _ = occ.cut(
                [(3, sphere)], [(3, tag) for tag in solids], removeObject=True, removeTool=True
            )
            occ.synchronize()

            fluid_tags = [tag for dim, tag in fluid if dim == 3]
            surfaces = gmsh.model.getBoundary(
                [(3, tag) for tag in fluid_tags], combined=True, oriented=False
            )
            wall_surfaces: list[int] = []
            far_surfaces: list[int] = []
            for dim, tag in surfaces:
                sx0, sy0, sz0, sx1, sy1, sz1 = gmsh.model.getBoundingBox(dim, abs(tag))
                surf_diag = ((sx1 - sx0) ** 2 + (sy1 - sy0) ** 2 + (sz1 - sz0) ** 2) ** 0.5
                (far_surfaces if surf_diag > 1.5 * diagonal else wall_surfaces).append(abs(tag))
            if not wall_surfaces or not far_surfaces:
                raise ValueError(
                    f"[{self.TOPOLOGY_ID}] surface classification failed "
                    f"(wall={len(wall_surfaces)}, farfield={len(far_surfaces)})"
                )

            gmsh.model.addPhysicalGroup(2, wall_surfaces, name="wall")
            gmsh.model.addPhysicalGroup(2, far_surfaces, name="farfield")
            gmsh.model.addPhysicalGroup(3, fluid_tags, name="fluid")

            gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", curvature_points)
            gmsh.option.setNumber("Mesh.MeshSizeMin", wall_size_rel * diagonal)
            gmsh.option.setNumber("Mesh.MeshSizeMax", farfield_size_rel * radius)
            wall_points = gmsh.model.getBoundary(
                [(2, tag) for tag in wall_surfaces], recursive=True
            )
            if wall_points:
                gmsh.model.mesh.setSize(wall_points, wall_size_rel * diagonal)

            gmsh.model.mesh.generate(3)
            gmsh.write(str(su2_path))

            node_count = len(gmsh.model.mesh.getNodes()[0])
            volume_elements = gmsh.model.mesh.getElements(dim=3)
            tet_count = int(sum(len(tags) for tags in volume_elements[1]))
        finally:
            gmsh.finalize()

        report: dict[str, object] = {
            "schema": CAD_REPORT_SCHEMA_VERSION,
            "topology": self.TOPOLOGY_ID,
            "source": str(cad_path),
            "characteristic_length": diagonal,
            "mesh_file": str(su2_path),
            "mesh_format": "SU2",
            "n_nodes": int(node_count),
            "n_volume_elements": tet_count,
            "n_wall_surfaces": len(wall_surfaces),
            "farfield_radius": radius,
            "final_mesh": True,
            "solver_compatibility": ["su2"],
            "tier_note": "tet-only (no prism BL yet): Euler/wall-function studies",
        }
        (output_dir / "surface_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return report
