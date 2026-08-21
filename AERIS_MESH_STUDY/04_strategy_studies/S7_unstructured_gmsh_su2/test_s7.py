"""Laptop-safe unit and smoke coverage for the governed S7 pipeline.

The tests intentionally use an in-memory tetrahedral surface.  They do not
construct a pyGeo case, invoke SU2, or touch development/holdout campaign data.
"""

from __future__ import annotations

import copy
import importlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

S7_DIR = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "s7_test_package", S7_DIR / "__init__.py", submodule_search_locations=[str(S7_DIR)]
)
assert _spec and _spec.loader
_package = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _package
_spec.loader.exec_module(_package)
common = importlib.import_module("s7_test_package.common")
geometry = importlib.import_module("s7_test_package.geometry")
pipeline = importlib.import_module("s7_test_package.gmsh_pipeline")
audit = importlib.import_module("s7_test_package.mesh_audit")
intersections = importlib.import_module("s7_test_package.intersections")


class _FakePatch:
    """Small callable surface with exact nodes but curved triangle interiors."""

    def __init__(self, sign: float):
        self.sign = float(sign)

    def __call__(self, u, v):
        u_array = np.asarray(u, dtype=float)
        v_array = np.asarray(v, dtype=float)
        return np.column_stack(
            (
                1.0 - u_array,
                v_array,
                self.sign * 0.08 * np.sin(np.pi * u_array) * (1.0 - 0.2 * v_array),
            )
        )


def _tetra_surface() -> geometry.SurfaceMesh:
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=float
    )
    # Deliberately mixed orientation; orient_closed_surface must normalize it.
    triangles = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]], dtype=np.int64)
    return geometry.SurfaceMesh(
        points,
        triangles,
        ("wall_upper", "wall_lower", "wall_te", "wall_tip"),
        np.zeros(4),
        {
            "reference_values": {"mean_aerodynamic_chord_m": 1.0},
            # Any surface entering the pipeline must declare the trailing-edge
            # opening that bounds how far prisms may be extruded.  This synthetic
            # body is unit sized, so a generous opening keeps the fixture's
            # 3-layer stack inside the budget.
            "fidelity": {"min_realized_te_opening_m": 1.0},
        },
    )


def test_policy_and_holdout_tripwire():
    policy = common.load_policy()
    assert policy["schema_version"] == "aeris.s7.policy.v1"
    common.require_development_set(policy["data"]["development_set"])
    with pytest.raises(PermissionError):
        common.require_development_set(policy["data"]["locked_holdout_set"])
    with pytest.raises(ValueError):
        common.require_development_set("not-a-policy-set")


def test_orientation_and_topology_report_for_closed_tetrahedron():
    surface = _tetra_surface()
    oriented, details = geometry.orient_closed_surface(surface.points, surface.triangles)
    assert details["boundary_edge_count"] == 0
    assert details["nonmanifold_edge_count"] == 0
    assert details["connected_components"] == 1
    report = geometry.surface_topology_report(surface.points, oriented, surface.labels)
    assert report["boundary_edge_count"] == 0
    assert report["nonmanifold_edge_count"] == 0
    assert report["zero_area_face_count"] == 0
    assert report["duplicate_face_count"] == 0
    assert report["label_counts"] == {"wall_upper": 1, "wall_lower": 1, "wall_te": 1, "wall_tip": 1}


def test_self_intersections_ignore_adjacent_closed_tetra_faces():
    surface = _tetra_surface()
    report = intersections.self_intersection_report(
        surface.points, surface.triangles, tolerance=1.0e-12
    )
    assert report["self_intersection_count"] == 0


def test_self_intersection_report_counts_crossing_3d_triangles():
    points = np.array(
        [
            (-1.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, -0.5, -1.0),
            (0.0, 0.5, 1.0),
            (0.0, 0.5, -1.0),
        ]
    )
    report = intersections.self_intersection_report(
        points, np.array([[0, 1, 2], [3, 4, 5]]), tolerance=1.0e-12
    )
    assert report["self_intersection_count"] == 1
    assert report["sample_pairs"] == [[0, 1]]


def test_self_intersection_report_counts_coplanar_overlapping_triangles():
    points = np.array(
        [
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 2.0, 0.0),
            (1.0, 0.0, 0.0),
            (3.0, 0.0, 0.0),
            (1.0, 2.0, 0.0),
        ]
    )
    report = intersections.self_intersection_report(
        points, np.array([[0, 1, 2], [3, 4, 5]]), tolerance=1.0e-12
    )
    assert report["self_intersection_count"] == 1


def test_prism_layers_are_derived_from_the_trailing_edge_budget():
    """The TE-budget safeguard, which is disabled by default.

    No trailing-edge collision is currently established -- the PLC failures once
    attributed to one were a degenerate tip cap -- so the derivation is inert in
    POLICY.  This test enables it explicitly to keep the mechanism verified in
    case a future measurement justifies switching it on.  The first cell height
    sets y+ and the growth ratio sets stretching; both are preserved exactly.
    Only the layer COUNT is reduced, and only to the declared floor, below which
    the build fails closed.
    """
    surface = _tetra_surface()
    policy = copy.deepcopy(common.load_policy())
    policy["laptop_smoke"] = {
        "evidence_tier": "laptop_smoke",
        "surface_edge_over_L": 0.5,
        "te_surface_edge_over_L": 0.5,
        "tip_surface_edge_over_L": 0.5,
        "first_cell_height_over_L": 0.01,
        "prism_layers": 20,
        "prism_growth_ratio": 1.3,
        "near_core_edge_over_L": 0.5,
        "far_core_edge_over_L": 1.0,
        "wake_edge_over_L": 0.5,
        "farfield": policy["farfield"],
    }
    policy["gmsh"]["boundary_layer"]["derive_prism_layers_from_te_opening"] = True
    policy["gmsh"]["boundary_layer"]["min_prism_layers"] = 2
    # A 0.10 m opening cannot carry all 20 layers of a 0.01 m / 1.3 stack.
    surface.metadata["fidelity"] = {"min_realized_te_opening_m": 0.10}
    spec = pipeline.resolved_mesh_spec(
        surface, level="laptop_smoke", candidate_index=0, policy=policy
    )
    bl = spec["boundary_layer"]
    assert bl["requested_prism_layers"] == 20
    assert bl["applied_prism_layers"] < 20
    assert spec["relative"]["prism_layers"] == bl["applied_prism_layers"]
    assert spec["boundary_layer_total_thickness_m"] <= 0.10
    # first height and growth ratio are untouched
    assert spec["absolute"]["first_cell_height_m"] == pytest.approx(0.01)
    assert spec["relative"]["prism_growth_ratio"] == pytest.approx(1.3)

    # A generous opening keeps every requested layer.
    surface.metadata["fidelity"] = {"min_realized_te_opening_m": 1.0e3}
    roomy = pipeline.resolved_mesh_spec(
        surface, level="laptop_smoke", candidate_index=0, policy=policy
    )
    assert roomy["boundary_layer"]["applied_prism_layers"] == 20

    # Too tight even at the floor must fail closed, never silently continue.
    surface.metadata["fidelity"] = {"min_realized_te_opening_m": 1.0e-6}
    with pytest.raises(ValueError, match="trailing-edge budget"):
        pipeline.resolved_mesh_spec(
            surface, level="laptop_smoke", candidate_index=0, policy=policy
        )

    # A surface that declares no opening at all must also fail closed.
    surface.metadata["fidelity"] = {}
    with pytest.raises(ValueError, match="minimum realized trailing-edge"):
        pipeline.resolved_mesh_spec(
            surface, level="laptop_smoke", candidate_index=0, policy=policy
        )


def test_one_sided_vertex_contact_is_not_an_interpenetration():
    """A tip cap and the wall it closes touch along the shared tip curve.

    Interpenetration requires material strictly on both sides of the other
    triangle's plane.  A triangle resting on a plane it never crosses must not
    be reported as a fold, otherwise every closed cap is rejected.  Real
    crossings and coplanar overlaps stay covered by the two tests above.
    """
    # Triangle B lies in z = 0.  Triangle A touches it at a single vertex and is
    # otherwise strictly below, mirroring the measured wall/tip contact.
    points = np.array(
        [
            (0.10, 0.10, 0.0),
            (0.40, 0.30, -0.5),
            (0.20, 0.60, -0.5),
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
        ]
    )
    report = intersections.self_intersection_report(
        points, np.array([[0, 1, 2], [3, 4, 5]]), tolerance=1.0e-12
    )
    assert report["self_intersection_count"] == 0

    # Dropping that vertex through the plane makes it a genuine fold again.
    crossing = points.copy()
    crossing[0, 2] = 0.25
    report = intersections.self_intersection_report(
        crossing, np.array([[0, 1, 2], [3, 4, 5]]), tolerance=1.0e-12
    )
    assert report["self_intersection_count"] == 1


def test_common_serialization_and_layer_schedule(tmp_path):
    assert common.canonical_json({"b": 1, "a": np.array([2, 3])}) == '{"a":[2,3],"b":1}'
    output = common.write_json(tmp_path / "record.json", {"value": np.float64(2.5)})
    assert common.read_json(output) == {"value": 2.5}
    source_paths = set(common.source_paths())
    assert (common.REPO_ROOT / "pyproject.toml").resolve() in source_paths
    assert (
        common.REPO_ROOT / "src/aeris/dataset/sampling/samplers/lhs_v1.py"
    ).resolve() in source_paths
    assert pipeline.cumulative_layer_heights(1.0, 3, 1.5) == [1.0, 2.5, 4.75]
    for args in ((0.0, 1, 1.0), (1.0, 0, 1.0), (1.0, 1, 0.9)):
        with pytest.raises(ValueError):
            pipeline.cumulative_layer_heights(*args)


def test_resolved_laptop_spec_and_cell_estimate():
    surface = _tetra_surface()
    policy = common.load_policy()
    spec = pipeline.resolved_mesh_spec(
        surface, level="laptop_smoke", candidate_index=0, policy=policy
    )
    assert spec["evidence_tier"] == "laptop_smoke"
    assert (
        len(spec["boundary_layer_cumulative_heights_m"]) == policy["laptop_smoke"]["prism_layers"]
    )
    assert spec["boundary_layer_total_thickness_m"] > spec["absolute"]["first_cell_height_m"]
    assert pipeline.estimate_cells(surface, spec, policy) > len(surface.triangles)


def test_pygeo_surface_fidelity_checks_nodes_and_every_oml_facet(monkeypatch):
    policy = copy.deepcopy(common.load_policy())
    # The relaxed test-only bound lets this intentionally coarse analytic
    # surface return while still proving that curved-facet error is measured.
    policy["mesh_gates"]["source_geometry"]["max_distance_over_local_chord"] = 0.02
    pygeo_build = SimpleNamespace(
        geometry=SimpleNamespace(surfs=[_FakePatch(1.0), _FakePatch(-1.0)])
    )
    inner = SimpleNamespace(
        reference_values={"mean_aerodynamic_chord_m": 1.0, "span_m": 2.0},
        pygeo=pygeo_build,
        extracted=[SimpleNamespace(chord_m=1.0)],
        geometry_id="synthetic_curved_patch",
    )
    case = SimpleNamespace(pygeo_result=inner)
    monkeypatch.setattr(
        geometry,
        "span_parameters_for_fractions",
        lambda _build, fractions: np.asarray(fractions, dtype=float),
    )

    surface = geometry.build_surface(
        case,
        level="laptop_smoke",
        te_variant="te_1p0mm",
        policy=policy,
    )
    fidelity = surface.metadata["fidelity"]
    oml_facets = surface.labels.count("wall_upper") + surface.labels.count("wall_lower")
    # Node fidelity is exact (correctness); facet chord error is non-zero
    # (resolution).  The two must be graded against separate limits, otherwise
    # no preregistered grid level can pass.  See the ADR-0017 facet amendment.
    assert fidelity["max_node_distance_over_local_chord"] == pytest.approx(0.0)
    assert fidelity["max_facet_centroid_distance_over_local_chord"] > 0.0
    assert fidelity["node_fidelity_passed"] is True
    assert fidelity["facet_fidelity_passed"] is True
    assert (
        fidelity["limit_facet_centroid_over_local_chord"]
        == policy["mesh_gates"]["source_geometry"][
            "max_facet_centroid_over_local_chord"
        ]["laptop_smoke"]
    )
    assert fidelity["tracked_facet_centroid_evaluations"] == oml_facets
    assert surface.metadata["accepted_pre_gmsh"] is True

    # A facet limit tighter than the achievable chord error must fail closed,
    # while exact node fidelity still passes.
    strict = copy.deepcopy(policy)
    strict["mesh_gates"]["source_geometry"][
        "max_facet_centroid_over_local_chord"
    ]["laptop_smoke"] = 1.0e-12
    with pytest.raises(ValueError, match="surface_facet_fidelity"):
        geometry.build_surface(
            case, level="laptop_smoke", te_variant="te_1p0mm", policy=strict
        )


def test_gmsh_tetra_tri_prism_tet_smoke(tmp_path):
    pytest.importorskip("gmsh")
    surface = _tetra_surface()
    policy = common.load_policy()
    # Keep the synthetic domain genuinely laptop-sized while preserving the
    # production laptop layer count and all mesher code paths.
    smoke_policy = dict(policy)
    smoke_policy["farfield"] = dict(
        policy["farfield"], upstream_over_L=1.0, downstream_over_L=1.0, radial_over_L=1.0
    )
    out = pipeline.generate_mesh(
        surface,
        output_dir=tmp_path / "attempt",
        level="laptop_smoke",
        candidate_index=0,
        policy=smoke_policy,
    )
    assert out["status"] == "completed"
    assert Path(out["mesh_msh"]).is_file()
    assert out["mesh_su2"]["volume_element_count"] > 0
    assert set(out["mesh_su2"]["marker_counts"]) == set((*geometry.LABELS, "farfield"))
    assert out["gmsh_element_counts"]
    report = audit.audit_mesh(
        msh_path=Path(out["mesh_msh"]),
        su2_path=Path(out["mesh_su2"]["path"]),
        surface=surface,
        level="laptop_smoke",
        candidate_index=0,
        output_path=tmp_path / "mesh_audit.json",
        policy=smoke_policy,
    )
    # This sharp tetrahedron is not an aerodynamic acceptance fixture, but it
    # proves that Gmsh renumbering does not corrupt the wall markers or columns.
    assert report["geometry_fidelity"]["max_wall_node_distance_m"] == 0.0
    assert report["prism_layers"]["wall_face_coverage_fraction"] == 1.0
    assert report["prism_layers"]["connected_column_fraction"] == 1.0
    assert report["prism_layers"]["first_height_relative_error"]["max"] < 1.0e-10
    projected_error = report["prism_layers"][
        "wall_normal_projected_first_height_relative_error"
    ]
    assert projected_error["count"] > 0
    assert projected_error["finite_count"] == projected_error["count"]
    audit_gates = {gate["name"]: gate for gate in report["acceptance"]["gates"]}
    assert audit_gates["wall_normal_first_cell_height"]["actual"] == projected_error["max"]
    assert report["prism_layers"]["growth_ratio_relative_error"]["max"] < 1.0e-3
    assert report["volume"]["negative_cell_count"] == 0
    assert report["su2_boundary"]["boundary_face_unassigned_count"] == 0
    assert report["su2_boundary"]["boundary_face_multiply_assigned_count"] == 0
    assert report["su2_boundary"]["boundary_marker_nonboundary_face_count"] == 0
    assert report["su2_boundary"]["volume_element_count"] == report["counts"]["volume_cells"]
