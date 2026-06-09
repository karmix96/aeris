"""
CLI tests for aeris airfoil commands (Domain 2).
Covers: check-solver, library-stats, dataset generate --n-airfoils/--seed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


# ── Registration / help ───────────────────────────────────────────────────────

def test_airfoil_help_shows_new_commands():
    result = runner.invoke(app, ["airfoil", "--help"])
    assert result.exit_code == 0, result.output
    assert "check-solver" in result.output
    assert "library-stats" in result.output


def test_airfoil_dataset_generate_help_has_n_airfoils():
    result = runner.invoke(app, ["airfoil", "dataset", "generate", "--help"])
    assert result.exit_code == 0, result.output
    assert "--n-airfoils" in result.output
    assert "--seed" in result.output


# ── check-solver ──────────────────────────────────────────────────────────────

def test_airfoil_check_solver_help():
    result = runner.invoke(app, ["airfoil", "check-solver", "--help"])
    assert result.exit_code == 0, result.output


def test_airfoil_check_solver_exits_0_when_binary_found(monkeypatch):
    import shutil as _shutil
    import aeris.aero_2d.xfoil_adapter as xa
    monkeypatch.setattr(_shutil, "which", lambda b: f"/usr/bin/{b}")
    monkeypatch.setattr(xa, "_xfoil_version", lambda _: "XFOIL Version 6.99")

    result = runner.invoke(app, ["airfoil", "check-solver"])
    assert result.exit_code == 0, result.output
    assert "ready" in result.output.lower()
    assert "6.99" in result.output


def test_airfoil_check_solver_exits_1_when_binary_missing(monkeypatch):
    import shutil as _shutil
    import shutil
    if shutil.which("xfoil") is not None:
        pytest.skip("xfoil installed — skip missing-binary test")
    monkeypatch.setattr(_shutil, "which", lambda _: None)

    result = runner.invoke(app, ["airfoil", "check-solver"])
    assert result.exit_code == 1
    assert "NOT FOUND" in result.output


# ── library-stats ─────────────────────────────────────────────────────────────

def test_airfoil_library_stats_help():
    result = runner.invoke(app, ["airfoil", "library-stats", "--help"])
    assert result.exit_code == 0, result.output


def test_airfoil_library_stats_exits_1_when_no_inventory(tmp_path):
    result = runner.invoke(app, ["airfoil", "library-stats",
                                 "--library", str(tmp_path / "no_lib")])
    assert result.exit_code == 1
    out = result.output.lower()
    assert "not found" in out or "ingest" in out


def test_airfoil_library_stats_reads_inventory(tmp_path):
    lib = tmp_path / "lib"; lib.mkdir()
    pd.DataFrame([
        {"airfoil_id": "aaa", "name": "NACA 0012", "family": "naca4",
         "t_c": 0.12, "t_c_x": 0.3, "camber_max": 0.00, "camber_max_x": 0.0,
         "le_radius": 0.016, "te_angle_deg": 12.0, "n_coords": 100, "source_file": "a.dat"},
        {"airfoil_id": "bbb", "name": "NACA 4412", "family": "naca4",
         "t_c": 0.12, "t_c_x": 0.3, "camber_max": 0.04, "camber_max_x": 0.4,
         "le_radius": 0.020, "te_angle_deg": 12.0, "n_coords": 100, "source_file": "b.dat"},
    ]).to_csv(lib / "airfoil_inventory.csv", index=False)

    result = runner.invoke(app, ["airfoil", "library-stats", "--library", str(lib)])
    assert result.exit_code == 0, result.output
    assert "2" in result.output
    assert "naca4" in result.output
    assert "t/c" in result.output.lower()


# ── dataset generate --n-airfoils ─────────────────────────────────────────────

def _fake_lib(tmp_path: Path, n: int = 10) -> Path:
    lib = tmp_path / "lib"; lib.mkdir()
    (lib / "coords").mkdir()
    rows = [{"airfoil_id": f"id{i:02d}", "name": f"A{i}", "family": "naca4",
             "t_c": 0.12, "t_c_x": 0.3, "camber_max": 0.0, "camber_max_x": 0.0,
             "le_radius": 0.016, "te_angle_deg": 12.0, "n_coords": 100,
             "source_file": f"a{i}.dat"} for i in range(n)]
    pd.DataFrame(rows).to_csv(lib / "airfoil_inventory.csv", index=False)
    return lib


def _fake_cfg(tmp_path: Path) -> Path:
    cfg = tmp_path / "sweep.yaml"
    cfg.write_text(
        "sweep:\n  alpha_start: 0\n  alpha_end: 2\n  alpha_step: 2\n"
        "  reynolds: [1000000]\nsolver:\n  max_iter: 10\n  repanel: true\n"
        "output:\n  drop_unconverged: false\n  solver_id: x\n",
        encoding="utf-8",
    )
    return cfg


def test_dataset_generate_n_airfoils_subsets(tmp_path, monkeypatch):
    """--n-airfoils 3 must pass a 3-element airfoil_ids list to generate_airfoil_dataset."""
    lib = _fake_lib(tmp_path, n=10)
    cfg = _fake_cfg(tmp_path)
    captured: dict = {}

    import aeris.airfoil.dataset_generate as dg
    def fake_gen(*, library_dir, config_path, dataset_root, name, airfoil_ids=None):
        captured["airfoil_ids"] = airfoil_ids
        return {"total_rows": 3, "converged_rows": 3, "convergence_rate": 1.0,
                "solver_failure_rows": 0}
    monkeypatch.setattr(dg, "generate_airfoil_dataset", fake_gen)

    result = runner.invoke(app, [
        "airfoil", "dataset", "generate",
        "--library", str(lib), "--config", str(cfg),
        "--name", "test", "--datasets-dir", str(tmp_path / "ds"),
        "--n-airfoils", "3", "--seed", "42",
    ])

    assert result.exit_code == 0, f"generate failed:\n{result.output}"
    assert captured["airfoil_ids"] is not None
    assert len(captured["airfoil_ids"]) == 3
    assert "Subset: 3/10" in result.output


def test_dataset_generate_no_n_airfoils_passes_none(tmp_path, monkeypatch):
    """Without --n-airfoils, airfoil_ids=None must reach generate_airfoil_dataset."""
    lib = _fake_lib(tmp_path, n=5)
    cfg = _fake_cfg(tmp_path)
    captured: dict = {}

    import aeris.airfoil.dataset_generate as dg
    def fake_gen(*, library_dir, config_path, dataset_root, name, airfoil_ids=None):
        captured["airfoil_ids"] = airfoil_ids
        return {"total_rows": 5, "converged_rows": 5, "convergence_rate": 1.0,
                "solver_failure_rows": 0}
    monkeypatch.setattr(dg, "generate_airfoil_dataset", fake_gen)

    result = runner.invoke(app, [
        "airfoil", "dataset", "generate",
        "--library", str(lib), "--config", str(cfg),
        "--name", "all_ds", "--datasets-dir", str(tmp_path / "ds"),
    ])

    assert result.exit_code == 0, f"generate failed:\n{result.output}"
    assert captured["airfoil_ids"] is None


def test_dataset_generate_n_airfoils_seed_deterministic(tmp_path, monkeypatch):
    """Same --seed must produce the same subset every time."""
    lib = _fake_lib(tmp_path, n=20)
    cfg = _fake_cfg(tmp_path)
    subsets: list = []

    import aeris.airfoil.dataset_generate as dg
    def fake_gen(*, library_dir, config_path, dataset_root, name, airfoil_ids=None):
        subsets.append(list(airfoil_ids) if airfoil_ids else None)
        return {"total_rows": 5, "converged_rows": 5, "convergence_rate": 1.0,
                "solver_failure_rows": 0}
    monkeypatch.setattr(dg, "generate_airfoil_dataset", fake_gen)

    for _ in range(2):
        runner.invoke(app, [
            "airfoil", "dataset", "generate",
            "--library", str(lib), "--config", str(cfg),
            "--name", "rep", "--datasets-dir", str(tmp_path / "ds"),
            "--n-airfoils", "5", "--seed", "99",
        ])

    assert len(subsets) == 2
    assert subsets[0] == subsets[1], "Same seed must produce same subset"
