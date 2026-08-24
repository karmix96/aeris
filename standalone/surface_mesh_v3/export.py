"""Write surface meshes for ParaView inspection, with quality carried as fields.

Mike inspects meshes in ParaView rather than in generated plots, so the quality
metrics travel WITH the mesh as cell data. Opening one file therefore answers
both "what does it look like" and "where are the bad cells" — colour by
``shape`` or ``aspect_ratio`` and the worst region is visible immediately,
which a table of extrema cannot show.

Two formats:

* ``.vts`` per block — a structured grid, so ParaView shows the actual grid
  lines and index directions. This is the one to look at.
* ``.vtm`` — a multiblock index tying the blocks together, so the whole
  surface opens as one object.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from standalone.surface_mesh_v3.measure import block_fields

Array = np.ndarray

_FIELDS = ("shape", "skew", "scaled_jacobian", "aspect_ratio", "growth", "fold", "area")


def write_vts(path: Path, nodes: Array) -> None:
    """One structured block as a legacy-ASCII VTK structured grid (.vtk).

    Written by hand rather than through the ``vtk`` module so the export has
    no dependency the rest of the pipeline does not already carry. Cell data
    is the quality field set, so ParaView can colour by it directly.
    """
    ni, nj, _ = nodes.shape
    fields = block_fields(nodes)
    with path.open("w", encoding="ascii") as fh:
        fh.write("# vtk DataFile Version 3.0\nAERIS surface mesh v3\nASCII\n")
        fh.write("DATASET STRUCTURED_GRID\n")
        fh.write(f"DIMENSIONS {ni} {nj} 1\n")
        fh.write(f"POINTS {ni * nj} double\n")
        for j in range(nj):
            for i in range(ni):
                x, y, z = nodes[i, j]
                fh.write(f"{x:.10e} {y:.10e} {z:.10e}\n")
        fh.write(f"\nCELL_DATA {(ni - 1) * (nj - 1)}\n")
        for name in _FIELDS:
            values = np.asarray(fields[name], dtype=float)
            fh.write(f"SCALARS {name} double 1\nLOOKUP_TABLE default\n")
            for j in range(values.shape[1]):
                for i in range(values.shape[0]):
                    v = values[i, j]
                    fh.write(f"{0.0 if not np.isfinite(v) else v:.6e}\n")


def write_surface(out_dir: Path, blocks: dict[str, Array], stem: str = "surface") -> list[Path]:
    """Write every block and return the paths written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, nodes in blocks.items():
        path = out_dir / f"{stem}_{name}.vtk"
        write_vts(path, np.asarray(nodes, dtype=float))
        written.append(path)
    return written


def write_master_surface(out_dir: Path, build: object, n_u: int = 201, n_v: int = 201) -> Path:
    """A dense sampling of the pyGeo master loft, for visual comparison.

    Loading this alongside a mesh shows whether the mesh lies ON the master
    geometry — the question the fidelity audit answers numerically.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    surfs = build.geometry.surfs  # type: ignore[attr-defined]
    u = np.linspace(0.0, 1.0, n_u)
    v = np.linspace(0.0, 1.0, n_v)
    vg, ug = np.meshgrid(v, u)
    path = out_dir / "master_loft.vtk"
    patches = [np.asarray(s(ug, vg), dtype=float) for s in surfs[:2]]
    with path.open("w", encoding="ascii") as fh:
        total = sum(p.shape[0] * p.shape[1] for p in patches)
        quads = sum((p.shape[0] - 1) * (p.shape[1] - 1) for p in patches)
        fh.write("# vtk DataFile Version 3.0\npyGeo master loft\nASCII\n")
        fh.write(f"DATASET POLYDATA\nPOINTS {total} double\n")
        for p in patches:
            for j in range(p.shape[1]):
                for i in range(p.shape[0]):
                    x, y, z = p[i, j]
                    fh.write(f"{x:.10e} {y:.10e} {z:.10e}\n")
        fh.write(f"\nPOLYGONS {quads} {5 * quads}\n")
        offset = 0
        for p in patches:
            pi, pj = p.shape[0], p.shape[1]
            for j in range(pj - 1):
                for i in range(pi - 1):
                    a = offset + i + pi * j
                    fh.write(f"4 {a} {a + 1} {a + 1 + pi} {a + pi}\n")
            offset += pi * pj
    return path
