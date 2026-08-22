"""Diagnostic: boundary-layer thickness against the numerical trailing-edge opening.

Gmsh's ``extrudeBoundaryLayer`` performs no collision detection and no layer
squeezing.  Opposing prism fronts extruded off a thin numerical trailing edge
therefore interpenetrate once the stack is thicker than the edge carrying it,
and Gmsh aborts core meshing with a PLC segment/facet error.

This script measures where that limit sits for the real development geometry.
It runs a *graded* configuration that keeps production size ratios while scaling
absolute lengths so the mesh fits a 16 GiB laptop.  It is a diagnostic only: the
preregistered levels in ``POLICY.yaml`` are never modified and no campaign claim
may be drawn from it.

    python bl_te_probe.py sweep      # BL thickness vs Gmsh success
    python bl_te_probe.py audit FIRST GROWTH DIRNAME
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from S7_unstructured_gmsh_su2 import geometry as G  # noqa: E402
from S7_unstructured_gmsh_su2 import gmsh_pipeline as P  # noqa: E402
from S7_unstructured_gmsh_su2 import mesh_audit as A  # noqa: E402
from S7_unstructured_gmsh_su2.common import load_policy  # noqa: E402

GRADED = {
    "evidence_tier": "laptop_smoke",
    "campaign_claims_forbidden": True,
    "surface_edge_over_L": 0.080,
    "te_surface_edge_over_L": 0.020,
    "tip_surface_edge_over_L": 0.030,
    "prism_layers": 8,
    # Production keeps the near core slightly COARSER than the surface triangles
    # (coarse: 0.050 core vs 0.030 surface).  An earlier probe inverted that and
    # asked the core to be finer than the cap it sits on, which forces refinement
    # right at the prism cap.  Mirror the production ratio instead.
    "near_core_edge_over_L": 0.133,
    "far_core_edge_over_L": 0.280,
    "wake_edge_over_L": 0.050,
    "farfield": {
        "upstream_over_L": 3.0,
        "downstream_over_L": 5.0,
        "radial_over_L": 3.0,
        "wake_length_over_L": 4.0,
    },
    "su2_iterations": 5,
    "su2_restart_iterations": 5,
}

SCHEDULES = ((1.0e-3, 1.35), (3.0e-4, 1.30), (1.0e-4, 1.30), (5.0e-5, 1.25))
ROOT = Path(__file__).resolve().parents[2] / (
    "artifacts/strategy_studies/S7_unstructured_gmsh_su2/lead_work/bl_sweep"
)


def _policy(first: float, growth: float) -> dict:
    policy = copy.deepcopy(load_policy())
    level = dict(GRADED)
    level["first_cell_height_over_L"] = first
    level["prism_growth_ratio"] = growth
    policy["laptop_smoke"] = level
    # The graded probe is coarser than any preregistered level, so its facet
    # budget is relaxed to match its own resolution.  Every other gate is stock.
    policy["mesh_gates"]["source_geometry"]["max_facet_centroid_over_local_chord"][
        "laptop_smoke"
    ] = 6.0e-3
    # Measure the raw extrusion limit rather than the derived layer cap.
    policy["gmsh"]["boundary_layer"]["derive_prism_layers_from_te_opening"] = False
    return policy


def _surface(policy: dict):
    case = G.build_pygeo_case("lhs100_seed42", 0, ROOT / "pygeo")
    return G.build_surface(
        case, level="laptop_smoke", te_variant="te_1p0mm", policy=policy
    )


def sweep() -> int:
    for first, growth in SCHEDULES:
        policy = _policy(first, growth)
        surface = _surface(policy)
        spec = P.resolved_mesh_spec(
            surface, level="laptop_smoke", candidate_index=0, policy=policy
        )
        total_mm = spec["boundary_layer_total_thickness_m"] * 1000.0
        te_mm = surface.metadata["fidelity"]["min_realized_te_opening_m"] * 1000.0
        target = ROOT / f"a_{first:g}_{growth:g}"
        if target.exists():
            shutil.rmtree(target)
        started = time.time()
        try:
            report = P.generate_mesh(
                surface,
                output_dir=target,
                level="laptop_smoke",
                candidate_index=0,
                policy=policy,
            )
            outcome = f"OK {report['gmsh_element_counts']}"
        except Exception as exc:  # noqa: BLE001 - the failure mode is the result
            outcome = f"FAIL {str(exc)[:48]}"
        print(
            f"first={first:.1e} growth={growth:.2f} BL={total_mm:7.3f} mm "
            f"({total_mm / te_mm:5.2f}x TE) -> {outcome} ({time.time() - started:.0f}s)",
            flush=True,
        )
    return 0


def audit(first: float, growth: float, dirname: str) -> int:
    policy = _policy(first, growth)
    surface = _surface(policy)
    target = ROOT / dirname
    report = A.audit_mesh(
        msh_path=target / "mesh.msh",
        su2_path=target / "mesh.su2",
        surface=surface,
        level="laptop_smoke",
        candidate_index=0,
        output_path=target / "mesh_audit.json",
        policy=policy,
    )
    prisms = report["prism_layers"]
    quality = report["quality"]
    faces = report["faces"]
    print(
        json.dumps(
            {
                "dir": dirname,
                "counts": report["counts"],
                "negative_cells": report["volume"]["negative_cell_count"],
                "prism_cover": prisms["wall_face_coverage_fraction"],
                "prism_continuity": prisms["connected_column_fraction"],
                "te_minSJ": prisms["by_label"]["wall_te"][
                    "minimum_prism_scaled_jacobian"
                ],
                "tip_minSJ": prisms["by_label"]["wall_tip"][
                    "minimum_prism_scaled_jacobian"
                ],
                "tip_invalid": prisms["by_label"]["wall_tip"]["invalid_prism_count"],
                "tet_minSICN_min": quality["tet_minSICN"]["min"],
                "tet_minSICN_p01": quality["tet_minSICN"]["p01"],
                "skew_p99": faces["equiangle_skewness"]["p99"],
                "nonortho_p99": faces["nonorthogonality_deg"]["p99"],
                "core_vol_ratio_max": faces["core_adjacent_volume_ratio"]["max"],
                "accepted": report["acceptance"]["accepted"],
                "failures": report["acceptance"]["failures"],
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "sweep":
        return sweep()
    if len(sys.argv) == 5 and sys.argv[1] == "audit":
        return audit(float(sys.argv[2]), float(sys.argv[3]), sys.argv[4])
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
