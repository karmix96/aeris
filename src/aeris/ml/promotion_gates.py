from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from aeris.ml.manifest import utc_now_iso

PROMOTION_GATE_CONFIG_SCHEMA_VERSION = "aeris.model_promotion_gate_config.v1"
PROMOTION_GATE_SUGGESTION_SCHEMA_VERSION = "aeris.model_promotion_gate_suggestions.v1"

_PROFILE_DEFAULTS: dict[str, dict[str, float]] = {
    "strict": {"max_nrmse_iqr": 0.05, "max_mae_iqr": 0.035, "min_r2": 0.95},
    "normal": {"max_nrmse_iqr": 0.10, "max_mae_iqr": 0.070, "min_r2": 0.90},
    "loose": {"max_nrmse_iqr": 0.15, "max_mae_iqr": 0.100, "min_r2": 0.80},
}


@dataclass(frozen=True)
class PromotionGateSuggestionResult:
    model_run_dir: Path
    output_dir: Path
    report_path: Path
    template_path: Path
    report: dict[str, Any]
    template: dict[str, Any]


def _load_json(path: Path, *, required: bool = True) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Missing required JSON file: {path}")
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _write_yaml(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _round_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        value_f = float(value)
    except Exception:
        return None
    if not pd.notna(value_f):
        return None
    return float(f"{value_f:.12g}")


def _read_table_if_exists(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception:
        return None


def _preferred_rows_for_targets(model_run_dir: Path) -> tuple[str | None, pd.DataFrame | None]:
    for partition in ("test", "val", "train"):
        df = _read_table_if_exists(model_run_dir / f"{partition}_rows.csv")
        if df is not None:
            return partition, df
    return None, None


def _target_stats_from_rows(
    *,
    model_run_dir: Path,
    target_columns: list[str],
    min_scale_epsilon: float,
) -> dict[str, dict[str, Any]]:
    partition, df = _preferred_rows_for_targets(model_run_dir)
    stats: dict[str, dict[str, Any]] = {}
    for target in target_columns:
        if df is None or target not in df.columns:
            stats[target] = {
                "source_partition": partition,
                "available": False,
                "n_finite": 0,
                "min": None,
                "max": None,
                "mean": None,
                "std": None,
                "range": None,
                "p05": None,
                "p95": None,
                "p05_p95_range": None,
                "q25": None,
                "q75": None,
                "iqr": None,
                "near_constant": None,
            }
            continue
        series = pd.to_numeric(df[target], errors="coerce").dropna()
        if series.empty:
            stats[target] = {
                "source_partition": partition,
                "available": True,
                "n_finite": 0,
                "min": None,
                "max": None,
                "mean": None,
                "std": None,
                "range": None,
                "p05": None,
                "p95": None,
                "p05_p95_range": None,
                "q25": None,
                "q75": None,
                "iqr": None,
                "near_constant": True,
            }
            continue
        q25 = float(series.quantile(0.25))
        q75 = float(series.quantile(0.75))
        p05 = float(series.quantile(0.05))
        p95 = float(series.quantile(0.95))
        target_range = float(series.max() - series.min())
        iqr = float(q75 - q25)
        std = float(series.std(ddof=0))
        near_constant = bool(iqr <= min_scale_epsilon and std <= min_scale_epsilon and target_range <= min_scale_epsilon)
        stats[target] = {
            "source_partition": partition,
            "available": True,
            "n_finite": int(series.shape[0]),
            "min": _round_float(series.min()),
            "max": _round_float(series.max()),
            "mean": _round_float(series.mean()),
            "std": _round_float(std),
            "range": _round_float(target_range),
            "p05": _round_float(p05),
            "p95": _round_float(p95),
            "p05_p95_range": _round_float(p95 - p05),
            "q25": _round_float(q25),
            "q75": _round_float(q75),
            "iqr": _round_float(iqr),
            "near_constant": near_constant,
        }
    return stats


def _get_target_columns(train_config: dict[str, Any], metrics: dict[str, Any]) -> list[str]:
    configured = train_config.get("target_columns") or []
    if configured:
        return [str(v) for v in configured]
    per_target = metrics.get("test", {}).get("per_target", {})
    if isinstance(per_target, dict):
        return [str(v) for v in per_target.keys()]
    return []


def _target_metric(metrics: dict[str, Any], partition: str, target: str, name: str) -> float | None:
    value = metrics.get(partition, {}).get("per_target", {}).get(target, {}).get(name)
    return _round_float(value)


def _overall_metric(metrics: dict[str, Any], partition: str, name: str) -> float | None:
    value = metrics.get(partition, {}).get("overall", {}).get(name)
    return _round_float(value)


def load_promotion_gate_config(path: str | Path) -> dict[str, Any]:
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Promotion gate config does not exist: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
    else:
        payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ValueError(f"Promotion gate config must contain a mapping/object: {path}")
    targets = payload.get("targets")
    if targets is not None and not isinstance(targets, dict):
        raise ValueError("Promotion gate config 'targets' must be a mapping of target -> gate settings")
    global_cfg = payload.get("global")
    if global_cfg is not None and not isinstance(global_cfg, dict):
        raise ValueError("Promotion gate config 'global' must be a mapping")
    return payload


def _threshold_value(config: dict[str, Any], key: str) -> float | None:
    value = config.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except Exception as exc:
        raise ValueError(f"Gate threshold '{key}' must be numeric or null, got: {value!r}") from exc


def evaluate_promotion_gates(
    *,
    model_run_dir: str | Path,
    gate_config: dict[str, Any],
    min_scale_epsilon: float = 1e-12,
) -> dict[str, Any]:
    model_run_dir = Path(model_run_dir).expanduser().resolve()
    metrics = _load_json(model_run_dir / "metrics.json")
    train_config = _load_json(model_run_dir / "train_config.json")
    target_columns = _get_target_columns(train_config, metrics)
    target_stats = _target_stats_from_rows(
        model_run_dir=model_run_dir,
        target_columns=target_columns,
        min_scale_epsilon=min_scale_epsilon,
    )

    blockers: list[str] = []
    warnings: list[str] = []
    global_results: dict[str, Any] = {}
    target_results: dict[str, Any] = {}

    global_cfg = gate_config.get("global") or {}
    global_thresholds = {
        "max_val_rmse_mean": _threshold_value(global_cfg, "max_val_rmse_mean"),
        "max_test_rmse_mean": _threshold_value(global_cfg, "max_test_rmse_mean"),
        "min_test_r2_mean": _threshold_value(global_cfg, "min_test_r2_mean"),
    }

    global_metric_map = {
        "max_val_rmse_mean": ("val", "rmse_mean", "<="),
        "max_test_rmse_mean": ("test", "rmse_mean", "<="),
        "min_test_r2_mean": ("test", "r2_mean", ">="),
    }
    for threshold_name, threshold_value in global_thresholds.items():
        if threshold_value is None:
            continue
        partition, metric_name, op = global_metric_map[threshold_name]
        current = _overall_metric(metrics, partition, metric_name)
        passed = None
        if current is None:
            blockers.append(f"global gate '{threshold_name}' cannot be checked because {partition}.overall.{metric_name} is missing")
            passed = False
        elif op == "<=" and current > threshold_value:
            blockers.append(f"global gate failed: {partition}.overall.{metric_name}={current} exceeds {threshold_value}")
            passed = False
        elif op == ">=" and current < threshold_value:
            blockers.append(f"global gate failed: {partition}.overall.{metric_name}={current} is below {threshold_value}")
            passed = False
        else:
            passed = True
        global_results[threshold_name] = {
            "metric": f"{partition}.overall.{metric_name}",
            "current": current,
            "threshold": threshold_value,
            "operator": op,
            "passed": passed,
        }

    configured_targets = gate_config.get("targets") or {}
    unknown_targets = sorted(set(configured_targets) - set(target_columns))
    for target in unknown_targets:
        blockers.append(f"target gate configured for unknown target '{target}'")

    for target in target_columns:
        target_cfg = configured_targets.get(target)
        if target_cfg is None:
            continue
        if not isinstance(target_cfg, dict):
            raise ValueError(f"Gate settings for target '{target}' must be a mapping")
        required = bool(target_cfg.get("required", True))
        per_target = metrics.get("test", {}).get("per_target", {}).get(target)
        if per_target is None:
            if required:
                blockers.append(f"target '{target}' is required by gate config but test.per_target metrics are missing")
            else:
                warnings.append(f"target '{target}' has no test.per_target metrics; optional gate skipped")
            target_results[target] = {"required": required, "passed": not required, "checks": {}, "stats": target_stats.get(target)}
            continue

        stats = target_stats.get(target, {})
        checks: dict[str, Any] = {}
        target_blockers_before = len(blockers)

        check_specs = {
            "max_rmse": ("rmse", "<=", _threshold_value(target_cfg, "max_rmse")),
            "max_mae": ("mae", "<=", _threshold_value(target_cfg, "max_mae")),
            "max_abs_error": ("max_abs_error", "<=", _threshold_value(target_cfg, "max_abs_error")),
            "max_error_p95": ("error_p95", "<=", _threshold_value(target_cfg, "max_error_p95")),
            "min_r2": ("r2", ">=", _threshold_value(target_cfg, "min_r2")),
        }
        for gate_name, (metric_name, op, threshold) in check_specs.items():
            if threshold is None:
                continue
            current = _target_metric(metrics, "test", target, metric_name)
            if current is None:
                blockers.append(f"target '{target}' gate '{gate_name}' cannot be checked because test.per_target.{target}.{metric_name} is missing")
                passed = False
            elif op == "<=" and current > threshold:
                blockers.append(f"target '{target}' gate failed: test.{metric_name}={current} exceeds {threshold}")
                passed = False
            elif op == ">=" and current < threshold:
                blockers.append(f"target '{target}' gate failed: test.{metric_name}={current} is below {threshold}")
                passed = False
            else:
                passed = True
            checks[gate_name] = {
                "metric": f"test.per_target.{target}.{metric_name}",
                "current": current,
                "threshold": threshold,
                "operator": op,
                "passed": passed,
            }

        max_nrmse_iqr = _threshold_value(target_cfg, "max_nrmse_iqr")
        if max_nrmse_iqr is not None:
            rmse = _target_metric(metrics, "test", target, "rmse")
            iqr = stats.get("iqr")
            if rmse is None:
                blockers.append(f"target '{target}' max_nrmse_iqr cannot be checked because test.rmse is missing")
                current = None
                passed = False
            elif iqr is None or float(iqr) <= min_scale_epsilon:
                blockers.append(f"target '{target}' max_nrmse_iqr cannot be checked because target IQR is unavailable or near zero")
                current = None
                passed = False
            else:
                current = _round_float(float(rmse) / float(iqr))
                passed = bool(current is not None and current <= max_nrmse_iqr)
                if not passed:
                    blockers.append(f"target '{target}' gate failed: test.rmse/IQR={current} exceeds {max_nrmse_iqr}")
            checks["max_nrmse_iqr"] = {
                "metric": f"test.per_target.{target}.rmse / target_iqr",
                "current": current,
                "threshold": max_nrmse_iqr,
                "operator": "<=",
                "passed": passed,
            }

        max_nrmse_range = _threshold_value(target_cfg, "max_nrmse_range")
        if max_nrmse_range is not None:
            rmse = _target_metric(metrics, "test", target, "rmse")
            target_range = stats.get("range")
            if rmse is None:
                blockers.append(f"target '{target}' max_nrmse_range cannot be checked because test.rmse is missing")
                current = None
                passed = False
            elif target_range is None or float(target_range) <= min_scale_epsilon:
                blockers.append(f"target '{target}' max_nrmse_range cannot be checked because target range is unavailable or near zero")
                current = None
                passed = False
            else:
                current = _round_float(float(rmse) / float(target_range))
                passed = bool(current is not None and current <= max_nrmse_range)
                if not passed:
                    blockers.append(f"target '{target}' gate failed: test.rmse/range={current} exceeds {max_nrmse_range}")
            checks["max_nrmse_range"] = {
                "metric": f"test.per_target.{target}.rmse / target_range",
                "current": current,
                "threshold": max_nrmse_range,
                "operator": "<=",
                "passed": passed,
            }

        target_results[target] = {
            "required": required,
            "passed": len(blockers) == target_blockers_before,
            "metrics": per_target,
            "stats": stats,
            "checks": checks,
        }

    return {
        "schema_version": "aeris.model_promotion_gate_evaluation.v1",
        "created_at_utc": utc_now_iso(),
        "model_run_dir": str(model_run_dir),
        "target_columns": target_columns,
        "passed": len(blockers) == 0,
        "blockers": blockers,
        "warnings": warnings,
        "global": global_results,
        "targets": target_results,
    }


def suggest_promotion_gates(
    *,
    model_run_dir: str | Path,
    output_dir: str | Path | None = None,
    profile: str = "normal",
    min_scale_epsilon: float = 1e-12,
) -> PromotionGateSuggestionResult:
    if profile not in _PROFILE_DEFAULTS:
        raise ValueError(f"Unknown promotion gate suggestion profile '{profile}'. Valid: {sorted(_PROFILE_DEFAULTS)}")

    model_run_dir = Path(model_run_dir).expanduser().resolve()
    if not model_run_dir.exists() or not model_run_dir.is_dir():
        raise FileNotFoundError(f"Model run directory does not exist: {model_run_dir}")
    output_dir = (
        Path(output_dir).expanduser().resolve()
        if output_dir is not None
        else model_run_dir / "promotion_gate_suggestions"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics = _load_json(model_run_dir / "metrics.json")
    train_config = _load_json(model_run_dir / "train_config.json")
    target_columns = _get_target_columns(train_config, metrics)
    stats_by_target = _target_stats_from_rows(
        model_run_dir=model_run_dir,
        target_columns=target_columns,
        min_scale_epsilon=min_scale_epsilon,
    )
    defaults = _PROFILE_DEFAULTS[profile]

    target_templates: dict[str, Any] = {}
    target_suggestions: dict[str, Any] = {}
    warnings: list[str] = []

    for target in target_columns:
        stats = stats_by_target.get(target, {})
        iqr = stats.get("iqr")
        near_constant = bool(stats.get("near_constant"))
        current = {
            "rmse": _target_metric(metrics, "test", target, "rmse"),
            "mae": _target_metric(metrics, "test", target, "mae"),
            "r2": _target_metric(metrics, "test", target, "r2"),
            "error_p95": _target_metric(metrics, "test", target, "error_p95"),
        }

        target_gate: dict[str, Any] = {"required": True}
        rationale: list[str] = []
        if iqr is not None and float(iqr) > min_scale_epsilon:
            target_gate["max_rmse"] = _round_float(float(iqr) * defaults["max_nrmse_iqr"])
            target_gate["max_mae"] = _round_float(float(iqr) * defaults["max_mae_iqr"])
            target_gate["max_nrmse_iqr"] = defaults["max_nrmse_iqr"]
            rationale.append(f"RMSE/MAE gates scaled from target IQR using the '{profile}' profile.")
        else:
            warnings.append(
                f"target '{target}' has unavailable or near-zero IQR; scale-normalized RMSE gates need operator review"
            )
            rationale.append("Target IQR is unavailable or near zero; absolute gates need operator review.")

        if near_constant:
            target_gate["min_r2"] = None
            rationale.append("R² gate disabled because the target is near-constant in the available rows.")
        else:
            target_gate["min_r2"] = defaults["min_r2"]
            rationale.append(f"R² gate set from the '{profile}' profile; adjust for engineering criticality.")

        target_templates[target] = target_gate
        target_suggestions[target] = {
            "target": target,
            "profile": profile,
            "current_test_metrics": current,
            "target_distribution": stats,
            "suggested_gate": target_gate,
            "rationale": rationale,
        }

    template: dict[str, Any] = {
        "schema_version": PROMOTION_GATE_CONFIG_SCHEMA_VERSION,
        "created_at_utc": utc_now_iso(),
        "model_run_dir": str(model_run_dir),
        "profile": profile,
        "global": {
            "max_val_rmse_mean": None,
            "max_test_rmse_mean": None,
            "min_test_r2_mean": None,
        },
        "targets": target_templates,
        "operator_notes": "Review and edit these thresholds before using them for model promotion.",
    }

    evaluation = evaluate_promotion_gates(
        model_run_dir=model_run_dir,
        gate_config=template,
        min_scale_epsilon=min_scale_epsilon,
    )
    report: dict[str, Any] = {
        "schema_version": PROMOTION_GATE_SUGGESTION_SCHEMA_VERSION,
        "created_at_utc": utc_now_iso(),
        "model_run_dir": str(model_run_dir),
        "profile": profile,
        "target_columns": target_columns,
        "global_current_metrics": {
            "val_rmse_mean": _overall_metric(metrics, "val", "rmse_mean"),
            "test_rmse_mean": _overall_metric(metrics, "test", "rmse_mean"),
            "test_r2_mean": _overall_metric(metrics, "test", "r2_mean"),
        },
        "target_suggestions": target_suggestions,
        "template_preview_passes_current_model": evaluation.get("passed"),
        "template_preview_blockers": evaluation.get("blockers", []),
        "warnings": warnings + evaluation.get("warnings", []),
    }

    report_path = _write_json(output_dir / "promotion_gate_suggestions.json", report)
    template_path = _write_yaml(output_dir / "promotion_gates_template.yaml", template)

    return PromotionGateSuggestionResult(
        model_run_dir=model_run_dir,
        output_dir=output_dir,
        report_path=report_path,
        template_path=template_path,
        report=report,
        template=template,
    )
