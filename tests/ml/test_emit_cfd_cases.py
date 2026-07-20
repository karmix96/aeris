"""Active learning → runnable CFD case emission."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from aeris.ml.active_learning.emit_cfd import emit_cfd_cases

TEMPLATE = {
    "schema": "aeris.cfd.case.v1",
    "case": {
        "name": "bwb_al",
        "geometry": {"surface_dir": "/data/ref_surface"},
        "volume_mesh": {"preset": "smoke"},
        "solve": {
            "solver": "adflow",
            "flow": {"alpha": 2.0, "mach": 0.2, "reynolds": 1.0e6},
            "area_ref": 1.094,
            "chord_ref": 0.8774,
        },
    },
}


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    template = tmp_path / "template.yaml"
    template.write_text(yaml.safe_dump(TEMPLATE))
    ranked = tmp_path / "ranked_candidate_samples.csv"
    pd.DataFrame(
        {
            "candidate_id": ["cand_00003", "cand_00001", "cand_00007"],
            "alpha_deg": [4.5, 1.0, 8.0],
            "mach": [0.25, 0.18, 0.3],
            "active_learning_rank": [2, 1, 3],
            "recommended": [True, True, False],
        }
    ).to_csv(ranked, index=False)
    return ranked, template


def test_emit_recommended_cases_in_rank_order(tmp_path: Path):
    ranked, template = _write_inputs(tmp_path)
    emitted = emit_cfd_cases(ranked, template, tmp_path / "cases")
    assert [e.candidate_id for e in emitted] == ["cand_00001", "cand_00003"]

    case = yaml.safe_load(emitted[0].case_yaml.read_text())
    assert case["case"]["name"] == "bwb_al_cand_00001"
    assert case["case"]["solve"]["flow"]["alpha"] == 1.0
    assert case["case"]["solve"]["flow"]["mach"] == 0.18
    # untouched keys survive from the template
    assert case["case"]["solve"]["flow"]["reynolds"] == 1.0e6
    assert case["case"]["volume_mesh"]["preset"] == "smoke"
    # provenance of the AI choice is recorded in the case itself
    assert case["case"]["provenance"]["candidate_id"] == "cand_00001"


def test_emitted_case_loads_as_valid_case_spec(tmp_path: Path):
    from aeris.cfd.case.loader import load_case_spec

    ranked, template = _write_inputs(tmp_path)
    emitted = emit_cfd_cases(ranked, template, tmp_path / "cases", top_n=1)
    spec = load_case_spec(emitted[0].case_yaml)
    assert spec.solve is not None
    assert spec.solve.flow.alpha == 1.0


def test_top_n_limits_emission(tmp_path: Path):
    ranked, template = _write_inputs(tmp_path)
    emitted = emit_cfd_cases(ranked, template, tmp_path / "cases", top_n=1)
    assert len(emitted) == 1


def test_missing_flow_columns_rejected(tmp_path: Path):
    template = tmp_path / "template.yaml"
    template.write_text(yaml.safe_dump(TEMPLATE))
    ranked = tmp_path / "ranked.csv"
    pd.DataFrame({"candidate_id": ["c1"], "wing_span": [3.0]}).to_csv(ranked, index=False)
    with pytest.raises(ValueError, match="flow-condition"):
        emit_cfd_cases(ranked, template, tmp_path / "cases")


def test_template_without_solve_rejected(tmp_path: Path):
    ranked, template = _write_inputs(tmp_path)
    bad = {"schema": "aeris.cfd.case.v1", "case": {"name": "x", "geometry": {}}}
    template.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError, match="solve"):
        emit_cfd_cases(ranked, template, tmp_path / "cases")
