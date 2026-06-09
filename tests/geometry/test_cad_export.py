from __future__ import annotations

from pathlib import Path

import pytest

from aeris.geometry.cad_export import openvsp_doctor, parse_cad_formats, parse_step_backend
from aeris.generators.bwb_segmented_v1 import vsp_export


class _FakeCompleted:
    returncode = 0
    stdout = "step ok"
    stderr = ""


def test_parse_cad_formats_accepts_aliases():
    assert parse_cad_formats("vsp,.stp") == ("vspscript", "step")
    assert parse_cad_formats("step") == ("vspscript", "step")
    assert parse_cad_formats("vspscript") == ("vspscript",)


def test_parse_cad_formats_rejects_unknown():
    with pytest.raises(ValueError):
        parse_cad_formats("iges")


def test_openvsp_doctor_reports_missing_command():
    report = openvsp_doctor("definitely_missing_openvsp_binary_for_aeris_tests")
    assert report["found"] is False
    assert "STEP export requires" in report["note"]


def test_run_openvsp_batch_script_skips_missing_executable(tmp_path):
    script = tmp_path / "geometry.vspscript"
    script.write_text("// test\n", encoding="utf-8")
    stdout = tmp_path / "stdout.txt"
    stderr = tmp_path / "stderr.txt"
    step = tmp_path / "geometry.step"

    result = vsp_export.run_openvsp_batch_script(
        vspscript_path=script,
        openvsp_executable="definitely_missing_openvsp_binary_for_aeris_tests",
        stdout_path=stdout,
        stderr_path=stderr,
        step_path=step,
        timeout_sec=1,
    )

    assert result.attempted is False
    assert result.succeeded is False
    assert stdout.exists()
    assert stderr.exists()
    assert "STEP export skipped" in stderr.read_text(encoding="utf-8")



def test_parse_step_backend_accepts_aliases():
    assert parse_step_backend("auto") == "auto"
    assert parse_step_backend("cadquery") == "cadquery"
    assert parse_step_backend("aerosandbox") == "cadquery"
    assert parse_step_backend("vsp") == "openvsp"


def test_parse_step_backend_rejects_unknown():
    with pytest.raises(ValueError):
        parse_step_backend("iges")
