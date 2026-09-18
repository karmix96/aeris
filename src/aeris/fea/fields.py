"""Small, dependency-light readers for interactive CalculiX result contours."""

# Contour tuple declarations are intentionally kept readable.
# ruff: noqa: E501

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from aeris.fea.visualize import _read_calculix_mesh

_FLOAT = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?")


def read_frd_fields(path: Path) -> dict[str, dict[int, tuple[float, ...]]]:
    """Read nodal displacement and elemental stress records from a CalculiX FRD."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    fields: dict[str, dict[int, tuple[float, ...]]] = {}
    active: str | None = None
    for line in lines:
        if "-4  DISP" in line:
            active = "displacement"
            fields[active] = {}
            continue
        if "-4  STRESS" in line:
            active = "stress"
            fields[active] = {}
            continue
        if line.strip() == "-3":
            active = None
            continue
        if active is None or not line.lstrip().startswith("-1"):
            continue
        match = re.match(r"\s*-1\s+(\d+)(.*)$", line)
        if match is None:
            continue
        values = tuple(float(value) for value in _FLOAT.findall(match.group(2)))
        if values:
            fields[active][int(match.group(1))] = values
    return fields


def contour_data(case_dir: Path, load_case: str) -> dict[str, object]:
    """Return mesh connectivity and available displacement/stress contour arrays."""
    mesh_path = case_dir / "mesh" / "wingbox_mesh.inp"
    result_path = case_dir / "solve" / load_case / "model.frd"
    nodes, elements, regions = _read_calculix_mesh(mesh_path)
    fields = read_frd_fields(result_path)
    node_ids = sorted(nodes)
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    coordinates = np.asarray([nodes[node_id] for node_id in node_ids], dtype=float)
    faces: list[tuple[int, int, int]] = []
    face_element: list[int] = []
    for element_id, connectivity in elements.items():
        if len(connectivity) < 4 or not all(node in node_index for node in connectivity):
            continue
        indices = [node_index[node] for node in connectivity]
        for triangle in ((indices[0], indices[1], indices[2]), (indices[0], indices[2], indices[3])):
            faces.append(triangle)
            face_element.append(element_id)
    displacement = np.zeros(len(node_ids), dtype=float)
    for node_id, values in fields.get("displacement", {}).items():
        if node_id in node_index:
            displacement[node_index[node_id]] = float(np.linalg.norm(values[:3]))
    stress_by_element = {
        element_id: float(np.linalg.norm(values[:3]))
        for element_id, values in fields.get("stress", {}).items()
    }
    stress = np.zeros(len(node_ids), dtype=float)
    counts = np.zeros(len(node_ids), dtype=float)
    for element_id, connectivity in elements.items():
        value = stress_by_element.get(element_id, 0.0)
        for node_id in connectivity:
            if node_id in node_index:
                stress[node_index[node_id]] += value
                counts[node_index[node_id]] += 1.0
    stress /= np.maximum(counts, 1.0)
    return {
        "coordinates": coordinates,
        "faces": np.asarray(faces, dtype=int),
        "displacement_m": displacement,
        "stress_pa": stress,
        "regions": regions,
        "node_ids": node_ids,
    }
