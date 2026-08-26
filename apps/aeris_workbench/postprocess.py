"""Load a finished solution and turn it into something worth looking at.

Both solvers write a surface file and a volume file; the shapes differ but the
questions do not - what is the pressure on the skin, where is y+ too large, what
does a cut plane through the wake look like, and what were the forces.  This
module answers those from whatever the solver left on disk.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

# What a viewer offers to colour by, in the order an engineer usually wants it.
PREFERRED_FIELDS = (
    "Pressure_Coefficient", "Cp", "cp",
    "Mach", "mach", "Pressure", "Density",
    "Skin_Friction_Coefficient_x", "cf",
    "Y_Plus", "yplus", "Velocity_x", "Momentum_x",
)


def _reader_for(path: Path):
    import vtk

    suffix = path.suffix.lower()
    if suffix == ".vtk":
        reader = vtk.vtkGenericDataObjectReader()
        reader.SetFileName(str(path))
        reader.ReadAllScalarsOn()
        reader.ReadAllVectorsOn()
        reader.ReadAllFieldsOn()
        return reader
    if suffix == ".vtu":
        return _configured(vtk.vtkXMLUnstructuredGridReader(), path)
    if suffix == ".vtp":
        return _configured(vtk.vtkXMLPolyDataReader(), path)
    if suffix == ".vts":
        return _configured(vtk.vtkXMLStructuredGridReader(), path)
    if suffix == ".cgns":
        reader = vtk.vtkCGNSReader()
        reader.SetFileName(str(path))
        reader.UpdateInformation()
        reader.EnableAllBases()
        reader.EnableAllCellArrays()
        reader.EnableAllPointArrays()
        return reader
    if suffix == ".plt":
        raise ValueError("Tecplot .plt is not readable here; ask the solver for VTK output")
    raise ValueError(f"no reader for {path.name}")


def _configured(reader, path: Path):
    reader.SetFileName(str(path))
    return reader


def load(path: Path):
    """Read any solution file the two solvers produce."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    reader = _reader_for(path)
    reader.Update()
    return reader.GetOutput()


def find_solution_files(run_dir: Path) -> dict[str, list[str]]:
    """Whatever the solver actually wrote, grouped by what it is."""
    run_dir = Path(run_dir)
    surface, volume = [], []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".vtk", ".vtu", ".vtp", ".cgns", ".vts"):
            continue
        name = path.name.lower()
        if "surface" in name or "slice" in name or path.suffix.lower() == ".vtp":
            surface.append(str(path))
        elif "volume" in name or "vol" in name or path.suffix.lower() in (".vtu", ".vts"):
            volume.append(str(path))
        else:
            surface.append(str(path))
    return {"surface": surface, "volume": volume}


def iter_blocks(dataset):
    """Yield leaf datasets, so a CGNS multiblock reads like a plain grid.

    ADflow and pyHyp both write CGNS, which VTK returns as a multiblock; SU2
    writes a single grid.  Every accessor below goes through here rather than
    calling GetPointData on whatever it was handed.
    """
    if dataset is None:
        return
    if hasattr(dataset, "NewIterator"):
        walker = dataset.NewIterator()
        walker.InitTraversal()
        while not walker.IsDoneWithTraversal():
            leaf = walker.GetCurrentDataObject()
            if leaf is not None and leaf.GetNumberOfPoints():
                yield leaf
            walker.GoToNextItem()
    else:
        yield dataset


def first_block(dataset):
    for block in iter_blocks(dataset):
        return block
    return dataset


def available_fields(dataset) -> dict[str, list[str]]:
    """The union of arrays across every block, in first-seen order."""
    point: list[str] = []
    cell: list[str] = []
    for block in iter_blocks(dataset):
        for source, target in ((block.GetPointData(), point), (block.GetCellData(), cell)):
            for index in range(source.GetNumberOfArrays()):
                name = source.GetArrayName(index)
                if name and name not in target:
                    target.append(name)
    return {"point": point, "cell": cell}


def best_field(dataset) -> tuple[str, str]:
    """Pick a sensible default colouring: pressure first, then Mach."""
    fields = available_fields(dataset)
    for candidate in PREFERRED_FIELDS:
        if candidate in fields["point"]:
            return candidate, "point"
        if candidate in fields["cell"]:
            return candidate, "cell"
    if fields["point"]:
        return fields["point"][0], "point"
    if fields["cell"]:
        return fields["cell"][0], "cell"
    return "", "point"


def field_range(dataset, name: str, association: str = "point") -> tuple[float, float]:
    """Range across every block, not just the first one."""
    low, high = float("inf"), float("-inf")
    for block in iter_blocks(dataset):
        data = block.GetPointData() if association == "point" else block.GetCellData()
        array = data.GetArray(name)
        if array is None:
            continue
        block_low, block_high = array.GetRange()
        low, high = min(low, block_low), max(high, block_high)
    if low == float("inf"):
        return (0.0, 1.0)
    if low == high:
        high = low + 1.0
    return (float(low), float(high))


def slice_plane(dataset, *, normal=(0.0, 1.0, 0.0), origin=None):
    """A cut through the solution, which is how a flow field is actually read."""
    import vtk

    if origin is None:
        bounds = dataset_bounds(dataset)
        origin = ((bounds[0] + bounds[1]) / 2,
                  (bounds[2] + bounds[3]) / 2,
                  (bounds[4] + bounds[5]) / 2)
    plane = vtk.vtkPlane()
    plane.SetNormal(*normal)
    plane.SetOrigin(*origin)
    append = vtk.vtkAppendPolyData()
    pieces = 0
    for block in iter_blocks(dataset):
        cutter = vtk.vtkCutter()
        cutter.SetInputData(block)
        cutter.SetCutFunction(plane)
        cutter.Update()
        piece = cutter.GetOutput()
        if piece.GetNumberOfPoints():
            append.AddInputData(piece)
            pieces += 1
    if not pieces:
        return vtk.vtkPolyData()
    append.Update()
    return append.GetOutput()


def dataset_bounds(dataset) -> tuple[float, ...]:
    lows = [float("inf")] * 3
    highs = [float("-inf")] * 3
    for block in iter_blocks(dataset):
        bounds = block.GetBounds()
        for axis in range(3):
            lows[axis] = min(lows[axis], bounds[2 * axis])
            highs[axis] = max(highs[axis], bounds[2 * axis + 1])
    if lows[0] == float("inf"):
        return (0.0,) * 6
    return tuple(v for pair in zip(lows, highs) for v in pair)


def contour(dataset, name: str, values: list[float]):
    import vtk

    dataset.GetPointData().SetActiveScalars(name)
    filt = vtk.vtkContourFilter()
    filt.SetInputData(dataset)
    for index, value in enumerate(values):
        filt.SetValue(index, value)
    filt.Update()
    return filt.GetOutput()


def streamlines(dataset, *, seed_center, seed_radius, count=200, vector="Velocity"):
    import vtk

    if dataset.GetPointData().GetArray(vector) is None:
        return None
    dataset.GetPointData().SetActiveVectors(vector)
    seed = vtk.vtkPointSource()
    seed.SetCenter(*seed_center)
    seed.SetRadius(seed_radius)
    seed.SetNumberOfPoints(int(count))
    tracer = vtk.vtkStreamTracer()
    tracer.SetInputData(dataset)
    tracer.SetSourceConnection(seed.GetOutputPort())
    tracer.SetIntegrationDirectionToBoth()
    tracer.SetMaximumPropagation(50.0)
    tracer.Update()
    return tracer.GetOutput()


def surface_scalar_summary(dataset, name: str, association: str = "point") -> dict[str, Any]:
    from vtk.util.numpy_support import vtk_to_numpy

    collected = []
    for block in iter_blocks(dataset):
        data = block.GetPointData() if association == "point" else block.GetCellData()
        array = data.GetArray(name)
        if array is None:
            continue
        values = vtk_to_numpy(array)
        if values.ndim > 1:
            values = np.linalg.norm(values, axis=1)
        collected.append(values)
    if not collected:
        return {}
    values = np.concatenate(collected)
    finite = values[np.isfinite(values)]
    if not len(finite):
        return {}
    return {
        "field": name,
        "min": float(finite.min()),
        "max": float(finite.max()),
        "mean": float(finite.mean()),
        "p95": float(np.percentile(finite, 95)),
        "p99": float(np.percentile(finite, 99)),
        "count": int(len(finite)),
    }


def su2_forces(run_dir: Path) -> dict[str, float]:
    """Final forces from the SU2 history file."""
    path = Path(run_dir) / "history.csv"
    if not path.is_file():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if len(rows) < 2:
        return {}
    headers = [h.strip().strip('"') for h in rows[0]]
    out: dict[str, float] = {}
    for name, cell in zip(headers, rows[-1]):
        if name in ("CL", "CD", "CMy", "CMx", "CMz", "CFx", "CFy", "CFz",
                    "CSF", "CEff", "rms[Rho]"):
            try:
                out[name] = float(cell)
            except ValueError:
                pass
    out["iterations"] = float(len(rows) - 1)
    return out


def convergence_summary(history: dict[str, list[float]]) -> dict[str, Any]:
    """Did it converge, and by how much - the same question the gate asks."""
    residual = history.get("rms_rho") or []
    if not residual:
        return {}
    initial, final = float(residual[0]), float(residual[-1])
    lowest = float(min(residual))
    return {
        "initial_log10": initial,
        "final_log10": final,
        "orders_dropped": initial - final,
        "best_orders_dropped": initial - lowest,
        "monotonic": abs(final - lowest) < 1e-9,
        "iterations": len(residual),
    }


def force_tail(history: dict[str, list[float]], *, rows: int = 200) -> dict[str, Any]:
    """How steady the forces are over the last stretch of the run."""
    out: dict[str, Any] = {}
    for key in ("CL", "CD", "CMy"):
        values = history.get(key) or []
        if len(values) < 2:
            continue
        tail = np.asarray(values[-rows:], dtype=float)
        mean = float(np.mean(tail))
        spread = float(np.ptp(tail))
        out[key] = {
            "final": float(tail[-1]),
            "mean": mean,
            "range": spread,
            "relative_range": spread / max(abs(mean), 1e-12),
            "rows": int(len(tail)),
        }
    return out


def write_report(run_dir: Path, payload: dict[str, Any]) -> Path:
    path = Path(run_dir) / "workbench_post.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path
