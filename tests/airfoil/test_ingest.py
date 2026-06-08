"""Unit tests for .dat airfoil ingest (Selig format)."""
from __future__ import annotations

import numpy as np
import pytest

from aeris.airfoil.ingest import ingest_airfoil_library, _parse_dat_file


def _write_dat(path, name, x, y):
    """Write a minimal Selig-format .dat file."""
    lines = [name]
    for xi, yi in zip(x, y):
        lines.append(f"{xi:.6f}  {yi:.6f}")
    path.write_text("\n".join(lines), encoding="utf-8")


def _symmetric_coords(n=40):
    """Simple symmetric airfoil (flat plate with thickness)."""
    x_upper = np.linspace(1, 0, n // 2)
    y_upper = 0.06 * np.sqrt(x_upper) * (1 - x_upper)
    x_lower = np.linspace(0, 1, n // 2)
    y_lower = -0.06 * np.sqrt(x_lower) * (1 - x_lower)
    x = np.concatenate([x_upper, x_lower])
    y = np.concatenate([y_upper, y_lower])
    return x, y


# ── _parse_dat_file ───────────────────────────────────────────────────────────

def test_parse_dat_with_name_line(tmp_path):
    x, y = _symmetric_coords()
    f = tmp_path / "test.dat"
    _write_dat(f, "TestAirfoil", x, y)
    name, xp, yp = _parse_dat_file(f)
    assert name == "TestAirfoil"
    assert len(xp) == len(x)
    assert np.allclose(xp.min(), 0.0, atol=1e-6)
    assert np.allclose(xp.max(), 1.0, atol=1e-6)


def test_parse_dat_no_name_line(tmp_path):
    """First line is coordinates, not a name — use filename."""
    x, y = _symmetric_coords()
    lines = [f"{xi:.6f}  {yi:.6f}" for xi, yi in zip(x, y)]
    f = tmp_path / "my_airfoil.dat"
    f.write_text("\n".join(lines), encoding="utf-8")
    name, xp, yp = _parse_dat_file(f)
    assert name == "my_airfoil"
    assert len(xp) == len(x)


def test_parse_dat_normalises_chord(tmp_path):
    """Coordinates scaled 0-100 should be normalised to 0-1."""
    x, y = _symmetric_coords()
    x_scaled = x * 100.0
    y_scaled = y * 100.0
    f = tmp_path / "scaled.dat"
    _write_dat(f, "Scaled", x_scaled, y_scaled)
    _, xp, yp = _parse_dat_file(f)
    assert xp.max() <= 1.0 + 1e-6
    assert xp.min() >= -1e-6


def test_parse_dat_skips_comment_lines(tmp_path):
    x, y = _symmetric_coords()
    lines = ["# This is a comment", "MyAirfoil"]
    for xi, yi in zip(x, y):
        lines.append(f"{xi:.6f}  {yi:.6f}")
    f = tmp_path / "commented.dat"
    f.write_text("\n".join(lines), encoding="utf-8")
    name, xp, yp = _parse_dat_file(f)
    assert name == "MyAirfoil"
    assert len(xp) >= 10


def test_parse_dat_too_few_points_raises(tmp_path):
    f = tmp_path / "tiny.dat"
    f.write_text("TinyAirfoil\n0.0 0.0\n0.5 0.1\n1.0 0.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="valid coordinate pairs"):
        _parse_dat_file(f)


def test_parse_dat_empty_file_raises(tmp_path):
    f = tmp_path / "empty.dat"
    f.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        _parse_dat_file(f)


# ── ingest_airfoil_library ────────────────────────────────────────────────────

def test_ingest_single_dat(tmp_path):
    db = tmp_path / "db"; db.mkdir()
    lib = tmp_path / "lib"
    x, y = _symmetric_coords()
    _write_dat(db / "naca0012.dat", "NACA 0012", x, y)

    report = ingest_airfoil_library(db_dir=db, output_dir=lib)
    assert report["ingested"] == 1
    assert report["failures"] == 0
    assert (lib / "airfoil_inventory.csv").exists()

    import pandas as pd
    df = pd.read_csv(lib / "airfoil_inventory.csv")
    assert len(df) == 1
    assert "airfoil_id" in df.columns
    assert "t_c" in df.columns
    assert len(df.iloc[0]["airfoil_id"]) == 16


def test_ingest_multiple_dat(tmp_path):
    db = tmp_path / "db"; db.mkdir()
    lib = tmp_path / "lib"
    x, y = _symmetric_coords()
    # Two distinct airfoils (different thickness)
    _write_dat(db / "a.dat", "Airfoil A", x, y * 1.0)
    _write_dat(db / "b.dat", "Airfoil B", x, y * 1.5)

    report = ingest_airfoil_library(db_dir=db, output_dir=lib)
    assert report["ingested"] == 2
    assert report["failures"] == 0


def test_ingest_duplicate_geometry_counted_as_failure(tmp_path):
    db = tmp_path / "db"; db.mkdir()
    lib = tmp_path / "lib"
    x, y = _symmetric_coords()
    _write_dat(db / "a.dat", "Airfoil A", x, y)
    _write_dat(db / "b.dat", "Airfoil B", x, y)  # identical coords

    report = ingest_airfoil_library(db_dir=db, output_dir=lib)
    assert report["ingested"] == 1
    assert report["failures"] == 1
    assert "duplicate" in report["failure_details"][0]["reason"]


def test_ingest_bad_file_skipped(tmp_path):
    db = tmp_path / "db"; db.mkdir()
    lib = tmp_path / "lib"
    # Bad file
    (db / "bad.dat").write_text("NotAnAirfoil\njunk data here\n", encoding="utf-8")
    # Good file
    x, y = _symmetric_coords()
    _write_dat(db / "good.dat", "Good", x, y)

    report = ingest_airfoil_library(db_dir=db, output_dir=lib)
    assert report["ingested"] == 1
    assert report["failures"] == 1


def test_ingest_no_dat_files_raises(tmp_path):
    db = tmp_path / "empty"; db.mkdir()
    lib = tmp_path / "lib"
    with pytest.raises(FileNotFoundError, match=".dat"):
        ingest_airfoil_library(db_dir=db, output_dir=lib)


def test_ingest_coords_npz_written(tmp_path):
    db = tmp_path / "db"; db.mkdir()
    lib = tmp_path / "lib"
    x, y = _symmetric_coords()
    _write_dat(db / "test.dat", "Test", x, y)

    report = ingest_airfoil_library(db_dir=db, output_dir=lib)

    import pandas as pd
    inv = pd.read_csv(lib / "airfoil_inventory.csv")
    aid = inv.iloc[0]["airfoil_id"]
    npz = lib / "coords" / f"{aid}.npz"
    assert npz.exists()
    data = np.load(npz)
    assert "x" in data and "y" in data
    assert data["x"].max() <= 1.0 + 1e-6
