from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    return p.parse_args()


def check_manifest(df, manifest):
    print("\n[CHECK] Manifest consistency")

    assert len(df) == manifest["successful_aero_rows"], \
        "Row count mismatch with manifest"

    print("✔ row count matches manifest")


def check_diagnostics(df):
    print("\n[CHECK] Control-surface diagnostics")

    cols = [
        "geometry_declares_controls",
        "airplane_has_controls",
        "diag_airplane_has_control_surfaces",
        "diag_airplane_avl_has_control_blocks",
        "diag_keystrokes_has_d1_command",
    ]

    for c in cols:
        if c in df.columns:
            if not df[c].astype(bool).all():
                raise RuntimeError(f"{c} has False values")
            print(f"✔ {c} all True")

    if "diag_stdout_control_variables" in df.columns:
        if not (df["diag_stdout_control_variables"] > 0).all():
            raise RuntimeError("AVL did not detect control variables")
        print("✔ AVL stdout reports control variables")


def check_control_effectiveness(df):
    print("\n[CHECK] Control effectiveness")

    group_cols = ["geometry_id", "alpha_deg", "velocity_mps", "altitude_m"]

    bad = 0

    for name, g in df.groupby(group_cols):
        ctrls = sorted(g["control_input_deg"].tolist())

        if ctrls == [-5.0, 0.0, 5.0]:
            g = g.sort_values("control_input_deg")

            cl_vals = g["cl"].values
            cm_vals = g["cm"].values

            if len(set(np.round(cl_vals, 8))) == 1:
                bad += 1
            if len(set(np.round(cm_vals, 8))) == 1:
                bad += 1

    if bad > 0:
        raise RuntimeError(f"{bad} cases show no control effect")

    print("✔ control affects CL and Cm")


def check_cardinality(df):
    print("\n[CHECK] Dataset cardinality")

    n_geom = df["geometry_id"].nunique()
    n_alpha = df["alpha_deg"].nunique()
    n_vel = df["velocity_mps"].nunique()
    n_alt = df["altitude_m"].nunique()
    n_ctrl = df["control_input_deg"].nunique()

    expected = n_geom * n_alpha * n_vel * n_alt * n_ctrl

    assert len(df) == expected, "Dataset grid is incomplete"

    print(f"✔ grid complete: {expected} rows")


def check_nan(df):
    print("\n[CHECK] NaNs")

    targets = ["cl", "cd", "cm"]

    for t in targets:
        if df[t].isna().any():
            raise RuntimeError(f"NaNs in {t}")

    print("✔ no NaNs in targets")


def main():
    args = parse_args()

    dataset = args.dataset
    df = pd.read_csv(dataset / "aero_dataset.csv")
    manifest = json.loads((dataset / "aero_dataset_manifest.json").read_text())

    print(f"\nDATASET: {dataset}")
    print(f"ROWS: {len(df)}")

    check_manifest(df, manifest)
    check_diagnostics(df)
    check_control_effectiveness(df)
    check_cardinality(df)
    check_nan(df)

    print("\n=== DATASET VALIDATION PASSED ===")


if __name__ == "__main__":
    main()