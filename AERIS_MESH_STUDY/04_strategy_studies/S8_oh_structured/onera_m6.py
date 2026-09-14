#!/usr/bin/env python
"""ONERA M6 validation: this project's SOLVER against published experiment.

    <mach-python> .../onera_m6.py grid    --out <dir>          # PLOT3D -> CGNS
    <mach-python> .../onera_m6.py solve   --grid <cgns> --out <dir>
    .venv/bin/python .../onera_m6.py compare --run <dir> --out <report.json>
    .venv/bin/python .../onera_m6.py plot    --run <dir> --out <png>

PLAN_desktop_campaign.md 5.  S8 has no experimental validation at all, and
agreement with AVL is not validation -- it is two codes agreeing about a wing
neither has been checked against.

What this establishes, and what it does not
--------------------------------------------
It validates the ADflow CONFIGURATION this project uses -- RANS-SA, ANK->NK, the
governed subspace and fill settings, and the convergence gate -- against a case
with published experimental surface pressures.

It does NOT validate the S8 mesher.  It cannot: S8's mesher builds AERIS BWB
lofts and nothing else, and no public experimental case is an AERIS BWB.  Both
halves belong in any report that cites this.

The regime gap is large and is not a footnote: M6 is transonic at M 0.8395 with
a lambda shock on the upper surface, AERIS runs at M 0.0837.  A transonic
validation says the solver, the turbulence model and the gate behave as
published; it does not transfer quantitatively to shock-free low speed.

Where the data comes from
--------------------------
NASA WIND validation archive, https://www.grc.nasa.gov/www/wind/valid/m6wing/.
The page links the grid as `m6wing.cgd`, which does not exist on the server; the
grid that does exist is `m6wing01/m6wing.x.fmt`, PLOT3D formatted, and the
server's HTTP 300 response names it.  A probe that reads only the status code
concludes there is no grid.  There is.

    grid        4 blocks, 316,932 points, ~290k cells
    experiment  Schmitt and Charpin, AGARD AR-138 (1979), cp at 7 stations
    conditions  M 0.8395, alpha 3.06 deg, Re 11.72e6 on MAC, T 460 R

ORIENTATION, which is the thing to get wrong
---------------------------------------------
Read off the grid rather than assumed, because defect 14 was exactly this:

    x  chordwise   root chord 0.6737, tip 0.3789 (taper 0.562)
    y  LIFT        wing surface spans +/-0.033; zone 2 lower, zone 3 upper
    z  SPAN        0 to 1.0168; K1 is the z = 0 root symmetry plane

So this case needs **liftIndex 2**, which is ADflow's default -- the OPPOSITE of
AERIS, whose meshes span +y and lift +z and therefore need 3.  Copying S8's
liftIndex into this case applies angle of attack as SIDESLIP.  The check that
caught defect 14 is reused here and is fail-closed.

The grid is nondimensionalised by SEMISPAN = 1.0.  That is confirmed rather than
believed: it makes the root chord 0.6737 and the MAC 0.54006, and WIND states
`Reference length = 0.5400570 ft`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))

ARCHIVE = REPO / "AERIS_MESH_STUDY/05_s6_cfd_qualification/external/onera_m6"
PLOT3D_GZ = ARCHIVE / "m6wing.x.fmt.gz"

#: NASA WIND case, from m6wing01/m6wing.txt.  Not the TMR variant, which
#: specifies M 0.84 and Re 14.6e6 on the ROOT chord of a sharp-TE geometry.
#: Both are legitimate published definitions of the same experiment; mixing them
#: is how a validation comes to compare two different flows.
CASE = {
    "source": "NASA WIND validation archive, m6wing01",
    "mach": 0.8395,
    "alpha_deg": 3.06,
    "reynolds": 11.72e6,
    "reynolds_length": 0.5400570,        # MAC, in the grid's units (semispan = 1)
    "temperature_R": 460.0,
    "temperature_K": 460.0 * 5.0 / 9.0,
    "experiment": "Schmitt, V. and Charpin, F., AGARD AR-138, 1979 (test 2308)",
}
#: geometry, derived from the grid and cross-checked against the published wing
GEOMETRY = {
    "semispan": 1.0,
    "root_chord": 0.6737,
    "tip_chord": 0.3789,
    "taper_ratio": 0.562,
    "mac": 0.5400570,
    "half_area": 0.5263,                 # (c_root + c_tip)/2 * semispan
    "le_sweep_deg": 30.0,
    "nondimensionalised_by": "semispan",
}
#: AERIS meshes span +y; this one spans +z, so lift is +y and liftIndex is 2.
LIFT_INDEX = 2
#: the seven measured stations, eta = z/b, read out of ONERAb114.tec itself.
#: The sixth is 0.96 and NOT the 0.95 that AGARD AR-138 and most secondary
#: sources print; recent measurements on the model corrected it.
STATIONS = (0.20, 0.44, 0.65, 0.80, 0.90, 0.96, 0.99)

#: gman.html, m6wing01.  I/J/K = (chordwise-around, wall-normal, spanwise).
#: Faces not named here are block-to-block and are found by `connect`.
WALL, FAR, SYM = "bcwallviscous", "bcfarfield", "bcsymmetryplane"
BCS = {
    1: {"iMin": (FAR, "far"), "jMax": (FAR, "far"), "kMin": (SYM, "sym")},
    2: {"jMin": (WALL, "wall"), "jMax": (FAR, "far"), "kMin": (SYM, "sym")},
    3: {"jMin": (WALL, "wall"), "jMax": (FAR, "far"), "kMin": (SYM, "sym")},
    4: {"iMax": (FAR, "far"), "jMax": (FAR, "far"), "kMin": (SYM, "sym")},
}
#: WIND calls zone 1 iMin and zone 4 iMax "outflow". They are the downstream
#: exit of a C-grid in an external transonic flow, and ADflow's farfield
#: (a characteristic/Riemann condition) is the right treatment: a fixed-pressure
#: outflow would reflect the wake. Recorded because it IS a departure from the
#: WIND setup, not a transcription.
OUTFLOW_NOTE = ("WIND specifies OUTFLOW on zone 1 iMin and zone 4 iMax; this "
                "uses bcfarfield, which is characteristic-based and does not "
                "reflect the wake leaving the C-grid.")


def read_plot3d(path: Path) -> list[np.ndarray]:
    """Multiblock formatted PLOT3D, with Fortran repeat counts expanded.

    The file uses list-directed output, so runs of equal values appear as
    `24*0.E+0`.  A plain float() over the tokens dies on those, and a reader
    that silently skips them produces a grid with the wrong number of points.
    """
    import gzip

    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as handle:
        raw = handle.read().replace(",", " ").split()

    def expand(tokens):
        for token in tokens:
            if "*" in token:
                count, value = token.split("*", 1)
                value = float(value)
                for _ in range(int(count)):
                    yield value
            else:
                yield float(token)

    tokens = list(expand(raw))
    index = 0
    nblocks = int(tokens[index]); index += 1
    dims = [tuple(int(tokens[index + 3 * b + k]) for k in range(3))
            for b in range(nblocks)]
    index += 3 * nblocks
    blocks = []
    for ni, nj, nk in dims:
        n = ni * nj * nk
        arr = np.array(tokens[index:index + 3 * n]); index += 3 * n
        blocks.append(arr.reshape(3, nk, nj, ni).transpose(3, 2, 1, 0))
    if index != len(tokens):
        raise SystemExit(f"PLOT3D: consumed {index} of {len(tokens)} tokens. "
                         f"The file is not the shape its header declares.")
    return blocks


def verify_orientation(blocks: list[np.ndarray]) -> dict:
    """Confirm span is +z and lift is +y BEFORE anything is written.

    Cheap, and the alternative is defect 14: an angle of attack silently applied
    as sideslip, every result void, nothing raised.
    """
    upper = blocks[2][:, 0, :, :]          # zone 3, jMin, the upper surface
    lower = blocks[1][:, 0, :, :]          # zone 2, jMin, the lower surface
    report = {
        "upper_surface_extent": {a: [float(upper[..., i].min()), float(upper[..., i].max())]
                                 for i, a in enumerate("xyz")},
        "lower_surface_extent": {a: [float(lower[..., i].min()), float(lower[..., i].max())]
                                 for i, a in enumerate("xyz")},
        "root_plane_z_spread": float(np.ptp(blocks[2][:, :, 0, 2])),
    }
    span = float(upper[..., 2].max())
    thickness = float(upper[..., 1].max())
    chord = float(upper[..., 0].max())
    report.update(span_extent=span, half_thickness=thickness, chord_extent=chord)
    if not (span > 5 * chord * 0.15 and thickness < 0.2 * chord):
        raise SystemExit(
            f"orientation is not what this case expects: span {span:.3f}, chord "
            f"{chord:.3f}, half-thickness {thickness:.3f}. Refusing to guess "
            f"which axis is lift.")
    if report["root_plane_z_spread"] > 1e-10:
        raise SystemExit(f"kMin is not a constant-z plane (spread "
                         f"{report['root_plane_z_spread']:.3e}); it cannot be the "
                         f"symmetry plane.")
    report["lift_index"] = LIFT_INDEX
    report["reading"] = ("x chordwise, y LIFT, z SPAN, kMin the z=0 root "
                         "symmetry plane. liftIndex 2 -- ADflow's default, and "
                         "the opposite of AERIS.")
    return report


def cmd_grid(args) -> int:
    from cgnsutilities.cgnsutilities import Block, Boco, Grid

    blocks = read_plot3d(args.plot3d)
    orientation = verify_orientation(blocks)
    print(json.dumps(orientation["reading"], indent=2))
    for key in ("span_extent", "chord_extent", "half_thickness"):
        print(f"  {key:<18} {orientation[key]:.4f}")

    args.out.mkdir(parents=True, exist_ok=True)
    grid = Grid()
    grid.cellDim = 3
    report = {"case": CASE, "geometry": GEOMETRY, "orientation": orientation,
              "outflow_note": OUTFLOW_NOTE, "blocks": {}}
    for number, coords in enumerate(blocks, start=1):
        dims = list(coords.shape[:3])
        ni, nj, nk = dims
        ranges = {
            "iMin": [[1, 1], [1, nj], [1, nk]], "iMax": [[ni, ni], [1, nj], [1, nk]],
            "jMin": [[1, ni], [1, 1], [1, nk]], "jMax": [[1, ni], [nj, nj], [1, nk]],
            "kMin": [[1, ni], [1, nj], [1, 1]], "kMax": [[1, ni], [1, nj], [nk, nk]],
        }
        block = Block(f"zone{number}", dims, np.asfortranarray(coords))
        for face, (bc, family) in BCS[number].items():
            block.addBoco(Boco(face, bc, np.array(ranges[face]), family))
        grid.addBlock(block)
        report["blocks"][f"zone{number}"] = {
            "dims": dims, "cells": int(np.prod(np.array(dims) - 1)),
            "explicit_bcs": {f: list(v) for f, v in BCS[number].items()}}

    grid.split([])
    grid.connect(args.tol)
    n_b2b = sum(len(b.B2Bs) for b in grid.blocks)
    n_boco = sum(len(b.bocos) for b in grid.blocks)
    report["block_to_block_connections"] = int(n_b2b)
    report["boundary_conditions"] = int(n_boco)
    report["total_cells"] = sum(b["cells"] for b in report["blocks"].values())

    out = args.out / "m6_L0.cgns"
    grid.writeToCGNS(str(out))
    report["levels"] = {"m6_L0": {"path": str(out), "cells": report["total_cells"]}}
    print(f"\n  wrote {out}  ({report['total_cells']:,} cells, "
          f"{n_b2b} block-to-block, {n_boco} BCs)")

    # a coarsened family, so gci.py can be exercised on a case with a known answer
    # cgnsutilities' coarsen() mutates the Grid in place and returns None, so
    # the returned value must not be reassigned. Coarsening halves each block's
    # intervals, which is the standard way to build a systematically refined
    # family from one delivered grid -- every level is the same mesh at a
    # different spacing, which is what a convergence family has to be.
    current = grid
    for level in range(1, args.levels):
        current.coarsen()
        name = f"m6_L{level}"
        path = args.out / f"{name}.cgns"
        current.writeToCGNS(str(path))
        cells = sum(int(np.prod(np.array(b.dims) - 1)) for b in current.blocks)
        report["levels"][name] = {"path": str(path), "cells": cells}
        print(f"  wrote {path}  ({cells:,} cells)")

    (args.out / "m6_grid_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"\n  wrote {args.out / 'm6_grid_report.json'}")
    return 0



def experiment() -> dict:
    """The measured cp, from ONERAb114.tec.

    That file is the authoritative one: it carries x/L, y/b, z/L AND cp for all
    seven sections in one place, so the station each point belongs to comes from
    the data rather than from a filename. The cp<n>u/l.ex files hold the same
    measurements split by surface with error estimates, and are used for the
    error bars only.
    """
    import re
    path = ARCHIVE / "ONERAb114.tec"
    if not path.exists():
        raise SystemExit(f"{path} is missing. Run tmr_onera_m6.py fetch.")
    sections: dict[int, list] = {}
    current = None
    for line in path.read_text().splitlines():
        match = re.match(r'ZONE T="Section\s+(\d+)"', line.strip())
        if match:
            current = int(match.group(1)); sections[current] = []; continue
        if current is None or line.startswith(("TITLE", "VARIABLES")):
            continue
        parts = line.split()
        if len(parts) == 5:
            try:
                sections[current].append([float(v) for v in parts])
            except ValueError:
                continue
    out = {}
    for number, rows in sorted(sections.items()):
        a = np.array(rows)
        # Columns are NP, X/L, Y/b, Z/L, Cp. Y/b is the SPAN station and Z/L is
        # the VERTICAL coordinate -- so in the experiment's frame z is up, while
        # in this grid Y is up and z is span. Their Z maps to our Y, and getting
        # that backwards silently compares an upper surface against a lower one.
        #
        # The measurements are NOT pre-split by surface: all 34 (or 45) points
        # of a station sit in one list, upper and lower interleaved. Splitting
        # them by the sign of their own vertical coordinate is what makes an
        # upper-to-upper comparison possible at all.
        vertical = a[:, 3]
        upper = vertical >= 0.0
        out[number] = {"eta": float(np.mean(a[:, 2])), "x_over_c": a[:, 1],
                       "vertical": vertical, "cp": a[:, 4], "n": len(a),
                       "upper": upper,
                       "n_upper": int(upper.sum()), "n_lower": int((~upper).sum())}
    return out


def local_chord(eta: float) -> tuple[float, float]:
    """(leading-edge x, chord) at a spanwise station, from the planform."""
    root, tip = GEOMETRY["root_chord"], GEOMETRY["tip_chord"]
    chord = root + (tip - root) * eta
    x_le = eta * np.tan(np.radians(GEOMETRY["le_sweep_deg"]))
    return float(x_le), float(chord)


def cmd_solve(args) -> int:
    """One ADflow point, with THIS PROJECT'S option set, on the M6 grid.

    The option block is copied from solve_s8.py deliberately and deliberately
    unchanged, because a validation establishes nothing about a configuration it
    did not run. What differs is only what MUST differ: the operating point, the
    references, and liftIndex -- which is 2 here and 3 for AERIS, for the reason
    in the module docstring.
    """
    from adflow import ADFLOW
    from baseclasses import AeroProblem

    args.out.mkdir(parents=True, exist_ok=True)
    options = {
        "gridFile": str(args.grid), "outputDirectory": str(args.out),
        "equationType": "RANS", "turbulenceModel": "SA",
        "liftIndex": args.lift_index,
        "MGCycle": "sg",
        "useANKSolver": True, "ANKSwitchTol": 1.0,
        "useNKSolver": not args.no_nk, "NKSwitchTol": 1.0e-6,
        "ANKSubspaceSize": 10, "NKSubspaceSize": 20,
        "ANKPCILUFill": 1, "NKPCILUFill": 1,
        "L2Convergence": args.l2, "nCycles": args.n_cycles,
        "timeLimit": args.time_limit,
        "storeConvHist": True,
        "writeVolumeSolution": True, "writeSurfaceSolution": True,
        "monitorVariables": ["resrho", "resmom", "resrhoe", "resturb",
                             "cl", "cd", "cmy", "cdp", "cdv"],
        "surfaceVariables": ["cp", "cf", "yplus", "vx", "vy", "vz"],
    }
    solver = ADFLOW(options=options)
    problem = AeroProblem(
        name=f"m6_a{args.alpha:g}", alpha=args.alpha, beta=0.0,
        mach=CASE["mach"], reynolds=CASE["reynolds"],
        reynoldsLength=CASE["reynolds_length"], T=CASE["temperature_K"],
        areaRef=GEOMETRY["half_area"], chordRef=GEOMETRY["mac"],
        xRef=0.0, yRef=0.0, zRef=0.0,
        evalFuncs=["cl", "cd", "cmy", "cdp", "cdv"])
    solver.setAeroProblem(problem)

    # defect 14's guard, re-aimed at this geometry: lift is +y here, so the
    # freestream must rotate in the x-y plane and NOT toward the span.
    a = np.radians(args.alpha)
    # liftIndex 2 rotates the freestream in x-y (the WIND grid spans +z);
    # liftIndex 3 rotates it in x-z (our own mesh spans +y, as every AERIS grid).
    if args.lift_index == 2:
        want_vel = np.array([np.cos(a), np.sin(a), 0.0])
        want_lift = np.array([-np.sin(a), np.cos(a), 0.0])
    else:
        want_vel = np.array([np.cos(a), 0.0, np.sin(a)])
        want_lift = np.array([-np.sin(a), 0.0, np.cos(a)])
    physics = solver.adflow.inputphysics
    got_vel = np.array(physics.veldirfreestream, dtype=float).ravel()[:3]
    got_lift = np.array(physics.liftdirection, dtype=float).ravel()[:3]
    got_index = int(physics.liftindex)
    errors = (float(np.linalg.norm(got_vel - want_vel)),
              float(np.linalg.norm(got_lift - want_lift)))
    directions = {"lift_index_requested": args.lift_index, "lift_index_realised": got_index,
                  "velocity_direction_expected": want_vel.tolist(),
                  "velocity_direction_realised": got_vel.tolist(),
                  "velocity_direction_error": errors[0],
                  "lift_direction_error": errors[1]}
    if got_index != args.lift_index or max(errors) > 1.0e-9:
        raise SystemExit(f"freestream is not what this geometry asked for: {directions}. "
                         f"A z-component here is SIDESLIP against the root symmetry "
                         f"plane. Not running.")

    solver(problem)
    funcs: dict = {}
    solver.evalFunctions(problem, funcs)
    try:
        iteration = solver.adflow.iteration
        residual = float(iteration.totalrfinal / iteration.totalr0)
    except Exception:  # noqa: BLE001 - never assumed converged
        residual = None
    result = {"case": CASE, "geometry": GEOMETRY, "grid": str(args.grid),
              "alpha_deg": args.alpha, "relative_residual": residual,
              "l2_target": args.l2, "converged": residual is not None and residual <= args.l2,
              "flow_directions": directions,
              "solver_overrides": {"useNKSolver": False} if args.no_nk else {},
              "functions": {k: float(v) for k, v in funcs.items()}}
    (args.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["functions"], indent=2))
    return 0


def surface_cp(run: Path, span: str = "z") -> dict:
    """Wall cp, kept STRUCTURED so a spanwise station can be selected by index.

    Flattening loses the only reliable way to pick a station. The grid's
    spanwise planes are not constant-z -- a single k-plane spans about 0.012 of
    semispan near mid-span, because the C-grid follows the sweep -- so a
    tolerance band on z either misses a row entirely (eta 0.44 returned nothing)
    or catches two (eta 0.99 returned 384 cells where a row is 144). The row
    index is exact and the z value is not.
    """
    import cgns_read
    surfaces = sorted(run.glob("*surf*.cgns"))
    if not surfaces:
        raise SystemExit(f"no surface solution in {run}")
    rows = []
    for name, node in cgns_read.surface_zones(surfaces[0]):
        if "Wall" not in name and "wall" not in name:
            continue
        g, s = node["GridCoordinates"], node["Flow solution"]
        xyz = [np.array(g[f"Coordinate{a}"][" data"]) for a in "XYZ"]
        cp = np.array(s["CoefPressure"][" data"])
        shape = (xyz[0].shape[0] - 1, xyz[0].shape[1] - 1)
        if cp.shape != shape:
            cp = cp[1:-1, 1:-1]
        centre = [0.25 * (c[:-1, :-1] + c[:-1, 1:] + c[1:, :-1] + c[1:, 1:])
                  for c in xyz]
        # orient so axis 0 is SPANWISE: the wing's span is much longer than its
        # chord here, so the axis whose mean z varies most is the spanwise one.
        # on the WIND grid the span is z; on a mesh of ours it is y
        s_coord = centre["xyz".index(span)]
        span_axis = 0 if np.ptp(s_coord.mean(axis=1)) > np.ptp(s_coord.mean(axis=0)) else 1
        if span_axis == 1:
            centre = [c.T for c in centre]; cp = cp.T
        rows.append({"name": name, "x": centre[0], "y": centre[1],
                     "z": centre[2], "cp": cp})
    if not rows:
        raise SystemExit(f"{surfaces[0]} has no wall zone")
    return {"zones": rows, "file": str(surfaces[0]),
            "x": np.concatenate([r["x"].ravel() for r in rows]),
            "y": np.concatenate([r["y"].ravel() for r in rows]),
            "z": np.concatenate([r["z"].ravel() for r in rows]),
            "cp": np.concatenate([r["cp"].ravel() for r in rows])}


def station_slice(surf: dict, eta: float, span: str = "z") -> dict:
    """Every wall zone's surface, interpolated to exactly a measured station.

    Each chordwise column is interpolated along the span to the station's own
    span coordinate, so upper and lower surfaces are both represented and the
    count is the same at every station.

    This was once the NEAREST row, and x/c was then normalised by the leading
    edge and chord at the REQUESTED station. On a 30-degree swept wing a row
    delta-eta off the station sits delta-eta * tan(30) * semispan further aft,
    so the whole section slid along x/c: on our own M6 mesh stations 2 and 3
    started at x/c +0.04 and -0.03, and read as shock-position errors of 0.043
    and 0.476 x/c that no flow produced.
    """
    target = eta * GEOMETRY["semispan"]
    x, y, zc, cp, zs = [], [], [], [], []
    for zone in surf["zones"]:
        # A tip cap is a wall zone too, but it is a flat face at one span
        # station, so its "nearest row" is chosen at EVERY station and its cells
        # land in every slice -- at the tip leading edge's x, which drifts forward
        # in x/c as eta grows. On our own M6 mesh that put a cp -1.9 spike into all
        # seven stations and read as a 62 % suction-peak error. A zone that barely
        # spans anything is not a slice of the wing.
        if np.ptp(zone[span]) < 0.05 * GEOMETRY["semispan"]:
            continue
        s = zone[span]
        row = {key: np.empty(s.shape[1]) for key in ("x", "y", "z", "cp")}
        for j in range(s.shape[1]):
            order = np.argsort(s[:, j])
            for key in row:
                row[key][j] = np.interp(target, s[order, j], zone[key][order, j])
        x.append(row["x"]); y.append(row["y"]); zc.append(row["z"])
        cp.append(row["cp"]); zs.append(row[span].mean())
    return {"x": np.concatenate(x), "y": np.concatenate(y), "z": np.concatenate(zc),
            "cp": np.concatenate(cp),
            "z_actual": float(np.mean(zs)),
            "z_requested": target}


def shock_position(xc: np.ndarray, cp: np.ndarray) -> dict:
    """Where the upper-surface shock sits, as x/c.

    A shock is a rapid PRESSURE RISE going aft, so it is the largest positive
    d(cp)/d(x/c) on the upper surface. This is the quantity a transonic
    validation should be read on, and pointwise cp is not: cp jumps by order one
    across a shock, so a shock placed two cells early produces a huge pointwise
    error from a solution whose physics is right. RMS over a station is
    therefore dominated by the shock and says more about grid resolution than
    about whether the code reproduces the flow.
    """
    order = np.argsort(xc)
    x, c = xc[order], cp[order]
    keep = (x > 0.05) & (x < 0.98)          # ignore the stagnation region and the TE
    x, c = x[keep], c[keep]
    if x.size < 6:
        return {"x_over_c": float("nan"), "strength": float("nan")}
    grad = np.gradient(c, x)
    i = int(np.argmax(grad))
    return {"x_over_c": float(x[i]), "strength": float(grad[i]),
            "cp_before": float(c[max(i - 2, 0)]), "cp_after": float(c[min(i + 2, c.size - 1)])}


def cmd_compare(args) -> int:
    """Computed cp against the seven measured stations."""
    exp = experiment()
    span, vert = args.span_axis, ("y" if args.span_axis == "z" else "z")
    surf = surface_cp(args.run, span=span)
    report = {"case": CASE, "run": str(args.run), "stations": []}
    print(f"{'stn':>4}{'eta':>7}{'exp pts':>9}{'cfd pts':>9}{'z used':>9}"
          f"{'cp_min exp':>12}{'cp_min cfd':>12}{'rms dcp':>10}")
    for number, data in exp.items():
        eta = data["eta"]
        sl = station_slice(surf, eta, span=span)
        x_le, chord = local_chord(eta)
        xc = (sl["x"] - x_le) / chord
        cp = sl["cp"]
        upper = sl[vert] >= 0
        pick = cp
        entry = {"station": number, "eta": eta, "n_experiment": data["n"],
                 "n_cfd_cells": int(cp.size),
                 "z_requested": sl["z_requested"], "z_actual": sl["z_actual"],
                 "x_le": x_le, "chord": chord,
                 "n_experiment_upper": data["n_upper"],
                 "n_experiment_lower": data["n_lower"],
                 "experiment": {"x_over_c": data["x_over_c"].tolist(),
                                "cp": data["cp"].tolist(),
                                "upper": data["upper"].tolist()},
                 "cfd": {"x_over_c": xc.tolist(), "cp": cp.tolist(),
                         "upper": upper.tolist()}}
        rms = float("nan")
        if cp.size > 5:
            # interpolate CFD onto the measured abscissae, upper and lower apart
            errs = []
            for mask, exp_mask in ((upper, data["upper"]), (~upper, ~data["upper"])):
                # upper against upper, lower against lower. Comparing a computed
                # upper surface against interleaved measurements that include the
                # lower surface is meaningless and produces a large RMS from a
                # solution that is in fact correct -- it did here, 0.40 against a
                # cp_min that agreed to one per cent.
                if mask.sum() < 3 or exp_mask.sum() < 2:
                    continue
                order = np.argsort(xc[mask])
                xi, ci = xc[mask][order], cp[mask][order]
                ex, ecp = data["x_over_c"][exp_mask], data["cp"][exp_mask]
                inside = (ex >= xi.min()) & (ex <= xi.max())
                if inside.sum():
                    errs.append(np.interp(ex[inside], xi, ci) - ecp[inside])
            if errs:
                rms = float(np.sqrt(np.mean(np.concatenate(errs) ** 2)))
        entry["rms_dcp_vs_experiment"] = rms
        # shock position, computed the same way for both, so the comparison is
        # like for like
        eu = data["upper"]
        entry["shock_experiment"] = shock_position(data["x_over_c"][eu], data["cp"][eu])
        entry["shock_cfd"] = shock_position(xc[upper], cp[upper])
        entry["shock_dx_over_c"] = (entry["shock_cfd"]["x_over_c"]
                                    - entry["shock_experiment"]["x_over_c"])
        entry["cp_min_experiment"] = float(data["cp"].min())
        entry["cp_min_cfd"] = float(cp.min())
        entry["cp_min_error"] = float(abs(cp.min() - data["cp"].min())
                                      / abs(data["cp"].min()))
        report["stations"].append(entry)
        print(f"{number:>4}{eta:>7.2f}{data['n']:>9}{int(cp.size):>9}"
              f"{sl['z_actual']:>9.3f}"
              f"{data['cp'].min():>12.3f}{cp.min():>12.3f}{rms:>10.4f}")
    print(f"\n{'stn':>4}{'eta':>7}{'shock exp':>11}{'shock cfd':>11}{'dx/c':>9}"
          f"{'cp_min err':>12}")
    for s in report["stations"]:
        print(f"{s['station']:>4}{s['eta']:>7.2f}"
              f"{s['shock_experiment']['x_over_c']:>11.3f}"
              f"{s['shock_cfd']['x_over_c']:>11.3f}"
              f"{s['shock_dx_over_c']:>+9.3f}"
              f"{100 * s['cp_min_error']:>11.1f}%")
    dx = [abs(s["shock_dx_over_c"]) for s in report["stations"]
          if np.isfinite(s["shock_dx_over_c"])]
    pk = [s["cp_min_error"] for s in report["stations"]]
    if dx:
        report["shock_position_mean_abs_error_x_over_c"] = float(np.mean(dx))
        report["cp_min_mean_relative_error"] = float(np.mean(pk))
        print(f"\n  mean |shock position error|  {np.mean(dx):.3f} x/c")
        print(f"  mean |suction peak error|    {100 * np.mean(pk):.1f} %")

    valid = [s["rms_dcp_vs_experiment"] for s in report["stations"]
             if np.isfinite(s["rms_dcp_vs_experiment"])]
    if valid:
        report["rms_dcp_all_stations"] = float(np.mean(valid))
        print(f"\n  mean RMS dcp over stations: {np.mean(valid):.4f}")
        print("  Context: this is a transonic case with a lambda shock. Agreement")
        print("  to a few hundredths in cp away from the shock, and larger error AT")
        print("  the shock, is the expected shape of a RANS-SA result -- shock")
        print("  POSITION is what to read, not pointwise cp through it.")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\n  wrote {args.out}")
    return 0


def cmd_plot(args) -> int:
    """Seven cp panels against experiment, plus convergence and forces."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    exp = experiment()
    span, vert = args.span_axis, ("y" if args.span_axis == "z" else "z")
    surf = surface_cp(args.run, span=span)
    result = json.loads((args.run / "result.json").read_text()) \
        if (args.run / "result.json").exists() else {}

    fig, ax = plt.subplots(2, 4, figsize=(21, 9))
    for idx, (number, data) in enumerate(exp.items()):
        a = ax.flat[idx]
        eta = data["eta"]
        sl = station_slice(surf, eta, span=span)
        x_le, chord = local_chord(eta)
        xc = (sl["x"] - x_le) / chord
        cp, upper = sl["cp"], sl[vert] >= 0
        for side, mask, colour in (("upper", upper, "C0"), ("lower", ~upper, "C2")):
            if mask.sum() < 3:
                continue
            order = np.argsort(xc[mask])
            a.plot(xc[mask][order], cp[mask][order], "-", color=colour, lw=1.4,
                   label=f"CFD {side}")
        for emask, mk, lab in ((data["upper"], "ko", "experiment upper"),
                               (~data["upper"], "ks", "experiment lower")):
            a.plot(data["x_over_c"][emask], data["cp"][emask], mk, ms=3.5,
                   mfc="none", label=lab)
        a.invert_yaxis()
        a.set_title(f"$\\eta$ = {eta:.2f}   (station {number})", fontsize=10)
        a.set_xlabel("$x/c$"); a.set_ylabel("$c_p$")
        a.grid(alpha=0.3)
        if idx == 0:
            a.legend(fontsize=7)

    a = ax.flat[7]
    log = args.run / "run.log"
    if log.exists():
        import re
        rows = [l.split() for l in log.read_text().splitlines()
                if re.match(r"^ +1 +\d+ +\d+ ", l)]
        if rows:
            width = min(len(r) for r in rows)
            res = np.array([float(r[7]) for r in rows if len(r) >= width])
            a.semilogy(res / res[0], color="C3")
            a.axhline(1e-6, ls="--", color="0.5", lw=1)
            a.annotate("1e-6 stopping target", (0.05, 1.4e-6), fontsize=7, color="0.4")
    a.set_xlabel("iteration"); a.set_ylabel("density residual / initial")
    a.set_title("Convergence", fontsize=10); a.grid(alpha=0.3)

    funcs = {k.split("_")[-1]: v for k, v in result.get("functions", {}).items()}
    subtitle = (f"CL {funcs.get('cl', float('nan')):.4f}   "
                f"CD {funcs.get('cd', float('nan')):.5f}" if funcs else "")
    fig.suptitle(
        f"ONERA M6 -- ADflow RANS-SA, this project's option set, against "
        f"Schmitt & Charpin (AGARD AR-138)\n"
        f"M {CASE['mach']}, alpha {CASE['alpha_deg']} deg, Re {CASE['reynolds']:.3g} "
        f"on MAC, liftIndex {LIFT_INDEX}.   {subtitle}\n"
        f"Validates the SOLVER CONFIGURATION and the gate. Does NOT validate the "
        f"S8 mesher, which no public experimental case can.", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=150)
    print(f"wrote {args.out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    g = sub.add_parser("grid", help="PLOT3D -> CGNS with boundary conditions")
    g.add_argument("--plot3d", type=Path, default=PLOT3D_GZ)
    g.add_argument("--out", type=Path,
                   default=REPO / "AERIS_MESH_STUDY/artifacts/onera_m6")
    g.add_argument("--levels", type=int, default=3,
                   help="how many grid levels, coarsening from the delivered one")
    g.add_argument("--tol", type=float, default=1.0e-8)
    g.set_defaults(func=cmd_grid)

    s = sub.add_parser("solve", help="one ADflow point with this project's options")
    s.add_argument("--grid", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--alpha", type=float, default=CASE["alpha_deg"])
    s.add_argument("--l2", type=float, default=1.0e-6)
    s.add_argument("--n-cycles", type=int, default=30000)
    s.add_argument("--time-limit", type=float, default=21600.0)
    s.add_argument("--no-nk", action="store_true")
    s.add_argument("--lift-index", type=int, default=LIFT_INDEX, choices=(2, 3),
                   help="2 for the WIND grid (spans +z), 3 for a mesh of ours (spans +y)")
    s.set_defaults(func=cmd_solve)

    c = sub.add_parser("compare", help="computed cp against the seven stations")
    c.add_argument("--run", type=Path, required=True)
    c.add_argument("--band", type=float, default=0.01,
                   help="spanwise half-width, in semispans, of the strip of wall "
                        "cells taken as one station")
    c.add_argument("--out", type=Path, default=None)
    c.add_argument("--span-axis", default="z", choices=("z", "y"),
                   help="z for the WIND grid, y for a mesh of ours")
    c.set_defaults(func=cmd_compare)

    pl = sub.add_parser("plot", help="cp panels, convergence and forces")
    pl.add_argument("--run", type=Path, required=True)
    pl.add_argument("--band", type=float, default=0.01)
    pl.add_argument("--out", type=Path, required=True)
    pl.add_argument("--span-axis", default="z", choices=("z", "y"),
                   help="z for the WIND grid, y for a mesh of ours")
    pl.set_defaults(func=cmd_plot)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
