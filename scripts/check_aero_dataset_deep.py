from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--cl-alpha-tol", type=float, default=-1e-6)
    p.add_argument("--min-cm-control-slope-mag", type=float, default=1e-5)
    p.add_argument("--outlier-sigma", type=float, default=5.0)
    return p.parse_args()


def load_dataset(dataset: Path) -> tuple[pd.DataFrame, dict]:
    csv_path = dataset / "aero_dataset.csv"
    manifest_path = dataset / "aero_dataset_manifest.json"

    if not csv_path.exists():
        raise FileNotFoundError(f"Missing CSV: {csv_path}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")

    df = pd.read_csv(csv_path)
    manifest = json.loads(manifest_path.read_text())

    return df, manifest


def require_columns(df: pd.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise RuntimeError(f"Missing required columns: {missing}")


def check_per_geometry_grid_complete(df: pd.DataFrame) -> None:
    print("\n[CHECK] Per-geometry grid completeness")

    global_alpha = sorted(df["alpha_deg"].unique())
    global_vel = sorted(df["velocity_mps"].unique())
    global_alt = sorted(df["altitude_m"].unique())
    global_ctrl = sorted(df["control_input_deg"].unique())

    expected_per_geom = len(global_alpha) * len(global_vel) * len(global_alt) * len(global_ctrl)

    bad = []
    for geom_id, g in df.groupby("geometry_id"):
        n = len(g)
        if n != expected_per_geom:
            bad.append((geom_id, n, expected_per_geom))

    if bad:
        raise RuntimeError(f"Incomplete geometry grids found: {bad[:10]}")

    print(f"✔ every geometry has {expected_per_geom} rows")


def check_zero_control_exists_once(df: pd.DataFrame) -> None:
    print("\n[CHECK] Exactly one zero-control row per condition group")

    group_cols = ["geometry_id", "alpha_deg", "velocity_mps", "altitude_m"]

    bad = []
    for name, g in df.groupby(group_cols):
        n_zero = int((g["control_input_deg"] == 0.0).sum())
        if n_zero != 1:
            bad.append((name, n_zero))

    if bad:
        raise RuntimeError(f"Zero-control multiplicity errors: {bad[:10]}")

    print("✔ exactly one control_input_deg = 0 row per group")


def check_cl_vs_alpha_monotonic(df: pd.DataFrame, tol: float) -> None:
    print("\n[CHECK] CL vs alpha monotonicity")

    group_cols = ["geometry_id", "velocity_mps", "altitude_m", "control_input_deg"]
    bad = []

    for name, g in df.groupby(group_cols):
        g = g.sort_values("alpha_deg")
        alphas = g["alpha_deg"].to_numpy()
        cls = g["cl"].to_numpy()

        if len(alphas) < 2:
            continue

        dcl = np.diff(cls)
        # For the current low-alpha dataset, CL should generally increase with alpha.
        if np.any(dcl < tol):
            bad.append((name, dcl.tolist(), cls.tolist()))

    if bad:
        print("First few failures:")
        for item in bad[:5]:
            print(item)
        raise RuntimeError(f"Found {len(bad)} CL-vs-alpha non-monotonic groups")

    print("✔ CL increases with alpha across all tested groups")


def check_cm_vs_control_has_effect(df: pd.DataFrame, min_slope_mag: float) -> None:
    print("\n[CHECK] Cm responds to control")

    group_cols = ["geometry_id", "alpha_deg", "velocity_mps", "altitude_m"]
    bad = []

    for name, g in df.groupby(group_cols):
        g = g.sort_values("control_input_deg")

        x = g["control_input_deg"].to_numpy()
        y = g["cm"].to_numpy()

        if len(x) < 2:
            continue

        coeffs = np.polyfit(x, y, deg=1)
        slope = float(coeffs[0])

        if abs(slope) < min_slope_mag:
            bad.append((name, slope, y.tolist()))

    if bad:
        print("First few failures:")
        for item in bad[:5]:
            print(item)
        raise RuntimeError(f"Found {len(bad)} near-zero Cm-vs-control groups")

    print("✔ Cm changes meaningfully with control input")


def check_control_symmetry_reasonableness(df: pd.DataFrame) -> None:
    print("\n[CHECK] Control increment symmetry reasonableness")

    group_cols = ["geometry_id", "alpha_deg", "velocity_mps", "altitude_m"]
    bad = []

    for name, g in df.groupby(group_cols):
        if set(np.round(g["control_input_deg"], 8)) != {-5.0, 0.0, 5.0}:
            continue

        g = g.sort_values("control_input_deg")

        cl_m5 = float(g[g["control_input_deg"] == -5.0]["cl"].iloc[0])
        cl_0 = float(g[g["control_input_deg"] == 0.0]["cl"].iloc[0])
        cl_p5 = float(g[g["control_input_deg"] == 5.0]["cl"].iloc[0])

        cm_m5 = float(g[g["control_input_deg"] == -5.0]["cm"].iloc[0])
        cm_0 = float(g[g["control_input_deg"] == 0.0]["cm"].iloc[0])
        cm_p5 = float(g[g["control_input_deg"] == 5.0]["cm"].iloc[0])

        dcl_neg = cl_0 - cl_m5
        dcl_pos = cl_p5 - cl_0
        dcm_neg = cm_0 - cm_m5
        dcm_pos = cm_p5 - cm_0

        # Not demanding exact symmetry, just reject pathological asymmetry.
        if max(abs(dcl_neg), abs(dcl_pos)) > 0:
            ratio_cl = abs(dcl_neg - dcl_pos) / max(abs(dcl_neg), abs(dcl_pos))
            if ratio_cl > 0.75:
                bad.append(("cl", name, dcl_neg, dcl_pos, ratio_cl))

        if max(abs(dcm_neg), abs(dcm_pos)) > 0:
            ratio_cm = abs(dcm_neg - dcm_pos) / max(abs(dcm_neg), abs(dcm_pos))
            if ratio_cm > 0.75:
                bad.append(("cm", name, dcm_neg, dcm_pos, ratio_cm))

    if bad:
        print("First few suspect groups:")
        for item in bad[:5]:
            print(item)
        raise RuntimeError(f"Found {len(bad)} strongly asymmetric control-response groups")

    print("✔ control-response asymmetry is within a sane range")


def check_outliers(df: pd.DataFrame, sigma: float) -> None:
    print("\n[CHECK] Global outlier scan")

    targets = ["cl", "cd", "cm"]
    bad = []

    for t in targets:
        x = df[t].to_numpy(dtype=float)
        mu = float(np.mean(x))
        sd = float(np.std(x))
        if sd == 0:
            continue
        z = np.abs((x - mu) / sd)
        idx = np.where(z > sigma)[0]
        for i in idx[:20]:
            bad.append((t, int(i), float(x[i]), float(z[i])))

    if bad:
        print("First few outliers:")
        for item in bad[:10]:
            print(item)
        raise RuntimeError(f"Detected {len(bad)} outlier rows beyond {sigma} sigma")

    print(f"✔ no extreme outliers beyond {sigma} sigma")


def check_basic_physical_ranges(df: pd.DataFrame) -> None:
    print("\n[CHECK] Basic physical range sanity")

    if (df["cd"] <= 0).any():
        raise RuntimeError("Found non-positive CD values")
    if (df["cl"].abs() > 5).any():
        raise RuntimeError("Found absurd CL magnitude > 5")
    if (df["cm"].abs() > 5).any():
        raise RuntimeError("Found absurd Cm magnitude > 5")

    print("✔ no obvious absurd coefficient magnitudes")


def main():
    args = parse_args()
    df, manifest = load_dataset(args.dataset)

    require_columns(
        df,
        [
            "geometry_id",
            "alpha_deg",
            "velocity_mps",
            "altitude_m",
            "control_input_deg",
            "cl",
            "cd",
            "cm",
        ],
    )

    print(f"DATASET: {args.dataset}")
    print(f"ROWS: {len(df)}")
    print(f"MANIFEST SUCCESS ROWS: {manifest['successful_aero_rows']}")

    if len(df) != manifest["successful_aero_rows"]:
        raise RuntimeError("CSV row count does not match manifest")

    check_per_geometry_grid_complete(df)
    check_zero_control_exists_once(df)
    check_cl_vs_alpha_monotonic(df, tol=args.cl_alpha_tol)
    check_cm_vs_control_has_effect(df, min_slope_mag=args.min_cm_control_slope_mag)
    check_control_symmetry_reasonableness(df)
    check_outliers(df, sigma=args.outlier_sigma)
    check_basic_physical_ranges(df)

    print("\n=== DEEP DATASET VALIDATION PASSED ===")


if __name__ == "__main__":
    main()