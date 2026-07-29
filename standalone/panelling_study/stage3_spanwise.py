"""Stage 3 — Spanwise convergence (§ Stage 3).

Mirror of Stage 2 but refining spanwise with chordwise fixed at 12.

span {1,2,4,8} x chord 12 x 8 geoms x angles {-2,0,+2,+4}  = 128 runs.
Chains: A={1,2,4}, B={2,4,8}. Same six admissibility gates, same labelling.

Two things the runbook asks to watch:
  * spanwise 1 is expected to FAIL on hinge moments (Stage 0 prediction), not a
    surprise — it resolves the elevon band with only the strips the placement
    provides.
  * the viscous correction is per strip, so refining spanwise also refines the
    profile-drag integral. cd_total may converge differently from cd_ind, and
    l_over_d may be governed by the viscous term. Reported explicitly below.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
from itertools import product

import common as C
import plots as P

SPANS = (1, 2, 4, 8)
CHORD = 12
ANGLES = (-2.0, 0.0, 2.0, 4.0)   # D2: no +8
CSPACE = 1.0
SYM, DIFF = 4.0, 4.0
N_GEOM = 8

KEY_Q = ("cl", "cm", "cd_ind", "cd_total", "x_np")
PLOT_Q = "hinge_moments.elevon_sym"   # the most spanwise-sensitive quantity


def rel(a, b):
    return abs(a - b) / abs(b) if b else float("nan")


def main():
    locked = json.loads((C.CONFIG_ROOT / "stage0_locked_config.json").read_text())
    scale = locked["normalisation_scale"]
    geoms = C.convergence_subset(N_GEOM)

    total = len(SPANS) * len(geoms) * len(ANGLES)
    print(f"Stage 3: {total} runs (span{SPANS} x chord{CHORD} x {len(geoms)} geoms "
          f"x angles{ANGLES}) [serial]", flush=True)

    data = {}
    n_new = n_hit = n_fail = 0
    i = 0
    for (gkey, s), a, ns in product(geoms, ANGLES, SPANS):
        i += 1
        C.assert_mesh_legal(C.realized_n_sections(s, gkey), CHORD, ns)
        r = C.run_case(s, nchordwise=CHORD, spanwise=ns, cspace=CSPACE, alpha_deg=a,
                       control_input_deg=SYM, diff_input_deg=DIFF,
                       sample_key=gkey, tag="stage3")
        data[(gkey, a, ns)] = r
        n_hit += bool(r.get("cache_hit"))
        n_new += bool(r.get("ok") and not r.get("cache_hit"))
        n_fail += (not r.get("ok"))
        if i % 16 == 0 or not r.get("ok"):
            print(f"  [{i:3d}/{total}] {gkey} a={a:+.0f} s{ns} ok={r.get('ok')} "
                  f"hit={r.get('cache_hit')} t={r.get('seconds_avl',0):.1f}s", flush=True)

    def val(q, gkey, a, ns):
        r = data.get((gkey, a, ns))
        v = r.get(q) if r and r.get("ok") else None
        return v if isinstance(v, (int, float)) else None

    q_stats = {}
    for q in C.QUANTITY_FIELDS:
        pB_list, R_list, gci_list, disc_list = [], [], [], []
        admissible = assessed = 0
        reasons_count = {}
        span1_disc = []  # discrepancy of span1 vs span8, for the prediction check
        for (gkey, _s), a in product(geoms, ANGLES):
            series = [val(q, gkey, a, ns) for ns in SPANS]
            if any(v is None for v in series):
                continue
            f1, f2, f4, f8 = series
            if f8 is not None and abs(f8) >= C.NOISE_FLOOR and f1 is not None:
                span1_disc.append(rel(f1, f8))
            if abs(f8) < C.NOISE_FLOOR:
                disc_list.append(abs(f2 - f8) / (scale.get(q) or 1))
                reasons_count["below_noise_floor"] = reasons_count.get("below_noise_floor", 0) + 1
                assessed += 1
                continue
            chainA = C.richardson_gci(f1, f2, f4)
            chainB = C.richardson_gci(f2, f4, f8)
            ok, reasons, det = C.convergence_admissible(chainA, chainB, abs(f8))
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
                disc_list.append(rel(f4, f8))
        q_stats[q] = {
            "assessed": assessed, "admissible": admissible,
            "median_p": statistics.median(pB_list) if pB_list else float("nan"),
            "median_R": statistics.median(R_list) if R_list else float("nan"),
            "worst_gci": max(gci_list) if gci_list else None,
            "worst_discrepancy": max(disc_list) if disc_list else None,
            "span1_vs_span8_max": max(span1_disc) if span1_disc else None,
            "reasons": reasons_count,
        }

    # ---- cd_ind vs cd_total vs l_over_d: is L/D governed by the viscous term? #
    def median_disc(q):
        errs = []
        for (gkey, _s), a in product(geoms, ANGLES):
            f2, f8 = val(q, gkey, a, 2), val(q, gkey, a, 8)
            if f2 is None or f8 is None or abs(f8) < C.NOISE_FLOOR:
                continue
            errs.append(rel(f2, f8))
        return statistics.median(errs) if errs else float("nan")
    visc_note = {q: median_disc(q) for q in ("cd_ind", "cd_total", "l_over_d")}

    # ---- knee ------------------------------------------------------------- #
    knee_secs, knee_err = {}, {}
    for ns in SPANS:
        secs = [data[(gkey, a, ns)].get("seconds_avl") for (gkey, _s), a
                in product(geoms, ANGLES) if data.get((gkey, a, ns), {}).get("ok")]
        knee_secs[ns] = statistics.median([x for x in secs if x]) if secs else float("nan")
        worst = 0.0
        for q in KEY_Q:
            errs = []
            for (gkey, _s), a in product(geoms, ANGLES):
                f = val(q, gkey, a, ns); f8 = val(q, gkey, a, 8)
                if f is None or f8 is None or abs(f8) < C.NOISE_FLOOR:
                    continue
                errs.append(rel(f, f8))
            if errs:
                worst = max(worst, statistics.median(errs))
        knee_err[ns] = worst * 100.0

    # ---- plots ------------------------------------------------------------- #
    gk0 = geoms[0][0]
    ys = [val(PLOT_Q, gk0, 4.0, ns) for ns in SPANS]
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    est = None
    if all(v is not None for v in ys) and abs(ys[3]) >= C.NOISE_FLOOR:
        cB = C.richardson_gci(ys[1], ys[2], ys[3]); cA = C.richardson_gci(ys[0], ys[1], ys[2])
        ok, _rs, _d = C.convergence_admissible(cA, cB, abs(ys[3]))
        if ok:
            est = cB["extrap"]
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    ax.plot(list(SPANS), ys, marker="o", color=P.ACCENT)
    ax.set_xscale("log", base=2); ax.set_xticks(list(SPANS))
    ax.get_xaxis().set_major_formatter(plt.matplotlib.ticker.ScalarFormatter())
    if est is not None:
        ax.axhline(est, color=P.REF, linestyle="--")
        ax.annotate("estimated limit", (SPANS[-1], est), color=P.REF, fontsize=9,
                    va="bottom", ha="right")
    ax.set_xlabel("spanwise panels per section"); ax.set_ylabel(PLOT_Q)
    ax.set_title(f"{PLOT_Q} vs spanwise ({'settles' if est else 'not in asymptotic range'})")
    fig.savefig(C.PLOTS_ROOT / "stage3_convergence.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    xs = [knee_secs[ns] for ns in SPANS]; ys2 = [knee_err[ns] for ns in SPANS]
    ax.plot(xs, ys2, marker="o", color=P.ACCENT)
    for ns, x, y in zip(SPANS, xs, ys2):
        ax.annotate(f"s{ns}", (x, y), fontsize=9, xytext=(4, 3), textcoords="offset points")
    ax.set_xlabel("median solve seconds"); ax.set_ylabel("worst key-quantity error [%] vs span 8")
    ax.set_title("where does more spanwise resolution stop buying accuracy?")
    fig.savefig(C.PLOTS_ROOT / "stage3_error_vs_time.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    # ---- CSV + summary ---------------------------------------------------- #
    with open(C.CONFIG_ROOT / "stage3_results.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["geom", "angle", "span", "ok"] + list(C.QUANTITY_FIELDS) + ["seconds_avl"])
        for (gkey, a, ns), r in data.items():
            w.writerow([gkey, a, ns, r.get("ok")]
                       + [r.get(q) for q in C.QUANTITY_FIELDS] + [r.get("seconds_avl")])

    lines = []; A = lines.append
    A("STAGE 3 — SPANWISE CONVERGENCE")
    A("=" * 60)
    A(f"1. RUN: {total} cells. new={n_new} hits={n_hit} fails={n_fail}")
    A(f"   median solve seconds by span: " +
      ", ".join(f"s{ns}={knee_secs[ns]:.1f}s" for ns in SPANS))
    A("")
    A(f"2. FAILURES: {n_fail}")
    A("")
    A("3. CONVERGENCE PER QUANTITY (chain B = 2->4->8; §4.5 floor applied)")
    A(f"   {'quantity':26s} {'adm/assess':>11s} {'medP':>6s} {'medR':>6s} "
      f"{'worstGCI%':>9s} {'worstDisc%':>10s} {'s1vs8max%':>10s}")
    for q in C.QUANTITY_FIELDS:
        st = q_stats[q]
        gci = f"{st['worst_gci']*100:.3f}" if st['worst_gci'] is not None else "  -"
        disc = f"{st['worst_discrepancy']*100:.3f}" if st['worst_discrepancy'] is not None else "  -"
        s1 = f"{st['span1_vs_span8_max']*100:.2f}" if st['span1_vs_span8_max'] is not None else "  -"
        A(f"   {q:26s} {st['admissible']:>4d}/{st['assessed']:<6d} "
          f"{st['median_p']:6.2f} {st['median_R']:6.2f} {gci:>9s} {disc:>10s} {s1:>10s}")
    A("")
    A("4. SPANWISE-1 PREDICTION CHECK (Stage 0 predicted hinge moments unusable)")
    for q in ("hinge_moments.elevon_sym", "hinge_moments.elevon_diff",
              "elevon_diff.Cl", "elevon_diff.Cn"):
        v = q_stats[q]["span1_vs_span8_max"]
        A(f"   {q:26s} span1 vs span8 (worst) = "
          f"{v*100:.1f}%" if v is not None else f"   {q}: n/a")
    A("")
    A("5. VISCOUS COUPLING (median span2->span8 discrepancy)")
    for q, v in visc_note.items():
        A(f"   {q:12s} {v*100:.3f}%")
    A("   If cd_total moves more than cd_ind, spanwise is refining the per-strip")
    A("   profile-drag integral and l_over_d is governed by the viscous term.")
    A("")
    A("6. KNEE (worst key-quantity error vs span 8)")
    for ns in SPANS:
        A(f"   span {ns}: {knee_err[ns]:6.3f}%  at median {knee_secs[ns]:.1f}s")
    A("")
    A("7. WHAT THIS MEANS")
    A("   Spanwise 1 is the deliberate below-the-knee point. The knee plot shows")
    A("   where more spanwise resolution stops paying. Hinge moments and lateral")
    A("   control derivatives are the spanwise-hungry quantities; forces and")
    A("   stability derivatives settle earlier.")

    (C.CONFIG_ROOT / "stage3_summary.txt").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
