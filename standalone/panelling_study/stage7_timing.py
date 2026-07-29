"""Stage 7 — Honest timings (§ Stage 7).

A timing taken while other jobs share the machine is not a timing; a timing from
cache is not a timing. Each of the 5 settings, 5 repeats, geom seed-2001 at +4,
STRICTLY ONE AT A TIME, bypassing the cache, into a separate tree. Report medians.
"""

from __future__ import annotations

import json
import statistics
import time

import common as C

REPEATS = 5
ALPHA = 4.0
SYM, DIFF = 4.0, 4.0
N_DESIGNS_PROJECTION = 2000
N_ANGLES_PROJECTION = 3


def main():
    shortlist = json.loads((C.CONFIG_ROOT / "stage5_shortlist.json").read_text())["shortlist"]
    gkey, sample = C.normal_samples()[0]   # seed-2001 equivalent = LHS index 0

    print(f"Stage 7: {len(shortlist)} settings x {REPEATS} repeats, SERIAL, "
          f"cache bypassed, geom={gkey}", flush=True)

    timings = {}
    for c in shortlist:
        nc, ns, cs, label = c["nchordwise"], c["spanwise"], c["cspace"], c["label"]
        avl_s, tot_s = [], []
        for rep in range(REPEATS):
            t0 = time.perf_counter()
            r = C.run_case(sample, nchordwise=nc, spanwise=ns, cspace=cs,
                           alpha_deg=ALPHA, control_input_deg=SYM, diff_input_deg=DIFF,
                           sample_key=gkey, tag=f"timing/{label}/{rep}",
                           bypass_cache=True)
            wall = time.perf_counter() - t0
            if r.get("ok"):
                avl_s.append(r.get("seconds_avl"))
                tot_s.append(wall)
            print(f"  {label} rep{rep}: avl={r.get('seconds_avl',0):.2f}s "
                  f"wall={wall:.2f}s ok={r.get('ok')}", flush=True)
        timings[label] = {
            "median_avl_s": statistics.median(avl_s) if avl_s else None,
            "median_end_to_end_s": statistics.median(tot_s) if tot_s else None,
            "nchordwise": nc, "spanwise": ns, "cspace": cs,
        }

    # projected hours for 2000 designs x 3 angles, from END-TO-END time
    for label, t in timings.items():
        e2e = t["median_end_to_end_s"]
        t["projected_hours_2000x3"] = (
            e2e * N_DESIGNS_PROJECTION * N_ANGLES_PROJECTION / 3600.0
            if e2e else None)

    # revise shortlist costs in place with measured end-to-end
    changed = []
    for c in shortlist:
        meas = timings[c["label"]]["median_end_to_end_s"]
        old = c.get("cost_s")
        if meas is not None:
            if old and abs(meas - old) / old > 0.20:
                changed.append((c["label"], old, round(meas, 1)))
            c["cost_s"] = round(meas, 1)
    full = json.loads((C.CONFIG_ROOT / "stage5_shortlist.json").read_text())
    full["shortlist"] = shortlist
    full["stage7_measured"] = True
    (C.CONFIG_ROOT / "stage5_shortlist.json").write_text(json.dumps(full, indent=2))

    # ---- plot: single-axis bar of end-to-end seconds, hours as text ------- #
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    labels = [c["label"] for c in shortlist]
    e2es = [timings[l]["median_end_to_end_s"] for l in labels]
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    ax.bar(range(len(labels)), e2es, color="crimson")
    ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels)
    ax.set_ylabel("median end-to-end seconds")
    for i, l in enumerate(labels):
        h = timings[l]["projected_hours_2000x3"]
        ax.annotate(f"{h:.1f} h" if h else "?", (i, e2es[i]), fontsize=8,
                    ha="center", va="bottom")
    ax.set_title("cost per solve, and projected 2000x3 sweep hours")
    fig.savefig(C.PLOTS_ROOT / "stage7_cost.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    # ---- summary ---------------------------------------------------------- #
    lines = []; A = lines.append
    A("STAGE 7 — HONEST TIMINGS (serial, cache bypassed)")
    A("=" * 60)
    A(f"1. RUN: {len(shortlist)} settings x {REPEATS} repeats on {gkey} at +4.")
    A("")
    A("2. MEDIAN TIMINGS")
    A(f"   {'setting':>8s} {'AVL-only s':>11s} {'end-to-end s':>13s} "
      f"{'proj hours (2000x3)':>20s}")
    for c in shortlist:
        t = timings[c["label"]]
        A(f"   {c['label']:>8s} {t['median_avl_s']:>11.2f} {t['median_end_to_end_s']:>13.2f} "
          f"{t['projected_hours_2000x3']:>20.1f}")
    A("")
    A("3. SECTION-BUILD DILUTION")
    A("   End-to-end includes the ~1.4 s per-design section build, a fixed cost")
    A("   that does not scale with panelling and so dilutes the relative saving of")
    A("   a cheaper mesh. The selection rule sees end-to-end, not AVL-only.")
    A("")
    A("4. INTERPOLATED-COST CORRECTIONS (>20% off)")
    if changed:
        for lbl, old, new in changed:
            A(f"   {lbl}: interpolated {old}s -> measured {new}s")
    else:
        A("   None: all Stage 5 interpolated costs were within 20% of measured.")
    A("")
    A("5. WHAT THIS MEANS")
    prod = next((c for c in shortlist if "PRODUCTION" in c["role"]), None)
    cheap = next((c for c in shortlist if c["label"] == "c16s2u"), None)
    if prod and cheap:
        ph = timings[prod["label"]]["projected_hours_2000x3"]
        ch = timings[cheap["label"]]["projected_hours_2000x3"]
        A(f"   A 2000-design x 3-angle sweep costs ~{ph:.0f} h at the production mesh")
        A(f"   ({prod['label']}) vs ~{ch:.0f} h at c16s2u — a {ph/ch:.1f}x wall-clock")
        A("   difference, the concrete stake behind the gate-4/gate-6 discussion.")

    (C.CONFIG_ROOT / "stage7_summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
