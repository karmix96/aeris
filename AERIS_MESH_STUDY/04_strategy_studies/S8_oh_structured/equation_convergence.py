"""Did EVERY equation converge, not just the total?

Fluent judges a run equation by equation: continuity, each momentum component,
energy, turbulence. ADflow stops on `totalRes`, the norm over all of them
together, and `convergence_gate.py` re-judges on the continuity residual alone.
Either can hide one lagging equation behind five healthy ones.

This reads the iteration table every run already writes, maps the columns from
the printed header (so it works whatever `monitorVariables` were asked for), and
reports each equation's own drop.

Normalisation follows Fluent: the residual is divided by the LARGEST value in
the first five iterations, not by iteration zero. Iteration zero is the
freestream initial guess, where an equation can start artificially small --
nuturb starts at 7e-4 here while continuity starts at 9e+2 -- and dividing by it
would demand a drop that never had anywhere to fall from. Both are reported.

    python equation_convergence.py --runs "../../artifacts/s8_pilot/g*/gci_*_a*"
"""
from __future__ import annotations

import argparse
import glob
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
#: the equations; anything else in the table is a force monitor
EQUATIONS = ("rho", "rhou", "rhov", "rhow", "rhoE", "nuturb", "totalRes")
FLUENT_WINDOW = 5


def columns(log: Path) -> dict[str, int] | None:
    """Map name -> numeric column, from the header ADflow prints."""
    for line in log.read_text(errors="ignore").splitlines():
        if line.startswith("#") and "Res rho" in line:
            names = [c.strip() for c in line.lstrip("#").split("|")]
            names = [n for n in names if n]
            # the first seven are Grid, Iter, Iter, Iter, CFL, Step, Lin
            out = {}
            for i, name in enumerate(names[7:]):
                key = name.replace("Res ", "").replace("C_lift", "cl")
                key = key.replace("C_drag_p", "cdp").replace("C_drag_v", "cdv")
                key = key.replace("C_drag", "cd").replace("C_My", "cmy")
                out[key] = i
            return out
    return None


def history(log: Path, width: int) -> np.ndarray | None:
    rows = []
    for line in log.read_text(errors="ignore").splitlines():
        parts = line.split()
        if len(parts) < 7 + width or not parts[0].isdigit():
            continue
        try:
            rows.append([float(c) for c in parts[7:7 + width]])
        except ValueError:
            continue
    return np.array(rows) if len(rows) > FLUENT_WINDOW else None


def measure(run: Path) -> dict | None:
    log = run / "run.log"
    if not log.exists():
        return None
    cols = columns(log)
    if not cols:
        return None
    hist = history(log, len(cols))
    if hist is None:
        return None
    out: dict = {"run": str(run), "iterations": int(hist.shape[0]), "equations": {}}
    for name in EQUATIONS:
        if name not in cols:
            continue
        series = np.abs(hist[:, cols[name]])
        first, ref, final = series[0], series[:FLUENT_WINDOW].max(), series[-1]
        if not (final > 0 and ref > 0):
            continue
        out["equations"][name] = {
            "initial": float(first), "fluent_reference": float(ref), "final": float(final),
            "ratio_vs_fluent_reference": float(final / ref),
            "orders_vs_fluent_reference": float(-math.log10(final / ref)),
            "ratio_vs_iteration_zero": float(final / first)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs", nargs="+", required=True, help="run directories (globs)")
    ap.add_argument("--limit", type=float, default=None,
                    help="orders every equation must drop; without it, only measure")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    runs = sorted({Path(p) for pattern in args.runs for p in glob.glob(pattern)})
    results = [m for m in (measure(r) for r in runs) if m]
    if not results:
        raise SystemExit(f"no readable run logs in {args.runs}")

    names = [n for n in EQUATIONS if any(n in r["equations"] for r in results)]
    print(f"{len(results)} runs.  Orders dropped, against the first five iterations:\n")
    print(f"{'equation':>10}{'worst':>9}{'median':>9}{'best':>9}{'runs':>7}")
    summary = {}
    for name in names:
        orders = np.array([r["equations"][name]["orders_vs_fluent_reference"]
                           for r in results if name in r["equations"]])
        summary[name] = {"worst": float(orders.min()), "median": float(np.median(orders)),
                         "best": float(orders.max()), "n": int(orders.size)}
        print(f"{name:>10}{orders.min():>9.2f}{np.median(orders):>9.2f}"
              f"{orders.max():>9.2f}{orders.size:>7}")

    report = {"schema": "aeris.s8.equation_convergence.v1",
              "normalisation": "final / max(first 5 iterations), as Fluent scales residuals",
              "summary": summary, "runs": results}
    if args.limit is not None:
        failing = []
        for r in results:
            short = {n: e["orders_vs_fluent_reference"] for n, e in r["equations"].items()
                     if n != "totalRes" and e["orders_vs_fluent_reference"] < args.limit}
            if short:
                failing.append({"run": r["run"], "short_of_limit": short})
        report["limit_orders"] = args.limit
        report["failing"] = failing
        print(f"\n  {len(results) - len(failing)}/{len(results)} runs clear "
              f"{args.limit:g} orders on every equation")
        for f in failing[:12]:
            print(f"    {Path(f['run']).parent.name}/{Path(f['run']).name}: "
                  + ", ".join(f"{k} {v:.2f}" for k, v in sorted(f["short_of_limit"].items())))
    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\n  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
