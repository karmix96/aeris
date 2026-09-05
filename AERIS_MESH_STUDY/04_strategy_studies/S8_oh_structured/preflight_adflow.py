#!/usr/bin/env python
"""Mesh-acceptance preflight: does ADflow accept the S8 O-H grid?

    /home/mike/miniconda3/envs/mach-aero/bin/python \
        AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/preflight_adflow.py \
        --grid AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh/oh_probe_volume.cgns

This is NOT a solve and must not become one.  It constructs the solver, which
reads and partitions the grid and resolves the boundary-condition families, then
reports what ADflow itself saw and exits.  `nCycles` is zero and no solve call is
made, so nothing iterates.

The point is to separate two failure modes that look identical from the outside:
a mesh ADflow will not accept, and a mesh it accepts but cannot converge.  This
answers only the first, cheaply, before anything heavy is authorized.  S6's
policy blocks heavy work (POLICY.yaml, heavy_work.blocked), so the solve itself
belongs in a runbook for the desktop, not here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--grid", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("/tmp/s8_preflight"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    from adflow import ADFLOW

    options = {
        "gridFile": str(args.grid),
        "outputDirectory": str(args.out),
        "equationType": "RANS",
        "turbulenceModel": "SA",
        # Harmless here -- nCycles is 0 and nothing solves, so no direction is
        # ever used -- but the omission is the defect-14 pattern and an options
        # dict that reads as complete should not quietly be missing the one
        # option that voided every S8 result.  AERIS meshes span +y, lift +z.
        "liftIndex": 3,
        "nCycles": 0,
        "writeVolumeSolution": False,
        "writeSurfaceSolution": False,
        "printIterations": False,
        "printTiming": False,
        "monitorVariables": ["resrho"],
    }
    solver = ADFLOW(options=options)

    report = {
        "grid": str(args.grid),
        "accepted": True,
        "families": sorted(solver.families.keys()),
        "wall_families": sorted(
            f for f in solver.families if "wall" in f.lower()
        ),
    }
    try:
        report["n_surface_nodes_wall"] = int(
            solver.getSurfaceCoordinates(groupName="wall").shape[0]
        )
    except Exception as error:  # noqa: BLE001 - reported, not swallowed
        report["n_surface_nodes_wall"] = f"unavailable: {error}"
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
