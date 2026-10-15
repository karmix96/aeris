from __future__ import annotations

import json
from pathlib import Path

from aeris_research.monitor import scan_campaign


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def _case(tmp_path: Path, *, verdict: str = "ACCEPTED", converged: bool = True):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    qualification = repo / "AERIS_MESH_STUDY/qualification"
    (qualification / "dataset").mkdir(parents=True)
    (qualification / "reports").mkdir()
    _write_json(qualification / "dataset/rows.json", [])
    root = repo / "AERIS_MESH_STUDY/artifacts/pilot"
    geometry = root / "g1"
    run = geometry / "a0"
    run.mkdir(parents=True)
    surface = run / "case_surf.cgns"
    surface.write_bytes(b"CGNS payload")
    result = {
        "routine_failed": False,
        "converged": converged,
        "alpha_deg": 0.0,
        "mission": {"mach": 0.1, "reynolds": 1.0e6},
        "functions": {
            "case_cl": 0.2,
            "case_cd": 0.03,
            "case_cdp": 0.02,
            "case_cdv": 0.01,
            "case_cmy": -0.01,
        },
    }
    row = {
        "geometry_set": "development",
        "geometry_index": 1,
        "geometry_hash": "geometry-1",
        "design_vector": {"shape": 0.2},
        "grid_level": "coarse",
        "alpha_deg": 0.0,
        "mach": 0.1,
        "reynolds": 1.0e6,
        "CL": 0.2,
        "CD": 0.03,
        "CDp": 0.02,
        "CDv": 0.01,
        "CMy": -0.01,
        "gate_verdict": verdict,
        "surface_field_path": str(surface.relative_to(repo)),
    }
    passes = verdict == "ACCEPTED"
    gate_record = {
        "passes": passes,
        "verdict": verdict,
        "alpha_deg": 0.0,
        "directory": str(run.relative_to(repo)),
        "forces": {"cl": 0.2, "cd": 0.03, "cdp": 0.02, "cdv": 0.01, "cmy": -0.01},
    }
    _write_json(geometry / "dataset_rows.json", {"rows": [row]})
    _write_json(geometry / "gate.json", {"results": [gate_record]})
    _write_json(run / "result.json", result)
    _write_json(
        run / "memory_watch.json",
        {
            "peak_rank_rss_sum_gib": 1.2,
            "peak_swap_used_gib": 0.0,
            "aborted_reason": None,
            "samples": [{"t": 1.0}],
        },
    )
    run.joinpath("run.log").write_text(
        "1 1 3 ANK 5.0 1.0 0.1 1 2 3 4 5 6 0.2 0.03 0.02 0.01 -0.01 1e-5\n"
    )
    return qualification, root, run


def test_monitor_requires_scientific_completion_not_process_exit(tmp_path):
    qualification, root, _ = _case(tmp_path)
    scan = scan_campaign(qualification, [root], stale_after_seconds=0.0)
    assert len(scan.records) == 1
    assert scan.records[0].status == "FINAL_ACCEPTED"
    assert scan.report()["accepted_distinct_geometries"] == 1


def test_monitor_marks_rejected_gate_failed(tmp_path):
    qualification, root, _ = _case(tmp_path, verdict="REJECTED")
    record = scan_campaign(qualification, [root], stale_after_seconds=0.0).records[0]
    assert record.status == "FAILED"
    assert "gate_rejected" in record.reasons


def test_monitor_marks_recent_partial_run_running(tmp_path):
    qualification, root, run = _case(tmp_path)
    (run / "result.json").unlink()
    (run.parent / "gate.json").unlink()
    record = scan_campaign(qualification, [root], stale_after_seconds=3600.0).records[0]
    assert record.status == "RUNNING"
    assert "missing_result" in record.reasons
    assert "missing_gate" in record.reasons


def test_monitor_marks_stale_partial_run_incomplete(tmp_path):
    qualification, root, run = _case(tmp_path)
    (run.parent / "gate.json").unlink()
    record = scan_campaign(qualification, [root], stale_after_seconds=0.0).records[0]
    assert record.status == "INCOMPLETE"
    assert "missing_gate" in record.reasons


def test_monitor_marks_nonconverged_result_failed_even_with_accepted_gate(tmp_path):
    qualification, root, _ = _case(tmp_path, converged=False)
    record = scan_campaign(qualification, [root], stale_after_seconds=3600.0).records[0]
    assert record.status == "FAILED"
    assert "solver_not_converged" in record.reasons
