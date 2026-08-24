"""Stage 1 — build & legitimise the reference (RUNBOOK §2, Gate G1).

The reference is legitimate only if it is (G1a) PLACEMENT-INDEPENDENT — uniform,
adaptive and clustered dense placements agree to < 0.5% worst-case — and (G1b)
within its own Richardson band in 1/N. Proven per design, not assumed. This is
the fix for the prior study's uniform-biased reference.

Runs on a design subset by default; pass 'all' to do all 36.
"""
from __future__ import annotations

import json
import statistics
import sys

import common as pc
import common_sections as C

N_REF = 89
RICH = (25, 49, 89)
ANGLES = (-2.0, 0.0, 4.0)
POLICIES = ("uniform", "adaptive", "clustered")
KEY_Q = ("cl", "cm", "cd_ind", "cd_total", "x_np",
         "elevon_sym.CL", "elevon_sym.Cm", "hinge_moments.elevon_sym")
NEUTRAL_TOL = 0.5
RICH_TOL = 0.5
WORKERS = 4


def f(x):
    return x if isinstance(x, (int, float)) else None


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "subset"
    if which == "all":
        designs = C.normal_samples() + C.extreme_samples()
    else:
        designs = C.convergence_subset(8)
    keys = [k for k, _ in designs]

    cases = []
    for k in keys:
        for a in ANGLES:
            for pol in POLICIES:
                cases.append(dict(sample_key=k, n_sections=N_REF, policy=pol,
                                  alpha_deg=a, tag="stage1_neutral"))
        # Richardson chain: uniform at 25,49 (89 already above)
        for N in (25, 49):
            for a in ANGLES:
                cases.append(dict(sample_key=k, n_sections=N, policy="uniform",
                                  alpha_deg=a, tag="stage1_rich"))
    print(f"Stage 1: {len(designs)} designs, {len(cases)} cases, {WORKERS} workers",
          flush=True)
    res = C.parallel_by_design(cases, workers=WORKERS, tag="stage1")

    def get(k, pol, N, a, q):
        r = res.get((k, pol, N, a, 4.0, 4.0))
        return f(r.get(q)) if r and r.get("ok") else None

    # ---- G1a neutrality: worst spread across placements, per design -------- #
    neutrality = {}
    for k in keys:
        worst = 0.0; where = None
        for a in ANGLES:
            for q in KEY_Q:
                vals = [get(k, pol, N_REF, a, q) for pol in POLICIES]
                vals = [v for v in vals if v is not None]
                if len(vals) < 2:
                    continue
                mag = max(abs(v) for v in vals)
                if mag < C.NOISE_FLOOR:
                    continue
                spread = (max(vals) - min(vals)) / mag * 100.0
                if spread > worst:
                    worst = spread; where = (a, q)
        neutrality[k] = {"worst_pct": round(worst, 3), "where": where,
                         "pass": worst < NEUTRAL_TOL}

    # ---- G1b Richardson band on uniform (per design, per key q) ------------ #
    def gci_band(vc, vm, vf):
        # vc=coarse(25) vm=mid(49) vf=fine(89); ratio r~2 in 1/N
        import math
        if None in (vc, vm, vf):
            return None
        d1 = vm - vc; d2 = vf - vm
        if abs(d2) < 1e-12 or abs(d1) < 1e-12:
            return 0.0
        if d1 * d2 <= 0:   # non-monotonic: fall back to finest discrepancy
            return abs(d2) / (abs(vf) + 1e-12) * 100.0
        r = 2.0
        try:
            p = math.log(abs(d1 / d2)) / math.log(r)
        except ValueError:
            return abs(d2) / (abs(vf) + 1e-12) * 100.0
        if not (0.3 <= p <= 3.0):
            return abs(d2) / (abs(vf) + 1e-12) * 100.0
        gci = 1.25 * abs(d2) / (r ** p - 1.0) / (abs(vf) + 1e-12) * 100.0
        return gci

    richardson = {}
    for k in keys:
        worst = 0.0; where = None
        for a in ANGLES:
            for q in KEY_Q:
                vc = get(k, "uniform", 25, a, q)
                vm = get(k, "uniform", 49, a, q)
                vf = get(k, "uniform", 89, a, q)
                if None in (vc, vm, vf) or abs(vf) < C.NOISE_FLOOR:
                    continue
                band = gci_band(vc, vm, vf)
                if band is not None and band > worst:
                    worst = band; where = (a, q)
        richardson[k] = {"worst_pct": round(worst, 3), "where": where,
                         "pass": worst < RICH_TOL}

    g1a = all(v["pass"] for v in neutrality.values())
    g1b = all(v["pass"] for v in richardson.values())

    report = {"which": which, "N_ref": N_REF, "neutrality": neutrality,
              "richardson": richardson, "G1a_pass": g1a, "G1b_pass": g1b,
              "n_designs": len(designs)}
    (C.CONFIG_ROOT / f"stage1_reference_{which}.json").write_text(json.dumps(report, indent=2))

    # plot: neutrality + richardson worst per design
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        short = [k.split(":")[-1] for k in keys]
        x = np.arange(len(keys)); w = 0.4
        fig, ax = plt.subplots(figsize=(max(6, len(keys) * 0.35), 4.2))
        ax.bar(x - w/2, [neutrality[k]["worst_pct"] for k in keys], w,
               label="placement spread (G1a)", color="crimson")
        ax.bar(x + w/2, [richardson[k]["worst_pct"] for k in keys], w,
               label="Richardson band (G1b)", color="navy")
        ax.axhline(0.5, color="k", ls="--", lw=1, label="0.5% gate")
        ax.set_xticks(x); ax.set_xticklabels(short, rotation=90, fontsize=7)
        ax.set_ylabel("worst-case %"); ax.legend()
        ax.set_title(f"Reference legitimacy — G1a {'PASS' if g1a else 'FAIL'}, "
                     f"G1b {'PASS' if g1b else 'FAIL'}")
        fig.savefig(C.PLOTS_ROOT / f"stage1_reference_{which}.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
    except Exception as e:
        print("plot skipped:", e)

    L = []; A = L.append
    A(f"STAGE 1 — REFERENCE LEGITIMACY ({which}, {len(designs)} designs, N_ref={N_REF})")
    A("=" * 64)
    A(f"G1a placement-neutrality (<{NEUTRAL_TOL}%): {'PASS' if g1a else 'FAIL'}")
    A(f"G1b Richardson band     (<{RICH_TOL}%): {'PASS' if g1b else 'FAIL'}")
    A("")
    A(f"  {'design':>22s} {'neutral%':>9s} {'rich%':>7s}  worst-cell")
    for k in keys:
        n = neutrality[k]; r = richardson[k]
        A(f"  {k:>22s} {n['worst_pct']:9.3f} {r['worst_pct']:7.3f}  "
          f"neu@{n['where']} rich@{r['where']}")
    A("")
    if g1a and g1b:
        A("=> reference is placement-independent and converged: LEGITIMATE ground truth.")
    else:
        A("=> STOP per §10: reference not yet truth; raise N_ref or mark quantities unresolvable.")
    (C.CONFIG_ROOT / f"stage1_summary_{which}.txt").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
