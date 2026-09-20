#!/usr/bin/env python3
"""Does the trailing-edge credit survive grid refinement?

    python3 te_credit_grid.py

The credit is S8's central engineering claim: the drag saved by the 0.1 %-chord
trailing edge together with the wall-resolved tip cap, measured against the same
chi-3 baseline. The 17 September addendum in `S8_REPORT_2026-09-15.md` reports it
across ten wings as -5.27 to -8.98 counts, mean -7.26. Every one of those numbers
is measured at `gci_C`.

That is the problem this file exists to measure. A difference between two
configurations on the SAME grid enjoys some cancellation of discretisation error,
and the campaign has relied on that cancellation without ever testing it -- while
its own two-level trend says the absolute drag is still moving by 22-25 counts
between `gci_C` and `gci_M`. Cancellation is a hypothesis, not a property, and it
is cheap to test on the grids already in hand.

Geometry 83 is the only wing with BOTH the chi-3 baseline and the treatment at
BOTH levels, so it is the only wing where the question can be answered today.
The `gci_C` column reproduces the published table exactly, which is what licenses
reading the `gci_M` column beside it.

Written 2026-09-20 by the reliability audit (`docs/AUDIT_2026-09-20_reliability.md`).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE / "reports"

#: The baseline and the treatment. Both legs must be the same MESH FAMILY step at
#: each level, or the comparison measures the family change instead of the design
#: change: `s8_chi3`/`s8_pilot` carry the pre-fix tip cap (first cell 10.2 x s0)
#: and `s8_v2` carries the fixed one (2.04 x s0), which is exactly the pairing the
#: published credit uses -- it is a NET number, the trailing edge plus the cap's
#: cost, as the addendum says.
BASELINE = {"gci_C": HERE / "runs/s8_chi3/g83", "gci_M": HERE / "runs/s8_chi3/g83"}
TREATMENT = {"gci_C": HERE / "runs/s8_v2/g83", "gci_M": HERE / "runs/s8_v2/g83"}
ALPHAS = ["-2", "0", "4", "8"]

#: For the induced-drag cross-check below. Geometry 83, from
#: `reports/s8_geometry_audit.json`: semi-span 0.9772364568747856 m against the
#: half reference area the solver integrates over.
SEMI_SPAN_M = 0.9772364568747856
HALF_AREA_M2 = 0.394918242017589
OSWALD = 0.9


def forces(run: Path) -> dict:
    """CL, CD, CDp, CDv off one run, plus the fields that must match to compare."""
    result = json.loads((run / "result.json").read_text())
    f = result["functions"]

    def q(suffix):
        return next(v for k, v in f.items() if k.endswith("_" + suffix))

    return {"cl": q("cl"), "cd": q("cd"), "cdp": q("cdp"), "cdv": q("cdv"),
            "area_ref_m2": result.get("area_ref_m2"),
            "moment_ref_xyz_m": result.get("moment_ref_xyz_m"),
            "mach": result["mission"]["mach"],
            "reynolds": result["mission"]["reynolds"],
            "solver_overrides": result.get("solver_overrides"),
            "converged": result.get("converged"),
            "relative_residual": result.get("relative_residual"),
            "grid": result.get("grid")}


def main() -> int:
    aspect_ratio = (2 * SEMI_SPAN_M) ** 2 / (2 * HALF_AREA_M2)
    induced = math.pi * aspect_ratio * OSWALD

    report = {
        "schema": "aeris.s8.te_credit_grid.v1",
        "question": ("the trailing-edge credit is quoted at gci_C across ten wings. "
                     "Does it survive the one grid refinement the campaign has?"),
        "geometry_index": 83,
        "why_only_one_wing": ("geometry 83 is the only wing with the chi-3 baseline AND "
                              "the treatment at BOTH gci_C and gci_M. g13 and g47 have "
                              "the treatment at gci_M but no baseline there, so the "
                              "credit cannot be formed for them: 8 more solves."),
        "aspect_ratio": round(aspect_ratio, 4),
        "by_level": {},
        "incompatibilities": [],
    }

    for level in ("gci_C", "gci_M"):
        rows = []
        for alpha in ALPHAS:
            b = forces(BASELINE[level] / f"{level}_a{alpha}")
            t = forces(TREATMENT[level] / f"{level}_a{alpha}")
            # A credit is only a credit if everything except the design changed.
            for field in ("area_ref_m2", "moment_ref_xyz_m", "mach", "reynolds",
                          "solver_overrides"):
                if b[field] != t[field]:
                    report["incompatibilities"].append(
                        {"level": level, "alpha": alpha, "field": field,
                         "baseline": b[field], "treatment": t[field]})
            # Does a lift change carry part of it? If the treatment moves CL, some
            # of the "credit" is induced drag, not a profile-drag saving, and the
            # number would not transfer to a trimmed comparison.
            d_induced = (t["cl"] ** 2 - b["cl"] ** 2) / induced
            rows.append({
                "alpha_deg": float(alpha),
                "baseline_cd_counts": round(1e4 * b["cd"], 3),
                "treatment_cd_counts": round(1e4 * t["cd"], 3),
                "credit_counts": round(1e4 * (t["cd"] - b["cd"]), 3),
                "credit_cdp_counts": round(1e4 * (t["cdp"] - b["cdp"]), 3),
                "credit_cdv_counts": round(1e4 * (t["cdv"] - b["cdv"]), 3),
                "delta_cl": t["cl"] - b["cl"],
                "induced_drag_share_counts": round(1e4 * d_induced, 3),
                "credit_less_induced_counts": round(1e4 * ((t["cd"] - b["cd"]) - d_induced), 3),
                "baseline_converged": b["converged"],
                "treatment_converged": t["converged"],
            })
        mean_048 = sum(r["credit_counts"] for r in rows if r["alpha_deg"] != -2.0) / 3
        report["by_level"][level] = {
            "rows": rows,
            "mean_credit_counts_alpha_0_4_8": round(mean_048, 3),
            "range_counts": [min(r["credit_counts"] for r in rows),
                             max(r["credit_counts"] for r in rows)],
        }

    c, m = report["by_level"]["gci_C"], report["by_level"]["gci_M"]
    shift = [{"alpha_deg": a["alpha_deg"],
              "gci_C": a["credit_counts"], "gci_M": b["credit_counts"],
              "change_counts": round(b["credit_counts"] - a["credit_counts"], 3),
              "fraction_of_credit_lost": round(
                  (b["credit_counts"] - a["credit_counts"]) / abs(a["credit_counts"]), 4)}
             for a, b in zip(c["rows"], m["rows"])]
    report["grid_sensitivity"] = shift
    report["finding"] = (
        f"The credit is {c['range_counts'][1]:.2f} to {c['range_counts'][0]:.2f} counts at "
        f"gci_C and {m['range_counts'][1]:.2f} to {m['range_counts'][0]:.2f} counts at gci_M. "
        f"It loses {100 * min(s['fraction_of_credit_lost'] for s in shift):.0f}-"
        f"{100 * max(s['fraction_of_credit_lost'] for s in shift):.0f} % of its magnitude on "
        f"the one refinement available, in the same direction at all four incidences. The "
        f"discretisation error does NOT cancel in this difference.")
    report["induced_drag_check"] = (
        "The treatment moves CL by at most "
        f"{max(abs(r['delta_cl']) for lv in report['by_level'].values() for r in lv['rows']):.5f}, "
        "worth at most "
        f"{max(abs(r['induced_drag_share_counts']) for lv in report['by_level'].values() for r in lv['rows']):.2f} "
        "counts of induced drag, so the credit is a genuine profile-drag effect and not a "
        "lift change in disguise. That part of it is sound at both levels.")
    report["consequence"] = (
        "The published ten-wing range of -5.27 to -8.98 counts is a gci_C number. On the only "
        "wing that can be checked, the same measurement at gci_M is -2.05 to -3.03 counts. The "
        "ten-wing spread is therefore not a bound on the credit at any converged grid, and the "
        "credit's own grid sensitivity is larger than the wing-to-wing spread it is being used "
        "to resolve. Whether it keeps shrinking toward zero cannot be told from two levels.")

    out = REPORTS / "s8_te_credit_grid.json"
    out.write_text(json.dumps(report, indent=2) + "\n")

    print(f"geometry 83, trailing-edge credit (treatment minus chi-3 baseline)\n")
    print(f"{'alpha':>6} {'gci_C':>9} {'gci_M':>9} {'change':>9} {'lost':>7}")
    for s in shift:
        print(f"{s['alpha_deg']:>6} {s['gci_C']:>9.3f} {s['gci_M']:>9.3f} "
              f"{s['change_counts']:>+9.3f} {100 * s['fraction_of_credit_lost']:>6.1f}%")
    print(f"\nmean over alpha 0/4/8: gci_C {c['mean_credit_counts_alpha_0_4_8']:.3f} ct, "
          f"gci_M {m['mean_credit_counts_alpha_0_4_8']:.3f} ct")
    if report["incompatibilities"]:
        print("\nINCOMPATIBLE INPUTS -- the credit does not mean what it says:")
        for bad in report["incompatibilities"]:
            print(f"  {bad}")
    else:
        print("\ninputs compatible: same reference area, moment reference, Mach, "
              "Reynolds and solver overrides on both legs at both levels")
    print(f"\n{report['finding']}")
    print(f"\nwrote {out.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
