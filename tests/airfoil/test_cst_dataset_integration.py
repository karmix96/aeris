from __future__ import annotations

from pathlib import Path

import pandas as pd

from aeris.aero_2d.models import Aero2DResult
from aeris.airfoil.cst_generator import generate_cst_airfoil_library
from aeris.airfoil.dataset_generate import generate_airfoil_dataset


def _cst_cfg(tmp_path: Path) -> Path:
    path = tmp_path / "cst.yaml"
    path.write_text(
        """
airfoil:
  generator:
    id: cst_airfoil_v1
    seed: 11
    n_airfoils: 2
    order: 8
    n_per_surface: 31
    coefficient_bounds:
      au: [0.08, 0.22]
      al: [-0.22, -0.02]
    validation_limits:
      max_curvature_reversals: 12
""",
        encoding="utf-8",
    )
    return path


def _sweep_cfg(tmp_path: Path) -> Path:
    path = tmp_path / "xfoil.yaml"
    path.write_text(
        """
sweep:
  alpha_start: 0.0
  alpha_end: 0.0
  alpha_step: 1.0
  reynolds: [1000000]
  mach: [0.0]
  ncrit: 9.0
solver:
  max_iter: 10
  repanel: true
""",
        encoding="utf-8",
    )
    return path


def test_xfoil_dataset_rows_propagate_cst_feature_columns(tmp_path: Path, monkeypatch) -> None:
    lib = tmp_path / "lib"
    generate_cst_airfoil_library(config_path=_cst_cfg(tmp_path), output_dir=lib)

    def fake_run_alpha_sweep(**kwargs):
        return [Aero2DResult(
            airfoil_id=kwargs["airfoil_id"],
            airfoil_name=kwargs["airfoil_name"],
            source_file=kwargs["source_file"],
            alpha_deg=0.0,
            reynolds=1_000_000.0,
            mach=0.0,
            ncrit=9.0,
            cl=0.1,
            cd=0.01,
            cm=-0.02,
            cp_min=None,
            converged=True,
            solver_id="fake_xfoil",
            solver_version="test",
        )]

    import aeris.airfoil.dataset_generate as dg
    monkeypatch.setattr(dg, "run_alpha_sweep", fake_run_alpha_sweep)

    root = tmp_path / "dataset"
    manifest = generate_airfoil_dataset(
        library_dir=lib,
        config_path=_sweep_cfg(tmp_path),
        dataset_root=root,
        name="cst_ds",
    )

    df = pd.read_csv(root / "airfoil_dataset.csv")
    assert len(df) == 2
    assert "cst_u0" in df.columns
    assert "cst_u8" in df.columns
    assert "cst_l8" in df.columns
    assert "generator_id" in df.columns
    assert manifest["airfoil_source_schema"]["has_cst_features"] is True
    assert "cst_u0" in manifest["airfoil_source_schema"]["cst_feature_columns"]
