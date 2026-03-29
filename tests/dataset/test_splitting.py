from __future__ import annotations

import pandas as pd
import pytest

from aeris.dataset.splitting import (
    split_dataset,
    split_dataset_grouped,
    split_dataset_random,
)


def _build_grouped_df() -> pd.DataFrame:
    rows = []
    for geom_id in ["g1", "g2", "g3", "g4", "g5", "g6"]:
        for alpha in [-2.0, 0.0, 4.0]:
            rows.append(
                {
                    "geometry_id": geom_id,
                    "alpha_deg": alpha,
                    "cl": 0.1,
                    "cd": 0.01,
                    "cm": -0.02,
                }
            )
    return pd.DataFrame(rows)


def test_random_split_basic() -> None:
    df = pd.DataFrame({"x": range(20), "y": range(20)})
    split = split_dataset_random(df, random_seed=123)

    assert len(split.train_df) > 0
    assert len(split.val_df) > 0
    assert len(split.test_df) > 0
    assert len(split.train_df) + len(split.val_df) + len(split.test_df) == len(df)


def test_grouped_split_prevents_geometry_leakage() -> None:
    df = _build_grouped_df()
    split = split_dataset_grouped(df, random_seed=123)

    train_groups = set(split.train_df["geometry_id"].unique())
    val_groups = set(split.val_df["geometry_id"].unique())
    test_groups = set(split.test_df["geometry_id"].unique())

    assert train_groups.isdisjoint(val_groups)
    assert train_groups.isdisjoint(test_groups)
    assert val_groups.isdisjoint(test_groups)


def test_grouped_split_requires_group_column() -> None:
    df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})

    with pytest.raises(ValueError, match="requires column 'geometry_id'"):
        split_dataset_grouped(df)


def test_grouped_split_requires_enough_groups() -> None:
    df = pd.DataFrame(
        {
            "geometry_id": ["g1", "g1", "g2", "g2"],
            "x": [1, 2, 3, 4],
        }
    )

    with pytest.raises(ValueError, match="Need at least 3 unique groups"):
        split_dataset_grouped(df)


def test_split_dataset_dispatch_grouped() -> None:
    df = _build_grouped_df()
    split = split_dataset(df, method="grouped", random_seed=123)
    assert split.method == "grouped"


def test_split_dataset_dispatch_random() -> None:
    df = pd.DataFrame({"x": range(12), "y": range(12)})
    split = split_dataset(df, method="random", random_seed=123)
    assert split.method == "random"