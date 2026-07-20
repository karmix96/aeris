"""Preset registry: YAML load, validation, and equality with validated values."""

from __future__ import annotations

from pathlib import Path

import pytest

from aeris.cfd.presets.registry import (
    DATA_DIR,
    CfdPreset,
    _validate_preset,
    get_preset,
    list_presets,
)
from aeris.mesh.presets import CAP_WRAP_X, MARCH_POLICY, MESH_PRESETS


def test_mesh_family_presets_load():
    names = {p.name for p in list_presets(kind="mesh_family")}
    assert names == {"smoke", "fine", "production"}


def test_mesh_presets_equal_validated_values():
    """Pin the YAML-loaded values to the validated cap4 family (DSE_READINESS §5)."""
    expected = {
        "smoke": (49, 4),
        "fine": (71, 6),
        "production": (97, 8),
    }
    assert list(MESH_PRESETS) == ["smoke", "fine", "production"]  # coarse -> fine order
    for name, (pts, span) in expected.items():
        p = MESH_PRESETS[name]
        assert p.points_per_side == pts, name
        assert p.spanwise_panels == span, name
        assert p.cap_width_frac == 0.5, name
        assert p.cap_wrap_points == 17, name
        assert p.cap_wrap_x == 0.015, name


def test_march_policy_equals_validated_values():
    assert MARCH_POLICY == {
        "c_max": 0.5,
        "eps_e_far": 6.0,
        "eps_i_far": 12.0,
        "vol_smooth_iter": 1200,
        "n_constant_start": 3,
    }
    assert CAP_WRAP_X == 0.015  # the validated value — 0.03 was the CLI drift


def test_get_preset_unknown_lists_available():
    with pytest.raises(ValueError, match="Available"):
        get_preset("nope")


def test_preset_with_uncurated_volume_key_rejected():
    raw = {
        "schema": "aeris.cfd.preset.v1",
        "name": "bad",
        "kind": "mesh_family",
        "description": "x",
        "volume": {"splay": 0.25},
    }
    with pytest.raises(ValueError, match="curated"):
        _validate_preset(raw, Path("bad.yaml"))


def test_preset_with_unknown_surface_key_rejected():
    raw = {
        "schema": "aeris.cfd.preset.v1",
        "name": "bad",
        "kind": "mesh_family",
        "description": "x",
        "surface": {"points_per_sside": 49},
    }
    with pytest.raises(ValueError, match="unknown surface keys"):
        _validate_preset(raw, Path("bad.yaml"))


def test_all_shipped_presets_have_citation_and_valid_kind():
    for preset in list_presets():
        assert isinstance(preset, CfdPreset)
        assert preset.citation, f"{preset.name}: presets must cite their validation"
    assert DATA_DIR.is_dir()
