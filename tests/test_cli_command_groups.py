from __future__ import annotations

from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_root_help_lists_core_command_groups() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    output = result.stdout

    for command_group in [
        "version",
        "geometry",
        "dataset",
        "pipeline",
        "aero",
        "dynamics",
        "ml",
    ]:
        assert command_group in output


def test_domain_help_commands_do_not_crash() -> None:
    for command_group in [
        "geometry",
        "dataset",
        "pipeline",
        "aero",
        "dynamics",
        "ml",
        "version",
    ]:
        result = runner.invoke(app, [command_group, "--help"])
        assert result.exit_code == 0, f"{command_group} --help failed:\n{result.stdout}"


def test_ml_subcommands_are_registered() -> None:
    result = runner.invoke(app, ["ml", "--help"])

    assert result.exit_code == 0
    output = result.stdout

    for subcommand in ["train", "compare", "predict"]:
        assert subcommand in output