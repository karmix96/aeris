"""
Config helpers for AERIS ML experiments.

This module keeps ML experiment definitions reproducible and file-backed. The
CLI can still accept explicit options for quick smoke runs, but serious work
should use YAML configs and JSON model-parameter files so runs are repeatable.
"""

from __future__ import annotations

import json
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
        return [str(x).strip() for x in value if str(x).strip()]
    raise TypeError(
        f"ML config field '{field_name}' must be a list or comma-separated string."
    )


def _mapping_from_value(value: Any, *, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError(f"ML config field '{field_name}' must be a mapping/dict.")
    return dict(value)


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
    feature_preset: str | None = None
    feature_set: str | None = None


def load_ml_experiment_config(config_path: str | Path) -> MLExperimentConfig:
    """Load a single-model ML training config from YAML."""
    raw = load_yaml_config(config_path)
    ml = raw.get("ml", raw)
    if not isinstance(ml, dict):
        raise ValueError("ML config must contain a mapping at top-level or under 'ml'.")

    dataset = ml.get("dataset") or ml.get("dataset_path")
    if not dataset:
        raise ValueError("ML config requires 'dataset' or 'dataset_path'.")

    features = _list_from_value(
        ml.get("features") or ml.get("feature_columns"),
        field_name="features",
    )
    targets = _list_from_value(
        ml.get("targets") or ml.get("target_columns"),
        field_name="targets",
    )
    # ML-BUG-02/03: config may drive features via exactly one of
    # features / feature_preset / feature_set (mirrors the CLI contract).
    feature_preset_cfg = ml.get("feature_preset")
    feature_set_cfg = ml.get("feature_set")
    feature_preset_cfg = str(feature_preset_cfg).strip() if feature_preset_cfg else None
    feature_set_cfg = str(feature_set_cfg).strip() if feature_set_cfg else None
    _n_feature_sources = sum(
        1 for _v in (bool(features), bool(feature_preset_cfg), bool(feature_set_cfg)) if _v
    )
    if _n_feature_sources == 0:
        raise ValueError(
            "ML config requires exactly one of: features, feature_preset, feature_set."
        )
    if _n_feature_sources > 1:
        raise ValueError(
            "ML config must set exactly one of features, feature_preset, feature_set (not several)."
        )
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
        model_params=_mapping_from_value(
            model.get("params", ml.get("model_params", {})) or {},
            field_name="model.params",
        ),
        output_dir=None if output_dir_raw is None else Path(output_dir_raw),
        feature_preset=feature_preset_cfg,
        feature_set=feature_set_cfg,
    )


def load_json_mapping(path: str | Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    json_path = Path(path).expanduser().resolve()
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")
    if not json_path.is_file():
        raise ValueError(f"JSON path is not a file: {json_path}")
    if json_path.suffix.lower() != ".json":
        raise ValueError(f"Expected a .json file: {json_path}")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object/mapping: {json_path}")
    return payload


def load_model_params_json(path: str | Path) -> dict[str, Any]:
    """Load flat model parameters for one model run."""
    return load_json_mapping(path)


def load_model_params_by_type_json(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load per-model parameter mappings for compare runs.

    Expected layout:

    ```json
    {
      "random_forest": {"n_estimators": 300},
      "gradient_boosting": {"n_estimators": 200}
    }
    ```

    A top-level `models` wrapper is also accepted.
    """
    payload = load_json_mapping(path)
    raw = payload.get("models", payload)
    if not isinstance(raw, dict):
        raise ValueError("Compare model-params JSON must contain a mapping.")

    out: dict[str, dict[str, Any]] = {}
    for model_type, params in raw.items():
        if params is None:
            out[str(model_type)] = {}
        elif isinstance(params, dict):
            out[str(model_type)] = dict(params)
        else:
            raise ValueError(
                f"Parameters for model '{model_type}' must be a mapping/dict."
            )
    return out
