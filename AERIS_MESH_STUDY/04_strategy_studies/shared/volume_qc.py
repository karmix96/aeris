"""In-house volume QC for a strategy that does not march — SHARED CONTROL.

ADR-0014. `shared/gates.py`'s volume checklist is phrased in terms of pyHyp's
report, and RUNBOOK section 6 S4 exempts S4 from pyHyp. This module supplies the
same five facts (ADR-0014 section 3.1, V1-V5) from the mesh itself.

**Two things this module deliberately does not do.**

1. It does **not** reimplement cell volume. `aeris.cfd.meshing.volume_audit.
   signed_cell_volumes` is the repository's authority for hexahedral volume and it
   is imported, not copied. Instrument bug 9 was exactly this mistake — a quality
   number recomputed a second way for one caller's convenience reported 7 folded
   cells and a minimum of -0.132 on a mesh that was fine.
2. It does **not** invent a threshold. Every number it is compared against comes
   from ADR-0008 via `gates.py`.

What it *does* add is the hexahedral scaled Jacobian, which the repository did not
have — `aeris.cfd.meshing.quality.scaled_jacobian` is for quads. It is defined here
in the same *kind* as the quad version so the two are read the same way:

    At each of a cell's 8 corners take the three incident edge vectors, each
    oriented along the positive element direction, and form
    ``sign * det(e_i, e_j, e_k) / (|e_i| |e_j| |e_k|)`` where ``sign`` is
    ``(-1)**(a+b+c)`` for the corner at local coordinates (a, b, c). The cell's
    value is the minimum over its 8 corners; a perfect cube scores +1.0 at every
    corner, and a folded cell goes negative.

Handedness is resolved **once per mesh**, from the sign of the total signed volume,
not per block — the same rule `qc.orient_blocks_consistently` applies to surfaces.
A mesh built left-handed throughout is a labelling convention, not a folded mesh;
a mesh with both signs present has real inverted cells and is reported as such.

Verified against pyHyp before use — see :func:`equivalence_against_pyhyp` and
ADR-0014 section 3.4.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from aeris.cfd.meshing.volume_audit import signed_cell_volumes  # noqa: E402

Array = np.ndarray

VOLUME_QC_SCHEMA = "aeris.mesh_study.direct_volume_qc.v1"


def hex_scaled_jacobian(nodes: Array, *, orientation: float = 1.0) -> Array:
    """Per-cell minimum scaled corner Jacobian for a ``(nk, nj, ni, 3)`` block.

    Returns shape ``(nk-1, nj-1, ni-1)``. ``orientation`` is +1 or -1 and is the
    mesh-wide handedness resolved by :func:`volume_report`; it is not a per-block
    free choice, because letting each block pick its own sign would report a folded
    block as perfect.
    """
    nodes = np.asarray(nodes, dtype=float)
    if nodes.ndim != 4 or nodes.shape[-1] != 3:
        raise ValueError(f"expected a (nk, nj, ni, 3) block, got {nodes.shape}")
    if min(nodes.shape[:3]) < 2:
        raise ValueError(f"block has no cells: {nodes.shape}")

    def corner(a: int, b: int, c: int) -> Array:
        sk = slice(1, None) if a else slice(None, -1)
        sj = slice(1, None) if b else slice(None, -1)
        si = slice(1, None) if c else slice(None, -1)
        return nodes[sk, sj, si]

    minimum: Array | None = None
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                origin = corner(a, b, c)
                e_k = corner(1 - a, b, c) - origin  # along axis 0
                e_j = corner(a, 1 - b, c) - origin  # along axis 1
                e_i = corner(a, b, 1 - c) - origin  # along axis 2
                # The triple product is ordered (axis 2, axis 1, axis 0) so that
                # "positive" here means the same thing as "positive" in
                # `signed_cell_volumes`. The opposite order passes a unit-cube test
                # just as convincingly and then scores every valid pyHyp volume at
                # -1.0; that is how this ordering was fixed (ADR-0014 section 3.4).
                det = np.einsum("...i,...i->...", e_i, np.cross(e_j, e_k))
                lengths = (
                    np.linalg.norm(e_k, axis=-1)
                    * np.linalg.norm(e_j, axis=-1)
                    * np.linalg.norm(e_i, axis=-1)
                )
                denom = np.where(lengths > 0.0, lengths, np.inf)
                value = ((-1.0) ** (a + b + c)) * orientation * det / denom
                minimum = value if minimum is None else np.minimum(minimum, value)
    if minimum is None:  # pragma: no cover - loops above are fixed and non-empty
        raise RuntimeError("no hexahedral corners were evaluated")
    return minimum


def _worst_cell_diagnostic(nodes: Array, index: tuple[int, int, int]) -> dict:
    """Return local geometry for one cell without retaining full quality arrays."""
    k, j, i = index
    edges = []
    for b in (0, 1):
        for c in (0, 1):
            edges.append(nodes[k + 1, j + b, i + c] - nodes[k, j + b, i + c])
    for a in (0, 1):
        for c in (0, 1):
            edges.append(nodes[k + a, j + 1, i + c] - nodes[k + a, j, i + c])
    for a in (0, 1):
        for b in (0, 1):
            edges.append(nodes[k + a, j + b, i + 1] - nodes[k + a, j + b, i])
    lengths = np.linalg.norm(np.asarray(edges), axis=1)
    lower_face = np.mean(nodes[k, j : j + 2, i : i + 2], axis=(0, 1))
    wall_face = np.mean(nodes[0, j : j + 2, i : i + 2], axis=(0, 1))
    return {
        "cell_index_kji": [k, j, i],
        "wall_layer_index": k,
        "wall_distance_m": float(np.linalg.norm(lower_face - wall_face)),
        "min_edge_length_m": float(lengths.min()),
        "max_edge_length_m": float(lengths.max()),
        "edge_length_ratio": float(lengths.max() / lengths.min()),
        "cell_center_xyz_m": np.mean(
            nodes[k : k + 2, j : j + 2, i : i + 2], axis=(0, 1, 2)
        ).tolist(),
    }


def volume_report(blocks: dict[str, Array]) -> dict:
    """ADR-0014 section 3.1 V1-V5 for a set of ``{name: (nk, nj, ni, 3)}`` blocks.

    ``blocks`` is whatever the strategy built; the same dict shape
    `aeris.cfd.meshing.volume_audit.read_volume_blocks` returns for a pyHyp CGNS, so
    the two routes can be pointed at the same data (ADR-0014 section 3.4).
    """
    if not blocks:
        return {
            "schema": VOLUME_QC_SCHEMA,
            "route": "direct",
            "generation_completed": False,
            "reason": "no blocks were produced",
        }

    # V1 — every block finite and dimensioned. Checked before anything is measured,
    # because a NaN silently makes every comparison below False rather than True.
    non_finite = {
        name: int(np.count_nonzero(~np.isfinite(np.asarray(b, dtype=float))))
        for name, b in blocks.items()
    }
    total_non_finite = sum(non_finite.values())
    degenerate_shapes = {
        name: tuple(np.asarray(b).shape)
        for name, b in blocks.items()
        if np.asarray(b).ndim != 4 or np.asarray(b).shape[-1] != 3
        or min(np.asarray(b).shape[:3]) < 2
    }

    if total_non_finite or degenerate_shapes:
        return {
            "schema": VOLUME_QC_SCHEMA,
            "route": "direct",
            "generation_completed": False,
            "block_count": len(blocks),
            "non_finite_nodes": total_non_finite,
            "non_finite_by_block": {k: v for k, v in non_finite.items() if v},
            "degenerate_block_shapes": degenerate_shapes,
        }

    volumes = {name: signed_cell_volumes(np.asarray(b, dtype=float)) for name, b in blocks.items()}
    total_signed = float(sum(float(v.sum()) for v in volumes.values()))
    orientation = -1.0 if total_signed < 0.0 else 1.0

    per_block = {}
    jac_min = np.inf
    jac_sum = 0.0
    jac_n = 0
    jac_ge_030 = 0
    jac_lt_010 = 0
    jac_lt_015 = 0
    worst_cell: dict | None = None
    for name, b in blocks.items():
        nodes = np.asarray(b, dtype=float)
        vol = orientation * volumes[name]
        jac = hex_scaled_jacobian(nodes, orientation=orientation)
        minimum_index = tuple(int(value) for value in np.unravel_index(np.argmin(jac), jac.shape))
        diagnostic = _worst_cell_diagnostic(nodes, minimum_index)
        diagnostic["block"] = name
        diagnostic["min_scaled_quality"] = float(jac[minimum_index])
        if (
            worst_cell is None
            or diagnostic["min_scaled_quality"] < worst_cell["min_scaled_quality"]
        ):
            worst_cell = diagnostic
        jac_min = min(jac_min, float(jac.min()))
        jac_sum += float(jac.sum())
        jac_n += int(jac.size)
        jac_ge_030 += int(np.count_nonzero(jac >= 0.30))
        jac_lt_010 += int(np.count_nonzero(jac < 0.10))
        jac_lt_015 += int(np.count_nonzero(jac < 0.15))
        per_block[name] = {
            "shape": tuple(int(s) for s in np.asarray(b).shape[:3]),
            "cells": int(vol.size),
            "min_volume": float(vol.min()),
            "min_scaled_quality": float(jac.min()),
            "mean_scaled_quality": float(jac.mean()),
            "inverted_cells": int(np.count_nonzero(vol <= 0.0)),
            "low_quality_cells": int(np.count_nonzero(jac <= 0.0)),
            "cells_below_0_10": int(np.count_nonzero(jac < 0.10)),
            "cells_below_0_15": int(np.count_nonzero(jac < 0.15)),
            "worst_cell": diagnostic,
        }

    cells = sum(v["cells"] for v in per_block.values())
    return {
        "schema": VOLUME_QC_SCHEMA,
        "route": "direct",
        "generation_completed": True,
        "orientation": orientation,
        "block_count": len(blocks),
        "total_cells": cells,
        "min_volume": min(v["min_volume"] for v in per_block.values()),
        "inverted_cells": sum(v["inverted_cells"] for v in per_block.values()),
        "min_scaled_quality": jac_min,
        "mean_scaled_quality": jac_sum / jac_n,
        # ADR-0014 V5: the direct route has no marching layers, so the equivalent
        # "no failing region" test is per BLOCK.
        "low_quality_blocks": [
            n for n, v in per_block.items() if v["min_scaled_quality"] <= 0.0
        ],
        "fraction_at_or_above_0_30": jac_ge_030 / jac_n,
        "cells_below_0_10": jac_lt_010,
        "cells_below_0_15": jac_lt_015,
        "worst_cell": worst_cell,
        "per_block": per_block,
    }


def equivalence_against_pyhyp(cgns_path: Path) -> dict:
    """ADR-0014 section 3.4 — run the in-house metric on a volume pyHyp scored.

    S4's volume cannot be scored until this agrees with pyHyp on a mesh pyHyp
    already passed. An unverified instrument is how Stage 02 produced four numbers
    that had to be withdrawn.
    """
    from aeris.cfd.meshing.volume_audit import read_volume_blocks

    blocks = read_volume_blocks(Path(cgns_path))
    report = volume_report(blocks)
    report["source_cgns"] = str(cgns_path)
    return report
