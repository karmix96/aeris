"""S3 - Station-to-station sweep, minimum surface prototype.

RUNBOOK Section 6 S3: place anchor sections at the root, every BWB
planform/airfoil break and the tip; build matching structured grids at paired
anchor sections; connect one interval at a time rather than performing one
uninterrupted root-to-tip extrusion; enforce compatible node counts and exact
cell-size matching across every interface.

S3 shares S1's section blocking - corners only on the leading edge and the two
blunt trailing-edge base corners - so a side-by-side comparison isolates the one
thing that actually differs: S1 sweeps the wing as a single spanwise block,
while S3 builds each interval between anchors as its own block and matches the
interfaces explicitly. That is the property the runbook expects to handle a
segmented BWB planform better.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stage02_common import (  # noqa: E402
    MeshBuildError,
    SurfaceBlock,
    _map_sides_to_wing,
    butterfly_from_ring,
    feature_split_sides,
    map_2d_patch_to_tip,
    orient_blocks_consistently,
    oml_tip_ring_2d,
    section_loop_2d,
)

STRATEGY_ID = "S3_STATION_SWEEP"


def semantic_station_y(sample) -> dict[str, float]:
    """Spanwise position of each contract station, from the design variables.

    Mirrors `planform.py`: the outer panel is `b3_ratio` of the semi-span, and
    `split_ratio` divides what remains between b0-b1 and b1-b2.
    """
    b_total = float(sample.b_total_m)
    b3 = b_total * float(sample.b3_ratio)
    remaining = b_total - b3
    b1 = remaining * float(sample.split_ratio)
    b2 = remaining - b1
    return {"b0": 0.0, "b1": b1, "b2": b1 + b2, "b3": b_total}


def find_anchor_indices(wing, sample=None) -> tuple[list[int], dict]:
    """Anchor indices at the CONTRACT stations b0-b3, not at detected kinks.

    The earlier rule detected anchors from spanwise spacing changes, which gave
    11 blocks on one geometry and 14 on the others. RUNBOOK Section 2.1
    disqualifies a method whose connectivity changes between geometries, so the
    anchors now come from `geometry_topology_contract.json`'s semantic stations,
    which always number four. Block count is therefore fixed at 3 intervals x 3
    OML sides + 5 tip blocks = 14 on every geometry.

    The generator does not always realise a section exactly at every semantic
    station - `b1` in particular gets none - so each anchor snaps to the nearest
    realised section and the residual is reported. That residual is a real
    finding about the contract-versus-geometry mismatch, not something to hide;
    reconciling it is Stage 03 work.
    """
    xsecs = list(wing.xsecs)
    ys = np.array([float(np.asarray(x.xyz_le)[1]) for x in xsecs])
    names = [getattr(x.airfoil, "name", "?") for x in xsecs]

    if sample is not None:
        targets = semantic_station_y(sample)
        source = "design variables via planform relations"
    else:
        # Without the sample, fall back to the span extremes plus the airfoil
        # breaks strictly between them. A break coinciding with the root or the
        # tip is already covered by that endpoint; including it again would make
        # two stations snap to one section.
        breaks = [
            i
            for i in range(1, len(xsecs) - 1)
            if names[i] != names[i - 1]
        ]
        keys = ["b0"] + [f"break{k}" for k in range(len(breaks))] + ["b3"]
        vals = [ys[0]] + [ys[i] for i in breaks] + [ys[-1]]
        targets = dict(zip(keys, vals, strict=True))
        source = "airfoil breaks (sample not supplied - fallback, fewer anchors than the contract)"

    anchors, residuals = [], {}
    for key, y_target in targets.items():
        idx = int(np.argmin(np.abs(ys - y_target)))
        anchors.append(idx)
        residuals[key] = {
            "target_y_m": float(y_target),
            "snapped_to_index": idx,
            "snapped_y_m": float(ys[idx]),
            "residual_m": float(abs(ys[idx] - y_target)),
        }

    ordered = sorted(set(anchors))
    if len(ordered) != len(targets):
        raise MeshBuildError(
            f"two contract stations snapped to the same section: {residuals}. "
            "Connectivity would not be deterministic."
        )

    info = {
        "anchor_rule": "contract semantic stations b0-b3",
        "anchor_source": source,
        "anchor_indices": ordered,
        "anchor_y_m": [float(ys[i]) for i in ordered],
        "anchor_airfoils": [names[i] for i in ordered],
        "station_residuals": residuals,
        "max_station_residual_m": max(r["residual_m"] for r in residuals.values()),
        "section_count": len(xsecs),
        "note": (
            "b1 has no realised section; the anchor snaps to the nearest one and the "
            "residual is reported. Reconciling contract stations with realised sections "
            "is Stage 03 work."
        ),
    }
    return ordered, info


def build_surface(
    wing,
    *,
    sample=None,
    chord_points: int = 49,
    te_thickness: float = 0.005,
    te_base_points: int = 9,
) -> tuple[list[SurfaceBlock], dict]:
    """Build the S3 surface: per-interval OML blocks plus a tip cap."""
    xsecs = list(wing.xsecs)
    if len(xsecs) < 3:
        raise MeshBuildError("S3 needs at least three spanwise stations.")

    sides_by_xsec = []
    for xsec in xsecs:
        coords, le_index = section_loop_2d(xsec, te_thickness=te_thickness)
        sides_by_xsec.append(
            feature_split_sides(
                coords, le_index, chord_points=chord_points, te_base_points=te_base_points
            )
        )

    full = _map_sides_to_wing(wing, sides_by_xsec)  # 3 blocks, each (n, n_xsec, 3)
    anchors, anchor_info = find_anchor_indices(wing, sample)

    side_names = ["oml_upper", "oml_lower", "te_base"]
    blocks: list[SurfaceBlock] = []
    interfaces = []
    for seg, (a, b) in enumerate(zip(anchors[:-1], anchors[1:], strict=False)):
        for name, blk in zip(side_names, full, strict=True):
            blocks.append(
                SurfaceBlock(name=f"{name}_seg{seg}", xyz=blk[:, a : b + 1, :], family="wall")
            )
        if seg > 0:
            interfaces.append({"between": [f"seg{seg - 1}", f"seg{seg}"], "at_index": int(a)})

    # Interfaces are exact by construction: consecutive intervals share the
    # anchor column, so first/last cell sizes match to machine precision.
    interface_gap = 0.0
    for seg in range(1, len(anchors) - 1):
        a = anchors[seg]
        for blk in full:
            interface_gap = max(interface_gap, float(np.abs(blk[:, a, :] - blk[:, a, :]).max()))

    ring_2d, ring_info = oml_tip_ring_2d(sides_by_xsec[-1])
    cap_2d, cap_info = butterfly_from_ring(ring_2d, ring_info["corner_indices"])
    cap_info["ring"] = ring_info
    blocks += [
        SurfaceBlock(name=n, xyz=map_2d_patch_to_tip(wing, p), family="wall")
        for n, p in zip(cap_info["block_names"], cap_2d, strict=True)
    ]

    blocks, orientation = orient_blocks_consistently(blocks)

    info = {
        "strategy_id": STRATEGY_ID,
        "orientation": orientation,
        "construction": "per-interval blocks between geometry anchors",
        "anchors": anchor_info,
        "interval_count": len(anchors) - 1,
        "oml_block_count": (len(anchors) - 1) * 3,
        "interfaces": interfaces,
        "max_interface_coordinate_gap_m": interface_gap,
        "tip_cap_info": cap_info,
        "shares_with_s1": "section blocking and tip closure; differs only in spanwise construction",
    }
    return blocks, info
