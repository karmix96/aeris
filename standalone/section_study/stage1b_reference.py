"""Stage 1b — CORRECTED reference legitimacy + placement-error spectrum.

Correction vs Stage 1: legitimacy is Richardson convergence of DENSE UNIFORM in
N (the reference), NOT cross-placement neutrality. Adaptive/clustered deliberately
stay non-uniform, so requiring them to match a dense uniform was wrong — it
measured the placement EFFECT (a result), not reference legitimacy.

Runs at c8s1u (cheap mesh: separability-verified that the placement effect is
panel-mesh-independent, so the section-placement policy transfers to c16s2u).
Reference = uniform-201. Legitimacy = |uniform201 - uniform151| < 0.5%.
Then reports each candidate's error vs the reference (the placement spectrum).
"""
from __future__ import annotations

import json
import sys

import common_sections as C

NCH, SPW = 8, 1
N_REF = 201
RICH = (101, 151, 201)
CAND_N = (25, 49)
ANGLES = (-2.0, 0.0, 4.0)
SCALE = {"cl": 0.195025, "cm": 0.10417, "cd_ind": 0.00355085, "cd_total": 0.0103324,
         "x_np": 0.306318, "elevon_sym.CL": 0.010146, "elevon_sym.Cm": 0.00701,
         "elevon_diff.Cl": 0.002594, "hinge_moments.elevon_sym": 0.0002872}
KEY = tuple(SCALE)
WORKERS = 4


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "subset"
    designs = (C.normal_samples() + C.extreme_samples()) if which == "all" \
        else C.convergence_subset(8)
    keys = [k for k, _ in designs]

    cases = []
    for k in keys:
        for a in ANGLES:
            for N in RICH:
                cases.append(dict(sample_key=k, n_sections=N, policy="uniform",
                                  alpha_deg=a, tag="s1b_ref"))
            for N in CAND_N:
                for pol in ("uniform", "adaptive"):
                    cases.append(dict(sample_key=k, n_sections=N, policy=pol,
                                      alpha_deg=a, tag="s1b_cand"))
    # mesh override carried through the worker via extra keys
    for c in cases:
        c["nchord"] = NCH; c["spanw"] = SPW
    print(f"Stage 1b: {len(designs)} designs, {len(cases)} cases @ c8s1u", flush=True)
    C.parallel_by_design(cases, workers=WORKERS, tag="s1b")

    def g(k, pol, N, a, q):
        r = C._collect_one(k, pol, N, a, NCH, SPW)
        return r.get(q) if r and r.get("ok") else None

    def relerr(v, ref, q):
        if v is None or ref is None:
            return None
        return abs(v - ref) / max(abs(ref), 0.1 * SCALE[q]) * 100.0

    legit = {}; spectrum = {}
    for k in keys:
        # legitimacy: uniform 151 vs 201
        wl = 0.0; wwhere = None
        for a in ANGLES:
            for q in KEY:
                v1 = g(k, "uniform", 151, a, q); v2 = g(k, "uniform", 201, a, q)
                e = relerr(v1, v2, q)
                if e is not None and e > wl:
                    wl = e; wwhere = (a, q)
        legit[k] = {"richardson_pct": round(wl, 3), "where": wwhere, "pass": wl < 0.5}
        # placement spectrum: candidate uniform-25 and adaptive-25 vs uniform-201
        sp = {}
        for pol in ("uniform", "adaptive"):
            for q in KEY:
                worst = 0.0
                for a in ANGLES:
                    e = relerr(g(k, pol, 25, a, q), g(k, "uniform", N_REF, a, q), q)
                    if e is not None:
                        worst = max(worst, e)
                sp[f"{pol}:{q}"] = round(worst, 3)
        spectrum[k] = sp

    g1 = all(v["pass"] for v in legit.values())
    (C.CONFIG_ROOT / f"stage1b_{which}.json").write_text(json.dumps(
        {"mesh": "c8s1u", "N_ref": N_REF, "legit": legit, "spectrum": spectrum,
         "G1_richardson_pass": g1}, indent=2))

    L = []; A = L.append
    A(f"STAGE 1b — CORRECTED REFERENCE LEGITIMACY ({which}, c8s1u, N_ref={N_REF})")
    A("=" * 66)
    A(f"Legitimacy = dense-uniform Richardson |N201-N151| < 0.5%: "
      f"{'PASS' if g1 else 'FAIL'} on all {len(keys)} designs")
    A(f"  worst uniform Richardson band: "
      f"{max(v['richardson_pct'] for v in legit.values()):.3f}%")
    A("")
    A("PLACEMENT-ERROR SPECTRUM vs converged reference (worst over angles), "
      "uniform-25 -> adaptive-25:")
    A(f"  {'quantity':>26s} {'uni25%':>8s} {'ada25%':>8s}   verdict")
    for q in KEY:
        us = [spectrum[k][f"uniform:{q}"] for k in keys]
        as_ = [spectrum[k][f"adaptive:{q}"] for k in keys]
        um = max(us); am = max(as_)
        verdict = ("adaptive better" if am < um - 0.1 else
                   "uniform better" if um < am - 0.1 else "tie")
        A(f"  {q:>26s} {um:8.3f} {am:8.3f}   {verdict}")
    A("")
    A("READ: quantities where worst-case < 1% at uniform-25 are section-EASY;")
    A("those that stay high (cd_ind, hinge) are section-sensitive — the ones a")
    A("placement policy must earn its keep on.")
    (C.CONFIG_ROOT / f"stage1b_summary_{which}.txt").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
