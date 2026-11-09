import numpy as np
import pytest

from cfdauto.volume.family import JUDGED, check13, measures, ratios


def fake(level: int, r: float = 1.3) -> dict:
    k = r ** level
    y = np.linspace(0, 3, 10 + 3 * level)
    return {"level": "VCCMF"[level], "y": list(y), "s0": list(1e-4 * (1 + y) / k), "wall_growth": 1.25 ** (1 / k),
            "band_cell": 0.01 / k, "outboard_first_gap": 2e-4 / k, "first_wake_cell": 1e-4 / k,
            "cell_1c_wall": 0.2 / k, "cell_1c_wake": 0.19 / k,
            "counts": {"n_layers": 90 * k, "n_wake": 70 * k, "n_out": 75 * k, "n_span": 60 * k, "n_c": 370 * k,
                       "n_base": 9, "cells": 4.9e6 * k ** 3}}


def test_check13_exact_family_passes():
    c, table = check13({"VC": fake(0), "C": fake(1), "M": fake(2)})
    assert c.passed and c.value < 1e-9
    assert set(table) == {"VC/C", "C/M"} and all(k in table["VC/C"] for k in JUDGED)


def test_check13_catches_a_bad_spacing():
    b = fake(1)
    b["band_cell"] *= 1.05                         # the band cell 5 % too coarse at C
    c, _ = check13({"VC": fake(0), "C": b})
    assert not c.passed and "band_cell" in c.note


def test_measures_on_the_vc_mesh(volume_vc):
    m = measures(volume_vc)
    st = volume_vc._plane["sts"]
    assert np.allclose(m["s0"], [s.s0 for s in st], rtol=0.01)
    assert m["first_wake_cell"] == pytest.approx(st[0].s0, rel=0.01)
    assert m["band_cell"] <= m["band_cell_rule"] * 1.01
    assert m["counts"]["cells"] == volume_vc.cells
    assert ratios(m, m)["s0"] == pytest.approx(1.0)
