"""Sensitivity, interaction, refinement, and candidate-law extraction."""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.stats import spearmanr

from .spec import StudySpec, VariableSpec

ANALYSIS_SCHEMA = "aeris.pygeo_surface_mesh_analysis.v1"


def _case(result: Mapping[str, Any]) -> Mapping[str, Any]:
    value = result.get("case", {})
    return value if isinstance(value, Mapping) else {}


def _reference_metrics(result: Mapping[str, Any]) -> Mapping[str, float]:
    value = result.get("reference_metrics", {})
    return value if isinstance(value, Mapping) else {}


def _eligible_reference_results(
    results: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    return [
        result
        for result in results
        if result.get("status") in {"complete", "limits_unresolved"} and _reference_metrics(result)
    ]


def _baseline_result(
    results: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    return next(
        (
            result
            for result in _eligible_reference_results(results)
            if _case(result).get("stage") == "baseline"
        ),
        None,
    )


def _limit_scale(spec: StudySpec, metric_path: str, baseline: float) -> float:
    limit = next((item for item in spec.metric_limits if item.path == metric_path), None)
    if limit is not None and limit.enabled and limit.limit is not None:
        distance = abs(float(limit.limit) - baseline)
        if distance > 1.0e-12:
            return distance
    return max(abs(baseline), 1.0e-12)


def _ofat_for_variable(
    results: Sequence[Mapping[str, Any]], variable_name: str
) -> list[Mapping[str, Any]]:
    selected = []
    for result in _eligible_reference_results(results):
        case = _case(result)
        if case.get("stage") != "ofat":
            continue
        perturbations = case.get("perturbations", {})
        if isinstance(perturbations, Mapping) and set(perturbations) == {variable_name}:
            selected.append(result)
    return selected


def variable_sensitivity_score(
    spec: StudySpec,
    results: Sequence[Mapping[str, Any]],
    variable: VariableSpec,
) -> tuple[float, dict[str, float]]:
    baseline_result = _baseline_result(results)
    if baseline_result is None:
        return -math.inf, {}
    baseline_metrics = _reference_metrics(baseline_result)
    ofat_results = _ofat_for_variable(results, variable.name)
    metric_scores: dict[str, float] = {}
    for metric in spec.metric_limits:
        if not metric.enabled or metric.path not in baseline_metrics:
            continue
        baseline = float(baseline_metrics[metric.path])
        responses = [
            abs(float(_reference_metrics(result)[metric.path]) - baseline)
            for result in ofat_results
            if metric.path in _reference_metrics(result)
        ]
        if responses:
            metric_scores[metric.path] = max(responses) / _limit_scale(spec, metric.path, baseline)
    return (max(metric_scores.values()) if metric_scores else -math.inf), metric_scores


def rank_variable_names(
    spec: StudySpec,
    results: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Rank variables by their largest limit-normalized common-L3 response."""

    scored = []
    for index, variable in enumerate(spec.variables):
        score, _metric_scores = variable_sensitivity_score(spec, results, variable)
        if math.isfinite(score):
            scored.append((score, -index, variable.name))
    scored.sort(reverse=True)
    return [name for _score, _index, name in scored]


def _polynomial_fit(x: Sequence[float], y: Sequence[float]) -> dict[str, Any]:
    x_array = np.asarray(x, dtype=float)
    y_array = np.asarray(y, dtype=float)
    unique_x = np.unique(np.round(x_array, decimals=12))
    degree = min(2, len(unique_x) - 1)
    if degree < 1:
        return {
            "degree": 0,
            "coefficients_ascending": [float(np.mean(y_array))],
            "r2": None,
        }
    coefficients = np.polynomial.polynomial.polyfit(x_array, y_array, deg=degree)
    predicted = np.polynomial.polynomial.polyval(x_array, coefficients)
    residual = float(np.sum((y_array - predicted) ** 2))
    total = float(np.sum((y_array - np.mean(y_array)) ** 2))
    r2 = (
        1.0
        if total <= 1.0e-30 and residual <= 1.0e-30
        else (None if total <= 1.0e-30 else 1.0 - residual / total)
    )
    return {
        "degree": degree,
        "coefficients_ascending": [float(value) for value in coefficients],
        "r2": None if r2 is None else float(r2),
    }


def _trend(deltas: Sequence[float]) -> str:
    tolerance = max(1.0e-14, max((abs(value) for value in deltas), default=0.0) * 1.0e-8)
    signs = {int(np.sign(value)) for value in deltas if abs(value) > tolerance}
    if not signs:
        return "flat_over_tested_points"
    if signs == {1}:
        return "increases_from_baseline"
    if signs == {-1}:
        return "decreases_from_baseline"
    return "nonmonotone_or_direction_changes"


def _selected_order(result: Mapping[str, Any]) -> int | None:
    value = result.get("selected_level_order")
    return int(value) if isinstance(value, (int, float)) else None


def ofat_laws(
    spec: StudySpec,
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    baseline_result = _baseline_result(results)
    if baseline_result is None:
        return {}
    baseline_metrics = _reference_metrics(baseline_result)
    output: dict[str, Any] = {}
    for variable in spec.variables:
        variable_results = _ofat_for_variable(results, variable.name)
        rows = []
        for result in variable_results:
            case = _case(result)
            perturbations = case.get("perturbations", {})
            public = case.get("public_values", {})
            if not isinstance(perturbations, Mapping) or not isinstance(public, Mapping):
                continue
            rows.append(
                {
                    "fraction": float(perturbations[variable.name]),
                    "public_value": float(public[variable.name]),
                    "metrics": dict(_reference_metrics(result)),
                    "limits_satisfied": bool(result.get("limits_satisfied", False)),
                    "selected_level": result.get("selected_level"),
                    "selected_level_order": _selected_order(result),
                }
            )
        rows.sort(key=lambda row: row["fraction"])
        metric_laws: dict[str, Any] = {}
        for metric_limit in spec.metric_limits:
            metric_path = metric_limit.path
            if metric_path not in baseline_metrics:
                continue
            paired = [
                (float(row["fraction"]), float(row["metrics"][metric_path]))
                for row in rows
                if metric_path in row["metrics"]
            ]
            if not paired:
                continue
            x = [0.0, *(item[0] for item in paired)]
            y = [float(baseline_metrics[metric_path]), *(item[1] for item in paired)]
            baseline = y[0]
            deltas = [value - baseline for value in y[1:]]
            fit = _polynomial_fit(x, y)
            metric_laws[metric_path] = {
                "baseline": baseline,
                "minimum": min(y),
                "maximum": max(y),
                "maximum_absolute_delta": max(abs(value) for value in deltas),
                "maximum_relative_delta": (
                    None
                    if abs(baseline) <= 1.0e-15
                    else max(abs(value) for value in deltas) / abs(baseline)
                ),
                "trend": _trend(deltas),
                "fit_in_normalized_fraction": fit,
            }
        passed_values: list[float] = []
        if baseline_result.get("limits_satisfied", False):
            passed_values.append(variable.baseline)
        passed_values.extend(float(row["public_value"]) for row in rows if row["limits_satisfied"])
        selected_orders = [
            int(row["selected_level_order"])
            for row in rows
            if row["selected_level_order"] is not None
        ]
        baseline_order = _selected_order(baseline_result)
        if baseline_order is not None:
            selected_orders.append(baseline_order)
        score, metric_scores = variable_sensitivity_score(spec, results, variable)
        output[variable.name] = {
            "units": variable.units,
            "public_domain": [variable.low, variable.high],
            "baseline": variable.baseline,
            "tested_points": rows,
            "tested_passing_interval": (
                None if not passed_values else [min(passed_values), max(passed_values)]
            ),
            "maximum_selected_level_order": max(selected_orders, default=None),
            "sensitivity_score": None if not math.isfinite(score) else score,
            "metric_sensitivity_scores": metric_scores,
            "metric_laws": metric_laws,
        }
    return output


def pairwise_interactions(
    spec: StudySpec,
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    baseline_result = _baseline_result(results)
    if baseline_result is None:
        return {}
    baseline_metrics = _reference_metrics(baseline_result)

    ofat_lookup: dict[tuple[str, float, str], float] = {}
    for variable in spec.variables:
        for result in _ofat_for_variable(results, variable.name):
            case = _case(result)
            perturbations = case.get("perturbations", {})
            if not isinstance(perturbations, Mapping):
                continue
            fraction = round(float(perturbations[variable.name]), 10)
            for metric_path, value in _reference_metrics(result).items():
                ofat_lookup[(variable.name, fraction, metric_path)] = float(value)

    residuals: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    cases: list[dict[str, Any]] = []
    for result in _eligible_reference_results(results):
        case = _case(result)
        if case.get("stage") != "pairwise":
            continue
        perturbations = case.get("perturbations", {})
        if not isinstance(perturbations, Mapping) or len(perturbations) != 2:
            continue
        names = sorted(str(name) for name in perturbations)
        first, second = names
        first_fraction = round(float(perturbations[first]), 10)
        second_fraction = round(float(perturbations[second]), 10)
        case_residuals: dict[str, float] = {}
        for metric in spec.metric_limits:
            path = metric.path
            if path not in baseline_metrics or path not in _reference_metrics(result):
                continue
            first_ofat = ofat_lookup.get((first, first_fraction, path))
            second_ofat = ofat_lookup.get((second, second_fraction, path))
            if first_ofat is None or second_ofat is None:
                continue
            additive = first_ofat + second_ofat - float(baseline_metrics[path])
            residual = float(_reference_metrics(result)[path]) - additive
            residuals[(first, second, path)].append(residual)
            case_residuals[path] = residual
        cases.append(
            {
                "case_id": case.get("case_id"),
                "variables": names,
                "fractions": {
                    first: float(perturbations[first]),
                    second: float(perturbations[second]),
                },
                "interaction_residuals": case_residuals,
            }
        )

    summaries: dict[str, Any] = {}
    for (first, second, metric_path), values in residuals.items():
        pair_key = f"{first}__{second}"
        summaries.setdefault(pair_key, {"variables": [first, second], "metrics": {}})
        baseline = float(baseline_metrics[metric_path])
        summaries[pair_key]["metrics"][metric_path] = {
            "samples": len(values),
            "mean_residual": float(np.mean(values)),
            "rms_residual": float(np.sqrt(np.mean(np.asarray(values) ** 2))),
            "max_absolute_residual": max(abs(value) for value in values),
            "max_absolute_residual_relative_to_baseline": (
                None
                if abs(baseline) <= 1.0e-15
                else max(abs(value) for value in values) / abs(baseline)
            ),
        }
    return {"summaries": summaries, "cases": cases}


def lhs_correlations(
    spec: StudySpec,
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    lhs_results = [
        result
        for result in _eligible_reference_results(results)
        if _case(result).get("stage") == "lhs"
    ]
    output: dict[str, Any] = {}
    for variable in spec.variables:
        per_metric: dict[str, Any] = {}
        x = []
        rows = []
        for result in lhs_results:
            public = _case(result).get("public_values", {})
            if isinstance(public, Mapping) and variable.name in public:
                x.append(float(public[variable.name]))
                rows.append(result)
        if len(x) < 3 or np.ptp(x) <= 0.0:
            continue
        for metric in spec.metric_limits:
            paired = [
                (x_value, float(_reference_metrics(result)[metric.path]))
                for x_value, result in zip(x, rows, strict=False)
                if metric.path in _reference_metrics(result)
            ]
            if len(paired) < 3:
                continue
            x_values, y_values = zip(*paired, strict=False)
            if np.ptp(y_values) <= 0.0:
                rho, pvalue = 0.0, 1.0
            else:
                rho, pvalue = spearmanr(x_values, y_values)
            per_metric[metric.path] = {
                "spearman_rho": float(rho),
                "p_value": float(pvalue),
                "samples": len(paired),
            }
        output[variable.name] = per_metric
    return output


def refinement_summary(
    spec: StudySpec,
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    level_stats: dict[str, dict[str, Any]] = {
        level.name: {
            "order": level.order,
            "attempted": 0,
            "passed": 0,
            "metrics": defaultdict(list),
        }
        for level in spec.levels
    }
    selected_counts: dict[str, int] = defaultdict(int)
    unresolved = 0
    nonmonotone_cases: list[str] = []
    transitions: dict[tuple[str, str, str], list[float]] = defaultdict(list)

    for result in results:
        attempts = result.get("attempts", [])
        if not isinstance(attempts, list):
            continue
        selected = result.get("selected_level")
        if selected is None and result.get("status") == "limits_unresolved":
            unresolved += 1
        elif selected is not None:
            selected_counts[str(selected)] += 1
        monotonicity = result.get("resolution_monotonicity", {})
        if (
            isinstance(monotonicity, Mapping)
            and monotonicity.get("monotone_pass_after_first_success") is False
        ):
            nonmonotone_cases.append(str(_case(result).get("case_id", "unknown")))

        metrics_by_level: dict[str, Mapping[str, float]] = {}
        for attempt in attempts:
            if not isinstance(attempt, Mapping):
                continue
            level_name = str(attempt.get("level"))
            if level_name not in level_stats:
                continue
            acceptance = attempt.get("acceptance", {})
            if not isinstance(acceptance, Mapping):
                continue
            level_stats[level_name]["attempted"] += 1
            if acceptance.get("passed", False):
                level_stats[level_name]["passed"] += 1
            metrics = acceptance.get("flat_metrics", {})
            if isinstance(metrics, Mapping):
                metrics_by_level[level_name] = metrics
                for path, value in metrics.items():
                    if isinstance(value, (int, float)):
                        level_stats[level_name]["metrics"][path].append(float(value))

        ordered_present = [level for level in spec.levels if level.name in metrics_by_level]
        for first, second in zip(ordered_present, ordered_present[1:], strict=False):
            first_metrics = metrics_by_level[first.name]
            second_metrics = metrics_by_level[second.name]
            for metric in spec.metric_limits:
                if metric.path in first_metrics and metric.path in second_metrics:
                    transitions[(first.name, second.name, metric.path)].append(
                        float(second_metrics[metric.path]) - float(first_metrics[metric.path])
                    )

    levels_output: dict[str, Any] = {}
    for level in spec.levels:
        stats = level_stats[level.name]
        metric_summary = {
            path: {
                "median": float(np.median(values)),
                "minimum": min(values),
                "maximum": max(values),
            }
            for path, values in stats["metrics"].items()
            if values
        }
        levels_output[level.name] = {
            "order": level.order,
            "attempted": stats["attempted"],
            "passed": stats["passed"],
            "conditional_pass_rate": (
                None if stats["attempted"] == 0 else stats["passed"] / stats["attempted"]
            ),
            "metric_summary": metric_summary,
        }
    transition_output: dict[str, Any] = {}
    for (first, second, path), values in transitions.items():
        key = f"{first}__to__{second}"
        transition_output.setdefault(key, {})
        transition_output[key][path] = {
            "samples": len(values),
            "median_delta": float(np.median(values)),
            "minimum_delta": min(values),
            "maximum_delta": max(values),
        }
    return {
        "levels": levels_output,
        "selected_level_distribution": dict(selected_counts),
        "unresolved_cases": unresolved,
        "nonmonotone_pass_cases": nonmonotone_cases,
        "observed_transition_deltas": transition_output,
        "caution": (
            "Fine-level pass rates are conditional because the adaptive ladder stops "
            "after the first passing level. L3 is the unbiased common-reference level."
        ),
    }


def build_analysis(
    spec: StudySpec,
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    eligible = _eligible_reference_results(results)
    ranked = rank_variable_names(spec, results)
    laws = ofat_laws(spec, results)
    ranking_rows = []
    for variable_name in ranked:
        variable = spec.variable_map[variable_name]
        score, metric_scores = variable_sensitivity_score(spec, results, variable)
        ranking_rows.append(
            {
                "rank": len(ranking_rows) + 1,
                "variable": variable_name,
                "units": variable.units,
                "score": score,
                "dominant_metric": (
                    max(metric_scores, key=metric_scores.get) if metric_scores else None
                ),
                "metric_scores": metric_scores,
            }
        )
    baseline = _baseline_result(results)
    return {
        "schema": ANALYSIS_SCHEMA,
        "study": spec.name,
        "reference_level": spec.reference_level,
        "result_count": len(results),
        "eligible_common_reference_count": len(eligible),
        "baseline_reference_metrics": (
            None if baseline is None else dict(_reference_metrics(baseline))
        ),
        "ranking": ranking_rows,
        "ofat_candidate_laws": laws,
        "pairwise_interactions": pairwise_interactions(spec, results),
        "lhs_rank_correlations": lhs_correlations(spec, results),
        "refinement": refinement_summary(spec, results),
        "interpretation_guardrails": [
            (
                "All geometry-response laws use the common reference level, "
                "not each case's selected level."
            ),
            (
                "Polynomial expressions are candidate empirical laws only "
                "inside the tested variable range."
            ),
            (
                "OFAT laws hold all other variables at baseline; pairwise "
                "residuals quantify departures from additivity."
            ),
            "Latin-hypercube rank correlations are association measures, not causal derivatives.",
            "A failed L5 case remains unresolved; limits are never relaxed automatically.",
        ],
    }


def render_candidate_laws_markdown(spec: StudySpec, analysis: Mapping[str, Any]) -> str:
    lines = [
        f"# {spec.name}: candidate surface-mesh laws",
        "",
        (
            f"All geometry-response fits below use the common **{spec.reference_level}** "
            "mesh. They are empirical screening laws, valid only over the stated test ranges."
        ),
        "",
        "## Sensitivity ranking",
        "",
        "| rank | variable | score | dominant metric |",
        "|---:|---|---:|---|",
    ]
    ranking = analysis.get("ranking", [])
    if isinstance(ranking, list):
        for row in ranking:
            score = float(row["score"])
            lines.append(
                f"| {row['rank']} | `{row['variable']}` | {score:.6g} | "
                f"`{row.get('dominant_metric') or 'n/a'}` |"
            )
    lines.extend(
        [
            "",
            "The score is the largest common-reference metric response normalized by "
            "its distance to the configured limit; when a limit is unset, the baseline "
            "metric magnitude is used.",
            "",
            "## One-factor candidate laws",
            "",
            "The normalized coordinate `f` is piecewise: `f=-1` is the low bound, "
            "`f=0` is baseline, and `f=+1` is the high bound.",
            "",
            "| variable | metric | tested domain | candidate fit | R² | trend |",
            "|---|---|---|---|---:|---|",
        ]
    )
    ofat = analysis.get("ofat_candidate_laws", {})
    if isinstance(ofat, Mapping):
        for variable_name, variable_data in ofat.items():
            if not isinstance(variable_data, Mapping):
                continue
            domain = variable_data.get("public_domain", [])
            metric_laws = variable_data.get("metric_laws", {})
            if not isinstance(metric_laws, Mapping):
                continue
            for metric_path, law in metric_laws.items():
                if not isinstance(law, Mapping):
                    continue
                fit = law.get("fit_in_normalized_fraction", {})
                if not isinstance(fit, Mapping):
                    continue
                coefficients = list(fit.get("coefficients_ascending", []))
                terms = []
                labels = ("1", "f", "f²")
                for index, coefficient in enumerate(coefficients):
                    terms.append(f"{float(coefficient):+.6g}·{labels[index]}")
                r2 = fit.get("r2")
                r2_text = "n/a" if r2 is None else f"{float(r2):.4f}"
                lines.append(
                    f"| `{variable_name}` | `{metric_path}` | "
                    f"[{float(domain[0]):.6g}, {float(domain[1]):.6g}] "
                    f"{variable_data.get('units', '')} | `{' '.join(terms)}` | "
                    f"{r2_text} | {law.get('trend', 'n/a')} |"
                )
    lines.extend(
        [
            "",
            "## Interaction and refinement interpretation",
            "",
            (
                "- Pairwise interaction residual = measured corner response "
                "minus the two OFAT responses added about baseline."
            ),
            (
                "- The adaptive ladder never changes a metric limit. A case is "
                "unresolved if no configured level passes."
            ),
            (
                "- A pass/fail reversal at a finer level is reported as "
                "non-monotone; coarse selection does not hide it."
            ),
            (
                "- The selected mesh is the coarsest observed passing level; "
                "the common reference remains the comparison basis."
            ),
            "",
            (
                "See `mesh_analysis.json` for pairwise residuals, LHS "
                "correlations, fit coefficients, and transition statistics."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def analyze_workdir(spec: StudySpec, workdir: Path) -> dict[str, Any]:
    from .runner import collect_results, write_json

    results = collect_results(workdir)
    analysis = build_analysis(spec, results)
    output_dir = Path(workdir)
    write_json(output_dir / "mesh_analysis.json", analysis)
    (output_dir / "candidate_mesh_laws.md").write_text(
        render_candidate_laws_markdown(spec, analysis),
        encoding="utf-8",
    )
    ranking_path = output_dir / "sensitivity_ranking.csv"
    with ranking_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["rank", "variable", "units", "score", "dominant_metric", "metric_scores"],
        )
        writer.writeheader()
        for row in analysis["ranking"]:
            writer.writerow(
                {
                    **row,
                    "metric_scores": json.dumps(row["metric_scores"], sort_keys=True),
                }
            )
    return analysis
