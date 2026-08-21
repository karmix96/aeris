"""Diagnostic: is S7 quality limited by the pipeline or by the laptop tier's grading?

Runs the real index-0 BWB through Gmsh at a *graded* configuration that keeps
production size ratios (near/far = 7, prism-to-core step ~5) while scaling all
absolute lengths so the mesh fits a 16 GiB laptop.  This is a diagnostic only:
POLICY levels are untouched and campaign claims are forbidden from it.
"""
from __future__ import annotations
import copy, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from S7_unstructured_gmsh_su2 import geometry as G           # noqa: E402
from S7_unstructured_gmsh_su2 import gmsh_pipeline as P      # noqa: E402
from S7_unstructured_gmsh_su2 import mesh_audit as A         # noqa: E402
from S7_unstructured_gmsh_su2.common import load_policy      # noqa: E402

GRADED = {
    "evidence_tier": "laptop_smoke",
    "campaign_claims_forbidden": True,
    "surface_edge_over_L": 0.080,
    "te_surface_edge_over_L": 0.020,
    "tip_surface_edge_over_L": 0.030,
    "first_cell_height_over_L": 1.0e-3,
    "prism_layers": 8,
    "prism_growth_ratio": 1.35,
    "near_core_edge_over_L": 0.040,
    "far_core_edge_over_L": 0.280,
    "wake_edge_over_L": 0.050,
    "farfield": {"upstream_over_L": 3.0, "downstream_over_L": 5.0,
                 "radial_over_L": 3.0, "wake_length_over_L": 4.0},
    "su2_iterations": 5, "su2_restart_iterations": 5,
}

def main() -> int:
    pol = copy.deepcopy(load_policy())
    pol["laptop_smoke"] = GRADED
    pol["mesh_gates"]["source_geometry"]["max_facet_centroid_over_local_chord"]["laptop_smoke"] = 6.0e-3
    out = Path(__file__).resolve().parents[3] / (
        "artifacts/strategy_studies/S7_unstructured_gmsh_su2/lead_work/graded_probe")
    out.mkdir(parents=True, exist_ok=True)
    case = G.build_pygeo_case("lhs100_seed42", 0, out / "pygeo")
    t = time.time()
    surf = G.build_surface(case, level="laptop_smoke", te_variant="te_1p0mm", policy=pol)
    print("surface: tris=%d si=%d facet=%.3e (%.0fs)" % (
        surf.metadata["topology"]["triangle_count"],
        surf.metadata["topology"]["self_intersection_count"],
        surf.metadata["fidelity"]["max_facet_centroid_distance_over_local_chord"],
        time.time() - t), flush=True)
    spec = P.resolved_mesh_spec(surf, level="laptop_smoke", candidate_index=0, policy=pol)
    print("estimated cells: %d" % P.estimate_cells(surf, spec, pol), flush=True)
    att = out / "attempt"
    if att.exists():
        import shutil; shutil.rmtree(att)
    t = time.time()
    rep = P.generate_mesh(surf, output_dir=att, level="laptop_smoke",
                          candidate_index=0, policy=pol)
    print("gmsh: %s %s (%.0fs)" % (rep["status"], rep["gmsh_element_counts"],
                                   time.time() - t), flush=True)
    audit = A.audit_mesh(msh_path=Path(rep["mesh_msh"]),
                         su2_path=Path(rep["mesh_su2"]["path"]), surface=surf,
                         level="laptop_smoke", candidate_index=0,
                         output_path=att / "mesh_audit.json", policy=pol)
    print(json.dumps({"counts": audit["counts"],
                      "accepted": audit["acceptance"]["accepted"],
                      "failures": audit["acceptance"]["failures"]}, indent=2))
    for g in audit["acceptance"]["gates"]:
        if not g["passed"]:
            print("  FAIL %-34s %-14s vs %s" % (g["name"], g["actual"], g["limit"]))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
