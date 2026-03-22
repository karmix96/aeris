import json
from typer.testing import CliRunner
from aeris.cli import app

runner = CliRunner()


def test_cg_sweep_inspect_command(tmp_path):
    run_dir = tmp_path / "run_001"
    dyn_dir = run_dir / "dynamics"
    dyn_dir.mkdir(parents=True)

    payload = {
        "mass_kg": 12.5,
        "cg_min_m": 0.35,
        "cg_max_m": 0.75,
        "static_margin_zero_crossing_estimate_m": 0.557,
        "stable_cg_min_m": 0.35,
        "stable_cg_max_m": 0.55,
        "cases": [
            {
                "x_cg_m": 0.35,
                "static_margin_percent_mac": 23.5,
                "longitudinal_interpretation": "positive_static_margin",
            },
            {
                "x_cg_m": 0.65,
                "static_margin_percent_mac": -10.2,
                "longitudinal_interpretation": "negative_static_margin",
            },
        ],
    }

    (dyn_dir / "cg_sweep.json").write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(app, ["dynamics", "cg-sweep-inspect", "--run-dir", str(run_dir)])

    assert result.exit_code == 0
    assert "Static-margin zero crossing estimate" in result.output
    assert "positive_static_margin" in result.output
    assert "negative_static_margin" in result.output