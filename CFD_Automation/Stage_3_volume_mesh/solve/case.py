"""One solver case from one Stage 3 mesh folder: the flow conditions, the reference values, the ADflow options and
the SU2 configurations (SA; SST + LM). Plain Python and numpy: runs anywhere, no solver needed.

    python solve/case.py --mesh data/meshes/volume_VC_<hash8>_re3e5 --alpha 4 --mach 0.1 --re 3e5 --out runs/v7_a4

Writes into --out: case.json (every number of the case), adflow_options.json (read by run_adflow.py),
su2_sa.cfg, su2_sst_lm.cfg. Lengths are in mean chords (the mesh unit; similarity, decision 70): the Reynolds number
is on the mean chord (1 mesh unit), the reference chord is 1, the reference area is the half wing's planform area,
the moment reference is the quarter point of the mean aerodynamic chord. Span is +y, lift is +z (liftIndex 3).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

TEMPERATURE_K = 288.15
#: SST + LM: the freestream turbulence of SU2's Langtry-Menter tutorials (E387, run in S8), 0.1 %
TURBULENCE_INTENSITY = 0.001
TURB2LAM_VISC_RATIO = 10.0
#: SA: the TMR's freestream (chi = 3); ADflow's default 0.009 is chi ~ 1.3 (S8 finding)
SA_NU_FACTOR = 3.0
SA_EDDY_VIS_INF_RATIO = 0.21


def references(mesh: Path) -> dict:
    """Half planform area, mean aerodynamic chord and its quarter point, from the wall nodes of the mesh (the
    stations from the root to the tip; the cap, past the tip station, is not in the area)."""
    q = json.loads((mesh / "quality.json").read_text())
    st = q["info"]["stations"]
    y = np.array([s["y"] for s in st])
    c = np.array([s["chord"] for s in st])
    B = np.load(mesh / "blocks.npz")
    wall = np.concatenate([B["CU_in"][:, 0], B["CN_in"][:, 0], B["CL_in"][:, 0]])     # (n, n_stations, 3)
    x_le = wall[..., 0].min(axis=0)
    half = float(np.trapezoid(c, y))
    mac = float(np.trapezoid(c ** 2, y) / half)
    x_le_mac = float(np.trapezoid(x_le * c, y) / half)
    y_mac = float(np.trapezoid(y * c, y) / half)
    return {"area_ref_half": half, "semi_span": float(y[-1]), "chord_ref": 1.0, "mac": mac, "y_mac": y_mac,
            "x_le_mac": x_le_mac, "moment_ref": [x_le_mac + 0.25 * mac, 0.0, 0.0],
            "note": "mean chord 1 by similarity, so the half area equals the semi-span to the area integration error"}


def adflow_options(case: dict, grid: Path, out: Path) -> dict:
    """The options of one ADflow SA run. ANK only (the RAM law of the V0 list, 1.51 + 9.46 GiB per M cells, is for
    ANK; NK would need more memory: S8 gci_M). Stopping: relative residual 1e-6 (S8: the forces move in the fifth
    decimal after it); acceptance is read separately (settled forces, a healthy history)."""
    return {
        "gridFile": str(grid), "outputDirectory": str(out),
        "equationType": "RANS", "turbulenceModel": "SA",
        "liftIndex": 3,                       # span +y, lift +z; ADflow's default 2 turns alpha into sideslip (S8)
        "eddyVisInfRatio": SA_EDDY_VIS_INF_RATIO,
        "MGCycle": "sg", "useANKSolver": True, "ANKSwitchTol": 1.0, "useNKSolver": False,
        "ANKSubspaceSize": 10, "ANKPCILUFill": 1,
        "L2Convergence": 1.0e-6, "nCycles": 30000, "timeLimit": 86400.0,
        "storeConvHist": True, "writeVolumeSolution": True, "writeSurfaceSolution": True,
        "monitorVariables": ["resrho", "resmom", "resrhoe", "resturb", "cl", "cd", "cmy", "cdp", "cdv"],
        "surfaceVariables": ["cp", "cf", "yplus", "vx", "vy", "vz"],
    }


SU2_COMMON = """% AERIS Stage 3, V7: {title}
% Mesh: {mesh_name} ({cells} hexahedra). Lengths in mean chords; span +y, lift +z (SU2's AoA turns in x-z).
SOLVER= RANS
KIND_TURB_MODEL= {turb}
{model_lines}MATH_PROBLEM= DIRECT
RESTART_SOL= NO
MACH_NUMBER= {mach}
AOA= {alpha}
SIDESLIP_ANGLE= 0.0
FREESTREAM_TEMPERATURE= {T}
REYNOLDS_NUMBER= {re}
REYNOLDS_LENGTH= 1.0
REF_ORIGIN_MOMENT_X= {mx}
REF_ORIGIN_MOMENT_Y= {my}
REF_ORIGIN_MOMENT_Z= {mz}
REF_LENGTH= 1.0
REF_AREA= {area}
REF_DIMENSIONALIZATION= FREESTREAM_VEL_EQ_MACH
MARKER_HEATFLUX= ( wall, 0.0 )
MARKER_SYM= ( symmetry )
MARKER_FAR= ( farfield )
MARKER_PLOTTING= ( wall )
MARKER_MONITORING= ( wall )
% numerics: SU2's Langtry-Menter tutorial set (E387), as S8 ran it; JST over-predicts viscous drag on low-Re meshes
NUM_METHOD_GRAD= GREEN_GAUSS
CONV_NUM_METHOD_FLOW= ROE
MUSCL_FLOW= YES
SLOPE_LIMITER_FLOW= VENKATAKRISHNAN
VENKAT_LIMITER_COEFF= 0.05
TIME_DISCRE_FLOW= EULER_IMPLICIT
CONV_NUM_METHOD_TURB= SCALAR_UPWIND
MUSCL_TURB= NO
TIME_DISCRE_TURB= EULER_IMPLICIT
CFL_NUMBER= 1.0
CFL_ADAPT= YES
CFL_ADAPT_PARAM= ( 0.1, 2.0, 1.0, 1e3 )
LINEAR_SOLVER= FGMRES
LINEAR_SOLVER_PREC= ILU
LINEAR_SOLVER_ERROR= 1E-4
LINEAR_SOLVER_ITER= 10
% stopping: the density residual at 1e-12 (absolute, as SU2's tutorials and S8) or the budget; acceptance is
% read from the history afterwards (read_results.py: residual drop and settled forces)
ITER= {iterations}
CONV_FIELD= RMS_DENSITY
CONV_RESIDUAL_MINVAL= -12
CONV_STARTITER= 25
MESH_FILENAME= {mesh}
MESH_FORMAT= SU2
OUTPUT_FILES= ( RESTART, SURFACE_CSV, SURFACE_TECPLOT_ASCII, PARAVIEW )
VOLUME_OUTPUT= ( COORDINATES, SOLUTION, PRIMITIVE )
HISTORY_OUTPUT= ( ITER, RMS_RES, AERO_COEFF, CFL_NUMBER )
SCREEN_OUTPUT= ( INNER_ITER, WALL_TIME, RMS_DENSITY, {screen_turb}LIFT, DRAG )
WRT_FORCES_BREAKDOWN= YES
BREAKDOWN_FILENAME= forces_breakdown.dat
CONV_FILENAME= history
RESTART_FILENAME= restart.dat
VOLUME_FILENAME= flow
SURFACE_FILENAME= surface_flow
OUTPUT_WRT_FREQ= 500
"""


def su2_config(case: dict, model: str, mesh_file: Path, iterations: int = 30000) -> str:
    if model == "SA":
        turb, lines, scr, title = "SA", f"FREESTREAM_NU_FACTOR= {SA_NU_FACTOR}\n", "RMS_NU_TILDE, ", "SU2 SA (fully turbulent), the ADflow case"
    elif model == "SST_LM":
        turb = "SST"
        lines = (f"SST_OPTIONS= V1994m\nKIND_TRANS_MODEL= LM\nFREESTREAM_TURBULENCEINTENSITY= {TURBULENCE_INTENSITY}\n"
                 f"FREESTREAM_TURB2LAMVISCRATIO= {TURB2LAM_VISC_RATIO}\n")
        scr, title = "RMS_INTERMITTENCY, RMS_RE_THETA_T, ", "SU2 SST + LM (Langtry-Menter transition)"
    else:
        raise ValueError(model)
    r = case["references"]
    return SU2_COMMON.format(title=title, mesh_name=case["mesh"], cells=case["cells"], turb=turb, model_lines=lines,
                             mach=case["mach"], alpha=case["alpha_deg"], T=case["temperature_K"], re=case["reynolds"],
                             mx=r["moment_ref"][0], my=r["moment_ref"][1], mz=r["moment_ref"][2], area=r["area_ref_half"],
                             iterations=iterations, mesh=mesh_file, screen_turb=scr)


def make_case(mesh: Path, alpha: float, mach: float, re: float, out: Path) -> dict:
    mesh, out = Path(mesh).resolve(), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    man = json.loads((mesh / "manifest.json").read_text())
    if man["outcome"] == "refused":
        raise SystemExit(f"{mesh.name} was refused: no solver case")
    case = {"mesh": man["name"], "mesh_folder": str(mesh), "mesh_node_hash": man["mesh_node_hash"],
            "wing": f"{man['wing_type']} {man['set']} {man['index']}", "level": man["level"], "cells": man["cells"],
            "alpha_deg": alpha, "beta_deg": 0.0, "mach": mach, "reynolds": re, "reynolds_length": 1.0,
            "temperature_K": TEMPERATURE_K, "references": references(mesh),
            "adflow": {"model": "SA", "eddyVisInfRatio": SA_EDDY_VIS_INF_RATIO, "ram_gib_law": man["ram_gib_adflow"]},
            "su2": {"version": "8.6.0", "models": ["SA", "SST_LM"], "sa_nu_factor": SA_NU_FACTOR,
                    "turbulence_intensity": TURBULENCE_INTENSITY, "turb2lam_visc_ratio": TURB2LAM_VISC_RATIO},
            "surface_band": "on (decision 81: the band stays on for every run)"}
    (out / "case.json").write_text(json.dumps(case, indent=1))
    (out / "adflow_options.json").write_text(json.dumps(adflow_options(case, mesh / "volume.cgns", out / "adflow"), indent=1))
    for model in ("SA", "SST_LM"):
        (out / f"su2_{model.lower()}.cfg").write_text(su2_config(case, model, mesh / "volume.su2"))
    return case


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--mesh", type=Path, required=True)
    p.add_argument("--alpha", type=float, default=4.0)
    p.add_argument("--mach", type=float, default=0.1)
    p.add_argument("--re", type=float, default=3e5)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    c = make_case(a.mesh, a.alpha, a.mach, a.re, a.out)
    print(json.dumps({k: c[k] for k in ("mesh", "cells", "alpha_deg", "mach", "reynolds", "references")}, indent=1))


if __name__ == "__main__":
    main()
