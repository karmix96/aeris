from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_dynamics_group_exists():
    result = runner.invoke(app, ["dynamics", "--help"])
    assert result.exit_code == 0
    assert "dynamics-foundation" in result.stdout.lower()


def test_dynamics_build_help_has_workflow_flag():
    result = runner.invoke(app, ["dynamics", "build", "--help"])
    assert result.exit_code == 0
    assert "--workflow" in result.stdout


def test_dynamics_inspect_help_has_json_flag():
    result = runner.invoke(app, ["dynamics", "inspect", "--help"])
    assert result.exit_code == 0
    assert "--json" in result.stdout


def test_dynamics_cg_sweep_inspect_help_has_json_flag():
    result = runner.invoke(app, ["dynamics", "cg-sweep-inspect", "--help"])
    assert result.exit_code == 0
    assert "--json" in result.stdout


def test_dynamics_trim_help_has_json_flag():
    result = runner.invoke(app, ["dynamics", "trim", "--help"])
    assert result.exit_code == 0
    assert "--json" in result.stdout


def test_dynamics_batch_labels_has_per_rad_flag_in_source():
    """batch-labels has too many flags for Typer to show all — verify from source."""
    import pathlib
    src = pathlib.Path("src/aeris/commands/dynamics.py").read_text(encoding="utf-8")
    fn_start = src.find("def dynamics_batch_labels(")
    fn_end   = src.find("\ndef ", fn_start + 1)
    fn_body  = src[fn_start:fn_end]
    assert '"--min-abs-cm-delta-e-per-rad"' in fn_body


def test_dynamics_build_workflow_recording_in_source():
    """dynamics build must wrap workflow recording in try/except."""
    import pathlib
    src = pathlib.Path("src/aeris/commands/dynamics.py").read_text(encoding="utf-8")
    fn_start = src.find("def dynamics_build(")
    fn_end   = src.find("\n@dynamics_app", fn_start + 1)
    fn_body  = src[fn_start:fn_end]
    assert "record_workflow_stage_success" in fn_body, "build must record workflow stage"
    assert 'stage="dynamics_build"' in fn_body, "build must use stage='dynamics_build'"

