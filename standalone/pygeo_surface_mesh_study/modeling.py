"""Validated response surfaces and agent-facing mesh-law artifacts."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.stats import beta as beta_distribution

from .spec import MetricLimit, StudySpec

MODEL_SCHEMA = "aeris.pygeo_surface_mesh_agent_law.v1"
_COMPOSITE_MARGIN_PATH = "acceptance.minimum_normalized_margin"


def _case(result: Mapping[str, Any]) -> Mapping[str, Any]:
    value = result.get("case", {})
    return value if isinstance(value, Mapping) else {}


def _attempt_metrics(
    result: Mapping[str, Any],
    level_name: str,
) -> Mapping[str, float]:
    attempts = result.get("attempts", [])
    if not isinstance(attempts, list):
        return {}
    for attempt in attempts:
        if not isinstance(attempt, Mapping) or attempt.get("level") != level_name:
            continue
        acceptance = attempt.get("acceptance", {})
        if not isinstance(acceptance, Mapping):
            return {}
        metrics = acceptance.get("flat_metrics", {})
        return metrics if isinstance(metrics, Mapping) else {}
    return {}


def _minimum_normalized_margin(
    spec: StudySpec,
    metrics: Mapping[str, float],
) -> float | None:
    margins = []
    for metric in spec.metric_limits:
        if not metric.enabled or metric.limit is None or metric.path not in metrics:
            continue
        value = float(metrics[metric.path])
        scale = max(abs(float(metric.limit)), abs(value), 1.0e-12)
        if metric.operator == "<=":
            margins.append((float(metric.limit) - value) / scale)
        else:
            margins.append((value - float(metric.limit)) / scale)
    return min(margins) if margins else None


def _response_value(
    spec: StudySpec,
    metrics: Mapping[str, float],
    metric_path: str,
) -> float | None:
    if metric_path == _COMPOSITE_MARGIN_PATH:
        return _minimum_normalized_margin(spec, metrics)
    value = metrics.get(metric_path)
    if not isinstance(value, (int, float, np.number)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


@dataclass(frozen=True)
class Basis:
    matrix: np.ndarray
    names: tuple[str, ...]
    linear_columns: tuple[int, ...]
    quadratic_columns: tuple[int, ...]
    pair_columns: dict[tuple[int, int], int]


def orthonormal_quadratic_basis(
    normalized: np.ndarray,
    variable_names: Sequence[str],
) -> Basis:
    """Second-order tensor Legendre basis orthonormal for U[-1, 1] factors."""

    x = np.asarray(normalized, dtype=float)
    if x.ndim != 2 or x.shape[1] != len(variable_names):
        raise ValueError("normalized design matrix has the wrong shape")
    if np.any(~np.isfinite(x)) or np.any(np.abs(x) > 1.0 + 1.0e-10):
        raise ValueError("normalized design must be finite and within [-1, 1]")

    phi1 = math.sqrt(3.0) * x
    phi2 = math.sqrt(5.0) * 0.5 * (3.0 * x**2 - 1.0)
    columns = [np.ones(len(x))]
    names = ["intercept"]
    linear_columns = []
    quadratic_columns = []
    for index, name in enumerate(variable_names):
        linear_columns.append(len(columns))
        columns.append(phi1[:, index])
        names.append(f"L1({name})")
    for index, name in enumerate(variable_names):
        quadratic_columns.append(len(columns))
        columns.append(phi2[:, index])
        names.append(f"L2({name})")
    pair_columns: dict[tuple[int, int], int] = {}
    for first in range(len(variable_names)):
        for second in range(first + 1, len(variable_names)):
            pair_columns[(first, second)] = len(columns)
            columns.append(phi1[:, first] * phi1[:, second])
            names.append(f"L1({variable_names[first]})*L1({variable_names[second]})")
    return Basis(
        matrix=np.column_stack(columns),
        names=tuple(names),
        linear_columns=tuple(linear_columns),
        quadratic_columns=tuple(quadratic_columns),
        pair_columns=pair_columns,
    )


def _ridge_coefficients(matrix: np.ndarray, values: np.ndarray, penalty: float) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=float)
    values = np.asarray(values, dtype=float)
    gram = matrix.T @ matrix
    regularizer = np.eye(matrix.shape[1]) * float(penalty)
    regularizer[0, 0] = 0.0
    right = matrix.T @ values
    try:
        return np.linalg.solve(gram + regularizer, right)
    except np.linalg.LinAlgError:
        augmented_matrix = np.vstack([matrix, np.sqrt(regularizer)])
        augmented_values = np.concatenate([values, np.zeros(matrix.shape[1])])
        return np.linalg.lstsq(augmented_matrix, augmented_values, rcond=None)[0]


def _ridge_cross_validation(
    matrix: np.ndarray,
    values: np.ndarray,
    lambdas: Sequence[float],
    folds: int,
    seed: int,
) -> tuple[float, dict[str, float]]:
    n_rows = len(values)
    folds = max(2, min(int(folds), n_rows))
    order = np.random.default_rng(seed).permutation(n_rows)
    fold_id = np.empty(n_rows, dtype=int)
    fold_id[order] = np.arange(n_rows) % folds
    scores: dict[str, float] = {}
    for penalty in lambdas:
        squared_errors = []
        for fold in range(folds):
            test = fold_id == fold
            train = ~test
            coefficient = _ridge_coefficients(matrix[train], values[train], penalty)
            squared_errors.extend(((values[test] - matrix[test] @ coefficient) ** 2).tolist())
        scores[f"{float(penalty):.12g}"] = float(np.sqrt(np.mean(squared_errors)))
    chosen = min((float(key) for key in scores), key=lambda value: (scores[f"{value:.12g}"], value))
    return chosen, scores


def _normalized_rows(
    spec: StudySpec,
    results: Sequence[Mapping[str, Any]],
    stage: str,
    level_name: str,
    metric_path: str,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    x_rows = []
    y_rows = []
    case_ids = []
    for result in results:
        case = _case(result)
        if case.get("stage") != stage:
            continue
        public = case.get("public_values", {})
        if not isinstance(public, Mapping):
            continue
        metrics = _attempt_metrics(result, level_name)
        response = _response_value(spec, metrics, metric_path)
        if response is None:
            continue
        try:
            x_row = [
                variable.normalized_fraction(float(public[variable.name]))
                for variable in spec.variables
            ]
        except (KeyError, TypeError, ValueError):
            continue
        x_rows.append(x_row)
        y_rows.append(response)
        case_ids.append(str(case.get("case_id", "")))
    if not x_rows:
        return np.empty((0, len(spec.variables))), np.empty(0), []
    return np.asarray(x_rows, dtype=float), np.asarray(y_rows, dtype=float), case_ids


def _quality_statistics(
    actual: np.ndarray, predicted: np.ndarray, scale_source: np.ndarray
) -> dict[str, float | None]:
    residual = actual - predicted
    rmse = float(np.sqrt(np.mean(residual**2)))
    mae = float(np.mean(np.abs(residual)))
    total = float(np.sum((actual - np.mean(actual)) ** 2))
    r2 = None if total <= 1.0e-30 else float(1.0 - np.sum(residual**2) / total)
    robust_scale = float(np.percentile(scale_source, 95.0) - np.percentile(scale_source, 5.0))
    if robust_scale <= 1.0e-15:
        robust_scale = max(float(np.ptp(scale_source)), abs(float(np.mean(scale_source))), 1.0)
    return {
        "rmse": rmse,
        "mae": mae,
        "max_absolute_error": float(np.max(np.abs(residual))),
        "normalized_rmse": rmse / robust_scale,
        "r2": r2,
    }


def _sobol_from_coefficients(
    coefficient: np.ndarray,
    basis: Basis,
    variable_names: Sequence[str],
) -> dict[str, Any]:
    variance = float(np.sum(np.asarray(coefficient[1:], dtype=float) ** 2))
    first = np.zeros(len(variable_names))
    total = np.zeros(len(variable_names))
    second: dict[str, float] = {}
    if variance > 1.0e-30:
        for index, _name in enumerate(variable_names):
            contribution = (
                coefficient[basis.linear_columns[index]] ** 2
                + coefficient[basis.quadratic_columns[index]] ** 2
            )
            first[index] = contribution / variance
            total[index] = first[index]
        for (first_index, second_index), column in basis.pair_columns.items():
            contribution = float(coefficient[column] ** 2 / variance)
            total[first_index] += contribution
            total[second_index] += contribution
            second[f"{variable_names[first_index]}__{variable_names[second_index]}"] = contribution
    return {
        "surrogate_variance": variance,
        "first_order": {name: float(first[index]) for index, name in enumerate(variable_names)},
        "total_effect": {name: float(total[index]) for index, name in enumerate(variable_names)},
        "second_order": second,
        "interaction_fraction": float(max(0.0, 1.0 - np.sum(first))),
    }


def _bootstrap_sobol_intervals(
    matrix: np.ndarray,
    values: np.ndarray,
    coefficient: np.ndarray,
    penalty: float,
    basis: Basis,
    variable_names: Sequence[str],
    replicates: int,
    seed: int,
) -> dict[str, Any] | None:
    """Residual-bootstrap intervals for surrogate-derived sensitivity indices."""

    if replicates < 2:
        return None
    gram = matrix.T @ matrix
    regularizer = np.eye(matrix.shape[1]) * float(penalty)
    regularizer[0, 0] = 0.0
    try:
        linear_operator = np.linalg.solve(gram + regularizer, matrix.T)
    except np.linalg.LinAlgError:
        return None
    fitted = matrix @ coefficient
    residual = values - fitted
    residual = residual - np.mean(residual)
    rng = np.random.default_rng(seed)
    sampled = rng.choice(residual, size=(len(residual), replicates), replace=True)
    boot_coefficients = linear_operator @ (fitted[:, None] + sampled)

    first_samples = {name: [] for name in variable_names}
    total_samples = {name: [] for name in variable_names}
    for column in range(replicates):
        indices = _sobol_from_coefficients(boot_coefficients[:, column], basis, variable_names)
        for name in variable_names:
            first_samples[name].append(indices["first_order"][name])
            total_samples[name].append(indices["total_effect"][name])

    def interval(values: Sequence[float]) -> list[float]:
        return [
            float(np.percentile(values, 2.5)),
            float(np.percentile(values, 97.5)),
        ]

    return {
        "method": "fixed-design residual bootstrap of validated ridge surrogate",
        "replicates": replicates,
        "confidence_level": 0.95,
        "first_order_intervals": {name: interval(values) for name, values in first_samples.items()},
        "total_effect_intervals": {
            name: interval(values) for name, values in total_samples.items()
        },
        "interpretation": (
            "Finite-design/surrogate uncertainty only; the deterministic mesher "
            "has no fitted aleatory-noise term."
        ),
    }


def _classification_audit(
    metric: MetricLimit,
    actual: np.ndarray,
    predicted: np.ndarray,
    absolute_error_bound: float,
) -> dict[str, Any] | None:
    if metric.limit is None:
        return None
    if metric.operator == "<=":
        predicted_pass = predicted + absolute_error_bound <= metric.limit
        actual_pass = actual <= metric.limit
    else:
        predicted_pass = predicted - absolute_error_bound >= metric.limit
        actual_pass = actual >= metric.limit
    false_accept = predicted_pass & ~actual_pass
    false_reject = ~predicted_pass & actual_pass
    false_accept_count = int(np.sum(false_accept))
    predicted_pass_count = int(np.sum(predicted_pass))
    if predicted_pass_count == 0:
        false_accept_rate = None
        false_accept_upper_95 = None
    elif false_accept_count == predicted_pass_count:
        false_accept_rate = 1.0
        false_accept_upper_95 = 1.0
    else:
        false_accept_rate = false_accept_count / predicted_pass_count
        false_accept_upper_95 = float(
            beta_distribution.ppf(
                0.95,
                false_accept_count + 1,
                predicted_pass_count - false_accept_count,
            )
        )
    return {
        "conservative_prediction": True,
        "false_accepts": false_accept_count,
        "false_rejects": int(np.sum(false_reject)),
        "actual_passes": int(np.sum(actual_pass)),
        "predicted_passes": predicted_pass_count,
        "false_accept_rate_among_predicted_passes": false_accept_rate,
        "false_accept_probability_upper_95": false_accept_upper_95,
        "false_accept_upper_method": "one-sided exact Clopper-Pearson",
        "samples": int(len(actual)),
    }


def _analysis_settings(spec: StudySpec) -> dict[str, Any]:
    model = spec.analysis_config.get("global_model", {})
    validation = spec.analysis_config.get("validation", {})
    if not isinstance(model, Mapping) or not isinstance(validation, Mapping):
        raise TypeError("analysis.global_model and analysis.validation must be mappings")
    return {
        "folds": int(model.get("cv_folds", 10)),
        "lambdas": [
            float(value) for value in model.get("ridge_lambdas", [0.0, 1.0e-6, 1.0e-2, 1.0])
        ],
        "coverage": float(model.get("conformal_coverage", 0.99)),
        "max_nrmse": float(validation.get("max_normalized_rmse", 0.05)),
        "min_r2": float(validation.get("minimum_r2", 0.90)),
        "max_false_accepts": int(validation.get("maximum_false_accepts", 0)),
        "max_false_accept_upper_95": float(
            validation.get("maximum_false_accept_probability_upper_95", 0.02)
        ),
        "bootstrap_replicates": int(model.get("bootstrap_replicates", 0)),
    }


def fit_response_model(
    spec: StudySpec,
    results: Sequence[Mapping[str, Any]],
    level_name: str,
    metric: MetricLimit,
) -> dict[str, Any] | None:
    """Fit one pre-registered quadratic law and audit it on held-out cases."""

    x_train, y_train, train_ids = _normalized_rows(
        spec, results, "global_train", level_name, metric.path
    )
    x_validation, y_validation, validation_ids = _normalized_rows(
        spec, results, "validation", level_name, metric.path
    )
    variable_names = [variable.name for variable in spec.variables]
    required_columns = 1 + 2 * len(variable_names) + math.comb(len(variable_names), 2)
    if len(y_train) < required_columns + 1 or len(y_validation) < 20:
        return None
    training_complete = bool(
        len(y_train) == spec.global_train_samples
        and len(set(train_ids)) == spec.global_train_samples
    )
    validation_complete = bool(
        len(y_validation) == spec.validation_samples
        and len(set(validation_ids)) == spec.validation_samples
    )

    settings = _analysis_settings(spec)
    train_basis = orthonormal_quadratic_basis(x_train, variable_names)
    validation_basis = orthonormal_quadratic_basis(x_validation, variable_names)
    penalty, cv_scores = _ridge_cross_validation(
        train_basis.matrix,
        y_train,
        settings["lambdas"],
        settings["folds"],
        spec.global_train_seed,
    )
    coefficient = _ridge_coefficients(train_basis.matrix, y_train, penalty)
    predicted_validation = validation_basis.matrix @ coefficient

    split = max(10, len(y_validation) // 2)
    calibration_residual = np.abs(y_validation[:split] - predicted_validation[:split])
    target_coverage = min(1.0, max(0.0, settings["coverage"]))
    calibration_rank = min(split, max(1, math.ceil((split + 1) * target_coverage)))
    ordered_calibration_residual = np.sort(calibration_residual)
    absolute_error_bound = float(ordered_calibration_residual[calibration_rank - 1])
    audit_actual = y_validation[split:]
    audit_predicted = predicted_validation[split:]
    statistics = _quality_statistics(audit_actual, audit_predicted, y_train)
    coverage = float(np.mean(np.abs(audit_actual - audit_predicted) <= absolute_error_bound))

    classification = _classification_audit(
        metric,
        audit_actual,
        audit_predicted,
        absolute_error_bound,
    )
    r2 = statistics["r2"]
    classification_safe = bool(
        classification is None
        or (
            classification["false_accepts"] <= settings["max_false_accepts"]
            and (
                classification["predicted_passes"] == 0
                or classification["false_accept_probability_upper_95"]
                <= settings["max_false_accept_upper_95"]
            )
        )
    )
    sensitivity_intervals = None
    if level_name == spec.reference_level:
        sensitivity_intervals = _bootstrap_sobol_intervals(
            train_basis.matrix,
            y_train,
            coefficient,
            penalty,
            train_basis,
            variable_names,
            settings["bootstrap_replicates"],
            spec.global_train_seed + 17,
        )

    deployable = bool(
        training_complete
        and validation_complete
        and statistics["normalized_rmse"] <= settings["max_nrmse"]
        and r2 is not None
        and r2 >= settings["min_r2"]
        and coverage >= settings["coverage"] - 0.02
        and classification_safe
    )
    return {
        "level": level_name,
        "response": metric.path,
        "operator": metric.operator,
        "limit": metric.limit,
        "basis": {
            "family": "orthonormal Legendre, total degree 2",
            "factor_distribution": "independent uniform over registered bounds",
            "feature_names": list(train_basis.names),
            "coefficients": [float(value) for value in coefficient],
        },
        "regularization": {
            "method": "ridge",
            "selected_lambda": penalty,
            "cross_validation_rmse": cv_scores,
            "folds": settings["folds"],
        },
        "sample_counts": {
            "training": len(y_train),
            "training_expected": spec.global_train_samples,
            "validation_total": len(y_validation),
            "validation_expected": spec.validation_samples,
            "training_complete": training_complete,
            "validation_complete": validation_complete,
            "calibration": split,
            "audit": len(audit_actual),
        },
        "validation": {
            **statistics,
            "absolute_error_bound": absolute_error_bound,
            "calibration_method": "split conformal absolute residual",
            "calibration_rank": calibration_rank,
            "reference_measure": ("independent uniform factors over the registered hyperrectangle"),
            "target_coverage": settings["coverage"],
            "audit_coverage": coverage,
            "classification": classification,
            "audit_case_ids": validation_ids[split:],
        },
        "sobol_indices_from_validated_surrogate": _sobol_from_coefficients(
            coefficient, train_basis, variable_names
        ),
        "sensitivity_confidence_intervals": sensitivity_intervals,
        "deployable": deployable,
        "training_case_ids_hash": hashlib.sha256("\n".join(train_ids).encode("utf-8")).hexdigest(),
    }


def _composite_metric() -> MetricLimit:
    return MetricLimit(
        path=_COMPOSITE_MARGIN_PATH,
        operator=">=",
        limit=0.0,
        enabled=True,
        description="Worst normalized signed acceptance margin; pass when >= 0",
    )


def _flatten_numeric(value: object, prefix: str = "") -> dict[str, float]:
    output: dict[str, float] = {}
    if isinstance(value, Mapping):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            output.update(_flatten_numeric(child, path))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            path = f"{prefix}[{index}]"
            output.update(_flatten_numeric(child, path))
    elif isinstance(value, (int, float, np.number)) and not isinstance(value, bool):
        number = float(value)
        if math.isfinite(number):
            output[prefix] = number
    return output


def _descriptor_domain(
    results: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, float]]:
    observed: dict[str, list[float]] = {}
    for result in results:
        if _case(result).get("stage") != "global_train":
            continue
        geometry = result.get("geometry", {})
        descriptors = geometry.get("descriptors", {}) if isinstance(geometry, Mapping) else {}
        for path, value in _flatten_numeric(descriptors).items():
            observed.setdefault(path, []).append(value)
    return {
        path: {"observed_minimum": min(values), "observed_maximum": max(values)}
        for path, values in sorted(observed.items())
        if values
    }


def _campaign_completeness(
    spec: StudySpec,
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected = {case.case_id: case for case in spec.all_cases()}
    observed: dict[str, Mapping[str, Any]] = {}
    duplicate_case_ids: list[str] = []
    unidentifiable_results = 0
    for result in results:
        case_id = str(_case(result).get("case_id", ""))
        if not case_id:
            unidentifiable_results += 1
        elif case_id in observed:
            duplicate_case_ids.append(case_id)
        else:
            observed[case_id] = result

    missing = sorted(set(expected) - set(observed))
    unexpected = sorted(set(observed) - set(expected))
    identity_mismatches: list[str] = []
    invalid_statuses: dict[str, str] = {}
    geometry_missing: list[str] = []
    incomplete_level_ladders: dict[str, dict[str, list[str]]] = {}
    attempt_errors: list[str] = []
    expected_levels = {level.name for level in spec.levels}
    valid_statuses = {"complete", "limits_unresolved"}

    for case_id in sorted(set(expected) & set(observed)):
        result = observed[case_id]
        if result.get("case_identity_hash") != expected[case_id].identity_hash:
            identity_mismatches.append(case_id)
        status = str(result.get("status", "missing"))
        if status not in valid_statuses:
            invalid_statuses[case_id] = status
        if not isinstance(result.get("geometry"), Mapping):
            geometry_missing.append(case_id)
        attempts = result.get("attempts", [])
        attempted_levels = (
            {str(attempt.get("level")) for attempt in attempts if isinstance(attempt, Mapping)}
            if isinstance(attempts, list)
            else set()
        )
        if attempted_levels != expected_levels:
            incomplete_level_ladders[case_id] = {
                "missing": sorted(expected_levels - attempted_levels),
                "extra": sorted(attempted_levels - expected_levels),
            }
        if isinstance(attempts, list):
            attempt_errors.extend(
                f"{case_id}:{attempt.get('level')}"
                for attempt in attempts
                if isinstance(attempt, Mapping) and attempt.get("error") is not None
            )

    blockers = bool(
        missing
        or unexpected
        or duplicate_case_ids
        or unidentifiable_results
        or identity_mismatches
        or invalid_statuses
        or geometry_missing
        or incomplete_level_ladders
        or attempt_errors
    )
    return {
        "complete": not blockers,
        "expected_cases": len(expected),
        "observed_expected_cases": len(set(expected) & set(observed)),
        "missing_case_ids": missing,
        "unexpected_case_ids": unexpected,
        "duplicate_case_ids": sorted(set(duplicate_case_ids)),
        "unidentifiable_results": unidentifiable_results,
        "identity_mismatch_case_ids": identity_mismatches,
        "invalid_statuses": invalid_statuses,
        "geometry_missing_case_ids": geometry_missing,
        "incomplete_level_ladders": incomplete_level_ladders,
        "attempt_errors": attempt_errors,
    }


def build_agent_law(
    spec: StudySpec,
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the portable law contract; never mark an unvalidated law deployable."""

    metrics = [metric for metric in spec.metric_limits if metric.enabled]
    if not spec.unset_enabled_limits():
        metrics.append(_composite_metric())
    models: dict[str, Any] = {}
    for level in spec.levels:
        level_models = {}
        for metric in metrics:
            model = fit_response_model(spec, results, level.name, metric)
            if model is not None:
                level_models[metric.path] = model
        models[level.name] = level_models

    baseline = next(
        (
            result
            for result in results
            if _case(result).get("stage") == "baseline"
            and isinstance(result.get("geometry"), Mapping)
        ),
        None,
    )
    baseline_geometry = baseline.get("geometry", {}) if baseline is not None else {}
    airfoils = (
        baseline_geometry.get("airfoils", {}) if isinstance(baseline_geometry, Mapping) else {}
    )
    completeness = _campaign_completeness(spec, results)
    descriptor_domain = _descriptor_domain(results)
    configured_airfoils = (
        airfoils.get("configured_stations", {}) if isinstance(airfoils, Mapping) else {}
    )
    oml_topology = spec.mesh_common.get("oml_topology")
    tip_topology = spec.mesh_common.get("tip_topology")
    applicability_contract_complete = bool(
        isinstance(configured_airfoils, Mapping)
        and len(configured_airfoils) == 4
        and descriptor_domain
        and oml_topology
        and tip_topology
    )
    required_model_count = len(spec.levels) * len(metrics)
    fitted = [model for level in models.values() for model in level.values()]
    deployment_ready = bool(
        not spec.unset_enabled_limits()
        and completeness["complete"]
        and applicability_contract_complete
        and len(fitted) == required_model_count
        and all(model.get("deployable", False) for model in fitted)
    )

    reference_models = models.get(spec.reference_level, {})
    influence = {}
    for path, model in reference_models.items():
        total = model["sobol_indices_from_validated_surrogate"]["total_effect"]
        influence[path] = sorted(
            ({"variable": name, "total_effect": float(value)} for name, value in total.items()),
            key=lambda row: row["total_effect"],
            reverse=True,
        )

    return {
        "schema": MODEL_SCHEMA,
        "study": spec.name,
        "campaign_completeness": completeness,
        "deployment_ready": deployment_ready,
        "deployment_blockers": {
            "unset_limits": spec.unset_enabled_limits(),
            "missing_or_failed_models": required_model_count
            - sum(bool(model.get("deployable", False)) for model in fitted),
            "campaign_incomplete": not completeness["complete"],
            "applicability_contract_incomplete": not applicability_contract_complete,
        },
        "factor_contract": {
            variable.name: {
                "sample_field": variable.sample_field,
                "units": variable.units,
                "baseline": variable.baseline,
                "low": variable.low,
                "high": variable.high,
                "description": variable.description,
            }
            for variable in spec.variables
        },
        "fixed_sample_values": dict(spec.fixed_sample_values),
        "airfoil_signature": airfoils,
        "realised_descriptor_domain": descriptor_domain,
        "applicability": {
            "inside_registered_hyperrectangle_required": True,
            "exact_airfoil_signature_required": True,
            "topology": {
                "oml": oml_topology,
                "tip": tip_topology,
            },
            "descriptor_envelope_interpretation": (
                "Observed global-training envelope for out-of-distribution diagnostics; "
                "the registered factor bounds remain the hard applicability gate."
            ),
            "warning": (
                "Reject extrapolation. Fixed-airfoil data do not identify an "
                "independent thickness-ratio effect."
            ),
        },
        "mesh_levels": {
            level.name: {
                "order": level.order,
                "points_per_block_side": level.points_per_block_side,
                "spanwise_panels_per_section": level.spanwise_panels_per_section,
                "cap_wrap_points": level.cap_wrap_points,
                "tip_radial_points": level.tip_radial_points,
            }
            for level in spec.levels
        },
        "selection_rule": (
            "Choose the coarsest level whose conservative bound passes every "
            "metric; generate and measure the mesh; on failure, use the next "
            "predicted passing level. Never substitute prediction for QC."
        ),
        "models": models,
        "reference_level_total_effect_rankings": influence,
    }
