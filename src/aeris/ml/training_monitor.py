from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "aeris.training_monitor.v1"


@dataclass(frozen=True)
class TrainingMonitorArtifacts:
    """Artifacts produced by the lightweight ML training monitor."""

    monitor_dir: Path
    report_path: Path
    history_path: Path | None = None
    plots_dir: Path | None = None
    loss_curve_plot_path: Path | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    try:
        import numpy as np

        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
    except Exception:
        pass
    return value


def _inner_estimator(estimator: Any) -> Any:
    steps = getattr(estimator, "named_steps", None)
    if isinstance(steps, dict) and "model" in steps:
        return steps["model"]
    return estimator


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _history_rows_for_estimator(estimator: Any, *, member_id: int | None = None) -> list[dict[str, Any]]:
    """Extract epoch-like history from sklearn-style iterative estimators when available.

    Current AERIS tree/linear models usually have no epoch history. The sklearn
    MLP backend exposes ``loss_curve_`` and sometimes ``validation_scores_``;
    future PyTorch/DL backends can either expose the same fields or call this
    module with compatible rows.
    """

    inner = _inner_estimator(estimator)
    losses = list(getattr(inner, "loss_curve_", []) or [])
    val_scores = list(getattr(inner, "validation_scores_", []) or [])
    if not losses and not val_scores:
        return []

    n_epochs = max(len(losses), len(val_scores))
    rows: list[dict[str, Any]] = []
    for idx in range(n_epochs):
        row: dict[str, Any] = {
            "epoch": idx + 1,
            "member_id": member_id,
            "train_loss": _float_or_none(losses[idx]) if idx < len(losses) else None,
            "validation_score": _float_or_none(val_scores[idx]) if idx < len(val_scores) else None,
        }
        rows.append(row)
    return rows


def _extract_history_rows(model: Any) -> list[dict[str, Any]]:
    estimators = getattr(model, "estimators_", None)
    if isinstance(estimators, list) and estimators:
        rows: list[dict[str, Any]] = []
        for member_id, estimator in enumerate(estimators):
            rows.extend(_history_rows_for_estimator(estimator, member_id=member_id))
        return rows
    return _history_rows_for_estimator(model, member_id=None)


def _write_history_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["epoch", "member_id", "train_loss", "validation_score"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _write_loss_curve_plot(path: Path, rows: list[dict[str, Any]]) -> Path | None:
    usable = [r for r in rows if r.get("train_loss") is not None]
    if not usable:
        return None

    try:
        import matplotlib.pyplot as plt
    except Exception:
        return None

    # Average member losses by epoch for ensemble runs. Single-model runs are unchanged.
    by_epoch: dict[int, list[float]] = {}
    for row in usable:
        epoch = int(row["epoch"])
        loss = _float_or_none(row.get("train_loss"))
        if loss is None:
            continue
        by_epoch.setdefault(epoch, []).append(loss)
    if not by_epoch:
        return None

    epochs = sorted(by_epoch)
    losses = [sum(by_epoch[e]) / len(by_epoch[e]) for e in epochs]

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(epochs, losses, marker="o")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Training loss")
    ax.set_title("Training loss history")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _overall_metric_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for partition in ("train", "val", "test"):
        overall = metrics.get(partition, {}).get("overall")
        if isinstance(overall, dict):
            summary[partition] = {
                "rmse_mean": _float_or_none(overall.get("rmse_mean")),
                "mae_mean": _float_or_none(overall.get("mae_mean")),
                "r2_mean": _float_or_none(overall.get("r2_mean")),
            }
    return summary


def write_training_monitor(
    *,
    model: Any,
    model_type: str,
    metrics: dict[str, Any],
    output_dir: Path,
    target_columns: list[str],
) -> TrainingMonitorArtifacts:
    """Write immediate training-monitor artifacts for an AERIS ML run.

    V1 is intentionally conservative:
    - non-iterative models get an explicit report explaining no epoch history exists;
    - sklearn MLP-style models get ``training_history.csv`` and a loss plot;
    - future PyTorch/DL models can reuse the same schema.
    """

    monitor_dir = Path(output_dir)
    monitor_dir.mkdir(parents=True, exist_ok=True)
    plots_dir = monitor_dir / "plots"
    report_path = monitor_dir / "training_monitor_report.json"

    history_rows = _extract_history_rows(model)
    history_path: Path | None = None
    loss_curve_plot_path: Path | None = None

    if history_rows:
        history_path = monitor_dir / "training_history.csv"
        _write_history_csv(history_path, history_rows)
        loss_curve_plot_path = _write_loss_curve_plot(
            plots_dir / "training_loss_curve.png",
            history_rows,
        )
        monitor_status = "iterative_history_available"
        explanation = (
            "Epoch-like training history was found on the fitted estimator. "
            "For sklearn MLP this is immediate post-training history, not live streaming."
        )
    else:
        monitor_status = "non_iterative_model"
        explanation = (
            "This model does not expose epoch-by-epoch training history. "
            "Use AERIS dataset-size learning curves and repeated grouped CV for trust diagnostics."
        )

    report = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": _utc_now_iso(),
        "status": "completed",
        "monitor_status": monitor_status,
        "model_type": model_type,
        "target_columns": list(target_columns),
        "live_streaming_supported": False,
        "history_available": bool(history_rows),
        "n_history_rows": int(len(history_rows)),
        "explanation": explanation,
        "metrics_summary": _overall_metric_summary(metrics),
        "artifacts": {
            "training_monitor_report_json": str(report_path),
            "training_history_csv": None if history_path is None else str(history_path),
            "plots_dir": str(plots_dir) if loss_curve_plot_path is not None else None,
            "training_loss_curve_png": None if loss_curve_plot_path is None else str(loss_curve_plot_path),
        },
        "recommended_next_diagnostic": (
            "Inspect training_history.csv and training_loss_curve.png for plateau/instability."
            if history_rows
            else "Run `aeris ml learning-curves` for dataset-size learning curves."
        ),
    }

    report_path.write_text(json.dumps(_to_jsonable(report), indent=2), encoding="utf-8")
    return TrainingMonitorArtifacts(
        monitor_dir=monitor_dir,
        report_path=report_path,
        history_path=history_path,
        plots_dir=plots_dir if loss_curve_plot_path is not None else None,
        loss_curve_plot_path=loss_curve_plot_path,
    )
