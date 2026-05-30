from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aeris.ml.fingerprints import file_sha256
from aeris.ml.manifest import utc_now_iso

DELTA_DATASET_SCHEMA_VERSION = "aeris.multifidelity_delta_dataset.v1"


@dataclass(frozen=True)
class DeltaDatasetResult:
    output_dir: Path
    delta_dataset_csv: Path
    report_json: Path
    n_lf_rows: int
    n_hf_rows: int
    n_paired_rows: int
    n_unmatched_lf_rows: int
    n_unmatched_hf_rows: int
    pair_keys: list[str]
    targets: list[str]
    report: dict[str, Any]


def _ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_csv(path: str | Path, *, label: str) -> tuple[Path, pd.DataFrame]:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"{label} CSV does not exist: {resolved}")
    df = pd.read_csv(resolved)
    if df.empty:
        raise ValueError(f"{label} CSV is empty: {resolved}")
    return resolved, df


def _require_columns(df: pd.DataFrame, columns: list[str], *, label: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"{label} CSV is missing required columns: {missing}")


def _check_unique_pair_keys(df: pd.DataFrame, pair_keys: list[str], *, label: str) -> None:
    duplicated = df.duplicated(subset=pair_keys, keep=False)
    if duplicated.any():
        examples = df.loc[duplicated, pair_keys].head(5).to_dict(orient="records")
        raise ValueError(
            f"{label} CSV has duplicate rows for pair keys {pair_keys}; examples: {examples}"
        )


def _coerce_targets_numeric(df: pd.DataFrame, targets: list[str], *, label: str) -> pd.DataFrame:
    out = df.copy()
    for target in targets:
        numeric = pd.to_numeric(out[target], errors="coerce")
        values = numeric.to_numpy(dtype=float, na_value=np.nan)
        bad_mask = ~np.isfinite(values)
        if bad_mask.any():
            n_bad = int(bad_mask.sum())
            raise ValueError(f"{label} target column '{target}' contains {n_bad} non-finite/non-numeric values")
        out[target] = numeric.astype(float)
    return out


def _count_unmatched(left: pd.DataFrame, right: pd.DataFrame, pair_keys: list[str]) -> int:
    marker = left.merge(right[pair_keys].drop_duplicates(), on=pair_keys, how="left", indicator=True)
    return int((marker["_merge"] == "left_only").sum())


def _delta_stats(df: pd.DataFrame, delta_targets: list[str]) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    for col in delta_targets:
        values = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            stats[col] = {"n": 0, "mean": None, "std": None, "min": None, "max": None}
            continue
        stats[col] = {
            "n": int(finite.size),
            "mean": float(np.mean(finite)),
            "std": float(np.std(finite)),
            "min": float(np.min(finite)),
            "max": float(np.max(finite)),
        }
    return stats


def build_delta_dataset(
    *,
    lf_csv: str | Path,
    hf_csv: str | Path,
    pair_keys: list[str],
    targets: list[str],
    output_dir: str | Path,
    delta_prefix: str = "delta__",
    lf_prefix: str = "lf__",
    hf_prefix: str = "hf__",
) -> DeltaDatasetResult:
    """Build an ML-ready multifidelity delta dataset from paired LF/HF scalar rows.

    The pairing rule is strict: every row is matched by ``pair_keys`` and both LF/HF
    tables must have unique rows for those keys. The output keeps pair keys and LF
    context columns unchanged, then adds LF/HF target copies and delta targets:

    ``delta__cl = hf__cl - lf__cl``
    """
    if not pair_keys:
        raise ValueError("pair_keys must contain at least one column")
    if not targets:
        raise ValueError("targets must contain at least one target column")
    overlap = sorted(set(pair_keys) & set(targets))
    if overlap:
        raise ValueError(f"pair_keys and targets must be disjoint; overlap: {overlap}")

    lf_path, lf_df_raw = _read_csv(lf_csv, label="LF")
    hf_path, hf_df_raw = _read_csv(hf_csv, label="HF")

    required = list(pair_keys) + list(targets)
    _require_columns(lf_df_raw, required, label="LF")
    _require_columns(hf_df_raw, required, label="HF")
    _check_unique_pair_keys(lf_df_raw, pair_keys, label="LF")
    _check_unique_pair_keys(hf_df_raw, pair_keys, label="HF")

    lf_df = _coerce_targets_numeric(lf_df_raw, targets, label="LF")
    hf_df = _coerce_targets_numeric(hf_df_raw, targets, label="HF")

    n_unmatched_lf = _count_unmatched(lf_df, hf_df, pair_keys)
    n_unmatched_hf = _count_unmatched(hf_df, lf_df, pair_keys)

    merged = lf_df.merge(
        hf_df[list(pair_keys) + list(targets)],
        on=pair_keys,
        how="inner",
        suffixes=("__lf", "__hf"),
    )

    context_cols = [c for c in lf_df.columns if c not in set(pair_keys) and c not in set(targets)]
    output = merged[list(pair_keys) + context_cols].copy()

    delta_cols: list[str] = []
    for target in targets:
        lf_col = f"{target}__lf"
        hf_col = f"{target}__hf"
        out_lf = f"{lf_prefix}{target}"
        out_hf = f"{hf_prefix}{target}"
        out_delta = f"{delta_prefix}{target}"
        output[out_lf] = merged[lf_col].astype(float)
        output[out_hf] = merged[hf_col].astype(float)
        output[out_delta] = output[out_hf] - output[out_lf]
        delta_cols.append(out_delta)

    out_dir = _ensure_output_dir(Path(output_dir).expanduser().resolve())
    delta_csv = out_dir / "delta_dataset.csv"
    report_json = out_dir / "delta_dataset_report.json"
    output.to_csv(delta_csv, index=False)

    report = {
        "schema_version": DELTA_DATASET_SCHEMA_VERSION,
        "created_at_utc": utc_now_iso(),
        "lf_csv": str(lf_path),
        "hf_csv": str(hf_path),
        "output_dir": str(out_dir),
        "delta_dataset_csv": str(delta_csv),
        "pair_keys": list(pair_keys),
        "targets": list(targets),
        "prefixes": {
            "lf_prefix": lf_prefix,
            "hf_prefix": hf_prefix,
            "delta_prefix": delta_prefix,
        },
        "counts": {
            "lf_rows": int(len(lf_df)),
            "hf_rows": int(len(hf_df)),
            "paired_rows": int(len(output)),
            "unmatched_lf_rows": n_unmatched_lf,
            "unmatched_hf_rows": n_unmatched_hf,
        },
        "columns": {
            "context_columns_from_lf": context_cols,
            "lf_target_columns": [f"{lf_prefix}{t}" for t in targets],
            "hf_target_columns": [f"{hf_prefix}{t}" for t in targets],
            "delta_target_columns": delta_cols,
        },
        "delta_stats": _delta_stats(output, delta_cols),
        "fingerprints": {
            "lf_csv_sha256": file_sha256(lf_path),
            "hf_csv_sha256": file_sha256(hf_path),
            "delta_dataset_csv_sha256": file_sha256(delta_csv),
        },
    }
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return DeltaDatasetResult(
        output_dir=out_dir,
        delta_dataset_csv=delta_csv,
        report_json=report_json,
        n_lf_rows=int(len(lf_df)),
        n_hf_rows=int(len(hf_df)),
        n_paired_rows=int(len(output)),
        n_unmatched_lf_rows=n_unmatched_lf,
        n_unmatched_hf_rows=n_unmatched_hf,
        pair_keys=list(pair_keys),
        targets=list(targets),
        report=report,
    )
