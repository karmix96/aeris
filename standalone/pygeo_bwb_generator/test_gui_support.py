from __future__ import annotations

import copy
from dataclasses import replace

import numpy as np

from standalone.pygeo_bwb_generator.generate import (
    ControlSurfaceSpec,
    create_doe,
    load_config,
    resolve_control_surface,
)
from standalone.pygeo_bwb_generator.gui_support import (
    build_config_payload,
    deflect_surface_pair,
)

CONFIG = "standalone/pygeo_bwb_generator/config.yaml"


def test_config_carries_aeris_style_control_surface_metadata() -> None:
    control = resolve_control_surface(load_config(CONFIG))
    assert control.enabled
    assert control.name == "elevon"
    assert np.isclose(control.hinge_point, 0.75)
    assert np.isclose(control.start_frac, 0.60)
    assert np.isclose(control.end_frac, 0.95)
    assert np.isclose(control.right_deflection_deg, 0.0)
    assert np.isclose(control.left_deflection_deg, 0.0)


def test_positive_kinematic_preview_moves_trailing_edge_down() -> None:
    x = np.asarray([0.0, 0.5, 1.0])
    y = np.asarray([0.0, 0.5, 1.0])
    upper = np.zeros((3, 3, 3))
    lower = np.zeros((3, 3, 3))
    upper[:, :, 0] = x[:, None]
    lower[:, :, 0] = x[:, None]
    upper[:, :, 1] = y[None, :]
    lower[:, :, 1] = y[None, :]
    upper[:, :, 2] = 0.05
    lower[:, :, 2] = -0.05
    control = ControlSurfaceSpec(
        enabled=True,
        name="elevon",
        family="trailing_edge",
        hinge_point=0.75,
        start_frac=0.0,
        end_frac=1.0,
        symmetric=True,
        deflection_sign="standard",
        delta_e_sym_deg=10.0,
        delta_a_diff_deg=0.0,
    )
    upper_deflected, lower_deflected = deflect_surface_pair(
        upper,
        lower,
        control,
        10.0,
    )
    np.testing.assert_allclose(upper_deflected[:2], upper[:2])
    np.testing.assert_allclose(lower_deflected[:2], lower[:2])
    assert np.mean(upper_deflected[-1, :, 2]) < np.mean(upper[-1, :, 2])
    assert np.mean(lower_deflected[-1, :, 2]) < np.mean(lower[-1, :, 2])


def test_operational_deflection_does_not_change_neutral_geometry_id() -> None:
    config = load_config(CONFIG)
    changed_geometry = copy.deepcopy(config.geometry)
    changed_geometry["control_surfaces"]["commands"] = {
        "delta_e_sym_deg": 12.0,
        "delta_a_diff_deg": -4.0,
    }
    commanded = replace(config, geometry=changed_geometry)
    assert (
        create_doe(config, n_samples_override=2)["geometry_id"].tolist()
        == create_doe(
            commanded,
            n_samples_override=2,
        )["geometry_id"].tolist()
    )


def test_gui_payload_keeps_physical_cad_outside_operational_commands() -> None:
    config = load_config(CONFIG)
    control = resolve_control_surface(config)
    extraction = config.geometry["extraction"]
    sampling = config.geometry["surface_sampling"]
    payload = build_config_payload(
        config,
        name=config.name,
        ranges=config.ranges,
        airfoils=config.fixed_airfoils,
        method=config.method,
        seed=config.seed,
        n_samples=config.n_samples,
        k_span=int(config.geometry["pygeo"]["k_span"]),
        spanwise_sections=int(extraction["spanwise_sections"]),
        chordwise_section_points=int(extraction["chordwise_points"]),
        cst_order=int(extraction["cst_order"]),
        surface_chordwise_points=int(sampling["chordwise_points"]),
        surface_spanwise_points=int(sampling["spanwise_points"]),
        control=control,
        output_root=str(config.output_root),
        output_flags={},
    )
    controls = payload["geometry"]["control_surfaces"]
    assert "physical_cad" in controls
    assert "physical_cad" not in controls["commands"]
