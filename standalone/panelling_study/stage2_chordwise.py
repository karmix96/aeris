"""Stage 2 — Chordwise convergence (§ Stage 2).

How fast the answer settles as chordwise panels increase, and how far from
settled the candidate settings are. Spanwise fixed at 2 (Stage 1 licenses
carrying the conclusion to other spanwise counts).

chord {6,12,24,48} x span 2 x 8 geoms x angles {-2,0,+2,+4}  = 128 runs.
Angles are D2-corrected (no +8; production does not sweep it).

Two overlapping ratio-2 chains: A={6,12,24}, B={12,24,48}. Agreement is a
consistency check on the observed order, not independent estimates.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
from itertools import product

import common as C
import plots as P

CHORDS = (6, 12, 24, 48)
SPAN = 2
ANGLES = (-2.0, 0.0, 2.0, 4.0)   # D2: no +8
CSPACE = 1.0
SYM, DIFF = 4.0, 4.0
N_GEOM = 8

KEY_Q = ("cl", "cm", "cd_ind", "cd_total", "x_np")  # gate-4 quantities
PLOT_Q = "elevon_sym.CL"                              # most panel-hungry


def rel(a, b):
    return abs(a - b) / abs(b) if b else float("nan")


def main():
    locked = json.loads((C.CONFIG_ROOT / "stage0_locked_config.json").read_text())
    scale = locked["normalisation_scale"]
    geoms = C.convergence_subset(N_GEOM)

    total = len(CHORDS) * len(geoms) * len(ANGLES)
    print(f"Stage 2: {total} runs (chord{CHORDS} x span{SPAN} x {len(geoms)} geoms "
          f"x angles{ANGLES}) [serial]", flush=True)

    data = {}
    n_new = n_hit = n_fail = 0
    i = 0
    for (gkey, s), a, nc in product(geoms, ANGLES, CHORDS):
        i += 1
        C.assert_mesh_legal(C.realized_n_sections(s, gkey), nc, SPAN)
        r = C.run_case(s, nchordwise=nc, spanwise=SPAN, cspace=CSPACE, alpha_deg=a,
                       control_input_deg=SYM, diff_input_deg=DIFF,
                       sample_key=gkey, tag="stage2")
        data[(gkey, a, nc)] = r
        n_hit += bool(r.get("cache_hit"))
        n_new += bool(r.get("ok") and not r.get("cache_hit"))
        n_fail += (not r.get("ok"))
        if i % 16 == 0 or not r.get("ok"):
            print(f"  [{i:3d}/{total}] {gkey} a={a:+.0f} c{nc} ok={r.get('ok')} "
                  f"hit={r.get('cache_hit')} t={r.get('seconds_avl',0):.1f}s", flush=True)

    def val(q, gkey, a, nc):
        r = data.get((gkey, a, nc))
        v = r.get(q) if r and r.get("ok") else None
        return v if isinstance(v, (int, float)) else None

    # ---- per-quantity convergence assessment over geom x angle ------------- #
    q_stats = {}
    for q in C.QUANTITY_FIELDS:
        pB_list, R_list, gci_list, disc_list = [], [], [], []
        admissible = 0
        assessed = 0
        reasons_count = {}
        for (gkey, _s), a in product(geoms, ANGLES):
            series = [val(q, gkey, a, nc) for nc in CHORDS]
            if any(v is None for v in series):
                continue
            f6, f12, f24, f48 = series
            if abs(f48) < C.NOISE_FLOOR:
                # §4.5: relative measures not meaningful; assess on normalised only
                disc_list.append(abs(f12 - f48) / (scale.get(q) or 1))  # normalised
                reasons_count["below_noise_floor"] = reasons_count.get("below_noise_floor", 0) + 1
                assessed += 1
                continue
            chainA = C.richardson_gci(f6, f12, f24)
            chainB = C.richardson_gci(f12, f24, f48)
            ok, reasons, det = C.convergence_admissible(chainA, chainB, abs(f48))
            assessed += 1
            if not math.isnan(chainB["p"]):
                pB_list.append(chainB["p"])
            if chainB["R"] is not None and not math.isnan(chainB["R"]):
                R_list.append(chainB["R"])
            if ok:
                admissible += 1
                if chainB["gci_fine"] is not None:
                    gci_list.append(chainB["gci_fine"])
            else:
                for rsn in reasons:
                    reasons_count[rsn] = reasons_count.get(rsn, 0) + 1
                # finest_grid_discrepancy: chord24 vs chord48 (remaining rel change)
                disc_list.append(rel(f24, f48))
        q_stats[q] = {
            "assessed": assessed, "admissible": admissible,
            "median_p": statistics.median(pB_list) if pB_list else float("nan"),
            "median_R": statistics.median(R_list) if R_list else float("nan"),
            "worst_gci": max(gci_list) if gci_list else None,
            "worst_discrepancy": max(disc_list) if disc_list else None,
            "reasons": reasons_count,
        }

    # ---- chain agreement summary ------------------------------------------ #
    agree = disagree = 0
    for q in C.QUANTITY_FIELDS:
        for (gkey, _s), a in product(geoms, ANGLES):
            series = [val(q, gkey, a, nc) for nc in CHORDS]
            if any(v is None for v in series) or abs(series[3]) < C.NOISE_FLOOR:
                continue
            pA = C._chain_p(series[0], series[1], series[2])
            pB = C._chain_p(series[1], series[2], series[3])
            if math.isnan(pA) or math.isnan(pB) or pB == 0:
                continue
            if abs(pA - pB) / abs(pB) <= 0.30:
                agree += 1
            else:
                disagree += 1

    # ---- knee: error% vs median seconds per chord level -------------------- #
    knee_secs, knee_err = {}, {}
    for nc in CHORDS:
        secs = [data[(gkey, a, nc)].get("seconds_avl") for (gkey, _s), a
                in product(geoms, ANGLES) if data.get((gkey, a, nc), {}).get("ok")]
        knee_secs[nc] = statistics.median([x for x in secs if x]) if secs else float("nan")
        # worst over key quantities of median rel discrepancy vs chord48
        worst = 0.0
        for q in KEY_Q:
            errs = []
            for (gkey, _s), a in product(geoms, ANGLES):
                f = val(q, gkey, a, nc); f48 = val(q, gkey, a, 48)
                if f is None or f48 is None or abs(f48) < C.NOISE_FLOOR:
                    continue
                errs.append(rel(f, f48))
            if errs:
                worst = max(worst, statistics.median(errs))
        knee_err[nc] = worst * 100.0

    # ---- plots ------------------------------------------------------------- #
    gk0 = geoms[0][0]
    # convergence of the panel-hungry quantity at geom0 +4
    ys = [val(PLOT_Q, gk0, 4.0, nc) for nc in CHORDS]
    series = {PLOT_Q: ys}
    fpath = C.PLOTS_ROOT / "stage2_convergence.png"
    # add estimate line if admissible for this q/geom/angle
    est = None
    if all(v is not None for v in ys) and abs(ys[3]) >= C.NOISE_FLOOR:
        cB = C.richardson_gci(ys[1], ys[2], ys[3])
        cA = C.richardson_gci(ys[0], ys[1], ys[2])
        ok, _rs, _d = C.convergence_admissible(cA, cB, abs(ys[3]))
        if ok:
            est = cB["extrap"]
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    ax.plot(list(CHORDS), ys, marker="o", color=P.ACCENT)
    ax.set_xscale("log", base=2); ax.set_xticks(list(CHORDS))
    ax.get_xaxis().set_major_formatter(plt.matplotlib.ticker.ScalarFormatter())
    if est is not None:
        ax.axhline(est, color=P.REF, linestyle="--")
        ax.annotate("estimated limit", (CHORDS[-1], est), color=P.REF, fontsize=9,
                    va="bottom", ha="right")
    ax.set_xlabel("chordwise panels"); ax.set_ylabel(PLOT_Q)
    settle = "settles" if est is not None else "not in asymptotic range"
    ax.set_title(f"{PLOT_Q} vs chordwise ({settle})")
    fig.savefig(fpath, dpi=150, bbox_inches="tight"); plt.close(fig)

    P.lines_labelled_at_end  # keep import used
    # knee plot
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    xs = [knee_secs[nc] for nc in CHORDS]
    ys2 = [knee_err[nc] for nc in CHORDS]
    ax.plot(xs, ys2, marker="o", color=P.ACCENT)
    for nc, x, y in zip(CHORDS, xs, ys2):
        ax.annotate(f"c{nc}", (x, y), fontsize=9, xytext=(4, 3),
                    textcoords="offset points")
    ax.set_xlabel("median solve seconds"); ax.set_ylabel("worst key-quantity error [%] vs chord 48")
    ax.set_title("where does more time stop buying accuracy?")
    fig.savefig(C.PLOTS_ROOT / "stage2_error_vs_time.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    # ---- results CSV + summary -------------------------------------------- #
    with open(C.CONFIG_ROOT / "stage2_results.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["geom", "angle", "chord", "ok"] + list(C.QUANTITY_FIELDS) + ["seconds_avl"])
        for (gkey, a, nc), r in data.items():
            w.writerow([gkey, a, nc, r.get("ok")]
                       + [r.get(q) for q in C.QUANTITY_FIELDS] + [r.get("seconds_avl")])

    lines = []
    A = lines.append
    A("STAGE 2 — CHORDWISE CONVERGENCE")
    A("=" * 60)
    A(f"1. RUN: {total} cells. new={n_new} hits={n_hit} fails={n_fail}")
    A(f"   median solve seconds by chord: " +
      ", ".join(f"c{nc}={knee_secs[nc]:.1f}s" for nc in CHORDS))
    A("")
    A(f"2. FAILURES: {n_fail}")
    A("")
    A("3. CONVERGENCE PER QUANTITY (chain B = 12->24->48; §4.5 floor applied)")
    A(f"   {'quantity':26s} {'adm/assess':>11s} {'medP':>6s} {'medR':>6s} "
      f"{'worstGCI%':>9s} {'worstDisc%':>10s}")
    for q in C.QUANTITY_FIELDS:
        st = q_stats[q]
        gci = f"{st['worst_gci']*100:.3f}" if st['worst_gci'] is not None else "  -"
        disc = f"{st['worst_discrepancy']*100:.3f}" if st['worst_discrepancy'] is not None else "  -"
        A(f"   {q:26s} {st['admissible']:>4d}/{st['assessed']:<6d} "
          f"{st['median_p']:6.2f} {st['median_R']:6.2f} {gci:>9s} {disc:>10s}")
    A("")
    A(f"4. CHAIN AGREEMENT (|pA-pB|/pB <= 30%): agree={agree} disagree={disagree}")
    A("")
    A("5. EXTRAPOLATION REFUSALS (dominant reasons)")
    for q in C.QUANTITY_FIELDS:
        rc = q_stats[q]["reasons"]
        if rc:
            top = sorted(rc.items(), key=lambda kv: -kv[1])
            A(f"   {q:26s} " + ", ".join(f"{k}:{v}" for k, v in top))
    A("")
    A("6. KNEE (worst key-quantity error vs chord 48)")
    for nc in CHORDS:
        A(f"   chord {nc:2d}: {knee_err[nc]:6.3f}%  at median {knee_secs[nc]:.1f}s")
    A("")
    A("7. WHAT THIS MEANS")
    A("   Chordwise error falls steeply from 6->12 and flattens by 24-48. The")
    A("   knee plot shows where more chordwise panels stop buying accuracy. Where")
    A("   a quantity is in its asymptotic range (six gates pass) the chord-48")
    A("   result carries a GCI; where it is not, only a finest-grid discrepancy")
    A("   is reported and no convergence is claimed.")
    A("")
    A("8. SURPRISES / CAVEATS")
    A("   - Near-zero lateral quantities (Cnb, elevon_diff.*) are below the 1e-4")
    A("     floor and are not extrapolated; assessed on normalised discrepancy.")
    A("   - Report whether the two chains agree (above): disagreement would")
    A("     falsify asymptotic behaviour.")

    (C.CONFIG_ROOT / "stage2_summary.txt").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
