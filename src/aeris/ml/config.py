"""
Config helpers for future config-driven ML experiments.

This first version validates the common schema but does not force all CLI paths
to use YAML yet. It is intentionally conservative so we can adopt it command by
command without breaking the current interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aeris.common.config import load_yaml_config


def _list_from_value(value: Any, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    if isinstance(value, list):
        out = [str(x).strip() for x in value if str(x).strip()]
        return out
    raise TypeError(f"ML config field '{field_name}' must be a list or comma-separated string.")


@dataclass(frozen=True)
class MLExperimentConfig:
    dataset_path: Path
    feature_columns: list[str]
    target_columns: list[str]
    model_type: str = "linear_regression"
    split_method: str = "grouped"
    group_column: str = "geometry_id"
    train_fraction: float = 0.7
    val_fraction: float = 0.15
    test_fraction: float = 0.15
    random_seed: int = 123
    allow_forced: bool = False
    model_params: dict[str, Any] = field(default_factory=dict)
    output_dir: Path | None = None


def load_ml_experiment_config(config_path: str | Path) -> MLExperimentConfig:
    raw = load_yaml_config(config_path)
    ml = raw.get("ml", raw)
    if not isinstance(ml, dict):
        raise ValueError("ML config must contain a mapping at top-level or under 'ml'.")

    dataset = ml.get("dataset") or ml.get("dataset_path")
    if not dataset:
        raise ValueError("ML config requires 'dataset' or 'dataset_path'.")

    features = _list_from_value(ml.get("features") or ml.get("feature_columns"), field_name="features")
    targets = _list_from_value(ml.get("targets") or ml.get("target_columns"), field_name="targets")
    if not features:
        raise ValueError("ML config requires non-empty features.")
    if not targets:
        raise ValueError("ML config requires non-empty targets.")

    split = ml.get("split", {}) or {}
    model = ml.get("model", {}) or {}
    if not isinstance(split, dict):
        raise TypeError("ML config field 'split' must be a mapping.")
    if not isinstance(model, dict):
        raise TypeError("ML config field 'model' must be a mapping.")

    output_dir_raw = ml.get("output_dir")

    return MLExperimentConfig(
        dataset_path=Path(dataset),
        feature_columns=features,
        target_columns=targets,
        model_type=str(model.get("type") or ml.get("model_type") or "linear_regression"),
        split_method=str(split.get("method") or ml.get("split_method") or "grouped"),
        group_column=str(split.get("group_column") or ml.get("group_column") or "geometry_id"),
        train_fraction=float(split.get("train_fraction", ml.get("train_fraction", 0.7))),
        val_fraction=float(split.get("val_fraction", ml.get("val_fraction", 0.15))),
        test_fraction=float(split.get("test_fraction", ml.get("test_fraction", 0.15))),
        random_seed=int(split.get("random_seed", ml.get("random_seed", 123))),
        allow_forced=bool(ml.get("allow_forced", False)),
        model_params=dict(model.get("params", ml.get("model_params", {})) or {}),
        output_dir=None if output_dir_raw is None else Path(output_dir_raw),
    )
