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
import hashlib
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
        # Continue rather than start again. Two things this used to get wrong.
        #
        # It read `restart.dat` unconditionally. After one continuation the newest
        # solution is `restart_cont.dat`, so a SECOND continuation would have
        # silently rewound the case to where the first one started and thrown
        # away everything it computed. fp_comp_545 and naca0012_inc_897 both have
        # a restart_cont.dat today, so this was live.
        #
        # And it wrote `history_cont` every time, so each leg overwrote the last.
        # Legs are numbered now, and nothing is ever written over a history that
        # already exists -- see history(), which reassembles them.
        existing = sorted((RUNS / args.case).glob("restart*.dat"),
                          key=lambda q: q.stat().st_mtime)
        newest = existing[-1].name if existing else "restart.dat"
        generation = len(list((RUNS / args.case).glob("history_cont*.csv"))) + 1
        changes.update({"RESTART_SOL": "YES", "SOLUTION_FILENAME": newest,
                        "RESTART_FILENAME": f"restart_cont{generation}.dat",
                        "CONV_FILENAME": f"history_cont{generation}",
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

#: A continuation writes its own history file, so a case's convergence story is
#: spread across several. `cmd_config --restart` sets CONV_FILENAME to
#: `history_cont`, and this reader used to open `history.csv` alone.
#:
#: The consequence, reproduced synthetically by an external review and confirmed
#: here: `fp_comp_545`, `fp_inc_545` and `naca0012_inc_897` each have a
#: `history_cont.csv` with thousands of iterations in it, and every verdict
#: those cases received was computed from the FIRST leg only -- the one that was
#: killed at its time limit. The forces came from `forces_breakdown.dat`, which
#: the continuation DOES overwrite, so the reports combined up-to-date forces
#: with a stale convergence history and no field said so.
def history_files(directory: Path) -> list[Path]:
    """history.csv then every numbered continuation, oldest first."""
    out = [directory / "history.csv", directory / "history_cont.csv"]
    out += sorted(directory.glob("history_cont[0-9]*.csv"),
                  key=lambda q: int("".join(c for c in q.stem if c.isdigit()) or 0))
    seen, ordered = set(), []
    for q in out:
        if q.name not in seen:
            seen.add(q.name)
            ordered.append(q)
    return ordered


def history(directory: Path) -> dict:
    """Every DISTINCT leg of the run, in order, as one convergence history.

    Deduplicated by content, because queue23 copied each continuation over the
    original at the end of its group. `history.csv` and `history_cont.csv` are
    byte-identical in `fp_comp_545`, `fp_inc_545` and `naca0012_inc_897`, and
    concatenating them blindly counts the same iterations twice.

    That copy also means the FIRST leg's history no longer exists for those
    three cases: both files start at Inner_Iter 0 and end at the continuation's
    last iteration, so the orders-dropped figure covers the continuation alone
    and the drop achieved before the time limit is unrecoverable. It is reported
    as `first_leg_overwritten` rather than quietly presented as the whole run.
    A continuation must never be copied over the history it continues.
    """
    legs, head, seen_digests = [], None, {}
    overwritten = False
    for path in history_files(directory):
        name = path.name
        if not path.exists():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen_digests:
            overwritten = True
            continue
        seen_digests[digest] = name
        rows = list(csv.reader(open(path)))
        if not rows:
            continue
        this_head = [c.strip().strip('"') for c in rows[0]]
        data = [r for r in rows[1:] if len(r) == len(this_head)]
        if not data:
            continue
        if head is None:
            head = this_head
        elif this_head != head:
            legs.append((name, this_head, data, True))
            continue
        legs.append((name, this_head, data, False))
    if not legs:
        return {}
    mismatched = [name for name, _, _, bad in legs if bad]
    usable = [(name, h, d) for name, h, d, bad in legs if not bad]
    if not usable:
        return {}
    first_data, last_data = usable[0][2], usable[-1][2]
    rms = {h: (float(first_data[0][i]), float(last_data[-1][i]))
           for i, h in enumerate(head) if h.startswith("rms[")}
    total = sum(len(d) for _, _, d in usable)
    out = {"iterations": (int(float(last_data[-1][head.index("Inner_Iter")]))
                          if "Inner_Iter" in head else total),
           "iterations_all_legs": total,
           "legs": [{"file": name, "rows": len(d)} for name, _, d in usable],
           "rms_first_last": rms,
           "orders_dropped": {h: round(a - b, 2) for h, (a, b) in rms.items()}}
    if mismatched:
        out["legs_skipped_column_mismatch"] = mismatched
    if overwritten:
        out["first_leg_overwritten"] = (
            "a continuation file is byte-identical to history.csv, so the queue "
            "copied it over the original. The drop before the restart is gone; "
            "orders_dropped covers the continuation only.")
    return out


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


def _contiguous(x: np.ndarray, mask: np.ndarray) -> list[list[float]]:
    """Start and end of every run of True in `mask`, as x values.

    Surface points arrive sorted by x, so a run of consecutive True entries is a
    connected region of the surface. Separate regions stay separate.
    """
    out, start = [], None
    for i, flag in enumerate(mask):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            out.append([float(x[start]), float(x[i - 1])])
            start = None
    if start is not None:
        out.append([float(x[start]), float(x[-1])])
    return out


def _cm_comparison(computed: float, reference: float) -> dict:
    """Signed AND magnitude, with the sign convention stated, not assumed."""
    same_sign = (computed >= 0) == (reference >= 0)
    return {
        "computed_CMz": float(computed),
        "reference_CM_nose_down_negative": float(reference),
        "signs_agree": bool(same_sign),
        "signed_error_pct": 100.0 * (computed - reference) / abs(reference),
        "magnitude_error_pct": 100.0 * (abs(computed) - abs(reference)) / abs(reference),
        "note": ("both conventions agree on the sign" if same_sign else
                 "SIGNS DISAGREE: the computed moment and the measurement point "
                 "opposite ways. Resolve the axis convention before reading the "
                 "magnitude error, which is blind to this."),
    }


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
                # Comparing |CMz| to |CM_ref| hides a sign error completely: an
                # external review ran this grader with +0.0794 and with -0.0794
                # and got zero magnitude error from BOTH. For a BWB, where the
                # pitching moment decides whether the aircraft can be trimmed at
                # all, that is not a detail. Both the signed and the magnitude
                # comparison are recorded, and the convention is asserted rather
                # than assumed -- if the signs disagree, the field says so.
                **({"CM": _cm_comparison(f["CMz"], ref["CM_nose_down_negative"])}
                   if "CMz" in f else {})}
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
        # CONTIGUOUS intervals, not the extremes of every reversed point. Taking
        # min and max over all of them merges a laminar bubble at 0.2-0.3 with a
        # trailing-edge separation at 0.7-0.8 into one fictitious region running
        # 0.2-0.8. The review demonstrated exactly that with a synthetic field;
        # here it would have reported a bubble four times its real length, and
        # reported one at all on a flow that has only trailing-edge separation.
        regions = _contiguous(xs, cs < 0)
        entry["upper_reversed_flow_regions_x_over_c"] = regions
        # the bubble is the reversed region that is NOT against the trailing edge
        bubbles = [r for r in regions if r[1] <= 0.95]
        got = max(bubbles, key=lambda r: r[1] - r[0]) if bubbles else None
        entry["upper_reversed_flow_x_over_c"] = got
        if isinstance(entry.get("reference"), dict) and "x_laminar_separation" in entry["reference"]:
            measured = [entry["reference"]["x_laminar_separation"],
                        entry["reference"]["x_turbulent_reattachment"]]
            entry["bubble"] = {
                "measured_x_over_c": measured,
                "computed_x_over_c": got,
                "all_reversed_regions": regions,
                "verdict": ("no bubble: the only reversed flow is at the trailing edge"
                            if got is None else
                            f"separation {got[0] - measured[0]:+.3f}c, "
                            f"reattachment {got[1] - measured[1]:+.3f}c")}
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
