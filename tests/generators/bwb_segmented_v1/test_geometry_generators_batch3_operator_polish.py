from pathlib import Path

import aerosandbox as asb
import pytest

from aeris.common.config import load_yaml_config
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator
from aeris.generators.bwb_segmented_v1.reconstruction_export import (
    export_reconstruction_artifacts,
)


def _load_cfg(name: str):
    raw = load_yaml_config(Path("configs/geometry") / name)
    gid, cfg = resolve_generator_and_config(raw)
    return gid, cfg


def test_geometry_summary_contains_geometry_audit(tmp_path):
    gid, cfg = _load_cfg("baseline_bwb_25.yaml")
    gen = get_geometry_generator(gid)
    sample = gen.sample_one(cfg, seed=cfg.generator.seed)
    case = gen.run_full_case(
        sample=sample,
        config=cfg,
        output_dir=tmp_path / "case",
        save_plot=False,
        build_aerosandbox=True,
    )

    audit = case.summary.get("geometry_audit")
    assert audit is not None
    assert audit["passed"] is True
    assert audit["errors"] == []
    assert "metrics" in audit
    assert audit["metrics"]["num_sections"] == len(case.section_geometry.sections)


def test_reconstruction_export_reports_airfoil_fallback_metadata(tmp_path):
    af = asb.Airfoil("dummy")
    # Simulate an unresolved/custom airfoil with no coordinates.
    af.coordinates = None
    wing = asb.Wing(
        name="W",
        symmetric=False,
        xsecs=[
            asb.WingXSec(xyz_le=[0, 0, 0], chord=1.0, twist=0.0, airfoil=af),
            asb.WingXSec(xyz_le=[0, 1, 0], chord=0.5, twist=0.0, airfoil=af),
        ],
    )
    airplane = asb.Airplane(name="A", wings=[wing])

    with pytest.warns(UserWarning):
        artifacts = export_reconstruction_artifacts(
            airplane=airplane,
            output_dir=tmp_path,
        )

    assert artifacts["airfoil_dat_count"] == 2
    assert artifacts["airfoil_fallback_count"] == 2
    assert len(artifacts["airfoil_fallbacks"]) == 2
    assert Path(artifacts["openvsp_sections_csv"]).exists()
