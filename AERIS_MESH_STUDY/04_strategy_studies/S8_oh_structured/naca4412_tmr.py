"""NACA 4412 near stall: SA drag and separation at AERIS's own Reynolds number.

VV_ACCEPTANCE_2026-09-13.md checked every validation case against the regime
AERIS flies in, and this is the one that matches it. NASA TMR case 2DN44, from
Coles & Wadcock (1979): M 0.09, Re 1.52e6 on the chord, alpha 13.87 deg, with
the upper-surface boundary layer separating ahead of the trailing edge. AERIS
flies Re 1.53e6 on 0.9 m at M 0.084. The NACA 0012 case verified drag in
attached flow at four times that Reynolds number; this asks the harder question
at the right one.

Three references, strongest first:
  * CFL3D and FUN3D, both SA, on TMR's 897x257 grid. A CODE band, not a
    converged answer: their drag differs by 3 %.
  * Coles & Wadcock's surface cp, and u along the six lines through the
    separated region that CFD has traditionally been compared on.
  * where the upper surface separates, from the sign of the wall shear.
TMR calls the case weak as validation -- a small tunnel, and tripped boundary
layers against fully turbulent CFD -- so the experiment is read for trends and
the SA band decides.

The grid family is ours, built as naca0012_tmr.py builds its own: pyHyp O-grids
around TMR's exact geometry (0.1036 x^4, which closes the trailing edge), 100
chords as TMR's grids, y+ below 1 on every level.

    mach python naca4412_tmr.py grid
    mpirun -np 6 mach python naca4412_tmr.py solve --grid .../o512.cgns --out .../runs/o512
    python naca4412_tmr.py compare
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from naca0012_tmr import richardson, write_surface

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = REPO / "AERIS_MESH_STUDY/artifacts/tmr_naca4412"
EXTERNAL = REPO / "AERIS_MESH_STUDY/05_s6_cfd_qualification/external/naca4412"
REPORT = REPO / "AERIS_MESH_STUDY/05_s6_cfd_qualification/reports/s8_naca4412_tmr.json"

#: n4412_cfl3d_typical_sa.inp: XMACH 0.09, ALPHA 13.87, REUE 1.52 million, TINF 536 R
CASE = {"mach": 0.09, "reynolds": 1.52e6, "reynolds_length": 1.0,
        "temperature_K": 536.0 / 1.8, "alpha_deg": 13.87}
#: naca4412sep_val_sa.html: 897x257 grid, coefficients on freestream conditions
REFERENCE = {"CFL3D": {"CL": 1.7210, "CD": 0.02861, "CDp": 0.02156, "CDv": 0.007042},
             "FUN3D": {"CL": 1.7170, "CD": 0.02947, "CDp": 0.02246, "CDv": 0.007006}}
#: SA freestream chi = 3 ("tur10 3." in the CFL3D deck, TMR note 5): nu_t/nu = 3 fv1(3)
EDDY_VIS_INF_RATIO = 0.21
#: the experiment normalises u by a velocity about one chord below and behind the
#: airfoil, which TMR puts at 0.93 of freestream; CFL3D's profiles are divided by it
U_REF_OVER_U_INF = 0.93
#: cells around the airfoil; 3/8 as many off the wall, so the 100-chord march keeps
#: its growth ratio near 1.17 on the coarsest level; first cell halves per doubling
LEVELS = {"o256": 256, "o512": 512, "o1024": 1024}
S0_AT_1024 = 1.0e-6
FARFIELD_CHORDS = 100.0
LIFT_INDEX = 2               # airfoil in x-y, span along z
#: judged on the campaign's stopping rule
CAMPAIGN_L2 = 1.0e-6


def camber(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    m, p = 0.04, 0.4
    fore = x < p
    yc = np.where(fore, m / p ** 2 * (2 * p * x - x ** 2),
                  m / (1 - p) ** 2 * ((1 - 2 * p) + 2 * p * x - x ** 2))
    slope = np.where(fore, 2 * m / p ** 2 * (p - x), 2 * m / (1 - p) ** 2 * (p - x))
    return yc, slope


def surface_loop(cells: int) -> np.ndarray:
    """TMR's NACA 4412, trailing edge -> upper -> leading edge -> lower -> trailing edge.

    Thickness is laid normal to the camber line, as the NACA definition asks.
    Same direction and cosine clustering as naca0012_tmr.surface_loop, so pyHyp
    marches into the flow.
    """
    x = 0.5 * (1.0 - np.cos(np.pi * np.linspace(0.0, 1.0, cells // 2 + 1)))
    yt = 0.6 * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x ** 2
                + 0.2843 * x ** 3 - 0.1036 * x ** 4)
    yc, slope = camber(x)
    theta = np.arctan(slope)
    upper = np.column_stack([x - yt * np.sin(theta), yc + yt * np.cos(theta)])
    lower = np.column_stack([x + yt * np.sin(theta), yc - yt * np.cos(theta)])
    return np.vstack([upper[::-1], lower[1:]])


def tmr_wall() -> np.ndarray:
    """The airfoil exactly as TMR's own 225x65 C-grid carries it, wake cut removed."""
    tokens = (EXTERNAL / "n4412_225-65.p2dfmt").read_text().split()
    ni, nj = int(tokens[1]), int(tokens[2])
    values = np.array(tokens[3:], dtype=float)
    x = values[:ni * nj].reshape(nj, ni)[0]
    y = values[ni * nj:2 * ni * nj].reshape(nj, ni)[0]
    wall = np.column_stack([x, y])
    shared = sum(bool(np.allclose(wall[i], wall[ni - 1 - i], atol=1e-9)) for i in range(ni // 2))
    return wall[shared - 1:ni - shared + 1]


def distance_to_polyline(points: np.ndarray, line: np.ndarray) -> np.ndarray:
    a, ab = line[:-1], np.diff(line, axis=0)
    out = np.empty(len(points))
    for i, q in enumerate(points):
        t = np.clip(np.einsum("ij,ij->i", q - a, ab) / np.einsum("ij,ij->i", ab, ab), 0.0, 1.0)
        out[i] = np.min(np.linalg.norm(a + t[:, None] * ab - q, axis=1))
    return out


def cmd_grid(args) -> int:
    # the geometry is checked BEFORE anything is built on it
    deviation = float(distance_to_polyline(tmr_wall(), surface_loop(8192)).max())
    print(f"  largest distance from TMR's own wall points: {deviation:.2e} chord")
    if deviation > 1.0e-4:
        raise SystemExit("the section does not match TMR's geometry; not building")

    from pyhyp import pyHyp

    OUT.mkdir(parents=True, exist_ok=True)
    report_path = OUT / "grid_report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    for name in args.levels:
        cells = LEVELS[name]
        surface = OUT / f"{name}_surface.xyz"
        write_surface(surface, surface_loop(cells))
        s0 = S0_AT_1024 * 1024 / cells
        normal = 3 * cells // 8
        hyp = pyHyp(options={
            "inputFile": str(surface), "fileType": "PLOT3D",
            "unattachedEdgesAreSymmetry": False, "outerFaceBC": "farfield",
            "autoConnect": True,
            "BC": {1: {"jLow": "zSymm", "jHigh": "zSymm"}},
            "families": "wall",
            "N": normal + 1, "s0": s0, "marchDist": FARFIELD_CHORDS,
            "ps0": -1.0, "pGridRatio": -1.0, "cMax": 3.0,
            "epsE": 1.0, "epsI": 2.0, "theta": 3.0,
            "volCoef": 0.25, "volBlend": 0.0001, "volSmoothIter": 100,
        })
        hyp.run()
        cgns = OUT / f"{name}.cgns"
        hyp.writeCGNS(str(cgns))
        report[name] = {"cgns": str(cgns), "cells": cells * normal, "cells_around": cells,
                        "cells_normal": normal, "first_cell": s0,
                        "farfield_chords": FARFIELD_CHORDS,
                        "max_distance_from_tmr_wall_chords": deviation}
        print(f"  {name}: {report[name]['cells']:,} cells, s0 {s0:.2e}")
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    return 0


def cmd_solve(args) -> int:
    """One point with the CAMPAIGN's option set; only the case differs."""
    from adflow import ADFLOW
    from baseclasses import AeroProblem

    args.out.mkdir(parents=True, exist_ok=True)
    overrides: dict = {"eddyVisInfRatio": args.eddy_vis_inf_ratio}
    if args.no_nk:
        overrides["useNKSolver"] = False
    # nonlinear-solver settings only: they change the path, never the solution
    for item in args.set:
        key, _, value = item.partition("=")
        try:
            overrides[key] = json.loads(value)
        except json.JSONDecodeError:
            overrides[key] = value
    options = {
        "gridFile": str(args.grid), "outputDirectory": str(args.out),
        "equationType": "RANS", "turbulenceModel": "SA",
        "liftIndex": LIFT_INDEX,
        "MGCycle": "sg",
        "useANKSolver": True, "ANKSwitchTol": 1.0,
        "useNKSolver": True, "NKSwitchTol": 1.0e-6,
        "ANKSubspaceSize": 10, "NKSubspaceSize": 20,
        "ANKPCILUFill": 1, "NKPCILUFill": 1,
        "L2Convergence": args.l2, "nCycles": args.n_cycles,
        "timeLimit": args.time_limit,
        "storeConvHist": True,
        # the volume is needed: the experiment's velocity profiles are off the wall
        "writeVolumeSolution": True, "writeSurfaceSolution": True,
        "monitorVariables": ["resrho", "resturb", "cl", "cd", "cdp", "cdv"],
        "surfaceVariables": ["cp", "cf", "cfx", "yplus"],
        "volumeVariables": ["mach", "eddyratio"],
        **overrides,
    }
    solver = ADFLOW(options=options)
    problem = AeroProblem(
        name="n4412", alpha=args.alpha, beta=0.0, mach=args.mach,
        reynolds=CASE["reynolds"], reynoldsLength=CASE["reynolds_length"],
        T=CASE["temperature_K"], areaRef=1.0, chordRef=1.0,
        xRef=0.25, yRef=0.0, zRef=0.0,
        evalFuncs=["cl", "cd", "cdp", "cdv", "cmz"])
    solver.setAeroProblem(problem)

    a = np.radians(args.alpha)
    physics = solver.adflow.inputphysics
    got = np.array(physics.veldirfreestream, dtype=float).ravel()[:3]
    if int(physics.liftindex) != LIFT_INDEX or float(np.linalg.norm(got - [np.cos(a), np.sin(a), 0.0])) > 1.0e-9:
        raise SystemExit(f"freestream direction {got} is not alpha {args.alpha} in the x-y plane")

    solver(problem)
    funcs: dict = {}
    solver.evalFunctions(problem, funcs)
    try:
        iteration = solver.adflow.iteration
        residual = float(iteration.totalrfinal / iteration.totalr0)
    except Exception:  # noqa: BLE001 - never assumed converged
        residual = None
    f = {k.split("_")[-1]: float(v) for k, v in funcs.items()}
    result = {"case": {**CASE, "mach": args.mach, "alpha_deg": args.alpha},
              "grid": str(args.grid), "relative_residual": residual, "l2_target": args.l2,
              "converged": residual is not None and residual <= args.l2,
              "solver_overrides": overrides, "functions": funcs,
              "u_inf_m_s": float(getattr(problem, "V", float("nan"))),
              # nose-up positive about the quarter chord, as TMR reports it
              "coefficients": {"CL": f["cl"], "CD": f["cd"], "CDp": f["cdp"],
                               "CDv": f["cdv"], "CM": -f["cmz"]}}
    (args.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["coefficients"], indent=2))
    return 0


# ----------------------------------------------------------------------------- compare

def load(run: Path) -> dict | None:
    path = run / "result.json"
    if not path.exists():
        return None
    result = json.loads(path.read_text())
    res = result.get("relative_residual")
    return result if res is not None and res <= CAMPAIGN_L2 else None


def _cells(c: np.ndarray) -> np.ndarray:
    """Vertex array (n, m) -> cell centres (n-1, m-1)."""
    return 0.25 * (c[:-1, :-1] + c[:-1, 1:] + c[1:, :-1] + c[1:, 1:])


def wall_curve(run: Path) -> dict:
    """Wall cp, signed x-friction and y+ on the airfoil, split upper and lower."""
    import cgns_read
    files = sorted(run.glob("*surf*.cgns"))
    if not files:
        raise SystemExit(f"no surface solution in {run}")
    for name, node in cgns_read.surface_zones(files[0]):
        if "wall" not in name.lower():
            continue
        g, s = node["GridCoordinates"], node["Flow solution"]
        x, y = (_cells(np.array(g[f"Coordinate{a}"][" data"])) for a in "XY")
        out = {"x": x.ravel(), "y": y.ravel(), "fields": sorted(s)}
        for key, label in (("cp", "CoefPressure"), ("cfx", "SkinFrictionX"), ("yplus", "YPlus")):
            if label in s:
                a = np.array(s[label][" data"])
                out[key] = (a if a.shape == x.shape else a[1:-1, 1:-1]).ravel()
        le = int(np.argmin(out["x"]))
        first, second = np.arange(le + 1), np.arange(le, out["x"].size)
        upper = first if out["y"][first].mean() > out["y"][second].mean() else second
        out["upper"] = np.zeros(out["x"].size, dtype=bool)
        out["upper"][upper] = True
        return out
    raise SystemExit(f"{files[0]} has no wall zone")


def velocity_field(run: Path):
    """u / U_inf as an interpolant over cell centres of the volume solution."""
    import cgns_read
    from scipy.interpolate import LinearNDInterpolator
    files = sorted(run.glob("*vol*.cgns"))
    if not files:
        raise SystemExit(f"no volume solution in {run}")
    xs, ys, us, speed = [], [], [], []
    with cgns_read.CGNSFile(files[0]) as handle:
        for zone in handle.zones():
            fields = {f["name"]: f for f in handle.fields(zone["base"], zone["zone"])}
            if "VelocityX" not in fields:
                raise SystemExit(f"no VelocityX in {files[0]}; fields: {sorted(fields)}")
            dims = [d for d in zone["vertex_dims"] if d > 0]
            xyz = handle.read_coords(zone["base"], zone["zone"], dims)
            centre = xyz[:-1, :-1, :-1] + xyz[1:, :-1, :-1] + xyz[:-1, 1:, :-1] + xyz[1:, 1:, :-1] \
                + xyz[:-1, :-1, 1:] + xyz[1:, :-1, 1:] + xyz[:-1, 1:, 1:] + xyz[1:, 1:, 1:]
            centre = centre / 8.0
            vel = []
            for label in ("VelocityX", "VelocityY"):
                a = cgns_read.read_field_auto(handle, zone, fields[label])
                if a.shape != centre.shape[:3]:
                    a = a[1:-1, 1:-1, 1:-1]
                vel.append(a)
            xs.append(centre[..., 0].ravel()); ys.append(centre[..., 1].ravel())
            us.append(vel[0].ravel()); speed.append(np.hypot(vel[0], vel[1]).ravel())
    x, y, u, sp = (np.concatenate(v) for v in (xs, ys, us, speed))
    # freestream speed from the cell farthest out: at 100 chords the airfoil's own
    # circulation adds about 0.1 %, and the result is right in whatever units ADflow wrote
    u_inf = float(sp[int(np.argmax(np.hypot(x - 0.5, y)))])
    near = (x > 0.5) & (x < 1.2) & (y > -0.2) & (y < 0.4)
    return LinearNDInterpolator(np.column_stack([x[near], y[near]]), u[near] / u_inf), u_inf


def read_zones(path: Path) -> dict:
    """Tecplot-style ZONE blocks -> {title: array}."""
    zones, title, rows = {}, None, []
    for line in path.read_text().splitlines():
        s = line.strip()
        if s.upper().startswith("ZONE"):
            if title is not None:
                zones[title] = np.array(rows)
            title, rows = s.split("=", 1)[1].strip().strip('"'), []
        elif s and s[0] in "-.0123456789" and title is not None:
            rows.append([float(v) for v in s.split()])
    if title is not None:
        zones[title] = np.array(rows)
    return zones


def columns(path: Path) -> np.ndarray:
    return np.array([[float(v) for v in l.split()] for l in path.read_text().splitlines()
                     if l.strip() and l.strip()[0] in "-.0123456789"])


def separation(x: np.ndarray, cf: np.ndarray) -> float:
    """Upper-surface x/c where the wall shear first reverses aft of 30 % chord."""
    o = np.argsort(x)
    x, cf = x[o], cf[o]
    reversed_ = np.where((x > 0.3) & (cf < 0))[0]
    if not reversed_.size or reversed_[0] == 0:
        return float("nan")
    i = reversed_[0]
    return float(x[i - 1] + (x[i] - x[i - 1]) * cf[i - 1] / (cf[i - 1] - cf[i]))


def rms_against(xc: np.ndarray, vc: np.ndarray, xr: np.ndarray, vr: np.ndarray) -> float:
    o = np.argsort(xc)
    inside = (xr >= xc.min()) & (xr <= xc.max())
    return float(np.sqrt(np.mean((np.interp(xr[inside], xc[o], vc[o]) - vr[inside]) ** 2)))


def cmd_compare(args) -> int:
    runs = {name: OUT / "runs" / name for name in LEVELS}
    family = {n: r for n, r in ((n, load(p)) for n, p in runs.items()) if r}
    names = list(family)
    report: dict = {"schema": "aeris.s8.naca4412_tmr.v1", "case": CASE,
                    "reference_sa_897": REFERENCE,
                    "unconverged_or_missing": [n for n in LEVELS if n not in family],
                    "levels": {n: family[n]["coefficients"] for n in names}}
    keys = ("CL", "CD", "CDp", "CDv")
    print(f"{'grid':>8}" + "".join(f"{k:>10}" for k in keys))
    for n in names:
        print(f"{n:>8}" + "".join(f"{family[n]['coefficients'][k]:>10.5f}" for k in keys))
    for code, ref in REFERENCE.items():
        print(f"{code:>8}" + "".join(f"{ref[k]:>10.5f}" for k in keys))
    if not names:
        REPORT.write_text(json.dumps(report, indent=2) + "\n")
        print("  no converged run yet")
        return 1

    forces = {}
    finest = names[-1]
    for k in keys:
        lo, hi = sorted(REFERENCE[c][k] for c in REFERENCE)
        value = family[finest]["coefficients"][k]
        entry = {"finest_grid": finest, "finest_value": value, "sa_band": [lo, hi],
                 "finest_inside_band": bool(lo <= value <= hi),
                 "finest_vs_band_mid_pct": 100 * (value - (lo + hi) / 2) / ((lo + hi) / 2)}
        if len(names) == 3:
            rich = richardson(*(family[n]["coefficients"][k] for n in names[::-1]))
            entry["richardson"] = rich
            if rich.get("monotone"):
                entry["extrapolated_inside_band"] = bool(lo <= rich["extrapolated"] <= hi)
                entry["extrapolated_vs_band_mid_pct"] = (
                    100 * (rich["extrapolated"] - (lo + hi) / 2) / ((lo + hi) / 2))
        forces[k] = entry
    report["forces"] = forces

    run = runs[finest]
    wall = wall_curve(run)
    up = wall["upper"]
    exp_cp = columns(EXTERNAL / "naca4412.cp.expt.dat")
    exp_upper = exp_cp[:, 1] > camber(exp_cp[:, 0])[0]
    cfl_cp = columns(EXTERNAL / "n4412_cfl3d_cp_sa.dat")
    le = int(np.argmin(cfl_cp[:, 0]))
    halves = (cfl_cp[:le + 1], cfl_cp[le:])
    cfl_upper, cfl_lower = sorted(halves, key=lambda h: h[:, 1].mean())
    cfl_cf = columns(EXTERNAL / "n4412_cfl3d_cfupper_sa.dat")
    surface = {"fields_in_file": wall["fields"],
               "yplus_max": float(wall["yplus"].max()) if "yplus" in wall else None}
    if "cp" in wall:
        surface["cp_rms_vs_experiment"] = {
            "upper": rms_against(wall["x"][up], wall["cp"][up], exp_cp[exp_upper, 0], exp_cp[exp_upper, 2]),
            "lower": rms_against(wall["x"][~up], wall["cp"][~up], exp_cp[~exp_upper, 0], exp_cp[~exp_upper, 2])}
        surface["cp_rms_vs_cfl3d"] = {
            "upper": rms_against(wall["x"][up], wall["cp"][up], cfl_upper[:, 0], cfl_upper[:, 1]),
            "lower": rms_against(wall["x"][~up], wall["cp"][~up], cfl_lower[:, 0], cfl_lower[:, 1])}
        surface["cp_min"] = {"cfd": float(wall["cp"].min()), "experiment": float(exp_cp[:, 2].min()),
                             "cfl3d": float(cfl_cp[:, 1].min())}
    if "cfx" in wall:
        surface["separation_x_over_c"] = {"cfd": separation(wall["x"][up], wall["cfx"][up]),
                                          "cfl3d": separation(cfl_cf[:, 0], cfl_cf[:, 1])}
        surface["cf_upper_rms_vs_cfl3d"] = rms_against(wall["x"][up], wall["cfx"][up],
                                                       cfl_cf[:, 0], cfl_cf[:, 1])
    report["surface"] = surface

    field, u_inf = velocity_field(run)
    exp_lines = read_zones(EXTERNAL / "exp.profiles.new.dat")
    cfl_lines = read_zones(EXTERNAL / "n4412_cfl3d_vel_sa.dat")
    profiles, first_reversed = {}, None
    for title, data in exp_lines.items():
        off = data[1:]                                  # the first row is AT the wall
        u_cfd = field(off[:, 0], off[:, 1]) / U_REF_OVER_U_INF
        ok = np.isfinite(u_cfd)
        entry = {"points": int(ok.sum()),
                 "rms_u_vs_experiment": float(np.sqrt(np.mean((u_cfd[ok] - off[ok, 2]) ** 2))),
                 "experiment_reversed_at_wall": bool(off[0, 2] < 0)}
        if title in cfl_lines:
            c = cfl_lines[title]
            u_cfl = np.interp(off[:, 1], c[:, 1], c[:, 2])
            entry["rms_u_vs_cfl3d"] = float(np.sqrt(np.mean((u_cfd[ok] - u_cfl[ok]) ** 2)))
            entry["rms_cfl3d_vs_experiment"] = float(np.sqrt(np.mean((u_cfl - off[:, 2]) ** 2)))
        if entry["experiment_reversed_at_wall"] and first_reversed is None:
            first_reversed = title
        profiles[title] = entry
    report["profiles"] = {"u_inf_from_far_field": u_inf, "u_inf_from_problem": family[finest].get("u_inf_m_s"),
                          "stations": profiles,
                          "experiment_first_station_reversed_near_wall": first_reversed}
    REPORT.write_text(json.dumps(report, indent=2) + "\n")

    for k, e in forces.items():
        line = f"  {k:>4}: {finest} {e['finest_vs_band_mid_pct']:+.2f}% of the SA band's middle"
        if "extrapolated_vs_band_mid_pct" in e:
            line += f", extrapolated {e['extrapolated_vs_band_mid_pct']:+.2f}%"
        print(line + ("  (inside)" if e["finest_inside_band"] else ""))
    for k, v in surface.items():
        print(f"  {k}: {v}")
    for title, e in profiles.items():
        print(f"  u at {title}: rms vs experiment {e['rms_u_vs_experiment']:.3f}"
              + (f", vs CFL3D {e['rms_u_vs_cfl3d']:.3f} (CFL3D vs experiment {e['rms_cfl3d_vs_experiment']:.3f})"
                 if "rms_u_vs_cfl3d" in e else ""))
    print(f"  wrote {REPORT}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grid")
    g.add_argument("--levels", nargs="+", default=list(LEVELS), choices=list(LEVELS))
    s = sub.add_parser("solve")
    s.add_argument("--grid", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--alpha", type=float, default=CASE["alpha_deg"])
    s.add_argument("--mach", type=float, default=CASE["mach"])
    s.add_argument("--l2", type=float, default=1.0e-6)
    s.add_argument("--n-cycles", type=int, default=30000)
    s.add_argument("--time-limit", type=float, default=10800.0)
    s.add_argument("--no-nk", action="store_true")
    s.add_argument("--eddy-vis-inf-ratio", type=float, default=EDDY_VIS_INF_RATIO)
    s.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                   help="extra ADflow option, recorded as an override")
    sub.add_parser("compare")
    args = ap.parse_args()
    return {"grid": cmd_grid, "solve": cmd_solve, "compare": cmd_compare}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
