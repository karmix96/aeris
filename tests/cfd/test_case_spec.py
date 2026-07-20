"""Case YAML loading, validation errors, and dry-run execution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from aeris.cfd.case.loader import load_case_spec
from aeris.cfd.case.runner import CASE_MANIFEST_SCHEMA_VERSION, CaseError, run_case

CHAR_LEN = 2.27


def _write_case(tmp_path: Path, body: dict) -> Path:
    path = tmp_path / "case.yaml"
    path.write_text(yaml.safe_dump({"schema": "aeris.cfd.case.v1", "case": body}))
    return path


def _ref_surface(tmp_path: Path) -> Path:
    ref = tmp_path / "ref_surface"
    ref.mkdir()
    (ref / "surface.fmt").write_text("dummy plot3d\n")
    (ref / "surface_report.json").write_text(json.dumps({"characteristic_length": CHAR_LEN}))
    return ref


def test_load_minimal_standalone_case(tmp_path: Path):
    ref = _ref_surface(tmp_path)
    path = _write_case(
        tmp_path,
        {
            "name": "t1",
            "geometry": {"surface_dir": str(ref)},
            "volume_mesh": {"preset": "smoke"},
        },
    )
    spec = load_case_spec(path)
    assert spec.name == "t1"
    assert spec.geometry.surface_dir == ref
    assert spec.volume_mesh is not None and spec.volume_mesh.preset == "smoke"
    assert spec.solve is None


def test_geometry_requires_exactly_one_source(tmp_path: Path):
    path = _write_case(tmp_path, {"name": "t", "geometry": {}})
    with pytest.raises(ValueError, match="exactly one"):
        load_case_spec(path)
    path = _write_case(
        tmp_path,
        {"name": "t", "geometry": {"surface_dir": "a", "aeris_config": "b"}},
    )
    with pytest.raises(ValueError, match="exactly one"):
        load_case_spec(path)


def test_schema_version_required(tmp_path: Path):
    path = tmp_path / "case.yaml"
    path.write_text(yaml.safe_dump({"case": {"name": "t"}}))
    with pytest.raises(ValueError, match="schema"):
        load_case_spec(path)


def test_flow_fields_validated(tmp_path: Path):
    ref = _ref_surface(tmp_path)
    path = _write_case(
        tmp_path,
        {
            "name": "t",
            "geometry": {"surface_dir": str(ref)},
            "solve": {"flow": {"alpha": 2.0, "mach": "fast", "reynolds": 1e6}},
        },
    )
    with pytest.raises(ValueError, match="solve.flow.mach"):
        load_case_spec(path)


def test_dry_run_resolves_options_with_preset_config_raw_provenance(tmp_path: Path):
    ref = _ref_surface(tmp_path)
    path = _write_case(
        tmp_path,
        {
            "name": "t1",
            "geometry": {"surface_dir": str(ref)},
            "volume_mesh": {
                "preset": "smoke",
                "overrides": {"theta": 4.0},
                "pyhyp_options": {"splay": 0.25},
            },
        },
    )
    spec = load_case_spec(path)
    workdir = tmp_path / "run"
    results = run_case(spec, workdir=workdir, dry_run=True)

    assert results["surface"].status == "ok"
    assert results["volume"].status == "dry_run"

    options = json.loads((workdir / "surface" / "pyhyp_options.json").read_text())
    assert options["cMax"] == 0.5  # preset march policy
    assert options["N"] == 129  # level:smoke
    assert options["theta"] == 4.0  # config override
    assert options["splay"] == 0.25  # raw pass-through

    manifest = json.loads((workdir / "surface" / "pyhyp_effective_options.json").read_text())
    assert manifest["options"]["cMax"]["source"] == "preset:smoke"
    assert manifest["options"]["theta"]["source"] == "config"
    assert manifest["options"]["splay"]["source"] == "raw"

    case_manifest = json.loads((workdir / "case_manifest.json").read_text())
    assert case_manifest["schema"] == CASE_MANIFEST_SCHEMA_VERSION
    assert case_manifest["stages"]["volume"]["status"] == "dry_run"
    surface_sha = case_manifest["stages"]["surface"]["artifact_sha256"]["surface.fmt"]
    assert isinstance(surface_sha, str) and len(surface_sha) == 64


def test_solve_stage_requires_volume_mesh(tmp_path: Path):
    ref = _ref_surface(tmp_path)
    path = _write_case(
        tmp_path,
        {
            "name": "t",
            "geometry": {"surface_dir": str(ref)},
            "volume_mesh": {"preset": "smoke"},
            "solve": {"flow": {"alpha": 2.0, "mach": 0.2, "reynolds": 1.0e6}},
        },
    )
    spec = load_case_spec(path)
    with pytest.raises(CaseError, match="volume"):
        run_case(spec, workdir=tmp_path / "run", stages=("solve",))


def test_post_stage_requires_solve_report(tmp_path: Path):
    ref = _ref_surface(tmp_path)
    path = _write_case(
        tmp_path,
        {"name": "t", "geometry": {"surface_dir": str(ref)}},
    )
    spec = load_case_spec(path)
    with pytest.raises(CaseError, match="solve stage first"):
        run_case(spec, workdir=tmp_path / "run", stages=("post",))


def test_missing_surface_inputs_fail_clearly(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    path = _write_case(
        tmp_path,
        {"name": "t", "geometry": {"surface_dir": str(empty)}, "volume_mesh": {}},
    )
    spec = load_case_spec(path)
    with pytest.raises(CaseError, match="missing"):
        run_case(spec, workdir=tmp_path / "run", dry_run=True)
