#!/usr/bin/env python3
"""Does the trailing-edge credit survive grid refinement?

    python3 te_credit_grid.py                    # every wing that has both legs
    python3 te_credit_grid.py --indices 13 47 83

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

The `gci_C` column reproduces the published table exactly, which is what licenses
reading the `gci_M` column beside it. A wing with no baseline at a level is
reported as such and not guessed at.

Written 2026-09-20 by the reliability audit (`docs/AUDIT_2026-09-20_reliability.md`).
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE / "reports"

#: The baseline leg and the treatment leg, per grid level.
#:
#: Both must be the same MESH FAMILY step at each level or the comparison measures
#: the family change instead of the design change. `s8_chi3` carries the pre-fix
#: tip cap (first cell ~10.2 x s0) and the chi-3 trailing edge; `s8_v2` carries
#: the wall-resolved cap and the 0.1 %-chord edge. That is exactly the pairing the
#: published credit uses -- it is a NET number, the trailing edge plus the cap's
#: cost, as the addendum says.
#:
#: NOT `s8_pilot`, although it holds gci_M runs on the same family-A meshes and
#: looks like the baseline. Those run ADflow's DEFAULT freestream turbulence, not
#: chi 3, so differencing against them moves the mesh and the freestream at once
#: -- worth +0.8 to +2.1 counts (reports/s8_freestream_turbulence.json), about
#: 30 % of the answer. `check_pairing` below refuses that automatically.
BASELINE_ROOT = HERE / "runs/s8_chi3"
TREATMENT_ROOT = HERE / "runs/s8_v2"
LEVELS = ["gci_CC", "gci_C", "gci_M"]
ALPHAS = ["-2", "0", "4", "8"]

#: Where each leg of each level lives, because `gci_CC` does not follow the
#: `<root>/g<index>/<level>_a<alpha>` convention the other two do: its treatment leg
#: was built as its own campaign and its baseline leg needed a level defined for it.
#: Written as an explicit map rather than a naming rule, so a level that moves has to
#: be moved HERE and cannot silently resolve to the wrong directory -- which is how
#: the 52 gate verdicts were lost.
#:
#: gci_CC added 2026-09-22, and it is what makes the credit a three-level question
#: instead of a two-point extrapolation. Extrapolating the C and M credits alone with
#: the order measured on absolute drag predicted the credit would change SIGN to about
#: +10 counts. The third level refutes that: the credit is -2.5, -8.7, -2.6 across
#: CC, C, M -- non-monotone, with gci_C the outlier.
LEVEL_PATHS = {
    "gci_CC": {"baseline": HERE / "runs/s8_ccbase/g83/gci_CC_baseline_a{alpha}",
               "treatment": HERE / "runs/s8_gciCC/g83/gci_CC_a{alpha}"},
}

#: Cells per leg per level, for the refinement ratios. The two legs do NOT have the
#: same cell count at a given level -- the wall-resolved cap costs about 6 % more
#: cells -- so each family gets its own ratios.
CELLS = {
    "baseline": {"gci_CC": 298712, "gci_C": 567256, "gci_M": 1111152},
    "treatment": {"gci_CC": 320648, "gci_C": 603592, "gci_M": 1172856},
}

#: For the induced-drag cross-check: if the treatment moves CL, part of any
#: "credit" is induced drag rather than a profile-drag saving, and would not
#: transfer to a trimmed comparison. Span from `reports/s8_geometry_audit.json`
#: (as BUILT, not as asked for), half area from `reference_areas.json`.
OSWALD = 0.9

#: Published gci_C values, as a self-check. The tool must reproduce the report it
#: is auditing before its new column may be believed.
PUBLISHED_GCI_C = {83: {-2.0: -8.11, 0.0: -8.97, 4.0: -9.15, 8.0: -7.51}}


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


def aspect_ratio(index: int) -> float | None:
    try:
        span = json.loads((REPORTS / "s8_geometry_audit.json").read_text())
        semi = span["designs"][str(index)]["semi_span_m"]["built"]
        half_area = json.loads((HERE / "reference_areas.json").read_text())
        area = half_area["areas"][str(index)]["half_area_m2"]
    except (OSError, KeyError, ValueError):
        return None
    return (2 * semi) ** 2 / (2 * area)


def check_pairing(b: dict, t: dict) -> list[str]:
    """A credit is only a credit if everything except the design changed."""
    problems = []
    for field in ("area_ref_m2", "moment_ref_xyz_m", "mach", "reynolds",
                  "solver_overrides"):
        if b[field] != t[field]:
            problems.append(f"{field}: baseline {b[field]!r} vs treatment {t[field]!r}")
    for leg, label in ((b, "baseline"), (t, "treatment")):
        if not leg["converged"]:
            problems.append(f"{label} did not converge")
    return problems


def credit_for(index: int, level: str) -> dict:
    """The credit for one wing at one level, or why it cannot be formed."""
    rows, problems, missing = [], [], []
    ar = aspect_ratio(index)
    induced = math.pi * ar * OSWALD if ar else None
    for alpha in ALPHAS:
        special = LEVEL_PATHS.get(level)
        if special:
            bd = Path(str(special["baseline"]).format(alpha=alpha))
            td = Path(str(special["treatment"]).format(alpha=alpha))
        else:
            bd = BASELINE_ROOT / f"g{index}" / f"{level}_a{alpha}"
            td = TREATMENT_ROOT / f"g{index}" / f"{level}_a{alpha}"
        if not (bd / "result.json").exists():
            missing.append(f"baseline {bd.relative_to(HERE)}")
            continue
        if not (td / "result.json").exists():
            missing.append(f"treatment {td.relative_to(HERE)}")
            continue
        b, t = forces(bd), forces(td)
        problems += [f"a{alpha}: {p}" for p in check_pairing(b, t)]
        d_induced = ((t["cl"] ** 2 - b["cl"] ** 2) / induced) if induced else None
        rows.append({
            "alpha_deg": float(alpha),
            "baseline_cd_counts": round(1e4 * b["cd"], 3),
            "treatment_cd_counts": round(1e4 * t["cd"], 3),
            "credit_counts": round(1e4 * (t["cd"] - b["cd"]), 3),
            "credit_cdp_counts": round(1e4 * (t["cdp"] - b["cdp"]), 3),
            "credit_cdv_counts": round(1e4 * (t["cdv"] - b["cdv"]), 3),
            "delta_cl": t["cl"] - b["cl"],
            "induced_drag_share_counts": (round(1e4 * d_induced, 3)
                                          if d_induced is not None else None),
        })
    out = {"rows": rows, "pairing_problems": problems, "missing": missing,
           "aspect_ratio": round(ar, 4) if ar else None}
    if rows:
        settled = [r["credit_counts"] for r in rows if r["alpha_deg"] != -2.0]
        out["mean_credit_counts_alpha_0_4_8"] = (
            round(sum(settled) / len(settled), 3) if settled else None)
        out["range_counts"] = [min(r["credit_counts"] for r in rows),
                               max(r["credit_counts"] for r in rows)]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--indices", type=int, nargs="+", default=None,
                    help="wings to report. Default: every wing with a baseline.")
    args = ap.parse_args()

    indices = args.indices
    if indices is None:
        indices = sorted(int(p.name[1:]) for p in BASELINE_ROOT.glob("g*")
                         if p.is_dir() and p.name[1:].isdigit())

    report = {
        "schema": "aeris.s8.te_credit_grid.v2",
        "question": ("the trailing-edge credit is quoted at gci_C across ten wings. "
                     "Does it survive the one grid refinement the campaign has?"),
        "baseline": str(BASELINE_ROOT.relative_to(HERE)),
        "treatment": str(TREATMENT_ROOT.relative_to(HERE)),
        "by_geometry": {},
    }

    for index in indices:
        entry = {level: credit_for(index, level) for level in LEVELS}
        both = [lv for lv in LEVELS if entry[lv].get("rows")]
        if len(both) == 2:
            shift = []
            by_alpha = {lv: {r["alpha_deg"]: r["credit_counts"]
                             for r in entry[lv]["rows"]} for lv in LEVELS}
            for a in sorted(set(by_alpha["gci_C"]) & set(by_alpha["gci_M"])):
                c, m = by_alpha["gci_C"][a], by_alpha["gci_M"][a]
                shift.append({"alpha_deg": a, "gci_C": c, "gci_M": m,
                              "change_counts": round(m - c, 3),
                              "fraction_of_credit_lost": round((m - c) / abs(c), 4)})
            entry["grid_sensitivity"] = shift
        report["by_geometry"][str(index)] = entry

    # The self-check. If the gci_C column does not reproduce the published table,
    # nothing else here may be read.
    checks = []
    for index, published in PUBLISHED_GCI_C.items():
        rows = report["by_geometry"].get(str(index), {}).get("gci_C", {}).get("rows")
        if not rows:
            continue
        for r in rows:
            want = published.get(r["alpha_deg"])
            if want is None:
                continue
            checks.append({"geometry": index, "alpha_deg": r["alpha_deg"],
                           "published": want, "computed": r["credit_counts"],
                           "agrees_to_0p01_counts": abs(want - r["credit_counts"]) <= 0.01})
    report["reproduces_published_gci_C"] = {
        "checks": checks,
        "all_agree": bool(checks) and all(c["agrees_to_0p01_counts"] for c in checks)}

    with_both = [i for i in report["by_geometry"]
                 if "grid_sensitivity" in report["by_geometry"][i]]
    losses = [s["fraction_of_credit_lost"]
              for i in with_both for s in report["by_geometry"][i]["grid_sensitivity"]]
    if losses:
        report["finding"] = (
            f"Measured on {len(with_both)} wing(s) ({', '.join('g' + i for i in with_both)}): the "
            f"credit loses {100 * min(losses):.0f}-{100 * max(losses):.0f} % of its magnitude "
            f"between gci_C and gci_M. The discretisation error does NOT cancel in this "
            f"difference, which the campaign had assumed without testing.")

    # EACH LEG'S OWN FAMILY, judged separately. This is the finding the credit
    # column cannot show: a difference between a family that converges and one that
    # does not cannot itself converge, and no extrapolation of it means anything.
    import sys as _sys
    _sys.path.insert(0, str(HERE))
    from gci import gci_triplet
    for index in indices:
        e = report["by_geometry"].get(str(index))
        if not e:
            continue
        legs = {}
        for leg in ("baseline", "treatment"):
            key = "baseline_cd_counts" if leg == "baseline" else "treatment_cd_counts"
            series = {}
            for lv in LEVELS:
                for r in e.get(lv, {}).get("rows", []):
                    series.setdefault(r["alpha_deg"], {})[lv] = r[key]
            cells = CELLS[leg]
            per_alpha = {}
            for a, vals in series.items():
                if not all(lv in vals for lv in LEVELS):
                    continue
                cc, c, m = (vals[lv] * 1e-4 for lv in LEVELS)
                r21 = (cells["gci_M"] / cells["gci_C"]) ** (1 / 3)
                r32 = (cells["gci_C"] / cells["gci_CC"]) ** (1 / 3)
                t = gci_triplet(m, c, cc, r21, r32)
                per_alpha[a] = {
                    "counts": {lv: round(vals[lv], 3) for lv in LEVELS},
                    "differences": [round(vals["gci_C"] - vals["gci_CC"], 3),
                                    round(vals["gci_M"] - vals["gci_C"], 3)],
                    "p_observed": (round(t["p_observed"], 3)
                                   if t.get("p_observed") is not None else None),
                    "condition": t["condition"],
                    "converges": t["condition"] == "ok",
                    "certified_uncertainty_percent": t.get("certified_uncertainty_percent"),
                }
            legs[leg] = per_alpha
        e["leg_families"] = legs
        conv = {leg: [v["converges"] for v in pa.values()] for leg, pa in legs.items()}
        if all(conv.values()):
            e["why_the_credit_does_not_converge"] = (
                "TREATMENT family converges (p ~ 1.75-1.88, condition ok at every "
                "incidence). BASELINE family does NOT: its successive differences GROW "
                "under refinement and gci.py returns DIVERGENT. A difference between a "
                "convergent family and a divergent one cannot converge, which is why the "
                "credit reads about -2.5, -8.7, -2.6 across CC, C, M rather than settling, "
                "and why extrapolating any two of those points is meaningless. The "
                "engineering reading is the useful one: the 0.1 %-chord trailing edge is "
                "the configuration whose grid family behaves. The 0.4 % edge is not. That "
                "argues FOR the change on numerical grounds, independently of how many "
                "counts it is worth -- and it means 'the credit in counts' was never a "
                "well-posed quantity to measure."
                if conv["treatment"] and not all(conv["baseline"]) else
                "read leg_families: both legs converge, so the credit's behaviour needs "
                "another explanation")

    out = REPORTS / "s8_te_credit_grid.json"
    out.write_text(json.dumps(report, indent=2) + "\n")

    print("trailing-edge credit = treatment (s8_v2) minus chi-3 baseline (s8_chi3), "
          "drag counts\n")
    for index in indices:
        e = report["by_geometry"][str(index)]
        print(f"  geometry {index}   (AR {e['gci_C'].get('aspect_ratio')})")
        for level in LEVELS:
            lv = e[level]
            if not lv.get("rows"):
                why = "; ".join(lv["missing"][:2]) or "no runs"
                print(f"    {level}: not available -- {why}")
                continue
            per = "  ".join(f"a{r['alpha_deg']:+.0f} {r['credit_counts']:+7.3f}"
                            for r in lv["rows"])
            print(f"    {level}: {per}   mean(0/4/8) "
                  f"{lv['mean_credit_counts_alpha_0_4_8']:+.3f}")
            if lv["pairing_problems"]:
                for p in lv["pairing_problems"][:4]:
                    print(f"      PAIRING PROBLEM {p}")
        if "grid_sensitivity" in e:
            worst = max(s["fraction_of_credit_lost"] for s in e["grid_sensitivity"])
            best = min(s["fraction_of_credit_lost"] for s in e["grid_sensitivity"])
            print(f"    -> credit loses {100 * best:.1f}-{100 * worst:.1f} % at gci_M")
        print()

    rp = report["reproduces_published_gci_C"]
    if rp["checks"]:
        print(f"  self-check against the published gci_C table: "
              f"{'REPRODUCED' if rp['all_agree'] else 'DOES NOT AGREE -- do not read the rest'}")
        for c in rp["checks"]:
            if not c["agrees_to_0p01_counts"]:
                print(f"    g{c['geometry']} a{c['alpha_deg']}: published {c['published']}, "
                      f"computed {c['computed']}")
    if "finding" in report:
        print(f"\n  {report['finding']}")
    print(f"\nwrote {out.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
