#!/usr/bin/env python
"""Global mass conservation: does as much mass leave the domain as enters it?

    .venv/bin/python .../mass_balance.py --runs 'AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/runs/s8_cfd/gci_C_a*'

A residual is a statement about how well the discrete equations balance in each
cell.  This is the INTEGRAL statement, over the whole domain boundary, and it
asks a question the residual does not: is the converged solution actually
conserving mass across the far field, or is it balancing a set of equations that
leak?  A solver can drive resrho to 1e-8 on a domain whose boundary fluxes do not
close -- a mis-set boundary condition, an unclaimed face treated as a wall, a
block interface that did not connect -- and every per-cell residual will look
fine, because each cell is individually consistent with its neighbours.

For steady flow the statement is

    sum over the closed boundary of  rho (V . n) dA  =  0

with n outward.  The wing and tip-cap walls are viscous, so V = 0 there and they
contribute nothing; the root plane is a symmetry plane, so V . n = 0 there.  All
of the flux therefore passes through the far field, and the net of it should be
zero to within discretization.  Both of the zero-by-construction contributions
are COMPUTED rather than assumed, because "the wall carries no flux" is exactly
the kind of thing that is true right up until a boundary condition is wrong.

Density is not in the surface solution, so it comes from cp isentropically:

    p/p_inf   = 1 + cp * gamma * M_inf^2 / 2
    rho/rho_inf = (p/p_inf) ^ (1/gamma)

At M 0.0837 that correction is under half a per cent, but it is free and it is
the right relation, and assuming rho = rho_inf would hide a genuine
compressibility error rather than bound it.

Normalisation.  A raw kg/s means nothing without a scale, so the imbalance is
reported against the total THROUGHPUT -- the sum of |rho V.n| dA over the
far field, i.e. how much mass is moving through the boundary in total.  A net of
1e-4 of throughput is a closed domain; a net of order one is a hole in it.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cgns_read  # noqa: E402

GAMMA = 1.4
#: mission_authority_v1.yaml, matching solve_s8.py
MACH = 0.0837


def face_area_vectors(xyz: np.ndarray) -> np.ndarray:
    """Outward-ish area vectors of each quad, from the node grid (nj, ni, 3).

    Each quad's area vector is half the cross product of its diagonals, which is
    exact for a planar quad and the standard choice for a warped one.
    """
    p00 = xyz[:-1, :-1, :]
    p10 = xyz[:-1, 1:, :]
    p01 = xyz[1:, :-1, :]
    p11 = xyz[1:, 1:, :]
    return 0.5 * np.cross(p11 - p00, p01 - p10)


def cell_centres(xyz: np.ndarray) -> np.ndarray:
    return 0.25 * (xyz[:-1, :-1, :] + xyz[:-1, 1:, :] + xyz[1:, :-1, :] + xyz[1:, 1:, :])


def strip_rind(a: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Drop the one-cell rind ADflow writes around cell-centred surface data."""
    if a.shape == shape:
        return a
    if a.shape == (shape[0] + 2, shape[1] + 2):
        return a[1:-1, 1:-1]
    raise SystemExit(f"cell array shape {a.shape} matches neither {shape} nor its "
                     f"rind-padded form; refusing to guess which cells are which")


def analyse(surface: Path) -> dict:
    zones = cgns_read.surface_zones(surface)
    wing_points = []
    for name, node in zones:
        if "Wall" in name:
            g = node["GridCoordinates"]
            wing_points.append(np.stack([np.array(g[f"Coordinate{a}"][" data"])
                                         for a in "XYZ"], axis=-1).reshape(-1, 3))
    if not wing_points:
        raise SystemExit(f"{surface} has no wall zone; cannot orient the far field")
    wing_centroid = np.concatenate(wing_points).mean(axis=0)

    out: dict = {"surface_file": str(surface), "zones": {}, "wing_centroid_m": wing_centroid.tolist()}
    far_net = far_through = 0.0
    wall_abs = symmetry_abs = 0.0

    for name, node in zones:
        g, s = node["GridCoordinates"], node["Flow solution"]
        xyz = np.stack([np.array(g[f"Coordinate{a}"][" data"]) for a in "XYZ"], axis=-1)
        shape = (xyz.shape[0] - 1, xyz.shape[1] - 1)
        cp = strip_rind(np.array(s["CoefPressure"][" data"]), shape)
        vel = np.stack([strip_rind(np.array(s[f"Velocity{a}"][" data"]), shape)
                        for a in "XYZ"], axis=-1)
        area = face_area_vectors(xyz)
        centre = cell_centres(xyz)

        # non-dimensional density from cp, isentropically
        pressure_ratio = 1.0 + cp * GAMMA * MACH ** 2 / 2.0
        rho_ratio = np.sign(pressure_ratio) * np.abs(pressure_ratio) ** (1.0 / GAMMA)

        # orient outward: away from the wing for the far field, which is a
        # cylinder enclosing it. Sign convention on a wall or symmetry plane is
        # irrelevant, since the flux there is zero either way.
        outward = centre - wing_centroid
        flip = np.sign((area * outward).sum(-1))
        flip[flip == 0] = 1.0
        area = area * flip[..., None]

        flux = rho_ratio * (vel * area).sum(-1)      # rho/rho_inf * V.n * dA
        record = {"cells": int(flux.size),
                  "net_flux": float(flux.sum()),
                  "throughput": float(np.abs(flux).sum()),
                  "area_m2": float(np.linalg.norm(area, axis=-1).sum()),
                  "max_velocity_magnitude": float(np.linalg.norm(vel, axis=-1).max())}
        out["zones"][name] = record
        if "FarField" in name:
            far_net += record["net_flux"]
            far_through += record["throughput"]
        elif "Wall" in name:
            wall_abs += record["throughput"]
        elif "Symmetry" in name:
            symmetry_abs += record["throughput"]

    out["far_field_net_flux"] = far_net
    out["far_field_throughput"] = far_through
    out["relative_imbalance"] = abs(far_net) / far_through if far_through else float("nan")
    out["wall_leakage_abs"] = wall_abs
    out["wall_leakage_relative"] = wall_abs / far_through if far_through else float("nan")
    out["symmetry_leakage_abs"] = symmetry_abs
    out["symmetry_leakage_relative"] = symmetry_abs / far_through if far_through else float("nan")
    out["units"] = ("fluxes are rho/rho_inf * V * area, so m^4/s per unit density; "
                    "only the RATIOS are interpreted")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    directories = sorted({Path(p) for pattern in args.runs for p in glob.glob(pattern)})
    results = []
    for directory in directories:
        surfaces = sorted(directory.glob("*surf.cgns"))
        if not surfaces:
            continue
        match = re.search(r"_a(-?\d+(?:\.\d+)?)", directory.name)
        record = analyse(surfaces[0])
        record["directory"] = str(directory)
        record["alpha_deg"] = float(match.group(1)) if match else None
        results.append(record)
    results.sort(key=lambda r: (r["alpha_deg"] is None, r["alpha_deg"]))

    print("global mass balance over the closed domain boundary\n")
    print(f"{'alpha':>7}{'far-field net':>16}{'throughput':>14}{'imbalance':>12}"
          f"{'wall leak':>12}{'sym leak':>11}")
    for r in results:
        print(f"{r['alpha_deg']:>7.1f}{r['far_field_net_flux']:>16.6e}"
              f"{r['far_field_throughput']:>14.4e}"
              f"{r['relative_imbalance']:>11.3e} "
              f"{r['wall_leakage_relative']:>11.3e}"
              f"{r['symmetry_leakage_relative']:>11.3e}")

    print("\n  imbalance = |net far-field flux| / total far-field throughput.")
    print("  wall and symmetry leakage should be zero BY BOUNDARY CONDITION;")
    print("  they are computed, not assumed, because a wrong BC is silent.")
    worst = max((r["relative_imbalance"] for r in results), default=float("nan"))
    if np.isfinite(worst):
        print(f"\n  worst imbalance {worst:.3e} -- ", end="")
        print("the domain closes" if worst < 1e-3 else
              "MARGINAL, worth investigating" if worst < 1e-2 else
              "the domain does NOT close; boundary conditions or connectivity")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"runs": results}, indent=2) + "\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
