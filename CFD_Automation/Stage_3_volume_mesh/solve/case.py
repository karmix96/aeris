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
#: The freestream turbulence for SU2's transition models: 0.07 %, N_crit 9, the value similarity fixed (decision 70).
#: The V7 case files had 0.1 %, SU2's Langtry-Menter tutorial value (E387, run in S8).
TURBULENCE_INTENSITY = 0.0007
#: The freestream pressure behind the incompressible SU2 case (ISA sea level; only rho = p/(R T) uses it)
PRESSURE_PA = 101325.0
GAS_CONSTANT = 287.058
GAMMA = 1.4
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
    """The options of one ADflow SA run. ANK only, as the S8 campaign (NK froze at 1.1 M cells with its lean
    settings). Memory, S8's two-point fits (ADR-0020): ANK only 2.69 + 7.23 GiB per M cells; ANK then NK 1.51 + 9.46
    (the law check 14 reports, the higher of the two: decision 112). Stopping: relative residual 1e-6 (S8: the forces move in the fifth
    decimal after it); acceptance is read separately (settled forces, a healthy history)."""
    return {
        "gridFile": str(grid), "outputDirectory": str(out),
        "equationType": "RANS", "turbulenceModel": "SA",
        "liftIndex": 3,                       # span +y, lift +z; ADflow's default 2 turns alpha into sideslip (S8)
        "eddyVisInfRatio": SA_EDDY_VIS_INF_RATIO,
        "MGCycle": "sg", "useANKSolver": True, "ANKSwitchTol": 1.0, "useNKSolver": False,
        "ANKSubspaceSize": 10, "ANKPCILUFill": 1,
        # DECISIONS O1 (Mike, 13 Nov 2026): the turbulence by its own Krylov solve, not one DADI sweep per ANK step.
        # As written the SA residual stalled (V7 night A1: 4.2 orders in 182 iterations); with it 6 orders in 136-239
        # iterations at -5, 4 and +10 deg (A1b, A4, A5). Cost on VVC: +0.7 GiB, +22 % time per iteration.
        "ANKUseTurbDADI": False,
        "L2Convergence": 1.0e-6, "nCycles": 30000, "timeLimit": 86400.0,
        "storeConvHist": True, "writeVolumeSolution": True, "writeSurfaceSolution": True,
        "monitorVariables": ["resrho", "resmom", "resrhoe", "resturb", "cl", "cd", "cmy", "cdp", "cdv"],
        "surfaceVariables": ["cp", "cf", "yplus", "vx", "vy", "vz"],
    }


#: The V7 night's compressible template (SU2 RANS, Roe, Venkatakrishnan 0.05, adaptive CFL to 1e3). Kept as the record
#: (DECISIONS O3): on the Stage 3 mesh it never converged (V7 night B1, B1b, B1c, B2b: 2.1 to 2.8 orders) and its Roe
#: scheme overshot the stagnation pressure at Mach 0.1. Not used.
SU2_COMMON_V7_COMPRESSIBLE = """% AERIS Stage 3, V7: {title}
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


#: The SU2 numerics since 13 Nov 2026 (DECISIONS O3, Mike's yes): the recipe of the SU2 study
#: (data/v7/su2_transition/REPORT.md, run R1f): the incompressible solver (Mach 0.1), FDS, MUSCL, Venkatakrishnan 0.05
#: frozen after the start-up (LIMITER_ITER: the limiter switching at two leading-edge corners held the residual,
#: R1c and D1), adaptive CFL capped at 50 (10 linear iterations cannot hold more, R1e). SA converged from the
#: freestream with it (R1f: 4.83 orders, CL 0.1958, CD 167.8 counts on today's VVC).
SU2_COMMON = """% AERIS Stage 3: {title}
% Mesh: {mesh_name} ({cells} hexahedra). Lengths in mean chords; span +y, lift +z (SU2's AoA turns in x-z).
% Incompressible: the freestream of Mach {mach}, {T} K, {p} Pa, Re {re} on the mean chord (rho = p/(R T),
% |V| = Mach sqrt(gamma R T), mu = rho |V| c / Re); the velocity at {alpha} deg in x-z.
SOLVER= INC_RANS
KIND_TURB_MODEL= {turb}
{model_lines}MATH_PROBLEM= DIRECT
RESTART_SOL= NO
INC_DENSITY_MODEL= CONSTANT
INC_ENERGY_EQUATION= NO
INC_DENSITY_INIT= {rho:.7f}
INC_VELOCITY_INIT= ( {vx:.10f}, 0.0, {vz:.10f} )
INC_NONDIM= INITIAL_VALUES
VISCOSITY_MODEL= CONSTANT_VISCOSITY
MU_CONSTANT= {mu:.7e}
AOA= {alpha}
SIDESLIP_ANGLE= 0.0
REF_ORIGIN_MOMENT_X= {mx}
REF_ORIGIN_MOMENT_Y= {my}
REF_ORIGIN_MOMENT_Z= {mz}
REF_LENGTH= 1.0
REF_AREA= {area}
MARKER_HEATFLUX= ( wall, 0.0 )
MARKER_SYM= ( symmetry )
MARKER_FAR= ( farfield )
MARKER_PLOTTING= ( wall )
MARKER_MONITORING= ( wall )
NUM_METHOD_GRAD= GREEN_GAUSS
CONV_NUM_METHOD_FLOW= FDS
MUSCL_FLOW= YES
SLOPE_LIMITER_FLOW= VENKATAKRISHNAN
VENKAT_LIMITER_COEFF= 0.05
LIMITER_ITER= 500
TIME_DISCRE_FLOW= EULER_IMPLICIT
CONV_NUM_METHOD_TURB= SCALAR_UPWIND
MUSCL_TURB= NO
TIME_DISCRE_TURB= EULER_IMPLICIT
CFL_NUMBER= 1.0
CFL_ADAPT= YES
CFL_ADAPT_PARAM= ( 0.1, 2.0, 1.0, 50 )
LINEAR_SOLVER= FGMRES
LINEAR_SOLVER_PREC= ILU
LINEAR_SOLVER_ERROR= 1E-4
LINEAR_SOLVER_ITER= 10
% stopping: no time limit; SU2 runs to the budget and the run is ended by the acceptance rule of
% solve/read_results.py (data/v7/su2_transition/tools/monitor.py), or by hand on the stall rule
ITER= {iterations}
CONV_FIELD= RMS_PRESSURE
CONV_RESIDUAL_MINVAL= -16
CONV_STARTITER= 25
MESH_FILENAME= {mesh}
MESH_FORMAT= SU2
OUTPUT_FILES= ( RESTART, SURFACE_CSV, SURFACE_TECPLOT_ASCII )
VOLUME_OUTPUT= ( COORDINATES, SOLUTION, PRIMITIVE )
HISTORY_OUTPUT= ( ITER, RMS_RES, AERO_COEFF, CFL_NUMBER, LINSOL )
SCREEN_OUTPUT= ( INNER_ITER, WALL_TIME, RMS_PRESSURE, {screen_turb}LIFT, DRAG )
WRT_FORCES_BREAKDOWN= YES
BREAKDOWN_FILENAME= forces_breakdown.dat
CONV_FILENAME= history
RESTART_FILENAME= restart.dat
SOLUTION_FILENAME= restart.dat
VOLUME_FILENAME= flow
SURFACE_FILENAME= surface_flow
OUTPUT_WRT_FREQ= 250
"""


def su2_config(case: dict, model: str, mesh_file: Path, iterations: int = 99999) -> str:
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
    T, a_deg = case["temperature_K"], case["alpha_deg"]
    rho = PRESSURE_PA / (GAS_CONSTANT * T)
    v = case["mach"] * float(np.sqrt(GAMMA * GAS_CONSTANT * T))
    mu = rho * v * case["reynolds_length"] / case["reynolds"]
    return SU2_COMMON.format(title=title, mesh_name=case["mesh"], cells=case["cells"], turb=turb, model_lines=lines,
                             mach=case["mach"], alpha=a_deg, T=T, p=PRESSURE_PA, re=case["reynolds"], rho=rho,
                             vx=v * float(np.cos(np.radians(a_deg))), vz=v * float(np.sin(np.radians(a_deg))), mu=mu,
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
            "su2": {"version": "8.5.0", "solver": "INC_RANS (the recipe, DECISIONS O3)", "models": ["SA", "SST_LM"], "sa_nu_factor": SA_NU_FACTOR,
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
