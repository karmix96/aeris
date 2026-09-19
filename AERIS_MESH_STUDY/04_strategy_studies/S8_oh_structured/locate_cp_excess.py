#!/usr/bin/env python
"""Where does surface cp exceed its physical bound on an S8 O-H surface solution?

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/locate_cp_excess.py \
        --surface AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/runs/s8_cfd/oh_L3_a0/s8_a0_000_surf.cgns

`check_cp_bound.py` answers whether the bound is exceeded.  It cannot answer
where, because it concatenates every zone's cp array and throws the structure
away.  That was enough to rank S8 against C03 -- 30 cells against 137 -- and it
is not enough to fix the remaining 30, because "leading-edge resolution" and
"tip corner" and "trailing-edge base" are different defects with different
repairs and the aggregate number is identical under all three.

The surface zones are structured, so every cp cell has an (i, j) address and
four corner nodes.  This walks them and reports each over-bound cell with:

  * its ring index i and span index j, and i relative to the leading edge;
  * its cell-centre coordinates;
  * the local y+ and skin friction, which separate a resolution defect from a
    boundary-layer one;
  * whether it is a physical interior cell or a rind value.

Rind planes are ghost cells.  ADflow writes them into the same array and a rind
value is not a physical value, so they are reported apart and excluded from the
verdict -- the same separation `s8_oh_first_cfd_point_20260904.json` makes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

CP_PHYSICAL_MAX = 1.0018


def _data(group, name):
    """A CGNS DataArray_t child, as a numpy array."""
    return np.array(group[name][" data"])


def zones(handle):
    """Every Zone_t under the surface base, with its label."""
    base = handle["BaseSurfaceSol"]
    out = []
    for key in base:
        node = base[key]
        label = node.attrs.get("label", b"")
        if isinstance(label, bytes):
            label = label.decode()
        if label == "Zone_t":
            out.append((key, node))
    return out


def analyse_zone(name, node, le_index=None):
    """Locate over-bound cp in one structured surface zone."""
    solution = node["Flow solution"]
    coords = node["GridCoordinates"]
    xyz = np.stack(
        [_data(coords, f"Coordinate{axis}") for axis in "XYZ"], axis=-1
    )  # (nj, ni, 3)
    cp = _data(solution, "CoefPressure")  # (nj_cell + 2, ni_cell + 2), rind 1 each side
    yplus = _data(solution, "YPlus") if "YPlus" in solution else None
    cf = (
        _data(solution, "SkinFrictionMagnitude")
        if "SkinFrictionMagnitude" in solution
        else None
    )

    nj_node, ni_node = xyz.shape[0], xyz.shape[1]
    nj_cell, ni_cell = nj_node - 1, ni_node - 1
    if cp.shape != (nj_cell + 2, ni_cell + 2):
        raise SystemExit(
            f"{name}: cp {cp.shape} is not cell dims {(nj_cell, ni_cell)} plus one "
            f"rind layer each side; the rind assumption does not hold here"
        )

    # cell centres from the four corner nodes
    centres = 0.25 * (
        xyz[:-1, :-1] + xyz[1:, :-1] + xyz[:-1, 1:] + xyz[1:, 1:]
    )  # (nj_cell, ni_cell, 3)

    interior = cp[1:-1, 1:-1]
    over = interior > CP_PHYSICAL_MAX
    jj, ii = np.nonzero(over)

    def at(array, j, i):
        if array is None:
            return None
        return float(array[j + 1, i + 1])

    cells = []
    for j, i in zip(jj, ii):
        entry = {
            "i_ring": int(i),
            "j_span": int(j),
            "cp": float(interior[j, i]),
            "excess": float(interior[j, i] - CP_PHYSICAL_MAX),
            "xyz_m": [float(v) for v in centres[j, i]],
            "yplus": at(yplus, j, i),
            "cf": at(cf, j, i),
        }
        if le_index is not None:
            # signed distance around the ring from the leading edge, wrapped
            offset = i - le_index
            if offset > ni_cell // 2:
                offset -= ni_cell
            elif offset < -(ni_cell // 2):
                offset += ni_cell
            entry["cells_from_le"] = int(offset)
        cells.append(entry)
    cells.sort(key=lambda c: -c["excess"])

    # rind, reported apart
    rind_mask = np.ones(cp.shape, dtype=bool)
    rind_mask[1:-1, 1:-1] = False
    rind_over = int((cp[rind_mask] > CP_PHYSICAL_MAX).sum())

    return {
        "zone": name,
        "cell_dims": [int(ni_cell), int(nj_cell)],
        "interior_cells": int(interior.size),
        "cp_min": float(interior.min()),
        "cp_max": float(interior.max()),
        "cp_min_at": [
            float(v) for v in centres[np.unravel_index(interior.argmin(), interior.shape)]
        ],
        "interior_over_bound": int(over.sum()),
        "rind_over_bound": rind_over,
        "cells": cells,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--surface", type=Path, required=True)
    ap.add_argument(
        "--le-index",
        type=int,
        default=None,
        help="ring CELL index of the leading edge on the OML zone, so offsets "
        "can be reported relative to it. For a level with n_side points per "
        "side the leading-edge node is n_side - 1.",
    )
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--max-listed", type=int, default=40)
    args = ap.parse_args()

    # CGNS has two container formats and ADflow writes whichever its linked
    # library supports. On this host that is ADF, which h5py cannot open at all
    # -- it raises "file signature not found" -- so opening with h5py
    # unconditionally meant this script had nothing to read and the cp panel of
    # plot_sweep.py came out BLANK rather than wrong. cgns_read handles both.
    import cgns_read

    report = {"surface_file": str(args.surface), "cp_physical_max": CP_PHYSICAL_MAX}
    zone_reports = []
    if cgns_read.is_hdf5(args.surface):
        import h5py
        handle = h5py.File(args.surface, "r")
        found = zones(handle)
    else:
        handle = None
        found = cgns_read.surface_zones(args.surface)
    report["container_format"] = "HDF5" if handle else "ADF"
    try:
        for name, node in found:
            if "Wall" not in name:
                continue
            # the OML is the larger wall zone; the leading-edge offset only
            # means anything there
            le = args.le_index if "Zone5" in name else None
            zone_reports.append(analyse_zone(name, node, le_index=le))
    finally:
        if handle is not None:
            handle.close()

    report["zones"] = zone_reports
    report["total_interior_over_bound"] = sum(
        z["interior_over_bound"] for z in zone_reports
    )

    out = args.out or args.surface.parent / "cp_excess_locations.json"
    trimmed = json.loads(json.dumps(report))
    for zone in trimmed["zones"]:
        zone["cells"] = zone["cells"][: args.max_listed]
    out.write_text(json.dumps(report, indent=2) + "\n")

    for zone in zone_reports:
        print(f"\n=== {zone['zone']}  cells {zone['cell_dims']}  "
              f"interior {zone['interior_cells']} ===")
        print(f"  cp range {zone['cp_min']:.4f} .. {zone['cp_max']:.4f}")
        print(f"  over bound: {zone['interior_over_bound']} interior, "
              f"{zone['rind_over_bound']} rind")
        if zone["cells"]:
            print(f"  {'i':>4} {'j':>4} {'dLE':>5} {'cp':>8} {'excess':>8} "
                  f"{'y+':>7} {'x':>9} {'y':>9} {'z':>9}")
            for c in zone["cells"][: args.max_listed]:
                d = c.get("cells_from_le")
                print(
                    f"  {c['i_ring']:>4} {c['j_span']:>4} "
                    f"{'' if d is None else d:>5} {c['cp']:>8.4f} "
                    f"{c['excess']:>8.4f} "
                    f"{-1.0 if c['yplus'] is None else c['yplus']:>7.3f} "
                    + " ".join(f"{v:>9.4f}" for v in c["xyz_m"])
                )
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
