"""ADflow adapter: options parity with the legacy smoke driver, prepare, parse."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aeris.cfd.case.spec import FlowConditions, SolveSpec
from aeris.cfd.options.layers import OptionLayer
from aeris.cfd.presets.registry import get_preset
from aeris.cfd.solvers.adflow.adapter import AdflowAdapter
from aeris.cfd.solvers.adflow.options_schema import build_adflow_options
from aeris.cfd.solvers.adflow.parse import parse_monitor_history, resrho_from_line
from aeris.cfd.solvers.base import get_solver_adapter

GRID = Path("/tmp/mesh/wing_vol_smoke.cgns")
OUT = Path("/tmp/mesh/adflow")


def _preset_layer() -> OptionLayer:
    preset = get_preset("rans_ank_nk_v1")
    return OptionLayer("preset:rans_ank_nk_v1", dict(preset.solver))


def test_default_options_equal_legacy_smoke_driver_dict():
    """aeris defaults + rans_ank_nk_v1 == the exact scripts/adflow_smoke.py dict."""
    effective = build_adflow_options(GRID, OUT, extra_layers=[_preset_layer()])
    assert effective.values == {
        "gridFile": str(GRID),
        "outputDirectory": str(OUT),
        "monitorVariables": ["resrho", "resturb", "cl", "cd"],
        "surfaceVariables": ["cp", "cf", "yplus", "vx", "vy", "vz"],
        "writeTecplotSurfaceSolution": False,
        "equationType": "RANS",
        "liftIndex": 3,
        "MGCycle": "sg",
        "useANKSolver": True,
        "ANKSwitchTol": 1.0,
        "useNKSolver": True,
        "NKSwitchTol": 1.0e-6,
        "nCycles": 20000,
        "L2Convergence": 1.0e-8,
    }
    assert effective.provenance["MGCycle"] == "preset:rans_ank_nk_v1"
    assert effective.provenance["liftIndex"] == "aeris-default"


def test_raw_pass_through_reaches_adflow_verbatim():
    effective = build_adflow_options(
        GRID,
        OUT,
        extra_layers=[_preset_layer()],
        adflow_options={"ANKCFLLimit": 1e4, "turbulenceModel": "SST"},
    )
    assert effective.values["ANKCFLLimit"] == 1e4
    assert effective.values["turbulenceModel"] == "SST"
    assert effective.provenance["ANKCFLLimit"] == "raw"
    # turbulenceModel is curated; raw shadowing is traced
    assert "turbulence_model" in effective.overridden_curated_keys


def _spec(**kwargs) -> SolveSpec:
    base = dict(
        solver="adflow",
        flow=FlowConditions(alpha=2.0, mach=0.2, reynolds=1.0e6),
        area_ref=1.094,
        chord_ref=0.8774,
        mpi_np=4,
    )
    base.update(kwargs)
    return SolveSpec(**base)


def test_prepare_writes_static_runner_and_manifests(tmp_path: Path):
    grid = tmp_path / "wing_vol_smoke.cgns"
    grid.write_bytes(b"dummy cgns")
    workdir = tmp_path / "solve"
    prepared = AdflowAdapter().prepare(_spec(), grid, workdir)

    runner_text = (workdir / "run_adflow.py").read_text()
    assert "20000" not in runner_text  # nothing baked in
    assert "adflow_options.json" in runner_text

    options = json.loads((workdir / "adflow_options.json").read_text())
    assert options["MGCycle"] == "sg"
    assert options["gridFile"] == str(grid)

    case = json.loads((workdir / "adflow_case.json").read_text())
    assert case["alpha"] == 2.0
    assert case["area_ref"] == 1.094
    assert case["eval_funcs"] == ["cl", "cd", "cmy"]

    manifest = json.loads((workdir / "adflow_effective_options.json").read_text())
    assert manifest["extra"]["solver_preset"] == "rans_ank_nk_v1"
    assert isinstance(manifest["input_sha256"]["volume_mesh"], str)

    assert prepared.command[1:3] == ("-np", "4")
    assert prepared.command[-1].endswith("run_adflow.py")


def test_prepare_requires_refs(tmp_path: Path):
    grid = tmp_path / "g.cgns"
    grid.write_bytes(b"x")
    with pytest.raises(ValueError, match="area_ref"):
        AdflowAdapter().prepare(_spec(area_ref=None), grid, tmp_path / "s")


MONITOR_LINE = (
    "      1       5          5     *ANK    10.0  1.0  0.01  "
    "1.2345E-03  2.0E-04  0.4321  0.0123  4.5E-02"
)
NK_MONITOR_LINE = (
    "      1     150       1480       NK     ----    1.00  0.540  "
    "1.602654E-04  1.503105E-09  -1.946696E-02  3.366330E-02  2.804432E-01"
)


def test_resrho_column_convention():
    assert resrho_from_line(MONITOR_LINE) == pytest.approx(1.2345e-03)
    assert resrho_from_line(NK_MONITOR_LINE) == pytest.approx(1.602654e-04)
    assert resrho_from_line("some text line") is None


def test_parse_monitor_history_orders_dropped():
    lines = [
        MONITOR_LINE,
        MONITOR_LINE.replace("1.2345E-03", "1.2345E-08"),
    ]
    history = parse_monitor_history("\n".join(lines))
    assert history["iterations"] == 2
    assert history["final_resrho"] == pytest.approx(1.2345e-08)
    assert history["orders_dropped"] == pytest.approx(5.0)


def test_parse_monitor_history_keeps_newton_rows():
    history = parse_monitor_history("\n".join([MONITOR_LINE, NK_MONITOR_LINE]))
    assert history["iterations"] == 2
    assert history["final_resrho"] == pytest.approx(1.602654e-04)


def test_parse_produces_normalized_solve_report(tmp_path: Path):
    grid = tmp_path / "g.cgns"
    grid.write_bytes(b"x")
    workdir = tmp_path / "solve"
    adapter = AdflowAdapter()
    adapter.prepare(_spec(), grid, workdir)
    # simulate a finished run
    (workdir / "adflow_run.json").write_text(
        json.dumps(
            {
                "schema": "aeris.cfd.adflow_run.v1",
                "solve_failed": False,
                "functions": {"cl": 0.4321, "cd": 0.0123, "cmy": -0.05},
                "elapsed_seconds": 12.5,
            }
        )
    )
    (workdir / "adflow_run.log").write_text(MONITOR_LINE + "\n")

    report = adapter.parse(workdir)
    assert report.status == "converged"
    assert report.forces["cl"] == pytest.approx(0.4321)
    assert report.flow["alpha"] == 2.0
    assert report.convergence["final_resrho"] == pytest.approx(1.2345e-03)

    on_disk = json.loads((workdir / "solve_report.json").read_text())
    assert on_disk["schema"] == "aeris.cfd.solve_report.v1"
    assert on_disk["solver_id"] == "adflow"


def test_parse_without_run_json_is_failed(tmp_path: Path):
    grid = tmp_path / "g.cgns"
    grid.write_bytes(b"x")
    workdir = tmp_path / "solve"
    adapter = AdflowAdapter()
    adapter.prepare(_spec(), grid, workdir)
    report = adapter.parse(workdir)
    assert report.status == "failed"


def test_solver_registry():
    assert get_solver_adapter("adflow").SOLVER_ID == "adflow"
    with pytest.raises(ValueError, match="Available"):
        get_solver_adapter("openfoam")
