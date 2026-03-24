"""Tests for single-case geometry pipeline orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from aeris.pipeline.geometry_run import _to_jsonable, run_geometry_generation


def make_geometry_config_text() -> str:
    """Return a valid minimal YAML config for geometry-run pipeline tests."""
    return """
name: test_bwb_pipeline

geometry:
  generator:
    family: bwb_segmented
    version: v1
    seed: 42

  controls:
    n_points: 10
    n_spline_inboard: 4
    n_spline_outboard: 5
    desired_curvature_strength: 0.7
    spline_split_ratio: 0.55
    segment_length_variation: 0.25
    sweep_variation: 0.10

  planform_bounds:
    c1_m: {min: 1.0, max: 2.0}
    c2_ratio: {min: 0.4, max: 0.8}
    c3_ratio: {min: 0.2, max: 0.6}
    c4_ratio: {min: 0.1, max: 0.4}
    b_total_m: {min: 2.0, max: 4.0}
    b3_ratio: {min: 0.2, max: 0.5}
    split_ratio: {min: 0.2, max: 0.8}
    sw1_deg: {min: 10.0, max: 30.0}
    sw2_deg: {min: 5.0, max: 20.0}
    sw3_deg: {min: 0.0, max: 10.0}

  section_bounds:
    airfoil_name: naca4412
    dihedral_root_deg: 0.0
    twist_b0_deg: {min: -2.0, max: 2.0}
    twist_b1_deg: {min: -3.0, max: 3.0}
    twist_b2_deg: {min: -4.0, max: 4.0}
    twist_b3_deg: {min: -5.0, max: 5.0}
    dihedral_b1_deg: {min: 0.0, max: 5.0}
    dihedral_b2_deg: {min: 0.0, max: 8.0}
    dihedral_b3_deg: {min: 0.0, max: 10.0}

  outputs:
    save_plot: false
    build_aerosandbox: true
"""


def test_to_jsonable_handles_dataclasses_paths_and_numpy_scalars():
    """_to_jsonable should convert common project values into JSON-safe structures."""

    @dataclass(frozen=True)
    class Demo:
        x: int
        y: float

    payload = {
        "path": Path("/tmp/example"),
        "scalar": np.float64(3.5),
        "data": Demo(x=1, y=2.0),
        "items": (1, 2, 3),
    }

    converted = _to_jsonable(payload)

    assert converted["path"] == "/tmp/example"
    assert converted["scalar"] == 3.5
    assert converted["data"] == {"x": 1, "y": 2.0}
    assert converted["items"] == [1, 2, 3]


def test_run_geometry_generation_happy_path(tmp_path, monkeypatch):
    """Pipeline geometry run should succeed and write a success manifest."""
    config_path = tmp_path / "geometry.yaml"
    config_path.write_text(make_geometry_config_text(), encoding="utf-8")

    fake_run_root = tmp_path / "runs" / "geometry_test_run"

    from aeris.common.paths import RunPaths

    fake_run_paths = RunPaths(
        root=fake_run_root,
        logs=fake_run_root / "logs",
        artifacts=fake_run_root / "artifacts",
        run_id="geometry_test_run",
    )

    monkeypatch.setattr(
        "aeris.pipeline.geometry_run.create_run_folder",
        lambda prefix: fake_run_paths,
    )

    exit_code = run_geometry_generation(config_path=config_path)

    assert exit_code == 0
    assert fake_run_root.exists()

    manifest_path = fake_run_root / "manifest.json"
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "success"
    assert manifest["phase"] == "geometry_generate"
    assert manifest["run_id"] == "geometry_test_run"
    assert manifest["config_path"] == str(config_path.resolve())
    assert manifest["copied_config_path"] == str(fake_run_root / "input_config.yaml")
    assert manifest["completed_at_utc"] is not None

    geometry = manifest["geometry"]
    assert geometry["generator_id"] == "bwb_segmented_v1"
    assert geometry["geometry_deterministic"] is True
    assert "design_sample" in geometry
    assert "case_summary" in geometry

    copied_config = fake_run_root / "input_config.yaml"
    assert copied_config.exists()

    log_file = fake_run_root / "logs" / "app.log"
    assert log_file.exists()

    geometry_artifacts_dir = fake_run_root / "artifacts" / "geometry"
    assert geometry_artifacts_dir.exists()


def test_run_geometry_generation_failure_path_writes_failed_manifest(tmp_path, monkeypatch):
    """Pipeline geometry run should write a failed manifest when generator resolution fails."""
    bad_config_path = tmp_path / "bad_geometry.yaml"
    bad_config_path.write_text(
        """
name: broken_case

geometry:
  generator:
    family: does_not_exist
    version: v999
""",
        encoding="utf-8",
    )

    fake_run_root = tmp_path / "runs" / "geometry_test_fail"

    from aeris.common.paths import RunPaths

    fake_run_paths = RunPaths(
        root=fake_run_root,
        logs=fake_run_root / "logs",
        artifacts=fake_run_root / "artifacts",
        run_id="geometry_test_fail",
    )

    monkeypatch.setattr(
        "aeris.pipeline.geometry_run.create_run_folder",
        lambda prefix: fake_run_paths,
    )

    exit_code = run_geometry_generation(config_path=bad_config_path)

    assert exit_code == 1
    assert fake_run_root.exists()

    manifest_path = fake_run_root / "manifest.json"
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["completed_at_utc"] is not None
    assert manifest["error"] is not None
    assert "type" in manifest["error"]
    assert "message" in manifest["error"]

    # The copied input config should still exist because failure happens after config load/copy.
    copied_config = fake_run_root / "input_config.yaml"
    assert copied_config.exists()