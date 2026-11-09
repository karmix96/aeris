from pathlib import Path

import numpy as np
import pytest

from cfdauto.volume.laws import move, rules


RULES1 = Path(__file__).resolve().parents[1] / "configs" / "volume_rules1.yaml"


def test_family_rule_per_level():
    """Rule set 2 (decisions 107, 111): 30 boundary-layer cells and 12 fan cells at M (the fan is -5 to +10 deg, 1.25 deg
    per cell), outboard growth 1.3 at VC."""
    want = {"VC": (1.25, 30 / 1.3 ** 2, 0.0075 * 1.69, 1.30, 12 / 1.69),
            "F": (1.25 ** (1 / 1.3 ** 3), 30 * 1.3, 0.0075 / 1.3, 1.30 ** (1 / 1.3 ** 3), 12 * 1.3)}
    for lev, (g, n, h, go, fan) in want.items():
        r = rules(lev)
        assert r.wall_growth == pytest.approx(g, rel=1e-12)
        assert r.bl_cells == pytest.approx(n, rel=1e-12)
        assert r.band["spacing_c"] == pytest.approx(h, rel=1e-12)
        assert r.outboard_growth == pytest.approx(go, rel=1e-12)
        assert r.band["fan_cells"] == pytest.approx(fan, rel=1e-12)
        assert r.band["max_aspect"] == 8.0 and r.raw["wake"]["first_cell"] == "te_cell"
        assert (r.band["alpha_lo_deg"], r.band["alpha_hi_deg"]) == (-5.0, 10.0)


def test_rule_set_1_is_kept():
    """Rule set 1 (V0-V6) stays buildable from its own file."""
    r = rules("VC", RULES1)
    assert r.bl_cells == 30.0 and r.outboard_growth == 1.15 and r.band["max_aspect"] == 4.0
    assert r.band["fan_cells"] == pytest.approx(40 / 1.69, rel=1e-12) and r.raw["wake"].get("first_cell", "s0") == "s0"


def test_anchor_is_exact():
    assert rules("M").band["spacing_c"] == 0.0075
    assert rules("VC").wall_growth == 1.25
    assert move(10.0, "size", 0, 1.3) == 10.0


def test_first_cell_is_stage2_law13():
    from cfdauto.mesh.laws import first_cell_c, rules as srules
    for lev in ("VC", "M"):
        r = rules(lev)
        assert r.first_cell(3e5, 2.0) == pytest.approx(first_cell_c(3e5, srules(lev).yplus) * 2.0, rel=1e-14)


def test_delta_turbulent_te():
    r = rules("VC")
    assert r.delta(1e6, 1.0) == pytest.approx(0.37 * 1e6 ** -0.2, rel=1e-14)


def test_band_cell_keeps_the_fan_cells():
    r = rules("M")
    b = r.band
    fan = np.tan(np.radians(b["alpha_hi_deg"])) - np.tan(np.radians(b["alpha_lo_deg"]))
    d = 50.0
    assert d * fan / r.band_cell(d) == pytest.approx(b["fan_cells"], rel=0.02)   # the TE cell adds 1.3 %
    assert r.band_cell(0.0) == pytest.approx(0.0075)
