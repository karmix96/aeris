import json

from aeris.dynamics.analysis import build_dynamics_foundation_result
from aeris.dynamics.models import MassProperties


def test_mac_falls_back_to_geometry_summary(tmp_path):
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
            "mean_aerodynamic_chord_m": 0.40
        }
    }

    # not strictly needed if your function accepts dict directly,
    # but keeps the run-folder layout realistic
    (aero_dir / "aero_result.json").write_text(json.dumps(aero_result), encoding="utf-8")
    (geom_dir / "geometry_summary.json").write_text(json.dumps(geometry_summary), encoding="utf-8")

    result = build_dynamics_foundation_result(
        aero_result=aero_result,
        mass_properties=MassProperties(mass_kg=12.5, x_cg_m=0.72),
        source_run_dir=run_dir,
    )

    assert result.stability_metrics.mac_m == 0.40
    assert result.stability_metrics.static_margin is not None