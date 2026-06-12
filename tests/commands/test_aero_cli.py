from __future__ import annotations

from typer.testing import CliRunner

# Adjust this import if your cli entry object is named differently.
# Common possibilities:
# from aeris.cli import app
# from aeris.cli import main as app
from aeris.cli import app

runner = CliRunner()


def test_aero_help_runs() -> None:
    result = runner.invoke(app, ["aero", "--help"])
    assert result.exit_code == 0
    assert "run" in result.stdout
    assert "inspect" in result.stdout
    assert "sweep" in result.stdout


def test_aero_run_help_runs() -> None:
    result = runner.invoke(app, ["aero", "run", "--help"])
    assert result.exit_code == 0
    assert "--config" in result.stdout or "--run-dir" in result.stdout
    assert "--alpha" in result.stdout
    assert "--velocity" in result.stdout
    assert "--altitude" in result.stdout
    assert "--workflow" in result.stdout


def test_aero_inspect_help_runs() -> None:
    result = runner.invoke(app, ["aero", "inspect", "--help"])
    assert result.exit_code == 0
    assert "--run-dir" in result.stdout
    assert "--json" in result.stdout


def test_aero_sweep_help_runs() -> None:
    result = runner.invoke(app, ["aero", "sweep", "--help"])
    assert result.exit_code == 0
    assert "--alpha-values" in result.stdout
    assert "--beta-values" in result.stdout
    assert "--velocity-values" in result.stdout
    assert "--q-values" in result.stdout
    assert "--workflow" in result.stdout


def test_aero_sweep_inspect_help_runs() -> None:
    result = runner.invoke(app, ["aero", "sweep-inspect", "--help"])
    assert result.exit_code == 0
    assert "--run-dir" in result.stdout
    assert "--json" in result.stdout


def test_aero_sweep_case_inspect_help_runs() -> None:
    result = runner.invoke(app, ["aero", "sweep-case-inspect", "--help"])
    assert result.exit_code == 0
    assert "--run-dir" in result.stdout
    assert "--case-index" in result.stdout or "--case-label" in result.stdout
    assert "--json" in result.stdout


def test_aero_run_help_shows_diff_input_deg() -> None:
    result = runner.invoke(app, ["aero", "run", "--help"])
    assert result.exit_code == 0
    assert "--diff-input-deg" in result.stdout


def test_aero_sweep_help_shows_diff_input_values() -> None:
    result = runner.invoke(app, ["aero", "sweep", "--help"])
    assert result.exit_code == 0
    assert "--diff-input-values" in result.stdout


def test_aero_run_help_no_stale_d1_reference() -> None:
    result = runner.invoke(app, ["aero", "run", "--help"])
    assert result.exit_code == 0
    assert "d1 command" not in result.stdout


def test_aero_run_workflow_stage_is_aero_run() -> None:
    """The aero run workflow stage name must be 'aero_run', not 'aero_sweep'."""
    import ast, pathlib
    src = pathlib.Path("src/aeris/commands/aero.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_aero":
            func_src = ast.get_source_segment(src, node) or ""
            # Must contain aero_run stage inside run_aero function
            assert 'stage="aero_run"' in func_src, (
                "run_aero must record stage='aero_run', not 'aero_sweep'"
            )
            # Must NOT contain aero_sweep stage inside run_aero function
            assert 'stage="aero_sweep"' not in func_src, (
                "run_aero must not record stage='aero_sweep'"
            )
            return
    raise AssertionError("run_aero function not found in aero.py")

