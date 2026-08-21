"""S5 - RBF + mandatory CAD reprojection (formerly "frozen topology with RBF").

RECLASSIFIED 2026-08-13. Pure frozen-RBF transfer FAILED the geometry-fidelity
gate by roughly 250-350x: OML nodes land 2.35-3.50% of chord off the true surface
against a 0.01% gate, while the landmark residual is machine zero (3.7e-15). It is
therefore not a fitting failure but a real limit of frozen deformation across this
design space - the RBF reproduces its landmarks exactly and still cannot reproduce
the surface between them.

The surviving method is **RBF + mandatory CAD reprojection**: S1's layout, with
OML nodes projected to their exact prescribed positions and RBF used only for the
free tip-cap interior, where deviation is small (1.6e-5 to 5.5e-5 m). Projection
is a required step, not a refinement. The original frozen-skeleton concept is a
recorded negative result.


RUNBOOK Section 6 S5: after S0-S4 baseline prototypes exist, select the strongest
baseline block skeleton as the seed; freeze its block graph, node indexing,
landmarks and boundary labels; map it to new geometries by RBF deformation;
project boundary nodes back to the exact CAD surface; store maximum/RMS
projection error, tangent error and RBF conditioning diagnostics; reject folds,
block overlap and connectivity changes.

The seed is S1. Of the prototypes measured in Stage 02 it is the only one that
passes geometry fidelity, watertightness and connectivity determinism together,
and a frozen skeleton is only as good as the layout it freezes - seeding from a
holed or drifting layout would propagate that defect to every geometry the
skeleton is transferred to.

What S5 actually tests is whether the design space is topologically homeomorphic
under a frozen correspondence. The honest measurement is not "does it produce a
mesh" - it always will - but how far the RBF-mapped nodes land from the true
surface before projection. That distance is the evidence for or against freezing
a skeleton across the DSE.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import RBFInterpolator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "S1_tip_first"))

import strategy_s1  # noqa: E402
from stage02_common import SurfaceBlock  # noqa: E402

STRATEGY_ID = "S5_FROZEN_RBF"


def _landmarks(blocks: list[SurfaceBlock], stride: int) -> np.ndarray:
    """Ordered landmark set taken from the OML blocks.

    Correspondence is by index, not by search: both geometries are built through
    the same section parameterisation, so node (i, j) of a given block is the
    same semantic point on both. That is exactly the frozen correspondence the
    strategy is meant to test.
    """
    pts = []
    for b in sorted(blocks, key=lambda x: x.name):
        if b.name.startswith("tip"):
            continue
        pts.append(b.xyz[::stride, ::stride, :].reshape(-1, 3))
    return np.concatenate(pts, axis=0)


def build_surface(
    reference_wing,
    target_wing,
    *,
    landmark_stride: int = 4,
    smoothing: float = 0.0,
    kernel: str = "thin_plate_spline",
    **s1_kwargs,
) -> tuple[list[SurfaceBlock], dict]:
    """Freeze the S1 skeleton on ``reference_wing`` and RBF-map it to ``target_wing``."""
    ref_blocks, ref_info = strategy_s1.build_surface(reference_wing, **s1_kwargs)
    tgt_blocks, _tgt_info = strategy_s1.build_surface(target_wing, **s1_kwargs)

    ref_names = [b.name for b in ref_blocks]
    tgt_names = [b.name for b in tgt_blocks]
    if ref_names != tgt_names or any(
        a.xyz.shape != b.xyz.shape for a, b in zip(ref_blocks, tgt_blocks, strict=True)
    ):
        raise ValueError(
            "frozen correspondence requires identical block names and dimensions; "
            f"reference {ref_names} vs target {tgt_names}"
        )

    src = _landmarks(ref_blocks, landmark_stride)
    dst = _landmarks(tgt_blocks, landmark_stride)

    rbf = RBFInterpolator(src, dst - src, kernel=kernel, smoothing=smoothing)

    mapped: list[SurfaceBlock] = []
    for b in ref_blocks:
        flat = b.xyz.reshape(-1, 3)
        moved = flat + rbf(flat)
        mapped.append(SurfaceBlock(name=b.name, xyz=moved.reshape(b.xyz.shape), family=b.family))

    # Deviation of the RBF map from the truth, BEFORE any projection. This is
    # the number that decides whether a frozen skeleton is viable across the
    # design space; projecting first would hide it.
    dev_oml, dev_tip = [], []
    for m, t in zip(mapped, tgt_blocks, strict=True):
        d = np.linalg.norm(m.xyz - t.xyz, axis=2).ravel()
        (dev_tip if m.name.startswith("tip") else dev_oml).append(d)
    dev_oml = np.concatenate(dev_oml)
    dev_tip = np.concatenate(dev_tip)

    ref_chord = float(np.ptp(np.concatenate([b.xyz.reshape(-1, 3) for b in tgt_blocks])[:, 0]))

    # Projection step. OML nodes go to their exact prescribed positions. For the
    # tip cap, only the INTERIOR is free: its boundary nodes lie on the OML tip
    # edge and on the cap's own block interfaces, so leaving them at their RBF
    # position tears the surface open - measured as 36 OML tip-edge nodes missing
    # from the cap on lhs7_01 and lhs7_02. Boundaries are therefore projected too,
    # which is what "RBF for the free tip-cap interior only" actually means.
    projected = []
    for m, t in zip(mapped, tgt_blocks, strict=True):
        if not m.name.startswith("tip"):
            projected.append(SurfaceBlock(name=m.name, xyz=t.xyz, family=m.family))
            continue
        xyz = t.xyz.copy()  # exact target boundary everywhere ...
        if xyz.shape[0] > 2 and xyz.shape[1] > 2:
            xyz[1:-1, 1:-1, :] = m.xyz[1:-1, 1:-1, :]  # ... RBF in the interior
        projected.append(SurfaceBlock(name=m.name, xyz=xyz, family=m.family))

    landmark_residual = float(np.abs(rbf(src) - (dst - src)).max())
    info = {
        "strategy_id": STRATEGY_ID,
        "seed_strategy": ref_info["strategy_id"],
        "seed_rationale": "only Stage 02 prototype passing fidelity, watertightness and determinism",
        "kernel": kernel,
        "smoothing": smoothing,
        "landmark_stride": landmark_stride,
        "landmark_count": int(len(src)),
        "landmark_residual_max_m": landmark_residual,
        "rbf_deviation_before_projection": {
            "oml_max_m": float(dev_oml.max()),
            "oml_rms_m": float(np.sqrt((dev_oml**2).mean())),
            "oml_max_frac_of_reference_chord": float(dev_oml.max()) / max(ref_chord, 1e-12),
            "tip_max_m": float(dev_tip.max()),
            "tip_rms_m": float(np.sqrt((dev_tip**2).mean())),
        },
        "connectivity_preserved": True,
        "block_count": len(projected),
        "note": (
            "OML nodes and all tip-cap BOUNDARY nodes are projected to their exact "
            "prescribed positions; RBF is retained only in the tip-cap interior. "
            "Leaving cap boundaries at their RBF position breaks watertightness."
        ),
    }
    return projected, info
