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


def test_manifest_consistency():
    df, manifest = load()
    assert len(df) == manifest["successful_aero_rows"]


def test_no_nan_targets():
    df, _ = load()
    for t in ["cl", "cd", "cm"]:
        assert not df[t].isna().any()


def test_control_diagnostics_all_true():
    df, _ = load()

    cols = [
        "geometry_declares_controls",
        "airplane_has_controls",
        "diag_airplane_has_control_surfaces",
        "diag_airplane_avl_has_control_blocks",
        "diag_keystrokes_has_d1_command",
    ]

    for c in cols:
        if c in df.columns:
            assert df[c].astype(bool).all()


def test_control_effectiveness_not_zero():
    df, _ = load()

    group_cols = ["geometry_id", "alpha_deg", "velocity_mps", "altitude_m"]

    for _, g in df.groupby(group_cols):
        ctrls = sorted(g["control_input_deg"].tolist())

        if ctrls == [-5.0, 0.0, 5.0]:
            g = g.sort_values("control_input_deg")

            assert len(set(np.round(g["cl"], 8))) > 1
            assert len(set(np.round(g["cm"], 8))) > 1


def test_grid_complete():
    df, _ = load()

    expected = (
        df["geometry_id"].nunique()
        * df["alpha_deg"].nunique()
        * df["velocity_mps"].nunique()
        * df["altitude_m"].nunique()
        * df["control_input_deg"].nunique()
    )

    assert len(df) == expected