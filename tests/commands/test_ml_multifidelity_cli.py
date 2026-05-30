from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def test_ml_build_delta_dataset_cli(tmp_path: Path) -> None:
    lf_path = tmp_path / "lf.csv"
    hf_path = tmp_path / "hf.csv"
    out_dir = tmp_path / "delta"

    pd.DataFrame({
        "geometry_id": ["g1", "g2"],
        "alpha_deg": [0.0, 2.0],
        "velocity_mps": [28.0, 28.0],
        "cl": [0.10, 0.20],
        "cd": [0.010, 0.020],
        "cm": [-0.10, -0.20],
    }).to_csv(lf_path, index=False)
    pd.DataFrame({
        "geometry_id": ["g1", "g2"],
        "alpha_deg": [0.0, 2.0],
        "velocity_mps": [28.0, 28.0],
        "cl": [0.11, 0.21],
        "cd": [0.012, 0.019],
        "cm": [-0.09, -0.22],
    }).to_csv(hf_path, index=False)

    result = runner.invoke(app, [
        "ml", "build-delta-dataset",
        "--lf-csv", str(lf_path),
        "--hf-csv", str(hf_path),
        "--pair-keys", "geometry_id,alpha_deg,velocity_mps",
        "--targets", "cl,cd,cm",
        "--output-dir", str(out_dir),
    ])

    assert result.exit_code == 0, result.stdout
    assert "ML multifidelity delta dataset built" in result.stdout
    assert "paired_rows: 2" in result.stdout
    assert (out_dir / "delta_dataset.csv").exists()
    assert (out_dir / "delta_dataset_report.json").exists()
