"""
Tests: commands.dataset

Purpose:
    Validate basic CLI behavior for dataset commands.

What is tested:
    - Dataset command help renders
    - Dataset generate help renders
    - Dataset inspect help renders

Why it matters:
    Confirms dataset command registration and operator entrypoints work.
"""

from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_dataset_help_runs() -> None:
    result = runner.invoke(app, ["dataset", "--help"])
    assert result.exit_code == 0


def test_dataset_generate_help_runs() -> None:
    result = runner.invoke(app, ["dataset", "generate", "--help"])
    assert result.exit_code == 0


def test_dataset_inspect_help_runs() -> None:
    result = runner.invoke(app, ["dataset", "inspect", "--help"])
    assert result.exit_code == 0

def test_dataset_generate_help_mentions_qc_preset() -> None:
    result = runner.invoke(app, ["dataset", "generate", "--help"])
    assert result.exit_code == 0
    assert "--qc-preset" in result.stdout
    assert "production" in result.stdout
    assert "promotion_strict" in result.stdout


def test_dataset_aero_generate_help_mentions_qc_preset() -> None:
    result = runner.invoke(app, ["dataset", "aero-generate", "--help"])
    assert result.exit_code == 0
    assert "--qc-preset" in result.stdout
    assert "production" in result.stdout
    assert "promotion_strict" in result.stdout

def test_dataset_aero_generate_help_mentions_override_behavior() -> None:
    result = runner.invoke(app, ["dataset", "aero-generate", "--help"])
    assert result.exit_code == 0
    assert "overrides" in result.stdout.lower()

def test_dataset_curate_aero_help_runs() -> None:
    result = runner.invoke(app, ["dataset", "curate-aero", "--help"])
    assert result.exit_code == 0
    assert "--dataset" in result.stdout
    assert "--reject-incomple" in result.stdout or "incomplete." in result.stdout

def test_dataset_aero_generate_help_runs() -> None:
    result = runner.invoke(app, ["dataset", "aero-generate", "--help"])
    assert result.exit_code == 0
    assert "Generate a unified aero dataset from a geometry config." in result.stdout


def test_dataset_inspect_help_has_json_flag():
    result = runner.invoke(app, ["dataset", "inspect", "--help"])
    assert result.exit_code == 0
    assert "--json" in result.stdout


def test_dataset_qc_help_runs():
    result = runner.invoke(app, ["dataset", "qc", "--help"])
    assert result.exit_code == 0
    assert "--dataset" in result.stdout
    assert "--profile" in result.stdout


def test_dataset_compute_control_derivatives_help_has_per_rad_flag():
    result = runner.invoke(app, ["dataset", "compute-control-derivatives", "--help"])
    assert result.exit_code == 0
    # Typer truncates long flags with ellipsis in narrow terminals — check unambiguous prefix
    assert "min-abs-cm-delta-e-per" in result.stdout


def test_dataset_compute_flyability_labels_help_has_per_rad_flag():
    result = runner.invoke(app, ["dataset", "compute-flyability-labels", "--help"])
    assert result.exit_code == 0
    assert "min-abs-cm-delta-e-per" in result.stdout


def test_dataset_compute_dynamics_labels_has_per_rad_flag():
    """compute-dynamics-labels has too many flags for Typer to show all in narrow
    terminal help — verify the rename directly from source instead."""
    import pathlib
    src = pathlib.Path("src/aeris/commands/dataset.py").read_text(encoding="utf-8")
    # Find the compute_dynamics_labels function and check the flag name
    fn_start = src.find("def dataset_compute_dynamics_labels(")
    fn_end   = src.find("\ndef ", fn_start + 1)
    fn_body  = src[fn_start:fn_end]
    assert '"--min-abs-cm-delta-e-per-rad"' in fn_body, (
        "compute-dynamics-labels must use --min-abs-cm-delta-e-per-rad"
    )
    assert '"--min-abs-cm-delta-e",' not in fn_body, (
        "old short flag name must be gone from compute-dynamics-labels"
    )


def test_dataset_aero_generate_compound_stage_not_aero_sweep():
    """Compound aero-generate must not record stage 'aero_sweep' — that name
    is reserved for standalone aeris aero sweep commands."""
    import ast, pathlib
    src = pathlib.Path("src/aeris/commands/dataset.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "dataset_aero_generate":
            func_src = ast.get_source_segment(src, node) or ""
            assert 'stage="aero_sweep"' not in func_src, (
                "dataset_aero_generate must not use stage='aero_sweep'; "
                "use 'aero_dataset_sweep' to avoid collision with standalone sweep records"
            )
            assert 'stage="aero_dataset_sweep"' in func_src, (
                "dataset_aero_generate must use stage='aero_dataset_sweep'"
            )
            return
    raise AssertionError("dataset_aero_generate function not found")

