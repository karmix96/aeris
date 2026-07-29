"""Stage 5 — Shortlist (§ Stage 5). 0 runs.

Chooses the 5 settings Stage 6 will rank. Cost and composed uncertainty come
from the MEASURED Stages 2-4 data (no new solves). Selection is fixed here and
not revised after seeing Stage 6.

Cost model: solve time depends only on vortex count (Stages 2 & 3 both traced
672/1344/2688/5376 -> ~1.35/6.8/23.6/83 s). We fit a power law and prefer
measured medians where a config was actually run.

Composed uncertainty (additive, licensed by Stage 1 separability):
  eps(nc, ns, cs) = eps_stage4(nc, cs at span 2)  +  span_correction(ns)
where eps_stage4 is the Stage 4 worst-key error vs the chord-48 comparator and
span_correction = eps_span(ns) - eps_span(2) from the Stage 3 knee.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
from itertools import product

import common as C
import plots as P

REALIZED_N = 29  # dominant realized section count (Stage 0)


def vortices(nc, ns, N=REALIZED_N):
    return 2 * (N - 1) * ns * nc


# measured (vortices -> median seconds) anchors from Stages 2 & 3
_COST_ANCHORS = [(672, 1.35), (1344, 6.8), (2688, 23.6), (5376, 83.0)]


def cost_seconds(nc, ns):
    v = vortices(nc, ns)
    for va, ta in _COST_ANCHORS:
        if v == va:
            return ta
    # log-log power-law interpolation/extrapolation
    xs = [math.log(a) for a, _ in _COST_ANCHORS]
    ys = [math.log(t) for _, t in _COST_ANCHORS]
    n = len(xs); sx = sum(xs); sy = sum(ys)
    sxx = sum(x * x for x in xs); sxy = sum(x * y for x, y in zip(xs, ys))
    b = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    a = (sy - b * sx) / n
    return math.exp(a + b * math.log(v))


def load_stage4_eps():
    """(chord, cspace) -> worst-key error % (median over geoms), from Stage 4."""
    rows = list(csv.DictReader(open(C.CONFIG_ROOT / "stage4_results.csv")))
    by = {}
    for r in rows:
        if r["ok"] != "True":
            continue
        key = (int(r["chord"]), float(r["cspace"]))
        by.setdefault(key, []).append(float(r["worst_key_err_pct"]))
    return {k: statistics.median(v) for k, v in by.items()}


def load_stage2_eps():
    """chord -> worst-key error % vs chord48 (cspace1.0, span2), from Stage 2."""
    rows = list(csv.DictReader(open(C.CONFIG_ROOT / "stage2_results.csv")))
    KEY_Q = ("cl", "cm", "cd_ind", "cd_total", "x_np")
    # build val[(geom,angle,chord)]
    val = {}
    for r in rows:
        if r["ok"] != "True":
            continue
        val[(r["geom"], float(r["angle"]), int(r["chord"]))] = r
    out = {}
    for nc in (6, 12, 24, 48):
        errs = []
        for (g, a, c), r in val.items():
            if c != nc:
                continue
            r48 = val.get((g, a, 48))
            if not r48:
                continue
            worst = 0.0
            for q in KEY_Q:
                try:
                    x = float(r[q]); y = float(r48[q])
                except (TypeError, ValueError):
                    continue
                if abs(y) < C.NOISE_FLOOR:
                    continue
                worst = max(worst, abs(x - y) / abs(y))
            errs.append(worst * 100)
        out[nc] = statistics.median(errs) if errs else float("nan")
    return out


def load_span_correction():
    """spanwise -> eps_span(ns) - eps_span(2) in %, from the Stage 3 knee."""
    rows = list(csv.DictReader(open(C.CONFIG_ROOT / "stage3_results.csv")))
    KEY_Q = ("cl", "cm", "cd_ind", "cd_total", "x_np")
    val = {}
    for r in rows:
        if r["ok"] != "True":
            continue
        val[(r["geom"], float(r["angle"]), int(r["span"]))] = r
    kneed = {}
    for ns in (1, 2, 4, 8):
        errs = []
        for (g, a, s), r in val.items():
            if s != ns:
                continue
            r8 = val.get((g, a, 8))
            if not r8:
                continue
            worst = 0.0
            for q in KEY_Q:
                try:
                    x = float(r[q]); y = float(r8[q])
                except (TypeError, ValueError):
                    continue
                if abs(y) < C.NOISE_FLOOR:
                    continue
                worst = max(worst, abs(x - y) / abs(y))
            errs.append(worst * 100)
        kneed[ns] = statistics.median(errs) if errs else float("nan")
    base = kneed.get(2, 0.0)
    return {ns: kneed[ns] - base for ns in kneed}


def main():
    s4 = load_stage4_eps()
    s2 = load_stage2_eps()
    span_corr = load_span_correction()

    def eps(nc, ns, cs):
        # eps at span2 from Stage 4 (chord 8-24) or Stage 2 (chord 6/48, cs=1.0)
        if (nc, cs) in s4:
            base = s4[(nc, cs)]
        elif cs == 1.0 and nc in s2:
            base = s2[nc]
        else:
            return None
        corr = span_corr.get(ns, 0.0)
        return max(0.0, base + corr)

    # ---- enumerate every config we can score --------------------------------
    grid = []
    for nc, ns, cs in product((6, 8, 12, 16, 24, 48), (1, 2, 4, 8), (0.0, 0.5, 1.0)):
        if vortices(nc, ns) > C.MAX_VORTICES or 2 * (REALIZED_N - 1) * ns > C.MAX_STRIPS:
            continue
        e = eps(nc, ns, cs)
        if e is None:
            continue
        grid.append({"nchordwise": nc, "spanwise": ns, "cspace": cs,
                     "cost_s": cost_seconds(nc, ns), "eps_pct": e,
                     "vortices": vortices(nc, ns)})

    # ---- the 5 chosen settings (fixed here) --------------------------------
    def cfg(nc, ns, cs, role):
        e = eps(nc, ns, cs)
        return {"nchordwise": nc, "spanwise": ns, "cspace": cs, "role": role,
                "cost_s": round(cost_seconds(nc, ns), 1),
                "eps_pct": round(e, 3) if e is not None else None,
                "vortices": vortices(nc, ns),
                "label": f"c{nc}s{ns}" + ("u" if cs == 0.0 else ("h" if cs == 0.5 else "c"))}

    shortlist = [
        cfg(8, 2, 0.0, "below_knee (expected to fail gate 4)"),
        cfg(12, 2, 0.0, "spanning_knee (cheap)"),
        cfg(16, 2, 0.0, "spanning_knee (mid)"),
        cfg(24, 4, 1.0, "spanning_knee + PRODUCTION default (chord24/span4/cosine)"),
        cfg(48, 2, 1.0, "above_knee COMPARATOR (Stages 2-4 reference; eps=0 in-study)"),
    ]
    # comparator's in-study eps is 0 (it is the reference)
    shortlist[-1]["eps_pct"] = 0.0

    # ---- pareto plot -------------------------------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter([g["cost_s"] for g in grid], [g["eps_pct"] for g in grid],
               c="0.7", s=18)
    for c in shortlist:
        ax.scatter(c["cost_s"], c["eps_pct"], c=P.ACCENT, s=60)
        ax.annotate(c["label"], (c["cost_s"], c["eps_pct"]), color=P.ACCENT,
                    fontsize=8, xytext=(5, 3), textcoords="offset points")
    ax.set_xlabel("median solve seconds"); ax.set_ylabel("composed numerical uncertainty [%]")
    ax.set_title("the five settings taken forward, and why")
    fig.savefig(C.PLOTS_ROOT / "stage5_pareto.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    # ---- write shortlist json ---------------------------------------------
    out = {
        "cost_model": "seconds ~ power-law in vortex count, anchored to Stages 2&3",
        "eps_model": "eps(nc,ns,cs) = stage4_worstkey(nc,cs @ span2) + (eps_span(ns)-eps_span(2))",
        "span_correction_pct": span_corr,
        "stage4_eps_pct": {f"c{k[0]}_cs{k[1]}": v for k, v in s4.items()},
        "stage2_eps_pct": s2,
        "shortlist": shortlist,
        "box_extrapolation_note": (
            "Configs 4 (chord24) and 5 (chord48) lie outside the Stage 1 separability "
            "box (chord 8-16). Approved: Stage 1's interaction index for the mesh-"
            "responsive quantities was <0.06 and Stage 2 confirmed monotone chordwise "
            "convergence to chord 48, so extending separability to chord 24/48 is low "
            "risk. Recorded per §Stage5 / §13 limitation 1."),
        "spacing_finding": (
            "Stages 3-4 show spanwise 2 and UNIFORM spacing dominate at every cost "
            "level, so 4 of 5 configs use (span2, uniform). This is the acceptable "
            "'single spanwise/spacing dominates' outcome the runbook allows, stated "
            "with evidence (Stage 3 knee, Stage 4 grouped bars)."),
    }
    (C.CONFIG_ROOT / "stage5_shortlist.json").write_text(json.dumps(out, indent=2))

    # ---- summary -----------------------------------------------------------
    lines = []; A = lines.append
    A("STAGE 5 — SHORTLIST (0 runs)")
    A("=" * 60)
    A("")
    A("THE FIVE SETTINGS TAKEN FORWARD")
    A(f"   {'#':>2s} {'label':>8s} {'chord':>6s} {'span':>5s} {'spacing':>8s} "
      f"{'cost_s':>7s} {'eps%':>6s}  role")
    sp = {0.0: "uniform", 0.5: "half-cos", 1.0: "cosine"}
    for i, c in enumerate(shortlist, 1):
        A(f"   {i:>2d} {c['label']:>8s} {c['nchordwise']:>6d} {c['spanwise']:>5d} "
          f"{sp[c['cspace']]:>8s} {c['cost_s']:>7.1f} {c['eps_pct']:>6.2f}  {c['role']}")
    A("")
    A("SELECTION RATIONALE")
    A("   1 below the knee, deliberately too cheap (should fail gate 4).")
    A("   2-4 span the knee; 4 is the production default (chord24/span4/cosine).")
    A("   5 is the comparator (chord48/span2/cosine) — the Stages 2-4 reference.")
    A("   Not all share one (span,cspace) pair (4 is span4/cosine).")
    A("")
    A("KEY FINDINGS DRIVING THIS")
    A("   - Chordwise dominates the error budget; spanwise 2 is near-optimal")
    A("     (Stage 3 knee 0.63%). Uniform spacing beats cosine at every chord")
    A("     (Stage 4). Hence the candidates cluster at (span2, uniform).")
    A("   - The production default (chord24/span4/cosine) costs ~%.0fs but its"
      % shortlist[3]["cost_s"])
    A("     spanwise-4 over-resolves a direction that barely matters, while its")
    A("     cosine spacing is the WORST performer. chord16/span2/uniform costs")
    A("     ~%.0fs at ~%.1f%% — a candidate that may beat production on both axes."
      % (shortlist[2]["cost_s"], shortlist[2]["eps_pct"]))
    A("")
    A("BOX EXTRAPOLATION (approved, documented)")
    A("   Configs 4-5 exceed the Stage 1 box (chord 8-16). Approved: interaction")
    A("   index <0.06 on mesh-responsive quantities and monotone chordwise")
    A("   convergence to chord 48 make the extrapolation low risk.")
    A("")
    A("*** STAGE 6 IS THE DECISIVE, EXPENSIVE TEST (540 runs). This shortlist is")
    A("    fixed and will not be revised after seeing Stage 6 results. ***")

    (C.CONFIG_ROOT / "stage5_summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
