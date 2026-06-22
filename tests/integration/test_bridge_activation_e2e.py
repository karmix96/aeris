"""
BRIDGE.4 -- end-to-end polar-bridge activation test.

Unlike test_strip_profile_drag_physics.py / test_avl_polar_injection.py /
test_polar_store.py (which construct SectionAirfoilMap / AirfoilPolarStore
directly and call solver internals), this test goes through the real
production call chain:

    aeris dataset aero-generate (CLI)
      -> run_aero_dataset_generation()
        -> execute_aero_sweep()
          -> AeroSolverSettings(solver_options={...})
            -> AVLStrips / aerosandbox_avl.run_case()

and asserts the bridge actually fired: cd_profile / cd_total are non-null
in the resulting aero_dataset.csv row, not just present-but-empty.

STATUS BEFORE BRIDGE.1 IS WIRED: this test is EXPECTED TO FAIL. No
production code path supplies section_map / polar_store yet, so the bridge
never activates and cd_profile / cd_total stay None even when a curated
polar CSV exists. The failure is the point -- it is a red/green guard for
the wiring gap, not a re-test of already-proven strip-integration math.

run_aero_dataset_generation() does not yet accept airfoil_curated_csv /
airfoil_library_id kwargs -- calling with them will raise TypeError until
BRIDGE.1 is wired (patch_bridge_step2_wire_bridge1.sh). That TypeError IS
the expected red-state failure for this test.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from aeris.dataset.aero_dataset_run import run_aero_dataset_generation


def _write_curated_polar_csv(path: Path, airfoil_id: str) -> None:
    """Minimal curated XFOIL dataset AirfoilPolarStore can load.

    cd is a simple parabola in cl so fit_cdcl() has well-behaved data to fit.
    """
    rows = []
    re = 500_000.0
    mach = 0.08
    for cl in [-0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        cd = 0.006 + 0.018 * (cl - 0.25) ** 2
        rows.append(
            {
                "airfoil_id": airfoil_id,
                "cl": cl,
                "cd": cd,
                "reynolds": re,
                "mach": mach,
                "converged": True,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


@pytest.mark.integration
def test_polar_bridge_activates_through_dataset_aero_generate(tmp_path):
    """BRIDGE.4: real campaign call chain must populate cd_total when the
    bridge config (airfoil_curated_csv + segment airfoil) is supplied."""
    curated_csv = tmp_path / "curated_airfoil_polars.csv"
    airfoil_id = "naca4412_test_bridge"
    _write_curated_polar_csv(curated_csv, airfoil_id)

    config_yaml = tmp_path / "bridge_test_config.yaml"
    config_yaml.write_text(
        "name: bridge_activation_test\n"
        "\n"
        "geometry:\n"
        "  generator:\n"
        "    id: bwb_segmented_v1\n"
        "    seed: 100\n"
        "\n"
        "  controls:\n"
        "    n_points: 10\n"
        "    n_spline_inboard: 10\n"
        "    n_spline_outboard: 5\n"
        "    spline_split_ratio: 0.55\n"
        "    segment_length_variation: 0.0\n"
        "    sweep_variation: 0.0\n"
        "    desired_curvature_strength: 1.0\n"
        "\n"
        "  planform_bounds:\n"
        "    c1_m:\n"
        "      min: 1.6000\n"
        "      max: 1.6001\n"
        "    c2_ratio:\n"
        "      min: 0.5500\n"
        "      max: 0.5501\n"
        "    c3_ratio:\n"
        "      min: 0.3800\n"
        "      max: 0.3801\n"
        "    c4_ratio:\n"
        "      min: 0.1200\n"
        "      max: 0.1201\n"
        "    b_total_m:\n"
        "      min: 1.6000\n"
        "      max: 1.6001\n"
        "    b3_ratio:\n"
        "      min: 0.5000\n"
        "      max: 0.5001\n"
        "    split_ratio:\n"
        "      min: 0.4500\n"
        "      max: 0.4501\n"
        "    sw1_deg:\n"
        "      min: 40.0000\n"
        "      max: 40.0001\n"
        "    sw2_deg:\n"
        "      min: 25.0000\n"
        "      max: 25.0001\n"
        "    sw3_deg:\n"
        "      min: 10.0000\n"
        "      max: 10.0001\n"
        "\n"
        "  section_bounds:\n"
        "    airfoil_name: naca4412\n"
        "    dihedral_root_deg: 0.0\n"
        "\n"
        "    twist_b0_deg:\n"
        "      min: 0.0000\n"
        "      max: 0.0001\n"
        "    twist_b1_deg:\n"
        "      min: 0.0000\n"
        "      max: 0.0001\n"
        "    twist_b2_deg:\n"
        "      min: 0.0000\n"
        "      max: 0.0001\n"
        "    twist_b3_deg:\n"
        "      min: 0.0000\n"
        "      max: 0.0001\n"
        "\n"
        "    dihedral_b1_deg:\n"
        "      min: 0.0000\n"
        "      max: 0.0001\n"
        "    dihedral_b2_deg:\n"
        "      min: 0.0000\n"
        "      max: 0.0001\n"
        "    dihedral_b3_deg:\n"
        "      min: 0.0000\n"
        "      max: 0.0001\n"
        "\n"
        "  control_surfaces:\n"
        "    enabled: true\n"
        "    surfaces:\n"
        "      - name: elevon\n"
        "        family: trailing_edge\n"
        "        hinge_point: 0.75\n"
        "        symmetric: true\n"
        "        spanwise:\n"
        "          start_frac: 0.60\n"
        "          end_frac: 0.95\n"
        "        deflection_sign: standard\n"
        "        required: false\n"
        "\n"
        "  outputs:\n"
        "    save_plot: false\n"
        "    build_aerosandbox: true\n"
        "\n"
        "dataset:\n"
        "  sampling:\n"
        "    method: lhs_v1\n"
        "    seed: 123\n",
        encoding="utf-8",
    )

    dataset_name = "bridge_activation_test_ds"

    exit_code = run_aero_dataset_generation(
        config_path=config_yaml,
        n_samples=1,
        sampler=None,
        sampler_seed=0,
        dataset_name=dataset_name,
        save_plot=False,
        build_aerosandbox=True,
        alpha_values=[2.0],
        beta_values=[0.0],
        velocity_values=[28.0],
        altitude_values=[0.0],
        p_values=[0.0],
        q_values=[0.0],
        r_values=[0.0],
        control_input_values=[0.0],
        diff_input_values=None,
        solver="aerosandbox_avl",
        avl_command="",
        timeout_sec=180,
        spanwise_resolution=4,
        chordwise_resolution=8,
        spanwise_spacing="equal",
        chordwise_spacing="cosine",
        save_surface_forces=False,
        save_element_forces=False,
        max_cases=None,
        keep_geometry_dataset=False,
        retain_aero_runs="none",
        # --- polar bridge config under test (kwargs do not exist pre-BRIDGE.1) ---
        airfoil_curated_csv=curated_csv,
        airfoil_library_id=airfoil_id,
    )

    assert exit_code == 0, "dataset aero-generate did not complete successfully"

    csv_path = Path("data/datasets") / dataset_name / "aero_dataset.csv"
    assert csv_path.exists(), "aero_dataset.csv was not produced"

    df = pd.read_csv(csv_path)
    assert len(df) >= 1, "no successful aero rows produced"

    assert "cd_total" in df.columns, "cd_total column missing from aero_dataset.csv"
    assert "cd_profile" in df.columns, "cd_profile column missing from aero_dataset.csv"

    row = df.iloc[0]
    assert row["cd_profile"] is not None and not (
        isinstance(row["cd_profile"], float) and math.isnan(row["cd_profile"])
    ), (
        "BRIDGE.1 not wired: cd_profile is null even though airfoil_curated_csv "
        "and airfoil_library_id were supplied to run_aero_dataset_generation(). "
        "section_map/polar_store are not reaching solver_options in execute_aero_sweep()."
    )
    assert row["cd_total"] is not None and not (
        isinstance(row["cd_total"], float) and math.isnan(row["cd_total"])
    ), "cd_total is null -- polar bridge did not activate end-to-end."
