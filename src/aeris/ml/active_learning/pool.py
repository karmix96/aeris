"""Active-learning candidate pool generation. AERIS_ML_W3_POOL_V1

Generates a Latin-Hypercube pool of RAW design/condition rows inside (or a
controlled expansion of) the model's training design space. Decision columns
are the feature set's SOURCE columns (engineered columns are recomputed at
scoring/inference time by the feature-set machinery, never sampled
independently). Bounds come from training_envelope.json (promotion artifact)
with an explicit train_rows.csv fallback, and every bound's provenance is
recorded in the pool manifest.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aeris.ml.fingerprints import file_sha256
from aeris.ml.manifest import utc_now_iso


@dataclass
class DesignSpace:
    source_columns: list[str]
    bounds: dict[str, dict[str, Any]]  # col -> {min, max, source}
    train_config: dict[str, Any]
    feature_set_name: str | None


@dataclass
class PoolResult:
    pool_csv_path: Path
    manifest_path: Path
    columns: list[str]
    n_samples: int
    bounds: dict[str, dict[str, Any]]
    fixed: dict[str, float]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_design_space(model_run_dir: str | Path) -> DesignSpace:
    """Resolve raw decision columns + per-column bounds for a trained run."""
    run = Path(model_run_dir).expanduser().resolve()
    train_config = _load_json(run / "train_config.json")

    from aeris.ml.feature_set_inference import trained_feature_set_name_from_config

    fs_name = trained_feature_set_name_from_config(train_config)
    if fs_name:
        from aeris.ml.feature_sets import get_feature_set

        source_columns = list(get_feature_set(fs_name).required_source_columns)
    else:
        source_columns = list(train_config.get("feature_columns", []))
    if not source_columns:
        raise ValueError(
            "Could not resolve raw decision columns from train_config.json "
            f"in {run} (feature_set={fs_name!r})."
        )

    env_path = run / "training_envelope.json"
    env_ranges: dict[str, Any] = {}
    if env_path.exists():
        env_ranges = _load_json(env_path).get("feature_ranges", {}) or {}

    fallback_df: pd.DataFrame | None = None
    bounds: dict[str, dict[str, Any]] = {}
    for col in source_columns:
        item = env_ranges.get(col, {}) or {}
        lo, hi = item.get("min"), item.get("max")
        if lo is not None and hi is not None and np.isfinite([lo, hi]).all():
            bounds[col] = {"min": float(lo), "max": float(hi), "source": "training_envelope"}
            continue
        if fallback_df is None:
            rows = run / "train_rows.csv"
            if not rows.exists():
                raise FileNotFoundError(
                    f"No envelope range for '{col}' and no train_rows.csv fallback in {run}. "
                    "Promote the model (writes training_envelope.json) or keep train_rows.csv."
                )
            fallback_df = pd.read_csv(rows)
        if col not in fallback_df.columns:
            raise ValueError(f"Decision column '{col}' missing from train_rows.csv fallback.")
        series = pd.to_numeric(fallback_df[col], errors="coerce")
        lo_f, hi_f = float(series.min()), float(series.max())
        if not np.isfinite([lo_f, hi_f]).all():
            raise ValueError(f"Non-finite fallback bounds for '{col}'.")
        bounds[col] = {"min": lo_f, "max": hi_f, "source": "train_rows_min_max"}
    return DesignSpace(source_columns, bounds, train_config, fs_name)


def _expanded(lo: float, hi: float, frac: float) -> tuple[float, float]:
    width = hi - lo
    return lo - frac * width, hi + frac * width


def generate_candidate_pool(
    *,
    model_run_dir: str | Path,
    n_samples: int = 2000,
    seed: int = 123,
    expand_frac: float = 0.0,
    fixed: dict[str, float] | None = None,
    output_dir: str | Path | None = None,
) -> PoolResult:
    """Write an LHS candidate pool CSV + provenance manifest."""
    if n_samples < 1:
        raise ValueError("n_samples must be >= 1")
    if expand_frac < 0.0:
        raise ValueError("expand_frac must be >= 0")
    fixed = dict(fixed or {})

    run = Path(model_run_dir).expanduser().resolve()
    space = resolve_design_space(run)
    unknown = sorted(set(fixed) - set(space.source_columns))
    if unknown:
        raise ValueError(f"--fix columns not in design space: {unknown}")

    free_cols = [c for c in space.source_columns if c not in fixed]
    from scipy.stats import qmc

    data: dict[str, np.ndarray] = {}
    if free_cols:
        sampler = qmc.LatinHypercube(d=len(free_cols), seed=seed)
        unit = sampler.random(n=n_samples)
        lo = np.array([_expanded(space.bounds[c]["min"], space.bounds[c]["max"], expand_frac)[0] for c in free_cols])
        hi = np.array([_expanded(space.bounds[c]["min"], space.bounds[c]["max"], expand_frac)[1] for c in free_cols])
        scaled = qmc.scale(unit, lo, hi)
        for i, c in enumerate(free_cols):
            data[c] = scaled[:, i]
    for c, v in fixed.items():
        data[c] = np.full(n_samples, float(v), dtype=float)

    df = pd.DataFrame({c: data[c] for c in space.source_columns})
    out = Path(output_dir).expanduser().resolve() if output_dir else run / "active_learning" / "candidate_pool"
    out.mkdir(parents=True, exist_ok=True)
    pool_csv = out / "candidate_pool.csv"
    df.to_csv(pool_csv, index=False)

    manifest = {
        "schema_version": "aeris.al_candidate_pool.v1",
        "created_utc": utc_now_iso(),
        "model_run_dir": str(run),
        "feature_set_name": space.feature_set_name,
        "columns": space.source_columns,
        "n_samples": int(n_samples),
        "seed": int(seed),
        "expand_frac": float(expand_frac),
        "fixed": {k: float(v) for k, v in fixed.items()},
        "bounds": space.bounds,
        "pool_csv_sha256": file_sha256(pool_csv),
        "note": (
            "Raw source columns only; engineered features are recomputed by the "
            "feature-set machinery at scoring/inference time."
        ),
    }
    manifest_path = out / "candidate_pool_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return PoolResult(pool_csv, manifest_path, space.source_columns, int(n_samples), space.bounds, fixed)
