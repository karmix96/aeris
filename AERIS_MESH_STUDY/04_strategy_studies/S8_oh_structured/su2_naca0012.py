"""SU2 on the NACA 0012 TMR case: whose friction drag is right, and how to fix SU2's.

On the AERIS wing's coarse mesh SU2 carried about 25 % more friction drag than ADflow.
ADflow's friction on the NACA 0012 TMR case -- M 0.15, Re 6e6, alpha 10, SA, chi 3 --
is within 0.6 % of the answer CFL3D, FUN3D and TAU agree on. With exactly the numerics
it ran the wing with, on ADflow's own o512 grid, SU2's is 15 % over (variant `wing`).
So the gap is SU2's setup, and each other variant tests ONE idea about where it comes
from, at about five minutes a run.

The grid is ADflow's o512 (pyHyp, 500 chords), written as a 2D SU2 mesh from one of its
two span planes. SU2 takes lift in y in 2D, which is how the airfoil lies.

    python su2_naca0012.py mesh
    python su2_naca0012.py config --variant wls
    (cd artifacts/su2_naca0012/wls && mpirun -np 1 SU2_CFD case.cfg > run.log)
    python su2_naca0012.py compare --variant wls
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np

from naca0012_tmr import OUT as TMR_OUT, REFERENCE

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
OUT = STUDY / "artifacts/su2_naca0012"
REPORT = STUDY / "05_s6_cfd_qualification/reports/s8_su2_naca0012.json"
GRID = TMR_OUT / "o512.cgns"
ADFLOW_RESULT = TMR_OUT / "runs/o512_m0.15_chi3/result.json"
#: the configuration SU2 ran the wing with; only the case changes
WING_CFG = STUDY / "artifacts/su2_check/a0/case.cfg"
CASE = {"MACH_NUMBER": "0.15", "AOA": "10.0", "SIDESLIP_ANGLE": "0.0",
        "FREESTREAM_TEMPERATURE": "300.0", "REYNOLDS_NUMBER": "6000000.0",
        "REYNOLDS_LENGTH": "1.0", "REF_LENGTH": "1.0", "REF_AREA": "1.0",
        "REF_ORIGIN_MOMENT_X": "0.25", "REF_ORIGIN_MOMENT_Y": "0.0",
        "REF_ORIGIN_MOMENT_Z": "0.0", "FREESTREAM_NU_FACTOR": "3.0",
        "MARKER_HEATFLUX": "( wall, 0.0 )", "MARKER_FAR": "( far )",
        "MARKER_PLOTTING": "( wall )", "MARKER_MONITORING": "( wall )",
        "MESH_FILENAME": str(OUT / "o512.su2"), "MESH_FORMAT": "SU2",
        "ITER": "60000", "CONV_FIELD": "DRAG", "CONV_CAUCHY_ELEMS": "500",
        "CONV_CAUCHY_EPS": "1E-7", "CONV_STARTITER": "10",
        "VOLUME_OUTPUT": "( COORDINATES, SOLUTION, PRIMITIVE )"}
DROP = {"MARKER_SYM"}                  # a 2D mesh has no symmetry planes
#: one idea each about where +15 % friction comes from
VARIANTS = {
    "wing": {},
    # friction is built from velocity gradients at the wall, and Green-Gauss gradients
    # are the usual suspect on the very flat cells a wall-resolved mesh puts there
    "wls": {"NUM_METHOD_GRAD": "WEIGHTED_LEAST_SQUARES"},
    # second-order advection of the turbulence variable, as the TMR codes run it
    "wls_muscl_turb": {"NUM_METHOD_GRAD": "WEIGHTED_LEAST_SQUARES", "MUSCL_TURB": "YES"},
    # an upwind flux in place of JST's central flux with scalar dissipation
    "roe_wls": {"CONV_NUM_METHOD_FLOW": "ROE", "MUSCL_FLOW": "YES",
                "SLOPE_LIMITER_FLOW": "NONE", "NUM_METHOD_GRAD": "WEIGHTED_LEAST_SQUARES"},
}


def run_dir(variant: str) -> Path:
    return OUT if variant == "wing" else OUT / variant


def cmd_mesh(args) -> int:
    import cgns_read
    with cgns_read.CGNSFile(GRID) as handle:
        zones = handle.zones()
        if len(zones) != 1:
            raise SystemExit(f"{GRID} has {len(zones)} zones; expected pyHyp's one")
        zone = zones[0]
        xyz = handle.read_coords(zone["base"], zone["zone"],
                                 [d for d in zone["vertex_dims"] if d > 0])
    # pyHyp extrudes the `n 2 1` surface: (around, span planes, wall -> far field)
    if xyz.ndim != 4 or xyz.shape[1] != 2:
        raise SystemExit(f"unexpected grid shape {xyz.shape}")
    plane = xyz[:, 0, :, :2]
    radius = np.hypot(plane[..., 0] - 0.5, plane[..., 1])
    if radius[:, 0].max() > 0.6 or radius[:, -1].min() < 100:
        raise SystemExit("the first march layer is not the wall or the last is not the far field")
    ni, nk = plane.shape[:2]
    gap = float(np.linalg.norm(plane[0] - plane[-1], axis=1).max())
    if gap > 1.0e-10:
        raise SystemExit(f"the O-grid does not close on itself: {gap:.2e}")
    n = ni - 1

    def node(i: int, k: int) -> int:
        return (i % n) * nk + k

    # counter-clockwise quadrilaterals, whichever way pyHyp ran round the airfoil
    p = [plane[0, 0], plane[1, 0], plane[1, 1], plane[0, 1]]
    area = 0.5 * sum(p[m][0] * p[(m + 1) % 4][1] - p[(m + 1) % 4][0] * p[m][1] for m in range(4))
    order = ((0, 0), (1, 0), (1, 1), (0, 1)) if area > 0 else ((0, 0), (0, 1), (1, 1), (1, 0))
    lines = ["NDIME= 2", f"NELEM= {n * (nk - 1)}"]
    element = 0
    for i in range(n):
        for k in range(nk - 1):
            lines.append("9 " + " ".join(str(node(i + a, k + b)) for a, b in order) + f" {element}")
            element += 1
    lines.append(f"NPOIN= {n * nk}")
    for i in range(n):
        for k in range(nk):
            lines.append(f"{plane[i, k, 0]:.16e} {plane[i, k, 1]:.16e} {node(i, k)}")
    lines.append("NMARK= 2")
    for tag, k in (("wall", 0), ("far", nk - 1)):
        lines += [f"MARKER_TAG= {tag}", f"MARKER_ELEMS= {n}"]
        lines += [f"3 {node(i, k)} {node(i + 1, k)}" for i in range(n)]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "o512.su2").write_text("\n".join(lines) + "\n")
    print(f"  o512.su2: {n * (nk - 1):,} quadrilaterals, {n * nk:,} nodes, "
          f"{'counter-clockwise as read' if area > 0 else 'reordered counter-clockwise'}")
    return 0


def cmd_config(args) -> int:
    keys = {**CASE, **VARIANTS[args.variant]}
    out, seen = [], set()
    for line in WING_CFG.read_text().splitlines():
        key = line.split("=")[0].strip()
        if key in DROP:
            continue
        if key in keys:
            out.append(f"{key}= {keys[key]}")
            seen.add(key)
        else:
            out.append(line)
    out += [f"{k}= {v}" for k, v in keys.items() if k not in seen]
    directory = run_dir(args.variant)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "case.cfg").write_text("\n".join(out) + "\n")
    print(f"  {directory / 'case.cfg'}: the wing's numerics, {len(CASE)} case keys, "
          f"variant {args.variant!r} {VARIANTS[args.variant]}")
    return 0


def cmd_compare(args) -> int:
    directory = run_dir(args.variant)
    text = (directory / "forces_breakdown.dat").read_text()
    number = r"([-\d.eE+]+)"

    def total(key: str) -> list[float]:
        m = re.search(rf"Total {key}:\s+{number} \| Pressure \(\s*-?\d+%\):\s+{number} \| "
                      rf"Friction \(\s*-?\d+%\):\s+{number}", text)
        return [float(v) for v in m.groups()]

    cl = total("CL")[0]
    cd, cdp, cdv = total("CD")
    su2 = {"CL": cl, "CD": cd, "CDp": cdp, "CDv": cdv}
    adflow = json.loads(ADFLOW_RESULT.read_text())["coefficients"]
    tmr = {k: sum(v) / 2 for k, v in REFERENCE.items()}
    log = (directory / "run.log").read_text() if (directory / "run.log").exists() else ""
    report = json.loads(REPORT.read_text()) if REPORT.exists() else {}
    if report.get("schema") != "aeris.s8.su2_naca0012.v2":
        # v1 held the one `wing` run; keep it as that variant
        old = report if report.get("su2") else None
        report = {"schema": "aeris.s8.su2_naca0012.v2", "grid": str(GRID),
                  "tmr_sa_no_point_vortex_mid": tmr, "adflow_o512_chi3": adflow,
                  "adflow_vs_tmr_pct": {k: 100 * (adflow[k] - tmr[k]) / tmr[k] for k in su2},
                  "variants": {}}
        if old:
            report["variants"]["wing"] = {"changes": {}, "su2": old["su2"],
                                          "su2_vs_tmr_pct": old["su2_vs_tmr_pct"],
                                          "exit_success": old.get("su2_exit_success")}
    report["variants"][args.variant] = {
        "changes": VARIANTS[args.variant], "su2": su2, "exit_success": "Exit Success" in log,
        "su2_vs_tmr_pct": {k: 100 * (su2[k] - tmr[k]) / tmr[k] for k in su2}}
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{'':>16}{'CL':>9}{'CD':>9}{'CDp':>9}{'CDv':>9}   (% from TMR)")
    print(f"{'ADflow':>16}" + "".join(f"{v:>+9.2f}" for v in report["adflow_vs_tmr_pct"].values()))
    for name, v in report["variants"].items():
        print(f"{'SU2 ' + name:>16}" + "".join(f"{x:>+9.2f}" for x in v["su2_vs_tmr_pct"].values())
              + ("" if v.get("exit_success") else "   (did not finish cleanly)"))
    print(f"  wrote {REPORT}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("mesh")
    for name in ("config", "compare"):
        p = sub.add_parser(name)
        p.add_argument("--variant", default="wing", choices=list(VARIANTS))
    args = ap.parse_args()
    return {"mesh": cmd_mesh, "config": cmd_config, "compare": cmd_compare}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
