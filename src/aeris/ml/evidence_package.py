"""Evidence packaging for AERIS Paper-1 / ML trust workflows.

This module does not rerun solvers or retrain models. It collects/indexes the
existing trust-chain artifacts that already prove the dataset/model state:
EDA, learning curves, repeated grouped CV, per-regime residuals, model-quality
audit, promotion manifests, inference/confidence reports, and optional workflow
reports.
"""
from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from aeris.ml.fingerprints import file_sha256
from aeris.ml.manifest import utc_now_iso

EVIDENCE_PACKAGE_SCHEMA_VERSION = "aeris.evidence_package.v1"


@dataclass(frozen=True)
class EvidencePackageArtifacts:
    output_dir: Path
    manifest_path: Path
    summary_md_path: Path
    artifact_index_csv_path: Path
    copied_artifacts_dir: Path | None = None


@dataclass(frozen=True)
class EvidencePackageResult:
    status: str
    manifest: dict[str, Any]
    artifacts: EvidencePackageArtifacts


def _safe_load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_json_status": "invalid", "_error": str(exc)}
    if not isinstance(data, dict):
        return {"_json_status": "not_object", "_type": type(data).__name__}
    data.setdefault("_json_status", "ok")
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _slug(text: str) -> str:
    chars = []
    for ch in str(text).strip().lower():
        if ch.isalnum():
            chars.append(ch)
        elif ch in {"-", "_", "."}:
            chars.append(ch)
        else:
            chars.append("_")
    out = "".join(chars).strip("._-")
    return out or "artifact"


def _copy_file(source: Path, *, output_dir: Path, category: str, label: str) -> Path:
    dest_dir = output_dir / "artifacts" / _slug(category)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{_slug(label)}__{source.name}"
    # Avoid accidental overwrite if two files share name/label.
    if dest.exists() and dest.resolve() != source.resolve():
        stem = dest.stem
        suffix = dest.suffix
        i = 2
        while True:
            candidate = dest.with_name(f"{stem}_{i}{suffix}")
            if not candidate.exists():
                dest = candidate
                break
            i += 1
    shutil.copy2(source, dest)
    return dest


def _artifact_row(
    *,
    category: str,
    label: str,
    role: str,
    source_path: Path,
    required: bool,
    output_dir: Path,
    copy_artifacts: bool,
) -> dict[str, Any]:
    exists = source_path.exists() and source_path.is_file()
    copied_path: Path | None = None
    if exists and copy_artifacts:
        copied_path = _copy_file(source_path, output_dir=output_dir, category=category, label=label)

    return {
        "category": category,
        "label": label,
        "role": role,
        "required": bool(required),
        "status": "present" if exists else "missing_required" if required else "missing_optional",
        "source_path": str(source_path),
        "package_path": str(copied_path) if copied_path is not None else None,
        "sha256": file_sha256(source_path) if exists else None,
        "size_bytes": source_path.stat().st_size if exists else None,
    }


def _add_file(
    rows: list[dict[str, Any]],
    *,
    category: str,
    label: str,
    path: Path,
    required: bool = False,
    role: str = "evidence",
    output_dir: Path,
    copy_artifacts: bool,
) -> None:
    rows.append(
        _artifact_row(
            category=category,
            label=label,
            role=role,
            source_path=path,
            required=required,
            output_dir=output_dir,
            copy_artifacts=copy_artifacts,
        )
    )


def _add_glob(
    rows: list[dict[str, Any]],
    *,
    category: str,
    label_prefix: str,
    root: Path,
    pattern: str,
    output_dir: Path,
    copy_artifacts: bool,
) -> None:
    if not root.exists():
        return
    for path in sorted(root.glob(pattern)):
        if path.is_file():
            _add_file(
                rows,
                category=category,
                label=f"{label_prefix}:{path.stem}",
                path=path,
                required=False,
                role="supporting_artifact",
                output_dir=output_dir,
                copy_artifacts=copy_artifacts,
            )


def _add_extra_artifacts(
    rows: list[dict[str, Any]],
    *,
    extra_artifacts: Iterable[str | Path] | None,
    output_dir: Path,
    copy_artifacts: bool,
) -> None:
    if not extra_artifacts:
        return
    for item in extra_artifacts:
        path = Path(item).expanduser().resolve()
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    _add_file(
                        rows,
                        category="extra",
                        label=f"extra:{child.stem}",
                        path=child,
                        role="operator_supplied",
                        output_dir=output_dir,
                        copy_artifacts=copy_artifacts,
                    )
        else:
            _add_file(
                rows,
                category="extra",
                label=f"extra:{path.stem}",
                path=path,
                role="operator_supplied",
                output_dir=output_dir,
                copy_artifacts=copy_artifacts,
            )


def _read_first_present(rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    for row in rows:
        if row.get("label") == label and row.get("status") == "present":
            return _safe_load_json(Path(str(row["source_path"])))
    return {}


def _brief_json_status(report: dict[str, Any]) -> dict[str, Any]:
    if not report:
        return {}
    keys = [
        "schema_version",
        "status",
        "passed",
        "promotion_ready",
        "promotion_ready_at_time_of_promotion",
        "promotion_forced",
        "row_count",
        "kept_rows",
        "rejected_rows",
        "n_rows",
        "n_groups",
        "n_regime_rows",
    ]
    return {k: report.get(k) for k in keys if k in report}


def _build_key_findings(rows: list[dict[str, Any]]) -> dict[str, Any]:
    dataset_promotion = _read_first_present(rows, "dataset_promotion_manifest")
    model_promotion = _read_first_present(rows, "model_promotion_manifest")
    curation = _read_first_present(rows, "curation_report")
    eda = _read_first_present(rows, "eda_report")
    learning_curves = _read_first_present(rows, "learning_curves_report")
    repeated_cv = _read_first_present(rows, "repeated_grouped_cv_report")
    regime = _read_first_present(rows, "per_regime_residuals_report")
    model_quality = _read_first_present(rows, "model_quality_report")
    confidence = _read_first_present(rows, "prediction_confidence_report")
    workflow_validation = _read_first_present(rows, "workflow_validation_report")

    return {
        "dataset_promotion": _brief_json_status(dataset_promotion),
        "model_promotion": _brief_json_status(model_promotion),
        "curation": _brief_json_status(curation),
        "eda": _brief_json_status(eda.get("metadata", eda)),
        "learning_curves": _brief_json_status(learning_curves),
        "repeated_grouped_cv": _brief_json_status(repeated_cv),
        "per_regime_residuals": _brief_json_status(regime),
        "model_quality": _brief_json_status(model_quality),
        "prediction_confidence": _brief_json_status(confidence),
        "workflow_validation": _brief_json_status(workflow_validation),
    }


def _write_artifact_index(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "category",
        "label",
        "role",
        "required",
        "status",
        "source_path",
        "package_path",
        "sha256",
        "size_bytes",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _write_summary_md(path: Path, manifest: dict[str, Any]) -> None:
    counts = manifest.get("counts", {})
    findings = manifest.get("key_findings", {})
    lines = [
        "# AERIS Evidence Package",
        "",
        f"Status: **{manifest.get('status')}**",
        f"Created: `{manifest.get('created_at_utc')}`",
        "",
        "## Inputs",
        "",
        f"- Dataset: `{manifest.get('dataset')}`",
        f"- Model run: `{manifest.get('model_run_dir') or 'not provided'}`",
        f"- Workflow: `{manifest.get('workflow') or 'not provided'}`",
        "",
        "## Artifact counts",
        "",
        f"- Present: {counts.get('present', 0)}",
        f"- Missing optional: {counts.get('missing_optional', 0)}",
        f"- Missing required: {counts.get('missing_required', 0)}",
        "",
        "## Key findings",
        "",
    ]
    for name, payload in findings.items():
        lines.append(f"### {name.replace('_', ' ').title()}")
        if payload:
            for key, value in payload.items():
                lines.append(f"- `{key}`: `{value}`")
        else:
            lines.append("- No report available in this package.")
        lines.append("")

    lines += [
        "## Artifact index",
        "",
        "See `evidence_artifact_index.csv` for paths, hashes, and missing evidence.",
        "",
        "## Operator note",
        "",
        "This package indexes existing evidence. It does not rerun solvers, retrain models, or certify the aircraft.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_evidence_package(
    *,
    dataset: str | Path,
    model_run_dir: str | Path | None = None,
    confidence_dir: str | Path | None = None,
    workflow: str | Path | None = None,
    output_dir: str | Path | None = None,
    extra_artifacts: Iterable[str | Path] | None = None,
    allow_missing: bool = False,
    copy_artifacts: bool = True,
) -> EvidencePackageResult:
    """Build a compact evidence package from already-generated AERIS artifacts."""
    dataset_root = Path(dataset).expanduser().resolve()
    if not dataset_root.exists() or not dataset_root.is_dir():
        raise FileNotFoundError(f"Dataset directory does not exist: {dataset_root}")

    model_root = Path(model_run_dir).expanduser().resolve() if model_run_dir is not None else None
    if model_root is not None and (not model_root.exists() or not model_root.is_dir()):
        raise FileNotFoundError(f"Model run directory does not exist: {model_root}")

    confidence_root = Path(confidence_dir).expanduser().resolve() if confidence_dir is not None else None
    workflow_root = Path(workflow).expanduser().resolve() if workflow is not None else None

    output_root = Path(output_dir).expanduser().resolve() if output_dir is not None else dataset_root / "paper1_evidence_package"
    output_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []

    def add(category: str, label: str, path: Path, *, required: bool = False, role: str = "evidence") -> None:
        _add_file(
            rows,
            category=category,
            label=label,
            path=path,
            required=required,
            role=role,
            output_dir=output_root,
            copy_artifacts=copy_artifacts,
        )

    # Dataset trust chain.
    add("dataset", "dataset_promotion_manifest", dataset_root / "promotion_manifest.json", required=True)
    add("dataset", "curation_report", dataset_root / "curation_report.json")
    add("dataset", "final_run_summary", dataset_root / "final_run_summary.json")
    add("dataset", "curated_aero_dataset", dataset_root / "curated_aero_dataset.csv")
    add("dataset", "rejected_aero_rows", dataset_root / "rejected_aero_rows.csv")
    _add_glob(rows, category="dataset_qc", label_prefix="qc_json", root=dataset_root / "qc", pattern="**/*.json", output_dir=output_root, copy_artifacts=copy_artifacts)

    # Dataset/model diagnostics.
    add("eda", "eda_report", dataset_root / "eda" / "eda_report.json")
    add("eda", "eda_comparison_report", dataset_root / "eda" / "eda_comparison_report.json")
    _add_glob(rows, category="eda", label_prefix="eda_plot", root=dataset_root / "eda" / "plots", pattern="*.png", output_dir=output_root, copy_artifacts=copy_artifacts)

    add("learning_curves", "learning_curves_report", dataset_root / "learning_curves" / "learning_curves_report.json")
    add("learning_curves", "learning_curves_summary", dataset_root / "learning_curves" / "learning_curves_summary.md")
    _add_glob(rows, category="learning_curves", label_prefix="learning_curve_plot", root=dataset_root / "learning_curves" / "plots", pattern="*.png", output_dir=output_root, copy_artifacts=copy_artifacts)
    _add_glob(rows, category="learning_curves", label_prefix="learning_curve_table", root=dataset_root / "learning_curves", pattern="*.csv", output_dir=output_root, copy_artifacts=copy_artifacts)

    add("repeated_grouped_cv", "repeated_grouped_cv_report", dataset_root / "repeated_grouped_cv" / "repeated_grouped_cv_report.json")
    add("repeated_grouped_cv", "repeated_grouped_cv_summary", dataset_root / "repeated_grouped_cv" / "repeated_grouped_cv_summary.md")
    _add_glob(rows, category="repeated_grouped_cv", label_prefix="repeated_cv_plot", root=dataset_root / "repeated_grouped_cv" / "plots", pattern="*.png", output_dir=output_root, copy_artifacts=copy_artifacts)
    _add_glob(rows, category="repeated_grouped_cv", label_prefix="repeated_cv_table", root=dataset_root / "repeated_grouped_cv", pattern="*.csv", output_dir=output_root, copy_artifacts=copy_artifacts)

    add("per_regime_residuals", "per_regime_residuals_report", dataset_root / "per_regime_residuals" / "per_regime_residuals_report.json")
    add("per_regime_residuals", "per_regime_residuals_summary", dataset_root / "per_regime_residuals" / "per_regime_residuals_summary.md")
    _add_glob(rows, category="per_regime_residuals", label_prefix="regime_residual_plot", root=dataset_root / "per_regime_residuals" / "plots", pattern="*.png", output_dir=output_root, copy_artifacts=copy_artifacts)
    _add_glob(rows, category="per_regime_residuals", label_prefix="regime_residual_table", root=dataset_root / "per_regime_residuals", pattern="*.csv", output_dir=output_root, copy_artifacts=copy_artifacts)

    # Model trust chain.
    if model_root is not None:
        add("model", "ml_run_manifest", model_root / "ml_run_manifest.json")
        add("model", "train_config", model_root / "train_config.json")
        add("model", "metrics", model_root / "metrics.json")
        add("model", "model_promotion_manifest", model_root / "model_promotion_manifest.json", required=True)
        add("model", "model_card", model_root / "model_card.json")
        add("model", "training_envelope", model_root / "training_envelope.json")
        add("model_quality", "model_quality_report", model_root / "quality" / "model_audit" / "model_quality_report.json")
        add("model_quality", "residual_audit", model_root / "quality" / "model_audit" / "residual_audit.csv")
        add("promotion_gates", "promotion_gate_suggestions", model_root / "promotion_gate_suggestions" / "promotion_gate_suggestions.json")
        add("promotion_gates", "promotion_gates_template", model_root / "promotion_gate_suggestions" / "promotion_gates_template.yaml")
        _add_glob(rows, category="model_diagnostics", label_prefix="diagnostic", root=model_root / "diagnostics", pattern="**/*", output_dir=output_root, copy_artifacts=copy_artifacts)
        _add_glob(rows, category="model_plots", label_prefix="plot", root=model_root / "plots", pattern="*.png", output_dir=output_root, copy_artifacts=copy_artifacts)

    if confidence_root is not None:
        add("prediction_confidence", "prediction_confidence_report", confidence_root / "prediction_confidence_report.json")
        add("prediction_confidence", "prediction_confidence_csv", confidence_root / "prediction_confidence.csv")

    if workflow_root is not None:
        add("workflow", "workflow_manifest", workflow_root / "workflow_manifest.json")
        add("workflow", "workflow_status", workflow_root / "workflow_status.json")
        add("workflow", "workflow_validation_report", workflow_root / "workflow_validation_report.json")
        add("workflow", "workflow_events", workflow_root / "workflow_events.jsonl")

    _add_extra_artifacts(rows, extra_artifacts=extra_artifacts, output_dir=output_root, copy_artifacts=copy_artifacts)

    counts = {
        "present": sum(1 for row in rows if row["status"] == "present"),
        "missing_optional": sum(1 for row in rows if row["status"] == "missing_optional"),
        "missing_required": sum(1 for row in rows if row["status"] == "missing_required"),
        "total_indexed": len(rows),
    }
    if counts["missing_required"] > 0:
        status = "failed_missing_required_artifacts"
    elif counts["missing_optional"] > 0:
        status = "completed_with_missing_optional_artifacts"
    else:
        status = "complete"

    artifact_index_path = output_root / "evidence_artifact_index.csv"
    manifest_path = output_root / "evidence_package_manifest.json"
    summary_md_path = output_root / "evidence_package_summary.md"

    key_findings = _build_key_findings(rows)
    manifest: dict[str, Any] = {
        "schema_version": EVIDENCE_PACKAGE_SCHEMA_VERSION,
        "created_at_utc": utc_now_iso(),
        "status": status,
        "purpose": "index and optionally copy existing AERIS dataset/model/workflow evidence for Paper 1 reporting",
        "dataset": str(dataset_root),
        "model_run_dir": str(model_root) if model_root is not None else None,
        "confidence_dir": str(confidence_root) if confidence_root is not None else None,
        "workflow": str(workflow_root) if workflow_root is not None else None,
        "output_dir": str(output_root),
        "copy_artifacts": bool(copy_artifacts),
        "allow_missing": bool(allow_missing),
        "counts": counts,
        "key_findings": key_findings,
        "artifacts": {
            "evidence_package_manifest_json": str(manifest_path),
            "evidence_package_summary_md": str(summary_md_path),
            "evidence_artifact_index_csv": str(artifact_index_path),
            "copied_artifacts_dir": str(output_root / "artifacts") if copy_artifacts else None,
        },
        "artifact_index_preview": rows[:20],
    }

    _write_artifact_index(artifact_index_path, rows)
    _write_summary_md(summary_md_path, manifest)
    _write_json(manifest_path, manifest)

    artifacts = EvidencePackageArtifacts(
        output_dir=output_root,
        manifest_path=manifest_path,
        summary_md_path=summary_md_path,
        artifact_index_csv_path=artifact_index_path,
        copied_artifacts_dir=(output_root / "artifacts") if copy_artifacts else None,
    )
    result = EvidencePackageResult(status=status, manifest=manifest, artifacts=artifacts)

    if counts["missing_required"] > 0 and not allow_missing:
        raise ValueError(
            "Evidence package is missing required artifacts; "
            f"see {artifact_index_path}. Use --allow-missing for pilot/debug packages."
        )
    return result
