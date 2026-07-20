"""SU2 adapter: golden cfg, history parsing, normalized report parity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aeris.cfd.case.spec import FlowConditions, SolveSpec
from aeris.cfd.solvers.base import SolveReport, get_solver_adapter
from aeris.cfd.solvers.su2.adapter import Su2Adapter
from aeris.cfd.solvers.su2.cfg_writer import format_su2_value
from aeris.cfd.solvers.su2.parse import parse_history_csv


def _spec(**kwargs) -> SolveSpec:
    base = dict(
        solver="su2",
        flow=FlowConditions(alpha=10.0, mach=0.15, reynolds=6.0e6, temperature=300.0),
        area_ref=1.0,
        chord_ref=1.0,
        mpi_np=4,
    )
    base.update(kwargs)
    return SolveSpec(**base)


def test_prepare_writes_golden_cfg(tmp_path: Path):
    grid = tmp_path / "wing_vol_smoke.su2"
    grid.write_bytes(b"dummy")
    workdir = tmp_path / "solve"
    prepared = Su2Adapter().prepare(_spec(), grid, workdir)

    cfg = (workdir / "case.cfg").read_text().splitlines()
    body = {
        line.split("= ", 1)[0]: line.split("= ", 1)[1]
        for line in cfg
        if "= " in line and not line.startswith("%")
    }
    # golden expectations: physics invariants + preset strategy + flow
    assert body["SOLVER"].startswith("RANS")
    assert body["KIND_TURB_MODEL"].split("  %")[0].strip() == "SA"
    assert body["MACH_NUMBER"].split("  %")[0].strip() == "0.15"
    assert body["AOA"].split("  %")[0].strip() == "10.0"
    assert body["REYNOLDS_NUMBER"].split("  %")[0].strip() == "6000000.0"
    assert body["MESH_FORMAT"].split("  %")[0].strip() == "SU2"
    assert body["MESH_FILENAME"].split("  %")[0].strip() == str(grid)
    assert body["MARKER_HEATFLUX"].split("  %")[0].strip() == "( wall, 0.0 )"
    assert body["CFL_NUMBER"].split("  %")[0].strip() == "10.0"
    assert body["CONV_RESIDUAL_MINVAL"].split("  %")[0].strip() == "-10"
    # provenance annotations present
    assert any("% preset:su2_rans_sa_v1" in line for line in cfg)
    assert any("% flow" in line for line in cfg)
    # deterministic ordering
    keys = [line.split("= ", 1)[0] for line in cfg if "= " in line and not line.startswith("%")]
    assert keys == sorted(keys)
    assert prepared.command[-1].endswith("case.cfg")


def test_raw_su2_option_reaches_cfg_verbatim(tmp_path: Path):
    grid = tmp_path / "g.su2"
    grid.write_bytes(b"x")
    prepared = Su2Adapter().prepare(
        _spec(raw_options={"MUSCL_FLOW": "YES", "VENKAT_LIMITER_COEFF": 0.03}),
        grid,
        tmp_path / "solve",
    )
    cfg = Path(prepared.artifacts["cfg"]).read_text()
    assert "MUSCL_FLOW= YES  % raw" in cfg
    assert "VENKAT_LIMITER_COEFF= 0.03  % raw" in cfg


def test_format_su2_value():
    assert format_su2_value(True) == "YES"
    assert format_su2_value(False) == "NO"
    assert format_su2_value([1, 2]) == "( 1, 2 )"
    assert format_su2_value("( wall, 0.0 )") == "( wall, 0.0 )"


HISTORY_CSV = """"Inner_Iter","rms[Rho]","rms[RhoU]","CL","CD","CMz"
0, -2.0, -1.5, 0.1, 0.05, -0.01
1, -4.0, -3.2, 0.8, 0.02, -0.02
2, -8.5, -7.1, 1.0850, 0.01240, -0.0300
"""


def test_parse_history_csv(tmp_path: Path):
    path = tmp_path / "history.csv"
    path.write_text(HISTORY_CSV)
    history = parse_history_csv(path)
    assert history["iterations"] == 3
    assert history["final_resrho_log10"] == pytest.approx(-8.5)
    assert history["orders_dropped"] == pytest.approx(6.5)
    assert history["final_coefficients"]["cl"] == pytest.approx(1.0850)
    assert history["final_coefficients"]["cd"] == pytest.approx(0.01240)


def test_parse_produces_same_report_schema_as_adflow(tmp_path: Path):
    grid = tmp_path / "g.su2"
    grid.write_bytes(b"x")
    workdir = tmp_path / "solve"
    adapter = Su2Adapter()
    adapter.prepare(_spec(), grid, workdir)
    (workdir / "history.csv").write_text(HISTORY_CSV)

    report = adapter.parse(workdir)
    assert isinstance(report, SolveReport)
    assert report.status == "converged"
    assert report.forces["cl"] == pytest.approx(1.0850)

    on_disk = json.loads((workdir / "solve_report.json").read_text())
    assert on_disk["schema"] == "aeris.cfd.solve_report.v1"
    assert on_disk["solver_id"] == "su2"
    # same normalized top-level keys as the ADflow report
    assert {"status", "flow", "refs", "forces", "convergence", "artifacts"} <= set(on_disk)


def test_parse_without_history_is_failed(tmp_path: Path):
    grid = tmp_path / "g.su2"
    grid.write_bytes(b"x")
    workdir = tmp_path / "solve"
    adapter = Su2Adapter()
    adapter.prepare(_spec(), grid, workdir)
    assert adapter.parse(workdir).status == "failed"


def test_su2_registered_in_solver_registry():
    assert get_solver_adapter("su2").SOLVER_ID == "su2"
