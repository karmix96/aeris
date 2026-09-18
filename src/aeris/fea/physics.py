"""CalculiX modal, eigenvalue-buckling, and geometrically nonlinear analyses."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Callable

from aeris.fea.calculix import (
    equivalent_nodal_load_lines,
    load_lines,
    model_definition_lines,
    parse_calculix_dat,
    run_calculix,
)
from aeris.fea.case.spec import CaseSpec, LoadCaseSpec
from aeris.fea.mesh import StructuralMesh


def _write(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_modal_deck(
    spec: CaseSpec, mesh: StructuralMesh, mesh_include: Path, output_dir: Path
) -> Path:
    return _write(
        output_dir / "model.inp",
        [
            f"** AERIS modal analysis: {spec.name}",
            *model_definition_lines(spec, mesh, mesh_include),
            "*STEP",
            "*FREQUENCY",
            str(spec.analyses.modal.modes),
            "*NODE FILE, NSET=NALL",
            "U",
            "*END STEP",
        ],
    )


def write_buckling_deck(
    spec: CaseSpec,
    load: LoadCaseSpec,
    mesh: StructuralMesh,
    mesh_include: Path,
    output_dir: Path,
    static_solve_dir: Path,
) -> Path:
    load_block = equivalent_nodal_load_lines(load, mesh, static_solve_dir)
    return _write(
        output_dir / "model.inp",
        [
            f"** AERIS linear buckling analysis: {spec.name} / {load.name}",
            *model_definition_lines(spec, mesh, mesh_include),
            "*STEP",
            "*BUCKLE",
            str(spec.analyses.buckling.modes),
            *load_block,
            "*NODE FILE, NSET=NALL",
            "U",
            "*END STEP",
        ],
    )


def write_nonlinear_deck(
    spec: CaseSpec,
    load: LoadCaseSpec,
    mesh: StructuralMesh,
    mesh_include: Path,
    output_dir: Path,
    static_solve_dir: Path,
) -> Path:
    load_block, _pressures, _metadata = load_lines(load, mesh, static_solve_dir)
    return _write(
        output_dir / "model.inp",
        [
            f"** AERIS geometrically nonlinear analysis: {spec.name} / {load.name}",
            *model_definition_lines(spec, mesh, mesh_include),
            "*STEP, NLGEOM",
            "*STATIC",
            "0.02, 1.0, 1e-08, 0.05",
            *load_block,
            "*NODE PRINT, NSET=NALL",
            "U",
            "*EL PRINT, ELSET=EALL",
            "S",
            "*NODE FILE, NSET=NALL",
            "U",
            "*EL FILE, ELSET=EALL",
            "S",
            "*END STEP",
        ],
    )


_FLOAT = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"


def parse_eigenvalues(log_path: Path) -> list[float]:
    """Parse the eigenvalue table emitted by CalculiX/ARPACK."""
    text = log_path.read_text(encoding="utf-8", errors="replace")
    values: list[float] = []
    in_table = False
    row = re.compile(rf"^\s*\d+\s+({_FLOAT})(?:\s+({_FLOAT}))?")
    for line in text.splitlines():
        lower = line.lower()
        if "mode no" in lower and ("eigenvalue" in lower or "buckling" in lower):
            in_table = True
            continue
        if in_table:
            match = row.match(line)
            if match:
                values.append(float(match.group(1)))
            elif values and not line.strip():
                break
    if not values:
        raise ValueError(f"no eigenvalues found in {log_path}")
    return values


def run_physics_analyses(
    spec: CaseSpec,
    mesh: StructuralMesh,
    mesh_include: Path,
    workdir: Path,
    *,
    echo: Callable[[str], None] | None = None,
    reference_root: Path | None = None,
    topology_note: str | None = None,
) -> dict[str, object]:
    report: dict[str, object] = {
        "schema": "aeris.fea.physics_report.v1",
        "status": "pass",
        "checks": {},
        "analyses": {},
    }
    if topology_note:
        report["topology"] = topology_note
    checks: dict[str, bool] = report["checks"]  # type: ignore[assignment]
    analyses: dict[str, object] = report["analyses"]  # type: ignore[assignment]
    load_by_name = {load.name: load for load in spec.loads}

    def reference_dir(load_name: str) -> Path:
        return (
            reference_root / load_name
            if reference_root is not None
            else workdir.parent / "solve" / load_name
        )

    if spec.analyses.modal.enabled:
        output = workdir / "modal"
        deck = write_modal_deck(spec, mesh, mesh_include, output)
        returncode = run_calculix(deck, executable=spec.solver.executable, echo=echo)
        if returncode != 0:
            raise ValueError(f"CalculiX modal analysis failed with exit code {returncode}")
        eigenvalues = parse_eigenvalues(output / "model.dat")
        frequencies = [math.sqrt(value) / (2.0 * math.pi) for value in eigenvalues if value > 0.0]
        if not frequencies:
            raise ValueError("modal analysis returned no positive frequencies")
        passed = frequencies[0] >= spec.analyses.modal.minimum_first_frequency_hz
        checks["modal_minimum_frequency"] = passed
        analyses["modal"] = {
            "eigenvalues_rad2_s2": eigenvalues,
            "frequencies_hz": frequencies,
            "first_frequency_hz": frequencies[0],
            "minimum_first_frequency_hz": spec.analyses.modal.minimum_first_frequency_hz,
        }

    if spec.analyses.buckling.enabled:
        load_name = spec.analyses.buckling.load_case
        assert load_name is not None
        output = workdir / "buckling"
        deck = write_buckling_deck(
            spec,
            load_by_name[load_name],
            mesh,
            mesh_include,
            output,
            reference_dir(load_name),
        )
        returncode = run_calculix(deck, executable=spec.solver.executable, echo=echo)
        if returncode != 0:
            raise ValueError(f"CalculiX buckling analysis failed with exit code {returncode}")
        factors = parse_eigenvalues(output / "model.dat")
        positive = [value for value in factors if value > 0.0]
        if not positive:
            raise ValueError("buckling analysis returned no positive load factors")
        passed = positive[0] >= spec.analyses.buckling.minimum_load_factor
        checks["buckling_minimum_load_factor"] = passed
        analyses["buckling"] = {
            "load_case": load_name,
            "load_factors": factors,
            "first_positive_load_factor": positive[0],
            "minimum_load_factor": spec.analyses.buckling.minimum_load_factor,
        }

    if spec.analyses.nonlinear.enabled:
        nonlinear: dict[str, object] = {}
        for load_name in spec.analyses.nonlinear.load_cases:
            output = workdir / "nonlinear" / load_name
            deck = write_nonlinear_deck(
                spec,
                load_by_name[load_name],
                mesh,
                mesh_include,
                output,
                reference_dir(load_name),
            )
            returncode = run_calculix(deck, executable=spec.solver.executable, echo=echo)
            if returncode != 0:
                raise ValueError(
                    f"CalculiX nonlinear analysis {load_name!r} failed with exit code {returncode}"
                )
            result = parse_calculix_dat(output / "model.dat")
            linear = json.loads(
                (reference_dir(load_name) / "solve_report.json").read_text(
                    encoding="utf-8"
                )
            )
            difference = abs(
                float(result["max_displacement_m"]) - float(linear["max_displacement_m"])
            ) / max(float(result["max_displacement_m"]), 1e-30)
            passed = difference <= spec.analyses.nonlinear.maximum_linear_displacement_difference
            checks[f"nonlinear_displacement:{load_name}"] = passed
            nonlinear[load_name] = {
                **result,
                "linear_displacement_m": linear["max_displacement_m"],
                "linear_relative_difference": difference,
                "maximum_linear_relative_difference": (
                    spec.analyses.nonlinear.maximum_linear_displacement_difference
                ),
            }
        analyses["nonlinear"] = nonlinear

    report["status"] = "pass" if all(checks.values()) else "fail"
    path = workdir / "physics_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
