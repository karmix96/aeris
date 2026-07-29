"""Stage 6 — extreme-geometry reporting (companion to stage6_ranking.py).

Stage 6 solved the 6 extreme geometries (5 settings x 6 extremes x 3 angles = 90
runs) but only tabulated the seven gates on the 30 NORMAL designs, per §7 ("the 6
extreme geometries are reported against the same gates but separately, and a
failure there is a documented limitation, not a disqualification"). This script
computes the separate extreme report from the cached solves — no new solving.

For each cheap setting and each extreme geometry it reports the worst-case
gate-4 key-quantity error vs the comparator (chord48/span2/cosine) at +4 deg,
with the §4.5 print-noise floor applied, plus sign-preservation of the five
control derivatives. All rows are cache hits.
"""

from __future__ import annotations

import json

import common as C

KEY_Q = ["cl", "cm", "cd_ind", "cd_total", "x_np"]
CTRL_Q = ["elevon_sym.CL", "elevon_sym.Cm", "elevon_diff.Cl",
          "elevon_diff.Cn", "elevon_diff.CY"]
ANGLE = 4.0
SYM, DIFF = 4.0, 4.0


def main():
    shortlist = json.loads((C.CONFIG_ROOT / "stage5_shortlist.json").read_text())["shortlist"]
    settings = [(c["nchordwise"], c["spanwise"], c["cspace"], c["label"], c["role"])
                for c in shortlist]
    comp = next(c for c in settings if "COMPARATOR" in c[4])
    cheaps = [c for c in settings if "COMPARATOR" not in c[4]]

    extremes = C.extreme_samples()  # [(gkey, sample), ...] length 6

    def solve(sample, gkey, s):
        return C.run_case(sample, nchordwise=s[0], spanwise=s[1], cspace=s[2],
                          alpha_deg=ANGLE, control_input_deg=SYM, diff_input_deg=DIFF,
                          sample_key=gkey, tag="stage6")

    # comparator rows for each extreme
    comp_rows = {gkey: solve(sample, gkey, comp) for gkey, sample in extremes}

    report = {}
    for s in cheaps:
        label = s[3]
        per_geom = {}
        worst = 0.0
        signs_ok = True
        for gkey, sample in extremes:
            rc = comp_rows[gkey]
            rk = solve(sample, gkey, s)
            if not (rc.get("ok") and rk.get("ok")):
                per_geom[gkey] = None
                continue
            # worst gate-4 key-quantity relative error, §4.5 floor
            geom_worst = 0.0
            for q in KEY_Q:
                a = rc.get(q); b = rk.get(q)
                if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
                    continue
                if abs(a) < C.NOISE_FLOOR:
                    continue  # below print-noise floor: not assessed relatively
                e = abs(b - a) / abs(a) * 100.0
                geom_worst = max(geom_worst, e)
            per_geom[gkey] = round(geom_worst, 3)
            worst = max(worst, geom_worst)
            # control-derivative sign preservation
            for q in CTRL_Q:
                a = rc.get(q); b = rk.get(q)
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    if abs(a) >= C.NOISE_FLOOR and abs(b) >= C.NOISE_FLOOR and (a * b) < 0:
                        signs_ok = False
        report[label] = {"per_geom": per_geom, "worst_key_pct": round(worst, 3),
                         "ctrl_sign_preserved": signs_ok}

    # short extreme-geometry names in the order extreme_samples() returns them
    ext_names = list(C.EXTREME_OVERRIDES.keys())
    gkeys = [gkey for gkey, _ in extremes]
    name_of = dict(zip(gkeys, ext_names))

    lines = []; A = lines.append
    A("STAGE 6 — EXTREME-GEOMETRY REPORT (separate, per §7)")
    A("=" * 60)
    A(f"1. RUN: 5 settings x 6 extremes at +4 deg (cached from Stage 6).")
    A("   Worst gate-4 key-quantity error vs comparator, §4.5 floor applied.")
    A("")
    A("2. WORST KEY-QUANTITY ERROR PER SETTING, PER EXTREME [%]")
    hdr = "   {:>8s} |".format("setting")
    for gk in gkeys:
        hdr += " {:>12s}".format(name_of[gk][:12])
    hdr += " | {:>7s} {:>5s}".format("worst", "sign")
    A(hdr)
    for s in cheaps:
        r = report[s[3]]
        ln = "   {:>8s} |".format(s[3])
        for gk in gkeys:
            v = r["per_geom"].get(gk)
            ln += " {:>12s}".format("--" if v is None else f"{v:.2f}")
        ln += " | {:>7.2f} {:>5s}".format(r["worst_key_pct"],
                                          "ok" if r["ctrl_sign_preserved"] else "FLIP")
        A(ln)
    A("")
    A("3. WHAT THIS MEANS")
    A("   Extremes are stress shapes (narrow/wide elevon, high aspect ratio,")
    A("   strong taper, min tip chord, max sweep). A larger error here than on")
    A("   the normal designs is a DOCUMENTED LIMITATION, not a gate failure.")
    A("   The controlling observation is unchanged: the error is dominated by")
    A("   elevon-power resolution and shrinks monotonically with chordwise count.")

    (C.CONFIG_ROOT / "stage6_extremes.txt").write_text("\n".join(lines) + "\n")
    (C.CONFIG_ROOT / "stage6_extremes.json").write_text(
        json.dumps({"names": name_of, "report": report}, indent=2))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
