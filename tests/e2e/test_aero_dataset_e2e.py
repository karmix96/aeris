from __future__ import annotations

import json
import shutil
from pathlib import Path

from aeris.dataset.aero_dataset_run import run_aero_dataset_generation


def test_aero_dataset_e2e_small_real_run() -> None:
    dataset_name = "test_aero_e2e_small"
    dataset_root = Path("data/datasets") / dataset_name
    geometry_dataset_root = Path("data/datasets") / f"{dataset_name}__geometry"

    if dataset_root.exists():
        shutil.rmtree(dataset_root)
    if geometry_dataset_root.exists():
        shutil.rmtree(geometry_dataset_root)

    exit_code = run_aero_dataset_generation(
        config_path=Path("configs/geometry/baseline_bwb_25.yaml"),
        n_samples=2,
        sampler="lhs_v1",
        sampler_seed=123,
        dataset_name=dataset_name,
        save_plot=False,
        build_aerosandbox=True,
        alpha_values=[0.0, 2.0],
        beta_values=[0.0],
        velocity_values=[28.0],
        altitude_values=[1500.0],
        p_values=[0.0],
        q_values=[0.0],
        r_values=[0.0],
        control_input_values=[-5.0, 0.0, 5.0],
        solver="aerosandbox_avl",
        avl_command="avl",
        timeout_sec=120,
        spanwise_resolution=2,
        chordwise_resolution=4,
        spanwise_spacing="equal",
        chordwise_spacing="cosine",
        save_surface_forces=False,
        save_element_forces=False,
        max_cases=None,
        keep_geometry_dataset=False,
        retain_aero_runs="failures_only",
        qc_preset="production",
        run_geometry_qc=True,
        geometry_qc_profile="basic",
        fail_on_geometry_qc_error=True,
        run_aero_qc=True,
        aero_qc_profile="basic",
        fail_on_aero_qc_error=True,
    )

    assert exit_code == 0

    manifest_path = dataset_root / "aero_dataset_manifest.json"
    summary_path = dataset_root / "final_run_summary.json"
    aero_csv_path = dataset_root / "aero_dataset.csv"
    failure_csv_path = dataset_root / "aero_failures.csv"
    qc_dir = dataset_root / "qc"

    assert dataset_root.exists()
    assert manifest_path.exists()
    assert summary_path.exists()
    assert aero_csv_path.exists()
    assert failure_csv_path.exists()
    assert qc_dir.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert manifest["dataset_name"] == dataset_name
    assert manifest["status"] in {"success", "partial_success"}

    assert "geometry_qc" in manifest
    assert manifest["geometry_qc"]["run_qc"] is True
    assert manifest["geometry_qc"]["passed"] is True

    assert "aero_qc" in manifest
    assert manifest["aero_qc"]["run_qc"] is True
    assert manifest["aero_qc"]["passed"] is True

    assert summary["dataset_name"] == dataset_name
    assert summary["qc_preset"] == "production"
    assert summary["exit_code"] == 0
    assert summary["successful_aero_rows"] > 0

    retention = summary["retention"]
    assert retention["retain_aero_runs"] == "failures_only"
    assert retention["keep_geometry_dataset"] is False

    assert not geometry_dataset_root.exists()

    shutil.rmtree(dataset_root)