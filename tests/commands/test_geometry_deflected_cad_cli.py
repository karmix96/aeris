from typer.testing import CliRunner

from aeris.cli import app


def test_geometry_export_deflected_cad_help():
    result = CliRunner().invoke(app, ["geometry", "export-deflected-cad", "--help"])
    assert result.exit_code == 0
    assert "--delta-e-sym-deg" in result.output
    assert "--delta-a-diff-deg" in result.output
    assert "--hinge-gap-fraction" in result.output
    assert "deflection-topology" in result.output or "topology" in result.output
    # Do not assert the exact long option text in Rich help; Typer/Rich may truncate it
    # differently depending on terminal width. Instead, verify that the parser accepts
    # the real option name and does not reject it as an unknown option.
    parsed = CliRunner().invoke(
        app,
        [
            "geometry",
            "export-deflected-cad",
            "--config",
            "configs/geometry/does_not_exist.yaml",
            "--formats",
            "vspscript",
            "--output-dir",
            "data/runs/_cli_parse_probe",
            "--boundary-epsilon-fraction",
            "1e-6",
        ],
    )
    assert "No such option" not in parsed.output
