from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from aeris.airfoil.cst_generator import CSTAirfoil, ValidationLimits, generate_cst_airfoil_library
from aeris.airfoil.library import AirfoilLibrary
from aeris.ml.feature_presets import get_feature_preset, list_feature_preset_names


def _cfg(tmp_path: Path, n: int = 4) -> Path:
    path = tmp_path / "cst.yaml"
    path.write_text(
        f"""
airfoil:
  generator:
    id: cst_airfoil_v1
    seed: 7
    n_airfoils: {n}
    order: 8
    n_per_surface: 31
    coefficient_bounds:
      au: [0.08, 0.22]
      al: [-0.22, -0.02]
    validation_limits:
      min_thickness: 0.005
      max_thickness: 0.50
      max_curvature_reversals: 12
""",
        encoding="utf-8",
    )
    return path


def test_cst_airfoil_random_generation_validates() -> None:
    foil = CSTAirfoil.generate_random(
        order=8,
        au_bounds=(0.08, 0.22),
        al_bounds=(-0.22, -0.02),
        limits=ValidationLimits(max_curvature_reversals=12),
        rng=np.random.default_rng(1),
    )
    report = foil.validate(ValidationLimits(max_curvature_reversals=12))
    assert report.valid, report.failures
    coords = foil.coordinates(n_per_surface=31)
    assert coords.shape[1] == 2
    assert np.isfinite(coords).all()


def test_generate_cst_library_writes_aeris_library_contract(tmp_path: Path) -> None:
    out = tmp_path / "lib"
    report = generate_cst_airfoil_library(config_path=_cfg(tmp_path, n=3), output_dir=out)

    assert report["generator_id"] == "cst_airfoil_v1"
    assert report["n_airfoils_generated"] == 3
    assert (out / "airfoil_inventory.csv").exists()
    assert (out / "coords").is_dir()
    assert (out / "dat").is_dir()
    assert (out / "cst_airfoil_library_manifest.json").exists()

    df = pd.read_csv(out / "airfoil_inventory.csv")
    assert len(df) == 3
    assert "cst_u0" in df.columns
    assert "cst_u8" in df.columns
    assert "cst_l8" in df.columns
    assert set(df["family"]) == {"cst"}
    assert df["cst_validation_valid"].astype(bool).all()

    lib = AirfoilLibrary(out)
    first = df.iloc[0]["airfoil_id"]
    rec = lib.get_by_id(first)
    metadata = lib.metadata_for_id(first)
    assert rec.airfoil_id == first
    assert "cst_u0" in metadata


def test_airfoil_cst_feature_preset_registered() -> None:
    assert "airfoil_cst_xfoil_v1" in list_feature_preset_names()
    preset = get_feature_preset("airfoil_cst_xfoil_v1")
    assert "cst_u0" in preset.columns
    assert "cst_u8" in preset.columns
    assert "cst_l8" in preset.columns
    assert "alpha_deg" in preset.columns
    assert preset.domain == "airfoil_2d_scalar_aero"
