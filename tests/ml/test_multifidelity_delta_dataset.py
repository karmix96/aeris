from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aeris.ml.multifidelity import build_delta_dataset


def test_build_delta_dataset_pairs_rows_and_computes_deltas(tmp_path: Path) -> None:
    lf = pd.DataFrame({
        "geometry_id": ["g1", "g2", "g3"],
        "alpha_deg": [0.0, 2.0, 4.0],
        "velocity_mps": [28.0, 28.0, 28.0],
        "c1_m": [1.5, 1.6, 1.7],
        "cl": [0.10, 0.20, 0.30],
        "cd": [0.010, 0.020, 0.030],
        "cm": [-0.10, -0.20, -0.30],
    })
    hf = pd.DataFrame({
        "geometry_id": ["g1", "g2", "g4"],
        "alpha_deg": [0.0, 2.0, 6.0],
        "velocity_mps": [28.0, 28.0, 28.0],
        "cl": [0.11, 0.23, 0.44],
        "cd": [0.012, 0.021, 0.040],
        "cm": [-0.12, -0.19, -0.40],
    })
    lf_path = tmp_path / "lf.csv"
    hf_path = tmp_path / "hf.csv"
    lf.to_csv(lf_path, index=False)
    hf.to_csv(hf_path, index=False)

    result = build_delta_dataset(
        lf_csv=lf_path,
        hf_csv=hf_path,
        pair_keys=["geometry_id", "alpha_deg", "velocity_mps"],
        targets=["cl", "cd", "cm"],
        output_dir=tmp_path / "delta",
    )

    assert result.n_paired_rows == 2
    assert result.n_unmatched_lf_rows == 1
    assert result.n_unmatched_hf_rows == 1
    assert result.delta_dataset_csv.exists()
    assert result.report_json.exists()

    out = pd.read_csv(result.delta_dataset_csv)
    assert list(out["geometry_id"]) == ["g1", "g2"]
    assert "c1_m" in out.columns
    assert "lf__cl" in out.columns
    assert "hf__cl" in out.columns
    assert "delta__cl" in out.columns
    assert pytest.approx(float(out.loc[out["geometry_id"] == "g1", "delta__cl"].iloc[0])) == 0.01
    assert pytest.approx(float(out.loc[out["geometry_id"] == "g2", "delta__cm"].iloc[0])) == 0.01

    report = json.loads(result.report_json.read_text(encoding="utf-8"))
    assert report["counts"]["paired_rows"] == 2
    assert report["columns"]["delta_target_columns"] == ["delta__cl", "delta__cd", "delta__cm"]
    assert "lf_csv_sha256" in report["fingerprints"]


def test_build_delta_dataset_rejects_duplicate_pair_keys(tmp_path: Path) -> None:
    lf = pd.DataFrame({
        "geometry_id": ["g1", "g1"],
        "alpha_deg": [0.0, 0.0],
        "cl": [0.1, 0.2],
    })
    hf = pd.DataFrame({
        "geometry_id": ["g1"],
        "alpha_deg": [0.0],
        "cl": [0.15],
    })
    lf_path = tmp_path / "lf.csv"
    hf_path = tmp_path / "hf.csv"
    lf.to_csv(lf_path, index=False)
    hf.to_csv(hf_path, index=False)

    with pytest.raises(ValueError, match="duplicate rows"):
        build_delta_dataset(
            lf_csv=lf_path,
            hf_csv=hf_path,
            pair_keys=["geometry_id", "alpha_deg"],
            targets=["cl"],
            output_dir=tmp_path / "delta",
        )
