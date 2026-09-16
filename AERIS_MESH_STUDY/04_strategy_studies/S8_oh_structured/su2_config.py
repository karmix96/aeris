"""An SU2 case for an S8 mesh: the same wing, the same model, a different code.

Cross-code agreement is the one check internal verification cannot give. Where
ADflow and SU2 agree on our own grid, the number is a property of the problem;
where they disagree, one of them is doing something we would never otherwise
see. The configuration below mirrors the campaign's as closely as two codes
allow, and every place they cannot match is named in the comments.

    python su2_config.py --mesh .../gci_C.su2 --alpha 0 --out .../su2_a0
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
#: mission_authority_v1.yaml, the same numbers solve_s8.py hands to ADflow
MISSION = {"mach": 0.0837, "reynolds": 1.53e6, "reynolds_length": 0.9,
           "temperature_K": 278.4, "chord_ref": 0.9, "moment_ref": (0.4, 0.0, 0.0)}

TEMPLATE = """% AERIS S8 cross-check: the ADflow campaign case, in SU2.
SOLVER= RANS
KIND_TURB_MODEL= SA
MATH_PROBLEM= DIRECT
RESTART_SOL= NO

% ---- the operating point, identical to the ADflow runs ----------------------
MACH_NUMBER= {mach}
AOA= {alpha}
SIDESLIP_ANGLE= 0.0
FREESTREAM_TEMPERATURE= {temperature}
REYNOLDS_NUMBER= {reynolds}
REYNOLDS_LENGTH= {reynolds_length}
% SU2's freestream turbulence is set as a ratio like ADflow's; 3 is the TMR's
% prescription and what the campaign now uses.
FREESTREAM_NU_FACTOR= 3.0

% ---- references, identical ---------------------------------------------------
REF_ORIGIN_MOMENT_X= {mx}
REF_ORIGIN_MOMENT_Y= {my}
REF_ORIGIN_MOMENT_Z= {mz}
REF_LENGTH= {chord_ref}
REF_AREA= {area}
REF_DIMENSIONALIZATION= DIMENSIONAL

% ---- boundaries, as write_cgns.py names them ---------------------------------
MARKER_HEATFLUX= ( wall, 0.0 )
MARKER_SYM= ( sym )
MARKER_FAR= ( far )
MARKER_PLOTTING= ( wall )
MARKER_MONITORING= ( wall )

% ---- numerics ----------------------------------------------------------------
% JST is central differencing with artificial dissipation, which is the family
% ADflow's default scheme belongs to. The two are not identical -- no two codes'
% dissipation is -- and that difference is part of what this comparison measures.
NUM_METHOD_GRAD= GREEN_GAUSS
CONV_NUM_METHOD_FLOW= JST
JST_SENSOR_COEFF= ( 0.5, 0.02 )
TIME_DISCRE_FLOW= EULER_IMPLICIT
CONV_NUM_METHOD_TURB= SCALAR_UPWIND
MUSCL_TURB= NO
TIME_DISCRE_TURB= EULER_IMPLICIT

CFL_NUMBER= 5.0
CFL_ADAPT= YES
CFL_ADAPT_PARAM= ( 0.1, 2.0, 1.0, 1e3 )
LINEAR_SOLVER= FGMRES
LINEAR_SOLVER_PREC= ILU
LINEAR_SOLVER_ERROR= 1E-4
LINEAR_SOLVER_ITER= 20

% ---- stopping, matched to the campaign's rule where the codes allow ----------
ITER= {iterations}
CONV_FIELD= RMS_DENSITY
CONV_RESIDUAL_MINVAL= -12
CONV_STARTITER= 25

MESH_FILENAME= {mesh}
MESH_FORMAT= SU2
SCREEN_OUTPUT= ( INNER_ITER, RMS_DENSITY, RMS_NU_TILDE, LIFT, DRAG )
HISTORY_OUTPUT= ( ITER, RMS_RES, AERO_COEFF )
OUTPUT_FILES= ( RESTART, SURFACE_CSV, SURFACE_TECPLOT_ASCII )
VOLUME_OUTPUT= ( COORDINATES, SOLUTION, PRIMITIVE )
WRT_FORCES_BREAKDOWN= YES
BREAKDOWN_FILENAME= forces_breakdown.dat
CONV_FILENAME= history
VOLUME_FILENAME= volume
SURFACE_FILENAME= surface
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mesh", type=Path, required=True)
    ap.add_argument("--alpha", type=float, required=True)
    ap.add_argument("--area", type=float, required=True)
    ap.add_argument("--iterations", type=int, default=8000)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    text = TEMPLATE.format(
        mach=MISSION["mach"], alpha=args.alpha, temperature=MISSION["temperature_K"],
        reynolds=MISSION["reynolds"], reynolds_length=MISSION["reynolds_length"],
        mx=MISSION["moment_ref"][0], my=MISSION["moment_ref"][1], mz=MISSION["moment_ref"][2],
        chord_ref=MISSION["chord_ref"], area=args.area, mesh=args.mesh,
        iterations=args.iterations)
    path = args.out / "case.cfg"
    path.write_text(text)
    (args.out / "case.json").write_text(json.dumps(
        {"schema": "aeris.s8.su2_case.v1", "mission": MISSION, "alpha_deg": args.alpha,
         "area_ref": args.area, "mesh": str(args.mesh),
         "matched_to": "solve_s8.py governed configuration",
         "cannot_match": ["artificial dissipation coefficients are each code's own",
                          "ADflow marches with ANK; SU2 with implicit Euler and CFL ramping",
                          "the stopping rules are each code's own residual norm"]},
        indent=2) + "\n")
    print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
