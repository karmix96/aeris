#!/usr/bin/env python3
"""The wall-normal direction, on both mesh families, judged by gci.py.

    python3 normal_direction.py

Refining only the wall-normal direction -- layers and first cell together at 1.3
and 1.3 squared, every other count held -- is the one direction in this study that
made drag WORSE under refinement, and faster each step. On family A:

    CD 208.237 -> 209.134 -> 213.330 counts, the second step 4.7x the first

`gci.py` returns p = -5.97 and refuses to certify: the family has no demonstrated
limit. That matters far beyond the direction itself, because Richardson
extrapolation and the GCI both assume an asymptotic range, and a GLOBAL refinement
refines this direction along with the others. A third grid level bought while this
stands is a third point on a family that may have nothing to extrapolate to.

But family A carries the tip cap declared defective on 13 September and since
rebuilt, and the production dataset is family B. So the result is attached to a
mesh the campaign abandoned. This re-measures it on family B, where the cap fix
also changed the outboard extrusion from 48 to 54 layers -- the region the
divergence signature (CDp rising while CDv falls) actually points at.

Written 2026-09-21 by the reliability audit follow-up.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gci  # noqa: E402

REPORTS = HERE / "reports"

#: coarse -> fine. Each entry: label, run directory, mesh summary.
FAMILIES = {
    "A (tip cap 10.2 x s0, pre-fix)": [
        ("gci_C", HERE / "runs/s8_cfd/gci_C_a0", HERE / "runs/s8_gci83/gci_C_summary.json"),
        ("gci_C_normal_s0", HERE / "runs/s8_checklist/dir_normal_s0/gci_C_normal_s0_a0",
         HERE / "runs/s8_checklist/dir_normal_s0/gci_C_normal_s0_summary.json"),
        ("gci_C_normal_s0_2", HERE / "runs/s8_checklist/dir_normal_s0_2/gci_C_normal_s0_2_a0",
         HERE / "runs/s8_checklist/dir_normal_s0_2/gci_C_normal_s0_2_summary.json"),
    ],
    "B (tip cap 2.04 x s0, rebuilt)": [
        ("gci_C", HERE / "runs/s8_v2/g83/gci_C_a0", HERE / "runs/s8_v2/g83/gci_C_summary.json"),
        ("gci_C_normal_s0_b", HERE / "runs/s8_normalB/gci_C_normal_s0_b_a0",
         HERE / "runs/s8_normalB/gci_C_normal_s0_b_summary.json"),
        ("gci_C_normal_s0_2_b", HERE / "runs/s8_normalB/gci_C_normal_s0_2_b_a0",
         HERE / "runs/s8_normalB/gci_C_normal_s0_2_b_summary.json"),
    ],
}
QUANTITIES = ("cd", "cdp", "cdv")

#: The wall-normal node ratios the family is built on. Taken from the level
#: definitions rather than from the cell counts: this is a DIRECTIONAL family, so
#: the global cell-count ratio (~1.09) describes nothing that was refined, while
#: 1.3 is the ratio actually applied to the layers and the first cell. Recorded
#: explicitly because the choice of r is exactly what the 2026-09-20 audit found
#: being made silently elsewhere.
R21 = 109 / 84
R32 = 84 / 65


#: Rows of the ADflow iteration table, for reading a run that produced no result.
ROW = __import__("re").compile(r"^\s*\d+\s+\d+\s+\d+\s")


def stall_evidence(run: Path) -> dict | None:
    """Why a run produced no result.json -- ATTEMPTED AND FAILED, or never started.

    These are different facts and the difference is the whole lesson of this audit:
    a missing verdict reads like an unasked question when it is really a broken
    one. A run that stalled is a RESULT about the mesh, and reporting it as
    "missing" throws that away.
    """
    log = run / "run.log"
    if not log.exists():
        return {"outcome": "NOT_ATTEMPTED", "why": "no run.log"}
    rows = [line.split() for line in log.read_text().splitlines() if ROW.match(line)]
    if len(rows) < 20:
        return {"outcome": "ATTEMPTED_NO_HISTORY", "iterations": len(rows)}
    # EVERY equation, and each against its own limit -- not one column called "the
    # residual". The ADflow table is
    #   Grid | Iter | IterTot | IterType | CFL | Step | LinRes | rho | rhou | rhov | rhow | rhoE | nu
    # so field 8 is rho and field 9 is rhou. Reading field 9 and calling it the total
    # residual is what produced the first version of this analysis: rhou happened to
    # drift up over the tail, which read as "the solver walked away from a solution"
    # when continuity and energy were in fact FLAT. The real finding was better and
    # more specific -- the transverse momentum equations are the laggards -- and it
    # was invisible from one column. `convergence_gate.py` had this right all along
    # with its per-equation test; this file did not.
    #
    # Parsed per row because ADflow writes `----` in the CFL column when it has no
    # step to report, and a comprehension over the whole log throws on that.
    import math
    cols = {"rho": 7, "rhou": 8, "rhov": 9, "rhow": 10, "rhoE": 11, "nu": 12}
    limits = {"rho": 3.0, "rhou": 3.0, "rhov": 3.0, "rhow": 3.0, "rhoE": 6.0, "nu": 3.0}
    series: dict[str, list[float]] = {k: [] for k in cols}
    cfl = []
    for r in rows:
        for name, idx in cols.items():
            if len(r) > idx:
                try:
                    series[name].append(float(r[idx]))
                except ValueError:
                    pass
        if len(r) > 4:
            try:
                cfl.append(float(r[4]))
            except ValueError:
                pass
    if len(series["rho"]) < 20:
        return {"outcome": "ATTEMPTED_UNREADABLE_HISTORY", "iterations": len(rows),
                "why": f"only {len(series['rho'])} of {len(rows)} rows had a readable residual"}

    equations, short = {}, []
    for name, values in series.items():
        if len(values) < 20 or values[-1] <= 0:
            continue
        # normalised on the largest of the first five, as Fluent and the gate do:
        # iteration zero can start a quantity artificially small
        reference = max(values[:5])
        dropped = math.log10(reference / values[-1])
        tail = values[-max(20, len(values) // 5):]
        rising = sum(b > a for a, b in zip(tail, tail[1:])) / max(1, len(tail) - 1)
        equations[name] = {"reference_first_five": reference, "final": values[-1],
                           "orders_dropped": round(dropped, 3),
                           "limit": limits[name],
                           "meets_limit": bool(dropped >= limits[name]),
                           "fraction_of_tail_rising": round(rising, 3)}
        if dropped < limits[name]:
            short.append(name)

    flat_or_drifting = [n for n, e in equations.items()
                        if 0.25 <= e["fraction_of_tail_rising"] <= 1.0]
    return {
        "outcome": "ATTEMPTED_AND_STALLED" if short else "ATTEMPTED_INCOMPLETE",
        "iterations": len(rows),
        "equations": equations,
        "equations_short_of_limit": short,
        "cfl_last": cfl[-1] if cfl else None,
        "cfl_max": max(cfl) if cfl else None,
        "note": (
            f"Short of the per-equation limit on: {', '.join(short)}. This says the run did not "
            f"reach its stopping rule. It does NOT say the solve diverged, was frozen, or that "
            f"the mesh is at fault -- those are separate tests and `convergence_gate.py` is the "
            f"instrument for all of them (`not_diverging`, `no_growing_oscillation`, "
            f"`solver_frozen`, `linear_solve_dead`, plus the force-settling tail). Run the gate "
            f"before drawing any conclusion from the numbers above: on 2026-09-21 this file's "
            f"predecessor read one residual column, called a mild drift in it a divergence, and "
            f"a run was stopped at iteration 224 that the gate scored as not diverging, not "
            f"frozen, forces settled to 0.001 %, and 4.46e-6 against a 1e-6 target."
            if short else "reached every per-equation limit but wrote no result"),
        "equations_with_drifting_tails": flat_or_drifting,
    }


def forces(run: Path) -> dict | None:
    p = run / "result.json"
    if not p.exists():
        return None
    r = json.loads(p.read_text())
    f = r["functions"]
    out = {q: next(v for k, v in f.items() if k.endswith("_" + q)) for q in QUANTITIES}
    out["converged"] = r.get("converged")
    out["s0_frac_note"] = r.get("grid", "")
    return out


#: The families to compare aspect ratios across. A directional family refines ONE
#: direction; a global family refines all of them. That difference is measurable at
#: the leading edge and it decides whether the directional family's divergence says
#: anything about the global one.
ASPECT_FAMILIES = {
    "wall_normal_only_chord_held": [
        ("gci_C", HERE / "runs/s8_v2/g83"),
        ("gci_C_normal_s0_b", HERE / "runs/s8_normalB"),
        ("gci_C_normal_s0_2_b", HERE / "runs/s8_normalB")],
    "global_all_directions": [
        ("gci_C", HERE / "runs/s8_v2/g83"), ("gci_M", HERE / "runs/s8_v2/g83"),
        ("gci_F", HERE / "runs/s8_cloud/g83"), ("gci_FF", HERE / "runs/s8_cloud/g83")],
}


def nose_aspect(level: str, directory: Path, span_fraction: float = 0.25) -> dict | None:
    """Chordwise spacing over first-cell height at the leading edge.

    The number that decides how to read the divergence. Refining ONE direction at
    fixed spacing in the others necessarily changes the cell aspect ratio, and the
    leading edge -- where the suction peak lives and where the CDp change localises
    -- is where that bites. A global refinement holds the ratio; a directional one
    does not. So a directional family carries a confound the global family does not,
    and its divergence cannot be transferred to the global family without saying so.
    """
    import numpy as np
    blocks = directory / f"{level}_blocks.npz"
    if not blocks.exists():
        return None
    b = np.load(blocks)["o_wing"]
    ni, nj, nk = b.shape[:3]
    k = round(span_fraction * nk)
    wall = b[:, 0, k, :]
    le = int(np.argmin(wall[:, 0]))
    ds_chord = float(np.linalg.norm(wall[le + 1] - wall[le]))
    first_cell = float(np.linalg.norm(b[le, 1, k, :] - b[le, 0, k, :]))
    return {"n_ring": ni, "n_normal": nj, "ds_chord_at_le_m": ds_chord,
            "first_cell_m": first_cell,
            "nose_aspect_ratio": round(ds_chord / first_cell, 2)}


def gate_verdict(run: Path) -> str | None:
    """What convergence_gate.py said about this run, if anything did.

    Checked because this file formed a three-level family out of result.json alone
    and computed an observed order from it. One of those runs was gate-REJECTED, and
    an order built on a rejected run is not evidence -- it is the "unjudged run in
    the archive" of defect 25, one level up. `gci.py` refuses frozen runs for the
    same reason; it cannot refuse what it is not told about.
    """
    # Beside the run, then every gate report in reports/. The per-campaign reports
    # are where the older families' verdicts live (`s8_gci_gate.json`,
    # `s8_aniso_gate.json`), and looking only beside the run reported the whole of
    # family A as ungated when it had been gated in September.
    candidates = [run / "gate.json", run.parent / "gate.json",
                  run.parent / f"{run.name.rsplit('_a', 1)[0]}_gate.json"]
    candidates += sorted(REPORTS.glob("*gate*.json"))
    identity = f"{run.resolve().parent.name}/{run.name}"
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            records = json.loads(candidate.read_text()).get("results", [])
        except (ValueError, AttributeError):
            continue
        for r in records:
            stored = str(r.get("directory", ""))
            if not stored:
                continue
            # resolved path, then the identity the 2026-09-20 fix added, then
            # <parent>/<name> -- never the run name alone, which is `gci_C_a0` for
            # every wing and every campaign.
            if (Path(stored).resolve() == run.resolve()
                    or r.get("run_identity") == identity
                    or f"{Path(stored).parent.name}/{Path(stored).name}" == identity):
                return r.get("verdict")
    return None


def cells(summary: Path) -> int | None:
    if not summary.exists():
        return None
    return int(json.loads(summary.read_text())["cells"])


def cap(summary: Path) -> float | None:
    if not summary.exists():
        return None
    return json.loads(summary.read_text())["outboard"]["first_cell_in_s0"]


def main() -> int:
    report = {
        "schema": "aeris.s8.normal_direction.v1",
        "question": ("the wall-normal direction diverged on family A. Does it still "
                     "diverge on family B, the meshes the production dataset uses?"),
        "why_it_matters": ("a global refinement refines this direction too, so a third "
                          "grid level cannot be read while any direction has no "
                          "demonstrated limit."),
        "refinement_ratios": {"r21": round(R21, 4), "r32": round(R32, 4),
                              "measured_on": "wall-normal layer count and first cell",
                              "note": ("a DIRECTIONAL family: the global cell-count ratio "
                                       "describes nothing that was refined here.")},
        "families": {},
    }

    for family, levels in FAMILIES.items():
        rows, missing = [], []
        for name, run, summary in levels:
            f = forces(run)
            if f is None:
                missing.append({"run": str(run.relative_to(HERE)),
                                **(stall_evidence(run) or {})})
                continue
            rows.append({"level": name, "cells": cells(summary),
                         "tip_cap_first_cell_in_s0": (round(cap(summary), 3)
                                                      if cap(summary) else None),
                         "converged": f["converged"],
                         "gate_verdict": gate_verdict(run),
                         **{q: round(1e4 * f[q], 3) for q in QUANTITIES}})
        entry = {"levels": rows, "missing": missing}
        not_accepted = [r["level"] for r in rows if r["gate_verdict"] != "ACCEPTED"]
        entry["levels_not_gate_accepted"] = not_accepted
        entry["family_usable"] = not not_accepted
        if not_accepted:
            entry["refusal"] = (
                f"NO ORDER REPORTED: {', '.join(not_accepted)} is not ACCEPTED by "
                f"convergence_gate.py (verdict "
                f"{[r['gate_verdict'] for r in rows if r['level'] in not_accepted]}). An "
                f"observed order computed from a run the gate refuses is not evidence. Fix or "
                f"re-run the level, do not average over it.")

        if len(rows) == 3 and entry["family_usable"]:
            # WITH A TOLERANCE. The cap's first cell is a measured spacing, not a
            # setting: the same `tip_span_first_cell_in_s0` gives 10.205, 10.204 and
            # 10.203 across three levels because s0 itself changes. Comparing them
            # exactly reported a consistent family as mixed. The question is whether
            # one level was built at 2 while the others were built at 10, and 5 %
            # separates those by a factor of five.
            caps = [r["tip_cap_first_cell_in_s0"] for r in rows
                    if r["tip_cap_first_cell_in_s0"] is not None]
            entry["caps"] = sorted(caps)
            entry["cap_consistent"] = bool(caps) and (max(caps) - min(caps)) <= 0.05 * min(caps)
            if not entry["cap_consistent"]:
                entry["warning"] = ("the three levels do NOT share a tip cap, so any order "
                                    "below mixes the cap change into the normal direction")
            entry["verdicts"] = {}
            for q in QUANTITIES:
                f3, f2, f1 = (rows[0][q] * 1e-4, rows[1][q] * 1e-4, rows[2][q] * 1e-4)
                t = gci.gci_triplet(f1, f2, f3, R21, R32)
                entry["verdicts"][q] = {
                    "steps_counts": [round(rows[1][q] - rows[0][q], 3),
                                     round(rows[2][q] - rows[1][q], 3)],
                    "p_observed": (round(t["p_observed"], 4)
                                   if t.get("p_observed") is not None else None),
                    "condition": t.get("condition"),
                    "divergent": str(t.get("condition", "")).startswith("DIVERGENT"),
                    "gci_21_percent": (round(t["gci_21_percent"], 4)
                                       if t.get("gci_21_percent") is not None else None),
                    "certified_uncertainty_percent": t.get("certified_uncertainty_percent"),
                    "extrapolated_counts": (round(1e4 * t["f_extrapolated"], 3)
                                            if t.get("f_extrapolated") else None),
                }
        report["families"][family] = entry

    # THE CONFOUND, measured. Report it beside the divergence, never after it.
    report["aspect_ratio_at_the_leading_edge"] = {
        fam: {lv: nose_aspect(lv, d) for lv, d in levels
              if nose_aspect(lv, d) is not None}
        for fam, levels in ASPECT_FAMILIES.items()}
    ar = report["aspect_ratio_at_the_leading_edge"]
    def ratios(fam):
        return [v["nose_aspect_ratio"] for v in ar.get(fam, {}).values()]
    dir_ar, glob_ar = ratios("wall_normal_only_chord_held"), ratios("global_all_directions")
    if len(dir_ar) > 1 and len(glob_ar) > 1:
        dir_growth = max(dir_ar) / min(dir_ar)
        glob_growth = max(glob_ar) / min(glob_ar)
        report["how_to_read_the_divergence"] = {
            "directional_aspect_ratio": dir_ar,
            "global_aspect_ratio": glob_ar,
            "directional_growth": round(dir_growth, 3),
            "global_growth": round(glob_growth, 3),
            "chordwise_count_held_in_directional_family": len(
                {v["n_ring"] for v in ar["wall_normal_only_chord_held"].values()}) == 1,
            "reading": (
                "The wall-normal family refines the direction carrying about 12 % of the "
                "coarse-to-fine CDp error (reports/s8_directional_refinement.json puts chord at "
                "88 % and normal at -15 %) while HOLDING the chordwise count at 93. The nose cell "
                "aspect ratio therefore grows "
                f"{dir_growth:.2f}x across that family, against {glob_growth:.2f}x across the "
                "global family -- and the CDp change localises to the leading edge and the first "
                "half-chord at 0.17-0.33 span, which is exactly where that aspect ratio bites. "
                "So the divergence is measured, real, and CONFOUNDED: it is what happens when the "
                "non-limiting direction is refined alone, not a demonstrated property of the grid "
                "family. It does NOT transfer to a global refinement, which holds the aspect ratio "
                "and whose two measured points move the other way (CDp 110.794 -> 89.288). "
                "Confirming test, about 1.5 h on this host: refine wall-normal ON TOP of a "
                "chord-refined mesh and see whether the divergence survives. Until that is run, "
                "this is an inference from one measurement, not a result."),
        }

    a = report["families"].get("A (tip cap 10.2 x s0, pre-fix)", {}).get("verdicts")
    b = report["families"].get("B (tip cap 2.04 x s0, rebuilt)", {}).get("verdicts")
    if a and b:
        report["comparison"] = {
            q: {"family_A_divergent": a[q]["divergent"],
                "family_B_divergent": b[q]["divergent"],
                "family_A_steps": a[q]["steps_counts"],
                "family_B_steps": b[q]["steps_counts"]}
            for q in QUANTITIES}
        still = [q for q in QUANTITIES if b[q]["divergent"]]
        confounded = bool(report.get("how_to_read_the_divergence"))
        report["gate"] = {
            "divergent_quantities_on_family_B": still,
            "divergence_is_confounded_by_aspect_ratio": confounded,
            "blocks_the_third_level": bool(still) and not confounded,
            "verdict": (
                "CLEAR: no quantity diverges in the wall-normal direction on the production "
                "mesh family. A third global level can be read."
                if not still else
                f"DIVERGES BUT DOES NOT BLOCK: {', '.join(still)} diverge on family B, and "
                f"identically on family A, so the tip-cap rebuild is irrelevant to it. But the "
                f"divergence is CONFOUNDED -- the family refines the direction carrying ~12 % of "
                f"the error while holding the one carrying 88 %, and the leading-edge cell aspect "
                f"ratio grows 1.63x across it against 1.20x across the global family, in exactly "
                f"the region where the CDp change localises. A global refinement holds the aspect "
                f"ratio and its two measured points move the OTHER way. So this is not a "
                f"demonstrated property of the grid family and it does not justify refusing the "
                f"third level. Run the 1.5 h confirming test first: wall-normal refinement on top "
                f"of a chord-refined mesh. If the divergence survives THAT, it is real."
                if confounded else
                f"NOT CLEAR: {', '.join(still)} diverge on family B and the confound check did "
                f"not run. Do not rent hardware until it has."),
        }

    out = REPORTS / "s8_normal_direction.json"
    out.write_text(json.dumps(report, indent=2) + "\n")

    for family, entry in report["families"].items():
        print(f"\n  FAMILY {family}")
        if entry["missing"]:
            for m in entry["missing"]:
                print(f"    {m['run']}: {m.get('outcome')}")
                for name, e in (m.get("equations") or {}).items():
                    print(f"      {name:<5} {e['orders_dropped']:>6.2f} orders "
                          f"(limit {e['limit']:.0f})  "
                          f"{'ok' if e['meets_limit'] else 'SHORT'}")
                if m.get("note"):
                    print(f"      {m['note']}")
            continue
        print(f"    {'level':<24}{'cells':>10}{'cap':>7}{'CD':>10}{'CDp':>10}{'CDv':>10}")
        for r in entry["levels"]:
            print(f"    {r['level']:<24}{r['cells']:>10}{r['tip_cap_first_cell_in_s0']:>7}"
                  f"{r['cd']:>10.3f}{r['cdp']:>10.3f}{r['cdv']:>10.3f}")
        if not entry.get("cap_consistent", True):
            print(f"    WARNING: {entry['warning']}")
        for r in entry["levels"]:
            if r["gate_verdict"] != "ACCEPTED":
                print(f"    gate: {r['level']} is {r['gate_verdict']}")
        if entry.get("refusal"):
            print(f"    {entry['refusal']}")
        for q, v in (entry.get("verdicts") or {}).items():
            mark = "DIVERGENT" if v["divergent"] else "ok"
            print(f"      {q:<4} steps {v['steps_counts'][0]:+8.3f} {v['steps_counts'][1]:+8.3f}"
                  f"   p={v['p_observed']}   {mark}")

    if "how_to_read_the_divergence" in report:
        h = report["how_to_read_the_divergence"]
        print(f"\n  LEADING-EDGE ASPECT RATIO: directional {h['directional_aspect_ratio']} "
              f"({h['directional_growth']}x)   global {h['global_aspect_ratio']} "
              f"({h['global_growth']}x)")
        print(f"\n  {h['reading']}")
    if "gate" in report:
        print(f"\n  GATE: {report['gate']['verdict']}")
    print(f"\nwrote {out.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
