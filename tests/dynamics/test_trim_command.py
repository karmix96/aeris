import json
from typer.testing import CliRunner
from aeris.cli import app

runner = CliRunner()


def test_trim_command(tmp_path):
    run_dir = tmp_path / "run_001"
    aero_dir = run_dir / "aero"
    aero_dir.mkdir(parents=True)

    aero_result = {
        "scalars": {"cm": -0.47811},
        "stability_axis_derivatives": {"Cma": -2.517702},
        "solver_metadata": {
            "flight_condition": {"alpha_deg": 4.0}
        },
    }

    (aero_dir / "aero_result.json").write_text(json.dumps(aero_result), encoding="utf-8")

    result = runner.invoke(app, ["dynamics", "trim", "--run-dir", str(run_dir)])

    assert result.exit_code == 0
    assert "Estimated trim alpha" in result.output