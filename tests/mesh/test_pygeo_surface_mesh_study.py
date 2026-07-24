from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from standalone.pygeo_surface_mesh_study.analysis import (
    build_analysis,
    rank_variable_names,
)
from standalone.pygeo_surface_mesh_study.modeling import (
    fit_response_model,
    orthonormal_quadratic_basis,
)
from standalone.pygeo_surface_mesh_study.runner import (
    build_geometry,
    evaluate_acceptance,
    group_block_metrics,
    load_generator_config,
)
from standalone.pygeo_surface_mesh_study.spec import (
    MetricLimit,
    VariableSpec,
    load_study_spec,
)

ROOT = Path(__file__).resolve().parents[2]
STUDY_CONFIG = ROOT / "configs/cfd/pygeo_surface_mesh_study.yaml"


def _spec():
    return load_study_spec(STUDY_CONFIG)


def _block(name: str, *, shape: float, skew: float, cells: int = 100) -> dict:
    return {
        "name": name,
        "nodes": cells + 1,
        "cells": cells,
        "min_area": 1.0e-5,
        "median_area": 2.0e-5,
        "min_shape_metric": shape,
        "median_shape_metric": shape + 0.1,
        "min_scaled_jacobian": shape * 0.9,
        "min_triangle_normal_alignment": 0.99,
        "median_triangle_normal_alignment": 1.0,
        "max_adjacent_normal_angle_deg": 12.0,
        "max_equiangle_skewness": skew,
        "mean_equiangle_skewness": skew * 0.5,
        "max_aspect_ratio": 4.0,
        "max_growth_ratio": 1.3,
    }


def _report() -> dict:
    return {
        "accepted_pre_pyhyp": True,
        "connectivity": {"all_matched": True},
        "free_edges": {"closed_except_root": True},
        "symmetry_root": {"planar_within_tolerance": True},
        "global": {
            "min_area": 1.0e-5,
            "area_floor": 1.0e-12,
            "min_triangle_normal_alignment": 0.99,
            "alignment_floor": -0.25,
        },
        "blocks": [
            _block("oml_0", shape=0.30, skew=0.60, cells=100),
            _block("oml_1", shape=0.20, skew=0.70, cells=300),
            _block("tip_ring_0", shape=0.10, skew=0.90, cells=50),
        ],
    }


def _result(
    spec,
    case_id: str,
    stage: str,
    metrics: dict[str, float],
    *,
    perturbations: dict[str, float] | None = None,
    public_values: dict[str, float] | None = None,
) -> dict:
    values = spec.baseline_values
    if public_values:
        values.update(public_values)
    return {
        "status": "complete",
        "limits_satisfied": True,
        "selected_level": "L1",
        "selected_level_order": 1,
        "reference_metrics": metrics,
        "case": {
            "case_id": case_id,
            "stage": stage,
            "perturbations": perturbations or {},
            "public_values": values,
        },
        "attempts": [],
    }


def test_real_study_config_and_plan_are_deterministic() -> None:
    first = _spec()
    second = _spec()
    generator_config = load_generator_config(first)
    airfoils = generator_config.section_bounds.station_airfoils
    assert airfoils is not None
    assert airfoils.to_dict() == {
        "b0": "mh91",
        "b1": "mh91",
        "b2": "e374",
        "b3": "nlf1015",
    }

    assert len(first.variables) == 16
    assert first.variable_map["root_chord_m"].baseline == pytest.approx(0.90)
    assert first.variable_map["root_chord_m"].low == pytest.approx(0.70)
    assert first.variable_map["root_chord_m"].high == pytest.approx(1.10)
    assert first.variable_map["semi_span_m"].baseline == pytest.approx(1.00)
    assert first.variable_map["semi_span_m"].low == pytest.approx(0.75)
    assert first.variable_map["semi_span_m"].high == pytest.approx(1.25)
    assert first.validation_method == "iid_uniform"
    assert first.fixed_sample_values == {
        "dihedral_b1_deg": 0.0,
        "elevon_start_frac": 0.60,
        "elevon_end_frac": 0.95,
        "elevon_hinge_frac": 0.75,
    }
    assert first.initial_plan() == second.initial_plan()
    assert first.initial_plan()["counts"] == {
        "baseline": 1,
        "global_train": 1024,
        "ofat": 128,
        "pairwise": 480,
        "validation": 512,
        "total_geometries": 2145,
        "planned_mesh_builds": 10725,
    }
    assert first.reference_level == "L3"
    assert first.complete_ladder
    assert [level.name for level in first.levels] == ["L1", "L2", "L3", "L4", "L5"]
    assert len(first.unset_enabled_limits()) == 14

    pairs = first.pairwise_cases()
    assert len(pairs) == len({case.identity_hash for case in pairs}) == 480
    global_sweep = [case.public_values["inner_le_sweep_deg"] for case in first.global_train_cases()]
    assert len(set(global_sweep)) == 1024
    assert all(20.0 < value < 40.0 for value in global_sweep)


def test_piecewise_delta_mapping_and_sweep_sign() -> None:
    variable = VariableSpec(
        name="sweep",
        sample_field="sw1_deg",
        units="deg",
        baseline=10.0,
        low=0.0,
        high=50.0,
        sample_scale=-1.0,
    )
    assert variable.value_at_fraction(-0.5) == pytest.approx(5.0)
    assert variable.value_at_fraction(0.5) == pytest.approx(30.0)
    assert variable.to_sample_value(30.0) == pytest.approx(-30.0)
    spec = _spec()
    public = spec.baseline_values
    public["inner_le_sweep_deg"] = 20.0
    assert spec.sample_values(public)["sw1_deg"] == pytest.approx(-20.0)


def test_group_metrics_and_acceptance_operators() -> None:
    report = _report()
    oml = group_block_metrics(report["blocks"], "oml_")
    assert oml["min_shape_metric"] == pytest.approx(0.20)
    assert oml["max_equiangle_skewness"] == pytest.approx(0.70)
    assert oml["mean_equiangle_skewness"] == pytest.approx(0.3375)
    assert oml["cells"] == 400

    limits = [
        MetricLimit("oml.min_shape_metric", ">=", 0.15, True),
        MetricLimit("oml.max_equiangle_skewness", "<=", 0.75, True),
        MetricLimit("tip.max_equiangle_skewness", "<=", None, True),
    ]
    strict = evaluate_acceptance(report, limits, allow_unset_limits=False)
    assert not strict["passed"]
    assert strict["metric_checks"][-1]["status"] == "unset"
    permissive = evaluate_acceptance(report, limits, allow_unset_limits=True)
    assert permissive["passed"]

    failed_report = copy.deepcopy(report)
    failed_report["blocks"][1]["min_shape_metric"] = 0.05
    failed = evaluate_acceptance(failed_report, limits, allow_unset_limits=True)
    assert not failed["passed"]


def test_synthetic_ofat_ranking_and_candidate_fit() -> None:
    spec = _spec()
    base_metrics = {
        metric.path: (0.5 if metric.operator == ">=" else 1.0) for metric in spec.metric_limits
    }
    results = [_result(spec, "baseline", "baseline", base_metrics)]
    for variable_name, fraction, delta in (
        ("root_chord_m", -1.0, 0.20),
        ("root_chord_m", 1.0, 0.40),
        ("chord_ratio_b1_root", -1.0, 0.02),
        ("chord_ratio_b1_root", 1.0, 0.03),
    ):
        variable = spec.variable_map[variable_name]
        metrics = dict(base_metrics)
        metrics["oml.max_aspect_ratio"] += delta
        results.append(
            _result(
                spec,
                f"ofat__{variable_name}__{fraction}",
                "ofat",
                metrics,
                perturbations={variable_name: fraction},
                public_values={
                    variable_name: variable.value_at_fraction(fraction),
                },
            )
        )
    ranked = rank_variable_names(spec, results)
    assert ranked[:2] == ["root_chord_m", "chord_ratio_b1_root"]
    analysis = build_analysis(spec, results)
    fit = analysis["ofat_candidate_laws"]["root_chord_m"]["metric_laws"]["oml.max_aspect_ratio"][
        "fit_in_normalized_fraction"
    ]
    assert fit["degree"] == 2
    assert fit["r2"] == pytest.approx(1.0)


def test_global_legendre_basis_is_centered_and_nearly_orthonormal() -> None:
    spec = _spec()
    normalized = np.random.default_rng(20260724).uniform(
        -1.0, 1.0, size=(4096, len(spec.variables))
    )
    basis = orthonormal_quadratic_basis(normalized, [variable.name for variable in spec.variables])
    assert basis.matrix.shape == (4096, 153)
    gram = basis.matrix.T @ basis.matrix / len(normalized)
    assert np.max(np.abs(np.diag(gram) - 1.0)) < 0.08
    off_diagonal = gram - np.diag(np.diag(gram))
    assert np.max(np.abs(off_diagonal)) < 0.10


def test_global_response_model_recovers_known_law_on_holdout() -> None:
    original = _spec()
    analysis_config = copy.deepcopy(original.analysis_config)
    analysis_config["global_model"].update(
        {
            "cv_folds": 3,
            "ridge_lambdas": [0.0],
            "bootstrap_replicates": 8,
        }
    )
    spec = replace(original, analysis_config=analysis_config)
    metric = MetricLimit("oml.max_aspect_ratio", "<=", 10.0, True)

    def result(case) -> dict:
        x = case.perturbations
        response = (
            4.0
            + 0.6 * x["root_chord_m"]
            + 0.3 * x["chord_ratio_b1_root"] * x["chord_ratio_b2_root"]
        )
        return {
            "case": case.to_dict(),
            "attempts": [
                {
                    "level": "L3",
                    "acceptance": {"flat_metrics": {"oml.max_aspect_ratio": response}},
                }
            ],
        }

    results = [
        *(result(case) for case in spec.global_train_cases()),
        *(result(case) for case in spec.validation_cases()),
    ]
    model = fit_response_model(spec, results, "L3", metric)
    assert model is not None
    assert model["validation"]["normalized_rmse"] < 1.0e-10
    assert model["validation"]["classification"]["false_accepts"] == 0
    assert model["deployable"]
    intervals = model["sensitivity_confidence_intervals"]
    assert intervals is not None and intervals["replicates"] == 8
    total = model["sobol_indices_from_validated_surrogate"]["total_effect"]
    assert total["root_chord_m"] > total["chord_ratio_b1_root"] > 0.0


@pytest.mark.integration
def test_baseline_pygeo_uniform_source_lattice() -> None:
    pytest.importorskip("pygeo")
    spec = _spec()
    generator_config = load_generator_config(spec)
    carrier, _build, geometry = build_geometry(
        spec,
        generator_config,
        spec.baseline_case(),
    )
    assert len(carrier.sections) == 14
    assert geometry["realised"]["quality_passed"]
    assert geometry["realised"]["minimum_source_spacing_fraction"] > 0.07
    descriptors = geometry["descriptors"]
    assert descriptors["scale"]["aspect_ratio"] > 0.0
    assert len(descriptors["planform"]["panel_taper_ratios"]) == 3
    assert descriptors["airfoil_shape"]["thickness_ratio_max"] > 0.0
    assert not descriptors["airfoil_shape"]["independent_thickness_effect_identifiable"]
