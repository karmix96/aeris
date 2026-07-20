"""
Study execution: run every variant through the ordinary case runner and
collect one comparison/sensitivity report.

Each variant is a full, independent case run (own workdir, own manifest
chain) — nothing is shared or mutated between variants, so a study is just
an index over ordinary, individually-reproducible case runs.  This keeps
the "one case = one reviewable artifact" property of ``aeris.cfd.case``
intact at the study level: ``study_report.json`` never carries a number
that isn't also sitting in a variant's own ``solve_report.json`` /
``verification.json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from aeris.cfd.case.runner import CaseError, StageResult, run_case
from aeris.cfd.study.loader import build_variant_case_spec
from aeris.cfd.study.spec import STUDY_REPORT_SCHEMA_VERSION, StudySpec, StudyVariant
from aeris.common.config import file_sha256

STUDY_REPORT_SCHEMA_VERSION_VALUE = STUDY_REPORT_SCHEMA_VERSION


@dataclass(frozen=True)
class VariantResult:
    variant: str
    status: str  # "ok" | "failed" | "dry_run"
    workdir: Path
    forces: dict[str, float] = field(default_factory=dict)
    final_resrho: float | None = None
    error: str | None = None
    stage_results: dict[str, StageResult] = field(default_factory=dict)


def _run_variant(
    study: StudySpec,
    variant: StudyVariant,
    study_dir: Path,
    *,
    dry_run: bool,
    echo: Callable[[str], None],
) -> VariantResult:
    variant_dir = study_dir / variant.name
    try:
        spec = build_variant_case_spec(study, variant)
    except ValueError as exc:
        return VariantResult(
            variant=variant.name, status="failed", workdir=variant_dir, error=str(exc)
        )

    echo(f"[study {study.name}] variant '{variant.name}': {variant.description or variant.patch}")
    try:
        results = run_case(
            spec, workdir=variant_dir, stages=study.stages, dry_run=dry_run, echo=echo
        )
    except CaseError as exc:
        return VariantResult(
            variant=variant.name,
            status="failed",
            workdir=variant_dir,
            error=str(exc),
            stage_results={},
        )

    if dry_run:
        return VariantResult(
            variant=variant.name, status="dry_run", workdir=variant_dir, stage_results=results
        )

    solve_result = results.get("solve")
    if solve_result is None or solve_result.status not in ("converged", "ok"):
        status = solve_result.status if solve_result is not None else "skipped"
        return VariantResult(
            variant=variant.name,
            status="failed" if status not in ("converged", "ok") else status,
            workdir=variant_dir,
            forces=dict(solve_result.details.get("forces", {})) if solve_result else {},
            final_resrho=solve_result.details.get("final_resrho") if solve_result else None,
            error=None if status in ("converged", "ok") else f"solve stage status={status}",
            stage_results=results,
        )

    return VariantResult(
        variant=variant.name,
        status="ok",
        workdir=variant_dir,
        forces=dict(solve_result.details.get("forces", {})),
        final_resrho=solve_result.details.get("final_resrho"),
        stage_results=results,
    )


def _deltas(
    rows: list[VariantResult], baseline_name: str | None, quantities: tuple[str, ...]
) -> dict[str, object]:
    ok_rows = {r.variant: r for r in rows if r.status == "ok"}
    baseline = ok_rows.get(baseline_name) if baseline_name else None
    if baseline is None:
        return {}
    deltas: dict[str, object] = {}
    for name, row in ok_rows.items():
        if name == baseline_name:
            continue
        per_qty: dict[str, object] = {}
        for qty in quantities:
            b_val = baseline.forces.get(qty)
            v_val = row.forces.get(qty)
            if b_val is None or v_val is None:
                continue
            abs_delta = v_val - b_val
            rel_delta = (abs_delta / b_val) * 100.0 if b_val != 0 else float("nan")
            per_qty[qty] = {"absolute": abs_delta, "relative_percent": rel_delta}
        deltas[name] = per_qty
    return deltas


def run_study(
    study: StudySpec,
    *,
    workdir: Path,
    dry_run: bool = False,
    echo: Callable[[str], None] | None = None,
) -> dict[str, object]:
    """Execute every variant; write and return ``study_report.json``."""
    say = echo or (lambda _msg: None)
    study_dir = workdir.expanduser().resolve()
    study_dir.mkdir(parents=True, exist_ok=True)

    say(f"[study {study.name}] {len(study.variants)} variant(s), stages={list(study.stages)}")
    rows = [
        _run_variant(study, variant, study_dir, dry_run=dry_run, echo=say)
        for variant in study.variants
    ]

    variants_payload = []
    for row in rows:
        manifest_path = row.workdir / "case_manifest.json"
        variants_payload.append(
            {
                "name": row.variant,
                "status": row.status,
                "workdir": str(row.workdir),
                "forces": row.forces,
                "final_resrho": row.final_resrho,
                "error": row.error,
                "case_manifest": str(manifest_path) if manifest_path.is_file() else None,
                "case_manifest_sha256": (
                    file_sha256(manifest_path) if manifest_path.is_file() else None
                ),
            }
        )

    payload = {
        "schema": STUDY_REPORT_SCHEMA_VERSION,
        "study": study.name,
        "study_yaml": str(study.source_path) if study.source_path else None,
        "study_yaml_sha256": (
            file_sha256(study.source_path)
            if study.source_path and Path(study.source_path).is_file()
            else None
        ),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "baseline": study.baseline,
        "quantities": list(study.quantities),
        "variants": variants_payload,
        "deltas_vs_baseline": (
            _deltas(rows, study.baseline, study.quantities) if not dry_run else {}
        ),
    }
    report_path = study_dir / "study_report.json"
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    say(f"[study {study.name}] report: {report_path}")
    return payload
