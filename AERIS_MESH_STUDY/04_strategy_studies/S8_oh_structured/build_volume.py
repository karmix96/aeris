#!/usr/bin/env python
"""Assemble and verify the S8 O-H volume grid, and write it for ParaView.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/build_volume.py \
        --level oh_L3

Block layout, three structured blocks that close the domain:

    o_wing   (n_ring+1, n_normal, n_span)  xi around the section, eta
                                           wall-normal, zeta root -> tip.
                                           eta=0 is the viscous wall, zeta=0 the
                                           root symmetry plane.
    o_out    (n_ring+1, n_normal, n_out)   the same annulus continued outboard
                                           from the tip plane to the spanwise
                                           far field.  Its zeta=0 plane IS
                                           o_wing's last plane.
    cap_out  (n_chord, n_base, n_out)      the tip cap patch continued outboard.
                                           Its zeta=0 face is the tip cap, a
                                           viscous wall; its perimeter is
                                           o_out's eta=0 face.

Together o_out and cap_out fill the whole disc outboard of the tip, so the
domain is closed: root symmetry plane, viscous wall on the OML and the tip cap,
far field on the cylinder and the outboard end.

Every cell volume is computed and reported.  Nothing here is accepted on the
strength of looking right.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (
    str(HERE), str(HERE.parent), str(HERE.parent / "S6_bounded_mesh_atlas"), str(REPO / "src")
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import march_o  # noqa: E402
import strategy_s8  # noqa: E402
from march_o import SMOOTHING_LADDER, march_section_auto  # noqa: E402

Array = np.ndarray

#: Growth ceiling for the outboard spanwise stack.
OUTBOARD_GROWTH_CEILING = 1.30


def hex_volumes(xyz: Array) -> Array:
    """Signed volumes of every hexahedral cell, by decomposition into six tets.

    The mean-Jacobian shortcut agrees with this on well-shaped cells and hides
    the twisted ones, which are exactly the cells worth finding.
    """
    p000 = xyz[:-1, :-1, :-1]
    p100 = xyz[1:, :-1, :-1]
    p110 = xyz[1:, 1:, :-1]
    p010 = xyz[:-1, 1:, :-1]
    p001 = xyz[:-1, :-1, 1:]
    p101 = xyz[1:, :-1, 1:]
    p111 = xyz[1:, 1:, 1:]
    p011 = xyz[:-1, 1:, 1:]
    tets = (
        (p000, p100, p110, p111), (p000, p110, p010, p111),
        (p000, p010, p011, p111), (p000, p011, p001, p111),
        (p000, p001, p101, p111), (p000, p101, p100, p111),
    )
    total = np.zeros(p000.shape[:3])
    for a, b, c, d in tets:
        total += np.einsum("...i,...i->...", np.cross(b - a, c - a), d - a) / 6.0
    return total


def write_structured_vtk(path: Path, xyz: Array, cell_arrays: dict[str, Array]) -> None:
    ni, nj, nk, _ = xyz.shape
    pts = xyz.transpose(2, 1, 0, 3).reshape(-1, 3)
    lines = [
        "# vtk DataFile Version 3.0",
        f"AERIS S8 O-H volume - {path.stem}",
        "ASCII",
        "DATASET STRUCTURED_GRID",
        f"DIMENSIONS {ni} {nj} {nk}",
        f"POINTS {len(pts)} float",
    ]
    lines += [f"{p[0]:.9g} {p[1]:.9g} {p[2]:.9g}" for p in pts]
    n_cells = (ni - 1) * (nj - 1) * (nk - 1)
    lines.append(f"CELL_DATA {n_cells}")
    for name, data in cell_arrays.items():
        flat = data.transpose(2, 1, 0).reshape(-1)
        lines.append(f"SCALARS {name} float 1")
        lines.append("LOOKUP_TABLE default")
        lines += [f"{v:.9g}" for v in flat]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def write_plot3d(path: Path, xyz: Array) -> None:
    """Single-block formatted Plot3D, the form pyHyp and ADflow tooling read."""
    ni, nj, nk, _ = xyz.shape
    with path.open("w") as fh:
        fh.write("1\n")
        fh.write(f"{ni} {nj} {nk}\n")
        for axis in range(3):
            block = xyz[:, :, :, axis].transpose(2, 1, 0).ravel()
            for start in range(0, block.size, 6):
                fh.write(" ".join(f"{v:.15e}" for v in block[start:start + 6]) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--level", default="oh_L3", choices=sorted(strategy_s8.LEVELS))
    ap.add_argument("--set-name", default="lhs100_seed42")
    ap.add_argument("--index", type=int, default=83)
    ap.add_argument("--out", type=Path,
                    default=REPO / "AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh")
    ap.add_argument("--no-plot3d", action="store_true")
    ap.add_argument("--allow-folded-cells", action="store_true",
                    help="write the grid even if the smoothing ladder cannot "
                         "clear every fold. For diagnosis only: a grid with "
                         "inverted cells must never reach a solver.")
    ap.add_argument("--open-tip", action="store_true",
                    help="skip the outboard blocks and write the wing block alone")
    args = ap.parse_args()

    import strategy_s6

    level = strategy_s8.LEVELS[args.level]
    with tempfile.TemporaryDirectory() as tmp:
        # Defect 18.  This called `build_locked_surface`, which builds an entire
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
    pygeo = case.pygeo_result.pygeo.geometry

    ring_xyz, surface_report = strategy_s8.build_oml_ring(pygeo, level)
    root_chord = surface_report["stations"][0]["chord_m"]
    diagonal = float(np.linalg.norm(np.ptp(ring_xyz.reshape(-1, 3), axis=0)))
    s0 = level.s0_frac * diagonal
    radius = level.farfield_chords * root_chord

    flat = ring_xyz.reshape(-1, 3)
    global_origin_xz = (float(flat[:, 0].mean()), float(flat[:, 2].mean()))

    # Defect 19.  march_section_auto climbs its ladder on an IN-PLANE fold test,
    # inside one section at a time.  A fold that lives BETWEEN two neighbouring
    # sections is invisible to it: on lhs100_seed42[65] every section is clean
    # in plane and the assembled hexes carry 645 folds, so the ladder stopped at
    # its first rung and the build wrote an invalid grid and exited zero.
    #
    # The fix is to climb the same ladder on the assembled 3D hex volumes, which
    # is the quantity that actually has to be positive, and to raise the floor
    # for EVERY section when it is not -- a fold between sections j and j+1 is
    # not attributable to either one alone.
    volume = None
    march_reports: list[dict] = []
    fold_ladder: list[dict] = []
    for floor in SMOOTHING_LADDER:
        planes = []
        march_reports = []
        for j in range(ring_xyz.shape[1]):
            grid, report = march_section_auto(
                ring_xyz[:, j, :], n_normal=level.n_normal, first_cell=s0,
                farfield_radius=radius, global_origin_xz=global_origin_xz,
                min_smoothing=floor,
            )
            planes.append(grid)
            march_reports.append(report)
        volume = np.stack(planes, axis=2)
        folded = int((hex_volumes(volume) <= 0.0).sum())
        fold_ladder.append({"smoothing_floor": floor, "folded_hexes": folded})
        print(f"  smoothing floor {floor:>3}: {folded} folded hexes in o_wing")
        if folded == 0:
            break
    else:
        message = (
            f"o_wing still has {fold_ladder[-1]['folded_hexes']} folded cells at "
            f"the top of the smoothing ladder ({SMOOTHING_LADDER[-1]}). A grid "
            f"with inverted cells is not a grid. Ladder: "
            + ", ".join(f"{a['smoothing_floor']}->{a['folded_hexes']}" for a in fold_ladder)
        )
        if not args.allow_folded_cells:
            raise SystemExit(message)
        print(f"WARNING, --allow-folded-cells was passed: {message}")

    # --- close the tip -------------------------------------------------------
    # The outboard region is the tip plane translated along the span.  A pure
    # translation is used deliberately: the tip-plane faces are already verified
    # non-degenerate, so every outboard cell is a prism on a valid base and
    # cannot invert.  Nothing here needs to bend, because the outer boundary is
    # already a cylinder of parallel circles after the frame blend.
    blocks: dict[str, Array] = {"o_wing": volume}
    outboard: dict[str, Any] = {"built": False}
    if not args.open_tip:
        cap_blocks, cap_info = strategy_s8.build_tip_cap(ring_xyz[:, -1, :], level)
        cap_patch = np.asarray(cap_blocks[0].xyz, dtype=float)
        tip_span_cell = float(
            np.linalg.norm(ring_xyz[:, -1, :] - ring_xyz[:, -2, :], axis=1).mean()
        )
        # The tip cap is a viscous wall whose normal IS the spanwise direction,
        # so the first outboard cell sets y+ on the cap.  Using the OML's tip
        # spanwise cell of 0.95 mm would give the cap a first cell 200 times the
        # OML's 4.7 um, and a y+ to match.  Tighten it, and pick the station
        # count from a growth ceiling rather than from the span count, so the
        # cell-size jump across the o_wing/o_out interface stays modest.
        # Match the OML's tip spanwise cell exactly, so the o_wing/o_out
        # interface carries no cell-size jump.  The span law now delivers that
        # cell as a request (level.tip_span_first_cell_in_s0), so this is a
        # match rather than the earlier compromise between a smooth interface
        # and a resolved cap.
        first_out = tip_span_cell
        n_out = 8
        while n_out < 200:
            _o, r = march_o.geometric_distribution(n_out, first_out, radius)
            if r <= OUTBOARD_GROWTH_CEILING:
                break
            n_out += 1
        offsets, span_growth = march_o.geometric_distribution(n_out, first_out, radius)
        shift = np.zeros((n_out, 3))
        shift[:, 1] = offsets
        blocks["o_out"] = volume[:, :, -1][:, :, None, :] + shift[None, None, :, :]
        blocks["cap_out"] = cap_patch[:, :, None, :] + shift[None, None, :, :]
        outboard = {
            "built": True,
            "n_out": int(n_out),
            "oml_tip_span_cell_m": tip_span_cell,
            "first_span_cell_m": float(first_out),
            "first_cell_in_s0": float(first_out / s0),
            "interface_span_jump": float(tip_span_cell / first_out),
            "tip_cap_yplus_scale_vs_oml": float(first_out / s0),
            "span_extent_m": float(offsets[-1]),
            "span_growth_ratio": span_growth,
            "tip_cap": cap_info,
        }

    per_block = {}
    worst = np.inf
    total_cells = 0
    for name, arr in blocks.items():
        v = hex_volumes(arr)
        per_block[name] = {
            "shape": list(arr.shape[:3]),
            "cells": int(v.size),
            "negative_cells": int((v <= 0.0).sum()),
            "min_cell_volume_m3": float(v.min()),
            "max_cell_volume_m3": float(v.max()),
        }
        worst = min(worst, float(v.min()))
        total_cells += int(v.size)

    # the shared faces must match node for node, or the domain is not closed
    interfaces = {
        "o_wing_zetamax_to_o_out_zeta0": float(
            np.abs(blocks["o_wing"][:, :, -1] - blocks["o_out"][:, :, 0]).max()
        ) if "o_out" in blocks else None,
    }
    if "cap_out" in blocks:
        cap0 = blocks["cap_out"][:, :, 0]
        perim = np.vstack([
            cap0[0, :, :], cap0[1:, -1, :], cap0[-1, -2::-1, :], cap0[-2::-1, 0, :],
        ])[:-1]
        ring0 = blocks["o_out"][:-1, 0, 0]
        interfaces["cap_out_perimeter_to_o_out_eta0"] = float(
            np.abs(np.sort(perim, axis=0) - np.sort(ring0, axis=0)).max()
        )

    vols = hex_volumes(volume)
    wall_spacing = np.linalg.norm(np.diff(volume, axis=1), axis=3)[:, 0, :]

    args.out.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, arr in blocks.items():
        v = hex_volumes(arr)
        path = args.out / f"{args.level}_{name}.vtk"
        write_structured_vtk(path, arr, {
            "volume_m3": v,
            "log10_volume": np.log10(np.maximum(np.abs(v), 1e-30)),
        })
        written[name] = str(path.relative_to(REPO))
    # Blocks in the order the CGNS writer expects, for `write_cgns.py`, which
    # runs under the mach-aero interpreter because libcgns is not in the venv.
    npz = args.out / f"{args.level}_blocks.npz"
    np.savez_compressed(npz, **{k: v for k, v in blocks.items()})
    written["blocks_npz"] = str(npz.relative_to(REPO))
    if not args.no_plot3d:
        write_plot3d(args.out / f"{args.level}_volume.xyz", volume)

    summary = {
        "schema": "aeris.s8.oh_volume.v1",
        "strategy_id": strategy_s8.STRATEGY_ID,
        "level": args.level,
        "geometry": f"{args.set_name}[{args.index}]",
        "blocks": per_block,
        "block_shape": list(volume.shape[:3]),
        "cells": total_cells,
        "negative_cells_all_blocks": sum(b["negative_cells"] for b in per_block.values()),
        "min_cell_volume_all_blocks_m3": worst,
        "outboard": outboard,
        "interface_match_m": interfaces,
        "boundary_conditions": {
            "o_wing": {"eta0": "viscous wall (OML)", "etamax": "far field",
                       "zeta0": "symmetry (root plane)", "zetamax": "interface o_out"},
            "o_out": {"eta0": "interface cap_out", "etamax": "far field",
                      "zeta0": "interface o_wing", "zetamax": "far field"},
            "cap_out": {"zeta0": "viscous wall (tip cap)", "zetamax": "far field",
                        "perimeter": "interface o_out"},
        },
        "surface": {
            "target_le_turn_deg": surface_report["target_le_turn_deg"],
            "worst_le_turn_per_cell_deg": surface_report["worst_le_turn_per_cell_deg"],
            "all_stations_met_target": surface_report["all_stations_met_target"],
            "min_surface_spacing_m": surface_report["min_surface_spacing_m"],
            "min_cell_over_s0": surface_report["min_surface_spacing_m"] / s0,
            # The spanwise smoothness of the leading-edge spacing has to appear
            # in the summary, not only inside the ring report that is discarded
            # after the build.  oh_L3 shipped with a 2.6x station-to-station
            # cliff that `worst_le_turn_per_cell_deg` could not see, because
            # every station still met its target; the number that would have
            # shown it was computed and thrown away.
            "le_spacing_smoothing": surface_report["le_spacing_smoothing"],
            "stations": surface_report["stations"],
        },
        "volume": {
            "s0_m": s0,
            "farfield_radius_m": radius,
            "farfield_root_chords": level.farfield_chords,
            "negative_cells": int((vols <= 0.0).sum()),
            "min_cell_volume_m3": float(vols.min()),
            "max_cell_volume_m3": float(vols.max()),
            "wall_spacing_min_m": float(wall_spacing.min()),
            "wall_spacing_max_m": float(wall_spacing.max()),
            "normal_growth_ratio": max(r["normal_growth_ratio"] for r in march_reports),
            "wall_orthogonality_median_deg": float(
                np.median([r["wall_orthogonality_median_deg"] for r in march_reports])
            ),
            "wall_orthogonality_worst_deg": max(
                r["wall_orthogonality_worst_deg"] for r in march_reports
            ),
            "smoothing_used": sorted({r["normal_smoothing"] for r in march_reports}),
            "fold_ladder_3d": fold_ladder,
            "stations_not_converged": [
                j for j, r in enumerate(march_reports) if not r["converged"]
            ],
        },
        "files": written,
        "open_tip": bool(args.open_tip),
        "status": (
            "WING_BLOCK_ONLY_TIP_NOT_CLOSED" if args.open_tip
            else "CLOSED_THREE_BLOCK_OH_DOMAIN"
        ),
    }
    (args.out / f"{args.level}_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({
        "status": summary["status"],
        "total_cells": summary["cells"],
        "negative_cells_all_blocks": summary["negative_cells_all_blocks"],
        "min_cell_volume_all_blocks_m3": summary["min_cell_volume_all_blocks_m3"],
        "blocks": per_block,
        "interface_match_m": interfaces,
        "surface": summary["surface"],
        "wall_orthogonality_median_deg": summary["volume"]["wall_orthogonality_median_deg"],
        "outboard": {k: v for k, v in outboard.items() if k != "tip_cap"},
    }, indent=2))
    print(f"\nwrote {len(written)} blocks to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
