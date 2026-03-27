from pathlib import Path
import shutil
import uuid
import json

from aeris.dataset.aero_dataset_run import run_aero_dataset_generation


def test_aero_qc_integration_writes_manifest_before_qc(tmp_path: Path):
    dataset_name = f"test_aero_qc_integration_{uuid.uuid4().hex[:8]}"
    dataset_root = Path("data/datasets") / dataset_name
    geometry_root = Path("data/datasets") / f"{dataset_name}__geometry"

    try:
        rc = run_aero_dataset_generation(
            config_path=Path("configs/geometry/baseline_bwb_25.yaml"),
            n_samples=1,
            sampler="lhs_v1",
            sampler_seed=123,
            dataset_name=dataset_name,
            save_plot=False,
            build_aerosandbox=True,
            alpha_values=[0.0],
            beta_values=[],
            velocity_values=[28.0],
            altitude_values=[1500.0],
            p_values=[],
            q_values=[],
            r_values=[],
            control_input_values=[-5.0, 0.0, 5.0],
            solver="aerosandbox_avl",
            avl_command="avl",
            timeout_sec=30,
            spanwise_resolution=8,
            chordwise_resolution=6,
            spanwise_spacing="cosine",
            chordwise_spacing="cosine",
            save_surface_forces=False,
            save_element_forces=False,
            max_cases=None,
            keep_geometry_dataset=True,
            run_geometry_qc=True,
            geometry_qc_profile="basic",
            fail_on_geometry_qc_error=True,
            run_aero_qc=True,
            aero_qc_profile="basic",
            fail_on_aero_qc_error=True,
        )

        assert rc == 0

        manifest_path = dataset_root / "aero_dataset_manifest.json"
        qc_report_path = dataset_root / "qc" / "aero_qc_report.json"

        assert manifest_path.exists(), "Manifest must exist before QC runs"
        assert qc_report_path.exists(), "QC report must exist"

        manifest = json.loads(manifest_path.read_text())
        report = json.loads(qc_report_path.read_text())

        assert manifest["aero_qc"]["passed"] is True
        assert report["passed"] is True

    finally:
        shutil.rmtree(dataset_root, ignore_errors=True)
        shutil.rmtree(geometry_root, ignore_errors=True)