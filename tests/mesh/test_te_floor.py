"""TE absolute-thickness floor (SURFACE_MESH_LAWS.md law 10)."""

from __future__ import annotations

import pytest

from aeris.mesh.surface import _te_fraction_with_floor


def test_floor_disabled_returns_base_fraction():
    # abs_floor = 0 is the default; behaviour must be unchanged.
    assert _te_fraction_with_floor(0.005, 1.6, 0.0) == pytest.approx(0.005)


def test_large_chord_is_untouched_by_floor():
    # Root chord 1.6 m: 0.5%c = 8 mm already exceeds an 8 mm floor.
    assert _te_fraction_with_floor(0.005, 1.6, 0.008) == pytest.approx(0.005)


def test_small_chord_is_raised_to_the_floor():
    # Tip chord 0.192 m: 0.5%c = 0.96 mm < 8 mm floor -> fraction rises so the
    # physical base is exactly the floor.
    frac = _te_fraction_with_floor(0.005, 0.192, 0.008)
    assert frac == pytest.approx(0.008 / 0.192)
    assert frac * 0.192 == pytest.approx(0.008)  # 8 mm absolute


def test_floor_is_clamped_to_five_percent_chord():
    # A floor far larger than the chord may not build a >5%c TE.
    assert _te_fraction_with_floor(0.005, 0.05, 0.010) == pytest.approx(0.05)


def test_zero_chord_falls_back_to_base_fraction():
    assert _te_fraction_with_floor(0.005, 0.0, 0.008) == pytest.approx(0.005)
