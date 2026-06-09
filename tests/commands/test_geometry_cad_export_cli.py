from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from aeris.cli import app
import aeris.commands.geometry as geometry_commands
from aeris.geometry.cad_export import CADExportResult

runner = CliRunner()


def test_geometry_export_cad_help_runs():
    result = runner.invoke(app, ["geometry", "export-cad", "--help"])
    assert result.exit_code == 0
    assert "--formats" in result.output
    assert "--openvsp-command" in result.output
    assert "--step-backend" in result.output


def test_geometry_openvsp_doctor_help_runs():
    result = runner.invoke(app, ["geometry", "openvsp-doctor", "--help"])
    assert result.exit_code == 0
    assert "--openvsp-command" in result.output


def test_geometry_export_cad_cli_delegates(monkeypatch, tmp_path):
    called: dict[str, object] = {}

    def fake_export_cad_from_config(*, config_path, formats, output_dir=None, openvsp_command="vsp", timeout_sec=180, step_backend="auto"):
        called["config_path"] = Path(config_path)
        called["formats"] = formats
        called["output_dir"] = output_dir
        called["openvsp_command"] = openvsp_command
        called["timeout_sec"] = timeout_sec
        called["step_backend"] = step_backend
        cad_dir = tmp_path / "cad_exports"
        cad_dir.mkdir()
        manifest = cad_dir / "geometry_export_manifest.json"
        vspscript = cad_dir / "geometry.vspscript"
        stdout = cad_dir / "stdout.txt"
        stderr = cad_dir / "stderr.txt"
        manifest.write_text("{}", encoding="utf-8")
        vspscript.write_text("// fake", encoding="utf-8")
        stdout.write_text("", encoding="utf-8")
        stderr.write_text("", encoding="utf-8")
        return CADExportResult(
            status="success",
            run_root=tmp_path,
            cad_dir=cad_dir,
            manifest_path=manifest,
            formats_requested=("vspscript",),
            formats_produced=("vspscript",),
            vspscript_path=vspscript,
            step_path=None,
            stdout_path=stdout,
            stderr_path=stderr,
            warnings=(),
        )

    monkeypatch.setattr(geometry_commands, "export_cad_from_config", fake_export_cad_from_config)

    result = runner.invoke(
        app,
        [
            "geometry",
            "export-cad",
            "--config",
            "configs/geometry/baseline_bwb_25.yaml",
            "--formats",
            "vspscript",
            "--output-dir",
            str(tmp_path),
            "--openvsp-command",
            "vsp",
            "--timeout-sec",
            "9",
            "--step-backend",
            "cadquery",
        ],
    )

    assert result.exit_code == 0, result.output
    assert called["config_path"].name == "baseline_bwb_25.yaml"
    assert called["formats"] == "vspscript"
    assert called["openvsp_command"] == "vsp"
    assert called["timeout_sec"] == 9
    assert called["step_backend"] == "cadquery"
    assert "Geometry CAD export" in result.output
    assert "geometry.vspscript" in result.output
