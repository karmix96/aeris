from __future__ import annotations

import gzip
import hashlib
import json

from aeris_research.evidence import (
    QualificationEvidence,
    parse_adflow_history,
    surface_payload_sha256,
)


def test_gzip_payload_hash_is_not_container_hash(tmp_path):
    payload = b"scientific CGNS payload\n"
    archive = tmp_path / "field.cgns.gz"
    with gzip.open(archive, "wb") as stream:
        stream.write(payload)
    assert surface_payload_sha256(archive) == hashlib.sha256(payload).hexdigest()
    assert hashlib.sha256(archive.read_bytes()).hexdigest() != surface_payload_sha256(archive)


def test_uncompressed_payload_hash(tmp_path):
    payload = b"uncompressed CGNS payload\n"
    field = tmp_path / "field.cgns"
    field.write_bytes(payload)
    assert surface_payload_sha256(field) == hashlib.sha256(payload).hexdigest()


def test_adflow_history_parser_reads_coefficients_and_normalises_residual():
    text = (
        "1 1 3 *ANK 5.00E+00 1.00 0.012 1 2 3 4 5 6 "
        "-1.5 0.12 0.07 0.05 0.01 1.0E+03\n"
        "1 2 7 ANK 2.50E+01 1.00 0.016 1 2 3 4 5 6 "
        "-0.2 0.02 0.01 0.01 0.001 1.0E+01\n"
    )
    records = parse_adflow_history(text)
    assert len(records) == 2
    assert records[0]["preconditioner_updated"] is True
    assert records[1]["cl"] == -0.2
    assert records[1]["relative_residual"] == 0.01


def test_successful_process_evidence_is_not_completion_without_convergence(tmp_path):
    repo = tmp_path / "repo"
    qualification = repo / "AERIS_MESH_STUDY/qualification"
    run_directory = qualification / "dataset/runs/case"
    field_directory = qualification / "dataset/fields"
    for directory in (repo / ".git", qualification / "reports", run_directory, field_directory):
        directory.mkdir(parents=True, exist_ok=True)
    payload = b"field"
    (field_directory / "case.cgns").write_bytes(payload)
    row = {
        "run_name": "case",
        "alpha_deg": 0.0,
        "mach": 0.1,
        "reynolds": 1.0e6,
        "CL": 0.1,
        "CD": 0.02,
        "CDp": 0.01,
        "CDv": 0.01,
        "CMy": 0.0,
        "gate_verdict": "ACCEPTED",
        "surface_field_archive": "fields/case.cgns",
        "surface_field_sha256": hashlib.sha256(payload).hexdigest(),
    }
    (qualification / "dataset/rows.json").write_text(json.dumps([row]))
    result = {
        "routine_failed": False,
        "converged": False,
        "alpha_deg": 0.0,
        "mission": {"mach": 0.1, "reynolds": 1.0e6},
        "functions": {
            "case_cl": 0.1,
            "case_cd": 0.02,
            "case_cdp": 0.01,
            "case_cdv": 0.01,
            "case_cmy": 0.0,
        },
    }
    gate = {
        "passes": True,
        "verdict": "ACCEPTED",
        "alpha_deg": 0.0,
        "forces": {"cl": 0.1, "cd": 0.02, "cdp": 0.01, "cdv": 0.01, "cmy": 0.0},
    }
    (run_directory / "result.json").write_text(json.dumps(result))
    (run_directory / "gate.json").write_text(json.dumps(gate))
    classified = QualificationEvidence(qualification).runs()[0]
    assert classified.status == "FAILED"
    assert "solver_not_converged" in classified.reasons
