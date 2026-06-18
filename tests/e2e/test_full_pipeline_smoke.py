from pathlib import Path
import shutil
import uuid
import json
import pandas as pd

from aeris.dataset.aero_dataset_run import run_aero_dataset_generation


def test_full_pipeline_smoke(tmp_path: Path):
    dataset_name = f"test_full_pipeline_smoke_{uuid.uuid4().hex[:8]}"
    root = Path("data/datasets") / dataset_name
    geometry_root = Path("data/datasets") / f"{dataset_name}__geometry"

    try:
        rc = run_aero_dataset_generation(
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
            keep_geometry_dataset=True,
            run_geometry_qc=True,
            geometry_qc_profile="basic",
            fail_on_geometry_qc_error=True,
            run_aero_qc=True,
            aero_qc_profile="basic",
            fail_on_aero_qc_error=True,
        )

        assert rc == 0

        manifest = json.loads((root / "aero_dataset_manifest.json").read_text())
        df = pd.read_csv(root / "aero_dataset.csv")

        assert manifest["geometry_qc"]["passed"] is True
        assert manifest["aero_qc"]["passed"] is True

        assert len(df) == manifest["successful_aero_rows"]

        expected = (
            df["geometry_id"].nunique()
            * df["alpha_deg"].nunique()
            * df["velocity_mps"].nunique()
            * df["altitude_m"].nunique()
            * df["control_input_deg"].nunique()
        )

        assert len(df) == expected

    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(geometry_root, ignore_errors=True)