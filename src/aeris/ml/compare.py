from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Sequence

from aeris.ml.model_registry import get_model_spec, list_model_types
from aeris.ml.train import train_baseline_model


def _ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _normalize_model_types(model_types: Sequence[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for value in model_types:
        model = str(value).strip()
        if not model:
            continue

        if model not in list_model_types():
            supported = ", ".join(list_model_types())
            raise ValueError(
                f"Unsupported model type '{model}'. Supported model types: {supported}"
            )

        if model not in seen:
            seen.add(model)
            cleaned.append(model)

    if not cleaned:
        raise ValueError("At least one valid model type must be provided.")

    return cleaned


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_artifact_path(artifacts: Any, attr_name: str) -> str | None:
    if artifacts is None:
        return None

    if hasattr(artifacts, attr_name):
        value = getattr(artifacts, attr_name)
        return None if value is None else str(value)

    if isinstance(artifacts, dict):
        value = artifacts.get(attr_name)
        return None if value is None else str(value)

    return None


def _add_rankings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return rows

    rmse_order = sorted(rows, key=lambda r: (r["test_rmse_mean"], r["model_type"]))
    mae_order = sorted(rows, key=lambda r: (r["test_mae_mean"], r["model_type"]))
    r2_order = sorted(rows, key=lambda r: (-r["test_r2_mean"], r["model_type"]))

    rmse_rank = {row["model_type"]: i + 1 for i, row in enumerate(rmse_order)}
    mae_rank = {row["model_type"]: i + 1 for i, row in enumerate(mae_order)}
    r2_rank = {row["model_type"]: i + 1 for i, row in enumerate(r2_order)}

    for row in rows:
        model_type = row["model_type"]
        row["rank_test_rmse_mean"] = rmse_rank[model_type]
        row["rank_test_mae_mean"] = mae_rank[model_type]
        row["rank_test_r2_mean"] = r2_rank[model_type]

    return rows


def _build_csv_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for run in summary["model_runs"]:
        rows.append(
            {
                "model_type": run["model_type"],
                "model_name": run["model_name"],
                "family": run["family"],
                "train_rows": run["split"]["train_rows"],
                "val_rows": run["split"]["val_rows"],
                "test_rows": run["split"]["test_rows"],
                "train_hash": run["split"]["train_hash"],
                "val_hash": run["split"]["val_hash"],
                "test_hash": run["split"]["test_hash"],
                "train_rmse_mean": run["metrics"]["train"]["overall"]["rmse_mean"],
                "train_mae_mean": run["metrics"]["train"]["overall"]["mae_mean"],
                "train_r2_mean": run["metrics"]["train"]["overall"]["r2_mean"],
                "val_rmse_mean": run["metrics"]["val"]["overall"]["rmse_mean"],
                "val_mae_mean": run["metrics"]["val"]["overall"]["mae_mean"],
                "val_r2_mean": run["metrics"]["val"]["overall"]["r2_mean"],
                "test_rmse_mean": run["metrics"]["test"]["overall"]["rmse_mean"],
                "test_mae_mean": run["metrics"]["test"]["overall"]["mae_mean"],
                "test_r2_mean": run["metrics"]["test"]["overall"]["r2_mean"],
                "rank_test_rmse_mean": run["summary"]["rank_test_rmse_mean"],
                "rank_test_mae_mean": run["summary"]["rank_test_mae_mean"],
                "rank_test_r2_mean": run["summary"]["rank_test_r2_mean"],
                "run_dir": run["artifacts"]["run_dir"],
                "metrics_path": run["artifacts"]["metrics_path"],
                "model_path": run["artifacts"]["model_path"],
                "train_rows_path": run["artifacts"]["train_rows_path"],
                "val_rows_path": run["artifacts"]["val_rows_path"],
                "test_rows_path": run["artifacts"]["test_rows_path"],
                "explainability_path": run["artifacts"]["explainability_path"],
            }
        )

    return _add_rankings(rows)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        fieldnames = ["model_type"]
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
        return

    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def compare_models(
    *,
    dataset_path: Path,
    feature_columns: list[str],
    target_columns: list[str],
    model_types: Sequence[str],
    split_method: str = "grouped",
    group_column: str = "geometry_id",
    train_fraction: float = 0.7,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    random_seed: int = 123,
    allow_forced: bool = False,
    model_params_by_type: dict[str, dict[str, Any]] | None = None,
    feature_set_name: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    dataset_path = Path(dataset_path).expanduser().resolve()
    normalized_models = _normalize_model_types(model_types)

    if output_dir is None:
        output_dir = (
            Path("data")
            / "processed"
            / "ml_compare"
            / f"{dataset_path.name}__seed{random_seed}"
        )

    output_dir = _ensure_output_dir(output_dir)
    runs_root = _ensure_output_dir(output_dir / "runs")

    model_runs: list[dict[str, Any]] = []
    reference_split_hashes: dict[str, str] | None = None

    for model_type in normalized_models:
        model_output_dir = runs_root / model_type

        result = train_baseline_model(
            dataset_path=dataset_path,
            feature_columns=feature_columns,
            target_columns=target_columns,
            model_type=model_type,
            split_method=split_method,
            group_column=group_column,
            train_fraction=train_fraction,
            val_fraction=val_fraction,
            test_fraction=test_fraction,
            random_seed=random_seed,
            allow_forced=allow_forced,
            model_params=(model_params_by_type or {}).get(model_type, {}),
            output_dir=model_output_dir,
            feature_set_name=feature_set_name,
        )

        artifacts = result["artifacts"]
        metrics = result["metrics"]
        split = result["split"]

        train_rows_path = Path(_extract_artifact_path(artifacts, "train_rows_path") or "")
        val_rows_path = Path(_extract_artifact_path(artifacts, "val_rows_path") or "")
        test_rows_path = Path(_extract_artifact_path(artifacts, "test_rows_path") or "")

        split_hashes = {
            "train_hash": _file_sha256(train_rows_path),
            "val_hash": _file_sha256(val_rows_path),
            "test_hash": _file_sha256(test_rows_path),
        }

        if reference_split_hashes is None:
            reference_split_hashes = dict(split_hashes)
        else:
            if split_hashes != reference_split_hashes:
                raise RuntimeError(
                    f"Split mismatch detected for model '{model_type}'. "
                    "All compared models must use identical split rows."
                )

        explainability_path = (
            _extract_artifact_path(artifacts, "coefficients_path")
            or _extract_artifact_path(artifacts, "feature_importances_path")
        )

        split_metadata = dict(getattr(split, "metadata", {}) or {})
        spec = get_model_spec(model_type)

        model_runs.append(
            {
                "model_type": model_type,
                "model_name": spec.display_name,
                "family": spec.family_name,
                "metrics": metrics,
                "split": {
                    "method": split.method,
                    "group_column": split_metadata.get("group_column"),
                    "train_rows": len(split.train_df),
                    "val_rows": len(split.val_df),
                    "test_rows": len(split.test_df),
                    "metadata": split_metadata,
                    **split_hashes,
                },
                "artifacts": {
                    "run_dir": _extract_artifact_path(artifacts, "run_dir"),
                    "models_dir": _extract_artifact_path(artifacts, "models_dir"),
                    "model_path": _extract_artifact_path(artifacts, "model_path"),
                    "metrics_path": _extract_artifact_path(artifacts, "metrics_path"),
                    "train_config_path": _extract_artifact_path(artifacts, "train_config_path"),
                    "train_rows_path": _extract_artifact_path(artifacts, "train_rows_path"),
                    "val_rows_path": _extract_artifact_path(artifacts, "val_rows_path"),
                    "test_rows_path": _extract_artifact_path(artifacts, "test_rows_path"),
                    "explainability_path": explainability_path,
                },
                "summary": {
                    "test_rmse_mean": metrics["test"]["overall"]["rmse_mean"],
                    "test_mae_mean": metrics["test"]["overall"]["mae_mean"],
                    "test_r2_mean": metrics["test"]["overall"]["r2_mean"],
                },
            }
        )

    summary_rows = _add_rankings(
        [
            {
                "model_type": run["model_type"],
                "test_rmse_mean": run["summary"]["test_rmse_mean"],
                "test_mae_mean": run["summary"]["test_mae_mean"],
                "test_r2_mean": run["summary"]["test_r2_mean"],
            }
            for run in model_runs
        ]
    )

    ranks_by_model = {row["model_type"]: row for row in summary_rows}
    for run in model_runs:
        run["summary"].update(
            {
                "rank_test_rmse_mean": ranks_by_model[run["model_type"]]["rank_test_rmse_mean"],
                "rank_test_mae_mean": ranks_by_model[run["model_type"]]["rank_test_mae_mean"],
                "rank_test_r2_mean": ranks_by_model[run["model_type"]]["rank_test_r2_mean"],
            }
        )

    best_rmse = min(model_runs, key=lambda r: r["summary"]["test_rmse_mean"])
    best_mae = min(model_runs, key=lambda r: r["summary"]["test_mae_mean"])
    best_r2 = max(model_runs, key=lambda r: r["summary"]["test_r2_mean"])

    summary = {
        "dataset_path": str(dataset_path),
        "feature_columns": list(feature_columns),
        "target_columns": list(target_columns),
        "feature_set_name": feature_set_name,
        "split_config": {
            "split_method": split_method,
            "group_column": group_column,
            "train_fraction": train_fraction,
            "val_fraction": val_fraction,
            "test_fraction": test_fraction,
            "random_seed": random_seed,
            "allow_forced": allow_forced,
        },
        "model_types": list(normalized_models),
        "shared_split_hashes": reference_split_hashes or {},
        "best_model_by_test_rmse_mean": best_rmse["model_type"],
        "best_model_by_test_mae_mean": best_mae["model_type"],
        "best_model_by_test_r2_mean": best_r2["model_type"],
        "model_runs": model_runs,
    }

    summary_json_path = output_dir / "comparison_summary.json"
    summary_csv_path = output_dir / "comparison_summary.csv"

    summary_json_path.write_text(
        json.dumps(_to_jsonable(summary), indent=2),
        encoding="utf-8",
    )
    _write_csv(summary_csv_path, _build_csv_rows(summary))

    return {
        "output_dir": output_dir,
        "comparison_summary_json": summary_json_path,
        "comparison_summary_csv": summary_csv_path,
        "summary": summary,
    }