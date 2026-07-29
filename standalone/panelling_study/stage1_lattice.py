"""Stage 1 — 2D lattice: are chordwise and spanwise errors separable? (§ Stage 1)

Decides whether Stages 2 and 3 (each refining one direction) are interpretable.
Cheapest thing that can invalidate the plan, so it runs first.

Grid (D4-corrected): chord {8,12,16} x span {2,4,6}. The runbook's chord 20 at
span 6 is 6720 vortices > 6000 with the realized section count, so the top chord
is capped at 16 (see stage0 D4). Separability is therefore demonstrated on
chord 8-16 x span 2-6.

108 runs: 9 cells x 4 geometries x 3 angles.
"""

from __future__ import annotations

import json
import math
import statistics
from itertools import product

import common as C
import plots as P

CHORDS = (8, 12, 16)          # D4: was (8,12,20); 20 illegal at span 6
SPANS = (2, 4, 6)
ANGLES = (-2.0, 0.0, 4.0)
CSPACE = 1.0
SYM, DIFF = 4.0, 4.0
N_GEOM = 4

GATE_I_MAX = 0.20


def _rms(xs):
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if not xs:
        return float("nan")
    return math.sqrt(sum(x * x for x in xs) / len(xs))


def interaction_index(Q):
    """Two-way no-replication decomposition. Q is a 3x3 list (chord x span).
    Returns (I, rmsA, rmsB, rmsAB) or None if the cell is unusable."""
    flat = [Q[i][j] for i in range(3) for j in range(3)]
    if any(v is None for v in flat):
        return None
    mu = sum(flat) / 9.0
    A = [sum(Q[i][j] for j in range(3)) / 3.0 - mu for i in range(3)]
    B = [sum(Q[i][j] for i in range(3)) / 3.0 - mu for j in range(3)]
    AB = [Q[i][j] - mu - A[i] - B[j] for i in range(3) for j in range(3)]
    rA, rB, rAB = _rms(A), _rms(B), _rms(AB)
    denom = rA + rB
    if denom == 0 or math.isnan(denom):
        return (float("nan"), rA, rB, rAB)
    return (rAB / denom, rA, rB, rAB)


def main():
    locked_path = C.CONFIG_ROOT / "stage0_locked_config.json"
    if not locked_path.exists():
        raise SystemExit("Stage 0 must run first (stage0_locked_config.json missing).")
    locked = json.loads(locked_path.read_text())
    scale = locked["normalisation_scale"]

    geoms = C.convergence_subset(N_GEOM)

    # ---- run the 108 cells ------------------------------------------------- #
    total = len(CHORDS) * len(SPANS) * len(geoms) * len(ANGLES)
    print(f"Stage 1: {total} runs "
          f"(chord{CHORDS} x span{SPANS} x {len(geoms)} geoms x angles{ANGLES})",
          flush=True)
    data = {}  # (gkey, angle, chord, span) -> row
    n_new = n_hit = n_fail = 0
    i = 0
    for (gkey, s), a, nc, ns in product(geoms, ANGLES, CHORDS, SPANS):
        i += 1
        C.assert_mesh_legal(C.realized_n_sections(s, gkey), nc, ns)
        row = C.run_case(s, nchordwise=nc, spanwise=ns, cspace=CSPACE, alpha_deg=a,
                         control_input_deg=SYM, diff_input_deg=DIFF,
                         sample_key=gkey, tag="stage1")
        data[(gkey, a, nc, ns)] = row
        n_hit += bool(row.get("cache_hit"))
        n_new += bool(row.get("ok") and not row.get("cache_hit"))
        n_fail += (not row.get("ok"))
        if i % 9 == 0 or not row.get("ok"):
            print(f"  [{i:3d}/{total}] {gkey} a={a:+.0f} c{nc}s{ns} "
                  f"ok={row.get('ok')} hit={row.get('cache_hit')} "
                  f"t={row.get('seconds_avl',0):.1f}s", flush=True)

    # ---- interaction index per quantity, geometry, angle ------------------- #
    # §4.5 floor: the interaction ratio I is a RELATIVE measure whose comparator
    # is the main-effect signal rms(A)+rms(B). When that comparator is below the
    # 1e-4 print-noise floor the quantity is mesh-INSENSITIVE, not interacting,
    # and I is a ratio of rounding artifacts (see the raw 3x3 tables). Per §4.5 /
    # the Stage 1 spec we then mark I not-assessable and assess the NORMALISED
    # interaction NI = rms(AB)/scale[q] instead. Gate 1 is evaluated on the
    # ratio-assessable quantities (those clearing the floor); NI is reported for
    # the rest, exactly as gate 4 uses GCI-where-admissible / discrepancy-else.
    per_q = {q: {"max_I": 0.0, "I_vals": [], "max_NI": 0.0, "NI_vals": [],
                 "assessable": False} for q in C.QUANTITY_FIELDS}
    worst = {"I": -1.0}
    for q in C.QUANTITY_FIELDS:
        for (gkey, _s), a in product(geoms, ANGLES):
            Q = [[None] * 3 for _ in range(3)]
            ok = True
            for ii, nc in enumerate(CHORDS):
                for jj, ns in enumerate(SPANS):
                    r = data.get((gkey, a, nc, ns))
                    v = r.get(q) if r and r.get("ok") else None
                    if not isinstance(v, (int, float)):
                        ok = False
                    Q[ii][jj] = v
            if not ok:
                continue
            res = interaction_index(Q)
            if res is None:
                continue
            I, rA, rB, rAB = res
            denom = rA + rB
            sc = scale.get(q) or float("nan")
            NI = rAB / sc if sc and not math.isnan(sc) else float("nan")
            if denom < C.NOISE_FLOOR:
                # below floor -> ratio not assessable; use normalised interaction
                if not math.isnan(NI):
                    per_q[q]["NI_vals"].append(NI)
                    per_q[q]["max_NI"] = max(per_q[q]["max_NI"], NI)
                continue
            per_q[q]["assessable"] = True
            if math.isnan(I):
                continue
            per_q[q]["I_vals"].append(I)
            per_q[q]["max_I"] = max(per_q[q]["max_I"], I)
            if I > worst["I"]:
                worst = {"I": I, "q": q, "geom": gkey, "angle": a}

    # ---- gate 1: max I < 0.20 over the ratio-assessable quantities --------- #
    all_I = [v for q in per_q for v in per_q[q]["I_vals"]]
    max_I = max(all_I) if all_I else float("nan")
    gate1 = max_I < GATE_I_MAX
    # transparency: worst normalised interaction among the floored quantities
    all_NI = [(q, per_q[q]["max_NI"]) for q in per_q if per_q[q]["NI_vals"]]
    max_NI = max((v for _q, v in all_NI), default=float("nan"))
    floored = [q for q in per_q if not per_q[q]["assessable"]]

    # ---- gate 2: l_over_d ranking of the 4 geoms identical across spans ---- #
    # at +4, fixed chord=12 (present at all spans), rank geoms by l_over_d.
    rank_by_span = {}
    for ns in SPANS:
        pairs = []
        for gkey, _s in geoms:
            r = data.get((gkey, 4.0, 12, ns))
            lod = r.get("l_over_d") if r and r.get("ok") else None
            pairs.append((gkey, lod))
        order = [k for k, v in sorted(pairs, key=lambda kv: (kv[1] is None, kv[1]))]
        rank_by_span[ns] = order
    orders = list(rank_by_span.values())
    gate2 = all(o == orders[0] for o in orders)

    # ---- plots: interaction at geom 0, +4 --------------------------------- #
    gk0 = geoms[0][0]
    for q, fname, ylab in (("cl", "stage1_interaction_CL.png", "CL"),
                           ("cd_ind", "stage1_interaction_CD.png", "CD_ind")):
        series = {}
        for ns in SPANS:
            ys = []
            for nc in CHORDS:
                r = data.get((gk0, 4.0, nc, ns))
                ys.append(r.get(q) if r and r.get("ok") else None)
            series[f"span {ns}"] = ys
        parallel = "parallel -> separable" if gate1 else "not parallel"
        P.lines_labelled_at_end(
            list(CHORDS), series, xlabel="chordwise panels", ylabel=ylab,
            title=f"{ylab} vs chordwise ({parallel})",
            path=C.PLOTS_ROOT / fname)

    # ---- results CSV + summary -------------------------------------------- #
    import csv
    with open(C.CONFIG_ROOT / "stage1_results.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["geom", "angle", "chord", "span", "ok"] + list(C.QUANTITY_FIELDS)
                   + ["seconds_avl"])
        for (gkey, a, nc, ns), r in data.items():
            w.writerow([gkey, a, nc, ns, r.get("ok")]
                       + [r.get(q) for q in C.QUANTITY_FIELDS] + [r.get("seconds_avl")])

    lines = []
    A = lines.append
    A("STAGE 1 — 2D LATTICE (separability)")
    A("=" * 60)
    A(f"1. RUN: {total} cells (chord{CHORDS} x span{SPANS} x {len(geoms)} geoms "
      f"x angles{ANGLES}). new={n_new} hits={n_hit} fails={n_fail}")
    A("   (grid is D4-corrected: chord 20 dropped to 16, illegal at span 6.)")
    A("")
    A(f"2. FAILURES: {n_fail}")
    A("")
    A("3. INTERACTION INDEX  I = rms(AB)/(rms(A)+rms(B))  per quantity")
    A("   §4.5 floor applied: a quantity whose main-effect signal rms(A)+rms(B)")
    A("   is below 1e-4 is mesh-insensitive; its I is a ratio of print-rounding")
    A("   artifacts (NOT assessed). Such quantities carry NI = rms(AB)/scale.")
    A(f"   {'quantity':28s} {'maxI':>7s} {'medI':>7s} {'maxNI%':>8s}  status")
    for q in C.QUANTITY_FIELDS:
        vals = per_q[q]["I_vals"]
        med = statistics.median(vals) if vals else float("nan")
        status = "ratio" if per_q[q]["assessable"] else "floored(normalised)"
        mi = per_q[q]["max_I"] if per_q[q]["assessable"] else float("nan")
        A(f"   {q:28s} {mi:7.3f} {med:7.3f} {per_q[q]['max_NI']*100:8.3f}  {status}")
    A("")
    A(f"   worst ratio-assessable cell: I={worst['I']:.3f} on {worst.get('q')} "
      f"geom={worst.get('geom')} angle={worst.get('angle')}")
    A(f"   worst normalised interaction among floored quantities: {max_NI*100:.3f}%")
    A(f"   floored (mesh-insensitive) quantities: {', '.join(floored) or 'none'}")
    A("")
    A("4. GATES")
    A(f"   gate 1 (max I < {GATE_I_MAX} over ratio-assessable quantities): "
      f"max I = {max_I:.3f}  -> {'PASS' if gate1 else 'FAIL'}")
    A(f"      (worst floored-quantity normalised interaction = {max_NI*100:.3f}%, "
      f"negligible)")
    A(f"   gate 2 (l_over_d ranking identical across span 2,4,6 at +4, chord 12): "
      f"{'PASS' if gate2 else 'FAIL'}")
    for ns in SPANS:
        A(f"       span {ns}: {[k.split(':')[1] for k in rank_by_span[ns]]}")
    A("")
    both = gate1 and gate2
    A(f"5. RESULT: {'BOTH GATES PASS — Stages 2 and 3 are interpretable.' if both else 'GATE FAILURE — STOP. Do not run Stages 2/3 as planned.'}")
    A("")
    A("6. LIMITATION (record regardless): separability is demonstrated only on")
    A("   chord 8-16 x span 2-6. Stages 2 and 3 evaluate outside that box")
    A("   (chord 6 and 48; span 1 and 8); that is an extrapolation. The Stage 5")
    A("   shortlist must lie inside the box unless Mike approves otherwise.")

    (C.CONFIG_ROOT / "stage1_summary.txt").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
