"""CalculiX input generation, execution, and result parsing."""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

import numpy as np

from aeris.common.config import file_sha256
from aeris.fea.case.spec import CaseSpec, LoadCaseSpec
from aeris.fea.mesh import StructuralMesh, region_thickness
from aeris.fea.openaerostruct import load_oas_case


def pressure_for_element(load: LoadCaseSpec, span_fraction: float) -> float:
    shape = 1.0
    if load.distribution == "elliptical":
        shape = math.sqrt(max(0.0, 1.0 - span_fraction**2))
    if load.pressure_pa is None:
        raise ValueError(f"load case {load.name!r} has no direct pressure")
    return load.pressure_pa * load.load_factor * shape


def _element_pressures(
    load: LoadCaseSpec, mesh: StructuralMesh, solve_dir: Path
) -> tuple[dict[int, float], dict[str, object]]:
    top = [element for element in mesh.elements if element.region.startswith("SKIN_TOP")]
    if load.source == "pressure":
        values = {element.id: pressure_for_element(load, element.span_fraction) for element in top}
        return values, {
            "source": "prescribed_pressure",
            "pressure_pa": load.pressure_pa,
            "distribution": load.distribution,
        }
    if load.alpha_deg is None or load.aircraft_mass_kg is None:
        raise ValueError(f"OpenAeroStruct load {load.name!r} lacks alpha/mass")
    validation_path = solve_dir.parents[1] / "validation" / "openaerostruct_validation.json"
    if not validation_path.is_file():
        raise ValueError(f"OpenAeroStruct load requires {validation_path}")
    oas_case = load_oas_case(validation_path, load.alpha_deg)
    y_nodes = np.asarray(oas_case["span_y_nodes_m_tip_to_root"], dtype=float)
    forces = np.asarray(oas_case["spanwise_force_xyz_n_tip_to_root"], dtype=float)
    if forces.shape != (len(y_nodes) - 1, 3):
        raise ValueError("OpenAeroStruct spanwise force shape is inconsistent with its mesh")
    widths = np.abs(np.diff(y_nodes))
    density = np.abs(forces[:, 2]) / widths
    if not np.all(np.isfinite(density)) or float(np.max(density)) <= 0.0:
        raise ValueError(f"OpenAeroStruct alpha={load.alpha_deg:g} has no usable lift shape")
    panel_y = 0.5 * (y_nodes[:-1] + y_nodes[1:])
    order = np.argsort(panel_y)
    sample_y = np.asarray([element.span_fraction * mesh.semispan_m for element in top])
    shape = np.interp(sample_y, panel_y[order], density[order])
    normalization = sum(
        float(weight) * element.area_m2 for weight, element in zip(shape, top, strict=True)
    )
    if normalization <= 0.0:
        raise ValueError("OpenAeroStruct load mapping has zero normalization")
    gravity = 9.80665
    target_half_n = (
        load.direction * load.aircraft_mass_kg * gravity * load.load_factor / 2.0
    )
    values = {
        element.id: target_half_n * float(weight) / normalization
        for weight, element in zip(shape, top, strict=True)
    }
    return values, {
        "source": "openaerostruct_spanwise_shape",
        "validation_report": str(validation_path),
        "validation_report_sha256": file_sha256(validation_path),
        "alpha_deg": load.alpha_deg,
        "aircraft_mass_kg": load.aircraft_mass_kg,
        "gravity_m_s2": gravity,
        "load_factor": load.load_factor,
        "direction": load.direction,
        "target_resultant_half_model_n": target_half_n,
        "mapping": "absolute OAS sectional Fz shape, normalized onto top-skin shell area",
    }


def _applied_force_vector(
    mesh: StructuralMesh, element_pressures: dict[int, float]
) -> list[float]:
    force = np.zeros(3)
    for element in mesh.elements:
        if not element.region.startswith("SKIN_TOP"):
            continue
        points = [np.asarray(mesh.nodes[node], dtype=float) for node in element.nodes]
        area_vector = 0.5 * np.cross(points[1] - points[0], points[2] - points[0])
        area_vector += 0.5 * np.cross(points[2] - points[0], points[3] - points[0])
        force += element_pressures[element.id] * area_vector
    return force.tolist()


def model_definition_lines(spec: CaseSpec, mesh: StructuralMesh, mesh_include: Path) -> list[str]:
    lines = [
        f"*INCLUDE, INPUT={mesh_include.resolve()}",
        f"*MATERIAL, NAME={spec.material.name}",
        "*ELASTIC",
        f"{spec.material.youngs_modulus_pa:.12g}, {spec.material.poisson_ratio:.12g}",
        "*DENSITY",
        f"{spec.material.density_kg_m3:.12g}",
    ]
    for region in sorted({element.region for element in mesh.elements}):
        lines.extend(
            [
                f"*SHELL SECTION, ELSET={region}, MATERIAL={spec.material.name}",
                f"{region_thickness(region, spec.section):.12g}",
            ]
        )
    lines.extend(["*BOUNDARY", "ROOT, 1, 6, 0.0"])
    return lines


def load_lines(
    load: LoadCaseSpec, mesh: StructuralMesh, solve_dir: Path
) -> tuple[list[str], dict[int, float], dict[str, object]]:
    element_pressures, metadata = _element_pressures(load, mesh, solve_dir)
    lines = ["*DLOAD"]
    for element in mesh.elements:
        if element.region.startswith("SKIN_TOP"):
            lines.append(f"{element.id}, P, {element_pressures[element.id]:.12g}")
    return lines, element_pressures, metadata


def equivalent_nodal_load_lines(
    load: LoadCaseSpec, mesh: StructuralMesh, solve_dir: Path
) -> list[str]:
    """Convert shell pressure to a conservative, non-follower nodal load."""
    element_pressures, _metadata = _element_pressures(load, mesh, solve_dir)
    nodal: dict[int, np.ndarray] = {}
    for element in mesh.elements:
        if not element.region.startswith("SKIN_TOP"):
            continue
        points = [np.asarray(mesh.nodes[node], dtype=float) for node in element.nodes]
        area_vector = 0.5 * np.cross(points[1] - points[0], points[2] - points[0])
        area_vector += 0.5 * np.cross(points[2] - points[0], points[3] - points[0])
        share = element_pressures[element.id] * area_vector / len(element.nodes)
        for node in element.nodes:
            nodal[node] = nodal.get(node, np.zeros(3)) + share
    lines = ["*CLOAD"]
    for node in sorted(nodal):
        for dof, value in enumerate(nodal[node], start=1):
            if abs(float(value)) > 1e-15:
                lines.append(f"{node}, {dof}, {float(value):.12g}")
    return lines


def write_calculix_deck(
    spec: CaseSpec,
    load: LoadCaseSpec,
    mesh: StructuralMesh,
    mesh_include: Path,
    solve_dir: Path,
) -> Path:
    solve_dir.mkdir(parents=True, exist_ok=True)
    deck = solve_dir / "model.inp"
    load_block, element_pressures, load_metadata = load_lines(load, mesh, solve_dir)
    lines = [
        f"** AERIS open-source FEA case: {spec.name} / {load.name}",
        *model_definition_lines(spec, mesh, mesh_include),
    ]
    lines.extend(
        [
            "*STEP",
            "*STATIC",
            "0.1, 1.0, 1e-06, 0.1",
            *load_block,
        ]
    )
    lines.extend(
        [
            "*NODE PRINT, NSET=NALL",
            "U",
            "*NODE PRINT, NSET=ROOT",
            "RF",
            "*EL PRINT, ELSET=EALL",
            "S",
            "*NODE FILE, NSET=NALL",
            "U",
            "*EL FILE",
            "S",
            "*END STEP",
        ]
    )
    deck.write_text("\n".join(lines) + "\n", encoding="utf-8")
    applied_resultant = sum(
        element_pressures[e.id] * e.area_m2
        for e in mesh.elements
        if e.region.startswith("SKIN_TOP")
    )
    target = load_metadata.get("target_resultant_half_model_n")
    mapping_error = None
    if target is not None:
        mapping_error = abs(applied_resultant - float(target)) / max(abs(float(target)), 1e-30)
        if mapping_error > 1e-10:
            raise ValueError(
                f"load mapping conservation error {mapping_error:.3e} exceeds 1e-10"
            )
    metadata = {
        "schema": "aeris.fea.calculix_input.v1",
        "case": spec.name,
        "load_case": load.name,
        "solver": "calculix",
        "mesh_include": str(mesh_include.resolve()),
        "pressure_pa": load.pressure_pa,
        "distribution": load.distribution,
        "load_factor": load.load_factor,
        "applied_resultant_half_model_n": applied_resultant,
        "applied_force_vector_half_model_n": _applied_force_vector(mesh, element_pressures),
        "load_mapping_relative_error": mapping_error,
        "load_authority": load_metadata,
    }
    (solve_dir / "input_manifest.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return deck


def run_calculix(
    deck: Path,
    *,
    executable: str = "ccx",
    echo: Callable[[str], None] | None = None,
) -> int:
    resolved = shutil.which(executable)
    if resolved is None:
        raise FileNotFoundError(
            f"CalculiX executable {executable!r} was not found on PATH. "
            "Install the open-source CalculiX package or use --dry-run."
        )
    process = subprocess.Popen(
        [resolved, deck.stem],
        cwd=deck.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    captured: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        captured.append(line)
        if echo is not None:
            echo(line.rstrip())
    returncode = process.wait()
    (deck.parent / "calculix.log").write_text("".join(captured), encoding="utf-8")
    return returncode


_FLOAT = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"


def _von_mises(values: tuple[float, float, float, float, float, float]) -> float:
    sxx, syy, szz, sxy, sxz, syz = values
    return math.sqrt(
        0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2)
        + 3.0 * (sxy**2 + sxz**2 + syz**2)
    )


def parse_calculix_dat(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"CalculiX result file not found: {path}")
    mode: str | None = None
    max_displacement = 0.0
    max_von_mises = 0.0
    reaction_force = [0.0, 0.0, 0.0]
    displacement_rows = 0
    reaction_rows = 0
    stress_rows = 0
    numeric = re.compile(rf"^\s*(\d+)\s+((?:{_FLOAT}\s+){{2}}{_FLOAT})(?:\s+.*)?$")
    stress_numeric = re.compile(rf"^\s*(\d+)\s+(\d+)\s+((?:{_FLOAT}\s+){{5}}{_FLOAT})(?:\s+.*)?$")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        lower = line.lower()
        if "displacements" in lower:
            mode = "u"
            continue
        if "forces (fx,fy,fz)" in lower:
            mode = "rf"
            continue
        if "stresses" in lower:
            mode = "s"
            continue
        if not line.strip():
            continue
        if mode == "u":
            match = numeric.match(line)
            if match:
                values = tuple(float(v) for v in match.group(2).split())
                max_displacement = max(max_displacement, math.sqrt(sum(v * v for v in values)))
                displacement_rows += 1
        elif mode == "rf":
            match = numeric.match(line)
            if match:
                values = tuple(float(v) for v in match.group(2).split())
                reaction_force = [a + b for a, b in zip(reaction_force, values, strict=True)]
                reaction_rows += 1
        elif mode == "s":
            match = stress_numeric.match(line)
            if match:
                values = tuple(float(v) for v in match.group(3).split())
                max_von_mises = max(max_von_mises, _von_mises(values))  # type: ignore[arg-type]
                stress_rows += 1
    if displacement_rows == 0:
        raise ValueError(f"no displacement rows found in CalculiX result {path}")
    if stress_rows == 0:
        raise ValueError(f"no stress rows found in CalculiX result {path}")
    return {
        "max_displacement_m": max_displacement,
        "max_von_mises_pa": max_von_mises,
        "displacement_rows": displacement_rows,
        "reaction_force_n": reaction_force,
        "reaction_rows": reaction_rows,
        "stress_rows": stress_rows,
    }


def write_solve_report(
    spec: CaseSpec,
    load: LoadCaseSpec,
    solve_dir: Path,
    *,
    returncode: int,
) -> dict[str, object]:
    results = parse_calculix_dat(solve_dir / "model.dat")
    stress = float(results["max_von_mises_pa"])
    safety_factor = math.inf if stress == 0.0 else spec.material.yield_strength_pa / stress
    input_manifest_path = solve_dir / "input_manifest.json"
    input_manifest = json.loads(input_manifest_path.read_text(encoding="utf-8"))
    payload = {
        "schema": "aeris.fea.solve_report.v1",
        "solver": "calculix",
        "solver_returncode": returncode,
        "status": "converged" if returncode == 0 else "failed",
        "load_case": load.name,
        **results,
        "yield_strength_pa": spec.material.yield_strength_pa,
        "safety_factor_yield": safety_factor,
        "applied_resultant_half_model_n": input_manifest["applied_resultant_half_model_n"],
        "applied_force_vector_half_model_n": input_manifest[
            "applied_force_vector_half_model_n"
        ],
        "load_mapping_relative_error": input_manifest["load_mapping_relative_error"],
        "load_authority": input_manifest["load_authority"],
        "reaction_force_note": (
            "ROOT RF is diagnostic only for expanded S4 shells; it is not used as an "
            "equilibrium acceptance gate."
        ),
    }
    report = solve_dir / "solve_report.json"
    report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
