"""
Additional pipeline tests for geometry_run.py.

Covers gaps identified during Domain 1 GUI audit:
  1. run_geometry_generation returns tuple[int, Path] (not bare int)
  2. manifest["geometry"]["case_summary"]["metrics"] has real values
  3. manifest["geometry"]["design_sampling_seed"] is present
  4. Failure path returns tuple[1, Path] — run_root still accessible
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aeris.pipeline.geometry_run import run_geometry_generation


MINIMAL_CONFIG = """\
name: test_bwb_metrics

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
    c1_m:      {min: 1.0, max: 2.0}
    c2_ratio:  {min: 0.4, max: 0.8}
    c3_ratio:  {min: 0.2, max: 0.6}
    c4_ratio:  {min: 0.1, max: 0.4}
    b_total_m: {min: 2.0, max: 4.0}
    b3_ratio:  {min: 0.2, max: 0.5}
    split_ratio: {min: 0.2, max: 0.8}
    sw1_deg:   {min: 10.0, max: 30.0}
    sw2_deg:   {min: 5.0,  max: 20.0}
    sw3_deg:   {min: 0.0,  max: 10.0}

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


def _make_run_paths(tmp_path: Path, run_id: str):
    from aeris.common.paths import RunPaths
    root = tmp_path / "runs" / run_id
    return RunPaths(
        root=root,
        logs=root / "logs",
        artifacts=root / "artifacts",
        run_id=run_id,
    )


def test_run_geometry_generation_returns_tuple(tmp_path, monkeypatch):
    """run_geometry_generation must return (exit_code, run_root) — not bare int."""
    cfg = tmp_path / "geo.yaml"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    fake = _make_run_paths(tmp_path, "tuple_test")
    monkeypatch.setattr("aeris.pipeline.geometry_run.create_run_folder", lambda prefix: fake)

    result = run_geometry_generation(config_path=cfg)

    assert isinstance(result, tuple), (
        f"run_geometry_generation must return tuple[int, Path], got {type(result)}"
    )
    assert len(result) == 2, f"Expected 2-tuple, got length {len(result)}"
    exit_code, run_root = result
    assert exit_code == 0
    assert run_root == fake.root


def test_manifest_case_summary_has_metrics_key(tmp_path, monkeypatch):
    """manifest.geometry.case_summary must have a 'metrics' sub-dict with real values.

    This is the exact key path the GUI uses:
      cs = manifest["geometry"]["case_summary"]
      cs["metrics"]["semi_span_m"]  ← must be > 0
    """
    cfg = tmp_path / "geo.yaml"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    fake = _make_run_paths(tmp_path, "metrics_test")
    monkeypatch.setattr("aeris.pipeline.geometry_run.create_run_folder", lambda prefix: fake)

    exit_code, run_root = run_geometry_generation(config_path=cfg)
    assert exit_code == 0

    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    geo = manifest["geometry"]
    cs  = geo["case_summary"]

    assert "metrics" in cs, (
        "case_summary must have a 'metrics' key. "
        "GUI reads cs['metrics']['semi_span_m'] etc."
    )
    metrics = cs["metrics"]
    assert metrics.get("semi_span_m") is not None and metrics["semi_span_m"] > 0, (
        f"semi_span_m must be a positive float, got {metrics.get('semi_span_m')}"
    )
    assert metrics.get("full_span_m") is not None and metrics["full_span_m"] > 0
    assert metrics.get("approx_area_m2") is not None and metrics["approx_area_m2"] > 0
    assert metrics.get("approx_aspect_ratio_planform") is not None and metrics["approx_aspect_ratio_planform"] > 0


def test_manifest_case_summary_has_sampled_planform(tmp_path, monkeypatch):
    """manifest.geometry.case_summary['sampled_planform'] must have c1_m and b_total_m."""
    cfg = tmp_path / "geo.yaml"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    fake = _make_run_paths(tmp_path, "planform_test")
    monkeypatch.setattr("aeris.pipeline.geometry_run.create_run_folder", lambda prefix: fake)

    _, run_root = run_geometry_generation(config_path=cfg)
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    cs = manifest["geometry"]["case_summary"]

    assert "sampled_planform" in cs, "case_summary must have 'sampled_planform'"
    pf = cs["sampled_planform"]
    assert "c1_m" in pf and pf["c1_m"] > 0
    assert "b_total_m" in pf and pf["b_total_m"] > 0


def test_manifest_has_design_sampling_seed(tmp_path, monkeypatch):
    """manifest.geometry.design_sampling_seed must match config seed."""
    cfg = tmp_path / "geo.yaml"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    fake = _make_run_paths(tmp_path, "seed_test")
    monkeypatch.setattr("aeris.pipeline.geometry_run.create_run_folder", lambda prefix: fake)

    _, run_root = run_geometry_generation(config_path=cfg)
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))

    seed = manifest["geometry"].get("design_sampling_seed")
    assert seed == 42, f"Expected seed=42 (from config), got {seed}"


def test_run_geometry_generation_failure_returns_tuple(tmp_path, monkeypatch):
    """Failure path must also return a tuple[int, Path] so callers can unpack safely."""
    bad_cfg = tmp_path / "bad.yaml"
    bad_cfg.write_text(
        "name: bad\ngeometry:\n  generator:\n    family: does_not_exist\n    version: v999\n",
        encoding="utf-8",
    )
    fake = _make_run_paths(tmp_path, "fail_test")
    monkeypatch.setattr("aeris.pipeline.geometry_run.create_run_folder", lambda prefix: fake)

    result = run_geometry_generation(config_path=bad_cfg)

    assert isinstance(result, tuple) and len(result) == 2
    exit_code, run_root = result
    assert exit_code == 1
    assert run_root is not None  # run_root still accessible for diagnostics

    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["error"] is not None


def test_full_span_is_twice_semi_span(tmp_path, monkeypatch):
    """full_span_m must equal 2 × semi_span_m (basic geometry sanity)."""
    cfg = tmp_path / "geo.yaml"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    fake = _make_run_paths(tmp_path, "span_sanity")
    monkeypatch.setattr("aeris.pipeline.geometry_run.create_run_folder", lambda prefix: fake)

    _, run_root = run_geometry_generation(config_path=cfg)
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    metrics = manifest["geometry"]["case_summary"]["metrics"]

    semi = metrics["semi_span_m"]
    full = metrics["full_span_m"]
    assert abs(full - 2 * semi) < 1e-6, (
        f"full_span_m ({full}) must equal 2 × semi_span_m ({semi})"
    )
