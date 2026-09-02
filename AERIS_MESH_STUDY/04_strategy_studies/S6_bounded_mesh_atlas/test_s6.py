"""Focused unit tests for the S6 bounded mesh atlas."""

from __future__ import annotations

import csv
import json
import socket
import sys
import time
from pathlib import Path

import atlas
import audit_validation
import campaign
import cfd_qc
import deform
import h5py
import numpy as np
import pytest
import qualification
import resolution
import strategy_s6
import wall_normal
import yaml
from shared import volume_qc

from aeris.cfd.meshing.pyhyp_options import GRID_LEVELS


def test_qualification_plan_refines_all_directions_and_protects_holdout() -> None:
    plan = qualification.build_qualification_plan()
    assert plan["holdout_accessed"] is False
    assert plan["laptop_smoke"]["production_claim_allowed"] is False
    assert plan["laptop_smoke"]["template_routes"] == {"42": 42, "95": 95, "7": 95}
    assert (
        plan["laptop_smoke"]["production_wall_law_conclusion"]
        == "NOT_TESTED_AT_PRODUCTION_RESOLUTION"
    )
    assert plan["current_candidate_wall_test"]["surface_level"] == "smoke"
    assert plan["current_candidate_wall_test"]["normal_points"] == 257
    p0_span = plan["current_candidate_wall_test"]["span_cells"]
    assert p0_span["mode"] == "geometry_dependent_from_selected_registry_template"
    if plan["current_candidate_wall_test"]["registry_available"]:
        assert p0_span["minimum"] == 60
        assert p0_span["maximum"] == 98
        assert p0_span["by_template_geometry"]["42"] == 75
        assert p0_span["by_template_geometry"]["95"] == 85
    else:
        assert p0_span == {
            "mode": "geometry_dependent_from_selected_registry_template",
            "minimum": None,
            "maximum": None,
            "by_template_geometry": {},
        }
    assert plan["preregistration_evidence"] is False
    assert set(plan["implementation_provenance"]) == {
        "qualification_sha256",
        "strategy_s6_sha256",
        "campaign_mesh_implementation_sha256",
        "campaign_solver_implementation_sha256",
    }
    p0 = plan["current_candidate_wall_test"]
    assert "smoke tangential" in " ".join(p0["limitations"])
    assert p0["production_resolution_scope"].startswith("wall_normal_candidate")

    levels = plan["grid_study"]["levels"]
    for left, right in zip(levels[:-1], levels[1:], strict=True):
        for field in (
            "chord_points",
            "end_points",
            "collar_points",
            "span_cells",
            "normal_points",
        ):
            assert right[field] > left[field]
        assert (
            right["first_cell_fraction_characteristic"] < left["first_cell_fraction_characteristic"]
        )

    variants = plan["trailing_edge_study"]["variants"]
    assert [variant["name"] for variant in variants] == [
        "TE_small",
        "TE_baseline",
        "TE_large",
    ]
    te_metric = plan["trailing_edge_study"]["material_change_metric"]
    assert te_metric["reference_variant"] == "TE_baseline"
    assert "variant-baseline" in te_metric["formula"]
    assert te_metric is not plan["grid_study"]["medium_to_fine_gate"]
    assert [variant["te_abs_m"] for variant in variants] == sorted(
        variant["te_abs_m"] for variant in variants
    )


def test_local_solver_path_classification_excludes_yplus_by_design() -> None:
    assert qualification._local_solver_path_passed(
        returncode=0,
        solver_status="converged",
        residual_orders=6.1,
        force_plausibility={"passed": True},
        force_tail={"passed": True},
    )
    assert not qualification._local_solver_path_passed(
        returncode=0,
        solver_status="converged",
        residual_orders=5.9,
        force_plausibility={"passed": True},
        force_tail={"passed": True},
    )


def test_qualification_caches_require_matching_provenance(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text("registry", encoding="utf-8")
    output_cgns = tmp_path / "template.cgns"
    source_cgns = tmp_path / "source.cgns"
    surface_npz = tmp_path / "surface.npz"
    pyhyp_options = tmp_path / "pyhyp_options.json"
    surface_fmt = tmp_path / "surface.fmt"
    for path, content in (
        (output_cgns, b"output"),
        (source_cgns, b"source"),
        (surface_npz, b"surface"),
        (pyhyp_options, b"options"),
        (surface_fmt, b"fmt"),
    ):
        path.write_bytes(content)

    template_report_path = tmp_path / "template_report.json"
    template_report = {
        "schema": qualification.LAPTOP_TEMPLATE_SCHEMA,
        "state": "PASS",
        "source_registry_sha256": deform.sha256(registry),
        "mesh_implementation_sha256": "implementation-a",
        "cgns": str(output_cgns),
        "cgns_sha256": deform.sha256(output_cgns),
        "source_cgns": str(source_cgns),
        "source_cgns_sha256": deform.sha256(source_cgns),
        "surface_npz": str(surface_npz),
        "surface_npz_sha256": deform.sha256(surface_npz),
        "source_pyhyp_options": str(pyhyp_options),
        "source_pyhyp_options_sha256": deform.sha256(pyhyp_options),
        "source_surface_fmt": str(surface_fmt),
        "source_surface_fmt_sha256": deform.sha256(surface_fmt),
    }
    template_report_path.write_text(json.dumps(template_report), encoding="utf-8")
    assert qualification._accepted_existing_template(
        template_report_path,
        expected_registry_sha256=deform.sha256(registry),
        expected_implementation_sha256="implementation-a",
    )
    assert not qualification._accepted_existing_template(
        template_report_path,
        expected_registry_sha256="changed-registry",
        expected_implementation_sha256="implementation-a",
    )
    assert not qualification._accepted_existing_template(
        template_report_path,
        expected_registry_sha256=deform.sha256(registry),
        expected_implementation_sha256="implementation-b",
    )
    surface_fmt.write_bytes(b"changed")
    assert not qualification._accepted_existing_template(
        template_report_path,
        expected_registry_sha256=deform.sha256(registry),
        expected_implementation_sha256="implementation-a",
    )

    mesh = tmp_path / "mesh.cgns"
    mesh.write_bytes(b"mesh")
    mesh_report_path = tmp_path / "mesh_report.json"
    mesh_report_path.write_text(
        json.dumps(
            {
                "schema": qualification.LAPTOP_MESH_SCHEMA,
                "state": "MESH_ACCEPTED",
                "mesh_cgns": str(mesh),
                "mesh_cgns_sha256": deform.sha256(mesh),
                "template_cgns_sha256": "template-a",
                "template_surface_sha256": "surface-a",
                "mesh_implementation_sha256": "implementation-a",
            }
        ),
        encoding="utf-8",
    )
    assert qualification._accepted_existing_mesh(
        mesh_report_path,
        expected_template_sha256="template-a",
        expected_template_surface_sha256="surface-a",
        expected_implementation_sha256="implementation-a",
    )
    assert not qualification._accepted_existing_mesh(
        mesh_report_path,
        expected_template_sha256="template-b",
        expected_template_surface_sha256="surface-a",
        expected_implementation_sha256="implementation-a",
    )
    assert not qualification._accepted_existing_mesh(
        mesh_report_path,
        expected_template_sha256="template-a",
        expected_template_surface_sha256="surface-b",
        expected_implementation_sha256="implementation-a",
    )
    assert not qualification._accepted_existing_mesh(
        mesh_report_path,
        expected_template_sha256="template-a",
        expected_template_surface_sha256="surface-a",
        expected_implementation_sha256="implementation-b",
    )


def test_laptop_cfd_cache_binds_mesh_solver_and_mpi(tmp_path: Path) -> None:
    solve_report = tmp_path / "solve_report.json"
    solver_log = tmp_path / "adflow_run.log"
    surface_solution = tmp_path / "surface.cgns"
    solve_report.write_text("{}", encoding="utf-8")
    solver_log.write_text("solver output", encoding="utf-8")
    surface_solution.write_bytes(b"surface solution")
    report_path = tmp_path / "laptop_cfd_report.json"
    report_path.write_text(
        json.dumps(
            {
                "schema": qualification.LAPTOP_CFD_SCHEMA,
                "state": "LOCAL_SOLVER_PATH_PASSED",
                "mesh_cgns_sha256": "mesh-a",
                "solver_implementation_sha256": "solver-a",
                "mpi_processes": 4,
                "solve_report": str(solve_report),
                "solve_report_sha256": deform.sha256(solve_report),
                "solver_log": str(solver_log),
                "solver_log_sha256": deform.sha256(solver_log),
                "wall_yplus_gate": {
                    "surface_cgns": str(surface_solution),
                    "surface_cgns_sha256": deform.sha256(surface_solution),
                },
            }
        ),
        encoding="utf-8",
    )
    assert qualification._existing_laptop_cfd_result(
        report_path,
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=4,
    )
    assert not qualification._existing_laptop_cfd_result(
        report_path,
        mesh_sha256="mesh-b",
        implementation_sha256="solver-a",
        mpi_np=4,
    )
    assert not qualification._existing_laptop_cfd_result(
        report_path,
        mesh_sha256="mesh-a",
        implementation_sha256="solver-b",
        mpi_np=4,
    )
    assert not qualification._existing_laptop_cfd_result(
        report_path,
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=2,
    )
    surface_solution.write_bytes(b"changed surface solution")
    assert not qualification._existing_laptop_cfd_result(
        report_path,
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=4,
    )
    assert qualification._mpi_deviation_reason(None, 4) == ("actual_rank_count_missing_or_invalid")
    assert qualification._mpi_deviation_reason(2, 4) == (
        "actual_below_plan_reason_not_recorded_in_case_report"
    )
    assert qualification._mpi_deviation_reason(8, 4) == (
        "actual_above_plan_reason_not_recorded_in_case_report"
    )
    assert qualification._mpi_deviation_reason(4, 4) == "no_deviation"


def test_main_routes_legacy_laptop_audit(monkeypatch, tmp_path, capsys) -> None:
    audit_output = tmp_path / "audit.json"
    called = {}

    def fake_audit(*, indices, output, audit_output):
        called.update(
            indices=indices,
            output=output,
            audit_output=audit_output,
        )
        return {"state": "AUDITED"}

    monkeypatch.setattr(qualification, "audit_legacy_laptop", fake_audit)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qualification.py",
            "audit-legacy-laptop",
            "--output",
            str(tmp_path),
            "--audit-output",
            str(audit_output),
            "--indices",
            "42",
        ],
    )
    assert qualification.main() == 0
    assert called == {
        "indices": [42],
        "output": tmp_path,
        "audit_output": audit_output,
    }
    assert json.loads(capsys.readouterr().out) == {"state": "AUDITED"}


def test_primary_span_count_is_independent_of_block_order() -> None:
    tip = np.zeros((5, 3, 3))
    oml = np.zeros((5, 76, 3))
    assert qualification._primary_span_cells({"tip": tip, "oml": oml}) == 75
    assert qualification._primary_span_cells({"oml": oml, "tip": tip}) == 75


def test_collect_laptop_preserves_historical_summary(tmp_path, monkeypatch) -> None:
    historical = tmp_path / "laptop_summary.json"
    historical.write_bytes(b"historical evidence\n")
    monkeypatch.setattr(qualification, "DEFAULT_REGISTRY", tmp_path / "missing_registry.json")
    report_path = tmp_path / "lhs100_seed42_042" / "cfd" / "laptop_cfd_report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            {
                "schema": qualification.LAPTOP_CFD_SCHEMA,
                "state": "LOCAL_SOLVER_PATH_PASSED",
                "geometry_index": 42,
                "holdout_accessed": False,
                "mpi_processes": 2,
                "solver_implementation_sha256": "stale",
                "flow": qualification.FLOW,
            }
        ),
        encoding="utf-8",
    )

    summary = qualification.collect_laptop(indices=[42], output=tmp_path)

    assert historical.read_bytes() == b"historical evidence\n"
    assert Path(summary["summary_path"]).name == "laptop_summary_current.json"
    assert Path(summary["summary_path"]).is_file()
    assert summary["completed"] == 0
    assert summary["stale_or_invalid"] == 1
    assert summary["solver_path_passed"] is None
    assert summary["wall_yplus_passed"] is None
    assert summary["protocol_deviations"] == [
        {
            "geometry_index": 42,
            "row_state": "STALE_OR_INVALID_PROVENANCE",
            "field": "mpi_processes",
            "planned": 4,
            "actual": 2,
            "reason": "actual_below_plan_reason_not_recorded_in_case_report",
        }
    ]


def test_development_report_auditor_checks_written_selection(tmp_path) -> None:
    missing_mesh = tmp_path / "pruned.cgns"
    selected = {
        "template_index": 42,
        "state": "PASS",
        "selected": True,
        "min_scaled_quality": 0.18,
        "wall_error_m": 0.0,
        "interface_max_mismatch_m": 0.0,
        "surface_fidelity": {
            "passed": True,
            "max_fraction_of_local_chord": 1.0e-5,
        },
        "first_layer_spacing": {
            "deformed": {
                "nonfinite_count": 0,
                "nonpositive_count": 0,
                "min_fraction_characteristic": 3.5e-6,
                "p95_fraction_characteristic": 3.7e-6,
            }
        },
        "independent_written_acceptance": {
            "hard_gate_passed": True,
            "production_floor_passed": True,
            "quality": {
                "min_scaled_quality": 0.18,
                "min_volume": 1.0e-9,
                "inverted_cells": 0,
                "total_cells": 100,
                "cells_below_0_10": 0,
                "cells_below_0_15": 0,
            },
        },
        "interface_pair_count": 1,
        "candidate_cgns_sha256": "abc",
    }
    report = {
        "schema": audit_validation.REPORT_SCHEMA,
        "campaign_equivalent_written_cgns_audit": True,
        "geometry_indices": [0],
        "template_indices": [42],
        "candidate_count": 1,
        "preferred_quality": 0.15,
        "attempted": 1,
        "passed": 1,
        "pass_fraction": 1.0,
        "worst_min_scaled_quality": 0.18,
        "rows": [
            {
                "geometry_index": 0,
                "state": "PASS",
                "attempts": [selected],
                "accepted_template_index": 42,
                "accepted_min_scaled_quality": 0.18,
                "accepted_cgns": str(missing_mesh),
                "accepted_cgns_sha256": "abc",
                "accepted_cgns_retained": False,
                "is_atlas_template_target": False,
                "selected_identity_deformation": False,
            }
        ],
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    audit = audit_validation.audit_report(path, expected_count=1)
    assert audit["passed"]
    assert audit["report_integrity_passed"]
    assert audit["all_targets_passed"]
    assert audit["summary"]["first_try_passes"] == 1
    assert audit["summary"]["quality"]["minimum"] == pytest.approx(0.18)

    report["rows"][0]["accepted_min_scaled_quality"] = 0.17
    path.write_text(json.dumps(report), encoding="utf-8")
    audit = audit_validation.audit_report(path, expected_count=1)
    assert not audit["passed"]
    assert any("row quality differs" in error for error in audit["errors"])

    report["rows"][0]["accepted_min_scaled_quality"] = 0.18
    report["rows"][0]["state"] = "NEEDS_FALLBACK"
    report["rows"][0]["attempts"][0]["selected"] = False
    report["rows"][0]["accepted_template_index"] = None
    report["passed"] = 0
    report["pass_fraction"] = 0.0
    report["worst_min_scaled_quality"] = None
    path.write_text(json.dumps(report), encoding="utf-8")
    audit = audit_validation.audit_report(path, expected_count=1)
    assert audit["report_integrity_passed"]
    assert not audit["all_targets_passed"]
    assert not audit["passed"]


def test_production_wall_policy_matches_tested_calibration_and_is_numeric() -> None:
    policy = yaml.safe_load((Path(__file__).with_name("POLICY.yaml")).read_text())
    wall = policy["wall_spacing"]
    assert resolution.first_cell_fraction("production") == pytest.approx(3.6e-6)
    assert wall["production_development_fraction"] == pytest.approx(3.6e-6)
    assert wall["production_development_epsE"] == pytest.approx(1.5)
    assert isinstance(wall["reference_reynolds"], (int, float))
    assert wall["reference_reynolds"] == pytest.approx(resolution.REFERENCE_REYNOLDS)


def test_candidate_wall_spacing_registry_matches_pyhyp_defaults() -> None:
    """Prevent silent fallback to a retired C01/C02/C03 spacing value."""
    for level in ("candidate_c01", "candidate_c02", "candidate_c03"):
        assert GRID_LEVELS[level]["s0_frac"] == pytest.approx(resolution.first_cell_fraction(level))


def _cube() -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    i = np.linspace(0.0, 1.0, 5)
    j = np.linspace(0.0, 1.0, 4)
    k = np.linspace(0.0, 3.0, 8)
    kk, jj, ii = np.meshgrid(k, j, i, indexing="ij")
    volume = {"zone": np.stack((ii, jj, kk), axis=-1)}
    surface = {"wall": volume["zone"][0].transpose(1, 0, 2)}
    return volume, surface


def test_volume_report_records_worst_cell_diagnostic() -> None:
    volume, _surface = _cube()
    report = volume_qc.volume_report(volume)
    worst = report["worst_cell"]
    assert worst["block"] == "zone"
    assert worst["cell_index_kji"] == [0, 0, 0]
    assert worst["wall_layer_index"] == 0
    assert worst["wall_distance_m"] == pytest.approx(0.0)
    assert worst["min_scaled_quality"] == pytest.approx(1.0)
    assert report["cells_below_0_10"] == 0
    assert report["cells_below_0_15"] == 0


def test_eps_e_paths_follow_the_governed_ladder(tmp_path) -> None:
    assert resolution.epsilon_tag(1.5) == "eps15"
    cgns, surface = campaign._template_paths(7, tmp_path, 1.5)
    assert cgns == tmp_path / "lhs100_seed42_007/eps15/wing_vol.cgns"
    assert surface == tmp_path / "lhs100_seed42_007/eps15/surface_blocks.npz"
    with pytest.raises(ValueError, match="frozen ladder"):
        resolution.epsilon_tag(1.7)


def test_deformation_reports_realized_first_layer_spacing() -> None:
    volume, surface = _cube()
    deformed, metadata = deform.deform_volume_blocks(volume, surface, surface)
    expected = 3.0 / 7.0
    spacing = metadata["first_layer_spacing"]["deformed"]
    assert spacing["nonfinite_count"] == 0
    assert spacing["nonpositive_count"] == 0
    assert spacing["min_m"] == pytest.approx(expected)
    assert spacing["max_m"] == pytest.approx(expected)

    written = deform.written_deformation_metadata(deformed, surface, metadata)
    assert written["max_wall_error_m"] == pytest.approx(0.0)
    assert written["first_layer_spacing"]["deformed"]["median_m"] == pytest.approx(expected)


def test_wall_normal_reference_law_uses_selected_healthy_columns() -> None:
    i = np.linspace(0.0, 1.0, 3)
    j = np.linspace(0.0, 1.0, 2)
    k = np.array([0.0, 1.0, 3.0, 10.0])
    kk, jj, ii = np.meshgrid(k, j, i, indexing="ij")
    reference = np.stack((ii, jj, kk), axis=-1)
    distorted = reference.copy()
    distorted[1, ..., 2] = 8.0
    distorted[2, ..., 2] = 9.0

    fraction, metadata = wall_normal.reference_layer_fraction(
        {"healthy": reference, "excluded": distorted}, ["healthy"]
    )

    np.testing.assert_allclose(fraction, [0.0, 0.1, 0.3, 1.0])
    assert metadata["reference_zones"] == ["healthy"]
    assert metadata["reference_column_count"] == 6
    assert metadata["median_layer_spacing_m"] == pytest.approx([1.0, 2.0, 7.0])


def test_wall_normal_redistribution_preserves_endpoints_and_interfaces() -> None:
    i = np.linspace(0.0, 1.0, 5)
    old_k = np.array([0.0, 8.0, 9.0, 10.0])

    def block(y0: float, y1: float) -> np.ndarray:
        j = np.linspace(y0, y1, 3)
        kk, jj, ii = np.meshgrid(old_k, j, i, indexing="ij")
        return np.stack((ii, jj, kk), axis=-1)

    source = {"left": block(0.0, 0.5), "right": block(0.5, 1.0)}
    fraction = np.array([0.0, 0.1, 0.3, 1.0])
    redistributed = wall_normal.redistribute_volume_columns(source, fraction)

    for zone in source:
        np.testing.assert_array_equal(redistributed[zone][0], source[zone][0])
        np.testing.assert_array_equal(redistributed[zone][-1], source[zone][-1])
        np.testing.assert_allclose(redistributed[zone][:, 0, 0, 2], [0.0, 1.0, 3.0, 10.0])
    interfaces = deform.volume_interface_report(redistributed)
    assert interfaces["paired_face_count"] == 1
    assert interfaces["max_mismatch_m"] == pytest.approx(0.0)
    assert wall_normal.coordinate_payload_sha256(redistributed) == (
        wall_normal.coordinate_payload_sha256(
            {name: values.copy() for name, values in redistributed.items()}
        )
    )
    changed = {name: values.copy() for name, values in redistributed.items()}
    changed["left"][1, 0, 0, 2] += 1.0e-12
    assert wall_normal.coordinate_payload_sha256(changed) != (
        wall_normal.coordinate_payload_sha256(redistributed)
    )


def test_wall_normal_yplus_projection_uses_local_height_ratio(tmp_path: Path, monkeypatch) -> None:
    volume, _surface = _cube()
    candidate = {"zone": volume["zone"].copy()}
    candidate["zone"][1, ..., 2] *= 0.5
    surface_solution = tmp_path / "surface.cgns"
    surface_solution.write_bytes(b"test surface")
    measured = np.full(12, 1.5)

    monkeypatch.setattr(
        cfd_qc,
        "read_surface_field_arrays",
        lambda _path, _fields: (
            {"NSWallAdiabaticBCZone1": {"YPlus": [measured]}},
            {"reader": "synthetic"},
        ),
    )
    report = wall_normal.projected_wall_yplus(
        source_surface_cgns=surface_solution,
        source_blocks=volume,
        candidate_blocks=candidate,
    )

    assert report["status"] == "diagnostic_projection_not_cfd_acceptance"
    assert report["accepted_classification_allowed"] is False
    assert report["projected_gate_passed"]
    assert report["global"]["statistics"]["maximum"] == pytest.approx(0.75)
    region = report["regions"]["NSWallAdiabaticBCZone1"]
    assert region["volume_zone"] == "zone"
    assert region["first_cell_height_ratio"]["p50"] == pytest.approx(0.5)


def test_wall_normal_redistribution_rejects_invalid_law() -> None:
    volume, _surface = _cube()
    with pytest.raises(ValueError, match="increase strictly"):
        wall_normal.redistribute_volume_columns(volume, np.array([0.0, 0.5, 0.5, 1.0]))


def test_atlas_selection_is_deterministic_and_unique() -> None:
    rng = np.random.default_rng(4)
    points = rng.random((30, 6))
    first = atlas.farthest_point_indices(points, 8)
    second = atlas.farthest_point_indices(points, 8)
    assert first == second
    assert len(set(first)) == 8


def test_production_seed_qualification_prunes_and_never_freezes() -> None:
    manifest = atlas.build_atlas_manifest(template_count=3)
    templates = manifest["template_indices"]

    def row(index: int, quality: float, state: str = "PASS") -> dict:
        reasons = [] if state == "PASS" else ["quality_below_production_floor"]
        return {
            "geometry_index": index,
            "geometry_id": f"lhs100_seed42_{index:03d}",
            "state": state,
            "audit": {
                "state": state,
                "failure_reasons": reasons,
                "quality": {
                    "min_scaled_quality": quality,
                    "min_volume": 1.0,
                    "inverted_cells": 0,
                },
                "march_result": {"march_metrics": {"min_quality": quality + 0.2}},
            },
        }

    report = {
        "schema": "aeris.mesh.s6_seed_build.v1",
        "level": "production",
        "indices": templates,
        "attempted": 3,
        "rows": [
            row(templates[0], 0.16),
            row(templates[1], 0.03, "FAIL"),
            row(templates[2], 0.12),
        ],
    }
    qualified = atlas.qualify_atlas_seeds(manifest, report, minimum_templates=2)
    assert qualified["template_indices"] == [templates[0], templates[2]]
    evidence = qualified["seed_qualification"]
    assert [item["geometry_index"] for item in evidence["rejected"]] == [templates[1]]
    assert evidence["requires_complete_development_revalidation"]
    assert not evidence["freeze_ready"]


def test_seed_qualification_requires_complete_production_report() -> None:
    manifest = atlas.build_atlas_manifest(template_count=2)
    report = {
        "schema": "aeris.mesh.s6_seed_build.v1",
        "level": "smoke",
        "indices": manifest["template_indices"],
        "attempted": 0,
        "rows": [],
    }
    with pytest.raises(ValueError, match="production seed report"):
        atlas.qualify_atlas_seeds(manifest, report, minimum_templates=1)


def test_quality_enrichment_adds_weak_case_then_can_freeze() -> None:
    manifest = atlas.build_atlas_manifest(template_count=2)
    manifest["seed_qualification"] = {"evidence": "production-seeds"}
    manifest["prior_quality_enrichment"] = {"evidence": "smoke-history"}
    templates = manifest["template_indices"]
    weak_index = next(index for index in range(100) if index not in set(templates))

    def report_for(current: dict, weak: int | None) -> dict:
        rows = []
        for index in range(100):
            attempts = (
                [{"template_index": item} for item in current["template_indices"]]
                if index == weak
                else [{}]
            )
            rows.append(
                {
                    "geometry_index": index,
                    "state": "PASS",
                    "attempts": attempts,
                    "accepted_min_scaled_quality": (0.12 if index == weak else 0.20),
                }
            )
        return {
            "set_name": "lhs100_seed42",
            "volume_level": "production",
            "template_indices": current["template_indices"],
            "candidate_count": current["template_count"],
            "preferred_quality": 0.15,
            "rows": rows,
        }

    enriched = atlas.enrich_atlas_manifest(
        manifest,
        report_for(manifest, weak_index),
        maximum_templates=3,
    )
    assert enriched["template_indices"] == [*templates, weak_index]
    assert enriched["quality_enrichment"]["requires_revalidation"]
    assert not enriched["quality_enrichment"]["freeze_ready"]
    assert enriched["seed_qualification"] == manifest["seed_qualification"]
    assert enriched["prior_quality_enrichment"] == manifest["prior_quality_enrichment"]

    frozen = atlas.enrich_atlas_manifest(
        enriched,
        report_for(enriched, None),
        maximum_templates=3,
    )
    assert frozen["template_indices"] == enriched["template_indices"]
    assert not frozen["quality_enrichment"]["requires_revalidation"]
    assert frozen["quality_enrichment"]["freeze_ready"]

    existing_warning = atlas.enrich_atlas_manifest(
        manifest,
        report_for(manifest, templates[0]),
        maximum_templates=3,
    )
    warning = existing_warning["quality_enrichment"]
    assert warning["added_indices"] == []
    assert warning["unresolved_existing_template_cases"] == []
    assert [row["geometry_index"] for row in warning["accepted_existing_template_warnings"]] == [
        templates[0]
    ]
    assert warning["freeze_ready"]

    failed_existing_report = report_for(manifest, templates[0])
    failed_row = failed_existing_report["rows"][templates[0]]
    failed_row["state"] = "NEEDS_FALLBACK"
    failed_row["accepted_min_scaled_quality"] = None
    failed_existing = atlas.enrich_atlas_manifest(
        manifest,
        failed_existing_report,
        maximum_templates=3,
    )
    assert not failed_existing["quality_enrichment"]["freeze_ready"]
    assert len(failed_existing["quality_enrichment"]["unresolved_existing_template_cases"]) == 1

    known_unbuildable_manifest = json.loads(json.dumps(manifest))
    known_unbuildable_manifest["seed_qualification"] = {
        "rejected": [
            {
                "geometry_index": weak_index,
                "failure_reasons": ["quality_below_production_floor"],
            }
        ]
    }
    known_warning = atlas.enrich_atlas_manifest(
        known_unbuildable_manifest,
        report_for(known_unbuildable_manifest, weak_index),
        maximum_templates=3,
    )["quality_enrichment"]
    assert known_warning["added_indices"] == []
    assert known_warning["known_unbuildable_seed_indices"] == [weak_index]
    assert [
        row["geometry_index"] for row in known_warning["accepted_known_unbuildable_warnings"]
    ] == [weak_index]
    assert known_warning["freeze_ready"]

    known_failed_report = report_for(known_unbuildable_manifest, weak_index)
    known_failed_row = known_failed_report["rows"][weak_index]
    known_failed_row["state"] = "NEEDS_FALLBACK"
    known_failed_row["accepted_min_scaled_quality"] = None
    known_failed = atlas.enrich_atlas_manifest(
        known_unbuildable_manifest,
        known_failed_report,
        maximum_templates=3,
    )["quality_enrichment"]
    assert not known_failed["freeze_ready"]
    assert len(known_failed["unresolved_known_unbuildable_cases"]) == 1

    smoke_report = report_for(manifest, None)
    smoke_report["volume_level"] = "smoke"
    smoke_ready = atlas.enrich_atlas_manifest(
        manifest,
        smoke_report,
        maximum_templates=2,
    )
    assert smoke_ready["quality_enrichment"]["quality_enrichment_complete"]
    assert smoke_ready["quality_enrichment"]["requires_production_validation"]
    assert not smoke_ready["quality_enrichment"]["freeze_ready"]

    with pytest.raises(ValueError, match="permanently pinned"):
        atlas.enrich_atlas_manifest(
            manifest,
            smoke_report,
            maximum_templates=2,
            required_freeze_level="smoke",
        )


def test_registry_indices_are_read_from_current_atlas_schema(tmp_path) -> None:
    path = tmp_path / "atlas.json"
    path.write_text(
        json.dumps(
            {
                "schema": atlas.ATLAS_SCHEMA,
                "set_name": "lhs100_seed42",
                "template_indices": [42, 70, 16],
            }
        ),
        encoding="utf-8",
    )
    assert campaign.indices_from_atlas_manifest(path) == [42, 70, 16]


def test_portable_registry_assets_resolve_and_verify(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(campaign, "REPO_ROOT", tmp_path)
    assets = tmp_path / "templates" / "seed_042"
    assets.mkdir(parents=True)
    cgns = assets / "wing_vol.cgns"
    surface = assets / "surface_blocks.npz"
    options = assets / "pyhyp_options.json"
    cgns.write_bytes(b"cgns")
    surface.write_bytes(b"surface")
    options.write_text("{}\n", encoding="utf-8")

    template = {
        "template_id": "seed_042",
        "geometry_index": 42,
        "cgns": "templates/seed_042/wing_vol.cgns",
        "cgns_sha256": deform.sha256(cgns),
        "surface_npz": "templates/seed_042/surface_blocks.npz",
        "surface_npz_sha256": deform.sha256(surface),
        "pyhyp_options": "templates/seed_042/pyhyp_options.json",
        "pyhyp_options_sha256": deform.sha256(options),
    }
    registry = {
        "schema": campaign.REGISTRY_SCHEMA,
        "asset_path_base": "repository_root",
        "templates": [template],
    }
    path = tmp_path / "artifacts" / "registry.json"
    path.parent.mkdir()
    path.write_text(json.dumps(registry), encoding="utf-8")

    audit = campaign.verify_registry(path)
    assert audit["passed"]
    assert audit["template_count"] == 1
    materialized = campaign._materialize_registry_assets(
        json.loads(path.read_text(encoding="utf-8")), path
    )
    assert Path(materialized["templates"][0]["cgns"]) == cgns

    cgns.write_bytes(b"changed")
    with pytest.raises(campaign.RegistryIntegrityError, match="hash mismatch"):
        campaign.verify_registry(path)


def test_hpc_pilot_package_uses_only_governed_development_cases(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(campaign, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        campaign,
        "verify_registry",
        lambda _path: {"passed": True, "template_count": 21},
    )
    matrix, names = campaign.design_matrix("lhs100_seed42")
    report = {
        "schema": campaign.DEVELOPMENT_REPORT_SCHEMA,
        "set_name": "lhs100_seed42",
        "volume_level": "production",
        "attempted": 100,
        "passed": 100,
        "preferred_quality": 0.15,
        "rows": [],
    }
    for index in range(100):
        quality = 0.16 + 0.0005 * index
        attempts = 1
        if index == 7:
            attempts = 6
        elif index == 95:
            quality = 0.146
            attempts = 21
        report["rows"].append(
            {
                "geometry_index": index,
                "geometry_id": f"lhs100_seed42_{index:03d}",
                "state": "PASS",
                "accepted_min_scaled_quality": quality,
                "attempts": [{} for _ in range(attempts)],
                "accepted_template_index": index,
                "selected_identity_deformation": True,
            }
        )
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    atlas_manifest = {
        "schema": atlas.ATLAS_SCHEMA,
        "set_name": "lhs100_seed42",
        "quality_enrichment": {
            "freeze_ready": True,
            "requires_revalidation": False,
            "development_report": {"sha256": deform.sha256(report_path)},
        },
        "assignments": [
            {"geometry_index": index, "distance_rms": 0.001 * index} for index in range(100)
        ],
    }
    atlas_path = tmp_path / "atlas.json"
    atlas_path.write_text(json.dumps(atlas_manifest), encoding="utf-8")
    registry = {
        "schema": campaign.REGISTRY_SCHEMA,
        "asset_path_base": "repository_root",
        "atlas_manifest": {"sha256": deform.sha256(atlas_path)},
        "templates": [],
    }
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    flows_path = tmp_path / "flows.csv"
    flows_path.write_text(
        "flow_id,alpha,mach,reynolds,temperature\ncruise,2,0.2,1000000,288.15\n",
        encoding="utf-8",
    )

    package = campaign.prepare_hpc_pilot(
        development_report_path=report_path,
        atlas_manifest_path=atlas_path,
        registry_path=registry_path,
        flows_path=flows_path,
        output=tmp_path / "pilot",
    )
    indices = [row["geometry_index"] for row in package["selected"]]
    assert len(indices) == len(set(indices)) == 10
    assert {7, 89, 95}.issubset(indices)
    assert not package["holdout_accessed"]
    assert package["source_set"] == "lhs100_seed42"
    assert package["counts"] == {"designs": 10, "flows": 1, "cases": 10}
    assert (tmp_path / "pilot" / "verify_and_submit.sh").stat().st_mode & 0o100
    assert names == list(package_manifest_names(tmp_path / "pilot" / "manifest.json"))
    assert matrix.shape[0] == 100


def package_manifest_names(path: Path) -> tuple[str, ...]:
    return tuple(json.loads(path.read_text(encoding="utf-8"))["design_variables"])


def test_normalization_omits_fixed_design_variables() -> None:
    names, low, high = atlas.design_bounds()
    midpoint = 0.5 * (low + high)
    normalized = atlas.normalize_matrix(midpoint[None, :], names)
    expected = sum(
        hi > lo and name not in atlas.MESH_DISTANCE_EXCLUDED
        for name, lo, hi in zip(names, low, high, strict=True)
    )
    assert normalized.shape[1] == expected
    np.testing.assert_allclose(normalized, 0.5)


def test_mesh_distance_ignores_neutral_oml_inactive_elevon_variables() -> None:
    names, low, high = atlas.design_bounds()
    first = 0.5 * (low + high)
    second = first.copy()
    for name in atlas.MESH_DISTANCE_EXCLUDED:
        index = names.index(name)
        second[index] = high[index]
    normalized = atlas.normalize_matrix(np.stack((first, second)), names)
    np.testing.assert_allclose(normalized[0], normalized[1])


def test_normalization_rejects_nonfinite_and_changed_fixed_variables() -> None:
    names, low, high = atlas.design_bounds()
    midpoint = 0.5 * (low + high)
    nonfinite = midpoint.copy()
    nonfinite[0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        atlas.normalize_matrix(nonfinite[None, :], names)

    fixed = np.flatnonzero(high == low)
    assert fixed.size > 0
    changed = midpoint.copy()
    changed[fixed[0]] += 1.0
    with pytest.raises(ValueError, match="fixed canonical"):
        atlas.normalize_matrix(changed[None, :], names)


def test_span_law_rejects_infeasible_cap_without_nan() -> None:
    class PlaneSurface:
        def __call__(self, u, v):
            u = np.asarray(u, dtype=float)
            v = np.asarray(v, dtype=float)
            return np.column_stack((u, 1.2 * v, np.zeros_like(u)))

    pygeo = type("PyGeo", (), {"surfs": [PlaneSurface()]})()
    with pytest.raises(ValueError, match="cover at most"):
        strategy_s6._tip_clustered_parameters(
            pygeo,
            n_cells=80,
            first_cell_m=5.0e-4,
            max_cell_m=0.015,
        )

    edges, ratio, span, maximum = strategy_s6._tip_clustered_parameters(
        pygeo,
        n_cells=90,
        first_cell_m=5.0e-4,
        max_cell_m=0.015,
    )
    assert np.all(np.isfinite(edges))
    assert np.all(np.diff(edges) > 0.0)
    assert ratio > 1.0
    assert span == pytest.approx(1.2)
    assert maximum <= 0.015 + 1.0e-12


def test_deformation_matches_wall_and_keeps_farfield_residual_zero() -> None:
    volume, template = _cube()
    target = {"wall": template["wall"].copy()}
    target["wall"][..., 0] *= 1.1
    target["wall"][..., 1] *= 0.9
    target["wall"][..., 2] = 0.02 * np.sin(np.pi * target["wall"][..., 0] / 1.1)

    mapped, metadata = deform.deform_volume_blocks(volume, template, target)
    np.testing.assert_allclose(
        mapped["zone"][0],
        target["wall"].transpose(1, 0, 2),
        atol=1.0e-14,
    )
    source_farfield = volume["zone"][-1]
    expected_farfield = np.asarray(metadata["target_anchor_m"]) + (
        source_farfield - np.asarray(metadata["template_anchor_m"])
    ) * np.asarray(metadata["affine_scale_xyz"])
    np.testing.assert_allclose(mapped["zone"][-1], expected_farfield, atol=1.0e-14)
    report = deform.acceptance_report(mapped, metadata)
    assert report["hard_gate_passed"]
    assert report["quality"]["inverted_cells"] == 0


def test_correspondence_rejects_shape_mismatch() -> None:
    volume, surface = _cube()
    surface["wall"] = surface["wall"][:-1]
    with pytest.raises(ValueError, match="wall shape"):
        deform.validate_template_correspondence(volume, surface)


@pytest.mark.parametrize(
    ("normal_points", "expected"),
    [(129, "smoke"), (193, "fine"), (257, "production")],
)
def test_registry_maps_normal_resolution_to_fallback_level(
    normal_points: int, expected: str
) -> None:
    assert campaign._volume_level_from_normal_points(normal_points) == expected


def test_case_lock_recovers_after_dead_local_worker(tmp_path, monkeypatch) -> None:
    lock = tmp_path / ".case.lock"
    lock.write_text(
        f"pid=123456 host={socket.gethostname()} started={time.time()}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(campaign, "_process_is_alive", lambda _pid: False)

    with campaign._case_lock(lock, wait_s=0.1):
        assert lock.is_file()

    assert not lock.exists()


def test_mesh_fingerprint_covers_governing_modules() -> None:
    paths = {str(path.resolve()) for path in campaign._mesh_implementation_paths()}
    for name in (
        "gates.py",
        "geometry_sets.py",
        "ingestion.py",
        "qc.py",
        "volume_qc.py",
    ):
        expected = campaign.STUDIES / "shared" / name
        assert str(expected.resolve()) in paths
    for name in ("pyhyp_extrude.py", "pyhyp_options.py", "volume_audit.py"):
        expected = campaign.REPO_ROOT / "src/aeris/cfd/meshing" / name
        assert str(expected.resolve()) in paths
    lhs = campaign.REPO_ROOT / "src/aeris/dataset/sampling/samplers/lhs_v1.py"
    assert str(lhs.resolve()) in paths
    surface = campaign.REPO_ROOT / "src/aeris/mesh/surface.py"
    assert str(surface.resolve()) in paths


def test_accepted_result_caches_require_matching_input_hashes(tmp_path) -> None:
    mesh = tmp_path / "mesh.cgns"
    mesh.write_bytes(b"mesh")
    mesh_report = tmp_path / "mesh_report.json"
    mesh_report.write_text(
        json.dumps(
            {
                "schema": campaign.MESH_REPORT_SCHEMA,
                "state": "MESH_ACCEPTED",
                "manifest_sha256": "manifest-a",
                "registry_sha256": "registry-a",
                "mesh_implementation_sha256": "implementation-a",
                "accepted_mesh": {
                    "cgns": str(mesh),
                    "cgns_sha256": deform.sha256(mesh),
                },
            }
        ),
        encoding="utf-8",
    )
    assert campaign._existing_accepted_mesh(
        mesh_report,
        manifest_sha256="manifest-a",
        registry_sha256="registry-a",
        implementation_sha256="implementation-a",
    )
    assert not campaign._existing_accepted_mesh(
        mesh_report,
        manifest_sha256="manifest-b",
        registry_sha256="registry-a",
        implementation_sha256="implementation-a",
    )

    solve_report = tmp_path / "solve_report.json"
    solver_log = tmp_path / "adflow_run.log"
    wall_summary = tmp_path / "wall_yplus_summary.json"
    surface = tmp_path / "aeris_cfd_000_surf.cgns"
    solve_report.write_text("{}", encoding="utf-8")
    solver_log.write_text("solver", encoding="utf-8")
    wall_summary.write_text("{}", encoding="utf-8")
    surface.write_bytes(b"surface")
    cfd_report = tmp_path / "cfd_acceptance.json"
    report = {
        "schema": campaign.CFD_REPORT_SCHEMA,
        "state": "CFD_ACCEPTED",
        "manifest_sha256": "manifest-a",
        "mesh_sha256": "mesh-a",
        "solver_implementation_sha256": "solver-a",
        "mpi_processes": 4,
        "solve_report": str(solve_report),
        "solve_report_sha256": deform.sha256(solve_report),
        "solver_log": str(solver_log),
        "solver_log_sha256": deform.sha256(solver_log),
        "wall_yplus_summary": str(wall_summary),
        "wall_yplus_summary_sha256": deform.sha256(wall_summary),
        "wall_yplus_gate": {
            "passed": True,
            "surface_cgns": str(surface),
            "surface_cgns_sha256": deform.sha256(surface),
        },
        "surface_solution_retained": True,
    }
    cfd_report.write_text(json.dumps(report), encoding="utf-8")
    assert campaign._existing_accepted_cfd(
        cfd_report,
        manifest_sha256="manifest-a",
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=4,
    )
    assert not campaign._existing_accepted_cfd(
        cfd_report,
        manifest_sha256="manifest-a",
        mesh_sha256="mesh-b",
        implementation_sha256="solver-a",
        mpi_np=4,
    )
    assert not campaign._existing_accepted_cfd(
        cfd_report,
        manifest_sha256="manifest-a",
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=2,
    )
    report["surface_solution_retained"] = False
    cfd_report.write_text(json.dumps(report), encoding="utf-8")
    surface.unlink()
    assert campaign._existing_accepted_cfd(
        cfd_report,
        manifest_sha256="manifest-a",
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=4,
    )
    surface.write_bytes(b"surface")
    report["surface_solution_retained"] = True
    cfd_report.write_text(json.dumps(report), encoding="utf-8")

    solver_log.write_text("changed", encoding="utf-8")
    assert not campaign._existing_accepted_cfd(
        cfd_report,
        manifest_sha256="manifest-a",
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=4,
    )
    solver_log.write_text("solver", encoding="utf-8")
    surface.write_bytes(b"changed")
    assert not campaign._existing_accepted_cfd(
        cfd_report,
        manifest_sha256="manifest-a",
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=4,
    )
    surface.write_bytes(b"surface")

    report["state"] = "CFD_REJECTED"
    cfd_report.write_text(json.dumps(report), encoding="utf-8")
    assert (
        campaign._existing_cfd_result(
            cfd_report,
            manifest_sha256="manifest-a",
            mesh_sha256="mesh-a",
            implementation_sha256="solver-a",
            mpi_np=4,
        )["state"]
        == "CFD_REJECTED"
    )
    assert not campaign._existing_accepted_cfd(
        cfd_report,
        manifest_sha256="manifest-a",
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=4,
    )


def test_campaign_finalizes_best_valid_candidate(tmp_path) -> None:
    candidates = []
    attempts = []
    for name, quality in (("near", 0.12), ("better", 0.19)):
        path = tmp_path / name / "wing_vol.cgns"
        path.parent.mkdir()
        path.write_bytes(name.encode())
        digest = campaign.sha256(path)
        candidates.append(
            {
                "template_id": name,
                "distance_rms": 0.1 if name == "near" else 0.2,
                "cgns": str(path),
                "cgns_sha256": digest,
                "acceptance": {"quality": {"min_scaled_quality": quality}},
            }
        )
        attempts.append(
            {
                "template_id": name,
                "candidate_cgns_sha256": digest,
                "independent_written_acceptance": {"production_floor_passed": True},
            }
        )

    selected = campaign._finalize_best_candidate(
        candidates,
        design_dir=tmp_path,
        attempts=attempts,
    )
    assert selected is not None
    assert selected["template_id"] == "better"
    assert (tmp_path / "wing_vol.cgns").read_bytes() == b"better"
    assert not (tmp_path / "near" / "wing_vol.cgns").exists()
    assert [attempt["selected"] for attempt in attempts] == [False, True]


def test_completed_design_cache_does_not_require_pruned_mesh(tmp_path) -> None:
    design_dir = tmp_path / "geometries" / "design_0"
    design_dir.mkdir(parents=True)
    case_ids = ["design_0__flow_0", "design_0__flow_1"]
    design_report = {
        "schema": campaign.DESIGN_REPORT_SCHEMA,
        "state": "DESIGN_ACCEPTED",
        "manifest_sha256": "manifest-a",
        "registry_sha256": "registry-a",
        "mesh_implementation_sha256": "mesh-code-a",
        "solver_implementation_sha256": "solver-code-a",
        "mpi_processes": 4,
        "mesh_sha256": "mesh-a",
        "case_ids": case_ids,
    }
    (design_dir / "design_run_report.json").write_text(json.dumps(design_report), encoding="utf-8")
    for case_id in case_ids:
        case_dir = tmp_path / "cases" / case_id
        case_dir.mkdir(parents=True)
        solve_report = case_dir / "solve_report.json"
        solver_log = case_dir / "adflow_run.log"
        wall_summary = case_dir / "wall_yplus_summary.json"
        surface = case_dir / "aeris_cfd_000_surf.cgns"
        solve_report.write_text("{}", encoding="utf-8")
        solver_log.write_text("solver", encoding="utf-8")
        wall_summary.write_text("{}", encoding="utf-8")
        surface.write_bytes(b"surface")
        (case_dir / "cfd_acceptance.json").write_text(
            json.dumps(
                {
                    "schema": campaign.CFD_REPORT_SCHEMA,
                    "state": "CFD_ACCEPTED",
                    "manifest_sha256": "manifest-a",
                    "mesh_sha256": "mesh-a",
                    "solver_implementation_sha256": "solver-code-a",
                    "mpi_processes": 4,
                    "solve_report": str(solve_report),
                    "solve_report_sha256": deform.sha256(solve_report),
                    "solver_log": str(solver_log),
                    "solver_log_sha256": deform.sha256(solver_log),
                    "wall_yplus_summary": str(wall_summary),
                    "wall_yplus_summary_sha256": deform.sha256(wall_summary),
                    "wall_yplus_gate": {
                        "passed": True,
                        "surface_cgns": str(surface),
                        "surface_cgns_sha256": deform.sha256(surface),
                    },
                    "surface_solution_retained": True,
                }
            ),
            encoding="utf-8",
        )

    cached = campaign._existing_accepted_design(
        campaign_root=tmp_path,
        design_id="design_0",
        case_ids=case_ids,
        manifest_sha256="manifest-a",
        registry_sha256="registry-a",
        mesh_implementation_sha256="mesh-code-a",
        solver_implementation_sha256="solver-code-a",
        mpi_np=4,
    )
    assert cached is not None
    assert cached["state"] == "DESIGN_ACCEPTED"
    assert (
        campaign._existing_accepted_design(
            campaign_root=tmp_path,
            design_id="design_0",
            case_ids=case_ids,
            manifest_sha256="manifest-a",
            registry_sha256="registry-a",
            mesh_implementation_sha256="mesh-code-a",
            solver_implementation_sha256="solver-code-a",
            mpi_np=2,
        )
        is None
    )


def test_collect_handles_mixed_finished_and_missing_cases(tmp_path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest = {
        "schema": campaign.MANIFEST_SCHEMA,
        "cases": [
            {
                "case_index": 0,
                "case_id": "case_0",
                "design_id": "design_0",
                "flow_id": "flow_0",
            },
            {
                "case_index": 1,
                "case_id": "case_1",
                "design_id": "design_1",
                "flow_id": "flow_0",
            },
        ],
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_hash = deform.sha256(manifest_path)
    accepted_dir = tmp_path / "campaign" / "cases" / "case_0"
    accepted_dir.mkdir(parents=True)
    (accepted_dir / "cfd_acceptance.json").write_text(
        json.dumps(
            {
                "state": "CFD_ACCEPTED",
                "manifest_sha256": manifest_hash,
                "forces": {"cl": 0.4, "cd": 0.03, "cmy": -0.01},
                "residual_orders_dropped": 7.0,
                "wall_yplus_gate": {"statistics": {"p95": 0.8, "maximum": 1.2}},
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "summary.json"
    report = campaign.collect(tmp_path / "campaign", manifest_path, output)
    assert report["counts"] == {"CFD_ACCEPTED": 1, "NOT_RUN": 1}
    with output.with_suffix(".csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2
    assert rows[0]["cl"] == "0.4"
    assert rows[1]["cl"] == ""


def test_deformation_preserves_a_shared_block_face() -> None:
    i = np.linspace(0.0, 1.0, 5)
    k = np.linspace(0.0, 3.0, 8)

    def block(y0: float, y1: float) -> np.ndarray:
        j = np.linspace(y0, y1, 3)
        kk, jj, ii = np.meshgrid(k, j, i, indexing="ij")
        return np.stack((ii, jj, kk), axis=-1)

    volume = {"left": block(0.0, 0.5), "right": block(0.5, 1.0)}
    template = {
        "left_wall": volume["left"][0].transpose(1, 0, 2),
        "right_wall": volume["right"][0].transpose(1, 0, 2),
    }
    target = {name: wall.copy() for name, wall in template.items()}
    for wall in target.values():
        wall[..., 2] = 0.03 * np.sin(np.pi * wall[..., 0])

    mapped, metadata = deform.deform_volume_blocks(volume, template, target)
    interfaces = deform.volume_interface_report(mapped)
    assert interfaces["paired_face_count"] == 1
    assert interfaces["max_mismatch_m"] < 1.0e-14
    assert deform.acceptance_report(mapped, metadata)["hard_gate_passed"]


def test_manifest_expands_unique_design_flow_pairs(tmp_path) -> None:
    names, low, high = atlas.design_bounds()
    midpoint = 0.5 * (low + high)
    design_csv = tmp_path / "designs.csv"
    design_csv.write_text(
        ",".join(["design_id", *names])
        + "\n"
        + ",".join(["d0", *(str(value) for value in midpoint)])
        + "\n",
        encoding="utf-8",
    )
    flow_csv = tmp_path / "flows.csv"
    flow_csv.write_text(
        "flow_id,alpha,mach,reynolds,temperature\n"
        "cruise,2.0,0.2,1000000,288.15\n"
        "high_alpha,6.0,0.2,1000000,288.15\n",
        encoding="utf-8",
    )

    manifest = campaign.make_manifest(design_csv, flow_csv, tmp_path / "campaign.json")
    assert manifest["counts"] == {"designs": 1, "flows": 2, "cases": 2}
    assert [row["case_id"] for row in manifest["cases"]] == [
        "d0__cruise",
        "d0__high_alpha",
    ]


def test_force_tail_gate_rejects_unstable_forces(tmp_path) -> None:
    stable = tmp_path / "stable.log"
    stable.write_text(
        "\n".join(
            f"1 {index} {index} ANK 100 1 0.1 {1e-2 / index} 1e-6 "
            f"{0.4 + 1e-6 * index} {0.03 + 1e-7 * index} 1"
            for index in range(1, 31)
        ),
        encoding="utf-8",
    )
    assert campaign._force_tail_gate(stable, relative_range_max=0.001)["passed"]

    unstable = tmp_path / "unstable.log"
    unstable.write_text(
        stable.read_text(encoding="utf-8").replace("0.40003", "0.5"),
        encoding="utf-8",
    )
    assert not campaign._force_tail_gate(unstable, relative_range_max=0.001)["passed"]


def test_force_tail_gate_handles_near_zero_lift(tmp_path) -> None:
    log = tmp_path / "near_zero.log"
    log.write_text(
        "\n".join(
            f"1 {index} {index} ANK 100 1 0.1 {1e-2 / index} 1e-6 "
            f"{-0.02 + 1e-6 * index} {0.03 + 1e-7 * index} 1"
            for index in range(1, 31)
        ),
        encoding="utf-8",
    )
    report = campaign._force_tail_gate(log, relative_range_max=0.001)
    assert report["passed"]
    assert report["coefficient_floors"] == {"cl": 0.10, "cd": 0.01}


def test_force_plausibility_requires_complete_finite_positive_drag() -> None:
    assert campaign._force_plausibility_gate({"cl": 0.4, "cd": 0.03, "cmy": -0.02})["passed"]
    assert not campaign._force_plausibility_gate({"cl": 0.4, "cd": -0.001, "cmy": -0.02})["passed"]
    assert not campaign._force_plausibility_gate({"cl": 0.4, "cd": 0.03})["passed"]


def test_wall_yplus_gate_reads_only_no_slip_wall_zones(tmp_path) -> None:
    path = tmp_path / "surface.cgns"
    with h5py.File(path, "w") as handle:
        wall = handle.create_group("BaseSurfaceSol/NSWallAdiabaticBCZone1/Flow solution/YPlus")
        wall.create_dataset(" data", data=np.linspace(0.1, 0.9, 100))
        farfield = handle.create_group("BaseSurfaceSol/FarFieldBCZone2/Flow solution/YPlus")
        farfield.create_dataset(" data", data=np.full(100, 100.0))

    report = cfd_qc.wall_yplus_summary(path)
    assert report["passed"]
    assert report["wall_zone_count"] == 1
    assert report["sample_count"] == 100
    assert report["statistics"]["maximum"] == pytest.approx(0.9)
    assert report["threshold_scope"] == "global_and_each_no_slip_wall_zone"
    assert "first off-wall cell centroid" in report["wall_distance_convention"]
    assert report["regions"]["NSWallAdiabaticBCZone1"]["passed"]


def test_wall_yplus_gate_rejects_large_wall_values(tmp_path) -> None:
    path = tmp_path / "surface.cgns"
    with h5py.File(path, "w") as handle:
        wall = handle.create_group("BaseSurfaceSol/NSWallAdiabaticBCZone1/Flow solution/YPlus")
        wall.create_dataset(" data", data=np.linspace(0.1, 7.0, 100))

    report = cfd_qc.wall_yplus_summary(path)
    assert not report["passed"]
    assert "maximum_above_limit" in report["failure_reasons"]
    assert report["failed_regions"] == ["NSWallAdiabaticBCZone1"]
    assert "one_or_more_wall_regions_above_limit" in report["failure_reasons"]
