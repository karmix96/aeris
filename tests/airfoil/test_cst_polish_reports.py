from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aeris.airfoil.cst_reporting import polish_cst_library_outputs


def test_polish_cst_library_outputs_adds_aliases_and_report(tmp_path: Path) -> None:
    root = tmp_path / "cst_lib"
    (root / "coords").mkdir(parents=True)
    (root / "dat").mkdir()
    (root / "cst_json").mkdir()

    aid = "abc123"
    (root / "coords" / f"{aid}.npz").write_bytes(b"fake")
    (root / "dat" / "a.dat").write_text("a\n0 0\n1 0\n", encoding="utf-8")
    (root / "cst_json" / f"{aid}.json").write_text("{}", encoding="utf-8")

    pd.DataFrame([
        {
            "airfoil_id": aid,
            "name": "a",
            "source_file": "a.dat",
            "family": "cst",
            "cst_validation_valid": True,
            "cst_json": str(root / "cst_json" / f"{aid}.json"),
            "dat_path": str(root / "dat" / "a.dat"),
            "t_c": 0.12,
            "camber_max": 0.02,
            "le_radius": 0.01,
            "te_angle_deg": 8.0,
            "cst_u0": 0.1,
            "cst_l0": -0.1,
        }
    ]).to_csv(root / "airfoil_inventory.csv", index=False)

    manifest = {
        "schema_version": "airfoil_cst_library_v1",
        "generator_id": "cst_airfoil_v1",
        "n_airfoils_requested": 1,
        "n_airfoils_generated": 1,
        "order": 8,
        "n1": 0.5,
        "n2": 1.0,
        "dz_te": 0.0,
        "n_per_surface": 121,
    }
    (root / "cst_airfoil_library_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    out = polish_cst_library_outputs(root)

    inv = pd.read_csv(root / "airfoil_inventory.csv")
    assert inv.loc[0, "airfoil_name"] == "a"
    assert inv.loc[0, "cst_json_path"].endswith("abc123.json")
    assert inv.loc[0, "coords_npz_path"].endswith("coords/abc123.npz")

    assert out["generated_count"] == 1
    assert out["requested_count"] == 1
    assert "inventory_schema" in out
    assert (root / "library_report.json").exists()
    report = json.loads((root / "library_report.json").read_text(encoding="utf-8"))
    assert report["generated_count"] == 1
    assert "cst_u0" in report["cst_coefficient_columns"]
