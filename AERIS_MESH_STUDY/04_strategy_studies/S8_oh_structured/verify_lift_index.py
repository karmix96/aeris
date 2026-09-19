#!/usr/bin/env python
"""Prove which lift axis ADflow builds for an AERIS mesh, at both settings.

    /home/mike/miniconda3/envs/mach-aero/bin/python \
        AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/verify_lift_index.py \
        --grid AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/runs/paraview_inspection/s8_oh/oh_probe_volume.cgns

This is a measurement, not a solve: `nCycles` is zero and no solve call is made.
It constructs the solver at each `liftIndex` and each angle of attack, calls
`setAeroProblem`, and reads back the freestream and lift directions ADflow
actually built.

Why it exists.  `solve_s8.py` omitted `liftIndex`, so it ran at ADflow's default
of 2, which rotates alpha about z -- into the SPANWISE direction on an AERIS
mesh, against a root symmetry plane that forbids spanwise crossflow.  The
evidence for that was a `VelocityUnitVector` of (0.990268, 0.139173, 0) written
into the alpha-8 surface file.  This script turns that piece of forensics into a
repeatable check that anybody can re-run, and it records what the correct
setting produces so the two are on the same page of the record.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

MISSION = {
    "mach": 0.0837,
    "reynolds": 1530708.188575197,
    "reynolds_length_m": 0.9,
    "temperature_K": 278.4,
    "chord_ref_m": 0.9,
}
AREA_REF_M2 = 0.394918242017589


def probe(grid: Path, out: Path, lift_index: int, alphas: list[float]) -> list[dict]:
    from adflow import ADFLOW
    from baseclasses import AeroProblem

    solver = ADFLOW(options={
        "gridFile": str(grid),
        "outputDirectory": str(out),
        "equationType": "RANS",
        "turbulenceModel": "SA",
        "liftIndex": lift_index,
        "nCycles": 0,
        "writeVolumeSolution": False,
        "writeSurfaceSolution": False,
        "printIterations": False,
        "printTiming": False,
        "monitorVariables": ["resrho"],
    })
    rows = []
    for alpha in alphas:
        problem = AeroProblem(
            name=f"probe_li{lift_index}_a{alpha:g}",
            alpha=alpha,
            beta=0.0,
            mach=MISSION["mach"],
            reynolds=MISSION["reynolds"],
            reynoldsLength=MISSION["reynolds_length_m"],
            T=MISSION["temperature_K"],
            areaRef=AREA_REF_M2,
            chordRef=MISSION["chord_ref_m"],
            evalFuncs=["cl", "cd"],
        )
        solver.setAeroProblem(problem)
        physics = solver.adflow.inputphysics
        vel = np.array(physics.veldirfreestream, dtype=float).ravel()[:3]
        lift = np.array(physics.liftdirection, dtype=float).ravel()[:3]
        drag = np.array(physics.dragdirection, dtype=float).ravel()[:3]
        rad = np.radians(alpha)
        rows.append({
            "lift_index": lift_index,
            "alpha_deg": alpha,
            "velocity_direction": vel.tolist(),
            "lift_direction": lift.tolist(),
            "drag_direction": drag.tolist(),
            "spanwise_velocity_component": float(vel[1]),
            "vertical_velocity_component": float(vel[2]),
            "matches_span_y_lift_z": bool(
                abs(vel[1]) < 1e-12
                and abs(vel[2] - np.sin(rad)) < 1e-9
                and abs(lift[2] - np.cos(rad)) < 1e-9
            ),
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--grid", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/runs/s8_cfd/lift_index_probe"))
    ap.add_argument("--alphas", type=float, nargs="+", default=[0.0, 4.0, 8.0])
    ap.add_argument("--report", type=Path, default=None)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for lift_index in (2, 3):
        rows.extend(probe(args.grid, args.out, lift_index, list(args.alphas)))

    print(f"\n{'liftIndex':>10}{'alpha':>7}   {'velocity direction':<34}"
          f"{'v_y (sideslip)':>16}{'ok':>5}")
    for r in rows:
        v = "(" + ", ".join(f"{c:+.6f}" for c in r["velocity_direction"]) + ")"
        print(f"{r['lift_index']:>10}{r['alpha_deg']:>7.1f}   {v:<34}"
              f"{r['spanwise_velocity_component']:>16.6f}"
              f"{'  yes' if r['matches_span_y_lift_z'] else '   NO':>5}")

    report = {
        "schema": "aeris.s8.lift_index_probe.v1",
        "grid": str(args.grid),
        "geometry_convention": "AERIS meshes span +y, lift +z",
        "adflow_default_lift_index": 2,
        "required_lift_index": 3,
        "method": "ADflow constructed with nCycles 0, setAeroProblem called, "
                  "inputphysics direction arrays read back. No solve.",
        "rows": rows,
    }
    out = args.report or (args.out / "lift_index_probe.json")
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
