from __future__ import annotations

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_airfoil_help_shows_cst_generator_command() -> None:
    result = runner.invoke(app, ["airfoil", "--help"])
    assert result.exit_code == 0, result.output
    assert "generate-cst-library" in result.output


def test_airfoil_generate_cst_library_cli_smoke(tmp_path) -> None:
    cfg = tmp_path / "cst.yaml"
    cfg.write_text(
        """
airfoil:
  generator:
    id: cst_airfoil_v1
    seed: 5
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
    out = tmp_path / "library"
    result = runner.invoke(app, [
        "airfoil", "generate-cst-library",
        "--config", str(cfg),
        "--output-dir", str(out),
    ])
    assert result.exit_code == 0, result.output
    assert "cst_airfoil_v1" in result.output
    inv = out / "airfoil_inventory.csv"
    assert inv.exists()
    df = pd.read_csv(inv)
    assert len(df) == 2
    assert "cst_u8" in df.columns
