"""Establish SU2 before it is trusted: its developers' validated cases, reproduced first.

Stage 0 of the SU2 validation ladder, agreed with the principal investigator on 2026-09-15:
from here SU2 is to become a direct alternative to ADflow, and it is validated first.

Why stage 0 is SU2's own tutorials. SU2 on the AERIS wing carried 22-27 % more friction
drag than ADflow, and on the NACA 0012 TMR case 15 % more than the answer three codes agree
on (reports/s8_su2_naca0012.json). Those runs used numerics copied from SU2's ONERA M6
tutorial -- JST with Green-Gauss gradients, a transonic coarse-mesh setup. SU2's own
low-speed turbulent tutorials use upwind schemes with MUSCL reconstruction instead (Roe on
the compressible flat plate, FDS in the incompressible solver). So SU2 is first run on the
cases its developers validated, with their configuration files UNCHANGED except for where
and what it writes, and judged against the references those cases were built for:

  verification against NASA TMR answers
    fp_comp_137, fp_comp_545   compressible SA flat plate on TMR's 137x97 and 545x385 grids
    fp_inc_545                 incompressible SA flat plate, 545x385
    naca0012_inc_897           incompressible SA NACA 0012, TMR 897x257, alpha 10, Re 6e6
  transition, against experiment (reference data to be added before they are judged)
    fp_bc                      SA with the B-C transition model, Schubauer & Klebanoff plate
    t3a, t3a_minus             SST with Langtry-Menter, ERCOFTAC T3A and T3A-
    e387_sa_lm, e387_sst_lm    Eppler 387, Re 200k, alpha 2 (NASA Langley LTPT data)
    nlf_sst_lm                 natural-laminar-flow airfoil, Re 4e6

Every change made to a tutorial file is written to changes.json beside the run, and all of
them are output-only: file names, output fields, write frequency.

Criteria, set before any result exists:
  flat plate    skin friction at x = 0.97 and plate drag within 1 % of the mean of CFL3D and
                FUN3D on the SAME grid (they differ by 0.01-0.3 % there)
  NACA 0012     friction drag within 1 % of TMR; total drag within 2 %; lift within 1 % of
                TMR's M 0.15 value taken to incompressible by Prandtl-Glauert (x 0.9887)

    python su2_validation.py config  --case fp_comp_545
    (cd artifacts/su2_validation/fp_comp_545 && mpirun -np 2 SU2_CFD case.cfg > run.log)
    python su2_validation.py compare --case fp_comp_545        # or --all
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
TUTORIALS = STUDY / "artifacts/su2_tutorials"
RUNS = STUDY / "artifacts/su2_validation"
TMR_FP = STUDY / "05_s6_cfd_qualification/external/tmr_flatplate"
E387 = STUDY / "05_s6_cfd_qualification/external/e387"
REPORT = STUDY / "05_s6_cfd_qualification/reports/s8_su2_validation.json"

CASES = {
    "fp_comp_137": ("compressible_flow/Turbulent_Flat_Plate", "turb_SA_flatplate.cfg",
                    "mesh_flatplate_turb_137x97.su2", "flatplate"),
    "fp_comp_545": ("compressible_flow/Turbulent_Flat_Plate", "turb_SA_flatplate.cfg",
                    "mesh_flatplate_turb_545x385.su2", "flatplate"),
    "fp_inc_545": ("incompressible_flow/Inc_Turbulent_Flat_Plate", "turb_flatplate.cfg",
                   "mesh_flatplate_turb_545x385.su2", "flatplate_inc"),
    "naca0012_inc_897": ("incompressible_flow/Inc_Turbulent_NACA0012", "turb_naca0012.cfg",
                         "n0012_897-257.su2", "naca0012"),
    "fp_bc": ("compressible_flow/Transitional_Flat_Plate", "transitional_BC_model_ConfigFile.cfg",
              "grid.su2", "transition_plate"),
    "t3a": ("compressible_flow/Transitional_Flat_Plate/Langtry_and_Menter/T3A",
            "transitional_LM_model_ConfigFile.cfg", "grid.su2", "transition_plate"),
    "t3a_minus": ("compressible_flow/Transitional_Flat_Plate/Langtry_and_Menter/T3A-",
                  "transitional_LM_model_ConfigFile.cfg", "grid.su2", "transition_plate"),
    "e387_sa_lm": ("compressible_flow/Transitional_Airfoil/Langtry_and_Menter/E387",
                   "transitional_SA_LM_model_ConfigFile.cfg", "ogrid_e387.su2", "airfoil"),
    "e387_sst_lm": ("compressible_flow/Transitional_Airfoil/Langtry_and_Menter/E387",
                    "transitional_SST_LM_model_ConfigFile.cfg", "ogrid_e387.su2", "airfoil"),
    "nlf_sst_lm": ("compressible_flow/Transitional_Airfoil/Langtry_and_Menter/NLF",
                   "transitional_LM_model_ConfigFile.cfg", "grid.su2", "airfoil"),
}
#: what SU2 writes and where -- nothing that changes the solution
OUTPUT_ONLY = {
    # SURFACE_CSV carries only the solution variables; skin friction, y+ and the pressure
    # coefficient reach a file only through the Tecplot or ParaView surface writers. The first
    # stage-0 runs wrote CSV alone, so their flat-plate criterion -- cf at x = 0.97 -- could not
    # be evaluated at all.
    "OUTPUT_FILES": "( RESTART, SURFACE_CSV, SURFACE_TECPLOT_ASCII )",
    "VOLUME_OUTPUT": "( COORDINATES, SOLUTION, PRIMITIVE )",
    "HISTORY_OUTPUT": "( ITER, RMS_RES, AERO_COEFF, CFL_NUMBER )",
    "WRT_FORCES_BREAKDOWN": "YES", "BREAKDOWN_FILENAME": "forces_breakdown.dat",
    "CONV_FILENAME": "history", "SURFACE_FILENAME": "surface_flow",
    "RESTART_FILENAME": "restart.dat", "OUTPUT_WRT_FREQ": "1000",
}
X_CF = 0.970084071            # TMR's skin-friction station
NACA_TMR = {"CL": 1.09094, "CD": 0.0122728, "CDp": 0.006067, "CDv": 0.0062059}
# McGhee TM-4062 table A1, row 6 -- computed for this exact run condition (R = 200,000,
# M = 0.06, q = 0.033 psi). This is what "agreement" can mean for the E387 cases. The report's
# familiar "+/-2 drag counts" holds only above q = 0.08 psi and does NOT apply here.
E387_UNCERTAINTY = {"CD": 0.00026, "CL": 0.001, "CM": 0.0004}
# and repeating the same angle with decreasing alpha (run 11) moved the drag 3 counts, so 118
# counts is 118 +/- 3 before any instrument uncertainty is counted
E387_HYSTERESIS_CD = 0.0003
PRANDTL_GLAUERT_TO_INCOMPRESSIBLE = math.sqrt(1.0 - 0.15 ** 2)


def cfg_value(lines: list[str], key: str) -> str | None:
    for line in lines:
        s = line.split("%")[0]
        if "=" in s and s.split("=")[0].strip() == key:
            return s.split("=", 1)[1].strip()
    return None


def cmd_config(args) -> int:
    folder, cfg, mesh, _ = CASES[args.case]
    source = TUTORIALS / folder / cfg
    lines = source.read_text().splitlines()
    changes = {**OUTPUT_ONLY, "MESH_FILENAME": str(TUTORIALS / folder / mesh)}
    if getattr(args, "restart", False):
        # continue a run that was killed at its time limit rather than start again:
        # the three cases of stage 0's first group each wrote a restart file before
        # queue21's five-hour guard stopped them, two of them nearly settled
        changes.update({"RESTART_SOL": "YES", "SOLUTION_FILENAME": "restart.dat",
                        "RESTART_FILENAME": "restart_cont.dat", "CONV_FILENAME": "history_cont",
                        "BREAKDOWN_FILENAME": "forces_breakdown.dat"})
    recorded, seen, out = {}, set(), []
    for line in lines:
        key = line.split("%")[0].split("=")[0].strip() if "=" in line.split("%")[0] else None
        if key in changes:
            recorded[key] = {"tutorial": cfg_value([line], key), "here": changes[key]}
            out.append(f"{key}= {changes[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in changes.items():
        if key not in seen:
            recorded[key] = {"tutorial": None, "here": value}
            out.append(f"{key}= {value}")
    directory = RUNS / args.case
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "case.cfg").write_text("\n".join(out) + "\n")
    (directory / "changes.json").write_text(json.dumps(
        {"source": str(source), "output_only_changes": recorded}, indent=2) + "\n")
    print(f"  {args.case}: {source.name} with {len(recorded)} output-only changes")
    return 0


# ----------------------------------------------------------------------------- reading results

def history(directory: Path) -> dict:
    path = directory / "history.csv"
    if not path.exists():
        return {}
    rows = list(csv.reader(open(path)))
    head = [c.strip().strip('"') for c in rows[0]]
    data = [r for r in rows[1:] if len(r) == len(head)]
    if not data:
        return {}
    rms = {h: (float(data[0][i]), float(data[-1][i])) for i, h in enumerate(head) if h.startswith("rms[")}
    return {"iterations": int(float(data[-1][head.index("Inner_Iter")])) if "Inner_Iter" in head else len(data),
            "rms_first_last": rms,
            "orders_dropped": {h: round(a - b, 2) for h, (a, b) in rms.items()}}


def forces(directory: Path) -> dict | None:
    path = directory / "forces_breakdown.dat"
    if not path.exists():
        return None
    text = path.read_text()
    number = r"([-\d.eE+]+)"

    def total(key):
        m = re.search(rf"Total {key}:\s+{number} \| Pressure \(\s*-?\d+%\):\s+{number} \| "
                      rf"Friction \(\s*-?\d+%\):\s+{number}", text)
        return [float(v) for v in m.groups()] if m else None

    cl, cd = total("CL"), total("CD")
    if not cl or not cd:
        return None
    out = {"CL": cl[0], "CD": cd[0], "CDp": cd[1], "CDv": cd[2]}
    cm = total("CMz")
    if cm:
        # Kept with SU2's sign, which is opposite to the NASA reports: their pitching moment is
        # nose-down negative about the quarter chord, so E387's CMz = +0.0781 here is McGhee's
        # -0.0794. Graders compare magnitudes; comparing signed values scores a correct run at
        # roughly -200 %.
        out["CMz"] = cm[0]
    return out


def surface(directory: Path) -> dict | None:
    """Wall values, preferring the Tecplot surface file: it is the only one that carries the
    derived quantities (skin friction, y+, pressure coefficient)."""
    tecplot = directory / "surface_flow.dat"
    if tecplot.exists():
        head, rows = None, []
        for line in tecplot.read_text().splitlines():
            s = line.strip()
            if s.upper().startswith("VARIABLES"):
                head = [p.strip().strip('"') for p in s.split("=", 1)[1].split(",")]
            elif head and s and (s[0].isdigit() or s[0] in "-+."):
                parts = s.split()
                if len(parts) >= len(head):
                    rows.append([float(v) for v in parts[:len(head)]])
        if head and rows:
            data = np.array(rows)
            col = {h: data[:, i] for i, h in enumerate(head)}
            cf = next((h for h in head if h.lower().startswith("skin_friction_coefficient_x")), None)
            yplus = next((h for h in head if h.lower() == "y_plus"), None)
            return {"x": col.get("x"), "y": col.get("y"),
                    "cf": col.get(cf) if cf else None, "yplus": col.get(yplus) if yplus else None,
                    "columns": head, "file": tecplot.name}
    path = directory / "surface_flow.csv"
    if not path.exists():
        return None
    rows = list(csv.reader(open(path)))
    head = [c.strip().strip('"') for c in rows[0]]
    data = np.array([[float(v) for v in r] for r in rows[1:] if len(r) == len(head)])
    col = {h: data[:, i] for i, h in enumerate(head)}
    cf = next((h for h in head if h.lower().startswith("skin_friction_coefficient_x")), None)
    return {"x": col.get("x"), "y": col.get("y"), "cf": col.get(cf) if cf else None, "columns": head}


def cells(mesh: Path) -> int:
    with open(mesh) as fh:
        for _ in range(5):
            line = fh.readline()
            if line.startswith("NELEM"):
                return int(line.split("=")[1])
    return -1


def tmr_by_grid(path: Path) -> dict:
    """TMR convergence files: {code: {cells: value}}."""
    zones, name = {}, None
    for line in path.read_text().splitlines():
        s = line.strip()
        m = re.match(r'zone\s*,?\s*t\s*=\s*"([^"]+)"', s, re.I)
        if m:
            name = m.group(1); zones[name] = {}
        elif name and s and s[0].isdigit():
            parts = s.split()
            zones[name][int(float(parts[0]))] = float(parts[-1])
    return zones


# ----------------------------------------------------------------------------- judging

def judge_flatplate(case: str, directory: Path, entry: dict) -> None:
    folder, _, mesh, kind = CASES[case]
    n = cells(TUTORIALS / folder / mesh)
    surf, f = surface(directory), forces(directory)
    cf_file = TMR_FP / ("cf_incomp_results_sa.dat" if kind == "flatplate_inc" else "cf_convergence.dat")
    cf_ref = {code: v[n] for code, v in tmr_by_grid(cf_file).items() if n in v}
    cd_ref = {code: v[n] for code, v in tmr_by_grid(TMR_FP / "drag_convergence.dat").items() if n in v}
    entry.update({"cells": n, "reference_cf_x0.97_same_grid": cf_ref, "reference_cd_same_grid": cd_ref})
    if surf is not None and surf["cf"] is not None:
        order = np.argsort(surf["x"])
        cf = float(np.interp(X_CF, surf["x"][order], surf["cf"][order]))
        entry["cf_x0.97"] = cf
        if cf_ref:
            mean = sum(cf_ref.values()) / len(cf_ref)
            entry["cf_error_pct"] = 100 * (cf - mean) / mean
            entry["cf_pass"] = abs(entry["cf_error_pct"]) <= 1.0
    if f and cd_ref:
        mean = sum(cd_ref.values()) / len(cd_ref)
        entry["CD"] = f["CD"]
        entry["cd_error_pct"] = 100 * (f["CD"] - mean) / mean
        entry["cd_pass"] = abs(entry["cd_error_pct"]) <= 1.0


def judge_naca(directory: Path, entry: dict) -> None:
    f = forces(directory)
    if not f:
        return
    ref = dict(NACA_TMR, CL=NACA_TMR["CL"] * PRANDTL_GLAUERT_TO_INCOMPRESSIBLE)
    # over the reference's keys, not the run's. forces() also returns CMz now, and the TMR table
    # carries no moment, so iterating the run's keys raised KeyError('CMz') and left this case
    # ungraded -- the only thing that caught it was that compare records exceptions.
    err = {k: 100 * (f[k] - ref[k]) / ref[k] for k in ref}
    entry.update({"forces": f, "reference": ref, "error_pct": err,
                  "reference_note": "TMR SA at M 0.15, lift taken to M 0 by Prandtl-Glauert",
                  "pass": {"CDv": abs(err["CDv"]) <= 1.0, "CD": abs(err["CD"]) <= 2.0,
                           "CL": abs(err["CL"]) <= 1.0}})


def reynolds_per_length(lines: list[str]) -> float | None:
    solver = (cfg_value(lines, "SOLVER") or "").upper()
    if solver.startswith("INC"):
        rho = float(cfg_value(lines, "INC_DENSITY_INIT") or "nan")
        vel = [float(v) for v in re.findall(r"[-\d.eE+]+", cfg_value(lines, "INC_VELOCITY_INIT") or "")]
        mu = float(cfg_value(lines, "MU_CONSTANT") or "nan")
        return rho * math.hypot(*vel[:2]) / mu if vel else None
    re_number = cfg_value(lines, "REYNOLDS_NUMBER")
    length = float(cfg_value(lines, "REYNOLDS_LENGTH") or 1.0)
    return float(re_number) / length if re_number else None


def read_table(path: Path) -> list[list[float]]:
    """Whitespace columns, '#' comments, 'nan' where the report has no measurement."""
    rows = []
    for line in path.read_text().splitlines():
        stripped = line.split("#")[0].strip()
        if stripped:
            rows.append([float(v) for v in stripped.split()])
    return rows


def e387_reference(alpha: float, re_number: float) -> dict | None:
    """McGhee's measurement at the angle actually run, or None where he did not measure."""
    if not abs(re_number - 200000.0) < 1000.0:
        return None
    rows = [r for r in read_table(E387 / "mcghee_TM4062_R200k.dat") if abs(r[0] - alpha) <= 0.1]
    if not rows:
        return None
    a, cl, cd, cm = rows[0]
    out = {"source": "NASA TM-4062 table B1, runs 9,10,13", "alpha_measured_deg": a,
           "CL": cl, "CD": cd, "CM_nose_down_negative": cm}
    bubble = [r for r in read_table(E387 / "mcghee_TM4062_bubble.dat")
              if abs(r[0] - 200000.0) < 1.0 and abs(r[1] - alpha) <= 0.1]
    if bubble and not math.isnan(bubble[0][2]):
        out.update({"x_laminar_separation": bubble[0][2], "x_turbulent_reattachment": bubble[0][3],
                    "bubble_source": "NASA TM-4062 table III, oil flow visualization"})
    return out


def judge_transition(case: str, directory: Path, entry: dict) -> None:
    surf, f = surface(directory), forces(directory)
    lines = (directory / "case.cfg").read_text().splitlines()
    if f:
        entry["forces"] = f
    # Forces come from forces_breakdown.dat, so they are graded whether or not the case wrote a
    # Tecplot surface file: fp_bc and t3a wrote SURFACE_CSV only and would otherwise report
    # "finished": true while being judged on nothing at all.
    ref = (e387_reference(float(cfg_value(lines, "AOA") or "nan"),
                          float(cfg_value(lines, "REYNOLDS_NUMBER") or "nan"))
           if case.startswith("e387") else None)
    if ref:
        entry["reference"] = ref
        if f:
            entry["error_vs_experiment"] = {
                "CL_pct": 100.0 * (f["CL"] - ref["CL"]) / ref["CL"],
                "CD_counts": 1e4 * (f["CD"] - ref["CD"]),
                "CD_pct": 100.0 * (f["CD"] - ref["CD"]) / ref["CD"],
                # magnitudes: SU2's CMz is signed opposite to the report's nose-down-negative
                **({"CM_magnitude_pct":
                    100.0 * (abs(f["CMz"]) - abs(ref["CM_nose_down_negative"]))
                    / abs(ref["CM_nose_down_negative"])} if "CMz" in f else {})}
            entry["within_measurement_uncertainty"] = {
                "CD": bool(abs(f["CD"] - ref["CD"]) <= E387_UNCERTAINTY["CD"]),
                "CL": bool(abs(f["CL"] - ref["CL"]) <= E387_UNCERTAINTY["CL"])}
    if surf is None or surf["cf"] is None:
        entry.setdefault("note", "no skin friction on file: this run wrote SURFACE_CSV only, so "
                                 "nothing needing cf could be judged")
        return
    order = np.argsort(surf["x"])
    x, cf = surf["x"][order], surf["cf"][order]
    if CASES[case][3] == "transition_plate":
        wall = (x > 1e-6) & (cf > 0)
        x, cf = x[wall], cf[wall]
        # Onset is the FIRST local minimum of cf, not the smallest value on the plate. Downstream
        # of the turbulent peak cf decays monotonically, so a global argmin over a fixed window
        # lands on the window edge every time -- on 16 Sept it returned x = 9.915 on a plate of
        # length 20 (the 90 % point) and called it an onset at Re_x = 2.6e8. Requiring a real
        # rise after the minimum keeps noise from passing for transition.
        rex, i = reynolds_per_length(lines), None
        for k in range(1, cf.size - 1):
            if cf[k] <= cf[k - 1] and cf[k] <= cf[k + 1] and cf[k:].max() >= 1.25 * cf[k]:
                i = k
                break
        entry["reference"] = "experiment to be added before this is judged"
        if i is None:
            entry.update({"cf_minimum_x": None, "transition_onset_Re_x": None,
                          "note": "no cf minimum with a 25 % rise after it: no transition on this plate"})
        else:
            entry.update({"cf_minimum_x": float(x[i]), "cf_minimum": float(cf[i]),
                          "transition_onset_Re_x": float(rex * x[i]) if rex else None})
    else:
        # E387 at Re 200k is a separation-bubble flow: McGhee's oil flow puts the bubble between
        # x/c 0.43 and 0.67 at alpha 2. Grade the bubble, not only the forces -- drag can land
        # near the measurement with the bubble misplaced, or with no bubble at all.
        chord = float(x.max() - x.min())
        upper = surf["y"][order] > 0
        xs, cs = (x[upper] - x.min()) / chord, cf[upper]
        reversed_ = xs[cs < 0]
        got = [float(reversed_.min()), float(reversed_.max())] if reversed_.size else None
        entry["upper_reversed_flow_x_over_c"] = got
        if isinstance(entry.get("reference"), dict) and "x_laminar_separation" in entry["reference"]:
            measured = [entry["reference"]["x_laminar_separation"],
                        entry["reference"]["x_turbulent_reattachment"]]
            entry["bubble"] = {
                "measured_x_over_c": measured,
                "computed_x_over_c": got,
                "verdict": "no bubble: the only reversed flow is at the trailing edge"
                           if got is None or got[0] > 0.95 else
                           f"separation {got[0] - measured[0]:+.3f}c, "
                           f"reattachment {got[1] - measured[1]:+.3f}c"}
        elif not isinstance(entry.get("reference"), dict):
            entry["reference"] = "no measurement on file for this case at this angle"


def cmd_compare(args) -> int:
    report = json.loads(REPORT.read_text()) if REPORT.exists() else {"schema": "aeris.s8.su2_validation.v1", "cases": {}}
    for case in (CASES if args.all else [args.case]):
        directory = RUNS / case
        log = (directory / "run.log").read_text(errors="ignore") if (directory / "run.log").exists() else ""
        # SU2 prints "Exit Success" even when a signal stopped it: the roe_wls variant was
        # killed at iteration 727 on 15 Sept and its log still said Exit Success, so the queue
        # that tested for that string skipped the rerun. Ask for the real thing instead.
        entry = {"kind": CASES[case][3],
                 "finished": "All convergence criteria satisfied" in log and "Interrupt signal" not in log,
                 "interrupted": "Interrupt signal" in log,
                 "time_limit_hit": "TIME LIMIT" in log, "memory_guard_hit": "MEMORY GUARD" in log,
                 "convergence": history(directory)}
        kind = CASES[case][3]
        try:
            if kind.startswith("flatplate"):
                judge_flatplate(case, directory, entry)
            elif kind == "naca0012":
                judge_naca(directory, entry)
            else:
                judge_transition(case, directory, entry)
        except Exception as exc:  # noqa: BLE001 - recorded, never silently passed
            entry["compare_error"] = repr(exc)
        report["cases"][case] = entry
        short = {k: entry.get(k) for k in ("finished", "interrupted", "cf_error_pct", "cd_error_pct", "error_pct",
                                          "transition_onset_Re_x", "upper_reversed_flow_x_over_c",
                                          "error_vs_experiment", "within_measurement_uncertainty",
                                          "note", "compare_error") if entry.get(k) is not None}
        # the queues end on `compare --all | tail`, so a verdict missing from this line is a
        # verdict nobody reads
        if isinstance(entry.get("bubble"), dict):
            short["bubble"] = entry["bubble"]["verdict"]
        print(f"  {case}: {json.dumps(short, default=lambda v: round(v, 3))}")
    REPORT.write_text(json.dumps(report, indent=2, default=float) + "\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("config")
    c.add_argument("--case", required=True, choices=list(CASES))
    c.add_argument("--restart", action="store_true",
                   help="continue from this case's restart file instead of starting again")
    k = sub.add_parser("compare")
    group = k.add_mutually_exclusive_group(required=True)
    group.add_argument("--case", choices=list(CASES))
    group.add_argument("--all", action="store_true")
    args = ap.parse_args()
    return {"config": cmd_config, "compare": cmd_compare}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
