from __future__ import annotations

from pathlib import Path

import yaml


CONFIG = Path("configs/geometry/bwb_training_v1.yaml")
BASELINE = Path("configs/geometry/baseline_bwb_25.yaml")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _width(bounds: dict, key: str) -> float:
    item = bounds[key]
    return float(item["max"]) - float(item["min"])


def test_bwb_training_v1_config_exists_and_uses_current_generator() -> None:
    assert CONFIG.exists()
    cfg = _load(CONFIG)

    assert cfg["name"] == "bwb_training_v1"
    assert cfg["geometry"]["generator"]["id"] == "bwb_segmented_v1"
    assert cfg["geometry"]["outputs"]["build_aerosandbox"] is True
    assert cfg["geometry"]["outputs"]["save_plot"] is False
    assert cfg["dataset"]["sampling"]["method"] == "lhs_v1"


def test_bwb_training_v1_is_not_near_fixed_baseline() -> None:
    cfg = _load(CONFIG)
    baseline = _load(BASELINE)

    bounds = cfg["geometry"]["planform_bounds"]
    baseline_bounds = baseline["geometry"]["planform_bounds"]

    # The smoke baseline has near-zero widths; this training config must span a real design space.
    assert _width(bounds, "c1_m") >= 0.50
    assert _width(bounds, "b_total_m") >= 0.50
    assert _width(bounds, "sw1_deg") >= 20.0
    assert _width(bounds, "sw2_deg") >= 25.0
    assert _width(bounds, "sw3_deg") >= 25.0

    assert _width(bounds, "c1_m") > 1000.0 * _width(baseline_bounds, "c1_m")
    assert _width(bounds, "b_total_m") > 1000.0 * _width(baseline_bounds, "b_total_m")


def test_bwb_training_v1_keeps_control_surface_contract() -> None:
    cfg = _load(CONFIG)
    controls = cfg["geometry"]["control_surfaces"]

    assert controls["enabled"] is True
    surfaces = controls["surfaces"]
    assert len(surfaces) == 1

    elevon = surfaces[0]
    assert elevon["name"] == "elevon"
    assert elevon["family"] == "trailing_edge"
    assert elevon["hinge_point"] == 0.75
    assert elevon["symmetric"] is True
    assert elevon["spanwise"]["start_frac"] == 0.60
    assert elevon["spanwise"]["end_frac"] == 0.95
