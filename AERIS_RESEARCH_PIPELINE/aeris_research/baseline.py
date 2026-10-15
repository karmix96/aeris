from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import h5py
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .cgns import pressure_coefficients
from .common import PipelineError, output_manifest, utc_now, write_csv, write_json
from .dataset import SCHEMA_VERSION
from .models import (
    DenseAutoencoder,
    PODModel,
    RidgeModel,
    field_error_metrics,
    grouped_geometry_split,
)

BLUE = "#0072B2"


def _decode(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def _select_topology(handle: h5py.File, requested: str | None) -> str:
    rankings: dict[str, tuple[int, int]] = {}
    for topology_hash in handle["topologies"]:
        accepted = sum(
            snapshot.attrs["topology_hash"] == topology_hash
            and snapshot.attrs["run_status"] == "FINAL_ACCEPTED"
            for snapshot in handle["snapshots"].values()
        )
        cells = int(handle[f"topologies/{topology_hash}/connectivity"].shape[0])
        rankings[topology_hash] = (accepted, cells)
    if requested:
        matches = [value for value in rankings if value == requested or value.startswith(requested)]
        if len(matches) != 1:
            raise PipelineError(f"topology selector {requested!r} matched {len(matches)} families")
        return matches[0]
    if not rankings:
        raise PipelineError("canonical dataset has no topology families")
    return max(rankings, key=rankings.get)


def _load_family(path: Path, topology_selector: str | None) -> dict[str, Any]:
    with h5py.File(path, "r") as handle:
        if handle.attrs.get("schema_version") != SCHEMA_VERSION:
            raise PipelineError(f"unsupported canonical dataset: {path}")
        topology_hash = _select_topology(handle, topology_selector)
        topology = handle[f"topologies/{topology_hash}"]
        connectivity = topology["connectivity"][:]
        cell_zone = topology["cell_keys/zone"][:]
        cell_j = topology["cell_keys/j"][:]
        names, fields, features, geometry_groups = [], [], [], []
        snapshots = []
        for name, snapshot in sorted(handle["snapshots"].items()):
            if snapshot.attrs["topology_hash"] != topology_hash:
                continue
            if snapshot.attrs["run_status"] != "FINAL_ACCEPTED":
                continue
            cp = snapshot["fields/cp"][:]
            if not np.all(np.isfinite(cp)):
                continue
            row = json.loads(snapshot.attrs["source_row_json"])
            names.append(name)
            fields.append(cp)
            design = snapshot["design_vector"][:]
            flow = np.asarray([row["alpha_deg"], row["mach"], row["reynolds"]])
            features.append(np.concatenate([design, flow]))
            geometry_groups.append(f"{row['geometry_set']}:{row['geometry_index']}")
            snapshots.append(
                {
                    "row": row,
                    "coordinates": snapshot["coordinates"][:],
                    "normals": snapshot["normals"][:],
                    "areas": snapshot["areas"][:],
                }
            )
        feature_names = json.loads(handle["metadata"].attrs["design_feature_names_json"])
    if len(fields) < 2:
        raise PipelineError(f"topology family {topology_hash} has fewer than two accepted fields")
    if not np.all(np.isfinite(features)):
        raise PipelineError(
            f"topology family {topology_hash} contains missing/non-finite design or flow inputs"
        )
    return {
        "topology_hash": topology_hash,
        "connectivity": connectivity,
        "cell_zone": cell_zone,
        "cell_j": cell_j,
        "names": names,
        "fields": np.asarray(fields),
        "features": np.asarray(features),
        "feature_names": [*feature_names, "alpha_deg", "mach", "reynolds"],
        "geometry_groups": np.asarray(geometry_groups),
        "snapshots": snapshots,
    }


def _edge_masks(family: dict[str, Any], reference_index: int = 0) -> tuple[np.ndarray, np.ndarray]:
    snapshot = family["snapshots"][reference_index]
    centres = snapshot["coordinates"][family["connectivity"]].mean(axis=1)
    cell_zone, cell_j = family["cell_zone"], family["cell_j"]
    leading = np.zeros(centres.shape[0], dtype=bool)
    trailing = np.zeros(centres.shape[0], dtype=bool)
    for zone, span in np.unique(np.stack([cell_zone, cell_j], axis=1), axis=0):
        selected = np.flatnonzero((cell_zone == zone) & (cell_j == span))
        x = centres[selected, 0]
        extent = float(x.max() - x.min())
        if extent <= 0.0:
            continue
        fraction = (x - x.min()) / extent
        leading[selected[fraction <= 0.1]] = True
        trailing[selected[fraction >= 0.9]] = True
    return leading, trailing


def _save_pod(path: Path, model: PODModel) -> None:
    with Path(path).open("wb") as stream:
        np.savez_compressed(
            stream,
            model_type="POD",
            mean=model.mean,
            basis=model.basis,
            singular_values=model.singular_values,
        )


def _plot_pod(rows: list[dict[str, Any]], output: Path) -> None:
    ranks = np.asarray([row["rank"] for row in rows])
    rmse = np.asarray([row["rmse"] for row in rows])
    cumulative = np.asarray([row["cumulative_explained_variance"] for row in rows])
    figure, first = plt.subplots(figsize=(6.4, 4.0))
    second = first.twinx()
    first.plot(ranks, rmse, "o-", color="#0072B2", label="Reconstruction RMSE")
    second.plot(ranks, cumulative, "s--", color="#D55E00", label="Explained variance")
    first.set(xlabel="POD rank", ylabel=r"$C_p$ RMSE")
    second.set_ylabel("Cumulative explained variance")
    second.set_ylim(0.0, 1.02)
    first.grid(True, alpha=0.25)
    handles = [*first.get_lines(), *second.get_lines()]
    first.legend(handles, [line.get_label() for line in handles], loc="center right")
    figure.tight_layout()
    for suffix in ("png", "svg"):
        figure.savefig(output.with_suffix(f".{suffix}"), dpi=300, bbox_inches="tight")
    plt.close(figure)


def _learning_curve(
    family: dict[str, Any],
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    *,
    maximum_rank: int,
    seed: int,
) -> list[dict[str, Any]]:
    """Nested geometry-disjoint POD-ridge curves against a fixed test cohort."""

    train_groups = np.unique(family["geometry_groups"][train_indices])
    rows = []
    repeats = min(5, max(1, train_groups.size))
    for repeat in range(repeats):
        ordered = train_groups.copy()
        np.random.default_rng(seed + repeat).shuffle(ordered)
        for geometry_count in range(1, ordered.size + 1):
            chosen = ordered[:geometry_count]
            subset = train_indices[np.isin(family["geometry_groups"][train_indices], chosen)]
            if subset.size < 2:
                continue
            model = PODModel.fit(family["fields"][subset])
            rank = min(maximum_rank, model.max_rank, max(1, subset.size - 1))
            coefficients = model.encode(family["fields"][subset], rank)
            regressor = RidgeModel.fit(family["features"][subset], coefficients)
            prediction = model.decode(regressor.predict(family["features"][test_indices]), rank)
            rows.append(
                {
                    "repeat": repeat,
                    "training_geometries": geometry_count,
                    "training_snapshots": int(subset.size),
                    "test_snapshots": int(test_indices.size),
                    "pod_rank": rank,
                    "cp_rmse": field_error_metrics(family["fields"][test_indices], prediction)[
                        "rmse"
                    ],
                }
            )
    return rows


def _plot_learning_curve(rows: list[dict[str, Any]], output: Path) -> None:
    if not rows:
        return
    by_count: dict[int, list[float]] = {}
    for row in rows:
        by_count.setdefault(int(row["training_snapshots"]), []).append(float(row["cp_rmse"]))
    counts = np.asarray(sorted(by_count))
    mean = np.asarray([np.mean(by_count[count]) for count in counts])
    spread = np.asarray([np.std(by_count[count]) for count in counts])
    figure, axis = plt.subplots(figsize=(6.0, 3.8))
    axis.plot(counts, mean, "o-", color=BLUE)
    axis.fill_between(counts, mean - spread, mean + spread, color=BLUE, alpha=0.18)
    axis.set(xlabel="Training CFD snapshots", ylabel=r"Test $C_p$ RMSE")
    axis.grid(True, alpha=0.22)
    figure.tight_layout()
    for suffix in ("png", "svg"):
        figure.savefig(output.with_suffix(f".{suffix}"), dpi=300, bbox_inches="tight")
    plt.close(figure)


def _evaluate_predictions(
    family: dict[str, Any], indices: np.ndarray, predicted: np.ndarray, method: str
) -> list[dict[str, Any]]:
    leading, trailing = _edge_masks(family, int(indices[0]))
    rows = []
    for local_index, snapshot_index in enumerate(indices):
        truth = family["fields"][snapshot_index]
        estimate = predicted[local_index]
        snapshot = family["snapshots"][snapshot_index]
        row = snapshot["row"]
        metrics = field_error_metrics(truth, estimate)
        metrics["le_rmse"] = float(np.sqrt(np.mean((estimate[leading] - truth[leading]) ** 2)))
        metrics["te_rmse"] = float(np.sqrt(np.mean((estimate[trailing] - truth[trailing]) ** 2)))
        arguments = {
            "coordinates": snapshot["coordinates"],
            "connectivity": family["connectivity"],
            "normals": snapshot["normals"],
            "areas": snapshot["areas"],
            "alpha_deg": float(row["alpha_deg"]),
            "area_ref": float(row["area_ref"]),
            "chord_ref": float(row["chord_ref"]),
            "moment_ref_xyz": np.asarray(row["moment_ref_xyz"]),
        }
        truth_integrals = pressure_coefficients(truth, **arguments)
        predicted_integrals = pressure_coefficients(estimate, **arguments)
        rows.append(
            {
                "method": method,
                "run_name": family["names"][snapshot_index],
                "geometry_group": family["geometry_groups"][snapshot_index],
                "alpha_deg": row["alpha_deg"],
                **metrics,
                "cl_pressure_true": truth_integrals["cl_pressure"],
                "cl_pressure_predicted": predicted_integrals["cl_pressure"],
                "cl_pressure_abs_error": abs(
                    predicted_integrals["cl_pressure"] - truth_integrals["cl_pressure"]
                ),
                "cmy_pressure_true": truth_integrals["cmy_pressure"],
                "cmy_pressure_predicted": predicted_integrals["cmy_pressure"],
                "cmy_pressure_abs_error": abs(
                    predicted_integrals["cmy_pressure"] - truth_integrals["cmy_pressure"]
                ),
            }
        )
    return rows


def build_baselines(
    dataset_path: Path,
    output: Path,
    *,
    topology_selector: str | None = None,
    pod_rank: int = 16,
    latent_dim: int = 16,
    epochs: int = 250,
    seed: int = 42,
    train_predictors: bool = True,
) -> dict[str, Any]:
    dataset_path = Path(dataset_path).resolve()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    family = _load_family(dataset_path, topology_selector)
    fields = family["fields"]

    descriptive_pod = PODModel.fit(fields)
    maximum_rank = min(int(pod_rank), fields.shape[0] - 1, descriptive_pod.max_rank)
    variance = descriptive_pod.explained_variance_ratio()
    pod_rows = []
    for rank in range(1, maximum_rank + 1):
        reconstruction = descriptive_pod.decode(descriptive_pod.encode(fields, rank), rank)
        pod_rows.append(
            {
                "rank": rank,
                "rmse": field_error_metrics(fields, reconstruction)["rmse"],
                "cumulative_explained_variance": float(variance[:rank].sum()),
            }
        )
    write_csv(
        output / "pod_reconstruction.csv",
        pod_rows,
        ("rank", "rmse", "cumulative_explained_variance"),
    )
    _save_pod(output / "pod_model.npz", descriptive_pod)
    _plot_pod(pod_rows, output / "pod_reconstruction")

    groups = np.unique(family["geometry_groups"])
    report: dict[str, Any] = {
        "schema_version": "aeris.field_baselines.v1",
        "created_utc": utc_now(),
        "dataset": str(dataset_path),
        "topology_hash": family["topology_hash"],
        "snapshots": int(fields.shape[0]),
        "cells": int(fields.shape[1]),
        "distinct_geometries": int(groups.size),
        "pod": {
            "status": "COMPLETE",
            "maximum_rank_evaluated": maximum_rank,
            "rank_at_99_percent": int(np.searchsorted(np.cumsum(variance), 0.99) + 1),
        },
    }
    if not train_predictors:
        report["prediction"] = {
            "status": "READY_NOT_RUN" if groups.size >= 3 else "SKIPPED_INSUFFICIENT_GEOMETRIES",
            "reason": (
                "Predictor training was disabled for this build. Pass the explicit training "
                "option only when it will not contend with CFD."
                if groups.size >= 3
                else (
                    "Strict geometry-disjoint train/validation/test evaluation requires at "
                    f"least 3 geometries; this family contains {groups.size}."
                )
            ),
            "ready_models": ["POD", "POD-coefficient ridge", "regularized tanh autoencoder"],
        }
    elif groups.size < 3:
        report["prediction"] = {
            "status": "SKIPPED_INSUFFICIENT_GEOMETRIES",
            "reason": (
                "Strict geometry-disjoint train/validation/test evaluation requires at least "
                f"3 geometries; this family contains {groups.size}. No leaked score was produced."
            ),
            "ready_models": ["POD", "POD-coefficient ridge", "regularized tanh autoencoder"],
        }
    else:
        split = grouped_geometry_split(family["geometry_groups"], seed=seed)
        train, validation, test = split["train"], split["validation"], split["test"]
        model = PODModel.fit(fields[train])
        rank = min(int(pod_rank), model.max_rank, max(1, train.size - 1))
        train_coefficients = model.encode(fields[train], rank)
        ridge = RidgeModel.fit(family["features"][train], train_coefficients)
        pod_prediction = model.decode(ridge.predict(family["features"][test]), rank)

        autoencoder = DenseAutoencoder(
            input_dim=fields.shape[1], latent_dim=min(latent_dim, fields.shape[1]), seed=seed
        )
        history = autoencoder.fit(
            fields[train], fields[validation], epochs=epochs, patience=max(20, epochs // 8)
        )
        latent_regressor = RidgeModel.fit(
            family["features"][train], autoencoder.encode(fields[train])
        )
        autoencoder_prediction = autoencoder.decode(
            latent_regressor.predict(family["features"][test])
        )
        prediction_rows = [
            *_evaluate_predictions(family, test, pod_prediction, "POD_RIDGE"),
            *_evaluate_predictions(family, test, autoencoder_prediction, "AUTOENCODER_RIDGE"),
        ]
        columns = tuple(prediction_rows[0].keys())
        write_csv(output / "geometry_holdout_metrics.csv", prediction_rows, columns)
        write_csv(
            output / "autoencoder_training.csv",
            history,
            ("epoch", "train_loss", "train_reconstruction_loss", "validation_reconstruction_loss"),
        )
        autoencoder.save(output / "autoencoder_model.npz")
        with (output / "latent_ridge_model.npz").open("wb") as stream:
            np.savez_compressed(
                stream,
                feature_names=np.asarray(family["feature_names"]),
                feature_mean=latent_regressor.feature_mean,
                feature_scale=latent_regressor.feature_scale,
                weights=latent_regressor.weights,
            )
        learning_rows = _learning_curve(family, train, test, maximum_rank=int(pod_rank), seed=seed)
        write_csv(
            output / "learning_curve.csv",
            learning_rows,
            (
                "repeat",
                "training_geometries",
                "training_snapshots",
                "test_snapshots",
                "pod_rank",
                "cp_rmse",
            ),
        )
        _plot_learning_curve(learning_rows, output / "learning_curve")
        report["prediction"] = {
            "status": "COMPLETE",
            "split": {
                name: {
                    "snapshots": int(indices.size),
                    "geometries": sorted(set(family["geometry_groups"][indices])),
                }
                for name, indices in split.items()
            },
            "pod_rank": rank,
            "autoencoder_latent_dim": int(autoencoder.encoder_bias.size),
            "autoencoder_epochs": len(history),
            "learning_curve_points": len(learning_rows),
        }

    write_json(output / "baseline_report.json", report)
    report["outputs"] = output_manifest(output, exclude={"baseline_manifest.json"})
    write_json(output / "baseline_manifest.json", report)
    return report
