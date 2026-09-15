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
    "OUTPUT_FILES": "( RESTART, SURFACE_CSV )",
    "VOLUME_OUTPUT": "( COORDINATES, SOLUTION, PRIMITIVE )",
    "HISTORY_OUTPUT": "( ITER, RMS_RES, AERO_COEFF, CFL_NUMBER )",
    "WRT_FORCES_BREAKDOWN": "YES", "BREAKDOWN_FILENAME": "forces_breakdown.dat",
    "CONV_FILENAME": "history", "SURFACE_FILENAME": "surface_flow",
    "RESTART_FILENAME": "restart.dat", "OUTPUT_WRT_FREQ": "1000",
}
X_CF = 0.970084071            # TMR's skin-friction station
NACA_TMR = {"CL": 1.09094, "CD": 0.0122728, "CDp": 0.006067, "CDv": 0.0062059}
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
    return {"CL": cl[0], "CD": cd[0], "CDp": cd[1], "CDv": cd[2]}


def surface(directory: Path) -> dict | None:
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
    err = {k: 100 * (f[k] - ref[k]) / ref[k] for k in f}
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


def judge_transition(case: str, directory: Path, entry: dict) -> None:
    surf, f = surface(directory), forces(directory)
    lines = (directory / "case.cfg").read_text().splitlines()
    if f:
        entry["forces"] = f
    if surf is None or surf["cf"] is None:
        return
    order = np.argsort(surf["x"])
    x, cf = surf["x"][order], surf["cf"][order]
    if CASES[case][3] == "transition_plate":
        wall = x > 1e-6
        x, cf = x[wall], cf[wall]
        i = int(np.argmin(cf[: max(3, int(0.9 * cf.size))]))   # laminar minimum before the rise
        rex = reynolds_per_length(lines)
        entry.update({"cf_minimum_x": float(x[i]), "cf_minimum": float(cf[i]),
                      "transition_onset_Re_x": float(rex * x[i]) if rex else None,
                      "reference": "experiment to be added before this is judged"})
    else:
        chord = float(np.ptp(x))
        upper = surf["y"][order] > 0
        xs, cs = x[upper], cf[upper]
        reversed_ = xs[cs < 0]
        entry.update({"upper_reversed_flow_x_over_c": [float(reversed_.min() / chord), float(reversed_.max() / chord)]
                      if reversed_.size else None,
                      "reference": "NASA LTPT / UIUC data to be added before this is judged"})


def cmd_compare(args) -> int:
    report = json.loads(REPORT.read_text()) if REPORT.exists() else {"schema": "aeris.s8.su2_validation.v1", "cases": {}}
    for case in (CASES if args.all else [args.case]):
        directory = RUNS / case
        log = (directory / "run.log").read_text(errors="ignore") if (directory / "run.log").exists() else ""
        entry = {"kind": CASES[case][3], "exit_success": "Exit Success" in log,
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
        short = {k: entry.get(k) for k in ("exit_success", "cf_error_pct", "cd_error_pct", "error_pct",
                                          "transition_onset_Re_x", "upper_reversed_flow_x_over_c",
                                          "compare_error") if entry.get(k) is not None}
        print(f"  {case}: {json.dumps(short, default=lambda v: round(v, 3))}")
    REPORT.write_text(json.dumps(report, indent=2, default=float) + "\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("config")
    c.add_argument("--case", required=True, choices=list(CASES))
    k = sub.add_parser("compare")
    group = k.add_mutually_exclusive_group(required=True)
    group.add_argument("--case", choices=list(CASES))
    group.add_argument("--all", action="store_true")
    args = ap.parse_args()
    return {"config": cmd_config, "compare": cmd_compare}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
