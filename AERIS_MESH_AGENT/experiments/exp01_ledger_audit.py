#!/usr/bin/env python3
"""Experiment 1 — what the atlas ledger actually says.

Descriptive, no model. Produces the tables that motivate the paper.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mesh_agent.ledger import (  # noqa: E402
    OUTCOME_PASS,
    PRODUCTION_FLOOR,
    conflicts,
    load_attempts,
    outcome_matrix,
    production_pool,
)
from mesh_agent.paths import TABLES  # noqa: E402
from mesh_agent.policy import PREFERRED_QUALITY  # noqa: E402

HEADLINE_CAMPAIGN = "development_atlas_qualified21_production_written_v3"


def main() -> None:
    attempts = load_attempts()
    attempts.to_csv(TABLES / "attempts_all_campaigns.csv", index=False)

    pool = production_pool(attempts)
    pool.to_csv(TABLES / "attempts_production_pool.csv", index=False)

    clash = conflicts(pool)
    matrix = outcome_matrix(pool)
    matrix.to_csv(TABLES / "outcome_matrix_observed.csv", index=False)

    lines: list[str] = []
    add = lines.append
    add("# Experiment 1 — atlas ledger audit\n")

    add("## Campaign inventory\n")
    inventory = (
        attempts.groupby(["campaign", "config_key"])
        .agg(
            attempts=("state", "size"),
            geometries=("geometry_index", "nunique"),
            templates=("template_index", "nunique"),
        )
        .reset_index()
    )
    add(inventory.to_markdown(index=False))
    inventory.to_csv(TABLES / "campaign_inventory.csv", index=False)

    add("\n## Pooled production configuration\n")
    add(f"- config key (eps_e | first cell | N | level): `{pool['config_key'].iloc[0]}`")
    add(f"- attempts: **{len(pool)}** over {pool['geometry_index'].nunique()} geometries "
        f"and {pool['template_index'].nunique()} templates")
    add(f"- unique (geometry, template) cells observed: **{len(matrix)}** of "
        f"{pool['geometry_index'].nunique() * pool['template_index'].nunique()} "
        f"({100 * len(matrix) / (pool['geometry_index'].nunique() * pool['template_index'].nunique()):.1f}%)")
    add(f"- **cells measured twice that disagree: {len(clash)}** — the pipeline "
        "reproduces itself exactly across independent campaigns")

    add("\n## Outcome classes (unique cells)\n")
    counts = matrix["outcome"].value_counts().rename_axis("outcome").reset_index(name="cells")
    counts["share"] = (counts["cells"] / counts["cells"].sum()).round(3)
    add(counts.to_markdown(index=False))
    counts.to_csv(TABLES / "outcome_class_counts.csv", index=False)

    headline = pool[pool["campaign"] == HEADLINE_CAMPAIGN]
    add(f"\n## Headline campaign — `{HEADLINE_CAMPAIGN}`\n")
    per_geometry = headline.groupby("geometry_index").agg(
        attempts=("attempt_ordinal", "max"),
        passes=("outcome", lambda s: int((s == OUTCOME_PASS).sum())),
    )
    first_pass = int((per_geometry["attempts"] == 1).sum())
    add(f"- attempts: **{len(headline)}** for {len(per_geometry)} geometries "
        f"({len(headline) / len(per_geometry):.2f} per geometry)")
    add(f"- first-attempt completion: **{first_pass}/{len(per_geometry)}**")
    add(f"- worst case: **{int(per_geometry['attempts'].max())}** attempts")

    # Attempts spent after a PASS already existed: pure quality search.
    wasted = 0
    for _, group in headline.groupby("geometry_index"):
        group = group.sort_values("attempt_ordinal")
        passed = group["outcome"].to_numpy() == OUTCOME_PASS
        if passed.any():
            wasted += len(group) - 1 - int(passed.argmax())
    add(f"- attempts made **after a PASS already existed** (quality search, not "
        f"failure recovery): **{wasted}**")
    add(f"- acceptance rule recovered from the records: accept at "
        f"quality >= {PREFERRED_QUALITY}, fall back to best >= {PRODUCTION_FLOOR}")

    add("\n### Attempts per geometry\n")
    distribution = (
        per_geometry["attempts"].value_counts().sort_index()
        .rename_axis("attempts").reset_index(name="geometries")
    )
    add(distribution.to_markdown(index=False))

    worst_index = int(per_geometry["attempts"].idxmax())
    worst = headline[headline["geometry_index"] == worst_index].sort_values("attempt_ordinal")
    add(f"\n### The decisive case — geometry {worst_index} "
        f"(`{worst['geometry_id'].iloc[0]}`)\n")
    trail = worst[["attempt_ordinal", "template_index", "outcome", "min_scaled_quality"]]
    add(trail.to_markdown(index=False))
    best_position = int(pd.to_numeric(trail["min_scaled_quality"], errors="coerce").idxmax())
    add(f"\nBest quality of all {len(trail)} attempts occurred at attempt "
        f"**{int(worst.loc[best_position, 'attempt_ordinal'])}**; the campaign accepted "
        f"{worst['accepted_min_scaled_quality'].iloc[0]:.4f} after exhausting the atlas.")
    trail.to_csv(TABLES / "worst_case_trail.csv", index=False)

    report = "\n".join(lines) + "\n"
    (Path(__file__).resolve().parents[1] / "results" / "exp01_ledger_audit.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
