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
