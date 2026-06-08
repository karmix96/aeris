"""
CLI tests for geometry commands added in Domain 1 patch.

Covers:
  - geometry info: lists generators, shows DV count
  - geometry inspect: registered, prints metrics from manifest
  - geometry generate: returns tuple, stdout contains seed + metrics
  - geometry inspect --json: valid JSON output
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aeris.cli import app
import aeris.commands.geometry as geometry_commands

runner = CliRunner()


def test_geometry_info_lists_generators():
    """geometry info must mention the registered generator and design variables."""
    result = runner.invoke(app, ["geometry", "info"])
    assert result.exit_code == 0, f"geometry info failed:\n{result.output}"
    assert "bwb_segmented_v1" in result.output
    assert "17" in result.output  # design variable count
    assert "bwb_training_v1" in result.output


def test_geometry_inspect_is_registered():
    """geometry inspect must be a registered command."""
    result = runner.invoke(app, ["geometry", "inspect", "--help"])
    assert result.exit_code == 0, f"inspect --help failed:\n{result.output}"
    assert "--run-dir" in result.output


def test_geometry_inspect_prints_metrics(tmp_path):
    """geometry inspect must print seed and key metrics from a valid manifest."""
    # Build a minimal manifest matching the real schema
    run_root = tmp_path / "fake_run"
    run_root.mkdir()
    manifest = {
        "status": "success",
        "phase": "geometry_generate",
        "run_id": "fake_run",
        "config_path": str(tmp_path / "geo.yaml"),
        "copied_config_path": str(run_root / "input_config.yaml"),
        "created_at_utc": "2026-01-01T00:00:00+00:00",
        "completed_at_utc": "2026-01-01T00:00:01+00:00",
        "geometry": {
            "generator_id": "bwb_segmented_v1",
            "design_sampling_seed": 42,
            "name": "test",
            "geometry_deterministic": True,
            "design_sample": {},
            "case_summary": {
                "metrics": {
                    "semi_span_m": 1.6,
                    "full_span_m": 3.2,
                    "approx_area_m2": 2.18,
                    "approx_aspect_ratio_planform": 4.69,
                    "aspect_ratio_aerosandbox": 4.70,
                },
                "sampled_planform": {
                    "c1_m": 1.6,
                    "b_total_m": 1.6,
                },
            },
        },
    }
    (run_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = runner.invoke(app, ["geometry", "inspect", "--run-dir", str(run_root)])

    assert result.exit_code == 0, f"inspect failed:\n{result.output}"
    assert "42" in result.output            # seed
    assert "1.6000" in result.output        # semi_span_m
    assert "3.2000" in result.output        # full_span_m
    assert "2.1800" in result.output        # area
    assert "4.69" in result.output or "4.690" in result.output  # AR


def test_geometry_inspect_json_flag(tmp_path):
    """geometry inspect --json must output valid JSON containing manifest."""
    run_root = tmp_path / "fake_run_json"
    run_root.mkdir()
    manifest = {
        "status": "success",
        "geometry": {
            "generator_id": "bwb_segmented_v1",
            "design_sampling_seed": 99,
            "case_summary": {
                "metrics": {"semi_span_m": 1.5},
                "sampled_planform": {"c1_m": 1.6},
            },
        },
    }
    (run_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = runner.invoke(
        app, ["geometry", "inspect", "--run-dir", str(run_root), "--json"]
    )
    assert result.exit_code == 0, f"inspect --json failed:\n{result.output}"

    parsed = json.loads(result.output)
    assert parsed["manifest"]["geometry"]["design_sampling_seed"] == 99


def test_geometry_inspect_missing_run_dir(tmp_path):
    """geometry inspect with a nonexistent run-dir must exit non-zero."""
    result = runner.invoke(
        app, ["geometry", "inspect", "--run-dir", str(tmp_path / "no_such_run")]
    )
    assert result.exit_code != 0


def test_geometry_generate_stdout_contains_metrics(tmp_path, monkeypatch):
    """geometry generate stdout must contain seed and real metric values."""
    from aeris.common.paths import RunPaths

    run_root = tmp_path / "runs" / "gen_stdout_test"
    fake_paths = RunPaths(
        root=run_root,
        logs=run_root / "logs",
        artifacts=run_root / "artifacts",
        run_id="gen_stdout_test",
    )
    monkeypatch.setattr(
        "aeris.pipeline.geometry_run.create_run_folder",
        lambda prefix: fake_paths,
    )

    cfg_text = """\
name: stdout_test
geometry:
  generator:
    family: bwb_segmented
    version: v1
    seed: 77
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
    twist_b0_deg:   {min: -2.0, max: 2.0}
    twist_b1_deg:   {min: -3.0, max: 3.0}
    twist_b2_deg:   {min: -4.0, max: 4.0}
    twist_b3_deg:   {min: -5.0, max: 5.0}
    dihedral_b1_deg: {min: 0.0, max: 5.0}
    dihedral_b2_deg: {min: 0.0, max: 8.0}
    dihedral_b3_deg: {min: 0.0, max: 10.0}
  outputs:
    save_plot: false
    build_aerosandbox: true
"""
    cfg_path = tmp_path / "geo.yaml"
    cfg_path.write_text(cfg_text, encoding="utf-8")

    result = runner.invoke(app, ["geometry", "generate", "--config", str(cfg_path)])

    assert result.exit_code == 0, f"generate failed:\n{result.output}"
    assert "seed" in result.output
    assert "77" in result.output        # seed value
    assert "semi_span" in result.output
    assert "SUCCESS" in result.output

    # Key check: semi_span must show a real number, not a dash
    import re
    m = re.search(r"semi_span:\s*([\d.]+)", result.output)
    assert m is not None, (
        f"semi_span not found or shows '—' in stdout.\n"
        f"Full output:\n{result.output}"
    )
    semi = float(m.group(1))
    assert semi > 0, f"semi_span must be > 0, got {semi}"
