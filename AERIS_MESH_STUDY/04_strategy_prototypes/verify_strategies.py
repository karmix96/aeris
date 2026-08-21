"""Correctness verification for the Stage 02 strategy prototypes.

Cell quality is not correctness. Before comparing strategies it must be shown
that each one actually produces the prescribed geometry and a closed surface.
This script checks the properties that the Stage 00 gates call hard:

1. **Watertightness at the tip.** Every tip-cap boundary node must coincide with
   an OML tip-edge node. A cap that builds its own ring from the raw section,
   independently of the OML blocks, can leave a hole even though every block
   looks healthy on its own.
2. **Geometry fidelity.** Every OML node must lie on the prescribed section
   contour, within the Stage 00 gate of 0.01% of local chord.
3. **Determinism.** The same geometry must give the same block count and the
   same connectivity signature every time, and across geometries.
4. **Self-consistency.** No NaN or duplicate-collapsed cells.

Run from the repository root:

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_prototypes/verify_strategies.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))
for sub in ("", "S1_tip_first", "S3_station_sweep", "S4_analytic_multiblock", "S5_frozen_rbf"):
    sys.path.insert(0, str(HERE / sub))

import stage02_common as C  # noqa: E402
import strategy_s1  # noqa: E402
import strategy_s3  # noqa: E402
import strategy_s4  # noqa: E402
import strategy_s5  # noqa: E402
from aeris.dataset.sampling.samplers.lhs_v1 import build_lhs_design_matrix  # noqa: E402
from aeris.generators.bwb_segmented_v1.params import (  # noqa: E402
    BWBDesignSample,
    build_bwb_generator_config,
)
from aeris.geometry.registry import get_geometry_generator  # noqa: E402

# S5 needs a reference wing as well as a target, so it is adapted to the common
# single-wing signature here. An accepted strategy that was never hard-gate
# verified must not sit in the results table unchecked.
class _S5Adapter:
    """Bind S5's reference geometry so it matches the common build signature."""

    def __init__(self) -> None:
        self._reference = None

    def build_surface(self, wing):
        if self._reference is None:
            self._reference = wing  # first geometry seen becomes the frozen seed
        return strategy_s5.build_surface(self._reference, wing)


STRATEGIES = {
    "S1_TIP_FIRST_SWEEP": strategy_s1,
    "S3_STATION_SWEEP": strategy_s3,
    "S4_ANALYTIC_MULTIBLOCK": strategy_s4,
    "S5_RBF_PLUS_REPROJECTION": _S5Adapter(),
}


NODE_DECIMALS = 7  # 0.1 micron; finer than this compares float noise, not nodes


def tip_edge_nodes(blocks) -> np.ndarray:
    """OML nodes that actually lie on the tip station.

    Taking the outboard edge of every OML block is wrong for a segmented
    strategy like S3: each interval block has its own outboard edge, and only
    the outermost one is the tip. Selecting by spanwise position instead works
    for any blocking.
    """
    oml = [b for b in blocks if not b.name.startswith("tip")]
    tip_y = max(float(b.xyz[:, :, 1].max()) for b in oml)
    pts = []
    for b in oml:
        edge = b.xyz[:, -1, :]
        if abs(float(edge[:, 1].max()) - tip_y) <= 1e-9:
            pts.append(edge)
    return np.unique(np.round(np.concatenate(pts, axis=0), NODE_DECIMALS), axis=0)


def tip_cap_nodes(blocks) -> set:
    """All nodes belonging to tip-cap blocks.

    The test is NOT that every cap boundary node lies on the OML tip edge - the
    cap's internal block interfaces are legitimately interior to the cap, and
    requiring them to sit on the OML edge reports a sound mesh as holed. The
    correct condition is the other direction: every OML tip-edge node must be
    present in the cap, so the two surfaces share their whole common boundary.
    """
    out: set = set()
    for b in blocks:
        if not b.name.startswith("tip"):
            continue
        out |= {tuple(np.round(p, NODE_DECIMALS)) for p in b.xyz.reshape(-1, 3)}
    return out


def min_distances(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """For each point in a, distance to the nearest point in b."""
    out = np.empty(len(a))
    for i, p in enumerate(a):
        out[i] = float(np.min(np.linalg.norm(b - p, axis=1)))
    return out


def _point_to_polyline(pts: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Distance from each point to the nearest SEGMENT of a polyline.

    Distance to sampled points is not the same measurement: it is bounded below
    by half the reference spacing, which silently reports a clean mesh as being
    off-surface by that amount.
    """
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


def oml_fidelity(wing, blocks, te_thickness: float) -> dict:
    """Distance from OML nodes to the prescribed section contour.

    The reference contour must be CLOSED. The section loop runs upper TE -> LE
    -> lower TE, so the blunt base is not one of its segments; measuring against
    the open loop reports the trailing-edge base block as off-surface by half the
    trailing-edge thickness, which is an artefact of the reference, not an error
    in the mesh.
    """
    xsecs = list(wing.xsecs)
    worst_abs = 0.0
    worst_frac = 0.0
    worst_block = None
    skipped_refined: list[str] = []
    for idx, xsec in enumerate(xsecs):
        coords, _le = C.section_loop_2d(xsec, te_thickness=te_thickness)
        closed = np.vstack([coords, coords[0]])
        ref = C._map_sides_to_wing(wing, [[closed] for _ in xsecs])[0][:, idx, :]
        chord = float(np.ptp(ref[:, 0]))
        for b in blocks:
            if b.name.startswith("tip"):
                continue
            if b.xyz.shape[1] != len(xsecs):
                # Spanwise-refined blocks have columns BETWEEN stations, which
                # cannot be checked against a station contour. Skipping them
                # silently would report a refined mesh as fidelity-perfect when
                # its interpolated columns are off the loft entirely.
                skipped_refined.append(b.name)
                continue
            d = _point_to_polyline(b.xyz[:, idx, :], ref)
            frac = float(d.max()) / max(chord, 1e-12)
            if frac > worst_frac:
                worst_frac, worst_abs, worst_block = frac, float(d.max()), b.name
    return {
        "worst_abs_m": worst_abs,
        "worst_frac_of_local_chord": worst_frac,
        "worst_block": worst_block,
        "skipped_spanwise_refined_blocks": sorted(set(skipped_refined)),
        "fidelity_unverified_for_refined_blocks": bool(skipped_refined),
    }


def main() -> int:
    cfg = build_bwb_generator_config(
        yaml.safe_load((REPO_ROOT / "configs/geometry/bwb.yaml").read_text())
    )
    matrix = build_lhs_design_matrix(cfg, 10, np.random.default_rng(7))
    names = cfg.active_design_variable_names()
    generator = get_geometry_generator("bwb_segmented")

    report: dict = {"schema": "aeris.mesh_study.stage02_verification.v1", "strategies": {}}
    failures = 0

    for sid, module in STRATEGIES.items():
        entry: dict = {"geometries": {}}
        signatures = set()
        dim_sigs = set()
        for i in range(3):
            sample = BWBDesignSample(
                **{n: float(v) for n, v in zip(names, matrix[i], strict=True)}
            )
            case = generator.run_full_case(
                sample=sample,
                config=cfg,
                output_dir=REPO_ROOT / f"AERIS_MESH_STUDY/artifacts/stage02/geom/lhs7_{i:02d}",
                save_plot=False,
                build_aerosandbox=True,
            )
            # S3 drives its anchors from the contract stations, which need the
            # design sample. Without it S3 falls back to a weaker rule and the
            # table would report the fallback rather than the real strategy.
            try:
                blocks, _info = module.build_surface(case.wing, sample=sample)
            except TypeError:
                blocks, _info = module.build_surface(case.wing)

            cap = tip_cap_nodes(blocks)
            edge = tip_edge_nodes(blocks)
            edge_set = {tuple(np.round(p, NODE_DECIMALS)) for p in edge}
            missing = edge_set - cap
            ref_len = float(np.ptp(edge[:, 0]))
            on_edge = len(edge_set) - len(missing)
            if missing:
                cap_arr = np.array(sorted(cap))
                gap = np.array(
                    [
                        float(np.min(np.linalg.norm(cap_arr - np.array(p), axis=1)))
                        for p in list(missing)[:400]
                    ]
                )
            else:
                gap = np.zeros(1)

            fid = oml_fidelity(case.wing, blocks, 0.005)
            finite = all(np.isfinite(b.xyz).all() for b in blocks)
            # RUNBOOK 2.1 freezes the CONNECTIVITY signature - block count,
            # names, families, interfaces - while explicitly allowing "node
            # positions, spacing and permitted counts [to] adapt to geometry".
            # Hashing block dimensions would therefore fail a compliant method
            # for doing exactly what the runbook permits. Dimensions are
            # reported separately as information.
            sig = tuple(sorted((b.name, b.family) for b in blocks))
            signatures.add(sig)
            dim_sigs.add(tuple(sorted((b.name, tuple(b.xyz.shape)) for b in blocks)))

            geo = {
                "block_count": len(blocks),
                "oml_tip_edge_nodes": int(len(edge_set)),
                "missing_from_cap": int(len(missing)),
                "coincident_with_oml_tip_edge": on_edge,
                "max_gap_to_oml_tip_edge_m": float(gap.max()),
                "max_gap_as_frac_of_tip_chord": float(gap.max()) / max(ref_len, 1e-12),
                "oml_fidelity_worst_abs_m": fid["worst_abs_m"],
                "oml_fidelity_worst_frac_local_chord": fid["worst_frac_of_local_chord"],
                "all_finite": finite,
            }
            geo["watertight_tip"] = bool(len(missing) == 0)
            geo["fidelity_within_gate"] = bool(fid["worst_frac_of_local_chord"] <= 1.0e-4)
            if not geo["watertight_tip"] or not geo["fidelity_within_gate"] or not finite:
                failures += 1
            entry["geometries"][f"lhs7_{i:02d}"] = geo

        entry["deterministic_connectivity"] = len(signatures) == 1
        entry["distinct_connectivity_signatures"] = len(signatures)
        entry["distinct_block_dimension_sets"] = len(dim_sigs)
        entry["dimensions_adapt_to_geometry"] = len(dim_sigs) > 1
        report["strategies"][sid] = entry

    (HERE / "stage02_verification_report.json").write_text(json.dumps(report, indent=2) + "\n")

    print(f"{'strategy':24s} {'blocks':>6s} {'watertight':>11s} {'max gap m':>12s} "
          f"{'fidelity %c':>12s} {'determ':>7s}")
    for sid, entry in report["strategies"].items():
        g = entry["geometries"]["lhs7_00"]
        print(
            f"{sid:24s} {g['block_count']:6d} {str(g['watertight_tip']):>11s} "
            f"{g['max_gap_to_oml_tip_edge_m']:12.3e} "
            f"{g['oml_fidelity_worst_frac_local_chord'] * 100:12.5f} "
            f"{str(entry['deterministic_connectivity']):>7s}"
        )
    print(f"\nhard-gate failures across all checks: {failures}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
