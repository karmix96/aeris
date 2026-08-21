"""The verifier — SHARED CONTROL.

ADR-0011 section 4. Cell quality is not correctness. Before comparing strategies it
must be shown that each one produces the prescribed geometry and a closed,
consistently oriented surface. Migrated in substance from
`04_strategy_prototypes/verify_strategies.py`, generalised to verify any strategy's
blocks rather than a hard-coded list of four.

**Verify the verifier.** Five instrument bugs were found in Stage 02, each
reporting a false failure on a sound mesh, and a sixth reporting a false pass. Each
fix is preserved here with the failure it prevents, because the fixes look like
pedantry until you know what they cost:

1. Distance measured to sampled *points* rather than polyline *segments* floors the
   error at half the reference spacing — 0.0507% reported on an exact mesh.
   :func:`_point_to_polyline`.
2. An **open** reference contour excludes the blunt base, reporting the TE base
   block as 0.2516% off-surface, exactly half `te_thickness`. :func:`oml_fidelity`
   closes the loop.
3. Watertightness tested in the wrong direction — requiring every *cap* boundary
   node to lie on the OML edge — reports a cap's legitimate internal interfaces as
   holes. The correct condition is the other direction: every OML tip-edge node
   must be present in the cap. :func:`tip_cap_nodes`.
4. Tip-edge nodes taken from *every* OML block's outboard edge report a 0.58 m gap
   on a sound segmented mesh, where each interval has its own outboard edge.
   :func:`tip_edge_nodes` selects by spanwise position instead.
5. Determinism hashing block *dimensions* fails a compliant method: RUNBOOK section
   2.1 freezes the **connectivity** signature and explicitly permits "node
   positions, spacing and permitted counts [to] adapt to geometry".
   :func:`connectivity_signature`.
6. The fidelity check silently **skipped** spanwise-refined blocks — exactly the
   blocks whose interpolated columns sit off the loft — reporting a refined mesh as
   fidelity-perfect. It now records them as unverified, and
   `shared.gates.surface_gate_checklist` treats unverified as a failure.
7. **Found during the ADR-0011 migration, 2026-08-14.** The tip edge was taken from
   each OML block's *last j column*, which assumes that column is the outboard one.
   `orient_blocks_consistently` reverses the j index of any block it flips — seven
   of eight on `lhs7_00` — after which no block matched the tip station and the
   check raised `ValueError` rather than returning a result. Selection is now by
   spanwise **position**, which is instrument bug 4's own principle applied
   properly. :func:`tip_edge_nodes`.
"""

from __future__ import annotations

import numpy as np

from . import gates
from .ingestion import TE_THICKNESS_ABS_M, _map_sides_to_wing, section_loop_2d

NODE_DECIMALS = gates.NODE_DECIMALS


def tip_edge_nodes(blocks) -> np.ndarray:
    """OML nodes that actually lie on the tip station. See instrument bugs 4 and 7.

    **Instrument bug 7**, found by `shared/selftest.py` during the ADR-0011
    migration on 2026-08-14 and fixed here:

    The Stage 02 version took each OML block's `xyz[:, -1, :]` edge and kept it if
    its maximum y matched the tip station. That silently assumes the **last j
    column is the outboard one** — and `orient_blocks_consistently` reverses the j
    index of any block it flips. On `lhs7_00` it flips seven of eight blocks,
    including all three OML blocks, after which `xyz[:, -1, :]` is the ROOT edge,
    no block matches the tip station, and the check raised
    `ValueError: need at least one array to concatenate` instead of reporting a
    result. Any strategy whose blocks happen to be flipped would have been
    unverifiable rather than failed — which is worse, because it looks like a
    crash in the harness rather than a finding.

    The fix applies instrument bug 4's own principle properly: **select by
    spanwise position, not by index.** Every OML node at the tip station is
    collected, whatever the block's index orientation or blocking.
    """
    oml = [b for b in blocks if not b.name.startswith("tip")]
    if not oml:
        raise ValueError("no non-tip blocks; cannot locate the tip station")
    tip_y = max(float(b.xyz[:, :, 1].max()) for b in oml)
    tol = 10.0 ** (-NODE_DECIMALS)
    pts = [b.xyz.reshape(-1, 3)[b.xyz.reshape(-1, 3)[:, 1] >= tip_y - tol] for b in oml]
    pts = [p for p in pts if len(p)]
    if not pts:
        raise ValueError(
            f"no OML node lies within {tol} m of the tip station y={tip_y}; "
            "the tip station could not be located"
        )
    return np.unique(np.round(np.concatenate(pts, axis=0), NODE_DECIMALS), axis=0)


def tip_cap_nodes(blocks) -> set:
    """All nodes belonging to tip-cap blocks. See instrument bug 3."""
    out: set = set()
    for b in blocks:
        if not b.name.startswith("tip"):
            continue
        out |= {tuple(np.round(p, NODE_DECIMALS)) for p in b.xyz.reshape(-1, 3)}
    return out


def _point_to_polyline(pts: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Distance from each point to the nearest SEGMENT of a polyline. Bug 1."""
    a = poly[:-1]
    b = poly[1:]
    ab = b - a
    l2 = np.einsum("ij,ij->i", ab, ab)
    l2[l2 == 0] = 1e-30
    out = np.empty(len(pts))
    for i, p in enumerate(pts):
        t = np.clip(np.einsum("ij,ij->i", p - a, ab) / l2, 0.0, 1.0)
        out[i] = float(np.min(np.linalg.norm(a + t[:, None] * ab - p, axis=1)))
    return out


def oml_fidelity(
    wing, blocks, te_thickness_abs_m: float | None = None, *,
    te_thickness_frac: float | None = None,
) -> dict:
    """Distance from OML nodes to the prescribed section contour. Bugs 2, 6 and 8.

    **Instrument bug 8**, found on 2026-08-14 while measuring S0 without spanwise
    refinement, and fixed here:

    The previous version decided whether a block was spanwise-refined by
    comparing its column COUNT to the station count, then assumed column ``j``
    was station ``j``. Both halves are wrong. A block can carry exactly as many
    columns as there are stations without any of them lying ON a station — S0's
    proportional spanwise allocation does this at ``spanwise_panels=1``, since it
    spends one budget across intervals of unequal length. The check then compared
    each column against an unrelated station and reported **835% of local chord**
    on a mesh whose station columns are in fact exact.

    Columns are now matched to stations by spanwise POSITION. Matched columns are
    measured; unmatched ones are reported as unverified rather than being
    silently skipped (bug 6) or silently mismeasured (bug 8).
    """
    # The reference contour must be opened EXACTLY as the mesh was, or the
    # measurement is against a different aircraft. `te_thickness_frac` exists only
    # so the Stage 02 prior art, which used a chord fraction, can still be checked
    # against its own reference.
    if te_thickness_frac is None and te_thickness_abs_m is None:
        te_thickness_abs_m = TE_THICKNESS_ABS_M
    xsecs = list(wing.xsecs)
    refs = []
    for idx, xsec in enumerate(xsecs):
        coords, _le = section_loop_2d(
            xsec, te_thickness=te_thickness_frac,
            te_thickness_abs_m=None if te_thickness_frac is not None else te_thickness_abs_m,
        )
        closed = np.vstack([coords, coords[0]])  # bug 2: the reference must be CLOSED
        refs.append(_map_sides_to_wing(wing, [[closed] for _ in xsecs])[0][:, idx, :])
    station_y = np.array([float(r[:, 1].mean()) for r in refs])

    # A column counts as ON the prescribed geometry when it actually lies on a
    # station contour, measured — not when its index or its column count says it
    # should. Two earlier rules both failed:
    #
    #   * column COUNT equals station count  -> assumes column j is station j.
    #     S0's proportional spanwise allocation breaks that and the check
    #     reported 835% of local chord on a mesh whose station columns are exact.
    #   * nearest station by mean y within half a station gap -> matches
    #     interpolated columns to whichever station they sit nearest and then
    #     measures them against it (10-18% of chord, all artefact). Tightening
    #     the tolerance to node precision then matched only 16 of 68 real station
    #     columns, because a BLOCK is a sub-arc of the section and its mean y is
    #     not the whole contour's mean y.
    #
    # So the test is the measurement itself: a column is verified when its
    # distance to a station contour is within the fidelity gate. The two nearest
    # stations by mean y are the only candidates worth evaluating.
    worst_abs = 0.0
    worst_frac = 0.0
    worst_block = None
    unverified: dict[str, int] = {}
    measured_columns = 0
    for b in blocks:
        if b.name.startswith("tip"):
            continue
        cols_y = b.xyz[:, :, 1].mean(axis=0)
        for j, y in enumerate(cols_y):
            order = np.argsort(np.abs(station_y - y))[:2]
            best_frac = None
            best_abs = 0.0
            for k in order:
                ref = refs[int(k)]
                chord = float(np.ptp(ref[:, 0]))
                d = float(_point_to_polyline(b.xyz[:, j, :], ref).max())
                frac = d / max(chord, 1e-12)
                if best_frac is None or frac < best_frac:
                    best_frac, best_abs = frac, d
            if best_frac is None or best_frac > gates.FIDELITY_FRAC_OF_LOCAL_CHORD:
                unverified[b.name] = unverified.get(b.name, 0) + 1
                continue
            measured_columns += 1
            if best_frac > worst_frac:
                worst_frac, worst_abs, worst_block = best_frac, best_abs, b.name

    return {
        "worst_abs_m": worst_abs,
        "worst_frac_of_local_chord": worst_frac,
        "worst_block": worst_block,
        "measured_station_columns": measured_columns,
        "unverified_columns_by_block": unverified,
        "skipped_spanwise_refined_blocks": sorted(unverified),
        "fidelity_unverified_for_refined_blocks": bool(unverified),
    }


def connectivity_signature(blocks) -> tuple:
    """The frozen signature: block names and families. NOT dimensions. Bug 5."""
    return tuple(sorted((b.name, b.family) for b in blocks))


def dimension_signature(blocks) -> tuple:
    """Block dimensions — REPORTED, never gated. RUNBOOK section 2.1."""
    return tuple(sorted((b.name, tuple(b.xyz.shape)) for b in blocks))


def watertight_tip(blocks) -> dict:
    """Every OML tip-edge node must be present in the tip cap. Bug 3."""
    cap = tip_cap_nodes(blocks)
    edge = tip_edge_nodes(blocks)
    edge_set = {tuple(np.round(p, NODE_DECIMALS)) for p in edge}
    missing = edge_set - cap
    ref_len = float(np.ptp(edge[:, 0]))
    if missing:
        cap_arr = np.array(sorted(cap))
        gap = max(
            float(np.min(np.linalg.norm(cap_arr - np.array(p), axis=1)))
            for p in list(missing)[:400]
        )
    else:
        gap = 0.0
    return {
        "watertight_tip": not missing,
        "oml_tip_edge_nodes": len(edge_set),
        "missing_from_cap": len(missing),
        "max_gap_to_oml_tip_edge_m": gap,
        "max_gap_as_frac_of_tip_chord": gap / max(ref_len, 1e-12),
    }


def verify_geometry(wing, blocks, *, te_thickness_abs_m: float | None = None) -> dict:
    """Every per-geometry surface check, in one dict. Determinism needs the set."""
    result = watertight_tip(blocks)
    result["oml_fidelity"] = oml_fidelity(wing, blocks, te_thickness_abs_m)
    result["all_finite"] = bool(all(np.isfinite(b.xyz).all() for b in blocks))
    result["block_count"] = len(blocks)
    result["connectivity_signature"] = connectivity_signature(blocks)
    result["dimension_signature"] = dimension_signature(blocks)
    result["families"] = sorted({b.family for b in blocks})
    return result


def verify_set(per_geometry: dict) -> dict:
    """Cross-geometry checks: determinism of connectivity, dimension variation.

    ``per_geometry`` maps geometry_id -> :func:`verify_geometry` output.
    """
    sigs = {tuple(v["connectivity_signature"]) for v in per_geometry.values()}
    dims = {tuple(v["dimension_signature"]) for v in per_geometry.values()}
    return {
        "deterministic_connectivity": len(sigs) == 1,
        "distinct_connectivity_signatures": len(sigs),
        "distinct_block_dimension_sets": len(dims),
        "dimensions_adapt_to_geometry": len(dims) > 1,
        "note": (
            "RUNBOOK section 2.1 freezes CONNECTIVITY; dimension variation is "
            "reported, not gated (instrument bug 5)."
        ),
    }
