"""Build BWB geometry from explicit design variables, and hand it to VTK.

The study code samples designs out of a locked set by index.  A workbench needs
the opposite: the user moves a slider and one specific design comes back.  Both
end in the same place - `BWBDesignSample` -> pyGeo loft - so this module builds
the sample directly and reuses the study's own surface tessellation, rather than
carrying a second geometry engine that could drift from it.

The hold-out set is never reachable from here: the workbench only constructs
designs from explicit numbers or from the development set.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .environment import REPO_ROOT, S7_DIR, STRATEGY_DIR

for _path in (str(REPO_ROOT / "src"), str(STRATEGY_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

DEVELOPMENT_SET = "lhs100_seed42"

# label, unit, decimals, group
VARIABLE_META: dict[str, tuple[str, str, int, str]] = {
    "c1_m":              ("Root chord",           "m",   3, "planform"),
    "c2_ratio":          ("Chord at b1 / root",   "",    3, "planform"),
    "c3_ratio":          ("Chord at b2 / root",   "",    3, "planform"),
    "c4_ratio":          ("Tip chord / root",     "",    3, "planform"),
    "b_total_m":         ("Semi-span",            "m",   3, "planform"),
    "b3_ratio":          ("Outer panel fraction", "",    3, "planform"),
    "split_ratio":       ("LE spline split",      "",    3, "planform"),
    "sw1_deg":           ("Inner LE sweep",       "deg", 1, "planform"),
    "sw2_deg":           ("Mid LE sweep",         "deg", 1, "planform"),
    "sw3_deg":           ("Outer LE sweep",       "deg", 1, "planform"),
    "twist_b0_deg":      ("Twist at root",        "deg", 2, "section"),
    "twist_b1_deg":      ("Twist at b1",          "deg", 2, "section"),
    "twist_b2_deg":      ("Twist at b2",          "deg", 2, "section"),
    "twist_b3_deg":      ("Twist at tip",         "deg", 2, "section"),
    "dihedral_b1_deg":   ("Dihedral at b1",       "deg", 2, "section"),
    "dihedral_b2_deg":   ("Dihedral at b2",       "deg", 2, "section"),
    "dihedral_b3_deg":   ("Dihedral at tip",      "deg", 2, "section"),
    "elevon_start_frac": ("Elevon start",         "",    3, "control"),
    "elevon_end_frac":   ("Elevon end",           "",    3, "control"),
    "elevon_hinge_frac": ("Elevon hinge",         "",    3, "control"),
}

SWEEP_VARIABLES = ("sw1_deg", "sw2_deg", "sw3_deg")


@dataclass
class DesignVariable:
    key: str
    label: str
    unit: str
    decimals: int
    group: str
    minimum: float
    maximum: float
    value: float

    @property
    def step(self) -> float:
        span = self.maximum - self.minimum
        return round(span / 200.0, self.decimals + 2) or 10.0 ** (-self.decimals)


def _config() -> Any:
    from shared.geometry_sets import _config as study_config

    return study_config()


def default_design() -> dict[str, float]:
    """Index 0 of the development set: a real, known-good starting design."""
    from shared.geometry_sets import sample

    return sample(DEVELOPMENT_SET, 0).to_dict()


def design_variables(values: dict[str, float] | None = None) -> list[DesignVariable]:
    """Every design variable with configured bounds and current value.

    Sweep bounds are declared in YAML as positive magnitudes while the sample
    stores them negative-aft, so those three are shown as magnitudes and negated
    again on the way back into the sample.
    """
    config = _config()
    sources = {
        "planform": config.planform_bounds,
        "section": config.section_bounds,
        "control": getattr(config, "elevon_bounds", None),
    }
    defaults = default_design()
    values = values or {}

    out: list[DesignVariable] = []
    for key, (label, unit, decimals, group) in VARIABLE_META.items():
        source = sources.get(group)
        bound = getattr(source, key, None) if source is not None else None
        if bound is None:
            continue
        low, high = float(bound.min), float(bound.max)
        current = float(values.get(key, defaults.get(key, low)))
        if key in SWEEP_VARIABLES:
            current = abs(current)
        out.append(DesignVariable(key, label, unit, decimals, group,
                                  low, high, min(max(current, low), high)))
    return out


def design_from_values(values: dict[str, float]) -> Any:
    """Build a `BWBDesignSample` from slider values, restoring sweep signs."""
    from aeris.generators.bwb_segmented_v1.params import BWBDesignSample

    merged = default_design()
    merged.update({k: float(v) for k, v in values.items()})
    for key in SWEEP_VARIABLES:
        merged[key] = -abs(float(merged[key]))
    accepted = set(BWBDesignSample.__dataclass_fields__)
    return BWBDesignSample(**{k: v for k, v in merged.items() if k in accepted})


def build_case(values: dict[str, float], output_dir: Path) -> Any:
    """Run the full pyGeo case for one explicit design."""
    from aeris.geometry.registry import get_geometry_generator

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return get_geometry_generator("bwb_segmented").run_full_case(
        sample=design_from_values(values),
        config=_config(),
        output_dir=output_dir,
        save_plot=False,
        build_aerosandbox=False,
    )


def build_surface(case: Any, *, level: str, te_variant: str, policy: dict[str, Any] | None = None):
    """Tessellate a pyGeo case with the study's own surface builder."""
    parent = str(S7_DIR.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    from S7_unstructured_gmsh_su2 import geometry as s7_geometry

    return s7_geometry.build_surface(case, level=level, te_variant=te_variant, policy=policy)


def reference_values(case: Any) -> dict[str, float]:
    reference = dict(case.pygeo_result.reference_values)
    return {k: float(v) for k, v in reference.items() if isinstance(v, (int, float))}


def planform_summary(case: Any) -> dict[str, Any]:
    """Span, area, chord and the per-station table the geometry tab shows."""
    reference = reference_values(case)
    stations = []
    for index, section in enumerate(case.pygeo_result.extracted):
        stations.append({
            "station": index,
            "y_m": round(float(getattr(section, "y_m", index)), 4),
            "chord_m": round(float(section.chord_m), 4),
            "twist_deg": round(float(getattr(section, "twist_deg", 0.0)), 3),
            "dihedral_deg": round(float(getattr(section, "dihedral_deg", 0.0)), 3),
            "airfoil": str(getattr(section, "airfoil_name", "")),
        })
    span = float(reference.get("span_m", 0.0))
    area = float(reference.get("reference_area_m2", reference.get("area_m2", 0.0)))
    mac = float(reference.get("mean_aerodynamic_chord_m", 0.0))
    return {
        "span_m": span,
        "semi_span_m": 0.5 * span,
        "area_m2": area,
        "mac_m": mac,
        "aspect_ratio": (span * span / area) if area > 0 else float("nan"),
        "stations": stations,
        "reference": reference,
    }


def surface_to_polydata(surface: Any, *, color_by: str = "label"):
    """Convert a study `SurfaceMesh` into VTK polydata for the viewport."""
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray

    points = np.ascontiguousarray(np.asarray(surface.points, dtype=np.float64))
    triangles = np.ascontiguousarray(np.asarray(surface.triangles, dtype=np.int64))

    vtk_points = vtk.vtkPoints()
    vtk_points.SetData(numpy_to_vtk(points, deep=True))

    cells = np.empty((len(triangles), 4), dtype=np.int64)
    cells[:, 0] = 3
    cells[:, 1:] = triangles
    vtk_cells = vtk.vtkCellArray()
    vtk_cells.SetCells(len(triangles), numpy_to_vtkIdTypeArray(cells.ravel(), deep=True))

    polydata = vtk.vtkPolyData()
    polydata.SetPoints(vtk_points)
    polydata.SetPolys(vtk_cells)

    labels = list(surface.labels)
    unique = sorted(set(labels))
    index = {name: position for position, name in enumerate(unique)}
    arrays = {
        "label": np.array([index[name] for name in labels], dtype=np.float64),
        "span_fraction": np.asarray(surface.triangle_span_fraction, dtype=np.float64),
    }
    for name, values in arrays.items():
        cell_array = numpy_to_vtk(np.ascontiguousarray(values), deep=True)
        cell_array.SetName(name)
        polydata.GetCellData().AddArray(cell_array)
    polydata.GetCellData().SetActiveScalars(color_by if color_by in arrays else "label")
    return polydata, unique


def surface_statistics(surface: Any) -> dict[str, Any]:
    points = np.asarray(surface.points)
    triangles = np.asarray(surface.triangles)
    a = points[triangles[:, 1]] - points[triangles[:, 0]]
    b = points[triangles[:, 2]] - points[triangles[:, 0]]
    areas = 0.5 * np.linalg.norm(np.cross(a, b), axis=1)
    edges = np.concatenate([
        np.linalg.norm(points[triangles[:, 1]] - points[triangles[:, 0]], axis=1),
        np.linalg.norm(points[triangles[:, 2]] - points[triangles[:, 1]], axis=1),
        np.linalg.norm(points[triangles[:, 0]] - points[triangles[:, 2]], axis=1),
    ])
    counts: dict[str, int] = {}
    for name in surface.labels:
        counts[name] = counts.get(name, 0) + 1
    return {
        "points": int(len(points)),
        "triangles": int(len(triangles)),
        "wetted_area_m2": float(areas.sum()),
        "min_triangle_area_m2": float(areas.min()) if len(areas) else 0.0,
        "min_edge_m": float(edges.min()) if len(edges) else 0.0,
        "max_edge_m": float(edges.max()) if len(edges) else 0.0,
        "mean_edge_m": float(edges.mean()) if len(edges) else 0.0,
        "label_counts": counts,
        "bounds_m": [float(v) for v in (
            points[:, 0].min(), points[:, 0].max(),
            points[:, 1].min(), points[:, 1].max(),
            points[:, 2].min(), points[:, 2].max())],
    }


# --------------------------------------------------------------------------- #
# S6's own structured surface                                                   #
# --------------------------------------------------------------------------- #
#
# S6 does not mesh the triangulated surface above.  It builds its own structured
# multiblock OML - separate blocks for the upper and lower fore and aft panels,
# a nose and base collar, and a six-block tip cap - and pyHyp marches from that.
# Showing the S7 tessellation in the S6 workbench was misleading: it is not the
# surface that gets meshed, and at the diagnostic tier it is far coarser than
# anything S6 uses.

S6_SURFACE_LEVELS = ("coarse", "smoke", "medium", "fine")


def build_s6_surface(index: int, output_dir: Path, *, level: str = "smoke",
                     set_name: str = DEVELOPMENT_SET):
    """The structured surface S6 actually marches, with its own level names."""
    from .environment import S6_DIR

    if str(S6_DIR) not in sys.path:
        sys.path.insert(0, str(S6_DIR))
    from strategy_s6 import build_locked_surface  # noqa: PLC0415

    blocks, info, case = build_locked_surface(
        set_name, int(index), Path(output_dir), level=level)
    return blocks, info, case


def s6_blocks_to_polydata(blocks):
    """Structured surface blocks as one quad mesh, tagged by block.

    Each block is an (ni, nj, 3) lattice, so the quads follow the lattice
    directly - no triangulation, which is the point: the picture then shows the
    same cells pyHyp will march from.
    """
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray

    points: list[np.ndarray] = []
    quads: list[np.ndarray] = []
    block_ids: list[np.ndarray] = []
    names: list[str] = []
    offset = 0

    for index, block in enumerate(blocks):
        xyz = np.asarray(block.xyz, dtype=np.float64)
        ni, nj = xyz.shape[0], xyz.shape[1]
        points.append(xyz.reshape(-1, 3))
        names.append(block.name)
        if ni < 2 or nj < 2:
            continue
        i_index, j_index = np.meshgrid(np.arange(ni - 1), np.arange(nj - 1), indexing="ij")
        corner = (i_index * nj + j_index).ravel() + offset
        cell = np.column_stack([corner, corner + nj, corner + nj + 1, corner + 1])
        quads.append(cell)
        block_ids.append(np.full(len(cell), index, dtype=np.float64))
        offset += ni * nj

    if not quads:
        return vtk.vtkPolyData(), []

    coordinates = np.ascontiguousarray(np.concatenate(points))
    connectivity = np.ascontiguousarray(np.concatenate(quads).astype(np.int64))

    vtk_points = vtk.vtkPoints()
    vtk_points.SetData(numpy_to_vtk(coordinates, deep=True))

    cells = np.empty((len(connectivity), 5), dtype=np.int64)
    cells[:, 0] = 4
    cells[:, 1:] = connectivity
    array = vtk.vtkCellArray()
    array.SetCells(len(connectivity), numpy_to_vtkIdTypeArray(cells.ravel(), deep=True))

    polydata = vtk.vtkPolyData()
    polydata.SetPoints(vtk_points)
    polydata.SetPolys(array)

    tags = numpy_to_vtk(np.ascontiguousarray(np.concatenate(block_ids)), deep=True)
    tags.SetName("block")
    polydata.GetCellData().AddArray(tags)
    polydata.GetCellData().SetActiveScalars("block")
    return polydata, names


def s6_surface_statistics(blocks) -> dict[str, Any]:
    points = sum(int(np.asarray(b.xyz).shape[0] * np.asarray(b.xyz).shape[1]) for b in blocks)
    quads = sum(int((np.asarray(b.xyz).shape[0] - 1) * (np.asarray(b.xyz).shape[1] - 1))
                for b in blocks if np.asarray(b.xyz).shape[0] > 1
                and np.asarray(b.xyz).shape[1] > 1)
    every = np.concatenate([np.asarray(b.xyz).reshape(-1, 3) for b in blocks])
    return {
        "points": points,
        "quads": quads,
        "blocks": len(blocks),
        "block_names": [b.name for b in blocks],
        "bounds_m": [float(v) for v in (
            every[:, 0].min(), every[:, 0].max(),
            every[:, 1].min(), every[:, 1].max(),
            every[:, 2].min(), every[:, 2].max())],
    }
