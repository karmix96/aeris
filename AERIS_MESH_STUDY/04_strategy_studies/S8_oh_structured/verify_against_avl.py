#!/usr/bin/env python
"""Independent lift check: run AVL on the exact geometry S8 meshes.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/verify_against_avl.py

S8's CL at alpha 0 was wrong by a factor of five and a sign, and it went
unnoticed because nothing independent had ever been asked what the lift should
be.  This asks.

The comparison is as tight as it can be made: `strategy_s6.build_locked_surface`
is the same call `build_volume.py` uses, and the resulting pyGeo result is handed
straight to the native AVL writer.  AVL and ADflow therefore see the same loft,
the same twist distribution and the same sections -- not two models of the same
design.

What agreement would and would not mean:

* AVL is an inviscid vortex-lattice method on camber surfaces.  It carries the
  twist and camber, which is what sets CL at alpha 0 on a washed-out wing, so it
  should get the sign and rough magnitude right.
* It has no thickness, no boundary layer and no wake roll-up, so it typically
  runs a few per cent high on lift-curve slope.  Agreement to within about ten
  per cent is a good result; exact agreement would be suspicious.
* **Reference area is the trap.**  CL is a ratio, so it only transfers if each
  code divides by its own consistent area.  ADflow integrates a half model
  against a half reference area of 0.394918 m2; AVL builds a symmetric airplane
  and reports against its own Sref.  This script prints AVL's Sref against twice
  the ADflow half area and refuses to compare if they disagree, rather than
  quietly reporting a factor.

A failure here does not mean the CFD is wrong.  It means the two disagree, which
is a question, and the question is worth having before four hours of solver time
become a lift curve nobody has checked.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for extra in (
    REPO / "AERIS_MESH_STUDY/04_strategy_studies",
    REPO / "AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas",
):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

#: mission_authority_v1.yaml, authority_id s6_nominal_mission_20260830
MISSION = {"mach": 0.0837, "velocity_mps": 28.0, "altitude_m": 1500.0}
#: the reference contract the CFD runs use; ADflow gets the HALF area
ADFLOW_HALF_AREA_M2 = 0.394918242017589
#: converged S8 CFD results, filled in as they land
CFD = {0.0: -0.15996287669606987}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set-name", default="lhs100_seed42")
    ap.add_argument("--index", type=int, default=83)
    ap.add_argument("--alphas", type=float, nargs="+", default=[-2.0, 0.0, 4.0, 8.0])
    ap.add_argument("--out", type=Path,
                    default=REPO / "AERIS_MESH_STUDY/artifacts/s8_cfd/avl_verification")
    # Lift is what this script exists to check, and AVL's lift is inviscid: the
    # viscous path only adds a NeuralFoil profile-drag correction on top. It is
    # also what made the first attempt time out, because it builds per-section
    # CST polars for all 29 sections before AVL is ever called. Off by default.
    ap.add_argument("--viscous", action="store_true", default=False)
    ap.add_argument("--timeout-sec", type=int, default=900)
    ap.add_argument("--nchordwise", type=int, default=24)
    ap.add_argument("--spanwise-panels-per-section", type=int, default=4)
    #: the CFD moment reference, so both codes take moments about one point
    ap.add_argument("--moment-reference", type=float, nargs=3, default=[0.4, 0.0, 0.0])
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    import strategy_s6
    from aeris.aero.models import FlightCondition
    from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
        run_pygeo_native_avl_case,
    )

    print(f"building {args.set_name}[{args.index}] -- the same call build_volume.py makes")
    with tempfile.TemporaryDirectory() as tmp:
        # Defect 18 (see build_volume.py).  This called `build_locked_surface`, which builds an entire
        # S6 candidate_c01 SURFACE -- the C-family surface S8 exists to replace
        # -- purely so that `case.pygeo_result` could be read off the end of it.
        # S8 needs the pyGeo loft and nothing else, and it was inheriting S6's
        # own span-clustering constraints for free: on lhs100_seed42[0] the C01
        # spec raises "42 span cells capped at 0.025 m cannot cover the
        # 1.14972 m quarter-chord line" and S8 never got to build anything.
        # `build_pygeo_case` is the loft on its own.
        case = strategy_s6.build_pygeo_case(args.set_name, args.index, Path(tmp))
        if case.pygeo_result is None:
            raise RuntimeError("the canonical geometry config produced no pyGeo result")
    pygeo_result = case.pygeo_result
    sections = pygeo_result.extracted
    semispan = max(float(s.y_m) for s in sections)
    print(f"  {len(sections)} extracted sections, semispan {semispan:.6f} m")
    print(f"  twist at root / tip: {sections[0].twist_deg:+.3f} / "
          f"{sections[-1].twist_deg:+.3f} deg"
          if hasattr(sections[0], "twist_deg") else "")

    rows = []
    for alpha in args.alphas:
        condition = FlightCondition(alpha_deg=float(alpha), **MISSION)
        directory = args.out / f"alpha_{alpha:g}"
        directory.mkdir(parents=True, exist_ok=True)
        result = run_pygeo_native_avl_case(
            flight_condition=condition,
            output_dir=directory,
            pygeo_result=pygeo_result,
            semispan_m=semispan,
            viscous=args.viscous,
            timeout_sec=args.timeout_sec,
            nchordwise=args.nchordwise,
            spanwise_panels_per_section=args.spanwise_panels_per_section,
            # The CFD takes its moments about (0.4, 0, 0); AVL defaults to the
            # origin.  Transferring afterwards works and was checked against
            # AVL's own reported neutral point, but a moment comparison should
            # not depend on getting an arm right by hand -- set the same point
            # in both codes and the only remaining difference is c_ref, which is
            # a pure scale factor.
            moment_reference_m=tuple(args.moment_reference),
        )
        record = result if isinstance(result, dict) else getattr(result, "__dict__", {})
        rows.append({"alpha_deg": float(alpha), "raw": _plain(record)})
        status = _get(record, "status")
        cl = _get(record, "cl", "CL", "lift_coefficient")
        print(f"  alpha {alpha:>5.1f}: status={status}  CL={cl}")

    (args.out / "avl_sweep.json").write_text(json.dumps(rows, indent=2, default=str) + "\n")
    # Record the moment reference that was USED, next to the numbers it applies
    # to.  Without this the file is a set of moment coefficients about an
    # unstated point, and a consumer has no way to know whether an arm still
    # needs applying.  plot_sweep.py guessed from the OUTPUT DIRECTORY NAME
    # ("xref04" in the path), so running this script into any other directory
    # silently made it transfer an arm that had already been applied -- which
    # put the AVL neutral point 63 mm AHEAD of the leading edge and turned a
    # 3.7 %-of-MAC agreement into an apparent factor-of-ten disagreement.
    # That is defect 17 again (PLAN 0.7): a stability "disagreement" that was
    # a convention error, not physics.
    (args.out / "avl_reference.json").write_text(json.dumps({
        "moment_reference_m": list(args.moment_reference),
        "avl_c_ref_note": "AVL reports Cm about the point above, scaled by ITS "
                          "own c_ref, which is not the CFD's chordRef. Only the "
                          "chord scale differs once the point is shared.",
        "cfd_moment_reference_m": [0.4, 0.0, 0.0],
        "arm_already_applied": True,
        "set_name": args.set_name, "index": args.index,
    }, indent=2) + "\n")
    # Defect 23. The docstring has always said this script "refuses to compare if
    # they disagree". There was no code that did. Nine pilot geometries were then
    # compared against CFD normalised by a different wing's area, and the
    # resulting -25 to +32 per cent "disagreement" was reported as a finding
    # about AVL. A promise in a docstring is not a check.
    s_ref = next((float(r["raw"]["s_ref"]) for r in rows
                  if isinstance(r.get("raw"), dict) and r["raw"].get("s_ref")), None)
    table = Path(__file__).resolve().parent / "reference_areas.json"
    entry = (json.loads(table.read_text()).get("areas", {}).get(str(args.index))
             if table.exists() else None)
    cfd_half = float(entry["half_area_m2"]) if entry else ADFLOW_HALF_AREA_M2
    mismatch = abs((s_ref / 2.0) / cfd_half - 1.0) if s_ref else None
    ref_path = args.out / "avl_reference.json"
    ref = json.loads(ref_path.read_text())
    ref.update({"avl_s_ref_m2": s_ref, "cfd_half_area_m2": cfd_half,
                "cfd_area_source": "reference_areas.json" if entry else "legacy index-83 constant",
                "area_mismatch_fraction": mismatch})
    ref_path.write_text(json.dumps(ref, indent=2) + "\n")
    if mismatch is None or mismatch > 0.005:
        print(f"\nREFUSING TO COMPARE. AVL half area "
              f"{(s_ref / 2.0 if s_ref else float('nan')):.5f} m2, CFD reference "
              f"{cfd_half:.5f} m2 ({'from reference_areas.json' if entry else 'the legacy index-83 constant'}). "
              f"A lift coefficient divided by a different wing's area is not comparable.")
        return 1
    _report(rows)
    return 0


def _plain(record):
    out = {}
    for key, value in (record or {}).items():
        try:
            json.dumps(value)
            out[key] = value
        except TypeError:
            out[key] = str(value)
    return out


def _get(record, *names):
    for name in names:
        if isinstance(record, dict) and name in record:
            return record[name]
        if hasattr(record, name):
            return getattr(record, name)
    return None


def _report(rows) -> None:
    print(f"\n{'alpha':>7}{'AVL CL':>12}{'S8 CFD CL':>12}{'difference':>13}")
    for row in rows:
        alpha = row["alpha_deg"]
        cl = _get(row["raw"], "cl", "CL", "lift_coefficient")
        cfd = CFD.get(alpha)
        if cl is None:
            print(f"{alpha:>7.1f}{'FAILED':>12}{'':>12}{'':>13}")
            continue
        if cfd is None:
            print(f"{alpha:>7.1f}{cl:>12.6f}{'not yet':>12}{'':>13}")
        else:
            print(f"{alpha:>7.1f}{cl:>12.6f}{cfd:>12.6f}{cl - cfd:>+13.6f}")
    usable = [(r["alpha_deg"], _get(r["raw"], "cl", "CL", "lift_coefficient"))
              for r in rows]
    usable = [(a, c) for a, c in usable if c is not None]
    if len(usable) >= 2:
        usable.sort()
        (a0, c0), (a1, c1) = usable[0], usable[-1]
        print(f"\nAVL lift-curve slope over {a0:g} to {a1:g} deg: "
              f"{(c1 - c0) / (a1 - a0):.5f} per degree")


if __name__ == "__main__":
    raise SystemExit(main())
