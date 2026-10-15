from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np

from aeris_research.audits import (
    audit_holdout_leakage,
    audit_pressure_integration,
    audit_topology_identity,
)
from aeris_research.dataset import SCHEMA_VERSION


def _synthetic_dataset(path: Path, geometry_sets: list[str]) -> None:
    coordinates = np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0]])
    connectivity = np.asarray([[0, 1, 3, 2]], dtype=np.int64)
    with h5py.File(path, "w") as handle:
        handle.attrs["schema_version"] = SCHEMA_VERSION
        topologies = handle.create_group("topologies")
        topology = topologies.create_group("topology")
        topology.create_dataset("connectivity", data=connectivity)
        topology.create_dataset("zone_names", data=np.asarray(["wall"], dtype="S4"))
        nodes = topology.create_group("node_keys")
        nodes.create_dataset("zone", data=np.zeros(4, dtype=np.int32))
        nodes.create_dataset("i", data=np.asarray([0, 1, 0, 1], dtype=np.int32))
        nodes.create_dataset("j", data=np.asarray([0, 0, 1, 1], dtype=np.int32))
        cells = topology.create_group("cell_keys")
        cells.create_dataset("zone", data=np.zeros(1, dtype=np.int32))
        cells.create_dataset("i", data=np.zeros(1, dtype=np.int32))
        cells.create_dataset("j", data=np.zeros(1, dtype=np.int32))
        snapshots = handle.create_group("snapshots")
        for index, geometry_set in enumerate(geometry_sets):
            row = {
                "geometry_set": geometry_set,
                "geometry_index": index,
                "geometry_hash": f"hash-{index}",
                "design_vector": {"shape": float(index)},
                "connectivity_hash": "legacy-volume-hash",
                "alpha_deg": 0.0,
                "area_ref": 1.0,
                "chord_ref": 1.0,
                "moment_ref_xyz": [0.0, 0.0, 0.0],
                "CL": 0.0,
                "CMy": 0.0,
            }
            snapshot = snapshots.create_group(f"run-{index}")
            snapshot.attrs["topology_hash"] = "topology"
            snapshot.attrs["run_status"] = "FINAL_ACCEPTED"
            snapshot.attrs["geometry_hash_declared"] = row["geometry_hash"]
            snapshot.attrs["coordinate_hash"] = f"coordinates-{index}"
            snapshot.attrs["source_row_json"] = json.dumps(row)
            snapshot.attrs["cp_integrals_json"] = json.dumps(
                {"cl_pressure": 0.0, "cmy_pressure": 0.0}
            )
            snapshot.create_dataset("coordinates", data=coordinates)
            snapshot.create_dataset("normals", data=np.asarray([[0.0, 0.0, -1.0]]))
            snapshot.create_dataset("areas", data=np.asarray([1.0]))
            fields = snapshot.create_group("fields")
            fields.create_dataset("cp", data=np.asarray([0.0]))
    path.with_suffix(".manifest.json").write_text(
        json.dumps({"source_inputs": [{"path": "development/source.json"}]})
    )


def _holdout_contract(root: Path) -> None:
    path = root / "reports/check_holdout_lock.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"status": "PASS", "details": {"contents_read": False}}))


def test_adversarial_topology_and_pressure_audits_pass_structured_fixture(tmp_path):
    dataset = tmp_path / "surface.h5"
    _synthetic_dataset(dataset, ["development", "development", "development"])
    topology = audit_topology_identity(dataset)
    pressure = audit_pressure_integration(dataset)
    assert topology["status"] == "PASS"
    assert topology["cross_geometry_proof_exercised"] is True
    assert pressure["status"] == "PASS"


def test_holdout_audit_checks_split_without_opening_holdout_data(tmp_path):
    dataset = tmp_path / "surface.h5"
    _synthetic_dataset(dataset, ["development", "development", "development"])
    contract = tmp_path / "qualification"
    _holdout_contract(contract)
    report = audit_holdout_leakage(dataset, contract)
    assert report["status"] == "PASS"
    assert report["holdout_files_opened"] == []
    assert report["checks"]["geometry_disjoint_split_exercised"] is True


def test_holdout_audit_fails_on_contaminated_identity(tmp_path):
    dataset = tmp_path / "surface.h5"
    _synthetic_dataset(dataset, ["development", "round_c_lhs10_seed42", "development"])
    contract = tmp_path / "qualification"
    _holdout_contract(contract)
    report = audit_holdout_leakage(dataset, contract)
    assert report["status"] == "FAIL"
    assert report["contaminated_rows"] == ["run-1"]
