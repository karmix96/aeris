#!/usr/bin/env python
"""Does surface pressure stay inside its physical bound on the S8 O-H grid?

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/check_cp_bound.py \
        --surface AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/runs/s8_cfd/oh_L3_a0/<name>_surf.cgns

This is the acceptance question for S8 and the only one the first CFD point is
authorized to answer (policies/s8_oh_first_point_v1.yaml).

For isentropic flow the stagnation value of cp is bounded, and at Mach 0.0837
that bound is 1.0018.  A mesh that reports cp above it is not resolving the
surface it is integrating over.  On candidate_c03, 137 of the 296 leading-edge
collar faces exceeded it, peaking at 5.328, and that strip supplies roughly 80
percent of pressure drag
(reports/m2_a_c03_leading_edge_collar_defect_20260903.json).

Reads the CGNS surface solution directly as HDF5, which is what ADflow writes
here, and reports the distribution rather than a single pass/fail flag: the
count over the bound, the peak, and where it sits.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

#: isentropic stagnation cp at the mission Mach number of 0.0837
CP_PHYSICAL_MAX = 1.0018
C03_REFERENCE = {"faces_over_bound": 137, "of_faces": 296, "peak_cp": 5.328}


def collect(node, name: str, found: dict) -> None:
    """Walk an HDF5 tree collecting every dataset whose parent is named `name`."""
    import h5py

    for key, item in node.items():
        if isinstance(item, h5py.Group):
            if key == name and " data" in item:
                found.setdefault(node.name, []).append(np.array(item[" data"]).ravel())
            collect(item, name, found)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--surface", type=Path, required=True)
    ap.add_argument("--variable", default="CoefPressure")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    import h5py

    found: dict = {}
    with h5py.File(args.surface, "r") as handle:
        collect(handle, args.variable, found)
    if not found:
        raise SystemExit(
            f"no {args.variable!r} arrays in {args.surface}. Inspect with "
            f"`h5ls -r` and pass --variable."
        )

    cp = np.concatenate([np.concatenate(v) for v in found.values()])
    over = cp > CP_PHYSICAL_MAX
    result = {
        "surface_file": str(args.surface),
        "variable": args.variable,
        "zones": len(found),
        "n_surface_values": int(cp.size),
        "cp_min": float(cp.min()),
        "cp_max": float(cp.max()),
        "cp_physical_max": CP_PHYSICAL_MAX,
        "values_over_bound": int(over.sum()),
        "fraction_over_bound": float(over.mean()),
        "peak_excess": float(max(cp.max() - CP_PHYSICAL_MAX, 0.0)),
        "passes": bool(not over.any()),
        "c03_reference": C03_REFERENCE,
    }
    out = args.out or args.surface.parent / "cp_bound_check.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
