from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aeris.dataset.promoted_dataset import require_promoted_aero_dataset


@dataclass
class TrainingData:
    df: pd.DataFrame
    X: pd.DataFrame
    y: pd.DataFrame
    feature_columns: list[str]
    target_columns: list[str]
    metadata: dict[str, Any]


def load_training_data(
    dataset_path: Path,
    feature_columns: list[str],
    target_columns: list[str],
    *,
    allow_forced: bool = False,
    drop_non_finite: bool = True,
) -> TrainingData:
    """
    Load a promoted aero dataset and prepare ML-ready tabular data.

    Rules enforced:
    - dataset must pass the promoted-dataset gate
    - curated_aero_dataset.csv must exist
    - requested feature/target columns must exist
    - optional non-finite rows are dropped from X/y
    """
    dataset_path = Path(dataset_path).expanduser().resolve()

    promoted_info = require_promoted_aero_dataset(
        dataset_root=dataset_path,
        allow_forced=allow_forced,
    )

    curated_path = dataset_path / "curated_aero_dataset.csv"
    if not curated_path.exists():
        raise FileNotFoundError(
            f"Missing curated dataset CSV: {curated_path}"
        )

    df = pd.read_csv(curated_path)

    if df.empty:
        raise ValueError(f"Curated dataset is empty: {curated_path}")

    if not feature_columns:
        raise ValueError("feature_columns must not be empty.")

    if not target_columns:
        raise ValueError("target_columns must not be empty.")

    missing_features = [col for col in feature_columns if col not in df.columns]
    missing_targets = [col for col in target_columns if col not in df.columns]

    if missing_features:
        raise ValueError(
            f"Missing feature columns: {missing_features}. "
            f"Available columns: {list(df.columns)}"
        )

    if missing_targets:
        raise ValueError(
            f"Missing target columns: {missing_targets}. "
            f"Available columns: {list(df.columns)}"
        )

    X = df[feature_columns].copy()
    y = df[target_columns].copy()

    dropped_rows = 0
    if drop_non_finite:
        finite_mask = np.isfinite(X.to_numpy(dtype=float)).all(axis=1) & np.isfinite(
            y.to_numpy(dtype=float)
        ).all(axis=1)

        dropped_rows = int((~finite_mask).sum())

        if dropped_rows > 0:
            df = df.loc[finite_mask].copy()
            X = X.loc[finite_mask].copy()
            y = y.loc[finite_mask].copy()

    if df.empty:
        raise ValueError("No valid rows remain after filtering non-finite values.")

    metadata = {
        "dataset_path": str(dataset_path),
        "curated_csv_path": str(curated_path),
        "n_samples": int(len(df)),
        "n_features": int(len(feature_columns)),
        "n_targets": int(len(target_columns)),
        "feature_columns": list(feature_columns),
        "target_columns": list(target_columns),
        "dropped_non_finite_rows": dropped_rows,
        "promotion_context": promoted_info,
    }

    return TrainingData(
        df=df,
        X=X,
        y=y,
        feature_columns=list(feature_columns),
        target_columns=list(target_columns),
        metadata=metadata,
    )