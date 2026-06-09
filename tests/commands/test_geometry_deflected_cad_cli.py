from typer.testing import CliRunner

from aeris.cli import app


def test_geometry_export_deflected_cad_help():
    result = CliRunner().invoke(app, ["geometry", "export-deflected-cad", "--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "export-deflected-cad" in result.output
    # Do not assert exact long option names here: Typer/Rich may truncate
    # them depending on terminal width, e.g. --delta-e-sym-deg may render
    # as --delta-e-sym-d… in CI or local terminals.
    assert "deflected" in result.output.lower()
