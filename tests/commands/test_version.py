"""
Tests: commands.version

Purpose:
    Validate CLI version reporting.

What is tested:
    - Version command runs successfully
    - Output includes the package name

Why it matters:
    Confirms the CLI entrypoint and version registration are working.
"""

from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_version_command_runs() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "aeris" in result.stdout.lower()