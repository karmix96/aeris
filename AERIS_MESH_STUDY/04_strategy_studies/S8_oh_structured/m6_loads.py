"""ONERA M6 sectional normal force, computed against measured.

AUDIT_2026-09-10.md next step 8. The NASA WIND archive publishes pressures only
-- no lift or drag for this case -- so there is no published force to compare
against. But integrating the measured cp around each of the seven stations gives
the sectional normal-force coefficient, cn: a measured LOAD, not just a shape.

Both sides are integrated the same way. CFD sampled at the measured x/c points
carries exactly the experiment's integration error, so its difference from the
experiment is the pressure difference alone. CFD at full resolution shows how
big that integration error is.

    python m6_loads.py --run ../../artifacts/onera_m6/run_L0
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import onera_m6 as m6


def cn(xu, cpu, xl, cpl) -> float:
    """cn = integral over x/c of (cp_lower - cp_upper), trapezoidal, per surface."""
    iu, il = np.argsort(xu), np.argsort(xl)
    return float(np.trapezoid(cpl[il], xl[il]) - np.trapezoid(cpu[iu], xu[iu]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    exp, surf = m6.experiment(), m6.surface_cp(args.run)
    stations, rows = [], []
    print(f"{'stn':>4}{'eta':>7}{'cn exp':>9}{'cn cfd@exp':>12}{'diff':>8}{'cn cfd full':>13}")
    for number, data in exp.items():
        eta = data["eta"]
        sl = m6.station_slice(surf, eta)
        x_le, chord = m6.local_chord(eta)
        xc, cp, up = (sl["x"] - x_le) / chord, sl["cp"], sl["y"] >= 0
        ex, ecp, eu = data["x_over_c"], data["cp"], data["upper"]
        c_exp = cn(ex[eu], ecp[eu], ex[~eu], ecp[~eu])
        sampled = []
        for mask, emask in ((up, eu), (~up, ~eu)):
            o = np.argsort(xc[mask])
            sampled.append(np.interp(ex[emask], xc[mask][o], cp[mask][o]))
        c_at = cn(ex[eu], sampled[0], ex[~eu], sampled[1])
        c_full = cn(xc[up], cp[up], xc[~up], cp[~up])
        stations.append({"station": number, "eta": eta, "chord": chord,
                         "cn_experiment": c_exp, "cn_cfd_at_measured_points": c_at,
                         "cn_cfd_full_resolution": c_full,
                         "difference": c_at - c_exp,
                         "relative_difference": (c_at - c_exp) / c_exp})
        print(f"{number:>4}{eta:>7.2f}{c_exp:>9.4f}{c_at:>12.4f}"
              f"{100 * (c_at - c_exp) / c_exp:>7.1f}%{c_full:>13.4f}")

    # span loading, trapezoidal over the seven stations: cn c against eta, with
    # zero load at the tip. Crude -- the same rule on both sides, so comparable.
    eta = np.array([0.0] + [s["eta"] for s in stations] + [1.0])
    chord = np.array([m6.local_chord(e)[1] for e in eta])

    def span(key):
        values = np.array([stations[0][key]] + [s[key] for s in stations] + [0.0])
        return float(np.trapezoid(values * chord, eta) / np.trapezoid(chord, eta))

    total = {k: span(k) for k in ("cn_experiment", "cn_cfd_at_measured_points",
                                  "cn_cfd_full_resolution")}
    result = json.loads((args.run / "result.json").read_text())
    cl_solver = next((v for k, v in result.get("functions", {}).items()
                      if k.endswith("_cl")), None)
    diffs = np.array([s["relative_difference"] for s in stations])
    report = {"schema": "aeris.s8.onera_m6_loads.v1", "run": str(args.run),
              "solver_overrides": result.get("solver_overrides"),
              "why": "the WIND archive gives cp only; integrated cp is the one measured load",
              "stations": stations, "span_integrated_cn": total,
              "cl_from_solver": cl_solver,
              "summary": {"mean_abs_relative_difference": float(np.mean(np.abs(diffs))),
                          "worst_station": int(stations[int(np.argmax(np.abs(diffs)))]["station"]),
                          "worst_relative_difference": float(diffs[np.argmax(np.abs(diffs))]),
                          "span_integrated_relative_difference":
                              (total["cn_cfd_at_measured_points"] - total["cn_experiment"])
                              / total["cn_experiment"]}}
    out = args.out or (m6.HERE / "reports"
                       / f"s8_onera_m6_loads_{args.run.name}.json")
    out.write_text(json.dumps(report, indent=2) + "\n")
    s = report["summary"]
    print(f"\n  span-integrated cn: experiment {total['cn_experiment']:.4f}  "
          f"CFD {total['cn_cfd_at_measured_points']:.4f} "
          f"({100 * s['span_integrated_relative_difference']:+.1f}%)   solver CL {cl_solver}")
    print(f"  mean |station difference| {100 * s['mean_abs_relative_difference']:.1f}%"
          f"   worst station {s['worst_station']} "
          f"({100 * s['worst_relative_difference']:+.1f}%)\n  wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
