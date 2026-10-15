from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np
import pytest

from aeris_research.common import PipelineError
from aeris_research.evidence import QualificationEvidence
from aeris_research.monitor import scan_campaign
from aeris_research.release import create_release


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def _scan(tmp_path: Path, *, accepted: bool = True):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    qualification = repo / "AERIS_MESH_STUDY/qualification"
    (qualification / "dataset").mkdir(parents=True)
    (qualification / "reports").mkdir()
    _json(qualification / "dataset/rows.json", [])
    root = repo / "AERIS_MESH_STUDY/artifacts/pilot"
    geometry = root / "g7"
    run = geometry / "a4"
    run.mkdir(parents=True)
    surface = run / "surface_surf.cgns"
    surface.write_bytes(b"stable surface payload")
    verdict = "ACCEPTED" if accepted else "REJECTED"
    result = {
        "routine_failed": False,
        "converged": True,
        "alpha_deg": 4.0,
        "mission": {"mach": 0.1, "reynolds": 2.0e6},
        "functions": {
            "case_cl": 0.4,
            "case_cd": 0.04,
            "case_cdp": 0.03,
            "case_cdv": 0.01,
            "case_cmy": 0.02,
        },
    }
    row = {
        "geometry_set": "development",
        "geometry_index": 7,
        "geometry_hash": "geometry-7",
        "design_vector": {"shape": 0.7},
        "grid_level": "coarse",
        "alpha_deg": 4.0,
        "mach": 0.1,
        "reynolds": 2.0e6,
        "area_ref": 1.0,
        "chord_ref": 1.0,
        "moment_ref_xyz": [0.0, 0.0, 0.0],
        "CL": 0.4,
        "CD": 0.04,
        "CDp": 0.03,
        "CDv": 0.01,
        "CMy": 0.02,
        "gate_verdict": verdict,
        "surface_field_path": str(surface.relative_to(repo)),
        "missing_fields": {},
    }
    gate = {
        "passes": accepted,
        "verdict": verdict,
        "alpha_deg": 4.0,
        "directory": str(run.relative_to(repo)),
        "iterations": 10,
        "checks": {
            "residual_orders": {"value": 6.0},
            "cl_percent": {"value": 0.01},
            "cd_percent": {"value": 0.02},
            "cmy_absolute": {"value": 1.0e-6},
        },
        "forces": {"cl": 0.4, "cd": 0.04, "cdp": 0.03, "cdv": 0.01, "cmy": 0.02},
    }
    _json(geometry / "dataset_rows.json", {"rows": [row]})
    _json(geometry / "gate.json", {"results": [gate]})
    _json(run / "result.json", result)
    _json(
        run / "memory_watch.json",
        {"aborted_reason": None, "samples": [{"t": 2.0}], "peak_rank_rss_sum_gib": 1.0},
    )
    run.joinpath("run.log").write_text(
        "1 1 3 ANK 5 1 0.1 1 2 3 4 5 6 0.4 0.04 0.03 0.01 0.02 1e-6\n"
    )
    return scan_campaign(qualification, [root], stale_after_seconds=0.0), repo


def test_release_is_accepted_only_content_addressed_and_reusable(tmp_path, monkeypatch):
    scan, repo = _scan(tmp_path)
    synthetic = type(
        "Surface",
        (),
        {
            "fields": {"CoefPressure": np.asarray([0.0])},
            "topology_hash": "topology",
            "coordinates": np.zeros((4, 3)),
            "connectivity": np.zeros((1, 4), dtype=int),
        },
    )()
    monkeypatch.setattr("aeris_research.release.read_surface", lambda _: synthetic)
    releases = repo / "research/releases"
    first = create_release(scan, releases)
    release = releases / first["release_id"]
    assert first["accepted_snapshots"] == 1
    assert first["reused"] is False
    row = json.loads((release / "dataset/rows.json").read_text())[0]
    archive = release / "dataset" / row["surface_field_archive"]
    assert gzip.decompress(archive.read_bytes()) == b"stable surface payload"
    assert QualificationEvidence(release).runs()[0].status == "FINAL_ACCEPTED"

    second = create_release(scan, releases)
    assert second["release_id"] == first["release_id"]
    assert second["reused"] is True


def test_release_refuses_scan_without_accepted_snapshots(tmp_path):
    scan, repo = _scan(tmp_path, accepted=False)
    with pytest.raises(PipelineError, match="no FINAL_ACCEPTED"):
        create_release(scan, repo / "research/releases")


def test_release_refuses_unreadable_cgns_payload(tmp_path):
    scan, repo = _scan(tmp_path)
    with pytest.raises(PipelineError):
        create_release(scan, repo / "research/releases")
