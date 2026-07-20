"""CFD dataset collection with per-row verification gating."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from aeris.cfd.post.dataset import (
    collect_case_row,
    collect_cfd_dataset,
    gate_row,
    trust_chain_artifacts,
)


def _make_case(
    tmp_path: Path,
    name: str,
    *,
    status: str = "converged",
    orders: float = 6.0,
    march: str = "valid",
    cl: float = 0.4,
) -> Path:
    workdir = tmp_path / name
    solve = workdir / "solve"
    solve.mkdir(parents=True)
    (workdir / "case_manifest.json").write_text(json.dumps({"case": name}))
    (solve / "solve_report.json").write_text(
        json.dumps(
            {
                "schema": "aeris.cfd.solve_report.v1",
                "solver_id": "adflow",
                "status": status,
                "flow": {"alpha": 2.0, "mach": 0.2, "reynolds": 1e6, "temperature": 288.15},
                "refs": {"area_ref": 1.094, "chord_ref": 0.8774},
                "forces": {"cl": cl, "cd": 0.0264, "cmy": -0.34},
                "convergence": {"iterations": 113, "orders_dropped": orders},
            }
        )
    )
    (solve / "verification.json").write_text(
        json.dumps(
            {
                "schema": "aeris.cfd.verification.v1",
                "iterative": {
                    "status": status,
                    "returncode": 0,
                    "iterations": 113,
                    "orders_dropped": orders,
                    "final_resrho": 6.7e-5,
                },
                "mesh": {
                    "march_status": march,
                    "min_quality": 0.128,
                    "quality_warning": False,
                    "cgns_sha256": "a" * 64,
                },
                "solve_report_sha256": "b" * 64,
            }
        )
    )
    return workdir


def test_collect_case_row_pulls_verification(tmp_path: Path):
    row = collect_case_row(_make_case(tmp_path, "c1"))
    assert row["case"] == "c1"
    assert row["cl"] == 0.4
    assert row["orders_dropped"] == 6.0
    assert row["mesh_march_status"] == "valid"
    assert row["mesh_cgns_sha256"] == "a" * 64


def test_gate_row_reasons():
    good = {
        "solve_status": "converged",
        "mesh_march_status": "valid",
        "orders_dropped": 6.0,
        "cl": 0.4,
        "cd": 0.02,
    }
    assert gate_row(good) == []
    assert gate_row({**good, "solve_status": "failed"}) == ["solve_not_converged"]
    assert gate_row({**good, "mesh_march_status": "invalid"}) == ["mesh_march_invalid"]
    assert gate_row({**good, "orders_dropped": 2.0}) == ["insufficient_residual_drop"]
    assert "nonfinite_targets" in gate_row({**good, "cl": float("nan")})


def test_collect_cfd_dataset_gates_per_row(tmp_path: Path):
    cases = [
        _make_case(tmp_path, "good1"),
        _make_case(tmp_path, "good2", cl=0.5),
        _make_case(tmp_path, "bad_solve", status="failed"),
        _make_case(tmp_path, "bad_drop", orders=1.5),
    ]
    out = tmp_path / "dataset"
    report = collect_cfd_dataset(cases, out)
    assert report["kept_rows"] == 2
    assert report["rejected_rows"] == 2
    assert report["rejection_reason_counts"]["solve_not_converged"] == 1
    assert report["rejection_reason_counts"]["insufficient_residual_drop"] >= 1

    with (out / "cfd_dataset.csv").open() as handle:
        kept = list(csv.DictReader(handle))
    assert [row["case"] for row in kept] == ["good1", "good2"]
    assert kept[0]["mesh_cgns_sha256"] == "a" * 64  # provenance travels with the row

    gate = json.loads((out / "cfd_dataset_gate.json").read_text())
    assert gate["schema"] == "aeris.cfd.dataset_gate.v1"


def test_trust_chain_artifacts_lists_existing_files(tmp_path: Path):
    workdir = _make_case(tmp_path, "c1")
    (workdir / "surface").mkdir()
    (workdir / "surface" / "volume_report.json").write_text("{}")
    artifacts = trust_chain_artifacts(workdir)
    names = {path.name for path in artifacts}
    assert "solve_report.json" in names
    assert "verification.json" in names
    assert "volume_report.json" in names
    assert "case_manifest.json" in names
