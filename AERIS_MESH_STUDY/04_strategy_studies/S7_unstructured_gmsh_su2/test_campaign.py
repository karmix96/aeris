"""Toolchain-free tests for S7 planning and deterministic batch orchestration."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

S7_DIR = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "s7_campaign_test_package",
    S7_DIR / "__init__.py",
    submodule_search_locations=[str(S7_DIR)],
)
assert _spec and _spec.loader
_package = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _package
_spec.loader.exec_module(_package)
common = importlib.import_module("s7_campaign_test_package.common")
campaign = importlib.import_module("s7_campaign_test_package.campaign")
geometry = importlib.import_module("s7_campaign_test_package.geometry")


def test_mesh_and_cfd_case_identities_are_separate(tmp_path):
    mesh = campaign.plan_case(
        set_name="lhs100_seed42",
        index=0,
        level="laptop_smoke",
        te_variant="te_1p0mm",
        output=tmp_path,
    )
    cruise = campaign.plan_case(
        set_name="lhs100_seed42",
        index=0,
        level="laptop_smoke",
        te_variant="te_1p0mm",
        output=tmp_path,
        flow_id="cruise",
    )
    assert mesh["case_id"].endswith("__mesh")
    assert cruise["case_id"].endswith("__cruise")
    assert mesh["output"] != cruise["output"]
    with pytest.raises(PermissionError):
        campaign.plan_case(
            set_name="round_c_lhs10_seed42",
            index=0,
            level="laptop_smoke",
            te_variant="te_1p0mm",
            output=tmp_path,
        )


def test_flow_is_frozen_to_policy_baseline():
    policy = common.load_policy()
    baseline = dict(policy["flow_conditions"]["baseline"])
    assert campaign._resolved_flow(policy, requested=None, flow_id="mesh", run_cfd=True) == baseline
    altered = dict(baseline, mach=0.25)
    with pytest.raises(ValueError, match="flow.mach is frozen"):
        campaign._resolved_flow(policy, requested=altered, flow_id="cruise", run_cfd=True)
    with pytest.raises(ValueError, match="mesh-only"):
        campaign._resolved_flow(policy, requested=baseline, flow_id="mesh", run_cfd=False)


def test_existing_geometry_requires_current_source_and_policy_provenance(tmp_path):
    plan = campaign.plan_case(
        set_name="lhs100_seed42",
        index=0,
        level="laptop_smoke",
        te_variant="te_1p0mm",
        output=tmp_path,
    )
    metadata = {
        "geometry_set": "lhs100_seed42",
        "development_index": 0,
        "level": "laptop_smoke",
        "te_variant": "te_1p0mm",
        "accepted_pre_gmsh": True,
        "source_digest": common.source_digest(),
        "policy_sha256": common.sha256_file(common.POLICY_PATH),
    }
    surface = geometry.SurfaceMesh(
        points=np.asarray(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))),
        triangles=np.asarray(((0, 1, 2),), dtype=np.int64),
        labels=("wall_upper",),
        triangle_span_fraction=np.asarray((0.5,)),
        metadata=metadata,
    )
    artifacts = geometry.write_surface(surface, tmp_path / "geometry")
    path = Path(artifacts["surface_npz"])
    assert campaign._validate_existing_geometry(path, plan).metadata == metadata
    report_path = path.with_name("source_surface_report.json")
    stale = common.read_json(report_path)
    stale["source_digest"] = "stale"
    common.write_json(report_path, stale)
    with pytest.raises(RuntimeError, match="source digest"):
        campaign._validate_existing_geometry(path, plan)


def test_batch_continues_failures_and_terminal_resume_is_idempotent(tmp_path, monkeypatch):
    calls: list[int] = []

    def fake_run_case(**kwargs):
        index = int(kwargs["index"])
        calls.append(index)
        if index == 2:
            raise RuntimeError("synthetic preserved failure")
        return {
            "case_id": campaign.case_id(
                index,
                str(kwargs["level"]),
                str(kwargs["te_variant"]),
                campaign.MESH_FLOW_ID,
            ),
            "accepted": True,
        }

    monkeypatch.setattr(campaign, "run_case", fake_run_case)
    kwargs = {
        "set_name": "lhs100_seed42",
        "indices": [2, 1],
        "level": "laptop_smoke",
        "te_variant": "te_1p0mm",
        "output": tmp_path,
    }
    first = campaign.run_cases(**kwargs)
    assert first["case_count"] == 2
    assert first["technical_pass_count"] == 1
    assert not first["technical_all_passed"]
    assert [row["index"] for row in first["cases"]] == [1, 2]
    assert calls == [1, 2]

    second = campaign.run_cases(**kwargs)
    assert second == first
    assert calls == [1, 2]
