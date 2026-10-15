from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from .cgns import CanonicalSurface, pressure_coefficients, read_surface
from .common import PipelineError, sha256_file, sha256_object, utc_now, write_json
from .evidence import QualificationEvidence, RunEvidence

SCHEMA_VERSION = "aeris.ai_surface_dataset.v1"
NONPORTABLE_ROW_FIELDS = frozenset(
    {
        "environment",
        "source_directory",
        "surface_field_path",
        "volume_field_path",
        "volume_field_source",
        "volume_field_note",
    }
)


def scientific_snapshot_hash(
    row: dict[str, Any], *, topology_hash: str, coordinate_hash: str
) -> str:
    """Hash scientific identity without machine-specific absolute paths."""

    portable_row = {
        name: value for name, value in row.items() if name not in NONPORTABLE_ROW_FIELDS
    }
    return sha256_object(
        {
            "schema_version": SCHEMA_VERSION,
            "surface_payload_sha256": row.get("surface_field_sha256"),
            "topology_hash": topology_hash,
            "coordinate_hash": coordinate_hash,
            "row": portable_row,
        }
    )


def mesh_screen_surface_topology_preflight(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Infer physical-wall shapes from the governed S8 block boundary layout."""

    wall_signatures = set()
    volume_signatures = set()
    missing = []
    for record in records:
        shapes = record.get("block_shapes") or {}
        try:
            o_wing = tuple(int(value) for value in shapes["o_wing"])
            cap_out = tuple(int(value) for value in shapes["cap_out"])
            volume_signature = tuple(
                (name, tuple(int(value) for value in shape))
                for name, shape in sorted(shapes.items())
            )
        except (KeyError, TypeError, ValueError):
            missing.append(record.get("index"))
            continue
        # Governed S8 boundaries: o_wing eta0 is the OML and cap_out zeta0 is
        # the tip wall. Their two tangential dimensions define surface topology.
        wall_signatures.add((("oml", (o_wing[0], o_wing[2])), ("tip", cap_out[:2])))
        volume_signatures.add(volume_signature)
    passed = bool(records) and not missing and len(wall_signatures) == 1
    return {
        "status": "PASS" if passed else "FAIL",
        "records": len(records),
        "missing_block_shapes": missing,
        "surface_wall_shape_families": len(wall_signatures),
        "volume_block_shape_families": len(volume_signatures),
        "surface_wall_signatures": [
            {name: list(shape) for name, shape in signature}
            for signature in sorted(wall_signatures)
        ],
        "basis": (
            "In the governed S8 layout, o_wing eta0 is the OML and cap_out zeta0 "
            "is the tip wall. This is a mesh-screen preflight, not a substitute for "
            "the per-CGNS topology audit."
        ),
    }


def _coordinate_hash(surface: CanonicalSurface) -> str:
    digest = hashlib.sha256()
    digest.update(surface.topology_hash.encode("ascii"))
    digest.update(surface.coordinates.astype("<f8", copy=False).tobytes(order="C"))
    return digest.hexdigest()


def _safe_group_name(value: str) -> str:
    if not value or "/" in value or value in {".", ".."}:
        raise PipelineError(f"unsafe HDF5 group name: {value!r}")
    return value


def _string_array(values: list[str]) -> np.ndarray:
    return np.asarray(values, dtype=h5py.string_dtype(encoding="utf-8"))


def _write_topology(group: h5py.Group, surface: CanonicalSurface) -> None:
    group.attrs["topology_hash"] = surface.topology_hash
    group.attrs["node_order"] = "zone-name lexical, then CGNS Fortran order (i fastest)"
    group.attrs["cell_order"] = "zone-name lexical, then CGNS Fortran order (i fastest)"
    group.attrs["cell_type"] = "QUAD_4"
    group.create_dataset("zone_names", data=_string_array(list(surface.zone_names)))
    group.create_dataset("zone_vertex_shapes", data=np.asarray(surface.zone_shapes, dtype=np.int32))
    group.create_dataset(
        "connectivity", data=surface.connectivity, compression="gzip", shuffle=True
    )
    nodes = group.create_group("node_keys")
    nodes.create_dataset("zone", data=surface.node_zone, compression="gzip", shuffle=True)
    nodes.create_dataset("i", data=surface.node_i, compression="gzip", shuffle=True)
    nodes.create_dataset("j", data=surface.node_j, compression="gzip", shuffle=True)
    cells = group.create_group("cell_keys")
    cells.create_dataset("zone", data=surface.cell_zone, compression="gzip", shuffle=True)
    cells.create_dataset("i", data=surface.cell_i, compression="gzip", shuffle=True)
    cells.create_dataset("j", data=surface.cell_j, compression="gzip", shuffle=True)


def _write_snapshot(
    group: h5py.Group,
    run: RunEvidence,
    surface: CanonicalSurface,
    design_names: list[str],
) -> dict[str, Any]:
    row = run.row
    coordinate_hash = _coordinate_hash(surface)
    group.attrs["run_name"] = row["run_name"]
    group.attrs["topology_hash"] = surface.topology_hash
    group.attrs["coordinate_hash"] = coordinate_hash
    group.attrs["geometry_hash_declared"] = str(row.get("geometry_hash", ""))
    group.attrs["geometry_set"] = str(row.get("geometry_set", ""))
    group.attrs["geometry_index"] = int(row.get("geometry_index", -1))
    group.attrs["grid_level"] = str(row.get("grid_level", ""))
    group.attrs["alpha_deg"] = float(row.get("alpha_deg", np.nan))
    group.attrs["beta_deg"] = float(row.get("beta_deg", np.nan))
    group.attrs["mach"] = float(row.get("mach", np.nan))
    group.attrs["reynolds"] = float(row.get("reynolds", np.nan))
    group.attrs["run_status"] = run.status
    group.attrs["gate_verdict"] = str(row.get("gate_verdict") or "")
    group.attrs["status_reasons_json"] = json.dumps(run.reasons)
    group.attrs["source_archive_sha256"] = str(row.get("surface_field_sha256", ""))
    group.attrs["reader_backend"] = surface.backend
    group.attrs["source_row_json"] = json.dumps(row, sort_keys=True, separators=(",", ":"))

    design = row.get("design_vector") or {}
    vector = np.asarray(
        [float(design.get(name, np.nan)) for name in design_names], dtype=np.float64
    )
    dataset = group.create_dataset("design_vector", data=vector)
    dataset.attrs["feature_names_json"] = json.dumps(design_names)
    group.create_dataset("coordinates", data=surface.coordinates, compression="gzip", shuffle=True)
    group.create_dataset("normals", data=surface.normals, compression="gzip", shuffle=True)
    group.create_dataset("areas", data=surface.areas, compression="gzip", shuffle=True)
    fields = group.create_group("fields")
    for source_name, canonical_name in (
        ("CoefPressure", "cp"),
        ("SkinFrictionMagnitude", "skin_friction_magnitude"),
        ("YPlus", "y_plus"),
    ):
        values = surface.fields[source_name]
        field = fields.create_dataset(canonical_name, data=values, compression="gzip", shuffle=True)
        field.attrs["source_name"] = source_name
        field.attrs["location"] = "CellCenter"
        field.attrs["available"] = bool(np.any(np.isfinite(values)))

    integrated = pressure_coefficients(
        surface.fields["CoefPressure"],
        surface.coordinates,
        surface.connectivity,
        surface.normals,
        surface.areas,
        alpha_deg=float(row["alpha_deg"]),
        area_ref=float(row["area_ref"]),
        chord_ref=float(row["chord_ref"]),
        moment_ref_xyz=np.asarray(row["moment_ref_xyz"], dtype=float),
    )
    group.attrs["cp_integrals_json"] = json.dumps(integrated, sort_keys=True)
    snapshot_hash = scientific_snapshot_hash(
        row,
        topology_hash=surface.topology_hash,
        coordinate_hash=coordinate_hash,
    )
    group.attrs["snapshot_hash"] = snapshot_hash
    return {
        "run_name": row["run_name"],
        "geometry_set": row.get("geometry_set"),
        "geometry_index": row.get("geometry_index"),
        "geometry_hash": row.get("geometry_hash"),
        "grid_level": row.get("grid_level"),
        "alpha_deg": row.get("alpha_deg"),
        "mach": row.get("mach"),
        "reynolds": row.get("reynolds"),
        "topology_hash": surface.topology_hash,
        "coordinate_hash": coordinate_hash,
        "declared_connectivity_hash": row.get("connectivity_hash"),
        "run_status": run.status,
        "gate_verdict": row.get("gate_verdict"),
        "snapshot_hash": snapshot_hash,
        **integrated,
    }


def _write_metadata(group: h5py.Group, records: list[dict[str, Any]]) -> None:
    text_fields = (
        "run_name",
        "geometry_set",
        "geometry_hash",
        "grid_level",
        "topology_hash",
        "coordinate_hash",
        "declared_connectivity_hash",
        "run_status",
        "gate_verdict",
        "snapshot_hash",
    )
    integer_fields = ("geometry_index",)
    float_fields = ("alpha_deg", "mach", "reynolds", "cl_pressure", "cmy_pressure")
    for name in text_fields:
        group.create_dataset(
            name, data=_string_array([str(record.get(name) or "") for record in records])
        )
    for name in integer_fields:
        group.create_dataset(
            name, data=np.asarray([int(record.get(name, -1)) for record in records], dtype=np.int64)
        )
    for name in float_fields:
        group.create_dataset(
            name,
            data=np.asarray(
                [float(record.get(name, np.nan)) for record in records], dtype=np.float64
            ),
        )


def audit_canonical_dataset(path: Path) -> dict[str, Any]:
    """Prove that every integer node id maps to one explicit (zone, i, j) key."""

    families = []
    with h5py.File(path, "r") as handle:
        if handle.attrs.get("schema_version") != SCHEMA_VERSION:
            raise PipelineError(f"unsupported canonical dataset schema in {path}")
        declared_to_derived: dict[str, set[str]] = defaultdict(set)
        for snapshot in handle["snapshots"].values():
            source_row = json.loads(snapshot.attrs["source_row_json"])
            declared = source_row.get("connectivity_hash")
            if declared:
                declared_to_derived[str(declared)].add(str(snapshot.attrs["topology_hash"]))
        for topology_hash, topology in handle["topologies"].items():
            node_zone = topology["node_keys/zone"][:]
            node_i = topology["node_keys/i"][:]
            node_j = topology["node_keys/j"][:]
            node_keys = np.stack([node_zone, node_i, node_j], axis=1)
            unique_node_keys = np.unique(node_keys, axis=0)
            connectivity = topology["connectivity"][:]
            snapshots = [
                snapshot
                for snapshot in handle["snapshots"].values()
                if snapshot.attrs["topology_hash"] == topology_hash
            ]
            coordinate_counts_ok = all(
                snapshot["coordinates"].shape[0] == node_keys.shape[0] for snapshot in snapshots
            )
            field_counts_ok = all(
                snapshot["fields/cp"].shape[0] == connectivity.shape[0] for snapshot in snapshots
            )
            geometry_coordinates: dict[str, set[str]] = defaultdict(set)
            declared_connectivity = set()
            for snapshot in snapshots:
                geometry_coordinates[str(snapshot.attrs["geometry_hash_declared"])].add(
                    str(snapshot.attrs["coordinate_hash"])
                )
                source_row = json.loads(snapshot.attrs["source_row_json"])
                if source_row.get("connectivity_hash"):
                    declared_connectivity.add(str(source_row["connectivity_hash"]))
            stable_within_geometry = all(
                len(hashes) == 1 for hashes in geometry_coordinates.values()
            )
            declared_hashes_compatible = all(
                declared_to_derived[declared] == {topology_hash}
                for declared in declared_connectivity
            )
            checks = {
                "node_keys_unique": unique_node_keys.shape[0] == node_keys.shape[0],
                "connectivity_indices_in_range": bool(
                    connectivity.size
                    and connectivity.min() >= 0
                    and connectivity.max() < node_keys.shape[0]
                ),
                "snapshot_node_counts_match": coordinate_counts_ok,
                "snapshot_cell_counts_match": field_counts_ok,
                "same_geometry_coordinates_stable_across_runs": stable_within_geometry,
                "declared_hashes_map_to_one_derived_surface_topology": declared_hashes_compatible,
            }
            passed = all(checks.values())
            distinct_geometries = len(geometry_coordinates)
            families.append(
                {
                    "topology_hash": topology_hash,
                    "zone_names": [
                        value.decode() if isinstance(value, bytes) else str(value)
                        for value in topology["zone_names"][:]
                    ],
                    "nodes": int(node_keys.shape[0]),
                    "cells": int(connectivity.shape[0]),
                    "snapshots": len(snapshots),
                    "distinct_geometries": distinct_geometries,
                    "declared_connectivity_hashes": len(declared_connectivity),
                    "cross_geometry_test_exercised": distinct_geometries >= 2,
                    "scope": (
                        "CROSS_GEOMETRY_TOPOLOGICAL_IDENTITY"
                        if distinct_geometries >= 2
                        else "REPEATED_SOLUTION_IDENTITY_ONLY"
                    ),
                    "checks": checks,
                    "passed": passed,
                }
            )
    passed = bool(families) and all(family["passed"] for family in families)
    ambiguous_declared_hashes = {
        declared: sorted(derived)
        for declared, derived in declared_to_derived.items()
        if len(derived) > 1
    }
    return {
        "schema_version": "aeris.ai_surface_topology_audit.v1",
        "dataset": str(Path(path).resolve()),
        "status": "PASS" if passed else "FAIL",
        "claim": (
            "Within each topology family, node n is defined by the same ordered "
            "(zone, i, j) key in every snapshot; mixed topology families are never stacked."
        ),
        "limitation": (
            "A family with one distinct geometry validates repeated-solution ordering but does "
            "not yet exercise the cross-geometry part of the claim."
        ),
        "declared_hash_contract": (
            "Legacy connectivity hashes may encode volume-block topology and therefore vary "
            "across geometries. Each declared hash must map to exactly one independently "
            "derived surface topology."
        ),
        "ambiguous_declared_hashes": ambiguous_declared_hashes,
        "families": families,
    }


def build_canonical_dataset(
    evidence: QualificationEvidence,
    output: Path,
    *,
    include_incomplete: bool = True,
) -> dict[str, Any]:
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    runs = evidence.runs()
    robustness = evidence.report("s8_robustness_screen_final.json", optional=True) or {}
    topology_preflight = mesh_screen_surface_topology_preflight(
        list(robustness.get("records") or [])
    )
    selected = [run for run in runs if include_incomplete or run.status == "FINAL_ACCEPTED"]
    if not selected:
        raise PipelineError("no surface snapshots satisfy the selected status policy")
    design_names = sorted(
        {name for run in selected for name in (run.row.get("design_vector") or {}).keys()}
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".h5", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    records: list[dict[str, Any]] = []
    topology_examples: dict[str, CanonicalSurface] = {}
    declared_to_derived: dict[str, set[str]] = defaultdict(set)
    try:
        with h5py.File(temporary, "w") as handle:
            handle.attrs["schema_version"] = SCHEMA_VERSION
            handle.attrs["created_utc"] = utc_now()
            handle.attrs["qualification_root"] = str(evidence.root)
            handle.attrs["status_policy"] = (
                "all archived snapshots" if include_incomplete else "FINAL_ACCEPTED only"
            )
            handle.attrs["node_identity_contract"] = (
                "topology family + zone name + structured (i,j); i varies fastest"
            )
            handle.attrs["mesh_screen_surface_topology_preflight_json"] = json.dumps(
                topology_preflight, sort_keys=True
            )
            topologies = handle.create_group("topologies")
            snapshots = handle.create_group("snapshots")
            for run in selected:
                if run.archive is None:
                    continue
                surface = read_surface(run.archive)
                topology_examples.setdefault(surface.topology_hash, surface)
                declared = str(run.row.get("connectivity_hash") or "")
                if declared:
                    declared_to_derived[declared].add(surface.topology_hash)
                run_name = _safe_group_name(str(run.row["run_name"]))
                records.append(
                    _write_snapshot(snapshots.create_group(run_name), run, surface, design_names)
                )
            if not records:
                raise PipelineError("no readable archived surface fields were found")
            ambiguous = {
                declared: sorted(derived)
                for declared, derived in declared_to_derived.items()
                if len(derived) != 1
            }
            if ambiguous:
                raise PipelineError(
                    f"declared connectivity hashes map to multiple topologies: {ambiguous}"
                )
            for topology_hash, surface in topology_examples.items():
                _write_topology(topologies.create_group(topology_hash), surface)
            metadata = handle.create_group("metadata")
            metadata.attrs["design_feature_names_json"] = json.dumps(design_names)
            _write_metadata(metadata, records)
            logical_dataset_hash = sha256_object(
                {
                    "schema_version": SCHEMA_VERSION,
                    "topology_hashes": sorted(topology_examples),
                    "snapshot_hashes": sorted(record["snapshot_hash"] for record in records),
                }
            )
            handle.attrs["logical_dataset_hash"] = logical_dataset_hash
            handle.flush()

        audit = audit_canonical_dataset(temporary)
        if audit["status"] != "PASS":
            raise PipelineError("canonical topology audit failed")
        evidence.ledger.verify_unchanged()
        os.replace(temporary, output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

    audit = audit_canonical_dataset(output)
    audit_path = output.with_suffix(".topology_audit.json")
    write_json(audit_path, audit)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_utc": utc_now(),
        "dataset": str(output),
        "dataset_sha256": sha256_file(output),
        "logical_dataset_hash": logical_dataset_hash,
        "snapshots": len(records),
        "final_accepted": sum(record["run_status"] == "FINAL_ACCEPTED" for record in records),
        "topology_families": len(topology_examples),
        "design_features": design_names,
        "mesh_screen_surface_topology_preflight": topology_preflight,
        "topology_audit": audit,
        "source_inputs": evidence.ledger.manifest(evidence.repo),
    }
    write_json(output.with_suffix(".manifest.json"), manifest)
    return manifest
