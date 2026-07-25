"""Two gaps Mike's challenge exposed in the Task 3 study.

GAP 1 — sideslip was excluded too broadly.
    Task 3 compared symmetric cases only, justified by the AeroSandbox path having
    no differential-elevon degree of freedom. That justifies excluding da != 0. It
    does NOT justify excluding beta != 0 with da = 0, which is a perfectly valid
    comparison and is the only way to exercise CYb, Clb, Cnb, Clr, Cnr, CYp, Cnp
    with real (non-zero-by-symmetry) signal. Run it DoE-wide.

GAP 2 — "the native elevon extent is correct" was asserted, not proved.
    Differing from AeroSandbox at 25 sections does not establish which is right.
    The decisive test is the ASYMPTOTE: refine the section count and see whether
    the two paths converge to the SAME limit (then it is only discretisation) or
    to DIFFERENT limits (then one is geometrically wrong).

Usage:
    python standalone/lowfi_avl_study/probe_beta_and_elevon_asymptote.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data" / "lowfi_avl_study" / "beta_and_elevon_asymptote"

ALPHA = 6.0
BETA = 4.0
VELOCITY = 28.0
BETA_SEEDS = [7000 + i for i in range(12)]
ASYMPTOTE_SEEDS = [7000, 7005]
ASYMPTOTE_LEVELS = [13, 17, 25, 33, 49, 65]
ELEVON_DEG = 6.0

LATERAL = ["CYb", "Clb", "Cnb", "Clp", "Clr", "Cnr", "CYp", "Cnp", "CYr"]


def rel(a, b):
    if a is None or b is None:
        return None
    d = max(abs(a), abs(b))
    return 0.0 if d < 1e-12 else abs(a - b) / d


def main() -> None:
    from aeris.aero.models import FlightCondition
    from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
        build_pygeo_sections_from_config,
        run_pygeo_avl_case,
        run_pygeo_native_avl_case,
    )

    OUT.mkdir(parents=True, exist_ok=True)
    config = REPO / "configs" / "geometry" / "bwb.yaml"
    report: dict = {}

    # ================= GAP 1: beta != 0, da = 0 comparison =================
    beta_rows = []
    for seed in BETA_SEEDS:
        ex, semi, meta = build_pygeo_sections_from_config(config, n_sections=25, seed=seed)
        fc = FlightCondition(alpha_deg=ALPHA, beta_deg=BETA, velocity_mps=VELOCITY,
                             altitude_m=0.0)
        n = run_pygeo_native_avl_case(
            flight_condition=fc, output_dir=OUT / f"beta_s{seed}_n",
            extracted_sections=ex, semispan_m=semi, control=meta["control"],
            control_input_deg=0.0, diff_input_deg=0.0, viscous=True, name="n")
        a = run_pygeo_avl_case(
            flight_condition=fc, output_dir=OUT / f"beta_s{seed}_a",
            extracted_sections=ex, semispan_m=semi, control=meta["control"],
            viscous=True, name="a",
            paneling={"spanwise_resolution": 4, "chordwise_resolution": 8},
            control_input_deg=0.0, diff_input_deg=0.0)
        row = {"seed": seed,
               "CY": {"n": n.cy, "a": a.cy, "rel": rel(n.cy, a.cy)},
               "Cl_roll": {"n": n.cl_roll, "a": a.cl_roll,
                           "rel": rel(n.cl_roll, a.cl_roll)},
               "Cn": {"n": n.cn, "a": a.cn, "rel": rel(n.cn, a.cn)},
               "CL": {"n": n.cl, "a": a.cl, "rel": rel(n.cl, a.cl)}}
        for k in LATERAL:
            nv = (n.stability_axis_derivatives or {}).get(k)
            av = (a.stability_axis_derivatives or {}).get(k)
            row[k] = {"n": nv, "a": av, "rel": rel(nv, av)}
        beta_rows.append(row)
        print(f"beta seed {seed}: CY rel={row['CY']['rel']:.2e} "
              f"Clb rel={row['Clb']['rel']:.2e}")

    summary = {}
    for k in ["CY", "Cl_roll", "Cn", "CL"] + LATERAL:
        vals = [r[k]["rel"] for r in beta_rows if r[k]["rel"] is not None]
        mags = [max(abs(r[k]["n"] or 0), abs(r[k]["a"] or 0)) for r in beta_rows]
        keep = [v for v, m in zip(vals, mags) if m > 1e-6]
        if keep:
            summary[k] = {"n": len(keep), "median": float(np.median(keep)),
                          "max": float(np.max(keep)),
                          "median_magnitude": float(np.median([m for m in mags if m > 1e-6]))}
    report["gap1_beta"] = {"beta_deg": BETA, "alpha_deg": ALPHA,
                           "n_seeds": len(BETA_SEEDS),
                           "summary": summary, "rows": beta_rows}

    # ============ GAP 2: elevon asymptote — same limit or different? ========
    asym: dict = {}
    for seed in ASYMPTOTE_SEEDS:
        per_level = {}
        for nsec in ASYMPTOTE_LEVELS:
            ex, semi, meta = build_pygeo_sections_from_config(
                config, n_sections=nsec, seed=seed)
            fc = FlightCondition(alpha_deg=ALPHA, beta_deg=0.0,
                                 velocity_mps=VELOCITY, altitude_m=0.0)
            n = run_pygeo_native_avl_case(
                flight_condition=fc, output_dir=OUT / f"as_s{seed}_n{nsec}_n",
                extracted_sections=ex, semispan_m=semi, control=meta["control"],
                control_input_deg=ELEVON_DEG, diff_input_deg=0.0,
                viscous=False, name="n")
            a = run_pygeo_avl_case(
                flight_condition=fc, output_dir=OUT / f"as_s{seed}_n{nsec}_a",
                extracted_sections=ex, semispan_m=semi, control=meta["control"],
                viscous=False, name="a",
                paneling={"spanwise_resolution": 4, "chordwise_resolution": 8},
                control_input_deg=ELEVON_DEG, diff_input_deg=0.0)
            n_cd = next(iter(n.control_derivatives.values()), {})
            a_raw = (a.raw_outputs or {}).get("_stability_file_parsed", {}) or {}
            per_level[nsec] = {
                "n_sections_actual": n.n_sections,
                "CL_native": n.cl, "CL_asb": a.cl,
                "dCL": (a.cl - n.cl) if (a.cl and n.cl) else None,
                "CLde_native": n_cd.get("CL"), "CLde_asb": a_raw.get("CLd01"),
                "Cmde_native": n_cd.get("Cm"), "Cmde_asb": a_raw.get("Cmd01"),
            }
            print(f"asymptote seed {seed} n={nsec}: dCL={per_level[nsec]['dCL']}")
        asym[seed] = per_level
    report["gap2_elevon_asymptote"] = {"elevon_deg": ELEVON_DEG,
                                       "levels": ASYMPTOTE_LEVELS, "data": asym}

    (OUT / "beta_and_asymptote.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")

    # ---- report ------------------------------------------------------------
    L = [f"GAP 1 — sideslip comparison (alpha={ALPHA} deg, beta={BETA} deg, "
         f"da=0, {len(BETA_SEEDS)} DoE seeds)",
         "The lateral derivatives now carry real signal, so these relative errors",
         "are meaningful (unlike beta=0 where they are ~0 by symmetry).", "",
         f"{'field':<10}{'n':>4}{'med |val|':>12}{'median rel':>12}{'max rel':>12}"]
    for k, s in summary.items():
        L.append(f"{k:<10}{s['n']:>4}{s['median_magnitude']:>12.2e}"
                 f"{s['median']:>12.2e}{s['max']:>12.2e}")

    L += ["", "", f"GAP 2 — elevon asymptote (de={ELEVON_DEG} deg, inviscid).",
          "Same limit => discretisation only. Different limits => one path is",
          "geometrically wrong.", ""]
    for seed, per_level in asym.items():
        L.append(f"=== seed {seed} ===")
        L.append(f"{'n_sec':>6}{'CLde native':>14}{'CLde asb':>12}"
                 f"{'ratio a/n':>11}{'dCL':>11}")
        for nsec, r in per_level.items():
            ratio = (r["CLde_asb"] / r["CLde_native"]
                     if r["CLde_asb"] and r["CLde_native"] else float("nan"))
            L.append(f"{nsec:>6}{r['CLde_native']:>14.6f}{r['CLde_asb']:>12.6f}"
                     f"{ratio:>11.4f}{(r['dCL'] or float('nan')):>11.6f}")
        finest = per_level[ASYMPTOTE_LEVELS[-1]]
        coarse = per_level[ASYMPTOTE_LEVELS[0]]
        L.append(f"  native CLde {coarse['CLde_native']:.6f} -> {finest['CLde_native']:.6f}"
                 f"  ({100 * abs(finest['CLde_native'] - coarse['CLde_native']) / abs(finest['CLde_native']):.2f}% change)")
        L.append(f"  asb    CLde {coarse['CLde_asb']:.6f} -> {finest['CLde_asb']:.6f}"
                 f"  ({100 * abs(finest['CLde_asb'] - coarse['CLde_asb']) / abs(finest['CLde_asb']):.2f}% change)")
        r_fin = finest["CLde_asb"] / finest["CLde_native"]
        L.append(f"  ratio at the finest level = {r_fin:.4f}   => "
                 f"{'SAME limit (discretisation only)' if abs(r_fin - 1) < 0.01 else 'DIFFERENT limits (a real geometry difference)'}")
        L.append("")

    text = "\n".join(L)
    print("\n" + text)
    (OUT / "beta_and_asymptote.txt").write_text(text + "\n", encoding="utf-8")
    print(f"\nwrote {OUT / 'beta_and_asymptote.json'}")


if __name__ == "__main__":
    main()
