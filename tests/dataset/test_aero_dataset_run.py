from __future__ import annotations

import json
import shutil
from pathlib import Path

from aeris.dataset.aero_dataset_run import run_aero_dataset_generation


def test_aero_dataset_writes_final_summary() -> None:
    dataset_name = "test_aero_summary"
    dataset_root = Path("data/datasets") / dataset_name

    if dataset_root.exists():
        shutil.rmtree(dataset_root)

    exit_code = run_aero_dataset_generation(
        config_path=Path("configs/geometry/baseline_bwb_25.yaml"),
        n_samples=1,
        sampler="lhs_v1",
        sampler_seed=123,
        dataset_name=dataset_name,
        save_plot=False,
        build_aerosandbox=True,
        alpha_values=[0.0],
        beta_values=[0.0],
        velocity_values=[28.0],
        altitude_values=[1500.0],
        p_values=[0.0],
        q_values=[0.0],
        r_values=[0.0],
        control_input_values=[0.0],
        solver="aerosandbox_avl",
        avl_command="avl",
        timeout_sec=60,
        spanwise_resolution=2,
        chordwise_resolution=4,
        spanwise_spacing="equal",
        chordwise_spacing="cosine",
        save_surface_forces=False,
        save_element_forces=False,
        max_cases=1,
        keep_geometry_dataset=False,
        run_geometry_qc=False,
        geometry_qc_profile="basic",
        fail_on_geometry_qc_error=False,
        run_aero_qc=False,
        aero_qc_profile="basic",
        fail_on_aero_qc_error=False,
    )

    summary_path = dataset_root / "final_run_summary.json"
    assert summary_path.exists()

    data = json.loads(summary_path.read_text(encoding="utf-8"))

    assert data["dataset_name"] == dataset_name
    assert "successful_aero_rows" in data
    assert "failed_aero_rows" in data
    assert "exit_code" in data
    assert data["exit_code"] == exit_code

    shutil.rmtree(dataset_root)

from pathlib import Path

from aeris.dataset.aero_dataset_run import _prune_aero_run_artifacts


def test_prune_aero_run_artifacts_failures_only(tmp_path: Path) -> None:
    run_a = tmp_path / "geom_00001_run"
    run_b = tmp_path / "geom_00002_run"
    run_a.mkdir()
    run_b.mkdir()

    result = _prune_aero_run_artifacts(
        copied_sweep_roots_by_geometry={
            "geom_00001": run_a,
            "geom_00002": run_b,
        },
        geometry_ids_with_failures={"geom_00002"},
        retain_aero_runs="failures_only",
    )

    assert not run_a.exists()
    assert run_b.exists()
    assert result["retain_aero_runs"] == "failures_only"
    assert result["kept_run_count"] == 1
    assert result["deleted_run_count"] == 1

def test_prune_aero_run_artifacts_none(tmp_path: Path) -> None:
    run_a = tmp_path / "geom_00001_run"
    run_b = tmp_path / "geom_00002_run"
    run_a.mkdir()
    run_b.mkdir()

    result = _prune_aero_run_artifacts(
        copied_sweep_roots_by_geometry={
            "geom_00001": run_a,
            "geom_00002": run_b,
        },
        geometry_ids_with_failures={"geom_00002"},
        retain_aero_runs="none",
    )

    assert not run_a.exists()
    assert not run_b.exists()
    assert result["retain_aero_runs"] == "none"
    assert result["kept_run_count"] == 0
    assert result["deleted_run_count"] == 2

def test_validate_retain_aero_runs_accepts_expected_values() -> None:
    from aeris.dataset.aero_dataset_run import _validate_retain_aero_runs

    assert _validate_retain_aero_runs("all") == "all"
    assert _validate_retain_aero_runs("failures_only") == "failures_only"
    assert _validate_retain_aero_runs("none") == "none"

import pytest

def test_validate_retain_aero_runs_rejects_invalid_value() -> None:
    from aeris.dataset.aero_dataset_run import _validate_retain_aero_runs

    with pytest.raises(ValueError):
        _validate_retain_aero_runs("banana_mode")