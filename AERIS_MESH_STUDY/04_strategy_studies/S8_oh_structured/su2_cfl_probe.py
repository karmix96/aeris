#!/usr/bin/env python3
"""Why the fine flat plate stalls: one variable, three values, bounded cost.

`fp_comp_137` converges to rms -14.0 on the 137x97 grid. `fp_comp_545` is the
SAME configuration on 545x385 and stalls at -8.63, dropping 0.08 orders per
1,200 iterations. The histories say `Min CFL` sits at 100.0 from the first
iteration to the last in both -- which is the FLOOR set by
CFL_ADAPT_PARAM= ( 0.1, 2.0, 100.0, 1e5 ).

A floor the adapter never leaves is a floor it is pressed against. On a grid
whose cells are four times smaller, CFL 100 is a far more aggressive step than
the same number on the coarse grid, so the hypothesis is that the fine case
wants a CFL below 100 and is forbidden one.

Three floors, same restart, same iteration budget, and the control is the
current setting. What is measured is the residual SLOPE, because the question
is not where it gets to in 1,200 iterations but whether it is moving at all.
"""
from __future__ import annotations
import argparse, csv, json, re, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNS = ROOT / "AERIS_MESH_STUDY/artifacts/su2_validation"
PROBE = ROOT / "AERIS_MESH_STUDY/artifacts/su2_cfl_probe"
SU2 = ROOT / "AERIS_MESH_STUDY/tools/su2_8.5.0/bin/SU2_CFD"
MPIRUN = Path("/home/mike_kara/miniconda3/envs/mach-aero/bin/mpirun")

FLOORS = {"floor100_control": 100.0, "floor10": 10.0, "floor1": 1.0}


def prepare(case: str, name: str, floor: float, iters: int) -> Path:
    out = PROBE / f"{case}__{name}"
    out.mkdir(parents=True, exist_ok=True)
    cfg = (RUNS / case / "case.cfg").read_text().splitlines()
    newest = sorted((RUNS / case).glob("restart*.dat"),
                    key=lambda q: q.stat().st_mtime)[-1]
    # one solution file, copied so the probe cannot disturb the real run
    (out / "solution.dat").write_bytes(newest.read_bytes())
    changes = {
        "CFL_ADAPT_PARAM": f"( 0.1, 2.0, {floor}, 1e5 )",
        "RESTART_SOL": "YES",
        "SOLUTION_FILENAME": "solution.dat",
        "RESTART_FILENAME": "restart_probe.dat",
        "CONV_FILENAME": "history",
        "ITER": str(iters),
        "OUTPUT_WRT_FREQ": str(iters + 1),     # no intermediate volume writes
    }
    seen, lines = set(), []
    for line in cfg:
        body = line.split("%")[0]
        key = body.split("=")[0].strip() if "=" in body else None
        if key in changes:
            lines.append(f"{key}= {changes[key]}")
            seen.add(key)
        else:
            lines.append(line)
    for key, value in changes.items():
        if key not in seen:
            lines.append(f"{key}= {value}")
    (out / "case.cfg").write_text("\n".join(lines) + "\n")
    return out


def slope(directory: Path) -> dict:
    path = directory / "history.csv"
    if not path.exists():
        return {"error": "no history"}
    rows = list(csv.reader(open(path)))
    head = [c.strip().strip('"') for c in rows[0]]
    data = [r for r in rows[1:] if len(r) == len(head)]
    if len(data) < 20:
        return {"error": f"only {len(data)} rows"}
    key = next((h for h in head if h.startswith("rms[Rho]") or h.startswith("rms[P]")), None)
    i, it = head.index(key), head.index("Inner_Iter")
    first, last = float(data[0][i]), float(data[-1][i])
    n = int(float(data[-1][it])) - int(float(data[0][it])) or len(data)
    cfl = next((h for h in head if h.strip().strip('"') == "Min CFL"), None)
    out = {"residual_key": key, "first": round(first, 3), "last": round(last, 3),
           "iterations": n, "orders_per_1000": round(1000.0 * (first - last) / max(n, 1), 4)}
    if cfl:
        j = head.index(cfl)
        out["min_cfl_first_last"] = [float(data[0][j]), float(data[-1][j])]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", default="fp_comp_545")
    ap.add_argument("--iters", type=int, default=1200)
    ap.add_argument("--ranks", type=int, default=2)
    args = ap.parse_args()

    results = {}
    for name, floor in FLOORS.items():
        out = prepare(args.case, name, floor, args.iters)
        print(f"  {name}: CFL floor {floor}, {args.iters} iterations ...", flush=True)
        t0 = time.time()
        with open(out / "run.log", "w") as fh:
            subprocess.run([str(MPIRUN), "-np", str(args.ranks), str(SU2), "case.cfg"],
                           cwd=out, stdout=fh, stderr=subprocess.STDOUT)
        r = slope(out)
        r["wall_seconds"] = round(time.time() - t0, 1)
        r["cfl_floor"] = floor
        results[name] = r
        print(f"    {r.get('first')} -> {r.get('last')}  "
              f"{r.get('orders_per_1000')} orders/1000 iters  "
              f"minCFL {r.get('min_cfl_first_last')}  {r['wall_seconds']} s", flush=True)

    report = ROOT / "AERIS_MESH_STUDY/05_s6_cfd_qualification/reports/s8_su2_cfl_probe.json"
    report.write_text(json.dumps({"schema": "aeris.s8.su2_cfl_probe.v1",
                                  "case": args.case, "iterations_each": args.iters,
                                  "results": results}, indent=2) + "\n")
    best = max(results.items(), key=lambda kv: kv[1].get("orders_per_1000", -9))
    print(f"\n  fastest descent: {best[0]} at {best[1].get('orders_per_1000')} orders/1000")
    print(f"  wrote {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
