from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .audits import run_scientific_audits
from .baseline import build_baselines
from .common import PipelineError, output_manifest, sha256_file, sha256_object, utc_now, write_json
from .dataset import build_canonical_dataset
from .evidence import QualificationEvidence
from .monitor import scan_campaign, stable_hash, write_monitor_outputs
from .paper import build_paper_package
from .release import create_release

SCHEMA_VERSION = "aeris.incremental_refresh.v1"


def _paper_evidence_hash(qualification_root: Path) -> str:
    paths = []
    for relative in ("reports", "dataset/runs"):
        root = qualification_root / relative
        if root.is_dir():
            paths.extend(path for path in root.rglob("*") if path.is_file())
    for relative in ("dataset/rows.json", "dataset/MANIFEST.json"):
        path = qualification_root / relative
        if path.is_file():
            paths.append(path)
    records = [
        {
            "path": str(path.relative_to(qualification_root)),
            "sha256": stable_hash(path).sha256,
        }
        for path in sorted(set(paths))
    ]
    return sha256_object(records)


def _validate_existing_product(path: Path, product_id: str) -> dict[str, Any]:
    manifest_path = path / "refresh_manifest.json"
    if not manifest_path.is_file():
        raise PipelineError(f"product directory exists without a manifest: {path}")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("product_id") != product_id:
        raise PipelineError(f"product identity mismatch in {path}")
    for item in manifest.get("outputs") or []:
        candidate = path / item["path"]
        if not candidate.is_file() or sha256_file(candidate) != item["sha256"]:
            raise PipelineError(f"immutable product file is missing or changed: {candidate}")
    return manifest


def refresh_research_products(
    qualification_root: Path,
    run_roots: Iterable[Path],
    output_root: Path,
    *,
    lock_path: Path | None = None,
    stale_after_seconds: float = 1800.0,
    train_predictors: bool = False,
    pod_rank: int = 16,
    latent_dim: int = 16,
    epochs: int = 250,
    seed: int = 42,
) -> dict[str, Any]:
    """Scan, release, rebuild, and audit without mutating campaign inputs."""

    qualification_root = Path(qualification_root).resolve()
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    scan = scan_campaign(
        qualification_root,
        run_roots,
        lock_path=lock_path,
        stale_after_seconds=stale_after_seconds,
    )
    monitor_report = write_monitor_outputs(scan, output_root / "monitor")
    release_manifest = create_release(scan, output_root / "releases")
    release_id = release_manifest["release_id"]
    release_path = output_root / "releases" / release_id
    settings = {
        "train_predictors": bool(train_predictors),
        "pod_rank": int(pod_rank),
        "latent_dim": int(latent_dim) if train_predictors else None,
        "epochs": int(epochs) if train_predictors else None,
        "seed": int(seed) if train_predictors else None,
        "paper_evidence_hash": _paper_evidence_hash(qualification_root),
    }
    settings_hash = sha256_object(settings)[:10]
    product_id = f"{release_id}-{settings_hash}"
    product_root = output_root / "products"
    product_root.mkdir(exist_ok=True)
    product = product_root / product_id
    if product.exists():
        manifest = _validate_existing_product(product, product_id)
        write_json(
            output_root / "current.json",
            {
                "release_id": release_id,
                "product_id": product_id,
                "path": str(product.relative_to(output_root)),
                "updated_utc": utc_now(),
            },
        )
        return {
            **manifest["summary"],
            "monitor_counts": monitor_report["counts"],
            "reused": True,
        }

    staging = Path(tempfile.mkdtemp(prefix=f".{product_id}.", dir=product_root))
    try:
        paper = build_paper_package(QualificationEvidence(qualification_root), staging / "paper")
        dataset_path = staging / "ai_surface_fields.h5"
        dataset = build_canonical_dataset(
            QualificationEvidence(release_path), dataset_path, include_incomplete=False
        )
        baselines = build_baselines(
            dataset_path,
            staging / "baselines",
            pod_rank=pod_rank,
            latent_dim=latent_dim,
            epochs=epochs,
            seed=seed,
            train_predictors=train_predictors,
        )
        audits = run_scientific_audits(
            dataset_path,
            release_path,
            qualification_root,
            staging / "audits",
        )
        if audits["status"] != "PASS":
            raise PipelineError("scientific audits failed; incremental product was not published")
        summary = {
            "schema_version": SCHEMA_VERSION,
            "release_id": release_id,
            "product_id": product_id,
            "paper_outputs": len(paper["outputs"]),
            "dataset_snapshots": dataset["snapshots"],
            "dataset_topology_families": dataset["topology_families"],
            "dataset_logical_hash": dataset["logical_dataset_hash"],
            "accepted_distinct_geometries": monitor_report["accepted_distinct_geometries"],
            "pod_status": baselines["pod"]["status"],
            "prediction_status": baselines["prediction"]["status"],
            "audit_status": audits["status"],
            "training_was_explicitly_enabled": bool(train_predictors),
        }
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "created_utc": utc_now(),
            "product_id": product_id,
            "release_id": release_id,
            "settings": settings,
            "summary": summary,
            "outputs": output_manifest(staging, exclude={"refresh_manifest.json"}),
        }
        write_json(staging / "refresh_manifest.json", manifest)
        try:
            os.replace(staging, product)
        except OSError:
            if not product.exists():
                raise
            shutil.rmtree(staging)
            manifest = _validate_existing_product(product, product_id)
            summary = manifest["summary"]
        write_json(
            output_root / "current.json",
            {
                "release_id": release_id,
                "product_id": product_id,
                "path": str(product.relative_to(output_root)),
                "updated_utc": utc_now(),
            },
        )
        return {**summary, "monitor_counts": monitor_report["counts"], "reused": False}
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
