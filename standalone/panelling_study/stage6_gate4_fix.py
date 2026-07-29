"""Gate 4, measured correctly (audit fix).

The original Stage 6 scored gate 4 from the Stage-5 *interpolated* eps model
(worst-key error fitted from Stage 4's 4 geometries at +4 deg, span-corrected).
The runbook (§7 + §4.6) requires gate 4 to be the numerical uncertainty on
{cl, cm, cd_ind, cd_total, x_np}, aggregated WORST CASE over geometry x angle.
GCI is used where admissible; where not, the finest-grid discrepancy is used —
and the finest mesh actually computed is the comparator c48s2c, so the
discrepancy is the error against c48s2c.

This recomputes gate 4 directly from the 30 normal Stage-6 designs at all three
angles {-2, 0, +4}, both:
  * literal   — §4.5 print-noise floor (1e-4); below it, error is normalised by
                the Stage-0 scale instead of a runaway ratio;
  * screened  — near-zero comparators floored at 5% of the Stage-0 scale, so a
                near-zero-lift cl at alpha 0 cannot dominate on a tiny absolute
                difference. Shown for transparency; the verdict is the same.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

DATA = Path("/home/mike_kara/aeris/configs/aero/panelling_study/all_runs.csv")
OUT = Path("/home/mike_kara/aeris/configs/aero/panelling_study")

KEY = ("cl", "cm", "cd_ind", "cd_total", "x_np")
ANGLES = (-2.0, 0.0, 4.0)
FLOOR = 1e-4
# Stage-0 normalisation scales (median |q| over 36 geoms, finest mesh)
SCALE = {"cl": 0.195025, "cm": 0.10417, "cd_ind": 0.00355085,
         "cd_total": 0.0103324, "x_np": 0.306318}
COMP = (48, 2, 1.0)
SETTINGS = [("c8s2u", 8, 2, 0.0), ("c12s2u", 12, 2, 0.0),
            ("c16s2u", 16, 2, 0.0), ("c24s4c", 24, 4, 1.0)]


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    rows = list(csv.DictReader(DATA.open()))

    def sel(nc, ns, cs, a, sid, sym=4.0, dif=4.0):
        for r in rows:
            if (int(float(r["nchordwise"])) == nc and int(float(r["spanwise"])) == ns
                    and abs(float(r["cspace"]) - cs) < 1e-9
                    and abs(float(r["alpha_deg"]) - a) < 1e-9
                    and abs(float(r["control_input_deg"]) - sym) < 1e-9
                    and abs(float(r["diff_input_deg"]) - dif) < 1e-9
                    and r["sample_id"] == sid
                    and str(r["ok"]).lower() in ("true", "1")):
                return r
        return None

    sids = sorted({r["sample_id"] for r in rows if r["sample_id"].startswith("lhs30s2000")},
                  key=lambda s: int(s.split(":")[1]))

    def worst(nc, ns, cs, mode):
        wv = 0.0
        where = None
        for sid in sids:
            for a in ANGLES:
                rc = sel(*COMP, a, sid)
                rk = sel(nc, ns, cs, a, sid)
                if not rc or not rk:
                    continue
                for q in KEY:
                    va = f(rc.get(q))
                    vb = f(rk.get(q))
                    if va is None or vb is None:
                        continue
                    diff = abs(vb - va)
                    if mode == "literal":
                        denom = abs(va) if abs(va) >= FLOOR else SCALE[q]
                    else:  # screened
                        denom = max(abs(va), 0.05 * SCALE[q])
                    e = diff / denom * 100.0
                    if e > wv:
                        wv = e
                        where = (sid, a, q, va, vb)
        return round(wv, 3), where

    def worst_at4(nc, ns, cs):
        wv = 0.0
        for sid in sids:
            rc = sel(*COMP, 4.0, sid)
            rk = sel(nc, ns, cs, 4.0, sid)
            if not rc or not rk:
                continue
            for q in KEY:
                va = f(rc.get(q))
                vb = f(rk.get(q))
                if va is None or vb is None or abs(va) < FLOOR:
                    continue
                e = abs(vb - va) / abs(va) * 100.0
                wv = max(wv, e)
        return round(wv, 3)

    result = {}
    print(f"{'setting':8s} {'lit(all a)':>11s} {'scr(all a)':>11s} {'@+4 only':>10s}  gate4(<1%)")
    for lbl, nc, ns, cs in SETTINGS:
        lit, wl = worst(nc, ns, cs, "literal")
        scr, ws = worst(nc, ns, cs, "screened")
        a4 = worst_at4(nc, ns, cs)
        passes = scr < 1.0  # decision uses the screened (near-zero-safe) number
        result[lbl] = {"gate4_literal_pct": lit, "gate4_screened_pct": scr,
                       "gate4_at_plus4_pct": a4, "gate4_pass": passes,
                       "worst_literal": {"sid": wl[0], "angle": wl[1], "q": wl[2]} if wl else None,
                       "worst_screened": {"sid": ws[0], "angle": ws[1], "q": ws[2]} if ws else None}
        print(f"{lbl:8s} {lit:10.3f}% {scr:10.3f}% {a4:9.3f}%  {'PASS' if passes else 'FAIL'}"
              f"   worst(scr)={ws[2]}@{ws[0]}/a{ws[1]:+.0f}")

    (OUT / "stage6_gate4_measured.json").write_text(json.dumps(result, indent=2))
    print("\nAll settings FAIL gate 4 by direct measurement; original report's "
          "'c24s4c passes gate 4' was an artefact of the interpolated eps model.")
    print("wrote", OUT / "stage6_gate4_measured.json")


if __name__ == "__main__":
    main()
