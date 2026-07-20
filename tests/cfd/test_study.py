"""Sensitivity-study spec loading, patch merging, and (dry-run) execution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from aeris.cfd.study.loader import build_variant_case_spec, deep_merge, load_study_spec
from aeris.cfd.study.runner import VariantResult, _deltas, run_study
from aeris.cfd.study.spec import STUDY_REPORT_SCHEMA_VERSION


def _write_base_case(tmp_path: Path) -> Path:
    path = tmp_path / "base_case.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "aeris.cfd.case.v1",
                "case": {
                    "name": "base",
                    "geometry": {"airfoil": "naca0012"},
                    "surface_mesh": {
                        "topology": "airfoil_ogrid_v1",
                        "overrides": {"n_per_surface": 33},
                    },
                    "volume_mesh": {
                        "level": "smoke",
                        "march_dist_factor": 100.0,
                        "overrides": {"n_grid": 17, "s0": 5.0e-6},
                    },
                },
            }
        )
    )
    return path


def _write_study(tmp_path: Path, base_case: Path, *, variants: list[dict], **extra) -> Path:
    path = tmp_path / "study.yaml"
    payload = {
        "schema": "aeris.cfd.study.v1",
        "study": {
            "name": "s1",
            "base_case": base_case.name,
            "variants": variants,
            **extra,
        },
    }
    path.write_text(yaml.safe_dump(payload))
    return path


def test_deep_merge_mappings_merge_lists_and_scalars_replace():
    base = {"a": {"x": 1, "y": 2}, "b": [1, 2], "c": 3}
    patch = {"a": {"y": 20, "z": 30}, "b": [9], "c": 4}
    merged = deep_merge(base, patch)
    assert merged == {"a": {"x": 1, "y": 20, "z": 30}, "b": [9], "c": 4}
    # base untouched
    assert base["a"]["y"] == 2


def test_load_study_requires_schema_and_nonempty_variants(tmp_path: Path):
    base_case = _write_base_case(tmp_path)
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump({"study": {"name": "s", "base_case": "base_case.yaml"}}))
    with pytest.raises(ValueError, match="schema"):
        load_study_spec(path)

    path2 = _write_study(tmp_path, base_case, variants=[])
    with pytest.raises(ValueError, match="variants"):
        load_study_spec(path2)


def test_load_study_rejects_duplicate_variant_names(tmp_path: Path):
    base_case = _write_base_case(tmp_path)
    path = _write_study(
        tmp_path,
        base_case,
        variants=[{"name": "v1", "patch": {}}, {"name": "v1", "patch": {}}],
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_study_spec(path)


def test_load_study_rejects_unknown_baseline(tmp_path: Path):
    base_case = _write_base_case(tmp_path)
    path = _write_study(
        tmp_path,
        base_case,
        variants=[{"name": "v1", "patch": {}}],
        baseline="nope",
    )
    with pytest.raises(ValueError, match="baseline"):
        load_study_spec(path)


def test_load_study_rejects_missing_base_case(tmp_path: Path):
    path = tmp_path / "study.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "aeris.cfd.study.v1",
                "study": {
                    "name": "s",
                    "base_case": "does_not_exist.yaml",
                    "variants": [{"name": "v1", "patch": {}}],
                },
            }
        )
    )
    with pytest.raises(ValueError, match="base_case not found"):
        load_study_spec(path)


def test_build_variant_case_spec_merges_patch_and_renames_case(tmp_path: Path):
    base_case = _write_base_case(tmp_path)
    study = load_study_spec(
        _write_study(
            tmp_path,
            base_case,
            variants=[
                {
                    "name": "coarser",
                    "patch": {"volume_mesh": {"overrides": {"n_grid": 9}}},
                }
            ],
        )
    )
    variant = study.variants[0]
    spec = build_variant_case_spec(study, variant)
    assert spec.name == "s1_coarser"
    # patch key overridden, sibling key from base case preserved
    assert spec.volume_mesh.overrides["n_grid"] == 9
    assert spec.volume_mesh.overrides["s0"] == 5.0e-6
    assert spec.surface_mesh.overrides["n_per_surface"] == 33


def test_run_study_dry_run_writes_report_with_all_variants(tmp_path: Path):
    # 'post' always needs a real solve_report (dry_run only applies to
    # mesh/solver preparation, matching aeris.cfd.case.runner semantics), and
    # this base case has no 'solve' section — restrict to the stages a dry
    # run can meaningfully cover.
    base_case = _write_base_case(tmp_path)
    study = load_study_spec(
        _write_study(
            tmp_path,
            base_case,
            variants=[
                {"name": "a", "patch": {}},
                {"name": "b", "patch": {"volume_mesh": {"overrides": {"n_grid": 9}}}},
            ],
            baseline="a",
            stages=["surface", "volume"],
        )
    )
    report = run_study(study, workdir=tmp_path / "run", dry_run=True)

    assert report["schema"] == STUDY_REPORT_SCHEMA_VERSION
    assert {row["name"] for row in report["variants"]} == {"a", "b"}
    assert all(row["status"] == "dry_run" for row in report["variants"])
    # dry runs never produce force deltas (nothing was solved)
    assert report["deltas_vs_baseline"] == {}

    on_disk = json.loads((tmp_path / "run" / "study_report.json").read_text())
    assert on_disk == report

    # each variant is an ordinary, independently reproducible case run
    assert (tmp_path / "run" / "a" / "surface" / "surface.fmt").is_file()
    assert (tmp_path / "run" / "b" / "surface" / "surface.fmt").is_file()


def test_deltas_vs_baseline_relative_percent():
    rows = [
        VariantResult(
            variant="base", status="ok", workdir=Path("."), forces={"cl": 1.0, "cd": 0.01}
        ),
        VariantResult(
            variant="hi", status="ok", workdir=Path("."), forces={"cl": 1.1, "cd": 0.012}
        ),
        VariantResult(variant="failed_one", status="failed", workdir=Path("."), forces={}),
    ]
    deltas = _deltas(rows, "base", ("cl", "cd"))
    assert set(deltas) == {"hi"}  # failed variants excluded, baseline excluded from its own deltas
    assert deltas["hi"]["cl"]["absolute"] == pytest.approx(0.1)
    assert deltas["hi"]["cl"]["relative_percent"] == pytest.approx(10.0)
    assert deltas["hi"]["cd"]["relative_percent"] == pytest.approx(20.0)


def test_deltas_vs_baseline_missing_baseline_returns_empty():
    rows = [VariantResult(variant="a", status="ok", workdir=Path("."), forces={"cl": 1.0})]
    assert _deltas(rows, None, ("cl",)) == {}
    assert _deltas(rows, "nonexistent", ("cl",)) == {}
