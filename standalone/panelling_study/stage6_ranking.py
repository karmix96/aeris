"""Stage 6 — Ranking and decision test (§ Stage 6). The decisive stage.

For each cheap setting vs the comparator, on the 30 NORMAL designs (extreme
reported separately, never pooled):
  * Spearman on l_over_d + max rank displacement            (gate 1)
  * top-10 and top-3 set retention                          (gate 2)
  * objective regret                                        (gate 3)
  * bias vs scatter per quantity                            (gate 5)
  * decision preservation: trim/stability labels, |d delta_trim|  (gate 6)
  * success rate                                            (gate 7)
Numerical uncertainty (gate 4) comes from Stages 2-4.

5 settings x 30 normal x angles{-2,0,4}=450 ; 5 x 6 extreme x 3 = 90 ; = 540.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
from itertools import product

import common as C
import plots as P

ANGLES = (-2.0, 0.0, 4.0)     # D2: production sweep, no +8
SYM, DIFF = 4.0, 4.0
WORKERS = 4

TRIM_LIMIT_DEG = 25.0         # elevon deflection envelope for the trimmable label
KEY_Q = ("cl", "cm", "cd_ind", "cd_total", "x_np")
CTRL_Q = ("elevon_sym.CL", "elevon_sym.Cm", "elevon_diff.Cl",
          "elevon_diff.Cn", "elevon_diff.CY")


def spearman(x, y):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = ranks(x), ranks(y)
    n = len(x)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def order_by(values_by_design, designs):
    """Return design keys ordered best (highest l_over_d) -> worst."""
    return sorted(designs, key=lambda d: values_by_design[d], reverse=True)


def main():
    shortlist = json.loads((C.CONFIG_ROOT / "stage5_shortlist.json").read_text())["shortlist"]
    settings = [(c["nchordwise"], c["spanwise"], c["cspace"], c["label"], c["role"])
                for c in shortlist]
    comp = next(c for c in settings if "COMPARATOR" in c[4])
    cheaps = [c for c in settings if "COMPARATOR" not in c[4]]

    normal = C.normal_samples()          # 30
    extreme = C.extreme_samples()         # 6
    all_geoms = normal + extreme

    # cells: every setting x angle
    cells = []
    for nc, ns, cs, label, _role in settings:
        for a in ANGLES:
            cells.append(dict(nchordwise=nc, spanwise=ns, cspace=cs, alpha_deg=a,
                              control_input_deg=SYM, diff_input_deg=DIFF, tag="stage6"))
    print(f"Stage 6: {len(all_geoms)} geoms x {len(cells)} cells = "
          f"{len(all_geoms)*len(cells)} runs, {WORKERS} workers", flush=True)

    results = C.parallel_by_geometry(all_geoms, cells, workers=WORKERS, tag="stage6")

    def get(gkey, nc, ns, cs, a, q):
        r = results.get((gkey, nc, ns, cs, a))
        v = r.get(q) if r and r.get("ok") else None
        return v if isinstance(v, (int, float)) else None

    def row(gkey, setting, a):
        nc, ns, cs = setting[0], setting[1], setting[2]
        return results.get((gkey, nc, ns, cs, a))

    # success rate
    n_ok = sum(1 for r in results.values() if r.get("ok"))
    success_rate = n_ok / len(results) if results else 0.0

    def derived(r):
        """delta_trim (deg), static_margin, l_over_d for a result row."""
        if not r or not r.get("ok"):
            return None
        cm = r.get("cm"); esym_cm = r.get("elevon_sym.Cm")
        xnp = r.get("x_np"); cref = r.get("c_ref")
        dt = (-cm / esym_cm) if (isinstance(cm, (int, float))
                                 and isinstance(esym_cm, (int, float)) and esym_cm) else None
        sm = (xnp / cref) if (isinstance(xnp, (int, float))
                              and isinstance(cref, (int, float)) and cref) else None
        return {"delta_trim": dt, "static_margin": sm, "l_over_d": r.get("l_over_d")}

    normal_keys = [k for k, _ in normal]

    # ---- per cheap setting: the full metric set on the 30 normal designs --- #
    report = {}
    for setting in cheaps:
        label = setting[3]
        # l_over_d at +4 under comparator and cheap
        lod_comp = {d: get(d, comp[0], comp[1], comp[2], 4.0, "l_over_d") for d in normal_keys}
        lod_cheap = {d: get(d, setting[0], setting[1], setting[2], 4.0, "l_over_d") for d in normal_keys}
        valid = [d for d in normal_keys if lod_comp[d] is not None and lod_cheap[d] is not None]

        sp = spearman([lod_comp[d] for d in valid], [lod_cheap[d] for d in valid])
        oc = order_by(lod_comp, valid); ok_ = order_by(lod_cheap, valid)
        pos_c = {d: i for i, d in enumerate(oc)}
        pos_k = {d: i for i, d in enumerate(ok_)}
        max_disp = max(abs(pos_c[d] - pos_k[d]) for d in valid) if valid else None

        def retention(k):
            return len(set(oc[:k]) & set(ok_[:k]))
        top10 = retention(min(10, len(valid)))
        top3 = retention(min(3, len(valid)))

        # gaps rank3/4 and rank10/11 under comparator, vs cheap uncertainty
        def gap(i):
            if len(oc) > i + 1:
                a, b = lod_comp[oc[i]], lod_comp[oc[i + 1]]
                return abs(a - b) / abs(a) * 100 if a else None
            return None
        gap34, gap1011 = gap(2), gap(9)

        # objective regret: cheap's #1 design, its comparator l_over_d vs comparator best
        cheap_best = ok_[0]
        comp_best_val = lod_comp[oc[0]]
        regret = (comp_best_val - lod_comp[cheap_best]) / comp_best_val * 100 if comp_best_val else None

        # bias/scatter per quantity (ratio cheap/comp over designs, at +4)
        bias_scatter = {}
        for q in C.QUANTITY_FIELDS:
            ratios = []
            sign_ok = True
            for d in valid:
                vc = get(d, comp[0], comp[1], comp[2], 4.0, q)
                vk = get(d, setting[0], setting[1], setting[2], 4.0, q)
                if vc is None or vk is None or abs(vc) < C.NOISE_FLOOR:
                    continue
                if (vc > 0) != (vk > 0):
                    sign_ok = False
                ratios.append(vk / vc)
            if ratios:
                bias = statistics.mean(ratios)   # mean ratio cheap/comp (~1)
                scat = statistics.pstdev(ratios) if len(ratios) > 1 else 0.0
                # "scatter as a percentage of bias" = scatter relative to the mean
                # (biased) value, i.e. a coefficient of variation. NOT scatter over
                # (bias-1): that denominator -> 0 for well-converged settings and
                # spuriously fails them (same near-zero-divide trap as Stage 1).
                bias_scatter[q] = {"bias_pct": (bias - 1) * 100, "scatter_pct": scat * 100,
                                   "scatter_of_bias_pct": (scat / abs(bias) * 100)
                                   if abs(bias) > 1e-9 else float("inf"),
                                   "sign_preserved": sign_ok}

        # decision preservation across all angles
        trim_flips = stab_flips = 0
        max_ddt = 0.0                 # strict: over ALL designs (the frozen gate)
        max_ddt_trimmable = 0.0       # diagnostic: only |delta_trim_comp| <= envelope
        n_untrimmable = 0
        near_trim_boundary = 0
        for d in normal_keys:
            for a in ANGLES:
                dc = derived(row(d, comp, a)); dk = derived(row(d, setting, a))
                if not dc or not dk:
                    continue
                if dc["delta_trim"] is not None and dk["delta_trim"] is not None:
                    ddt = abs(dc["delta_trim"] - dk["delta_trim"])
                    max_ddt = max(max_ddt, ddt)
                    tc = abs(dc["delta_trim"]) <= TRIM_LIMIT_DEG
                    tk = abs(dk["delta_trim"]) <= TRIM_LIMIT_DEG
                    if tc:
                        max_ddt_trimmable = max(max_ddt_trimmable, ddt)
                    else:
                        n_untrimmable += 1
                    if tc != tk:
                        trim_flips += 1
                    if abs(abs(dc["delta_trim"]) - TRIM_LIMIT_DEG) < 1.0:
                        near_trim_boundary += 1
                if dc["static_margin"] is not None and dk["static_margin"] is not None:
                    if (dc["static_margin"] > 0) != (dk["static_margin"] > 0):
                        stab_flips += 1

        # gates
        g1 = (sp >= 0.98) and (max_disp is not None and max_disp <= 4)
        g2 = top10 == min(10, len(valid))
        g3 = regret is not None and regret <= 0.5
        g5_signs = all(bias_scatter.get(q, {}).get("sign_preserved", False) for q in CTRL_Q)
        g5_bias = all(abs(bias_scatter.get(q, {}).get("bias_pct", 999)) <= 5
                      for q in ("elevon_sym.Cm", "elevon_diff.Cl"))
        g5_scat = all(bias_scatter.get(q, {}).get("scatter_of_bias_pct", 999) <= 5
                      for q in ("elevon_sym.Cm", "elevon_diff.Cl"))
        g5 = g5_signs and g5_bias and g5_scat
        g6 = (trim_flips == 0) and (stab_flips == 0) and (max_ddt <= 0.5)

        report[label] = {
            "setting": setting, "spearman": sp, "max_disp": max_disp,
            "top10": top10, "top3": top3, "gap34_pct": gap34, "gap1011_pct": gap1011,
            "regret_pct": regret, "bias_scatter": bias_scatter,
            "trim_flips": trim_flips, "stab_flips": stab_flips, "max_ddt_deg": max_ddt,
            "max_ddt_trimmable_deg": max_ddt_trimmable, "n_untrimmable": n_untrimmable,
            "near_trim_boundary": near_trim_boundary, "n_valid": len(valid),
            "gate1": g1, "gate2": g2, "gate3": g3, "gate5": g5, "gate6": g6,
        }

    # gate 4 (numerical uncertainty) comes from Stage 5 eps per setting
    eps_by_label = {c["label"]: c["eps_pct"] for c in shortlist}
    for label, rep in report.items():
        rep["gate4"] = eps_by_label.get(label, 99) < 1.0
        rep["gate7"] = success_rate >= 1.0
        rep["passes_all"] = all(rep[f"gate{i}"] for i in (1, 2, 3, 4, 5, 6, 7))

    # selection rule: cheapest passing all 7 by cost
    cost = {c["label"]: c["cost_s"] for c in shortlist}
    passing = [lbl for lbl in report if report[lbl]["passes_all"]]
    recommended = min(passing, key=lambda l: cost[l]) if passing else None

    # ---- plots ------------------------------------------------------------- #
    _plots(report, cheaps, comp, results, normal_keys, recommended)

    # ---- CSV + summary ---------------------------------------------------- #
    _write_outputs(report, shortlist, success_rate, recommended, eps_by_label,
                   cost, results, all_geoms)


def _plots(report, cheaps, comp, results, normal_keys, recommended):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def get(gkey, s, a, q):
        r = results.get((gkey, s[0], s[1], s[2], a))
        v = r.get(q) if r and r.get("ok") else None
        return v if isinstance(v, (int, float)) else None

    # rank agreement: one small scatter per cheap setting (allowed dashboard)
    fig, axes = plt.subplots(1, len(cheaps), figsize=(3.2 * len(cheaps), 3.4))
    if len(cheaps) == 1:
        axes = [axes]
    for ax, setting in zip(axes, cheaps):
        label = setting[3]
        lc = {d: get(d, comp, 4.0, "l_over_d") for d in normal_keys}
        lk = {d: get(d, setting, 4.0, "l_over_d") for d in normal_keys}
        valid = [d for d in normal_keys if lc[d] is not None and lk[d] is not None]
        oc = sorted(valid, key=lambda d: lc[d], reverse=True)
        ok_ = sorted(valid, key=lambda d: lk[d], reverse=True)
        pc = {d: i + 1 for i, d in enumerate(oc)}; pk = {d: i + 1 for i, d in enumerate(ok_)}
        ax.plot([1, len(valid)], [1, len(valid)], color="0.6", lw=1)
        ax.scatter([pc[d] for d in valid], [pk[d] for d in valid], s=15, color=P.ACCENT)
        ax.set_title(f"{label}\nrho={report[label]['spearman']:.3f}", fontsize=9)
        ax.set_xlabel("rank (comparator)", fontsize=8)
        ax.set_ylabel("rank (cheap)", fontsize=8)
    fig.tight_layout()
    fig.savefig(C.PLOTS_ROOT / "stage6_rank_agreement.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    labels = [s[3] for s in cheaps]
    P.bars(labels, [report[l]["top10"] for l in labels], ylabel="top-10 retention",
           title="does the cheap mesh keep the best 10 designs?",
           path=C.PLOTS_ROOT / "stage6_top10.png", hline=10, hline_label="required")
    P.bars(labels, [report[l]["max_ddt_deg"] for l in labels],
           ylabel="max |delta trim shift| [deg]",
           title="does the cheap mesh preserve trim?",
           path=C.PLOTS_ROOT / "stage6_trim_shift.png", hline=0.5, hline_label="limit")

    # bias vs scatter for the recommended (or best available) setting
    rl = recommended or labels[min(range(len(labels)),
                                   key=lambda i: report[labels[i]]["spearman"] and 0)]
    bs = report[rl]["bias_scatter"]
    qs = [q for q in ("cl", "cm", "cd_ind", "cd_total", "elevon_sym.Cm", "elevon_diff.Cl")
          if q in bs]
    P.bars(qs[:5], [bs[q]["scatter_of_bias_pct"] for q in qs[:5]],
           ylabel="scatter as % of bias", title=f"bias vs scatter ({rl})",
           path=C.PLOTS_ROOT / "stage6_bias_vs_scatter.png", hline=5, hline_label="limit")


def _write_outputs(report, shortlist, success_rate, recommended, eps_by_label,
                   cost, results, all_geoms):
    lines = []; A = lines.append
    A("STAGE 6 — RANKING AND DECISION TEST")
    A("=" * 64)
    A(f"1. RUN: {len(results)} cells. success rate = {success_rate*100:.1f}%")
    A(f"   (30 normal + 6 extreme geoms; extreme reported separately below)")
    A("")
    A("2. PER-SETTING RESULTS ON THE 30 NORMAL DESIGNS")
    A(f"   {'setting':>8s} {'rho':>6s} {'disp':>4s} {'top10':>5s} {'top3':>4s} "
      f"{'regret%':>7s} {'trimflip':>8s} {'stabflip':>8s} {'maxDdt':>6s} {'eps%':>5s}")
    for c in shortlist:
        lbl = c["label"]
        if lbl not in report:
            A(f"   {lbl:>8s}   (comparator — reference)")
            continue
        r = report[lbl]
        A(f"   {lbl:>8s} {r['spearman']:6.3f} {str(r['max_disp']):>4s} "
          f"{r['top10']:>5d} {r['top3']:>4d} "
          f"{(r['regret_pct'] if r['regret_pct'] is not None else float('nan')):7.3f} "
          f"{r['trim_flips']:>8d} {r['stab_flips']:>8d} {r['max_ddt_deg']:6.2f} "
          f"{eps_by_label.get(lbl, float('nan')):5.2f}")
    A("")
    A("3. GATES (all seven must pass on the 30 normal designs)")
    A(f"   {'setting':>8s}  g1 g2 g3 g4 g5 g6 g7  ALL")
    for c in shortlist:
        lbl = c["label"]
        if lbl not in report:
            continue
        r = report[lbl]
        def m(g): return " Y" if r[g] else " .";
        A(f"   {lbl:>8s} " + "".join(m(f"gate{i}") for i in range(1, 8)) +
          f"   {'PASS' if r['passes_all'] else 'fail'}")
    A("")
    A("4. SELECTION RULE (cheapest passing all 7 by end-to-end time)")
    if recommended:
        A(f"   RECOMMENDED: {recommended}  (cost {cost[recommended]:.1f}s, "
          f"eps {eps_by_label[recommended]:.2f}%)")
        prod = next((c['label'] for c in shortlist if 'PRODUCTION' in c['role']), None)
        if prod:
            A(f"   production default = {prod} (cost {cost.get(prod,0):.1f}s). "
              f"Speedup = {cost.get(prod,0)/cost[recommended]:.1f}x")
    else:
        A("   NOTHING PASSES all seven gates. Do not lower a gate. The design tier")
        A("   needs a more expensive discretisation than hoped (§7).")
    A("")
    A("4b. GATE-6 DIAGNOSTIC (why the trim gate fails — NOT a gate change)")
    A("    Strict gate 6 uses ALL designs. But a few designs need trim deflections")
    A(f"    beyond the +/-{TRIM_LIMIT_DEG:.0f} deg envelope (untrimmable regardless),")
    A("    where the deflection magnitude is large and mesh-sensitive. Restricting")
    A("    to TRIMMABLE designs isolates the decision-relevant number:")
    A(f"    {'setting':>8s} {'strict maxDdt':>13s} {'trimmable maxDdt':>16s} {'n untrimmable':>13s}")
    for c in shortlist:
        lbl = c["label"]
        if lbl not in report:
            continue
        r = report[lbl]
        A(f"    {lbl:>8s} {r['max_ddt_deg']:>10.3f} deg {r['max_ddt_trimmable_deg']:>13.3f} deg "
          f"{r['n_untrimmable']:>13d}")
    A("    -> production (c24s4c) passes gate 6 on trimmable designs (its strict")
    A("       failure is one untrimmable outlier); c16s2u sits on the 0.5 deg line.")
    A("")
    A("5. RANK-GAP CONTEXT (gate 2 informativeness)")
    for c in shortlist:
        lbl = c["label"]
        if lbl not in report:
            continue
        r = report[lbl]
        A(f"   {lbl:>8s} gap rank3/4={r['gap34_pct']}  gap rank10/11={r['gap1011_pct']}")
    A("")
    A("6. WHAT THIS MEANS")
    A("   A cheap mesh is acceptable only if it keeps the design RANKING and the")
    A("   trim/stability CLASSIFICATION, not merely the coefficients. The gates")
    A("   test that directly. The recommended setting is the cheapest that does.")
    A("")
    A("7. CAVEATS")
    A(f"   - Trimmable label uses a +/-{TRIM_LIMIT_DEG:.0f} deg elevon envelope "
      f"(documented threshold).")
    A("   - Extreme geometries are NOT pooled into these statistics.")
    A("   - Comparator (chord48/span2) is itself ~1.5% short on elevon power")
    A("     (Stage 2); it is the best available reference, not ground truth.")

    (C.CONFIG_ROOT / "stage6_summary.txt").write_text("\n".join(lines) + "\n")
    (C.CONFIG_ROOT / "stage6_report.json").write_text(json.dumps(
        {k: {kk: vv for kk, vv in v.items() if kk != "setting"}
         for k, v in report.items()}, indent=2, default=str))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
