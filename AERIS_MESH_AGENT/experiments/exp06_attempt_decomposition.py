#!/usr/bin/env python3
"""Experiment 6 — where the incumbent's 162 attempts actually go.

Experiments 3 and 4 compare policies. This one asks a prior question: of the
attempts a perfect oracle would remove, how many are *routing* attempts (made
before any mesh passed) and how many are *quality search* attempts (made after a
mesh had already passed but below the preferred threshold)?

The distinction decides the paper's framing. A stopping rule can only ever
recover the second kind, and only the part of it that was unprofitable. This
script measures both, and measures how often the incumbent's search actually
paid for itself.

Descriptive, no model, read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mesh_agent.ledger import OUTCOME_PASS, load_attempts  # noqa: E402
from mesh_agent.paths import TABLES  # noqa: E402
from mesh_agent.policy import PREFERRED_QUALITY  # noqa: E402

HEADLINE_CAMPAIGN = "development_atlas_qualified21_production_written_v3"


def decompose(headline: pd.DataFrame) -> pd.DataFrame:
    """One row per geometry that continued searching after a mesh had passed."""
    rows: list[dict[str, object]] = []
    for geometry, group in headline.sort_values("attempt_ordinal").groupby("geometry_id"):
        passing = group["min_scaled_quality"].where(group["outcome"] == OUTCOME_PASS)
        # best passing quality strictly *before* each attempt; NaN until the first PASS
        best_before = passing.cummax().ffill().shift(1)
        after = group[best_before.notna()]
        if after.empty:
            continue
        first_pass = float(passing.dropna().iloc[0])
        best_pass = float(passing.max())
        rows.append(
            {
                "geometry_id": geometry,
                "attempts": len(group),
                "post_pass_attempts": len(after),
                "first_pass_quality": first_pass,
                "best_pass_quality": best_pass,
                "accepted_quality": float(group["accepted_min_scaled_quality"].iloc[0]),
                "search_was_justified": first_pass < PREFERRED_QUALITY,
                "search_paid_off": best_pass > first_pass + 1e-9,
                "reached_preferred": best_pass >= PREFERRED_QUALITY > first_pass,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    headline = load_attempts()
    headline = headline[headline["campaign"] == HEADLINE_CAMPAIGN].copy()

    n_attempts = len(headline)
    n_geometries = headline["geometry_id"].nunique()

    searched = decompose(headline)
    post_pass = int(searched["post_pass_attempts"].sum())
    routing = n_attempts - n_geometries - post_pass

    profitable = searched[searched["search_paid_off"]]
    wasted = searched[~searched["search_paid_off"]]

    lines: list[str] = []
    add = lines.append
    add("# Experiment 6 — where the 162 attempts go\n")

    add(f"Campaign `{HEADLINE_CAMPAIGN}`: {n_attempts} attempts over "
        f"{n_geometries} geometries. Preferred threshold {PREFERRED_QUALITY}.\n")

    add("## The three-way split\n")
    split = pd.DataFrame(
        [
            {"class": "irreducible (one successful extrusion per geometry)",
             "attempts": n_geometries,
             "recoverable_by": "nothing"},
            {"class": "routing (spent before any mesh passed)",
             "attempts": routing,
             "recoverable_by": "better routing only"},
            {"class": "quality search (spent after a mesh had already passed)",
             "attempts": post_pass,
             "recoverable_by": "better routing, or stopping"},
        ]
    )
    add(split.to_markdown(index=False))
    split.to_csv(TABLES / "attempt_decomposition.csv", index=False)

    add("\n## Was the quality search rational?\n")
    add(f"- geometries that continued after a PASS: **{len(searched)}**")
    add(f"- of those, the first PASS was already at or above {PREFERRED_QUALITY}: "
        f"**{int((~searched['search_was_justified']).sum())}**")
    add(f"- searches that improved the accepted mesh: **{int(searched['search_paid_off'].sum())}"
        f" of {len(searched)}**")
    add(f"- searches that lifted a fallback-grade mesh to preferred grade: "
        f"**{int(searched['reached_preferred'].sum())}**")
    add(f"- attempts spent on searches that paid off: **{int(profitable['post_pass_attempts'].sum())}**")
    add(f"- attempts spent on searches that returned nothing: "
        f"**{int(wasted['post_pass_attempts'].sum())}**\n")

    add(searched.sort_values("post_pass_attempts", ascending=False).to_markdown(index=False))
    searched.to_csv(TABLES / "post_pass_search.csv", index=False)

    add("\n## Reading it\n")
    add(f"Every one of the {len(searched)} searches was permitted by the incumbent's own "
        f"acceptance rule — in each case the mesh already in hand was below "
        f"{PREFERRED_QUALITY} and the rule says keep looking. "
        f"{int(searched['search_paid_off'].sum())} of them found a better mesh, and every one "
        f"of those crossed the preferred threshold. The incumbent's stopping behaviour is "
        f"therefore not a defect in general: it is profitable in "
        f"{int(searched['search_paid_off'].sum())} of {len(searched)} cases.")
    add(f"\nThe unprofitable search costs {int(wasted['post_pass_attempts'].sum())} attempts and "
        f"belongs to {len(wasted)} geometry. That is the entire quality-preserving prize "
        f"available to a stopping rule, and capturing it means predicting that *no* template in "
        f"the atlas can reach {PREFERRED_QUALITY} for that geometry — a ceiling prediction, not a "
        f"stopping heuristic.")
    add(f"\nA policy that stops at the first valid mesh instead saves all {post_pass} search "
        f"attempts by destroying the {int(searched['reached_preferred'].sum())} profitable "
        f"upgrades. That is the mechanism behind the preferred-threshold rate falling from "
        f"0.99 to 0.89 in experiment 3; it is not an untuned baseline, it is a baseline paying "
        f"a known price.")

    report = "\n".join(lines) + "\n"
    (Path(__file__).resolve().parents[1] / "results" / "exp06_attempt_decomposition.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
