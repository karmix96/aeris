from __future__ import annotations

import numpy as np
import pytest

from standalone.pygeo_bwb_generator.generate import (
    DIRECT_VARIABLES,
    create_doe,
    direct_to_aeris_sample,
    load_config,
)

CONFIG = "standalone/pygeo_bwb_generator/config.yaml"


def test_doe_is_deterministic_and_has_direct_physical_variables() -> None:
    config = load_config(CONFIG)
    first = create_doe(config, n_samples_override=4)
    second = create_doe(config, n_samples_override=4)
    assert list(first["geometry_id"]) == list(second["geometry_id"])
    np.testing.assert_allclose(
        first[list(DIRECT_VARIABLES)].to_numpy(float),
        second[list(DIRECT_VARIABLES)].to_numpy(float),
    )


def test_direct_variables_convert_exactly_to_aeris_ratios() -> None:
    config = load_config(CONFIG)
    row = create_doe(config, n_samples_override=1).iloc[0]
    direct = {name: float(row[name]) for name in DIRECT_VARIABLES}
    sample = direct_to_aeris_sample(direct)
    assert np.isclose(sample.c2_ratio, direct["c2_m"] / direct["c1_m"])
    assert np.isclose(sample.c3_ratio, direct["c3_m"] / direct["c1_m"])
    assert np.isclose(sample.c4_ratio, direct["c4_m"] / direct["c1_m"])
    semispan = direct["b1_m"] + direct["b2_m"] + direct["b3_m"]
    assert np.isclose(sample.b_total_m, semispan)
    assert np.isclose(sample.b3_ratio, direct["b3_m"] / semispan)
    assert np.isclose(
        sample.split_ratio,
        direct["b1_m"] / (direct["b1_m"] + direct["b2_m"]),
    )
    assert sample.sw1_deg < 0.0


def test_config_resolves_four_fixed_airfoils() -> None:
    config = load_config(CONFIG)
    assert tuple(config.fixed_airfoils) == ("b0", "b1", "b2", "b3")
    for name in config.fixed_airfoils.values():
        assert (config.airfoil_database / f"{name}.dat").is_file()


def test_root_panel_dihedral_is_hard_fixed_zero() -> None:
    config = load_config(CONFIG)
    root_panel = config.ranges["dihedral_b1_deg"]
    assert not root_panel.varied
    assert root_panel.minimum == root_panel.maximum == 0.0
    frame = create_doe(config, n_samples_override=4)
    np.testing.assert_allclose(frame["dihedral_b1_deg"], 0.0)


def test_direct_sample_rejects_nonzero_root_panel_dihedral() -> None:
    config = load_config(CONFIG)
    row = create_doe(config, n_samples_override=1).iloc[0]
    direct = {name: float(row[name]) for name in DIRECT_VARIABLES}
    direct["dihedral_b1_deg"] = 0.1
    with pytest.raises(ValueError, match="dihedral_b1_deg must be exactly 0"):
        direct_to_aeris_sample(direct)
