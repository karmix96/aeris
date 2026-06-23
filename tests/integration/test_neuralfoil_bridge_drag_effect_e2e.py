"""Real end-to-end proof that the NeuralFoil polar bridge changes AVL drag.

Deliberately different from test_neuralfoil_bridge_smoke_static.py, which only
string-matches source files and would pass even if the bridge silently fell
back to inviscid AVL (as the model_size="xsmall" bug did). String presence is
not behaviour.

This runs an ACTUAL generated BWB geometry through the real production call
chain TWICE -- once with viscous_polar_source="none" (inviscid), once with
"neuralfoil" -- and asserts the viscous run's cd is strictly HIGHER. If the
bridge ever silently reverts to inviscid, this test fails, which is the point.

The call signature and config schema are copied verbatim from the green
BRIDGE.4 test (test_bridge_activation_e2e.py); only viscous_polar_source
differs between the two runs.

Skips cleanly (never fails) when neuralfoil / aerosandbox / the AVL binary are
unavailable.
"""
from __future__ import annotations

import math
import shutil
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("neuralfoil")
pytest.importorskip("aerosandbox")

from aeris.dataset.aero_dataset_run import run_aero_dataset_generation


def _avl_available() -> bool:
    return shutil.which("avl") is not None


# Exact config schema from the passing BRIDGE.4 test. NeuralFoil needs the
# section airfoil shape, which comes from section_bounds.airfoil_name +
# build_aerosandbox: true, so the same config works for the neuralfoil source.
_CONFIG_YAML = (
    "name: nf_drag_effect_test\n"
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
    "    seed: 123\n"
)


def _run(dataset_name: str, tmp_path: Path, viscous_polar_source: str) -> pd.DataFrame:
    """Run the real campaign chain for one geometry; return its aero_dataset.csv."""
    config_yaml = tmp_path / f"{dataset_name}.yaml"
    config_yaml.write_text(_CONFIG_YAML, encoding="utf-8")

    run_aero_dataset_generation(
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
        viscous_polar_source=viscous_polar_source,
        viscous_polar_re_grid=[500_000.0, 1_000_000.0, 3_000_000.0],
    )

    csv_path = Path("data/datasets") / dataset_name / "aero_dataset.csv"
    assert csv_path.exists(), f"aero_dataset.csv not produced for {dataset_name}"
    return pd.read_csv(csv_path)


@pytest.mark.integration
@pytest.mark.avl
@pytest.mark.skipif(not _avl_available(), reason="AVL binary not on PATH")
def test_neuralfoil_bridge_actually_increases_cd(tmp_path, monkeypatch):
    """The NeuralFoil run must produce strictly higher cd than the inviscid run."""
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(repo_root)

    inviscid = _run("zz_nf_effect_inviscid", tmp_path, "none")
    bridged = _run("zz_nf_effect_neuralfoil", tmp_path, "neuralfoil")

    assert len(inviscid) >= 1, "inviscid run produced no rows"
    assert len(bridged) >= 1, "neuralfoil run produced no rows"

    cd_inviscid = float(inviscid.iloc[0]["cd"])
    cd_bridged = float(bridged.iloc[0]["cd"])
    cl_inviscid = float(inviscid.iloc[0]["cl"])
    cl_bridged = float(bridged.iloc[0]["cl"])

    # The bridge corrects drag, not lift -- CL should be (near) identical.
    assert abs(cl_bridged - cl_inviscid) < 0.05, (
        f"CL changed too much ({cl_inviscid:.4f} -> {cl_bridged:.4f}); the "
        "bridge should affect drag, not lift."
    )

    # CORE ASSERTION: viscous profile drag must make total cd strictly larger.
    assert cd_bridged > cd_inviscid, (
        "NeuralFoil bridge did NOT increase cd -- likely silent fallback to "
        f"inviscid AVL. cd_inviscid={cd_inviscid:.6f} cd_bridged={cd_bridged:.6f}. "
        "Check model_size validity and the try/except in execute_aero_sweep."
    )

    # Physically plausible profile-drag increase for a clean airfoil at low alpha.
    delta = cd_bridged - cd_inviscid
    assert 0.0005 < delta < 0.05, (
        f"cd increase {delta:.6f} outside plausible profile-drag band; "
        "investigate strip integration / Reynolds / extrapolation."
    )

    # Bridge bookkeeping columns, when present, must be consistent.
    row = bridged.iloc[0]
    if "cd_total" in bridged.columns and not (
        isinstance(row["cd_total"], float) and math.isnan(row["cd_total"])
    ):
        assert abs(float(row["cd_total"]) - cd_bridged) < 1e-9, (
            "cd should equal cd_total when the bridge is active"
        )
    if "cd_profile" in bridged.columns and not (
        isinstance(row["cd_profile"], float) and math.isnan(row["cd_profile"])
    ):
        assert float(row["cd_profile"]) > 0.0, "cd_profile should be positive when bridged"


@pytest.mark.integration
def test_neuralfoil_source_constructs_without_avl():
    """Isolate 'NeuralFoil works' from 'the AVL chain works': the polar source
    must build and produce a valid CDCL fit even without the AVL binary. Catches
    API regressions (model_size / mach signature) independently of AVL.
    """
    import numpy as np
    from aeris.airfoil.neuralfoil_polar_source import NeuralFoilPolarSource

    n = 80
    x = (1 - np.cos(np.linspace(0, np.pi, n))) / 2
    t = 0.12
    yt = 5 * t * (
        0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2
        + 0.2843 * x**3 - 0.1015 * x**4
    )
    coords = np.vstack([
        np.column_stack([x[::-1], yt[::-1]]),
        np.column_stack([x[1:], -yt[1:]]),
    ])

    source = NeuralFoilPolarSource(model_size="large")
    aid = source.register_shape(coords)
    params = source.fit_cdcl(aid, re=1_000_000.0, mach=0.0)

    assert params is not None, (
        "fit_cdcl returned None -- NeuralFoil API call failed. Check the "
        "get_aero_from_kulfan_parameters signature for this neuralfoil version."
    )
    assert params.is_valid(), "CDCL params invalid"
    assert params.cd2 > 0, "minimum-drag coefficient must be positive"
