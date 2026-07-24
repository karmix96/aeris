from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np

from standalone.pygeo_bwb_generator.generate import (
    create_doe,
    load_config,
    resolve_control_surface,
)
from standalone.pygeo_bwb_generator.physical_cad import (
    PhysicalCadSpec,
    _profile_from_section,
    physical_state_id,
    resolve_physical_cad_spec,
)

CONFIG = "standalone/pygeo_bwb_generator/config.yaml"


def test_physical_cad_configuration_is_enabled_and_named_split_topology() -> None:
    config = load_config(CONFIG)
    control = resolve_control_surface(config)
    spec = resolve_physical_cad_spec(
        config.geometry,
        control_enabled=control.enabled,
    )
    assert spec.enabled
    assert spec.topology == "split_elevon"
    assert spec.hinge_gap_fraction > 0.0
    assert spec.design_deflection_limit_deg >= 20.0
    assert spec.boundary_clearance_fraction > 0.0
    assert spec.max_master_to_cad_deviation_cref > 0.0

    assert bool(config.outputs["verify_step_import"])


def test_operational_commands_change_state_id_not_geometry_id() -> None:
    config = load_config(CONFIG)
    geometry_id = str(create_doe(config, n_samples_override=1).iloc[0]["geometry_id"])
    control = resolve_control_surface(config)
    commanded = replace(
        control,
        delta_e_sym_deg=8.0,
        delta_a_diff_deg=-3.0,
    )
    spec = resolve_physical_cad_spec(
        config.geometry,
        control_enabled=control.enabled,
    )
    assert physical_state_id(geometry_id, control, spec) != physical_state_id(
        geometry_id,
        commanded,
        spec,
    )


def test_root_profile_is_canonicalized_to_xz_symmetry_plane() -> None:
    section = SimpleNamespace(
        x_upper=np.array([0.0, 1.0]),
        z_upper=np.array([0.0, 0.01]),
        x_lower=np.array([0.0, 1.0]),
        z_lower=np.array([0.0, -0.01]),
        chord_axis=np.array([0.98, 0.04, -0.10]),
        local_span_axis=np.array([0.0, 0.99, 0.08]),
        thickness_axis=np.array([0.10, -0.08, 0.99]),
        span_fraction=0.0,
        le_xyz_m=np.array([0.2, 2.0e-5, 0.1]),
        chord_m=1.5,
    )
    profile = _profile_from_section(section, PhysicalCadSpec(chordwise_points=21))

    assert profile.le_xyz_m[1] == 0.0
    assert profile.chord_axis[1] == 0.0
    np.testing.assert_allclose(profile.span_axis, [0.0, 1.0, 0.0])
    assert profile.thickness_axis[1] == 0.0
    points = profile.xyz(profile.x, np.zeros_like(profile.x))
    np.testing.assert_allclose(points[:, 1], 0.0)
