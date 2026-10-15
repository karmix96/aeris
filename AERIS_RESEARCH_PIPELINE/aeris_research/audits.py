from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from .cgns import pressure_coefficients
from .common import PipelineError, utc_now, write_csv, write_json
from .dataset import SCHEMA_VERSION, audit_canonical_dataset
from .evidence import QualificationEvidence
from .models import grouped_geometry_split

AUDIT_SCHEMA_VERSION = "aeris.scientific_audits.v1"
CL_DIAGNOSTIC_TOLERANCE = 0.01
CMY_DIAGNOSTIC_TOLERANCE = 0.001
DIRECTION_TOLERANCE = 1.0e-10
GEOMETRY_TOLERANCE = 1.0e-11
HOLDOUT_TOKENS = ("holdout", "round_c_lhs10")


def _decode(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def _evidence_by_name(evidence_root: Path) -> dict[str, Any]:
    return {str(run.row["run_name"]): run for run in QualificationEvidence(evidence_root).runs()}


def _expected_directions(alpha_deg: float) -> tuple[np.ndarray, np.ndarray]:
    radians = np.deg2rad(alpha_deg)
    return (
        np.asarray([np.cos(radians), 0.0, np.sin(radians)]),
        np.asarray([-np.sin(radians), 0.0, np.cos(radians)]),
    )


def audit_coordinate_system(dataset_path: Path, evidence_root: Path) -> dict[str, Any]:
    """Challenge every axis, flow-direction, normal, and reference convention."""

    evidence = _evidence_by_name(evidence_root)
    rows = []
    with h5py.File(dataset_path, "r") as handle:
        if handle.attrs.get("schema_version") != SCHEMA_VERSION:
            raise PipelineError(f"unsupported canonical dataset: {dataset_path}")
        for run_name, snapshot in sorted(handle["snapshots"].items()):
            row = json.loads(snapshot.attrs["source_row_json"])
            run = evidence.get(run_name)
            result = run.result if run else None
            coordinates = snapshot["coordinates"][:]
            normals = snapshot["normals"][:]
            areas = snapshot["areas"][:]
            alpha = float(row["alpha_deg"])
            beta = float(row.get("beta_deg", 0.0))
            expected_velocity, expected_lift = _expected_directions(alpha)
            directions = (result or {}).get("flow_directions") or {}
            realised_velocity = np.asarray(
                directions.get("velocity_direction_realised", [np.nan] * 3), dtype=float
            )
            realised_lift = np.asarray(
                directions.get("lift_direction_realised", [np.nan] * 3), dtype=float
            )
            velocity_error = float(np.linalg.norm(realised_velocity - expected_velocity))
            lift_error = float(np.linalg.norm(realised_lift - expected_lift))
            normal_error = float(np.max(np.abs(np.linalg.norm(normals, axis=1) - 1.0)))
            minimum = coordinates.min(axis=0)
            maximum = coordinates.max(axis=0)
            y_tolerance = max(1.0, float(np.ptp(coordinates[:, 1]))) * 1.0e-10
            if minimum[1] >= -y_tolerance and maximum[1] > y_tolerance:
                domain = "POSITIVE_Y_HALF_DOMAIN"
            elif maximum[1] <= y_tolerance and minimum[1] < -y_tolerance:
                domain = "NEGATIVE_Y_HALF_DOMAIN"
            else:
                domain = "FULL_OR_CROSSING_Y_DOMAIN"
            checks = {
                "accepted_evidence_present": bool(run and run.status == "FINAL_ACCEPTED"),
                "zero_beta_pressure_projection_supported": abs(beta) <= DIRECTION_TOLERANCE,
                "lift_index_requested_is_z": directions.get("lift_index_requested") == 3,
                "lift_index_realised_is_z": directions.get("lift_index_realised") == 3,
                "velocity_direction_matches_alpha": velocity_error <= DIRECTION_TOLERANCE,
                "lift_direction_matches_alpha": lift_error <= DIRECTION_TOLERANCE,
                "coordinates_finite": bool(np.all(np.isfinite(coordinates))),
                "normals_finite_and_unit": bool(
                    np.all(np.isfinite(normals)) and normal_error <= GEOMETRY_TOLERANCE
                ),
                "cell_areas_positive": bool(np.all(np.isfinite(areas)) and np.all(areas > 0.0)),
                "positive_reference_area": float(row.get("area_ref", 0.0)) > 0.0,
                "positive_reference_chord": float(row.get("chord_ref", 0.0)) > 0.0,
                "three_component_moment_reference": len(row.get("moment_ref_xyz") or []) == 3,
            }
            rows.append(
                {
                    "run_name": run_name,
                    "alpha_deg": alpha,
                    "beta_deg": beta,
                    "domain": domain,
                    "coordinate_min_xyz": minimum.tolist(),
                    "coordinate_max_xyz": maximum.tolist(),
                    "velocity_direction_error": velocity_error,
                    "lift_direction_error": lift_error,
                    "normal_unit_max_error": normal_error,
                    "checks": checks,
                    "passed": all(checks.values()),
                }
            )
    domains = sorted({row["domain"] for row in rows})
    passed = bool(rows) and all(row["passed"] for row in rows)
    return {
        "schema_version": "aeris.coordinate_system_audit.v1",
        "created_utc": utc_now(),
        "status": "PASS" if passed else "FAIL",
        "dataset": str(Path(dataset_path).resolve()),
        "assumed_axes": {
            "x": "streamwise at alpha=0",
            "y": "spanwise",
            "z": "vertical/liftIndex=3 at alpha=0",
            "pitch_moment": "right-handed moment about +y",
        },
        "observed_surface_domains": domains,
        "pressure_projection_scope": "alpha rotation in x-z plane; beta must be zero",
        "runs_checked": len(rows),
        "runs": rows,
    }


def _derived_geometry(
    coordinates: np.ndarray, connectivity: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    p00 = coordinates[connectivity[:, 0]]
    p10 = coordinates[connectivity[:, 1]]
    p11 = coordinates[connectivity[:, 2]]
    p01 = coordinates[connectivity[:, 3]]
    area_vectors = -0.5 * np.cross(p11 - p00, p01 - p10)
    areas = np.linalg.norm(area_vectors, axis=1)
    return area_vectors / areas[:, None], areas


def audit_pressure_integration(dataset_path: Path) -> dict[str, Any]:
    """Recompute pressure loads and test sign and symmetry-factor counterfactuals."""

    rows = []
    with h5py.File(dataset_path, "r") as handle:
        if handle.attrs.get("schema_version") != SCHEMA_VERSION:
            raise PipelineError(f"unsupported canonical dataset: {dataset_path}")
        for run_name, snapshot in sorted(handle["snapshots"].items()):
            row = json.loads(snapshot.attrs["source_row_json"])
            topology_hash = str(snapshot.attrs["topology_hash"])
            connectivity = handle[f"topologies/{topology_hash}/connectivity"][:]
            coordinates = snapshot["coordinates"][:]
            normals = snapshot["normals"][:]
            areas = snapshot["areas"][:]
            cp = snapshot["fields/cp"][:]
            derived_normals, derived_areas = _derived_geometry(coordinates, connectivity)
            arguments = {
                "coordinates": coordinates,
                "connectivity": connectivity,
                "areas": areas,
                "alpha_deg": float(row["alpha_deg"]),
                "area_ref": float(row["area_ref"]),
                "chord_ref": float(row["chord_ref"]),
                "moment_ref_xyz": np.asarray(row["moment_ref_xyz"], dtype=float),
            }
            integrated = pressure_coefficients(cp, normals=normals, **arguments)
            reversed_result = pressure_coefficients(cp, normals=-normals, **arguments)
            doubled_result = pressure_coefficients(
                cp, normals=normals, symmetry_factor=2.0, **arguments
            )
            stored = json.loads(snapshot.attrs["cp_integrals_json"])
            cl_error = abs(integrated["cl_pressure"] - float(row["CL"]))
            cmy_error = abs(integrated["cmy_pressure"] - float(row["CMy"]))
            reversed_cl_error = abs(reversed_result["cl_pressure"] - float(row["CL"]))
            doubled_cl_error = abs(doubled_result["cl_pressure"] - float(row["CL"]))
            stored_error = max(
                abs(integrated[name] - float(stored[name]))
                for name in ("cl_pressure", "cmy_pressure")
            )
            normal_error = float(np.max(np.abs(derived_normals - normals)))
            area_error = float(np.max(np.abs(derived_areas - areas)))
            sign_test_required = abs(float(row["CL"])) >= 0.02
            checks = {
                "cp_is_finite": bool(np.all(np.isfinite(cp))),
                "stored_integral_reproduced": stored_error <= 1.0e-12,
                "normals_rederived": normal_error <= 1.0e-12,
                "areas_rederived": area_error <= 1.0e-12,
                "pressure_cl_consistent_with_solver_total": cl_error <= CL_DIAGNOSTIC_TOLERANCE,
                "pressure_cmy_consistent_with_solver_total": cmy_error <= CMY_DIAGNOSTIC_TOLERANCE,
                "normal_sign_beats_reversed_counterfactual": (
                    not sign_test_required or cl_error < reversed_cl_error
                ),
                "unity_symmetry_factor_beats_double_counterfactual": (
                    not sign_test_required or cl_error < doubled_cl_error
                ),
            }
            rows.append(
                {
                    "run_name": run_name,
                    "geometry_hash": row.get("geometry_hash"),
                    "alpha_deg": row["alpha_deg"],
                    "cl_solver_total": row["CL"],
                    "cl_pressure": integrated["cl_pressure"],
                    "cl_absolute_difference": cl_error,
                    "cmy_solver_total": row["CMy"],
                    "cmy_pressure": integrated["cmy_pressure"],
                    "cmy_absolute_difference": cmy_error,
                    "reversed_normal_cl_difference": reversed_cl_error,
                    "double_symmetry_cl_difference": doubled_cl_error,
                    "normal_max_difference": normal_error,
                    "area_max_difference": area_error,
                    "checks": checks,
                    "passed": all(checks.values()),
                }
            )
    passed = bool(rows) and all(row["passed"] for row in rows)
    return {
        "schema_version": "aeris.pressure_integration_audit.v1",
        "created_utc": utc_now(),
        "status": "PASS" if passed else "FAIL",
        "dataset": str(Path(dataset_path).resolve()),
        "runs_checked": len(rows),
        "diagnostic_tolerances": {
            "CL_pressure_vs_solver_total_absolute": CL_DIAGNOSTIC_TOLERANCE,
            "CMy_pressure_vs_solver_total_absolute": CMY_DIAGNOSTIC_TOLERANCE,
            "note": (
                "Pressure-only and total solver coefficients are not mathematically identical; "
                "these are convention diagnostics, not convergence acceptance gates."
            ),
        },
        "maximum_cl_absolute_difference": max(
            (row["cl_absolute_difference"] for row in rows), default=None
        ),
        "maximum_cmy_absolute_difference": max(
            (row["cmy_absolute_difference"] for row in rows), default=None
        ),
        "runs": rows,
    }


def _topology_structural_checks(handle: h5py.File, topology_hash: str) -> dict[str, Any]:
    topology = handle[f"topologies/{topology_hash}"]
    node_zone = topology["node_keys/zone"][:]
    node_i = topology["node_keys/i"][:]
    node_j = topology["node_keys/j"][:]
    cell_zone = topology["cell_keys/zone"][:]
    cell_i = topology["cell_keys/i"][:]
    cell_j = topology["cell_keys/j"][:]
    connectivity = topology["connectivity"][:]
    node_lookup = {
        (int(zone), int(i), int(j)): index
        for index, (zone, i, j) in enumerate(zip(node_zone, node_i, node_j, strict=True))
    }
    expected = np.asarray(
        [
            [
                node_lookup[(int(zone), int(i), int(j))],
                node_lookup[(int(zone), int(i) + 1, int(j))],
                node_lookup[(int(zone), int(i) + 1, int(j) + 1)],
                node_lookup[(int(zone), int(i), int(j) + 1)],
            ]
            for zone, i, j in zip(cell_zone, cell_i, cell_j, strict=True)
        ],
        dtype=np.int64,
    )
    cell_keys = np.stack([cell_zone, cell_i, cell_j], axis=1)
    zone_names = [_decode(value) for value in topology["zone_names"][:]]
    return {
        "zone_names_lexically_ordered": zone_names == sorted(zone_names),
        "cell_keys_unique": np.unique(cell_keys, axis=0).shape[0] == cell_keys.shape[0],
        "quad_connectivity_matches_structured_keys": bool(np.array_equal(connectivity, expected)),
    }


def audit_topology_identity(dataset_path: Path) -> dict[str, Any]:
    base = audit_canonical_dataset(dataset_path)
    structural: dict[str, Any] = {}
    with h5py.File(dataset_path, "r") as handle:
        for topology_hash in handle["topologies"]:
            structural[topology_hash] = _topology_structural_checks(handle, topology_hash)
    families = []
    for family in base["families"]:
        topology_hash = family["topology_hash"]
        checks = {**family["checks"], **structural[topology_hash]}
        families.append({**family, "checks": checks, "passed": all(checks.values())})
    cross_geometry = any(family["distinct_geometries"] >= 2 for family in families)
    passed = base["status"] == "PASS" and all(family["passed"] for family in families)
    return {
        **base,
        "schema_version": "aeris.adversarial_topology_audit.v1",
        "created_utc": utc_now(),
        "status": "PASS" if passed else "FAIL",
        "cross_geometry_proof_exercised": cross_geometry,
        "families": families,
    }


def _contains_holdout_token(value: Any) -> bool:
    text = json.dumps(value, sort_keys=True).casefold()
    return any(token in text for token in HOLDOUT_TOKENS)


def audit_holdout_leakage(dataset_path: Path, holdout_contract_root: Path) -> dict[str, Any]:
    """Audit identifiers and splits without opening any holdout design data."""

    dataset_path = Path(dataset_path).resolve()
    contract_path = Path(holdout_contract_root).resolve() / "reports/check_holdout_lock.json"
    contract = json.loads(contract_path.read_text()) if contract_path.is_file() else None
    contract_closed = bool(
        contract
        and contract.get("details", {}).get("contents_read") is False
        and contract.get("status") in {"PASS", "GO"}
    )
    contaminated_rows = []
    split_checks = []
    geometry_designs: dict[str, set[str]] = defaultdict(set)
    geometry_groups: dict[str, set[str]] = defaultdict(set)
    with h5py.File(dataset_path, "r") as handle:
        family_groups: dict[str, list[str]] = defaultdict(list)
        for run_name, snapshot in handle["snapshots"].items():
            row = json.loads(snapshot.attrs["source_row_json"])
            inspected_identity = {
                "run_name": run_name,
                "geometry_set": row.get("geometry_set"),
                "geometry_index": row.get("geometry_index"),
                "geometry_hash": row.get("geometry_hash"),
                "evidence_origin": row.get("evidence_origin"),
            }
            if _contains_holdout_token(inspected_identity):
                contaminated_rows.append(run_name)
            geometry_hash = str(row.get("geometry_hash") or "")
            geometry_group = f"{row.get('geometry_set')}:{row.get('geometry_index')}"
            geometry_designs[geometry_hash].add(
                json.dumps(row.get("design_vector") or {}, sort_keys=True, separators=(",", ":"))
            )
            geometry_groups[geometry_hash].add(geometry_group)
            family_groups[str(snapshot.attrs["topology_hash"])].append(geometry_group)
        for topology_hash, values in sorted(family_groups.items()):
            groups = np.asarray(values)
            distinct = np.unique(groups)
            if distinct.size < 3:
                split_checks.append(
                    {
                        "topology_hash": topology_hash,
                        "status": "NOT_EXERCISED",
                        "distinct_geometries": int(distinct.size),
                        "disjoint": None,
                    }
                )
                continue
            split = grouped_geometry_split(groups, seed=42)
            memberships = {name: set(groups[indices]) for name, indices in split.items()}
            disjoint = (
                memberships["train"].isdisjoint(memberships["validation"])
                and memberships["train"].isdisjoint(memberships["test"])
                and memberships["validation"].isdisjoint(memberships["test"])
            )
            split_checks.append(
                {
                    "topology_hash": topology_hash,
                    "status": "PASS" if disjoint else "FAIL",
                    "distinct_geometries": int(distinct.size),
                    "disjoint": disjoint,
                    "train": sorted(memberships["train"]),
                    "validation": sorted(memberships["validation"]),
                    "test": sorted(memberships["test"]),
                }
            )

    manifest_path = dataset_path.with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    contaminated_inputs = [
        item.get("path")
        for item in manifest.get("source_inputs") or []
        if _contains_holdout_token(item.get("path"))
    ]
    inconsistent_designs = sorted(
        geometry_hash for geometry_hash, values in geometry_designs.items() if len(values) != 1
    )
    aliased_geometry_hashes = sorted(
        geometry_hash for geometry_hash, values in geometry_groups.items() if len(values) != 1
    )
    exercised_splits = [check for check in split_checks if check["status"] != "NOT_EXERCISED"]
    checks = {
        "holdout_contract_reports_contents_unread": contract_closed,
        "no_holdout_identifiers_in_snapshot_rows": not contaminated_rows,
        "no_holdout_paths_in_dataset_input_manifest": not contaminated_inputs,
        "geometry_hash_maps_to_one_design_vector": not inconsistent_designs,
        "geometry_hash_maps_to_one_geometry_group": not aliased_geometry_hashes,
        "geometry_disjoint_split_exercised": bool(exercised_splits),
        "all_exercised_splits_are_disjoint": all(
            check.get("disjoint") is True for check in exercised_splits
        ),
    }
    passed = all(checks.values())
    return {
        "schema_version": "aeris.holdout_leakage_audit.v1",
        "created_utc": utc_now(),
        "status": "PASS" if passed else "FAIL",
        "dataset": str(dataset_path),
        "method": (
            "Only development-dataset identifiers, generated manifests, and the governed lock "
            "report were inspected. No holdout design file was opened."
        ),
        "holdout_files_opened": [],
        "contract_file_opened": str(contract_path) if contract_path.is_file() else None,
        "checks": checks,
        "contaminated_rows": contaminated_rows,
        "contaminated_input_paths": contaminated_inputs,
        "inconsistent_geometry_designs": inconsistent_designs,
        "aliased_geometry_hashes": aliased_geometry_hashes,
        "split_checks": split_checks,
    }


def run_scientific_audits(
    dataset_path: Path,
    evidence_root: Path,
    holdout_contract_root: Path,
    output: Path,
) -> dict[str, Any]:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    reports = {
        "coordinate_system": audit_coordinate_system(dataset_path, evidence_root),
        "pressure_integration": audit_pressure_integration(dataset_path),
        "topology_identity": audit_topology_identity(dataset_path),
        "holdout_leakage": audit_holdout_leakage(dataset_path, holdout_contract_root),
    }
    for name, report in reports.items():
        write_json(output / f"{name}.json", report)
    findings = [
        {
            "audit": name,
            "status": report["status"],
            "records_checked": report.get("runs_checked", len(report.get("families") or [])),
        }
        for name, report in reports.items()
    ]
    write_csv(output / "summary.csv", findings, ("audit", "status", "records_checked"))
    status = "PASS" if all(report["status"] == "PASS" for report in reports.values()) else "FAIL"
    summary = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "created_utc": utc_now(),
        "status": status,
        "dataset": str(Path(dataset_path).resolve()),
        "evidence_root": str(Path(evidence_root).resolve()),
        "audits": {
            name: {"status": report["status"], "output": f"{name}.json"}
            for name, report in reports.items()
        },
    }
    write_json(output / "SUMMARY.json", summary)
    return summary
