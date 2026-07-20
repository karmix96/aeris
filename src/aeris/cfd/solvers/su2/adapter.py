"""
SU2 solver adapter: prepare/run/parse with the same contract as ADflow.

``prepare`` resolves the layered options into a provenance-annotated
``.cfg`` (SU2's native input — no runner script needed), ``run`` executes
``mpirun -np N SU2_CFD case.cfg``, ``parse`` normalizes ``history.csv``
into the same ``solve_report.v1`` schema ADflow writes — the cross-solver
comparison artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

from aeris.cfd.case.spec import SolveSpec
from aeris.cfd.env import su2_cfd, su2_mpirun
from aeris.cfd.options.layers import OptionLayer
from aeris.cfd.options.manifest import write_effective_options_manifest
from aeris.cfd.presets.registry import get_preset
from aeris.cfd.solvers.base import (
    PreparedRun,
    SolverAdapter,
    SolveReport,
    write_solve_report,
)
from aeris.cfd.solvers.su2.cfg_writer import write_su2_cfg
from aeris.cfd.solvers.su2.options_schema import build_su2_options
from aeris.cfd.solvers.su2.parse import parse_history_csv

DEFAULT_SOLVER_PRESET = "su2_rans_sa_v1"

CFG_NAME = "case.cfg"
MANIFEST_NAME = "su2_effective_options.json"
CASE_JSON_NAME = "su2_case.json"
RUN_LOG_NAME = "su2_run.log"
HISTORY_NAME = "history.csv"

# Fallback marker names matching the CGNS FamilyName tags pyHyp writes
# (verified on a generated O-grid 2026-07-20: wall / Far / Sym).  When the
# mesh is a .su2 file its MARKER_TAG lines are scanned instead — the mesh
# itself is the authority on which markers exist.
DEFAULT_MARKERS = {
    "marker_wall": "( wall, 0.0 )",
    "marker_far": "( Far )",
    "marker_sym": "( Sym )",
    "marker_monitoring": "( wall )",
}


def markers_from_su2_mesh(su2_path: Path) -> dict[str, str]:
    """Derive SU2 marker options from the MARKER_TAG lines of a .su2 mesh.

    Tags are classified by prefix: wall* -> viscous wall, far* -> farfield,
    sym* -> symmetry.  Unrecognized tags are left for the user to assign
    via curated options / raw pass-through.  Falls back to DEFAULT_MARKERS
    when no tags are found (e.g. a dummy or truncated file).
    """
    tags: list[str] = []
    with Path(su2_path).open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("MARKER_TAG"):
                tags.append(line.split("=", 1)[1].strip())
    if not tags:
        return dict(DEFAULT_MARKERS)
    walls = [t for t in tags if t.lower().startswith("wall")]
    fars = [t for t in tags if t.lower().startswith("far")]
    syms = [t for t in tags if t.lower().startswith("sym")]
    markers: dict[str, str] = {}
    if walls:
        markers["marker_wall"] = "( " + ", ".join(f"{t}, 0.0" for t in walls) + " )"
        markers["marker_monitoring"] = "( " + ", ".join(walls) + " )"
    if fars:
        markers["marker_far"] = "( " + ", ".join(fars) + " )"
    if syms:
        markers["marker_sym"] = "( " + ", ".join(syms) + " )"
    return markers


class Su2Adapter(SolverAdapter):
    SOLVER_ID = "su2"

    def prepare(self, solve: SolveSpec, mesh_cgns: Path, workdir: Path) -> PreparedRun:
        if solve.flow is None:
            raise ValueError("solve.flow (alpha/mach/reynolds) is required for SU2")
        if solve.area_ref is None or solve.chord_ref is None:
            raise ValueError("solve.area_ref and solve.chord_ref are required for SU2")
        workdir = workdir.expanduser().resolve()
        workdir.mkdir(parents=True, exist_ok=True)
        mesh_cgns = mesh_cgns.expanduser().resolve()
        if not mesh_cgns.is_file():
            raise FileNotFoundError(f"volume mesh not found: {mesh_cgns}")

        # SU2's CGNS reader is unstructured-only (8.5.0 aborts on pyHyp's
        # structured output — measured); convert to native .su2 with the
        # node set preserved so the same-grid verification claim holds.
        mesh_file = mesh_cgns
        suffix = mesh_cgns.suffix.lower()
        if suffix == ".cgns":
            from aeris.cfd.solvers.su2.mesh_convert import convert_structured_cgns_to_su2

            mesh_file = workdir / "mesh.su2"
            convert_structured_cgns_to_su2(mesh_cgns, mesh_file)
            mesh_format = "SU2"
        elif suffix == ".su2":
            mesh_format = "SU2"
        else:
            mesh_format = "CGNS"

        markers = (
            markers_from_su2_mesh(mesh_file)
            if mesh_file.suffix.lower() == ".su2" and mesh_file.is_file()
            else dict(DEFAULT_MARKERS)
        )
        flow_layer = OptionLayer(
            "flow",
            {
                "mach": solve.flow.mach,
                "aoa": solve.flow.alpha,
                "reynolds": solve.flow.reynolds,
                "reynolds_length": solve.chord_ref,
                "freestream_temperature": solve.flow.temperature,
                "ref_area": solve.area_ref,
                "ref_length": solve.chord_ref,
                **markers,
            },
        )
        extra_layers: list[OptionLayer] = [flow_layer]
        preset_name = solve.preset or DEFAULT_SOLVER_PRESET
        preset = get_preset(preset_name)
        if preset.solver:
            extra_layers.append(OptionLayer(f"preset:{preset.name}", dict(preset.solver)))
        if solve.overrides:
            extra_layers.append(OptionLayer("config", dict(solve.overrides)))

        extra_layers.insert(1, OptionLayer("derived", {"mesh_format": mesh_format}))
        effective = build_su2_options(
            mesh_file,
            extra_layers=extra_layers,
            su2_options=solve.raw_options or None,
        )

        cfg_path = write_su2_cfg(
            workdir / CFG_NAME,
            effective,
            header=f"mesh: {mesh_cgns.name} | preset: {preset_name}",
        )
        write_effective_options_manifest(
            workdir / MANIFEST_NAME,
            effective=effective,
            input_files={"volume_mesh": mesh_cgns},
            extra={"solver_preset": preset_name},
        )
        (workdir / CASE_JSON_NAME).write_text(
            json.dumps(
                {
                    "alpha": solve.flow.alpha,
                    "mach": solve.flow.mach,
                    "reynolds": solve.flow.reynolds,
                    "temperature": solve.flow.temperature,
                    "area_ref": solve.area_ref,
                    "chord_ref": solve.chord_ref,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        command = (
            str(su2_mpirun()),
            "-np",
            str(solve.mpi_np),
            str(su2_cfd()),
            str(cfg_path),
        )
        return PreparedRun(
            solver_id=self.SOLVER_ID,
            workdir=workdir,
            command=command,
            log_name=RUN_LOG_NAME,
            artifacts={
                "cfg": str(cfg_path),
                "effective_options": str(workdir / MANIFEST_NAME),
                "case": str(workdir / CASE_JSON_NAME),
            },
        )

    def parse(self, workdir: Path) -> SolveReport:
        workdir = workdir.expanduser().resolve()
        case = json.loads((workdir / CASE_JSON_NAME).read_text(encoding="utf-8"))
        history_path = workdir / HISTORY_NAME

        convergence: dict[str, object] = {}
        forces: dict[str, float] = {}
        status = "failed"
        if history_path.is_file():
            history = parse_history_csv(history_path)
            forces = dict(history.pop("final_coefficients", {}))
            convergence = history
            if forces and history.get("iterations", 0) > 0:
                status = "converged"

        report = SolveReport(
            solver_id=self.SOLVER_ID,
            status=status,
            flow={
                "alpha": case["alpha"],
                "mach": case["mach"],
                "reynolds": case["reynolds"],
                "temperature": case["temperature"],
            },
            refs={"area_ref": case["area_ref"], "chord_ref": case["chord_ref"]},
            forces=forces,
            convergence=convergence,
            artifacts={
                "history": str(history_path),
                "log": str(workdir / RUN_LOG_NAME),
                "effective_options": str(workdir / MANIFEST_NAME),
            },
        )
        write_solve_report(workdir, report)
        return report
