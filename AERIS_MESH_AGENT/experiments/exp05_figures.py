#!/usr/bin/env python3
"""Experiment 5 — the paper's figures."""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mesh_agent.ledger import (  # noqa: E402
    OUTCOME_FAIL_FOLDED,
    OUTCOME_FAIL_LOW_QUALITY,
    OUTCOME_PASS,
    OUTCOME_SURFACE_BUILD_ERROR,
    PRODUCTION_FLOOR,
    load_attempts,
    outcome_matrix,
    production_pool,
)
from mesh_agent.paths import FIGURES, TABLES  # noqa: E402
from mesh_agent.policy import PREFERRED_QUALITY  # noqa: E402

HEADLINE_CAMPAIGN = "development_atlas_qualified21_production_written_v3"

COLOURS = {
    OUTCOME_PASS: "#2f6f4e",
    OUTCOME_FAIL_LOW_QUALITY: "#c9a227",
    OUTCOME_FAIL_FOLDED: "#b3402f",
    OUTCOME_SURFACE_BUILD_ERROR: "#6b6b6b",
}
plt.rcParams.update({
    "font.size": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 160,
    "savefig.bbox": "tight",
})


def _save(fig: plt.Figure, name: str) -> None:
    for extension in ("png", "pdf"):
        fig.savefig(FIGURES / f"{name}.{extension}")
    plt.close(fig)
    print(f"  figures/{name}.png")


def figure_retry_tail(recorded: pd.DataFrame) -> None:
    counts = recorded.groupby("geometry_index")["attempt_ordinal"].max().value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(4.6, 2.8))
    ax.bar(counts.index.astype(str), counts.to_numpy(), color="#3a5a80", width=0.7)
    for x, value in enumerate(counts.to_numpy()):
        ax.text(x, value + 1.2, str(value), ha="center", fontsize=8)
    ax.set_xlabel("attempts needed by the atlas")
    ax.set_ylabel("geometries")
    ax.set_title("The cost is a tail, not an average", loc="left", fontsize=10)
    ax.set_ylim(0, counts.max() * 1.18)
    _save(fig, "fig1_retry_tail")


def figure_worst_case(recorded: pd.DataFrame) -> None:
    per_geometry = recorded.groupby("geometry_index")["attempt_ordinal"].max()
    worst = recorded[recorded["geometry_index"] == int(per_geometry.idxmax())].sort_values(
        "attempt_ordinal"
    )
    quality = pd.to_numeric(worst["min_scaled_quality"], errors="coerce")

    # A surface-build error has no quality at all, so it is drawn in its own band
    # below the axis break rather than at a number it never produced.
    no_mesh_level = float(quality.min()) - 0.075

    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    ax.axhspan(PREFERRED_QUALITY, float(quality.max()) + 0.06, color="#2f6f4e", alpha=0.06)
    ax.axhline(PREFERRED_QUALITY, color="#2f6f4e", lw=1, ls="--")
    ax.axhline(PRODUCTION_FLOOR, color="#c9a227", lw=1, ls=":")
    ax.axhline(no_mesh_level + 0.032, color="#bbb", lw=0.8, ls="-")
    ax.text(21.4, PREFERRED_QUALITY, " preferred 0.15", va="center", fontsize=8, color="#2f6f4e")
    ax.text(21.4, PRODUCTION_FLOOR, " floor 0.10", va="center", fontsize=8, color="#c9a227")
    ax.text(0.4, no_mesh_level, "no volume written", va="center", ha="left",
            fontsize=7.5, color="#6b6b6b", style="italic")

    for ordinal, value, outcome in zip(worst["attempt_ordinal"], quality, worst["outcome"]):
        if np.isnan(value):
            ax.plot(ordinal, no_mesh_level, marker="x", color=COLOURS[outcome], ms=6, mew=1.6)
        else:
            ax.plot(ordinal, value, marker="o", color=COLOURS[outcome], ms=6)

    ax.plot([1], [quality.iloc[0]], marker="o", mfc="none", mec="#b3402f", ms=15, mew=1.6)
    ax.annotate(
        "best of all 21 attempts,\nand it was the first",
        xy=(1.35, quality.iloc[0]), xytext=(3.0, quality.iloc[0] - 0.135),
        fontsize=8, color="#b3402f",
        arrowprops=dict(arrowstyle="->", color="#b3402f", lw=0.9),
    )
    ax.set_xticks(range(1, 22))
    ax.set_xlim(0.2, 22.0)
    ax.set_xlabel("attempt")
    ax.set_ylabel("min scaled quality")
    ax.set_title(
        f"Geometry {int(per_geometry.idxmax())}: twenty attempts to rediscover the first",
        loc="left", fontsize=10, pad=10,
    )
    handles = [plt.Line2D([], [], marker="o", ls="", color=c, label=k.replace("_", " ").lower())
               for k, c in COLOURS.items()]
    ax.legend(handles=handles, fontsize=7, frameon=False, ncol=2,
              loc="lower right", bbox_to_anchor=(1.0, 0.02))
    _save(fig, "fig2_worst_case")


def figure_coverage(observations: pd.DataFrame) -> None:
    geometries = sorted(observations["geometry_index"].unique())
    templates = sorted(observations["template_index"].unique())
    grid = np.full((len(templates), len(geometries)), np.nan)
    order = {OUTCOME_PASS: 0, OUTCOME_FAIL_LOW_QUALITY: 1,
             OUTCOME_FAIL_FOLDED: 2, OUTCOME_SURFACE_BUILD_ERROR: 3}
    g_pos = {g: i for i, g in enumerate(geometries)}
    t_pos = {t: i for i, t in enumerate(templates)}
    for row in observations.itertuples():
        grid[t_pos[row.template_index], g_pos[row.geometry_index]] = order[row.outcome]

    cmap = matplotlib.colors.ListedColormap([COLOURS[k] for k in order])
    fig, ax = plt.subplots(figsize=(7.4, 2.8))
    ax.imshow(np.ma.masked_invalid(grid), aspect="auto", cmap=cmap, vmin=-0.5, vmax=3.5,
              interpolation="nearest")
    ax.set_facecolor("#f2f2f2")
    ax.set_xlabel("target geometry")
    ax.set_ylabel("template")
    ax.set_yticks(range(len(templates)))
    ax.set_yticklabels(templates, fontsize=6)
    filled = np.isfinite(grid).sum()
    ax.set_title(
        f"Observed outcome matrix: {filled} of {grid.size} cells "
        f"({100 * filled / grid.size:.1f}%); grey is unmeasured",
        loc="left", fontsize=10,
    )
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLOURS[k], label=k.replace("_", " ").lower())
               for k in order]
    ax.legend(handles=handles, fontsize=7, frameon=False, ncol=4,
              loc="upper center", bbox_to_anchor=(0.5, -0.28))
    _save(fig, "fig3_coverage")


def figure_policies() -> None:
    path = TABLES / "policy_summary.csv"
    if not path.is_file():
        print("  (skipped fig4: run exp03 first)")
        return
    summary = pd.read_csv(path).sort_values("total_attempts", ascending=False)

    def colour(policy: str) -> str:
        if policy.startswith("atlas (as run)"):
            return "#b3402f"
        if policy.startswith("atlas ordering"):
            return "#c9a227"       # the no-model ablation
        if policy.startswith("oracle"):
            return "#6b6b6b"
        return "#3a5a80"

    fig, ax = plt.subplots(figsize=(7.6, 3.4))
    bars = ax.barh(summary["policy"], summary["total_attempts"],
                   color=[colour(p) for p in summary["policy"]], height=0.62)

    loss = summary.get("quality_loss_pct")
    for bar, attempts, quality_loss in zip(bars, summary["total_attempts"], loss):
        label = f"{int(attempts)}"
        if quality_loss and quality_loss > 0.005:
            # A policy can always buy attempts with quality, so the price is
            # printed next to the saving rather than left to the caption.
            label += f"   (-{quality_loss:.1f}% quality)"
        ax.text(attempts + 2.0, bar.get_y() + bar.get_height() / 2, label,
                va="center", fontsize=8)

    ax.set_xlabel("total meshing attempts for 100 geometries")
    ax.set_title("Fewer attempts, and what each policy pays for them",
                 loc="left", fontsize=10)
    ax.set_xlim(0, summary["total_attempts"].max() * 1.42)
    handles = [
        plt.Rectangle((0, 0), 1, 1, color="#b3402f", label="incumbent"),
        plt.Rectangle((0, 0), 1, 1, color="#c9a227", label="stopping rule only, no model"),
        plt.Rectangle((0, 0), 1, 1, color="#3a5a80", label="learned"),
        plt.Rectangle((0, 0), 1, 1, color="#6b6b6b", label="oracle bound"),
    ]
    ax.legend(handles=handles, fontsize=7, frameon=False, ncol=4,
              loc="upper center", bbox_to_anchor=(0.5, -0.22))
    _save(fig, "fig4_policy_comparison")


def figure_quality_prediction() -> None:
    path = TABLES / "oof_predictions_design.csv"
    if not path.is_file():
        print("  (skipped fig5: run exp02 first)")
        return
    detail = pd.read_csv(path)
    defined = detail.dropna(subset=["min_scaled_quality"])
    fig, ax = plt.subplots(figsize=(3.5, 3.3))
    for outcome, colour in COLOURS.items():
        subset = defined[defined["outcome"] == outcome]
        ax.scatter(subset["min_scaled_quality"], subset["predicted_quality"],
                   s=13, color=colour, alpha=0.75, linewidths=0,
                   label=outcome.replace("_", " ").lower())
    limits = [defined["min_scaled_quality"].min() - 0.05, defined["min_scaled_quality"].max() + 0.05]
    ax.plot(limits, limits, color="#999", lw=0.8, ls="--")
    ax.set_xlabel("measured min scaled quality")
    ax.set_ylabel("predicted (out-of-fold)")
    ax.set_title("Predicted before meshing", loc="left", fontsize=10)
    ax.legend(fontsize=6.5, frameon=False, loc="upper left")
    _save(fig, "fig5_quality_prediction")


def main() -> None:
    pool = production_pool(load_attempts())
    recorded = pool[pool["campaign"] == HEADLINE_CAMPAIGN]
    observations = outcome_matrix(pool)
    print("writing figures:")
    figure_retry_tail(recorded)
    figure_worst_case(recorded)
    figure_coverage(observations)
    figure_policies()
    figure_quality_prediction()


if __name__ == "__main__":
    main()
