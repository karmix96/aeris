from __future__ import annotations

import json
from pathlib import Path

from aeris.generators.bwb_segmented_v1 import vsp_export


class _FakeAirplane:
    def export_OpenVSP_vspscript(self, output_path: Path) -> None:
        Path(output_path).write_text("// fake AeroSandbox OpenVSP script\nUpdate();\n", encoding="utf-8")


def test_bwb_vspscript_export_writes_traceable_script(monkeypatch, config, sample, section_geometry, tmp_path):
    monkeypatch.setattr(
        vsp_export,
        "_build_aerosandbox_airplane_from_sections",
        lambda **kwargs: _FakeAirplane(),
    )
    out = tmp_path / "geometry.vspscript"

    result = vsp_export.export_openvsp_vspscript_from_section_geometry(
        section_geometry=section_geometry,
        config=config,
        sample=sample,
        output_path=out,
    )

    assert result == out
    text = out.read_text(encoding="utf-8")
    assert "AERIS CAD EXPORT TRACEABILITY" in text
    assert "generator_id: bwb_segmented_v1" in text
    assert "fake AeroSandbox OpenVSP script" in text


def test_bwb_vspscript_step_footer(monkeypatch, config, sample, section_geometry, tmp_path):
    monkeypatch.setattr(
        vsp_export,
        "_build_aerosandbox_airplane_from_sections",
        lambda **kwargs: _FakeAirplane(),
    )
    out = tmp_path / "geometry.vspscript"
    step = tmp_path / "geometry.step"
    vsp3 = tmp_path / "geometry.vsp3"

    vsp_export.export_openvsp_vspscript_from_section_geometry(
        section_geometry=section_geometry,
        config=config,
        sample=sample,
        output_path=out,
        include_step_footer=True,
        step_path=step,
        vsp3_path=vsp3,
    )

    text = out.read_text(encoding="utf-8")
    assert "AERIS OPENVSP STEP EXPORT FOOTER" in text
    assert "ExportFile" in text
    assert "EXPORT_STEP" in text


def test_build_bwb_cad_source_writes_source_manifest(config, sample, tmp_path):
    result = vsp_export.build_bwb_cad_source(
        config=config,
        sample=sample,
        output_dir=tmp_path,
    )

    assert result.section_geometry.sections
    assert Path(result.artifact_paths["planform_sections_csv"]).exists()
    assert Path(result.artifact_paths["section_3d_csv"]).exists()
    summary_path = Path(result.artifact_paths["cad_source_summary_json"])
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["generator_id"] == "bwb_segmented_v1"
    assert payload["section_count"] == len(result.section_geometry.sections)



class _FakeCadQueryAirplane:
    def mesh_body(self):
        return []

    def export_cadquery_geometry(self, output_path):
        Path(output_path).write_text("ISO-10303-21; fake STEP\nEND-ISO-10303-21;\n", encoding="utf-8")


def test_bwb_cadquery_step_export_writes_step(monkeypatch, config, section_geometry, tmp_path):
    monkeypatch.setattr(
        vsp_export,
        "_build_aerosandbox_airplane_from_sections",
        lambda **kwargs: _FakeCadQueryAirplane(),
    )
    step = tmp_path / "geometry.step"

    result = vsp_export.export_cadquery_step_from_section_geometry(
        section_geometry=section_geometry,
        config=config,
        step_path=step,
        stdout_path=tmp_path / "cadquery_stdout.txt",
        stderr_path=tmp_path / "cadquery_stderr.txt",
    )

    assert result.succeeded is True
    assert step.exists()
    assert "fake STEP" in step.read_text(encoding="utf-8")
    assert "mesh_body" in result.stdout_path.read_text(encoding="utf-8")
