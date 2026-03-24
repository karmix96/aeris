"""Tests for geometry export helpers in bwb_segmented_v1.export."""

from __future__ import annotations

import csv
import json

from aeris.generators.bwb_segmented_v1.export import (
    build_geometry_summary,
    export_control_points_csv,
    export_geometry_summary,
    export_planform_sections_csv,
    export_section_3d_csv,
)


def test_export_control_points_csv_writes_expected_columns(planform, tmp_path):
    """Control-point CSV should be written with expected columns and row count."""
    output_path = tmp_path / "control_points.csv"
    export_control_points_csv(planform, output_path)

    assert output_path.exists()

    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert reader.fieldnames == ["index", "x_le_m", "y_le_m", "x_te_m", "y_te_m", "chord_m"]
    assert len(rows) == planform.n_points


def test_export_planform_sections_csv_writes_expected_columns(planform, tmp_path):
    """Planform-section CSV should be written with expected columns and row count."""
    output_path = tmp_path / "planform_sections.csv"
    export_planform_sections_csv(planform, output_path)

    assert output_path.exists()

    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert reader.fieldnames == ["index", "front_x_m", "front_y_m", "rear_x_m", "rear_y_m", "chord_m"]
    assert len(rows) == planform.num_sections


def test_export_section_3d_csv_writes_expected_columns(section_geometry, tmp_path):
    """Section 3D CSV should be written with expected columns and row count."""
    output_path = tmp_path / "section_3d.csv"
    export_section_3d_csv(section_geometry, output_path)

    assert output_path.exists()

    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert reader.fieldnames == [
        "index",
        "x_le_m",
        "y_m",
        "z_le_m",
        "chord_m",
        "twist_deg",
        "dihedral_deg",
        "airfoil_name",
    ]
    assert len(rows) == len(section_geometry.sections)


def test_export_geometry_summary_writes_json(config, planform, section_geometry, tmp_path):
    """Summary JSON export should write a readable payload with expected keys."""
    summary = build_geometry_summary(
        config=config,
        planform=planform,
        section_geometry=section_geometry,
        aerosandbox_result=None,
        artifact_paths={"summary_path": "dummy"},
    )
    output_path = tmp_path / "geometry_summary.json"

    export_geometry_summary(summary, output_path)

    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "name" in payload
    assert "generator" in payload
    assert "controls" in payload
    assert "metrics" in payload
    assert "reference_conventions" in payload

