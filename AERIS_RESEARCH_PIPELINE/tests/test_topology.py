from __future__ import annotations

import numpy as np

from aeris_research.cgns import SurfaceZone, _canonicalise
from aeris_research.dataset import (
    mesh_screen_surface_topology_preflight,
    scientific_snapshot_hash,
)


def _geometry(scale: float):
    i, j = np.meshgrid(np.arange(4.0), np.arange(3.0), indexing="ij")
    coordinates = np.stack([scale * i, j, 0.1 * scale * i * j], axis=-1)
    fields = {
        "CoefPressure": np.zeros((3, 2)),
        "SkinFrictionMagnitude": np.ones((3, 2)),
        "YPlus": np.ones((3, 2)) * 0.5,
    }
    return _canonicalise([SurfaceZone("NSWall", coordinates, fields)], "synthetic")


def test_node_i_is_same_topological_location_for_every_geometry():
    first = _geometry(1.0)
    second = _geometry(1.7)
    assert first.topology_hash == second.topology_hash
    np.testing.assert_array_equal(first.node_zone, second.node_zone)
    np.testing.assert_array_equal(first.node_i, second.node_i)
    np.testing.assert_array_equal(first.node_j, second.node_j)
    np.testing.assert_array_equal(first.connectivity, second.connectivity)
    assert not np.array_equal(first.coordinates, second.coordinates)


def test_topology_hash_changes_when_structured_layout_changes():
    first = _geometry(1.0)
    i, j = np.meshgrid(np.arange(5.0), np.arange(3.0), indexing="ij")
    coordinates = np.stack([i, j, 0.1 * i * j], axis=-1)
    fields = {name: np.zeros((4, 2)) for name in ("CoefPressure", "SkinFrictionMagnitude", "YPlus")}
    changed = _canonicalise([SurfaceZone("NSWall", coordinates, fields)], "synthetic")
    assert first.topology_hash != changed.topology_hash


def test_mesh_preflight_distinguishes_wall_and_volume_topology():
    records = [
        {
            "index": 0,
            "block_shapes": {
                "o_wing": [93, 65, 49],
                "o_out": [93, 65, 48],
                "cap_out": [43, 5, 48],
            },
        },
        {
            "index": 1,
            "block_shapes": {
                "o_wing": [93, 65, 49],
                "o_out": [93, 65, 49],
                "cap_out": [43, 5, 49],
            },
        },
    ]
    report = mesh_screen_surface_topology_preflight(records)
    assert report["status"] == "PASS"
    assert report["surface_wall_shape_families"] == 1
    assert report["volume_block_shape_families"] == 2


def test_scientific_snapshot_hash_ignores_machine_paths():
    first = {
        "run_name": "case",
        "CL": 0.2,
        "surface_field_sha256": "a" * 64,
        "source_directory": "/machine-a/repo/artifacts/case",
        "volume_field_source": "/machine-a/repo/artifacts/case/volume.cgns",
    }
    second = {
        **first,
        "source_directory": "/machine-b/clone/artifacts/case",
        "volume_field_source": "/machine-b/clone/artifacts/case/volume.cgns",
    }
    assert scientific_snapshot_hash(
        first, topology_hash="topology", coordinate_hash="coordinates"
    ) == scientific_snapshot_hash(second, topology_hash="topology", coordinate_hash="coordinates")
