from __future__ import annotations

import json
from pathlib import Path

from aeris.dynamics.state_space_plots import render_state_space_plots


def _write_state_space_result(run_dir: Path) -> None:
    dyn = run_dir / "dynamics"
    dyn.mkdir(parents=True)
    payload = {
        "schema_version": "state_space_result_v0.2",
        "overall_status": "completed",
        "linear_stability_summary": {
            "overall_linear_stable": False,
            "total_unstable_eigenvalue_count": 2,
            "max_real_eigenvalue": 0.2,
        },
        "longitudinal": {
            "valid": True,
            "short_period": {
                "eigenvalue_real": -5.0,
                "eigenvalue_imag": 14.0,
                "stable": True,
                "zeta": 0.33,
                "omega_n": 14.9,
            },
            "phugoid": {
                "eigenvalue_real": 0.2,
                "eigenvalue_imag": 0.0,
                "stable": False,
            },
            "all_eigenvalues": [
                {"real": -5.0, "imag": 14.0},
                {"real": -5.0, "imag": -14.0},
                {"real": -0.2, "imag": 0.0},
                {"real": 0.2, "imag": 0.0},
            ],
        },
        "lateral_directional": {
            "valid": True,
            "roll_subsidence": {"eigenvalue_real": -20.0, "eigenvalue_imag": 0.0, "stable": True},
            "spiral": {"eigenvalue_real": 0.01, "eigenvalue_imag": 0.0, "stable": False},
            "dutch_roll": {
                "eigenvalue_real": -0.1,
                "eigenvalue_imag": 1.2,
                "stable": True,
                "zeta": 0.08,
            },
            "all_eigenvalues": [
                {"real": -20.0, "imag": 0.0},
                {"real": -0.1, "imag": 1.2},
                {"real": -0.1, "imag": -1.2},
                {"real": 0.01, "imag": 0.0},
            ],
        },
    }
    (dyn / "state_space_result.json").write_text(json.dumps(payload), encoding="utf-8")


def test_render_state_space_plots_all(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_state_space_result(run_dir)

    manifest = render_state_space_plots(run_dir=run_dir, plot="all", dpi=90)

    assert manifest["schema_version"] == "state_space_plot_manifest_v0.2"
    assert manifest["plot_count"] == 4
    assert Path(manifest["artifacts"]["eigenvalues_png"]).exists()
    assert Path(manifest["artifacts"]["eigenvalues_zoom_png"]).exists()
    assert Path(manifest["artifacts"]["mode_summary_png"]).exists()
    assert Path(manifest["artifacts"]["mode_summary_zoom_png"]).exists()
    assert manifest["zoom_policy"]["unstable_eigenvalues_always_kept_in_zoom"] is True
    assert Path(manifest["manifest_path"]).exists()


def test_render_state_space_plots_single_eigenvalue_plot(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_state_space_result(run_dir)

    manifest = render_state_space_plots(run_dir=run_dir, plot="eigenvalues", dpi=90)

    assert manifest["plot_count"] == 1
    assert Path(manifest["artifacts"]["eigenvalues_png"]).exists()
    assert manifest["artifacts"]["eigenvalues_zoom_png"] is None
    assert manifest["artifacts"]["mode_summary_png"] is None
    assert manifest["artifacts"]["mode_summary_zoom_png"] is None



def test_render_state_space_plots_single_zoom_plots(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_state_space_result(run_dir)

    eig_manifest = render_state_space_plots(run_dir=run_dir, plot="eigenvalues-zoom", dpi=90)
    assert eig_manifest["plot_count"] == 1
    assert Path(eig_manifest["artifacts"]["eigenvalues_zoom_png"]).exists()

    mode_manifest = render_state_space_plots(run_dir=run_dir, plot="mode-summary-zoom", dpi=90)
    assert mode_manifest["plot_count"] == 1
    assert Path(mode_manifest["artifacts"]["mode_summary_zoom_png"]).exists()

def test_render_state_space_plots_rejects_unknown_plot(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_state_space_result(run_dir)

    try:
        render_state_space_plots(run_dir=run_dir, plot="banana")
    except ValueError as exc:
        assert "Invalid plot" in str(exc)
    else:
        raise AssertionError("expected invalid plot to fail")
