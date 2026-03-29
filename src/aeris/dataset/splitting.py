from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd


SplitMethod = Literal["random", "grouped"]


@dataclass
class DatasetSplit:
    method: SplitMethod
    random_seed: int
    train_df: pd.DataFrame
    val_df: pd.DataFrame
    test_df: pd.DataFrame
    train_indices: list[int]
    val_indices: list[int]
    test_indices: list[int]
    metadata: dict[str, Any]


def _validate_split_fractions(
    train_fraction: float,
    val_fraction: float,
    test_fraction: float,
) -> None:
    fractions = [train_fraction, val_fraction, test_fraction]
    names = ["train_fraction", "val_fraction", "test_fraction"]

    for name, value in zip(names, fractions):
        if value <= 0.0 or value >= 1.0:
            raise ValueError(f"{name} must be > 0 and < 1. Got {value}.")

    total = train_fraction + val_fraction + test_fraction
    if not np.isclose(total, 1.0, atol=1e-9):
        raise ValueError(
            f"Split fractions must sum to 1.0. "
            f"Got train={train_fraction}, val={val_fraction}, test={test_fraction}, total={total}."
        )


def _slice_by_indices(df: pd.DataFrame, indices: np.ndarray) -> pd.DataFrame:
    return df.iloc[indices].copy()


def split_dataset_random(
    df: pd.DataFrame,
    *,
    train_fraction: float = 0.7,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    random_seed: int = 123,
) -> DatasetSplit:
    _validate_split_fractions(train_fraction, val_fraction, test_fraction)

    if df.empty:
        raise ValueError("Cannot split an empty dataframe.")

    n = len(df)
    if n < 3:
        raise ValueError(f"Need at least 3 rows to create train/val/test splits. Got {n}.")

    rng = np.random.default_rng(random_seed)
    perm = rng.permutation(n)

    n_train = max(1, int(round(n * train_fraction)))
    n_val = max(1, int(round(n * val_fraction)))
    n_test = n - n_train - n_val

    if n_test < 1:
        n_test = 1
        if n_train >= n_val and n_train > 1:
            n_train -= 1
        elif n_val > 1:
            n_val -= 1
        else:
            raise ValueError("Could not allocate at least one row to each split.")

    train_idx = perm[:n_train]
    val_idx = perm[n_train:n_train + n_val]
    test_idx = perm[n_train + n_val:]

    train_df = _slice_by_indices(df, train_idx)
    val_df = _slice_by_indices(df, val_idx)
    test_df = _slice_by_indices(df, test_idx)

    metadata = {
        "n_rows_total": n,
        "n_rows_train": len(train_df),
        "n_rows_val": len(val_df),
        "n_rows_test": len(test_df),
    }

    return DatasetSplit(
        method="random",
        random_seed=random_seed,
        train_df=train_df,
        val_df=val_df,
        test_df=test_df,
        train_indices=train_idx.tolist(),
        val_indices=val_idx.tolist(),
        test_indices=test_idx.tolist(),
        metadata=metadata,
    )


def split_dataset_grouped(
    df: pd.DataFrame,
    *,
    group_column: str = "geometry_id",
    train_fraction: float = 0.7,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    random_seed: int = 123,
) -> DatasetSplit:
    _validate_split_fractions(train_fraction, val_fraction, test_fraction)

    if df.empty:
        raise ValueError("Cannot split an empty dataframe.")

    if group_column not in df.columns:
        raise ValueError(
            f"Grouped split requires column '{group_column}', but it is missing."
        )

    unique_groups = df[group_column].dropna().unique()
    n_groups = len(unique_groups)

    if n_groups < 3:
        raise ValueError(
            f"Need at least 3 unique groups for grouped train/val/test split. "
            f"Got {n_groups} unique '{group_column}' values."
        )

    rng = np.random.default_rng(random_seed)
    shuffled_groups = rng.permutation(unique_groups)

    n_train_groups = max(1, int(round(n_groups * train_fraction)))
    n_val_groups = max(1, int(round(n_groups * val_fraction)))
    n_test_groups = n_groups - n_train_groups - n_val_groups

    if n_test_groups < 1:
        n_test_groups = 1
        if n_train_groups >= n_val_groups and n_train_groups > 1:
            n_train_groups -= 1
        elif n_val_groups > 1:
            n_val_groups -= 1
        else:
            raise ValueError("Could not allocate at least one group to each split.")

    train_groups = set(shuffled_groups[:n_train_groups])
    val_groups = set(shuffled_groups[n_train_groups:n_train_groups + n_val_groups])
    test_groups = set(shuffled_groups[n_train_groups + n_val_groups:])

    train_mask = df[group_column].isin(train_groups)
    val_mask = df[group_column].isin(val_groups)
    test_mask = df[group_column].isin(test_groups)

    train_idx = np.flatnonzero(train_mask.to_numpy())
    val_idx = np.flatnonzero(val_mask.to_numpy())
    test_idx = np.flatnonzero(test_mask.to_numpy())

    train_df = _slice_by_indices(df, train_idx)
    val_df = _slice_by_indices(df, val_idx)
    test_df = _slice_by_indices(df, test_idx)

    overlap = (
        train_groups.intersection(val_groups)
        | train_groups.intersection(test_groups)
        | val_groups.intersection(test_groups)
    )
    if overlap:
        raise RuntimeError(f"Grouped split leakage detected across groups: {sorted(overlap)}")

    metadata = {
        "group_column": group_column,
        "n_rows_total": len(df),
        "n_rows_train": len(train_df),
        "n_rows_val": len(val_df),
        "n_rows_test": len(test_df),
        "n_groups_total": n_groups,
        "n_groups_train": len(train_groups),
        "n_groups_val": len(val_groups),
        "n_groups_test": len(test_groups),
        "train_groups": sorted(str(x) for x in train_groups),
        "val_groups": sorted(str(x) for x in val_groups),
        "test_groups": sorted(str(x) for x in test_groups),
    }

    return DatasetSplit(
        method="grouped",
        random_seed=random_seed,
        train_df=train_df,
        val_df=val_df,
        test_df=test_df,
        train_indices=train_idx.tolist(),
        val_indices=val_idx.tolist(),
        test_indices=test_idx.tolist(),
        metadata=metadata,
    )


def split_dataset(
    df: pd.DataFrame,
    *,
    method: SplitMethod = "grouped",
    group_column: str = "geometry_id",
    train_fraction: float = 0.7,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    random_seed: int = 123,
) -> DatasetSplit:
    if method == "random":
        return split_dataset_random(
            df,
            train_fraction=train_fraction,
            val_fraction=val_fraction,
            test_fraction=test_fraction,
            random_seed=random_seed,
        )

    if method == "grouped":
        return split_dataset_grouped(
            df,
            group_column=group_column,
            train_fraction=train_fraction,
            val_fraction=val_fraction,
            test_fraction=test_fraction,
            random_seed=random_seed,
        )

    raise ValueError(f"Unsupported split method: {method}")