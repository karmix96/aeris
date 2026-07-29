"""Stage 4 — Panel spacing (§ Stage 4).

Does chordwise cosine spacing (LE/TE bunching) help at REDUCED panel counts,
where it matters most? Run at spanwise 2 so the Stage 2 comparator applies
without mixing spanwise error into the spacing comparison.

cspace {0.0 uniform, 0.5 half-cosine, 1.0 full cosine} x chord {8,12,16,24}
x span 2 x geoms 0-3 x angle +4                                    = 48 runs
Comparator: chord 48, span 2, cspace 1.0 (cached from Stage 2).
Reference-neutrality: chord 48, span 2, cspace 0.0 on the same 4 geoms (4 runs).
"""

from __future__ import annotations

import csv
import json
import statistics
from itertools import product

import common as C
import plots as P

CSPACES = (0.0, 0.5, 1.0)
CHORDS = (8, 12, 16, 24)
SPAN = 2
ALPHA = 4.0
SYM, DIFF = 4.0, 4.0
N_GEOM = 4
COMP = dict(nchordwise=48, spanwise=2, cspace=1.0)   # Stage 2 comparator
KEY_Q = ("cl", "cm", "cd_ind", "cd_total", "x_np")
NEUTRAL_PCT = 1.0  # "agree" tolerance for the reference-neutrality check


def rel(a, b):
    return abs(a - b) / abs(b) if b else float("nan")


def worst_key_err(row, comp):
    """Worst relative error over the key quantities, floor-guarded."""
    worst = 0.0
    for q in KEY_Q:
        a, b = row.get(q), comp.get(q)
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            continue
        if abs(b) < C.NOISE_FLOOR:
            continue
        worst = max(worst, rel(a, b))
    return worst


def main():
    geoms = C.convergence_subset(N_GEOM)

    # ---- comparator (cached) ---------------------------------------------- #
    comp = {}
    for gkey, s in geoms:
        comp[gkey] = C.run_case(s, alpha_deg=ALPHA, control_input_deg=SYM,
                                diff_input_deg=DIFF, sample_key=gkey,
                                tag="stage2", **COMP)

    # ---- reference-neutrality: chord48 uniform vs cosine (4 runs) ---------- #
    neutral = {}
    for gkey, s in geoms:
        r0 = C.run_case(s, nchordwise=48, spanwise=2, cspace=0.0, alpha_deg=ALPHA,
                        control_input_deg=SYM, diff_input_deg=DIFF,
                        sample_key=gkey, tag="stage4_refneutral")
        neutral[gkey] = worst_key_err(r0, comp[gkey]) * 100.0
    max_neutral = max(neutral.values())
    neutral_ok = max_neutral < NEUTRAL_PCT

    # ---- main grid -------------------------------------------------------- #
    total = len(CSPACES) * len(CHORDS) * len(geoms)
    print(f"Stage 4: {total} runs + 4 comparator + 4 reference-neutrality "
          f"[serial]", flush=True)
    data = {}
    n_new = n_hit = n_fail = 0
    i = 0
    for (gkey, s), cs, nc in product(geoms, CSPACES, CHORDS):
        i += 1
        r = C.run_case(s, nchordwise=nc, spanwise=SPAN, cspace=cs, alpha_deg=ALPHA,
                       control_input_deg=SYM, diff_input_deg=DIFF,
                       sample_key=gkey, tag="stage4")
        data[(gkey, cs, nc)] = r
        n_hit += bool(r.get("cache_hit"))
        n_new += bool(r.get("ok") and not r.get("cache_hit"))
        n_fail += (not r.get("ok"))

    # ---- error vs comparator, per (chord, spacing) ------------------------- #
    err = {}   # (cs, nc) -> worst-key error % (median over geoms)
    for cs, nc in product(CSPACES, CHORDS):
        vals = []
        for gkey, _s in geoms:
            r = data.get((gkey, cs, nc))
            if r and r.get("ok"):
                vals.append(worst_key_err(r, comp[gkey]) * 100.0)
        err[(cs, nc)] = statistics.median(vals) if vals else float("nan")

    # ---- plot: grouped bars ----------------------------------------------- #
    labels = {0.0: "uniform", 0.5: "half-cosine", 1.0: "full cosine"}
    series = {labels[cs]: [err[(cs, nc)] for nc in CHORDS] for cs in CSPACES}
    P.grouped_bars(list(CHORDS), series, xlabel="chordwise panels",
                   ylabel="worst key-quantity error [%] vs chord-48 comparator",
                   title="does cosine spacing help at low panel counts?",
                   path=C.PLOTS_ROOT / "stage4_spacing.png")

    # ---- CSV + summary ---------------------------------------------------- #
    with open(C.CONFIG_ROOT / "stage4_results.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["geom", "cspace", "chord", "ok", "worst_key_err_pct"]
                   + list(C.QUANTITY_FIELDS))
        for (gkey, cs, nc), r in data.items():
            w.writerow([gkey, cs, nc, r.get("ok"),
                        worst_key_err(r, comp[gkey]) * 100.0 if r.get("ok") else None]
                       + [r.get(q) for q in C.QUANTITY_FIELDS])

    lines = []; A = lines.append
    A("STAGE 4 — PANEL SPACING")
    A("=" * 60)
    A(f"1. RUN: {total} main + 4 comparator + 4 reference-neutrality. "
      f"new={n_new} hits={n_hit} fails={n_fail}")
    A(f"   (all cspace=1.0 cells were cached from Stages 1-2.)")
    A("")
    A(f"2. FAILURES: {n_fail}")
    A("")
    A("3. REFERENCE-NEUTRALITY (chord48 uniform vs cosine, worst key-quantity)")
    for gkey, _s in geoms:
        A(f"   {gkey}: {neutral[gkey]:.3f}%")
    A(f"   max = {max_neutral:.3f}%  -> {'NEUTRAL (comparator is spacing-independent)' if neutral_ok else 'NOT NEUTRAL — STOP'}")
    A("")
    A("4. ERROR vs COMPARATOR, median over 4 geoms  [% worst key-quantity]")
    A(f"   {'chord':>6s} " + " ".join(f"{labels[cs]:>12s}" for cs in CSPACES))
    for nc in CHORDS:
        A(f"   {nc:>6d} " + " ".join(f"{err[(cs,nc)]:>12.3f}" for cs in CSPACES))
    A("")
    # which spacing wins per chord?
    A("5. BEST SPACING PER CHORD")
    for nc in CHORDS:
        best = min(CSPACES, key=lambda cs: err[(cs, nc)])
        A(f"   chord {nc:>2d}: {labels[best]} (err {err[(best,nc)]:.3f}%)")
    A("")
    A("6. WHAT THIS MEANS")
    A("   Established at spanwise 2 and carried to other spanwise counts under the")
    A("   Stage 1 separability result. If cosine spacing lowers the error at low")
    A("   chord counts, the shortlist should adopt it there; if the three spacings")
    A("   are within noise, spacing is not a lever and cspace can stay at 1.0.")

    (C.CONFIG_ROOT / "stage4_summary.txt").write_text("\n".join(lines) + "\n")
    if not neutral_ok:
        A("")
        A("*** STOP: reference-neutrality failed; spacing is not separable from")
        A("    convergence. Stage design needs revisiting (§ Stage 4).")
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
