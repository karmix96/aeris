import json
from typer.testing import CliRunner
from aeris.cli import app

runner = CliRunner()


def test_dynamics_build_with_mass_config(tmp_path):
    run_dir = tmp_path / "run_001"
    aero_dir = run_dir / "aero"
    geom_dir = run_dir / "geometry"
    aero_dir.mkdir(parents=True)
    geom_dir.mkdir(parents=True)

    aero_result = {
        "scalars": {"x_np": 0.557037},
        "stability_axis_derivatives": {"Cma": -2.517702},
        "derived_metrics": {"spiral_metric": 0.559975},
        "solver_id": "aerosandbox_avl",
    }

    geometry_summary = {
        "reference_values": {
            "mean_aerodynamic_chord_m": 0.8774849008856921
        }
    }

    (aero_dir / "aero_result.json").write_text(json.dumps(aero_result), encoding="utf-8")
    (geom_dir / "geometry_summary.json").write_text(json.dumps(geometry_summary), encoding="utf-8")

    mass_cfg = tmp_path / "mass.yaml"
    mass_cfg.write_text(
        """
mass_properties:
  mass_kg: 12.5
  x_cg_m: 0.4
  ixx_kg_m2: 0.8
  iyy_kg_m2: 1.5
  izz_kg_m2: 2.1
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "dynamics",
            "build",
            "--run-dir", str(run_dir),
            "--mass-config", str(mass_cfg),
        ],
    )

    assert result.exit_code == 0
    assert "Static margin" in result.output