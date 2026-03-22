from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_dynamics_group_exists():
    result = runner.invoke(app, ["dynamics", "--help"])
    assert result.exit_code == 0
    assert "dynamics-foundation" in result.stdout.lower()