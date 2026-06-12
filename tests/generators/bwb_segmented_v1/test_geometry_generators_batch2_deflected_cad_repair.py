from __future__ import annotations

import json
from pathlib import Path

import pytest

from aeris.generators.bwb_segmented_v1.deflected_cad import export_bwb_physical_deflected_cad


def _cfg(name: str = "baseline_bwb_25.yaml") -> Path:
    return Path("configs/geometry") / name


def test_deflected_cad_rejects_negative_hinge_gap(tmp_path: Path):
    with pytest.raises(ValueError, match="hinge_gap_fraction"):
        export_bwb_physical_deflected_cad(
            config_path=_cfg(),
            output_dir=tmp_path / "bad_gap",
            formats="vspscript",
            hinge_gap_fraction=-1e-3,
        )


def test_deflected_cad_rejects_nonpositive_boundary_epsilon(tmp_path: Path):
    with pytest.raises(ValueError, match="boundary_epsilon_fraction"):
        export_bwb_physical_deflected_cad(
            config_path=_cfg(),
            output_dir=tmp_path / "bad_eps",
            formats="vspscript",
            boundary_epsilon_fraction=0.0,
        )


def test_deflected_cad_writes_running_then_final_manifest(tmp_path: Path):
    out = tmp_path / "phys"
    manifest = export_bwb_physical_deflected_cad(
        config_path=_cfg(),
        output_dir=out,
        formats="vspscript",
        delta_e_sym_deg=5.0,
    )
    manifest_path = out / "cad_exports" / "physical_deflected_geometry_export_manifest.json"
    assert manifest_path.exists()
    saved = json.loads(manifest_path.read_text())
    assert saved["status"] == manifest["status"] == "success"
    assert saved["artifacts"]["step_bodies_report"] is None
    assert "created_at_utc" in saved
    assert "completed_at_utc" in saved
