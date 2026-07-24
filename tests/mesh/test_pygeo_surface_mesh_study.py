from __future__ import annotations

import copy
from pathlib import Path

import pytest

from standalone.pygeo_surface_mesh_study.analysis import (
    build_analysis,
    rank_variable_names,
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
    airfoils = load_generator_config(first).section_bounds.station_airfoils
    assert airfoils is not None
    assert airfoils.to_dict() == {
        "b0": "mh91",
        "b1": "mh91",
        "b2": "e374",
        "b3": "nlf1015",
    }

    assert len(first.variables) == 17
    assert first.initial_plan() == second.initial_plan()
    assert first.initial_plan()["counts"] == {
        "baseline": 1,
        "ofat": 62,
        "lhs": 64,
        "pairwise": None,
    }
    assert first.reference_level == "L3"
    assert [level.name for level in first.levels] == ["L1", "L2", "L3", "L4", "L5"]
    assert len(first.unset_enabled_limits()) == 14
    lhs_sweep = [case.public_values["sw1_deg"] for case in first.lhs_cases()]
    assert len(set(lhs_sweep)) == 64
    assert all(0.0 < value < 55.0 for value in lhs_sweep)


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
    public["sw1_deg"] = 20.0
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
        ("c1_m", -1.0, 0.20),
        ("c1_m", 1.0, 0.40),
        ("c2_ratio", -1.0, 0.02),
        ("c2_ratio", 1.0, 0.03),
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
    assert ranked[:2] == ["c1_m", "c2_ratio"]
    analysis = build_analysis(spec, results)
    fit = analysis["ofat_candidate_laws"]["c1_m"]["metric_laws"]["oml.max_aspect_ratio"][
        "fit_in_normalized_fraction"
    ]
    assert fit["degree"] == 2
    assert fit["r2"] == pytest.approx(1.0)


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
