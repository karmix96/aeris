"""S4's volume — constructed, not marched.

RUNBOOK §6 S4: "Generate the volume directly using TFI/elliptic/Poisson methods; do
not require pyHyp for this candidate." ADR-0014 restates ADR-0011 §6.1's volume gate
so a constructed volume can be scored against the same thresholds.

================================================================================
WHAT IS BUILT, AND WHAT IS NOT
================================================================================

**Built: the boundary-layer volume**, Type 1 (the wing surface) out to Type 2 (the
outer boundary of the boundary-layer mesh, §2.2.1b Eq. 2, `delta = 0.06 c_local`),
with the wall-normal node distribution clustered to the same first-cell height `s0`
every other strategy marches from.

**Not built: the interior field and the far field.** Eqs. 9-11 size an interior-field
boundary at `eta1 c_root` and beyond, and Type 4 sits at 100-150 MAC. The
implementation note is explicit that "farfield extent must wait for the farfield
independence study", and the interior field between them cannot be closed as an
O-topology — outside the boundary layer the trailing-edge region needs H-blocks in
the wake, which terminate on the far field that is deferred. Building half of that
and calling it a volume would be worse than not building it.

ADR-0014 §4 records what this costs the comparison, and the answer is: less than it
sounds. Validity is comparable, because the near field is where every inverted cell
in this study has appeared. Minimum quality is comparable, because on every march so
far the worst cell has been in the near-wall region. Cell counts are **not**
comparable and must never be tabled next to S1's without that sentence attached.

================================================================================
THE ONE THING THAT DECIDES WHETHER THIS WORKS
================================================================================

The offset surface must stay watertight and fold-free. A node shared between two
blocks must receive **one** normal and **one** delta, or the two blocks pull apart
and the volume is not a volume. So normals are accumulated in a global node table
keyed on rounded coordinates — the same `NODE_DECIMALS` convention `shared/verify.py`
uses for its coincidence tests — rather than per block.

Outward offset from a convex surface cannot fold, and the wing is convex nearly
everywhere; the places to watch are the two blunt-trailing-edge base corners, where a
single averaged normal has to serve a 90 degree turn, and the tip edge. Both are
measured rather than assumed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _p in (str(REPO_ROOT / "src"), str(STUDIES), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import strategy_s4 as S4  # noqa: E402
from shared.gates import NODE_DECIMALS  # noqa: E402
from shared.ingestion import MeshBuildError  # noqa: E402

Array = np.ndarray


#: Near-wall first-cell height as a fraction of the bounding-box diagonal, taken
#: from `aeris.cfd.meshing.pyhyp_options.GRID_LEVELS` so S4's first cell is the same
#: PHYSICAL size as the one every other strategy marches from. This is not borrowed
#: topology — it is the y+ condition, a property of the flow rather than of a
#: meshing strategy, and a volume built to a different near-wall spacing could not
#: be compared with S1's at all.
S0_FRAC = {"smoke": 8.8e-06, "fine": 6.0e-06, "production": 4.4e-06}


def S0_for(blocks, level: str) -> float:
    """First-cell height for this surface at this level, in metres."""
    from shared.pyhyp_runner import characteristic_length

    if level not in S0_FRAC:
        raise MeshBuildError(f"unknown level {level!r}; known: {sorted(S0_FRAC)}")
    return float(S0_FRAC[level]) * float(characteristic_length(blocks))


def _keys(xyz: Array) -> np.ndarray:
    return np.round(np.asarray(xyz, dtype=float), NODE_DECIMALS)


def _block_node_normals(xyz: Array) -> Array:
    """Un-normalised node normals for one ``(ni, nj, 3)`` patch.

    Central differences along both surface directions, one-sided at the borders, so
    every node gets a normal including the corners. The magnitude carries the local
    cell area, which is what makes the global accumulation area-weighted.
    """
    d0 = np.gradient(xyz, axis=0)
    d1 = np.gradient(xyz, axis=1)
    return np.cross(d0, d1)


def vertex_normals(blocks) -> tuple[dict, float]:
    """One outward unit normal per distinct node, shared across blocks.

    Returns ``({node_key: normal}, enclosed_volume_sign)``. The sign comes from the
    divergence theorem over the whole closed surface, so "outward" is decided once
    for the mesh rather than block by block.
    """
    acc: dict[tuple, np.ndarray] = {}
    three_v = 0.0
    for b in blocks:
        xyz = np.asarray(b.xyz, dtype=float)
        n = _block_node_normals(xyz)
        # **Area-weighted**, deliberately, and this was measured rather than assumed.
        # Eq. 8 blends the tip normal with the spanwise direction *unweighted*, and a
        # unit-normalised accumulation was built to match that literally. It is not
        # the same object: Eq. 8 governs the paper's Type 1 control-vertex normals,
        # which `strategy_s4.surface_normals` implements faithfully, whereas this is
        # a discrete surface-mesh normal field. Unit-normalising here made the volume
        # slightly worse (174 inverted cells against 147) and produced a genuinely
        # degenerate node on `lhs100_seed42_002`, where two blocks' unit normals at a
        # shared node cancelled and the sum went to zero — an outcome the area weight
        # cannot produce, because the larger cell always wins.
        k = _keys(xyz).reshape(-1, 3)
        nf = n.reshape(-1, 3)
        for key, vec in zip(map(tuple, k), nf, strict=True):
            acc[key] = acc.get(key, 0.0) + vec
        # Divergence theorem on the quad faces: sum(centroid . area_normal) = 3V.
        p00, p10, p11, p01 = xyz[:-1, :-1], xyz[1:, :-1], xyz[1:, 1:], xyz[:-1, 1:]
        face_n = 0.5 * np.cross(p11 - p00, p01 - p10)
        centroid = 0.25 * (p00 + p10 + p11 + p01)
        three_v += float(np.einsum("...i,...i->...", centroid, face_n).sum())

    sign = -1.0 if three_v < 0.0 else 1.0
    out = {}
    for key, vec in acc.items():
        norm = float(np.linalg.norm(vec))
        if norm < 1e-14:
            raise MeshBuildError(f"degenerate node normal at {key}")
        out[key] = sign * np.asarray(vec) / norm
    return out, sign * three_v / 3.0


def local_chords(wing) -> tuple[int, np.ndarray, np.ndarray]:
    """(spanwise axis, spanwise station coordinates, chord at each station)."""
    xsecs = list(wing.xsecs)
    le = np.asarray([np.asarray(x.xyz_le, dtype=float) for x in xsecs])
    axis = int(np.argmax(np.ptp(le, axis=0)))
    return axis, le[:, axis], np.asarray([float(x.chord) for x in xsecs])


def normal_distribution(n: int, first: float, total: float) -> Array:
    """Node parameters in [0, 1] with the first spacing equal to ``first/total``.

    A geometric series solved for the growth ratio, which is what a hyperbolic
    marcher produces and what makes S4's near-wall cell the same size as the one
    every other strategy starts its march from. Falls back to uniform when the
    requested first cell is already larger than a uniform one.
    """
    n = int(n)
    if n < 3:
        raise MeshBuildError(f"need at least 3 wall-normal points, got {n}")
    cells = n - 1
    f = float(first) / float(total)
    if f <= 0.0 or f >= 1.0 / cells:
        return np.linspace(0.0, 1.0, n)

    lo, hi = 1.0 + 1e-9, 3.0
    for _ in range(200):  # bisection on sum(f * r^i) == 1
        mid = 0.5 * (lo + hi)
        s = f * (mid**cells - 1.0) / (mid - 1.0)
        if s < 1.0:
            lo = mid
        else:
            hi = mid
    r = 0.5 * (lo + hi)
    steps = f * r ** np.arange(cells)
    t = np.concatenate([[0.0], np.cumsum(steps)])
    return t / t[-1]


def build_volume(
    wing,
    blocks,
    *,
    bl_points: int,
    s0: float,
    delta_frac: float = S4.DELTA_BL_FRAC,
    smoothing_passes: int = 0,
) -> tuple[dict, dict]:
    """The boundary-layer volume: ``{name: (bl_points, ni, nj, 3)}`` plus a report."""
    normals, enclosed = vertex_normals(blocks)
    axis, stations, chords = local_chords(wing)

    t = normal_distribution(bl_points, first=s0, total=1.0)  # normalised; scaled per node

    offsets: dict[str, Array] = {}
    deltas: dict[str, Array] = {}
    for b in blocks:
        xyz = np.asarray(b.xyz, dtype=float)
        keys = _keys(xyz)
        n = np.stack(
            [normals[tuple(k)] for k in keys.reshape(-1, 3)], axis=0
        ).reshape(xyz.shape)
        c_local = np.interp(xyz[..., axis], stations, chords)
        d = float(delta_frac) * c_local
        offsets[b.name] = n
        deltas[b.name] = d

    if smoothing_passes:
        offsets, deltas = _smooth_offsets(blocks, offsets, deltas, smoothing_passes)

    volume, folded = {}, []
    for b in blocks:
        xyz = np.asarray(b.xyz, dtype=float)
        outer = xyz + (deltas[b.name][..., None] * offsets[b.name])
        # 1D TFI along the wall normal: the near-wall law applied between the two
        # bounding surfaces. Straight normals make this exact rather than blended.
        tt = t.reshape(-1, 1, 1, 1)
        volume[b.name] = xyz[None, ...] * (1.0 - tt) + outer[None, ...] * tt
        if float(np.min(deltas[b.name])) <= 0.0:
            folded.append(b.name)

    report = {
        "route": "direct",
        "layer": "boundary_layer_only",
        "bl_points": int(bl_points),
        "s0_m": float(s0),
        "delta_frac_of_chord": float(delta_frac),
        "delta_range_m": [
            float(min(d.min() for d in deltas.values())),
            float(max(d.max() for d in deltas.values())),
        ],
        "first_cell_over_s0": 1.0,
        "enclosed_surface_volume_m3": float(enclosed),
        "distinct_nodes": len(normals),
        "smoothing_passes": int(smoothing_passes),
        "degenerate_delta_blocks": folded,
        "not_built": "interior field (Eqs. 9-11) and far field (Type 4) — ADR-0014 §4",
    }
    return volume, report


def _smooth_offsets(blocks, offsets, deltas, passes: int):
    """Laplacian passes on the offset field, shared across blocks by node key."""
    for _ in range(int(passes)):
        acc_n: dict[tuple, np.ndarray] = {}
        acc_d: dict[tuple, float] = {}
        cnt: dict[tuple, int] = {}
        for b in blocks:
            keys = _keys(b.xyz)
            n, d = offsets[b.name], deltas[b.name]
            ni, nj = keys.shape[0], keys.shape[1]
            for i in range(ni):
                for j in range(nj):
                    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        a, c = i + di, j + dj
                        if 0 <= a < ni and 0 <= c < nj:
                            k = tuple(keys[i, j])
                            acc_n[k] = acc_n.get(k, 0.0) + n[a, c]
                            acc_d[k] = acc_d.get(k, 0.0) + float(d[a, c])
                            cnt[k] = cnt.get(k, 0) + 1
        for b in blocks:
            keys = _keys(b.xyz)
            n, d = offsets[b.name].copy(), deltas[b.name].copy()
            for i in range(keys.shape[0]):
                for j in range(keys.shape[1]):
                    k = tuple(keys[i, j])
                    if cnt.get(k):
                        v = 0.5 * n[i, j] + 0.5 * acc_n[k] / cnt[k]
                        n[i, j] = v / max(float(np.linalg.norm(v)), 1e-14)
                        d[i, j] = 0.5 * d[i, j] + 0.5 * acc_d[k] / cnt[k]
            offsets[b.name], deltas[b.name] = n, d
    return offsets, deltas
