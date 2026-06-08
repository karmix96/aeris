from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.dataset.flyability_ml_dataset import build_flyability_ml_dataset


def _write_source_dataset(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for geom, c1, cm0, cmde, trim, flyable in [
        ("geom_00001", 1.2, -0.20, -0.50, -22.0, True),
        ("geom_00002", 1.4, -0.40, -0.45, -31.0, False),
    ]:
        for de in [-5.0, 0.0, 5.0]:
            rows.append(
                {
                    "geometry_id": geom,
                    "alpha_deg": 0.0,
                    "beta_deg": 0.0,
                    "velocity_mps": 28.0,
                    "altitude_m": 1500.0,
                    "p_rad_s": 0.0,
                    "q_rad_s": 0.0,
                    "r_rad_s": 0.0,
                    "delta_e_sym_deg": de,
                    "control_input_deg": de,
                    "c1_m": c1,
                    "b_total_m": 1.6,
                    "sw1_deg": -40.0,
                    "cl": 0.3,
                    "cd": 0.01,
                    "cm": cm0 + cmde * de * 3.141592653589793 / 180.0,
                }
            )
    curated = root / "curated_aero_dataset.csv"
    pd.DataFrame(rows).to_csv(curated, index=False)

    labels = pd.DataFrame(
        [
            {
                "geometry_id": "geom_00001",
                "alpha_deg": 0.0,
                "beta_deg": 0.0,
                "velocity_mps": 28.0,
                "altitude_m": 1500.0,
                "p_rad_s": 0.0,
                "q_rad_s": 0.0,
                "r_rad_s": 0.0,
                "status": "computed",
                "Cm_delta_e_per_rad": -0.50,
                "trim_delta_e_required_deg": -22.0,
                "trim_delta_e_margin_to_limit_deg": 3.0,
                "trim_delta_e_feasible": True,
                "longitudinal_basic_flyable": True,
                "red_flag": False,
                "label_failure_stage": "none",
            },
            {
                "geometry_id": "geom_00002",
                "alpha_deg": 0.0,
                "beta_deg": 0.0,
                "velocity_mps": 28.0,
                "altitude_m": 1500.0,
                "p_rad_s": 0.0,
                "q_rad_s": 0.0,
                "r_rad_s": 0.0,
                "status": "computed",
                "Cm_delta_e_per_rad": -0.45,
                "trim_delta_e_required_deg": -31.0,
                "trim_delta_e_margin_to_limit_deg": -6.0,
                "trim_delta_e_feasible": False,
                "longitudinal_basic_flyable": False,
                "red_flag": True,
                "red_flag_reasons": "trim_delta_e_required_exceeds_limit",
                "trim_failure_reason": "trim_delta_e_required_exceeds_limit",
                "label_failure_stage": "trim",
            },
        ]
    )
    labels.to_csv(root / "flyability_labels.csv", index=False)

    (root / "promotion_manifest.json").write_text(
        json.dumps(
            {
                "promotion_forced": False,
                "promotion_ready_at_time_of_promotion": True,
                "artifacts": {"curated_aero_dataset_csv": str(curated.resolve())},
            }
        ),
        encoding="utf-8",
    )


def test_build_flyability_ml_dataset_writes_promoted_like_output(tmp_path: Path) -> None:
    source = tmp_path / "source_ds"
    output = tmp_path / "flyability_ml"
    _write_source_dataset(source)

    report = build_flyability_ml_dataset(dataset_root=source, output_dir=output)

    assert report["status"] == "completed"
    assert report["row_counts"]["joined_ml_rows"] == 2
    assert (output / "curated_aero_dataset.csv").exists()
    assert (output / "flyability_ml_dataset.csv").exists()
    assert (output / "promotion_manifest.json").exists()

    df = pd.read_csv(output / "curated_aero_dataset.csv")
    assert len(df) == 2
    assert "c1_m" in df.columns
    assert "trim_delta_e_required_deg" in df.columns
    assert "longitudinal_basic_flyable_int" in df.columns
    assert set(df["longitudinal_basic_flyable_int"].dropna().astype(int)) == {0, 1}
