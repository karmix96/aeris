from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aeris.ml.manifest import utc_now_iso

MULTIFIDELITY_EVALUATION_SCHEMA_VERSION = "aeris.multifidelity_evaluation_report.v1"


@dataclass(frozen=True)
class MultifidelityEvaluationResult:
    model_run_dir: Path
    output_dir: Path
    report_json: Path
    report_csv: Path
    report: dict[str, Any]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required JSON file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return data


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y_pred - y_true) ** 2)))


def _mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_pred - y_true)))


def _r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    if ss_tot == 0.0:
        return 1.0 if ss_res == 0.0 else 0.0
    return float(1.0 - ss_res / ss_tot)


def _improvement_pct(baseline: float, corrected: float) -> float | None:
    if baseline == 0.0:
        return None
    return float(100.0 * (baseline - corrected) / baseline)


def evaluate_multifidelity_predictions(
    df: pd.DataFrame,
    *,
    base_targets: list[str],
    lf_prefix: str = "lf__",
    hf_prefix: str = "hf__",
    corrected_prefix: str = "pred_corrected__",
) -> dict[str, Any]:
    """Compare LF baseline error against corrected-prediction error."""
    if not base_targets:
        raise ValueError("base_targets must not be empty")

    required: list[str] = []
    for target in base_targets:
        required.extend([f"{lf_prefix}{target}", f"{hf_prefix}{target}", f"{corrected_prefix}{target}"])
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"prediction dataframe is missing required columns: {missing}")

    per_target: dict[str, Any] = {}
    lf_rmse_values: list[float] = []
    corrected_rmse_values: list[float] = []
    lf_mae_values: list[float] = []
    corrected_mae_values: list[float] = []
    lf_r2_values: list[float] = []
    corrected_r2_values: list[float] = []
    improved_targets: list[str] = []
    worsened_targets: list[str] = []
    tied_targets: list[str] = []

    for target in base_targets:
        lf_col = f"{lf_prefix}{target}"
        hf_col = f"{hf_prefix}{target}"
        corr_col = f"{corrected_prefix}{target}"
        values = df[[lf_col, hf_col, corr_col]].apply(pd.to_numeric, errors="coerce")
        arr = values.to_numpy(dtype=float)
        if not np.isfinite(arr).all():
            bad = int((~np.isfinite(arr)).sum())
            raise ValueError(f"target '{target}' contains {bad} non-finite LF/HF/corrected values")

        lf = values[lf_col].to_numpy(dtype=float)
        hf = values[hf_col].to_numpy(dtype=float)
        corrected = values[corr_col].to_numpy(dtype=float)

        lf_rmse = _rmse(hf, lf)
        corrected_rmse = _rmse(hf, corrected)
        lf_mae = _mae(hf, lf)
        corrected_mae = _mae(hf, corrected)
        lf_r2 = _r2(hf, lf)
        corrected_r2 = _r2(hf, corrected)
        rmse_improvement_abs = lf_rmse - corrected_rmse
        mae_improvement_abs = lf_mae - corrected_mae
        rmse_improvement_pct = _improvement_pct(lf_rmse, corrected_rmse)
        mae_improvement_pct = _improvement_pct(lf_mae, corrected_mae)

        if corrected_rmse < lf_rmse:
            status = "improved"
            improved_targets.append(target)
        elif corrected_rmse > lf_rmse:
            status = "worse"
            worsened_targets.append(target)
        else:
            status = "tied"
            tied_targets.append(target)

        per_target[target] = {
            "lf_rmse": lf_rmse,
            "corrected_rmse": corrected_rmse,
            "rmse_improvement_abs": rmse_improvement_abs,
            "rmse_improvement_pct": rmse_improvement_pct,
            "lf_mae": lf_mae,
            "corrected_mae": corrected_mae,
            "mae_improvement_abs": mae_improvement_abs,
            "mae_improvement_pct": mae_improvement_pct,
            "lf_r2": lf_r2,
            "corrected_r2": corrected_r2,
            "status": status,
        }
        lf_rmse_values.append(lf_rmse)
        corrected_rmse_values.append(corrected_rmse)
        lf_mae_values.append(lf_mae)
        corrected_mae_values.append(corrected_mae)
        lf_r2_values.append(lf_r2)
        corrected_r2_values.append(corrected_r2)

    lf_rmse_mean = float(np.mean(lf_rmse_values))
    corrected_rmse_mean = float(np.mean(corrected_rmse_values))
    lf_mae_mean = float(np.mean(lf_mae_values))
    corrected_mae_mean = float(np.mean(corrected_mae_values))
    overall = {
        "n_rows": int(len(df)),
        "n_targets": int(len(base_targets)),
        "lf_rmse_mean": lf_rmse_mean,
        "corrected_rmse_mean": corrected_rmse_mean,
        "rmse_improvement_abs_mean": float(lf_rmse_mean - corrected_rmse_mean),
        "rmse_improvement_pct_mean": _improvement_pct(lf_rmse_mean, corrected_rmse_mean),
        "lf_mae_mean": lf_mae_mean,
        "corrected_mae_mean": corrected_mae_mean,
        "mae_improvement_abs_mean": float(lf_mae_mean - corrected_mae_mean),
        "mae_improvement_pct_mean": _improvement_pct(lf_mae_mean, corrected_mae_mean),
        "lf_r2_mean": float(np.mean(lf_r2_values)),
        "corrected_r2_mean": float(np.mean(corrected_r2_values)),
        "improved_targets": improved_targets,
        "worsened_targets": worsened_targets,
        "tied_targets": tied_targets,
        "n_improved_targets": int(len(improved_targets)),
        "n_worsened_targets": int(len(worsened_targets)),
        "status": "improved" if corrected_rmse_mean < lf_rmse_mean else ("worse" if corrected_rmse_mean > lf_rmse_mean else "tied"),
    }
    return {"overall": overall, "per_target": per_target}


def evaluate_delta_model_run(
    *,
    model_run_dir: str | Path,
    partitions: list[str] | None = None,
    output_dir: str | Path | None = None,
) -> MultifidelityEvaluationResult:
    """Evaluate whether a trained delta model improves LF predictions on saved partitions."""
    model_run_dir = Path(model_run_dir).expanduser().resolve()
    if not model_run_dir.exists() or not model_run_dir.is_dir():
        raise FileNotFoundError(f"Delta model run directory does not exist: {model_run_dir}")

    config = _load_json(model_run_dir / "delta_train_config.json")
    manifest = _load_json(model_run_dir / "delta_model_manifest.json")
    base_targets = list(config.get("base_targets", []))
    if not base_targets:
        raise ValueError("delta_train_config.json does not define base_targets")
    prefixes = config.get("prefixes", {}) or {}
    lf_prefix = str(prefixes.get("lf_prefix", "lf__"))
    hf_prefix = str(prefixes.get("hf_prefix", "hf__"))

    partitions_eff = partitions or ["train", "val", "test"]
    diagnostics_dir = model_run_dir / "diagnostics"
    if output_dir is None:
        output_dir = model_run_dir / "multifidelity_evaluation"
    out_dir = _ensure_dir(Path(output_dir).expanduser().resolve())

    partition_reports: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    for partition in partitions_eff:
        csv_path = diagnostics_dir / f"{partition}_corrected_predictions.csv"
        if not csv_path.exists():
            raise FileNotFoundError(f"Missing corrected predictions CSV for partition '{partition}': {csv_path}")
        df = pd.read_csv(csv_path)
        report = evaluate_multifidelity_predictions(
            df,
            base_targets=base_targets,
            lf_prefix=lf_prefix,
            hf_prefix=hf_prefix,
            corrected_prefix="pred_corrected__",
        )
        partition_reports[partition] = {
            "corrected_predictions_csv": str(csv_path),
            **report,
        }
        overall = report["overall"]
        rows.append({"partition": partition, "target": "__overall__", **overall})
        for target, values in report["per_target"].items():
            rows.append({"partition": partition, "target": target, **values})

    selection_partition = "test" if "test" in partition_reports else partitions_eff[0]
    selected = partition_reports[selection_partition]
    winner_report = {
        "selection_partition": selection_partition,
        "status": selected["overall"]["status"],
        "lf_rmse_mean": selected["overall"]["lf_rmse_mean"],
        "corrected_rmse_mean": selected["overall"]["corrected_rmse_mean"],
        "rmse_improvement_pct_mean": selected["overall"]["rmse_improvement_pct_mean"],
        "n_improved_targets": selected["overall"]["n_improved_targets"],
        "n_worsened_targets": selected["overall"]["n_worsened_targets"],
        "improved_targets": selected["overall"]["improved_targets"],
        "worsened_targets": selected["overall"]["worsened_targets"],
    }

    report_payload = {
        "schema_version": MULTIFIDELITY_EVALUATION_SCHEMA_VERSION,
        "created_at_utc": utc_now_iso(),
        "model_run_dir": str(model_run_dir),
        "delta_model_manifest": str(model_run_dir / "delta_model_manifest.json"),
        "delta_dataset": manifest.get("delta_dataset", {}),
        "model": manifest.get("model", {}),
        "base_targets": base_targets,
        "partitions": partition_reports,
        "winner_report": winner_report,
    }
    report_json = out_dir / "multifidelity_evaluation_report.json"
    report_csv = out_dir / "multifidelity_evaluation_rows.csv"
    report_json.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(report_csv, index=False)

    return MultifidelityEvaluationResult(
        model_run_dir=model_run_dir,
        output_dir=out_dir,
        report_json=report_json,
        report_csv=report_csv,
        report=report_payload,
    )
