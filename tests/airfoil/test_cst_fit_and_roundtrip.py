"""Tests for CSTAirfoil.fit(), fit_dat(), generate_batch(), to_dat(),
to_json(), from_json(), __repr__, ValidationReport.__str__,
and aeris airfoil fit-cst CLI.

Restores the full capability of the original cst_airfoil.py script.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from aeris.airfoil.cst_generator import (
    CSTAirfoil,
    ValidationLimits,
    ValidationReport,
    _read_selig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _known_foil(order: int = 8) -> CSTAirfoil:
    return CSTAirfoil.generate_random(
        order=order,
        au_bounds=(0.10, 0.20),
        al_bounds=(-0.20, -0.05),
        limits=ValidationLimits(max_curvature_reversals=12),
        rng=np.random.default_rng(42),
        name="test_foil",
    )


# ---------------------------------------------------------------------------
# ValidationReport.__str__
# ---------------------------------------------------------------------------

def test_validation_report_str_valid() -> None:
    report = _known_foil().validate()
    s = str(report)
    assert s.startswith("VALID")
    assert "min_gap" in s


def test_validation_report_str_invalid() -> None:
    foil = CSTAirfoil(np.zeros(9), np.zeros(9), name="flat")
    report = foil.validate()
    assert not report.valid
    s = str(report)
    assert s.startswith("INVALID")


# ---------------------------------------------------------------------------
# __repr__
# ---------------------------------------------------------------------------

def test_cst_airfoil_repr() -> None:
    foil = _known_foil()
    r = repr(foil)
    assert "CSTAirfoil(" in r
    assert "order=8" in r
    assert "t/c=" in r


# ---------------------------------------------------------------------------
# generate_batch
# ---------------------------------------------------------------------------

def test_generate_batch_count_and_valid() -> None:
    foils = CSTAirfoil.generate_batch(
        4, seed=7, order=8,
        au_bounds=(0.08, 0.22), al_bounds=(-0.22, -0.02),
        limits=ValidationLimits(max_curvature_reversals=12),
    )
    assert len(foils) == 4
    for f in foils:
        assert f.validate().valid


def test_generate_batch_reproducible() -> None:
    kw = dict(seed=99, order=4, au_bounds=(0.10, 0.25), al_bounds=(-0.25, -0.05))
    a = CSTAirfoil.generate_batch(3, **kw)
    b = CSTAirfoil.generate_batch(3, **kw)
    for fa, fb in zip(a, b):
        np.testing.assert_array_equal(fa.au, fb.au)


# ---------------------------------------------------------------------------
# fit() + fit_dat()
# ---------------------------------------------------------------------------

def test_cst_fit_roundtrip_from_coordinates() -> None:
    foil = _known_foil(order=8)
    x = np.linspace(0.0, 1.0, 201)
    fitted, rms = CSTAirfoil.fit(x, foil.upper(x), x, foil.lower(x), order=8)
    assert rms < 1e-6, f"Self-fit RMS too large: {rms}"
    np.testing.assert_allclose(fitted.au, foil.au, atol=1e-5)
    np.testing.assert_allclose(fitted.al, foil.al, atol=1e-5)
    assert fitted.validate().valid


def test_cst_fit_lower_order_converges() -> None:
    foil = _known_foil(order=8)
    x = np.linspace(0.01, 0.99, 151)
    fitted, rms = CSTAirfoil.fit(
        x, foil.upper(x), x, foil.lower(x), order=4,
    )
    assert rms < 0.02
    assert fitted.validate(ValidationLimits(max_curvature_reversals=12)).valid


def test_cst_fit_dat_roundtrip(tmp_path: Path) -> None:
    foil = _known_foil(order=8)
    dat_path = tmp_path / "test.dat"
    foil.to_dat(str(dat_path), n_per_surface=201)
    fitted, rms = CSTAirfoil.fit_dat(dat_path, order=8)
    assert rms < 1e-4, f"fit_dat RMS: {rms}"
    assert fitted.validate().valid


def test_cst_fit_infers_dz_te_zero() -> None:
    foil = _known_foil()
    x = np.linspace(0.0, 1.0, 101)
    fitted, _ = CSTAirfoil.fit(x, foil.upper(x), x, foil.lower(x))
    assert abs(fitted.dz_te) < 1e-9


# ---------------------------------------------------------------------------
# to_dat() / _read_selig()
# ---------------------------------------------------------------------------

def test_to_dat_writes_selig_file(tmp_path: Path) -> None:
    foil = _known_foil()
    path = tmp_path / "out.dat"
    foil.to_dat(str(path), n_per_surface=81)
    text = path.read_text()
    lines = [l for l in text.splitlines() if l.strip()]
    assert foil.name in lines[0]
    coords = [tuple(float(v) for v in l.split()[:2]) for l in lines[1:]]
    # Selig loop: starts and ends near TE (x~1)
    assert coords[0][0] > 0.9
    assert coords[-1][0] > 0.9


def test_read_selig_round_trip(tmp_path: Path) -> None:
    foil = _known_foil()
    path = tmp_path / "out.dat"
    foil.to_dat(str(path), n_per_surface=81)
    pts = _read_selig(str(path))
    assert pts.shape[1] == 2
    assert pts.shape[0] >= 80


def test_read_selig_rejects_empty(tmp_path: Path) -> None:
    path = tmp_path / "bad.dat"
    path.write_text("naca2412\n", encoding="utf-8")
    with pytest.raises(ValueError, match="minimum 10 required"):
        _read_selig(str(path))


# ---------------------------------------------------------------------------
# to_json() / from_json()
# ---------------------------------------------------------------------------

def test_to_json_from_json_roundtrip(tmp_path: Path) -> None:
    foil = _known_foil()
    path = tmp_path / "foil.json"
    foil.to_json(path)
    loaded = CSTAirfoil.from_json(path)
    assert loaded.order == foil.order
    assert loaded.name == foil.name
    np.testing.assert_array_almost_equal(loaded.au, foil.au)
    np.testing.assert_array_almost_equal(loaded.al, foil.al)
    assert loaded.validate().valid


def test_to_json_is_valid_json(tmp_path: Path) -> None:
    foil = _known_foil()
    path = tmp_path / "foil.json"
    foil.to_json(path)
    data = json.loads(path.read_text())
    assert len(data["au"]) == foil.order + 1
    assert len(data["al"]) == foil.order + 1


# ---------------------------------------------------------------------------
# aeris airfoil fit-cst CLI
# ---------------------------------------------------------------------------

def test_airfoil_fit_cst_cli(tmp_path: Path) -> None:
    from typer.testing import CliRunner
    from aeris.cli import app

    foil = _known_foil()
    dat_path = tmp_path / "naca_test.dat"
    foil.to_dat(str(dat_path), n_per_surface=201)
    out_dir = tmp_path / "fit_output"

    runner = CliRunner()
    result = runner.invoke(app, [
        "airfoil", "fit-cst",
        str(dat_path),
        "--output-dir", str(out_dir),
        "--order", "8",
        "--name", "test_cli_fit",
    ])
    assert result.exit_code == 0, f"CLI failed:\n{result.stdout}"
    assert (out_dir / "naca_test_cst.json").exists()
    report = json.loads((out_dir / "fit_report.json").read_text())
    assert report["order"] == 8
    assert report["rms_error"] < 1e-3
    assert report["validation_valid"] is True
