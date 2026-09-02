#!/usr/bin/env python3
"""Experiment 2 — can the outcome of an attempt be predicted before making it?

Grouped out-of-fold by target geometry, so no geometry informs its own
prediction. Two feature sets are compared: what is free (design variables only)
against what costs a cheap geometry/surface build.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import balanced_accuracy_score, f1_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mesh_agent import features as feature_builder  # noqa: E402
from mesh_agent.ledger import OUTCOME_PASS, load_attempts, outcome_matrix, production_pool  # noqa: E402
from mesh_agent.outcome import fit_out_of_fold  # noqa: E402
from mesh_agent.paths import RESULTS, TABLES  # noqa: E402


def evaluate(observations: pd.DataFrame, *, include_surface: bool) -> tuple[dict, pd.DataFrame]:
    matrix, _ = feature_builder.build(observations, include_surface=include_surface)
    predictions = fit_out_of_fold(matrix, observations)

    truth = observations["outcome"].to_numpy()
    predicted = predictions.probability.idxmax(axis=1).to_numpy()
    is_pass = (truth == OUTCOME_PASS).astype(int)

    quality_truth = pd.to_numeric(observations["min_scaled_quality"], errors="coerce")
    defined = quality_truth.notna().to_numpy()

    rank = spearmanr(
        quality_truth[defined], predictions.quality[defined]
    ).statistic

    metrics = {
        "feature_set": "design+surface" if include_surface else "design only",
        "n_features": matrix.shape[1],
        "n_cells": len(observations),
        "balanced_accuracy": balanced_accuracy_score(truth, predicted),
        "macro_f1": f1_score(truth, predicted, average="macro"),
        "pass_auc": roc_auc_score(is_pass, predictions.p_pass),
        "quality_mae": float(
            np.abs(quality_truth[defined] - predictions.quality[defined]).mean()
        ),
        "quality_spearman": float(rank),
    }
    detail = observations[
        ["geometry_index", "template_index", "outcome", "min_scaled_quality"]
    ].copy()
    detail["p_pass"] = predictions.p_pass.to_numpy()
    detail["predicted_quality"] = predictions.quality.to_numpy()
    detail["score"] = predictions.score().to_numpy()
    detail["predicted_class"] = predicted
    return metrics, detail


def main() -> None:
    observations = outcome_matrix(production_pool(load_attempts())).reset_index(drop=True)

    rows = []
    for include_surface in (False, True):
        metrics, detail = evaluate(observations, include_surface=include_surface)
        rows.append(metrics)
        suffix = "design_surface" if include_surface else "design"
        detail.to_csv(TABLES / f"oof_predictions_{suffix}.csv", index=False)

    # Trivial reference points, so the numbers above mean something.
    majority = observations["outcome"].value_counts(normalize=True).iloc[0]
    base_rate = (observations["outcome"] == OUTCOME_PASS).mean()

    table = pd.DataFrame(rows)
    table.to_csv(TABLES / "outcome_model_metrics.csv", index=False)

    lines = ["# Experiment 2 — predicting an attempt's outcome\n"]
    lines.append(
        f"{len(observations)} observed (geometry, template) cells, grouped "
        "out-of-fold by target geometry (5 folds).\n"
    )
    lines.append(table.round(4).to_markdown(index=False))
    lines.append(
        f"\nReference points: always predicting the majority class gives accuracy "
        f"{majority:.3f} (balanced accuracy 0.25 for four classes); the PASS base "
        f"rate is {base_rate:.3f}, so an uninformed ranker has AUC 0.5 and Spearman 0."
    )
    lines.append(
        "\n**Reading it.** For the agent, the ranking correlation matters more than "
        "the point error: the policy never needs the quality value, only the order "
        "of the candidates."
    )
    report = "\n".join(lines) + "\n"
    (RESULTS / "exp02_outcome_model.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
