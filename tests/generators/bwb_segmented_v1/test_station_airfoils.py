"""Regression tests for StationAirfoilsConfig and _resolve_station_airfoil."""
from __future__ import annotations
import pytest
from pathlib import Path
from aeris.generators.bwb_segmented_v1.params import StationAirfoilsConfig, build_bwb_generator_config
from aeris.generators.bwb_segmented_v1.sections import _resolve_station_airfoil
from aeris.common.config import load_yaml_config

SA = StationAirfoilsConfig(b0="naca23012", b1="naca4412", b2="naca2412", b3="naca0012")
GBY = [0.0, 0.5, 1.0, 1.6]

def test_root_gets_b0():         assert _resolve_station_airfoil(0.0, GBY, SA) == "naca23012"
def test_inboard_gets_b0():      assert _resolve_station_airfoil(0.3, GBY, SA) == "naca23012"
def test_kink_gets_b1():         assert _resolve_station_airfoil(0.5, GBY, SA) == "naca4412"
def test_mid_segment_gets_b1():  assert _resolve_station_airfoil(0.7, GBY, SA) == "naca4412"
def test_mid_gets_b2():          assert _resolve_station_airfoil(1.0, GBY, SA) == "naca2412"
def test_outboard_gets_b2():     assert _resolve_station_airfoil(1.3, GBY, SA) == "naca2412"
def test_tip_gets_b3():          assert _resolve_station_airfoil(1.6, GBY, SA) == "naca0012"

def test_parse_fails_missing_key():
    from aeris.generators.bwb_segmented_v1.params import _parse_station_airfoils
    with pytest.raises(ValueError, match="missing key"):
        _parse_station_airfoils({"b0": "naca4412", "b1": "naca4412"})

def test_parse_fails_empty_name():
    from aeris.generators.bwb_segmented_v1.params import _parse_station_airfoils
    with pytest.raises(ValueError, match="non-empty string"):
        _parse_station_airfoils({"b0": "", "b1": "a", "b2": "b", "b3": "c"})

def test_yaml_integration():
    cfg_path = Path("configs/geometry/paper1_bwb_naca_stations.yaml")
    if not cfg_path.exists(): pytest.skip("config not found")
    config = build_bwb_generator_config(load_yaml_config(str(cfg_path)))
    sa = config.section_bounds.station_airfoils
    assert sa is not None
    assert sa.b0 == "naca23012" and sa.b3 == "naca0012"

def test_no_station_airfoils_backward_compat():
    cfg_path = Path("configs/geometry/baseline_bwb_25.yaml")
    if not cfg_path.exists(): pytest.skip("config not found")
    config = build_bwb_generator_config(load_yaml_config(str(cfg_path)))
    assert config.section_bounds.station_airfoils is None


# --- Wiring regression: the builder must APPLY station_airfoils, not just parse it ---

def _build_sections(cfg_path: Path):
    from aeris.generators.bwb_segmented_v1.generator import BwbSegmentedV1Generator
    from aeris.generators.bwb_segmented_v1.planform import (
        generate_bwb_planform_from_sample,
    )
    from aeris.generators.bwb_segmented_v1.sections import (
        build_section_geometry_from_sample,
    )
    generator = BwbSegmentedV1Generator()
    config = generator.build_config(load_yaml_config(str(cfg_path)))
    sample = generator.sample_one(config, seed=0)
    planform = generate_bwb_planform_from_sample(sample, config)
    return config, build_section_geometry_from_sample(planform, sample, config)


def test_builder_applies_station_airfoils():
    """The section builder must wire station_airfoils onto SectionRecords.

    Regression for the hardcoded-root bug: station_airfoils was parsed but the
    build loop stamped the single root airfoil onto every station.
    """
    cfg_path = Path("configs/geometry/paper1_bwb_naca_stations.yaml")
    if not cfg_path.exists(): pytest.skip("config not found")
    config, geom = _build_sections(cfg_path)
    spec = config.section_bounds.station_airfoils
    assert spec is not None
    names = {r.airfoil_name for r in geom.sections}
    # More than the single root airfoil must appear.
    assert len(names) > 1, f"builder ignored station_airfoils; got only {names}"
    assert names <= {spec.b0, spec.b1, spec.b2, spec.b3}
    # Root section carries b0; tip section carries b3.
    assert geom.sections[0].airfoil_name == spec.b0
    assert geom.sections[-1].airfoil_name == spec.b3
    # Every station matches the step-function resolver applied to its own y.
    gby = geom.group_boundary_y
    for r in geom.sections:
        assert r.airfoil_name == _resolve_station_airfoil(r.y_m, gby, spec)


def test_builder_single_airfoil_backward_compat():
    """With no station_airfoils, every station uses the single root airfoil."""
    cfg_path = Path("configs/geometry/baseline_bwb_25.yaml")
    if not cfg_path.exists(): pytest.skip("config not found")
    config, geom = _build_sections(cfg_path)
    assert config.section_bounds.station_airfoils is None
    names = {r.airfoil_name for r in geom.sections}
    assert names == {config.section_bounds.airfoil_name}
