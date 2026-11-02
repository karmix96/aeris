"""The tip cap: one chordwise H patch whose edge is the tip ring, node for node.

Ported from S8 (strategy_s8.build_tip_cap), where it replaced a "butterfly" cap that
folded. xi runs along the chord from a short nose arc to the base; eta runs across the
thickness from the lower to the upper surface. The nose arc carries the same number of
points as the base, so one quad patch closes the ring with no collapsed edge.
"""

from __future__ import annotations

import numpy as np

Array = np.ndarray


def tip_cap(ring: Array, n_side: int, n_base: int, smoothing: int) -> tuple[Array, dict]:
    """Patch (n_chord, n_base, 3) on the flat tip; i x j points outboard (+y)."""
    ring = np.asarray(ring, dtype=float)
    if n_base % 2 == 0:
        raise ValueError(f"n_base must be odd so the nose arc is centred on the leading edge; got {n_base}")
    half = (n_base - 1) // 2
    le = n_side - 1
    n_chord = n_side - half
    if n_chord < 3:
        raise ValueError("n_side is too small for this nose arc")

    upper = ring[: le + 1]                       # TE corner -> LE
    lower = ring[le: 2 * n_side - 1]             # LE -> TE corner
    base_inner = ring[2 * n_side - 1:]           # lower TE corner -> upper TE corner, interior only
    nose = np.vstack([upper[le - half:], lower[1: half + 1]])
    up_side = upper[: le - half + 1][::-1]       # nose end -> TE corner
    lo_side = lower[half:]                       # nose end -> TE corner
    base = np.vstack([lo_side[-1:], base_inner, up_side[-1:]])
    if not (len(nose) == len(base) == n_base and len(up_side) == len(lo_side) == n_chord):
        raise AssertionError("cap sides do not match the ring layout")

    xi = np.linspace(0.0, 1.0, n_chord)[:, None, None]
    et = np.linspace(0.0, 1.0, n_base)[None, :, None]
    patch = ((1 - et) * lo_side[:, None] + et * up_side[:, None]
             + (1 - xi) * nose[None, ::-1] + xi * base[None, :]
             - ((1 - xi) * (1 - et) * lo_side[0] + (1 - xi) * et * up_side[0]
                + xi * (1 - et) * lo_side[-1] + xi * et * up_side[-1]))

    perimeter = np.vstack([patch[0, :], patch[1:, -1], patch[-1, -2::-1], patch[-2::-1, 0]])
    gap = float(np.abs(np.sort(perimeter[:-1], axis=0) - np.sort(ring, axis=0)).max())
    if len(perimeter) != len(ring) + 1 or gap > 1e-12:
        raise AssertionError(f"cap edge is not the tip ring ({gap:.2e} m)")

    for _ in range(smoothing):                    # Laplacian sweeps, edges held
        patch[1:-1, 1:-1] = 0.25 * (patch[:-2, 1:-1] + patch[2:, 1:-1] + patch[1:-1, :-2] + patch[1:-1, 2:])

    mid_i, mid_j = patch.shape[0] // 2, patch.shape[1] // 2
    normal = np.cross(patch[mid_i + 1, mid_j] - patch[mid_i, mid_j], patch[mid_i, mid_j + 1] - patch[mid_i, mid_j])
    flipped = bool(normal[1] < 0.0)
    if flipped:
        patch = patch[:, ::-1]
    return patch, {"shape": [int(n_chord), int(n_base)], "edge_gap_m": gap, "eta_reversed": flipped,
                   "smoothing_sweeps": int(smoothing)}
