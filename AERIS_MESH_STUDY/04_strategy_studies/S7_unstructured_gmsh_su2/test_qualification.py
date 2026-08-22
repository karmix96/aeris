"""Synthetic, laptop-safe tests for S7's read-only qualification collector."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

S7 = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "s7_qual_package", S7 / "__init__.py", submodule_search_locations=[str(S7)]
)
assert spec and spec.loader
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
common = importlib.import_module("s7_qual_package.common")
qualification = importlib.import_module("s7_qual_package.qualification")


def _result(index, level, cells, forces=None):
    policy = common.load_policy()
    fields = policy["grid_family"]["grid_convergence"]["force_fields"]
    prisms = max(1, cells // 3)
    tetrahedra = cells - prisms
    return {
        "schema": common.SUMMARY_SCHEMA,
        "case_id": f"dev_{index:03d}__{level}__te_1p0mm__cruise",
        "geometry_set": policy["data"]["development_set"],
        "method": "unstructured",
        "grid_level": level,
        "development_index": index,
        "geometry_id": f"design-{index:03d}",
        "geometry_digest": f"synthetic-{index}-{level}",
        "te_variant": "te_1p0mm",
        "technical_accepted": True,
        "accepted": True,
        "acceptance_scope": "mesh_and_cfd",
        "flow_id": "cruise",
        "flow_condition": dict(policy["flow_conditions"]["baseline"]),
        "reference_quantities": {
            "area_ref": 10.0,
            "chord_ref": 2.0,
            "moment_origin": [0.0, 0.0, 0.0],
        },
        "y_plus": {"passed": True},
        "cell_counts": {
            "surface_triangles": max(1, cells // 20),
            "prisms": prisms,
            "tetrahedra": tetrahedra,
            "volume_cells": cells,
        },
        "forces": forces or {field: 1.0 + 10.0 / cells for field in fields},
        "provenance": {
            "policy_sha256": common.sha256_file(common.POLICY_PATH),
            "source_digest": common.source_digest(),
            "tool_versions": {"test": True},
            "pinned_versions": {"passed": True},
        },
    }


def _write_result(root: Path, name: str, result: dict) -> Path:
    case_root = root / name
    path = common.write_json(case_root / "case_result.json", result)
    manifest = common.digest_manifest({"case_result": path}, required={"case_result"})
    common.write_json(
        case_root / "case_terminal.json",
        {
            "schema": "aeris.s7.case_terminal.v1",
            "case_id": result["case_id"],
            "source_digest": common.source_digest(),
            "policy_sha256": common.sha256_file(common.POLICY_PATH),
            "accepted": result["accepted"],
            "acceptance_scope": result["acceptance_scope"],
            "artifact_manifest": manifest,
        },
    )
    return path


def test_plan_is_fixed_and_policy_driven():
    plan = qualification.build_qualification_plan()
    assert plan["representative_indices"] == [0, 24, 49, 74, 99]
    assert len(plan["grid_study"]["cases"]) == 5
    assert plan["trailing_edge_study"]["variants"] == ["te_0p5mm", "te_1p0mm", "te_1p5mm"]
    assert (
        plan["force_fields"]
        == common.load_policy()["grid_family"]["grid_convergence"]["force_fields"]
    )


def test_collect_uses_actual_counts_and_reports_gci(tmp_path):
    paths = []
    for level, cells in zip(("coarse", "medium", "fine"), (1000, 2000, 5000), strict=True):
        paths.append(_write_result(tmp_path, level, _result(0, level, cells)))
    summary = qualification.collect_qualification(paths)
    entry = summary["grid_convergence"]["0"]
    assert entry["status"] in {"passed", "failed_grid_convergence"}
    assert entry["actual_volume_cells"] == [1000, 2000, 5000]
    assert entry["effective_h"][0] > entry["effective_h"][1] > entry["effective_h"][2]


def test_manufactured_unequal_grid_order_and_fine_gci_limit(tmp_path):
    policy = common.load_policy()
    fields = policy["grid_family"]["grid_convergence"]["force_fields"]
    paths = []
    counts = (1000, 2300, 6000)
    for level, cells in zip(("coarse", "medium", "fine"), counts, strict=True):
        h = cells ** (-1.0 / 3.0)
        forces = {field: 1.0 + 20.0 * h**2 for field in fields}
        paths.append(_write_result(tmp_path, f"limit-{level}", _result(0, level, cells, forces)))
    entry = qualification.collect_qualification(paths)["grid_convergence"]["0"]
    assert entry["status"] == "failed_grid_convergence"
    for field in fields:
        assert entry["forces"][field]["observed_order"] == pytest.approx(2.0)
        assert entry["forces"][field]["status"] == "failed_fine_gci_limit"
        assert (
            entry["forces"][field]["gci_fine_percent"]
            > policy["grid_family"]["grid_convergence"]["max_fine_gci_percent"][field]
        )


def test_te_sensitivity_reports_deltas_and_missing_evidence(tmp_path):
    policy = common.load_policy()
    fields = policy["grid_family"]["grid_convergence"]["force_fields"]
    paths = []
    for variant, value in (
        ("te_0p5mm", 0.9),
        ("te_1p0mm", 1.0),
        ("te_1p5mm", 1.2),
    ):
        row = _result(0, "medium", 2000, {field: value for field in fields})
        row["te_variant"] = variant
        row["case_id"] = f"dev_000__medium__{variant}__cruise"
        paths.append(_write_result(tmp_path, variant, row))
    sensitivity = qualification.collect_qualification(paths)["trailing_edge_sensitivity"]["0"]
    assert sensitivity["status"] == "complete"
    assert sensitivity["fields"][fields[0]]["deltas"]["te_1p5mm"][
        "absolute_delta"
    ] == pytest.approx(0.2)
    assert (
        qualification.collect_qualification([])["trailing_edge_sensitivity"]["0"]["status"]
        == "unavailable_missing_case_result"
    )


def test_collect_rejects_bad_provenance_and_never_fakes_gci(tmp_path):
    paths = []
    for level, cells in zip(("coarse", "medium", "fine"), (2000, 1500, 5000), strict=True):
        paths.append(_write_result(tmp_path, level, _result(0, level, cells)))
    bad = _result(1, "coarse", 1000)
    bad["provenance"]["policy_sha256"] = "wrong"
    paths.append(_write_result(tmp_path, "bad", bad))
    summary = qualification.collect_qualification(paths)
    assert summary["grid_convergence"]["0"]["status"] == "invalid_nonmonotonic_coupled_cell_counts"
    assert "policy_provenance_mismatch" in summary["rejected_records"][-1]["errors"]


def test_collect_rejects_out_of_plan_and_mixed_grid_geometry(tmp_path):
    paths = []
    for level, cells in zip(("coarse", "medium", "fine"), (1000, 2300, 6000), strict=True):
        row = _result(0, level, cells)
        if level == "fine":
            row["geometry_id"] = "different-design"
        paths.append(_write_result(tmp_path, f"mixed-{level}", row))
    outside = _result(1, "medium", 2300)
    paths.append(_write_result(tmp_path, "outside", outside))
    summary = qualification.collect_qualification(paths)
    assert summary["grid_convergence"]["0"]["status"] == "invalid_mixed_geometry_or_flow"
    assert any("out_of_plan_case_result" in row["errors"] for row in summary["rejected_records"])


def test_comparison_marks_absent_evidence_explicitly():
    report = qualification.compare_summaries({}, {})
    assert report["S6"]["runtime"]["status"] == "missing_evidence"
    assert report["metrics"]["runtime"]["status"] == "incompatible_evidence"
    assert report["missing_evidence_is_not_zero_or_a_pass"] is True


def test_comparison_refuses_mismatched_normalization_basis():
    basis = {
        "geometry_set": "lhs100_seed42",
        "case_ids": ["dev_000"],
        "flow_condition": {"mach": 0.2},
        "full_wing_normalization": True,
        "force_reference": {"area": 10.0, "chord": 2.0, "origin": [0, 0, 0]},
    }
    left = {"comparison_basis": basis, "forces": {"cl": 0.2}}
    right_basis = dict(basis, full_wing_normalization=False)
    right = {"comparison_basis": right_basis, "forces": {"cl": 0.2}}
    report = qualification.compare_summaries(left, right)
    assert report["comparability"]["status"] == "incompatible_evidence"
    assert report["metrics"]["forces"]["status"] == "incompatible_evidence"
