import json

from aeris.dynamics.cg_sweep import run_cg_sweep, estimate_zero_crossing


def test_cg_sweep_runs(tmp_path):
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

    summary = run_cg_sweep(
        run_dir=run_dir,
        mass_kg=12.5,
        cg_min_m=0.35,
        cg_max_m=0.75,
        n=5,
        ixx_kg_m2=0.80,
        iyy_kg_m2=1.50,
        izz_kg_m2=2.10,
    )

    assert len(summary["cases"]) == 5
    assert summary["cases"][0]["static_margin"] is not None

def test_zero_crossing_estimate():
    cases = [
        {"x_cg_m": 0.50, "static_margin": 0.05},
        {"x_cg_m": 0.60, "static_margin": -0.05},
    ]

    zc = estimate_zero_crossing(cases)
    assert zc is not None
    assert abs(zc - 0.55) < 1e-9