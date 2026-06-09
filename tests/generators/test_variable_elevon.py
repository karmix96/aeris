"""Tests for variable elevon size (17 → 20 DVs)."""
from __future__ import annotations
from dataclasses import fields
from pathlib import Path
import numpy as np
import yaml
from aeris.generators.bwb_segmented_v1.params import (
    BWBDesignSample, ControlSurfaceBoundsConfig, RangeConfig,
)

def _cfg(name):
    from aeris.common.config import load_yaml_config
    from aeris.geometry.config_resolver import resolve_generator_and_config
    raw = load_yaml_config(Path(__file__).parents[2] / "configs" / "geometry" / f"{name}.yaml")
    _, config = resolve_generator_and_config(raw)
    return config

def _sample(config, seed=42):
    from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design
    return sample_bwb_design(config, np.random.default_rng(seed))

def test_bwb_design_sample_has_20_fields():
    assert len(fields(BWBDesignSample)) == 20

def test_elevon_fields_exist():
    names = {f.name for f in fields(BWBDesignSample)}
    assert "elevon_start_frac" in names
    assert "elevon_end_frac"   in names
    assert "elevon_hinge_frac" in names

def test_elevon_defaults():
    f_map = {f.name: f.default for f in fields(BWBDesignSample)}
    assert f_map["elevon_start_frac"] == 0.60
    assert f_map["elevon_end_frac"]   == 0.95
    assert f_map["elevon_hinge_frac"] == 0.75

def test_control_surface_bounds_config_exists():
    eb = ControlSurfaceBoundsConfig(
        elevon_start_frac=RangeConfig(min=0.50, max=0.65),
        elevon_end_frac=RangeConfig(min=0.80, max=0.98),
        elevon_hinge_frac=RangeConfig(min=0.65, max=0.85),
    )
    assert eb.elevon_start_frac.min == 0.50

def test_v3_config_has_elevon_bounds():
    assert _cfg("bwb_training_v3").elevon_bounds is not None

def test_v2_config_has_no_elevon_bounds():
    assert _cfg("bwb_training_v2").elevon_bounds is None

def test_v1_config_has_no_elevon_bounds():
    assert _cfg("bwb_training_v1").elevon_bounds is None

def test_sampler_varies_elevon_v3():
    config = _cfg("bwb_training_v3")
    from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design
    rng = np.random.default_rng(42)
    samples = [sample_bwb_design(config, rng) for _ in range(20)]
    assert len(set(round(s.elevon_start_frac, 4) for s in samples)) > 1
    assert len(set(round(s.elevon_end_frac,   4) for s in samples)) > 1
    assert len(set(round(s.elevon_hinge_frac, 4) for s in samples)) > 1

def test_sampler_fixed_elevon_v2():
    config = _cfg("bwb_training_v2")
    from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design
    rng = np.random.default_rng(99)
    samples = [sample_bwb_design(config, rng) for _ in range(10)]
    assert all(s.elevon_start_frac == 0.60 for s in samples)
    assert all(s.elevon_end_frac   == 0.95 for s in samples)
    assert all(s.elevon_hinge_frac == 0.75 for s in samples)

def test_start_always_lt_end():
    config = _cfg("bwb_training_v3")
    from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design
    rng = np.random.default_rng(7)
    for _ in range(100):
        s = sample_bwb_design(config, rng)
        assert s.elevon_start_frac < s.elevon_end_frac

def test_elevon_within_bounds():
    config = _cfg("bwb_training_v3")
    eb = config.elevon_bounds
    from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design
    rng = np.random.default_rng(13)
    for _ in range(50):
        s = sample_bwb_design(config, rng)
        assert eb.elevon_start_frac.min <= s.elevon_start_frac <= eb.elevon_start_frac.max
        assert eb.elevon_end_frac.min   <= s.elevon_end_frac   <= eb.elevon_end_frac.max
        assert eb.elevon_hinge_frac.min <= s.elevon_hinge_frac <= eb.elevon_hinge_frac.max

def test_v3_feature_presets():
    from aeris.ml.feature_presets import get_feature_preset
    p = get_feature_preset("bwb_control_sym_elevon_v3")
    assert "elevon_start_frac" in p.columns
    assert "delta_e_sym_deg"   in p.columns
    d = get_feature_preset("bwb_diff_elevon_v3")
    assert "delta_a_diff_deg" in d.columns

def test_existing_presets_unaffected():
    from aeris.ml.feature_presets import list_feature_preset_names
    names = list_feature_preset_names()
    for n in ("bwb_basic","bwb_control","bwb_control_sym_elevon","airfoil_xfoil_v1"):
        assert n in names

def test_v3_yaml_validates():
    from aeris.common.config import load_yaml_config
    from aeris.geometry.config_resolver import resolve_generator_and_config
    from aeris.generators.bwb_segmented_v1.validation import validate_bwb_generator_config
    cfg_path = Path(__file__).parents[2] / "configs" / "geometry" / "bwb_training_v3.yaml"
    _, config = resolve_generator_and_config(load_yaml_config(cfg_path))
    validate_bwb_generator_config(config)

def test_v3_yaml_start_max_lt_end_min():
    cfg_path = Path(__file__).parents[2] / "configs" / "geometry" / "bwb_training_v3.yaml"
    data = yaml.safe_load(cfg_path.read_text())
    eb = data["geometry"]["elevon_bounds"]
    assert eb["elevon_start_frac"]["max"] < eb["elevon_end_frac"]["min"]
