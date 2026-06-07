"""
Physics-informed feature engineering for AERIS BWB aero surrogate models.

Design rules:
- No randomness. No state. No fitting. Pure DataFrame → DataFrame transforms.
- Each transform is a named function. apply_feature_engineering() applies all
  active transforms and returns the augmented DataFrame + a manifest.
- Reusable across train, compare, predict — the manifest records exactly which
  transforms were applied so a saved model can reproduce its input space.
- No leakage: all transforms are derived from input columns only, with no
  statistics from held-out data.

Adding a new feature:
1. Write a function _add_<name>(df) -> pd.DataFrame.
2. Register it in FEATURE_TRANSFORMS with a unique key and description.
3. Done — it is automatically included when apply_feature_engineering() runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd


FEATURE_ENGINEERING_SCHEMA_VERSION = "aeris.feature_engineering.v1"


# ---------------------------------------------------------------------------
# Individual transform functions
# Each accepts a DataFrame and returns a new DataFrame with added columns.
# Must not modify the input in place.
# ---------------------------------------------------------------------------

def _add_alpha_sq(df: pd.DataFrame) -> pd.DataFrame:
    """alpha_deg² — captures the quadratic lift and drag trend with AoA."""
    if "alpha_deg" not in df.columns:
        return df
    out = df.copy()
    out["alpha_deg_sq"] = df["alpha_deg"] ** 2
    return out


def _add_abs_alpha(df: pd.DataFrame) -> pd.DataFrame:
    """|alpha_deg| — symmetric nonlinearity proxy for drag."""
    if "alpha_deg" not in df.columns:
        return df
    out = df.copy()
    out["abs_alpha_deg"] = df["alpha_deg"].abs()
    return out


def _add_control_sq(df: pd.DataFrame) -> pd.DataFrame:
    """control_input_deg² — captures symmetric Cm nonlinearity with deflection."""
    if "control_input_deg" not in df.columns:
        return df
    out = df.copy()
    out["control_input_deg_sq"] = df["control_input_deg"] ** 2
    return out


def _add_alpha_x_control(df: pd.DataFrame) -> pd.DataFrame:
    """alpha_deg × control_input_deg — interaction: control effectiveness varies with AoA."""
    if "alpha_deg" not in df.columns or "control_input_deg" not in df.columns:
        return df
    out = df.copy()
    out["alpha_x_control"] = df["alpha_deg"] * df["control_input_deg"]
    return out


def _add_delta_e_sym_sq(df: pd.DataFrame) -> pd.DataFrame:
    """delta_e_sym_deg² — explicit symmetric-elevon nonlinear deflection term."""
    if "delta_e_sym_deg" not in df.columns:
        return df
    out = df.copy()
    out["delta_e_sym_deg_sq"] = df["delta_e_sym_deg"] ** 2
    return out


def _add_alpha_x_delta_e_sym(df: pd.DataFrame) -> pd.DataFrame:
    """alpha_deg × delta_e_sym_deg — explicit symmetric-elevon/AoA interaction."""
    if "alpha_deg" not in df.columns or "delta_e_sym_deg" not in df.columns:
        return df
    out = df.copy()
    out["alpha_x_delta_e_sym"] = df["alpha_deg"] * df["delta_e_sym_deg"]
    return out


def _add_dynamic_pressure_proxy(df: pd.DataFrame) -> pd.DataFrame:
    """velocity_mps² — proportional to dynamic pressure q = ½ρV²; ρ not available."""
    if "velocity_mps" not in df.columns:
        return df
    out = df.copy()
    out["velocity_sq"] = df["velocity_mps"] ** 2
    return out


def _add_aspect_ratio_proxy(df: pd.DataFrame) -> pd.DataFrame:
    """
    (2 * b_total_m)² / (c1_m * 2 * b_total_m) = 2*b_total_m / c1_m.
    Crude AR proxy from available scalar features (no area in feature set).
    Only computed when both columns are present and c1_m > 0.
    """
    if "b_total_m" not in df.columns or "c1_m" not in df.columns:
        return df
    out = df.copy()
    with np.errstate(divide="ignore", invalid="ignore"):
        ar = np.where(df["c1_m"].to_numpy() > 0,
                      2.0 * df["b_total_m"].to_numpy() / df["c1_m"].to_numpy(),
                      np.nan)
    out["ar_proxy"] = ar
    return out


def _add_sweep_alpha_interaction(df: pd.DataFrame) -> pd.DataFrame:
    """sw1_deg × alpha_deg — sweep modulates effective AoA seen by the inner wing."""
    if "sw1_deg" not in df.columns or "alpha_deg" not in df.columns:
        return df
    out = df.copy()
    out["sw1_x_alpha"] = df["sw1_deg"] * df["alpha_deg"]
    return out



def _add_re_number(df):
    """Chord Reynolds number Re = rho(h)*V*c1_m/mu(h) via ISA + Sutherland."""
    required = {"velocity_mps", "altitude_m", "c1_m"}
    if not required.issubset(df.columns):
        return df
    import numpy as _np
    out = df.copy()
    V = df["velocity_mps"].to_numpy(dtype=float)
    h = df["altitude_m"].to_numpy(dtype=float)
    c = df["c1_m"].to_numpy(dtype=float)
    T = _np.clip(288.15 - 0.0065 * h, 216.65, None)
    p = 101325.0 * (T / 288.15) ** 5.2561
    rho = p / (287.058 * T)
    mu = 1.716e-5 * (T / 288.15) ** 1.5 * (288.15 + 110.4) / (T + 110.4)
    re = _np.where((V > 0) & (c > 0), rho * V * c / mu, _np.nan)
    out["re_number"] = _np.maximum(re, 1.0)
    return out

# ---------------------------------------------------------------------------
# Transform registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FeatureTransform:
    key: str
    description: str
    output_columns: tuple[str, ...]
    fn: Callable[[pd.DataFrame], pd.DataFrame]


FEATURE_TRANSFORMS: dict[str, FeatureTransform] = {
    "alpha_sq": FeatureTransform(
        key="alpha_sq",
        description="alpha_deg² — quadratic AoA term for lift/drag nonlinearity",
        output_columns=("alpha_deg_sq",),
        fn=_add_alpha_sq,
    ),
    "abs_alpha": FeatureTransform(
        key="abs_alpha",
        description="|alpha_deg| — symmetric drag proxy",
        output_columns=("abs_alpha_deg",),
        fn=_add_abs_alpha,
    ),
    "control_sq": FeatureTransform(
        key="control_sq",
        description="control_input_deg² — symmetric Cm nonlinearity",
        output_columns=("control_input_deg_sq",),
        fn=_add_control_sq,
    ),
    "alpha_x_control": FeatureTransform(
        key="alpha_x_control",
        description="alpha_deg × control_input_deg — legacy control effectiveness interaction",
        output_columns=("alpha_x_control",),
        fn=_add_alpha_x_control,
    ),
    "delta_e_sym_sq": FeatureTransform(
        key="delta_e_sym_sq",
        description="delta_e_sym_deg² — explicit symmetric-elevon nonlinear deflection term",
        output_columns=("delta_e_sym_deg_sq",),
        fn=_add_delta_e_sym_sq,
    ),
    "alpha_x_delta_e_sym": FeatureTransform(
        key="alpha_x_delta_e_sym",
        description="alpha_deg × delta_e_sym_deg — explicit symmetric-elevon effectiveness interaction",
        output_columns=("alpha_x_delta_e_sym",),
        fn=_add_alpha_x_delta_e_sym,
    ),
    "dynamic_pressure_proxy": FeatureTransform(
        key="dynamic_pressure_proxy",
        description="velocity_mps² — dynamic pressure proxy (ρ not available)",
        output_columns=("velocity_sq",),
        fn=_add_dynamic_pressure_proxy,
    ),
    "aspect_ratio_proxy": FeatureTransform(
        key="aspect_ratio_proxy",
        description="2*b_total_m/c1_m — crude AR proxy from scalar geometry features",
        output_columns=("ar_proxy",),
        fn=_add_aspect_ratio_proxy,
    ),
    "sweep_alpha_interaction": FeatureTransform(
        key="sweep_alpha_interaction",
        description="sw1_deg × alpha_deg — sweep modulates effective AoA",
        output_columns=("sw1_x_alpha",),
        fn=_add_sweep_alpha_interaction,
    ),
    "re_number": FeatureTransform(
        key="re_number",
        description="Chord Reynolds number from ISA atmosphere (velocity_mps, altitude_m, c1_m)",
        output_columns=("re_number",),
        fn=_add_re_number,
    ),
}


def list_transforms() -> list[str]:
    """Return sorted transform keys."""
    return sorted(FEATURE_TRANSFORMS)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def apply_feature_engineering(
    df: pd.DataFrame,
    *,
    transforms: list[str] | None = None,
    manifest_path: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Apply physics-informed feature transforms to df.

    Parameters
    ----------
    df:
        Input DataFrame. Not modified in place.
    transforms:
        List of transform keys to apply. If None, applies all registered
        transforms whose input columns are present in df.
    manifest_path:
        If provided, writes the manifest JSON to this path.

    Returns
    -------
    (augmented_df, manifest)
        augmented_df has all original columns plus new engineered columns.
        manifest records which transforms were applied and which columns were added.
    """
    if transforms is None:
        keys = sorted(FEATURE_TRANSFORMS)
    else:
        unknown = [k for k in transforms if k not in FEATURE_TRANSFORMS]
        if unknown:
            valid = sorted(FEATURE_TRANSFORMS)
            raise ValueError(
                f"Unknown feature transforms: {unknown}. "
                f"Valid keys: {valid}"
            )
        keys = list(transforms)

    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    result = df.copy()

    for key in keys:
        transform = FEATURE_TRANSFORMS[key]
        n_before = len(result.columns)
        result = transform.fn(result)
        n_after = len(result.columns)
        new_cols = list(result.columns[n_before:])

        if new_cols:
            applied.append({
                "key": key,
                "description": transform.description,
                "columns_added": new_cols,
            })
        else:
            skipped.append({
                "key": key,
                "description": transform.description,
                "reason": "required input columns not present in DataFrame",
            })

    manifest: dict[str, Any] = {
        "schema_version": FEATURE_ENGINEERING_SCHEMA_VERSION,
        "n_input_columns": len(df.columns),
        "n_output_columns": len(result.columns),
        "n_engineered_columns": len(result.columns) - len(df.columns),
        "transforms_requested": keys,
        "transforms_applied": applied,
        "transforms_skipped": skipped,
    }

    if manifest_path is not None:
        manifest_path = Path(manifest_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return result, manifest