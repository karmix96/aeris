from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from .cgns import read_surface
from .common import (
    PipelineError,
    atomic_write_bytes,
    output_manifest,
    sha256_file,
    sha256_object,
    utc_now,
    write_json,
)
from .evidence import QualificationEvidence
from .monitor import (
    SCHEMA_VERSION as MONITOR_SCHEMA_VERSION,
    CampaignRun,
    CampaignScan,
    stable_bytes,
    verify_stable_file,
)

SCHEMA_VERSION = "aeris.accepted_snapshot_release.v2"
PORTABLE_ROW_EXCLUSIONS = frozenset(
    {
        "environment",
        "source_directory",
        "surface_field_path",
        "surface_field_archive",
        "volume_field_path",
        "volume_field_source",
        "volume_field_note",
    }
)
GATE_ROW_FIELDS = (
    "gate_verdict",
    "iterations",
    "orders_dropped",
    "cl_pct",
    "cd_pct",
    "cmy_abs",
)


def _portable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {name: value for name, value in row.items() if name not in PORTABLE_ROW_EXCLUSIONS}


def _release_identity(records: list[CampaignRun]) -> str:
    identities = []
    for record in sorted(records, key=lambda item: item.run_id):
        if record.row is None or record.result is None or record.gate is None:
            raise PipelineError(f"accepted run {record.run_id} lacks release evidence")
        gate = {name: value for name, value in record.gate.items() if name != "directory"}
        result = {name: value for name, value in record.result.items() if name != "grid"}
        identities.append(
            {
                "run_id": record.run_id,
                "source_key": record.source_key,
                "row": _portable_row(record.row),
                "result": result,
                "gate": gate,
                "surface_payload_sha256": record.surface_payload_sha256,
                "input_hashes": {
                    name: evidence.sha256 for name, evidence in sorted(record.inputs.items())
                },
            }
        )
    return sha256_object({"schema_version": SCHEMA_VERSION, "records": identities})


def _normalised_gate(record: CampaignRun) -> dict[str, Any]:
    assert record.gate is not None
    gate = json.loads(json.dumps(record.gate))
    gate["directory"] = record.source_key
    return gate


def _normalised_row(record: CampaignRun, release: Path, archive_name: str) -> dict[str, Any]:
    assert record.row is not None and record.gate is not None
    row = json.loads(json.dumps(record.row))
    gate = record.gate
    checks = gate.get("checks") or {}
    row.update(
        {
            "run_name": record.run_id,
            "source_directory": str((release / "dataset/runs" / record.run_id).resolve()),
            "surface_field_path": f"dataset/fields/{archive_name}",
            "surface_field_archive": f"fields/{archive_name}",
            "surface_field_sha256": record.surface_payload_sha256,
            "gate_verdict": gate.get("verdict"),
            "iterations": gate.get("iterations"),
            "orders_dropped": (checks.get("residual_orders") or {}).get("value"),
            "cl_pct": (checks.get("cl_percent") or {}).get("value"),
            "cd_pct": (checks.get("cd_percent") or {}).get("value"),
            "cmy_abs": (checks.get("cmy_absolute") or {}).get("value"),
            "evidence_origin": record.source_key,
            "release_schema_version": SCHEMA_VERSION,
        }
    )
    missing = dict(row.get("missing_fields") or {})
    for name in GATE_ROW_FIELDS:
        if row.get(name) is not None:
            missing.pop(name, None)
    row["missing_fields"] = missing
    return row


def _payload(path: Path) -> bytes:
    content, _ = stable_bytes(path)
    if path.suffix != ".gz":
        return content
    try:
        return gzip.decompress(content)
    except (gzip.BadGzipFile, EOFError) as exc:
        raise PipelineError(f"invalid gzip surface field {path}: {exc}") from exc


def _copy_exact(record: CampaignRun, input_name: str, destination: Path) -> None:
    evidence = record.inputs.get(input_name)
    if evidence is None:
        raise PipelineError(f"accepted run {record.run_id} lacks {input_name}")
    content, current = stable_bytes(evidence.path)
    if current.sha256 != evidence.sha256:
        raise PipelineError(f"{input_name} changed after scan for {record.run_id}")
    atomic_write_bytes(destination, content)


def _copy_surface(record: CampaignRun, destination: Path) -> str:
    if record.surface is None or record.surface_payload_sha256 is None:
        raise PipelineError(f"accepted run {record.run_id} lacks a stable surface field")
    evidence = record.inputs.get("surface_field")
    if evidence is None:
        raise PipelineError(f"accepted run {record.run_id} lacks surface provenance")
    verify_stable_file(evidence)
    payload = _payload(record.surface)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != record.surface_payload_sha256:
        raise PipelineError(f"surface payload changed after scan for {record.run_id}")
    compressed = gzip.compress(payload, compresslevel=6, mtime=0)
    atomic_write_bytes(destination, compressed)
    return digest


def _validate_existing_release(path: Path, release_id: str) -> dict[str, Any]:
    manifest_path = path / "release.json"
    if not manifest_path.is_file():
        raise PipelineError(f"release directory exists without release.json: {path}")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("release_id") != release_id:
        raise PipelineError(f"release identity mismatch in {path}")
    for item in manifest.get("outputs") or []:
        candidate = path / item["path"]
        if not candidate.is_file() or sha256_file(candidate) != item["sha256"]:
            raise PipelineError(f"immutable release file is missing or changed: {candidate}")
    return manifest


def create_release(scan: CampaignScan, release_root: Path) -> dict[str, Any]:
    """Copy accepted evidence into an immutable content-addressed release."""

    release_root = Path(release_root).resolve()
    release_root.mkdir(parents=True, exist_ok=True)
    accepted = [record for record in scan.records if record.status == "FINAL_ACCEPTED"]
    if not accepted:
        raise PipelineError("campaign scan contains no FINAL_ACCEPTED snapshots")
    release_hash = _release_identity(accepted)
    release_id = f"release-{release_hash[:16]}"
    release = release_root / release_id
    if release.exists():
        manifest = _validate_existing_release(release, release_id)
        write_json(
            release_root / "latest.json",
            {"release_id": release_id, "path": release_id, "updated_utc": utc_now()},
        )
        return {**manifest, "reused": True}

    staging = Path(tempfile.mkdtemp(prefix=f".{release_id}.", dir=release_root))
    try:
        dataset = staging / "dataset"
        fields = dataset / "fields"
        runs = dataset / "runs"
        reports = staging / "reports"
        fields.mkdir(parents=True)
        runs.mkdir()
        reports.mkdir()
        rows = []
        source_records = []
        for record in sorted(accepted, key=lambda item: item.run_id):
            for evidence in record.inputs.values():
                verify_stable_file(evidence)
            archive_name = f"{record.run_id}_surf.cgns.gz"
            released_surface = fields / archive_name
            payload_hash = _copy_surface(record, released_surface)
            canonical_surface = read_surface(released_surface)
            if not np.all(np.isfinite(canonical_surface.fields["CoefPressure"])):
                raise PipelineError(f"released surface has missing/non-finite Cp: {record.run_id}")
            run_output = runs / record.run_id
            run_output.mkdir()
            _copy_exact(record, "result.json", run_output / "result.json")
            _copy_exact(record, "memory_watch.json", run_output / "memory_watch.json")
            _copy_exact(record, "run.log", run_output / "run.log")
            write_json(run_output / "gate.json", _normalised_gate(record))
            row = _normalised_row(record, release, archive_name)
            rows.append(row)
            source_records.append(
                {
                    "run_id": record.run_id,
                    "source_key": record.source_key,
                    "source_directory": str(record.directory),
                    "surface_payload_sha256": payload_hash,
                    "derived_surface_topology_hash": canonical_surface.topology_hash,
                    "surface_nodes": int(canonical_surface.coordinates.shape[0]),
                    "surface_cells": int(canonical_surface.connectivity.shape[0]),
                    "inputs": {
                        name: evidence.public(scan.repo)
                        for name, evidence in sorted(record.inputs.items())
                    },
                    "warnings": record.warnings,
                }
            )

        dataset_manifest = {
            "schema_version": "aeris.s8.dataset.release.v1",
            "release_id": release_id,
            "release_hash": release_hash,
            "purpose": "Immutable FINAL_ACCEPTED CFD surface snapshot release.",
            "counts": {"rows": len(rows), "excluded": len(scan.records) - len(rows)},
            "acceptance": {
                "required_status": "FINAL_ACCEPTED",
                "exit_code_is_acceptance": False,
                "source_monitor_schema": MONITOR_SCHEMA_VERSION,
            },
        }
        write_json(dataset / "rows.json", rows)
        write_json(dataset / "MANIFEST.json", dataset_manifest)

        classified = QualificationEvidence(staging).runs()
        invalid = [run.row["run_name"] for run in classified if run.status != "FINAL_ACCEPTED"]
        if invalid:
            raise PipelineError(f"released evidence failed independent reclassification: {invalid}")

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "created_utc": utc_now(),
            "release_id": release_id,
            "release_hash": release_hash,
            "path": str(release),
            "status": "COMPLETE",
            "immutable": True,
            "copy_policy": "deterministic gzip copy; no links to mutable campaign files",
            "accepted_snapshots": len(rows),
            "excluded_snapshots": len(scan.records) - len(rows),
            "distinct_geometries": len(
                {record.geometry_key for record in accepted if record.geometry_key is not None}
            ),
            "source_records": source_records,
            "outputs": output_manifest(staging, exclude={"release.json"}),
        }
        write_json(staging / "release.json", manifest)
        try:
            os.replace(staging, release)
        except FileExistsError:
            shutil.rmtree(staging)
            manifest = _validate_existing_release(release, release_id)
        write_json(
            release_root / "latest.json",
            {"release_id": release_id, "path": release_id, "updated_utc": utc_now()},
        )
        return {**manifest, "reused": False}
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
