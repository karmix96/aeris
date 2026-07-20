"""
Active learning → runnable CFD cases (the missing suggestion→execution seam).

``suggest_samples`` ranks candidates and stops at a CSV (its report tracks
batch ingestion as unbuilt, ML-W3B).  This module closes the loop for the
CFD pipeline: it takes the ranked candidates and a template case YAML and
emits one ready-to-run ``aeris cfd run`` case per recommended candidate,
with the flight-condition columns injected into ``case.solve.flow``.

Why this design: the emitted artifact is the same reviewable, provenance-
tracked case spec a human would write — the active learner proposes
*cases*, not opaque solver invocations, so every AI-chosen sample passes
through the identical verification chain (mesh QC, effective-options
manifests, solve verification) as a human-chosen one.  That is the
trustworthy-AI-in-CFD loop: surrogate uncertainty picks the point, the
verified CFD pipeline produces the label, the gate decides if it enters
the training set.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

# ranked-candidate column -> case.solve.flow key
FLOW_COLUMN_MAP = {
    "alpha_deg": "alpha",
    "alpha": "alpha",
    "mach": "mach",
    "reynolds": "reynolds",
    "re_number": "reynolds",
    "temperature": "temperature",
}


@dataclass(frozen=True)
class EmittedCase:
    candidate_id: str
    case_yaml: Path
    flow: dict[str, float]


def emit_cfd_cases(
    ranked_csv: str | Path,
    template_case_yaml: str | Path,
    output_dir: str | Path,
    *,
    top_n: int | None = None,
    only_recommended: bool = True,
) -> list[EmittedCase]:
    """Emit one case YAML per recommended candidate.

    The template must be a valid ``aeris.cfd.case.v1`` file with a
    ``solve`` section; each emitted case overrides ``case.name`` (suffixed
    with the candidate id) and the flow-condition keys found in the ranked
    CSV columns (``FLOW_COLUMN_MAP``).
    """
    ranked = pd.read_csv(ranked_csv)
    if "candidate_id" not in ranked.columns:
        raise ValueError(f"{ranked_csv}: missing 'candidate_id' column")
    if only_recommended and "recommended" in ranked.columns:
        ranked = ranked[ranked["recommended"].astype(bool)]
    if "active_learning_rank" in ranked.columns:
        ranked = ranked.sort_values("active_learning_rank")
    if top_n is not None:
        ranked = ranked.head(top_n)

    template = yaml.safe_load(Path(template_case_yaml).read_text(encoding="utf-8"))
    if not isinstance(template, dict) or "case" not in template:
        raise ValueError(f"{template_case_yaml}: not an aeris.cfd.case.v1 file")
    if "solve" not in template["case"]:
        raise ValueError(f"{template_case_yaml}: template must contain a case.solve section")

    flow_columns = {
        column: key for column, key in FLOW_COLUMN_MAP.items() if column in ranked.columns
    }
    if not flow_columns:
        raise ValueError(
            f"{ranked_csv}: no flow-condition columns found "
            f"(looked for {sorted(FLOW_COLUMN_MAP)})"
        )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    base_name = str(template["case"].get("name", "case"))

    emitted: list[EmittedCase] = []
    for _, row in ranked.iterrows():
        candidate_id = str(row["candidate_id"])
        case = yaml.safe_load(yaml.safe_dump(template))  # deep copy
        case["case"]["name"] = f"{base_name}_{candidate_id}"
        flow = dict(case["case"]["solve"].get("flow") or {})
        applied: dict[str, float] = {}
        for column, key in flow_columns.items():
            value = row[column]
            if pd.notna(value):
                flow[key] = float(value)
                applied[key] = float(value)
        case["case"]["solve"]["flow"] = flow
        case["case"]["provenance"] = {
            "emitted_by": "aeris.ml.active_learning.emit_cfd",
            "ranked_csv": str(ranked_csv),
            "candidate_id": candidate_id,
        }
        case_path = output_path / f"case_{candidate_id}.yaml"
        case_path.write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")
        emitted.append(EmittedCase(candidate_id=candidate_id, case_yaml=case_path, flow=applied))
    return emitted
