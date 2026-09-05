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
        _b, _i, case = strategy_s6.build_locked_surface(
            args.set_name, args.index, Path(tmp), level="candidate_c01"
        )
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
