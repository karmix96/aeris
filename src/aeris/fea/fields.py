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


def read_dat_fields(path: Path) -> dict[str, dict[int, object]]:
    """Read original mesh-node/element fields printed to CalculiX ``.dat``.

    CalculiX expands shell nodes internally in FRD files. DAT print blocks retain
    the original input IDs, so they map cleanly onto the audited shell mesh.
    """
    displacement: dict[int, tuple[float, float, float]] = {}
    stress: dict[int, float] = {}
    active: str | None = None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        lower = raw.lower()
        if "displacements (vx,vy,vz)" in lower:
            active = "displacement"
            continue
        if "stresses (elem, integ.pnt." in lower:
            active = "stress"
            continue
        if "forces (fx,fy,fz)" in lower:
            active = None
            continue
        parts = raw.split()
        if active == "displacement" and len(parts) == 4:
            try:
                node_id = int(parts[0])
                displacement[node_id] = tuple(float(value) for value in parts[1:4])
            except ValueError:
                continue
        elif active == "stress" and len(parts) >= 8:
            try:
                element_id = int(parts[0])
                values = [float(value) for value in parts[2:8]]
            except ValueError:
                continue
            sxx, syy, szz, sxy, sxz, syz = values
            von_mises = float(
                np.sqrt(
                    0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2)
                    + 3.0 * (sxy**2 + sxz**2 + syz**2)
                )
            )
            stress[element_id] = max(stress.get(element_id, 0.0), von_mises)
    return {"displacement": displacement, "stress": stress}


def mesh_data(case_dir: Path) -> dict[str, object]:
    """Return triangulated audited mesh coordinates and region intensities."""
    nodes, elements, regions = _read_calculix_mesh(case_dir / "mesh" / "wingbox_mesh.inp")
    node_ids = sorted(nodes)
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    coordinates = np.asarray([nodes[node_id] for node_id in node_ids], dtype=float)
    region_names = sorted(set(regions.values()) | {"UNASSIGNED"})
    region_number = {name: index for index, name in enumerate(region_names)}
    node_regions = np.zeros(len(node_ids), dtype=float)
    node_counts = np.zeros(len(node_ids), dtype=float)
    faces: list[tuple[int, int, int]] = []
    edges: set[tuple[int, int]] = set()
    for element_id, connectivity in elements.items():
        if len(connectivity) < 4 or not all(node in node_index for node in connectivity):
            continue
        indices = [node_index[node] for node in connectivity]
        faces.extend(
            ((indices[0], indices[1], indices[2]), (indices[0], indices[2], indices[3]))
        )
        for start, end in zip(indices, indices[1:] + indices[:1], strict=True):
            edges.add(tuple(sorted((start, end))))
        value = float(region_number[regions.get(element_id, "UNASSIGNED")])
        for index in indices:
            node_regions[index] += value
            node_counts[index] += 1.0
    node_regions /= np.maximum(node_counts, 1.0)
    return {
        "coordinates": coordinates,
        "faces": np.asarray(faces, dtype=int),
        "edges": np.asarray(sorted(edges), dtype=int),
        "region_values": node_regions,
        "region_names": region_names,
        "node_ids": node_ids,
        "elements": elements,
        "node_index": node_index,
    }


def contour_data(case_dir: Path, load_case: str) -> dict[str, object]:
    """Return audited mesh connectivity and real CalculiX contour arrays."""
    result_path = case_dir / "solve" / load_case / "model.dat"
    base = mesh_data(case_dir)
    elements = base["elements"]
    node_ids = base["node_ids"]
    node_index = base["node_index"]
    assert isinstance(elements, dict)
    assert isinstance(node_ids, list)
    assert isinstance(node_index, dict)
    fields = read_dat_fields(result_path)
    displacement_vectors = np.zeros((len(node_ids), 3), dtype=float)
    for node_id, values in fields["displacement"].items():
        if node_id in node_index:
            displacement_vectors[node_index[node_id]] = np.asarray(values, dtype=float)
    displacement = np.linalg.norm(displacement_vectors, axis=1)
    stress_by_element = fields["stress"]
    stress = np.zeros(len(node_ids), dtype=float)
    counts = np.zeros(len(node_ids), dtype=float)
    for element_id, connectivity in elements.items():
        value = float(stress_by_element.get(element_id, 0.0))
        for node_id in connectivity:
            if node_id in node_index:
                stress[node_index[node_id]] += value
                counts[node_index[node_id]] += 1.0
    stress /= np.maximum(counts, 1.0)
    if not np.any(displacement > 0.0):
        raise ValueError(f"CalculiX displacement field is empty in {result_path}")
    if not np.any(stress > 0.0):
        raise ValueError(f"CalculiX stress field is empty in {result_path}")
    return {
        "coordinates": base["coordinates"],
        "faces": base["faces"],
        "edges": base["edges"],
        "displacement_m": displacement,
        "displacement_vectors_m": displacement_vectors,
        "stress_pa": stress,
        "regions": base["region_names"],
        "node_ids": node_ids,
    }
