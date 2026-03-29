from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


DATASET = Path("data/datasets/aero_dataset_demo_v3")


if not DATASET.exists():
    pytest.skip(
        "Artifact-dependent dataset test skipped: data/datasets/aero_dataset_demo_v3 not found.",
        allow_module_level=True,
    )


def load():
    df = pd.read_csv(DATASET / "aero_dataset.csv")
    manifest = json.loads((DATASET / "aero_dataset_manifest.json").read_text())
    return df, manifest


def test_row_count_matches_manifest():
    df, manifest = load()
    assert len(df) == manifest["successful_aero_rows"]


def test_per_geometry_grid_complete():
    df, _ = load()

    expected_per_geom = (
        df["alpha_deg"].nunique()
        * df["velocity_mps"].nunique()
        * df["altitude_m"].nunique()
        * df["control_input_deg"].nunique()
    )

    counts = df.groupby("geometry_id").size()
    assert (counts == expected_per_geom).all()


def test_exactly_one_zero_control_row_per_condition_group():
    df, _ = load()

    group_cols = ["geometry_id", "alpha_deg", "velocity_mps", "altitude_m"]
    counts = (
        df.assign(is_zero=(df["control_input_deg"] == 0.0))
        .groupby(group_cols)["is_zero"]
        .sum()
    )
    assert (counts == 1).all()


def test_cl_increases_with_alpha():
    df, _ = load()

    group_cols = ["geometry_id", "velocity_mps", "altitude_m", "control_input_deg"]

    for _, g in df.groupby(group_cols):
        g = g.sort_values("alpha_deg")
        dcl = np.diff(g["cl"].to_numpy())
        assert (dcl >= -1e-6).all()


def test_cm_changes_with_control():
    df, _ = load()

    group_cols = ["geometry_id", "alpha_deg", "velocity_mps", "altitude_m"]

    for _, g in df.groupby(group_cols):
        g = g.sort_values("control_input_deg")
        x = g["control_input_deg"].to_numpy()
        y = g["cm"].to_numpy()
        slope = np.polyfit(x, y, deg=1)[0]
        assert abs(slope) > 1e-5


def test_no_extreme_global_outliers():
    df, _ = load()

    for t in ["cl", "cd", "cm"]:
        x = df[t].to_numpy(dtype=float)
        z = np.abs((x - x.mean()) / x.std())
        assert (z <= 5.0).all()


def test_basic_physical_ranges():
    df, _ = load()

    assert (df["cd"] > 0).all()
    assert (df["cl"].abs() <= 5).all()
    assert (df["cm"].abs() <= 5).all()