"""Self-test for the shared control module.

The shared module is the experimental control: if it drifts, every strategy's
numbers drift with it and the comparison silently stops meaning anything. This
reproduces the frozen Stage 02 S1 configuration through the migrated shared code
and asserts the recorded numbers, so a regression in `shared/` is caught here
rather than in a strategy's results.

It uses `S1_tip_first/s1_stage02_prior_art.py` — the archived Stage 02
implementation — purely as a fixture with a known answer. That file is prior art,
not S1's entry under ADR-0011.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/shared/selftest.py

Reference, `status` section 5F.3 — S1 frozen configuration on
`epse_calibration_lhs10_seed7` index 0 (`lhs7_00`), chord_points 49, uniform
chordwise, te_base_points 3, collar_points 3, realise_law True at 0.010 m:

    blocks                    8
    min scaled Jacobian    +0.045
    cell-size range           99x
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

STUDIES = Path(__file__).resolve().parents[1]
REPO_ROOT = STUDIES.parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(STUDIES))
sys.path.insert(0, str(STUDIES / "S1_tip_first"))

from shared import gates, geometry_sets, verify  # noqa: E402
from shared.ingestion import (  # noqa: E402
    SurfaceBlock,
    _map_sides_to_wing,
    section_loop_2d,
)
from shared.qc import orient_blocks_consistently, qc_blocks  # noqa: E402

import s1_stage02_prior_art as prior  # noqa: E402

# `feature_split_sides` is S1's BLOCKING decision, not shared ingestion — it puts
# corners on the LE and the two blunt-TE base corners, which is S1's answer and
# not cap4's. It moved into S1's folder on 2026-08-14 while S0 was being built.
feature_split_sides = prior.feature_split_sides

# The frozen Stage 02 S1 configuration, `status` section 5F.3.
CFG = dict(
    chord_points=49,
    distribution="uniform",
    te_base_points=3,
    collar_points=3,
    te_thickness=0.005,
    target_spanwise_cell=0.010,
)
EXPECTED = {"blocks": 8, "min_scaled_jacobian": 0.045, "cell_size_range": 99.0}
TOLERANCE = 0.10  # 10% — this guards against drift, not against float noise


def build_prior_art_s1(wing):
    """Stage 02's S1 surface, rebuilt through the migrated shared modules."""
    xsecs = list(wing.xsecs)
    sides_by_xsec = []
    for xsec in xsecs:
        coords, le_index = section_loop_2d(
            xsec, te_thickness=CFG["te_thickness"], te_thickness_abs_m=None
        )
        sides_by_xsec.append(
            feature_split_sides(
                coords,
                le_index,
                chord_points=CFG["chord_points"],
                te_base_points=CFG["te_base_points"],
                distribution=CFG["distribution"],
            )
        )
    oml = _map_sides_to_wing(wing, sides_by_xsec)

    le_line = np.asarray(
        wing.mesh_line(x_nondim=[0.0] * len(xsecs), z_nondim=[0.0] * len(xsecs), add_camber=False)
    )
    lengths = [float(np.linalg.norm(le_line[i + 1] - le_line[i])) for i in range(len(xsecs) - 1)]
    law = prior.geometric_progression_counts(lengths, target_cell=CFG["target_spanwise_cell"])
    oml = prior.realise_spanwise_law(oml, [p - 1 for p in law])

    blocks = [
        SurfaceBlock(name=n, xyz=b, family="wall")
        for n, b in zip(["oml_upper", "oml_lower", "te_base"], oml, strict=True)
    ]
    ring, ring_info = prior.oml_tip_ring_2d(sides_by_xsec[-1])
    cap, cap_info = prior.butterfly_from_ring(
        ring, ring_info["corner_indices"], collar_points=CFG["collar_points"]
    )
    blocks += [
        SurfaceBlock(name=n, xyz=prior.map_2d_patch_to_tip(wing, p), family="wall")
        for n, p in zip(cap_info["block_names"], cap, strict=True)
    ]
    return orient_blocks_consistently(blocks)


def main() -> int:
    wing = geometry_sets.wing("epse_calibration_lhs10_seed7", 0)
    blocks, orientation = build_prior_art_s1(wing)
    qc = qc_blocks(blocks)
    # Stage 02 used the chord FRACTION; the reference must match the mesh.
    fid = verify.oml_fidelity(wing, blocks, te_thickness_frac=CFG["te_thickness"])
    water = verify.watertight_tip(blocks)

    got = {
        "blocks": qc["block_count"],
        "min_scaled_jacobian": qc["global"]["min_scaled_jacobian"],
        "cell_size_range": qc["cell_size_range"],
    }
    print(f"{'metric':24s} {'expected':>12s} {'got':>12s}")
    failures = []
    for key, want in EXPECTED.items():
        have = got[key]
        ok = abs(have - want) <= TOLERANCE * abs(want)
        print(f"{key:24s} {want:12.4g} {have:12.4g}  {'OK' if ok else 'DRIFT'}")
        if not ok:
            failures.append(f"{key}: expected ~{want}, got {have}")

    print(f"\nwatertight tip          {water['watertight_tip']}")
    print(f"blocks reached by walk  {orientation['blocks_reached_by_edge_walk']}"
          f"/{orientation['block_count']}")
    print(f"enclosed signed volume  {orientation['signed_volume_before_global_flip']:+.4e}")
    print(f"fidelity worst frac     {fid['worst_frac_of_local_chord']:.3e} of local chord")
    print(f"fidelity unverified     {fid['fidelity_unverified_for_refined_blocks']} "
          f"{fid['skipped_spanwise_refined_blocks']}")

    # The spanwise law is realised, so fidelity is legitimately UNVERIFIED for the
    # refined blocks — COMMON_BRIEF section 9.5. `gates.surface_gate_checklist`
    # must treat that as a failure rather than a pass, and this asserts it does.
    passed, reasons = gates.surface_gate_checklist(
        qc, fid, orientation, water["watertight_tip"], deterministic_connectivity=True
    )
    print(f"\nsurface gate            {'PASS' if passed else 'FAIL'}")
    for r in reasons:
        print(f"  - {r}")
    if passed:
        failures.append(
            "surface gate PASSED on a spanwise-refined surface whose fidelity is "
            "unverified; the instrument-bug-6 guard is not working"
        )

    if failures:
        print("\nSELFTEST FAILED")
        for f in failures:
            print(f"  {f}")
        return 1
    print("\nSELFTEST OK — shared control reproduces the recorded Stage 02 numbers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
