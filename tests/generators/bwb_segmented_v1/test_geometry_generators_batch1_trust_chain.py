from __future__ import annotations

import json
from pathlib import Path

import pytest

from aeris.common.config import load_yaml_config
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator
from aeris.geometry.visualization import visualize_geometry_from_config
from aeris.generators.bwb_segmented_v1.deflected_cad import export_bwb_physical_deflected_cad
from aeris.generators.bwb_segmented_v1 import vsp_export


CFG_DIR = Path("configs/geometry")


def _load_cfg(name: str):
    raw = load_yaml_config(CFG_DIR / name)
    gid, cfg = resolve_generator_and_config(raw)
    return gid, cfg


def test_active_design_variable_names_distinguish_fixed_and_sampled_elevons() -> None:
    _gid, baseline = _load_cfg("baseline_bwb_25.yaml")
    _gid, v3 = _load_cfg("bwb_training_v3.yaml")

    assert len(baseline.sample_field_names()) == 20
    assert len(baseline.active_design_variable_names()) == 17
    assert len(baseline.design_variable_names()) == 17
    assert "elevon_start_frac" not in baseline.active_design_variable_names()

    assert len(v3.sample_field_names()) == 20
    assert len(v3.active_design_variable_names()) == 20
    assert len(v3.design_variable_names()) == 20
    assert "elevon_start_frac" in v3.active_design_variable_names()


def test_sample_one_without_seed_uses_config_seed() -> None:
    gid, cfg = _load_cfg("baseline_bwb_25.yaml")
    gen = get_geometry_generator(gid)

    a = gen.sample_one(cfg, seed=None).to_dict()
    b = gen.sample_one(cfg, seed=None).to_dict()
    c = gen.sample_one(cfg, seed=cfg.generator.seed).to_dict()

    assert a == b == c


def test_physical_deflected_cad_uses_sampled_v3_elevon_geometry(tmp_path: Path) -> None:
    manifest = export_bwb_physical_deflected_cad(
        config_path=CFG_DIR / "bwb_training_v3.yaml",
        output_dir=tmp_path / "deflected_v3",
        formats="vspscript",
        delta_e_sym_deg=10.0,
        delta_a_diff_deg=0.0,
        save_preview=False,
        draw_3d=False,
    )

    sample = manifest["generator"]["design_sample"]
    controls = manifest["physical_controls"]

    assert controls["geometry_source"] == "sampled_elevon_geometry"
    assert controls["start_frac"] == sample["elevon_start_frac"]
    assert controls["end_frac"] == sample["elevon_end_frac"]
    assert controls["hinge_point"] == sample["elevon_hinge_frac"]
    assert controls["matches_design_sample"] == {
        "start_frac": True,
        "end_frac": True,
        "hinge_point": True,
    }


def test_physical_deflected_cad_rejects_negative_boundary_epsilon(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="boundary_epsilon_fraction must be > 0"):
        export_bwb_physical_deflected_cad(
            config_path=CFG_DIR / "baseline_bwb_25.yaml",
            output_dir=tmp_path / "bad_epsilon",
            formats="vspscript",
            boundary_epsilon_fraction=-1.0,
        )


def test_visualization_no_save_plot_does_not_report_stale_plot(tmp_path: Path) -> None:
    out = tmp_path / "viz_reuse"

    first = visualize_geometry_from_config(
        CFG_DIR / "baseline_bwb_25.yaml",
        output_dir=out,
        save_plot=True,
        build_aerosandbox=True,
        show_plot=False,
        draw_3d=False,
    )
    assert first.plot_path is not None
    assert first.plot_path.exists()

    second = visualize_geometry_from_config(
        CFG_DIR / "baseline_bwb_25.yaml",
        output_dir=out,
        save_plot=False,
        build_aerosandbox=True,
        show_plot=False,
        draw_3d=False,
    )
    assert second.plot_path is None
    assert not (out / "plots" / "planform.png").exists()


def test_cadquery_step_export_removes_stale_step_on_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    step_path = tmp_path / "geometry.step"
    stdout_path = tmp_path / "stdout.txt"
    stderr_path = tmp_path / "stderr.txt"
    step_path.write_text("OLD_STALE_STEP", encoding="utf-8")

    class FakeAirplane:
        def mesh_body(self):
            return None

        def export_cadquery_geometry(self, _path: str):
            raise RuntimeError("forced export failure")

    monkeypatch.setattr(
        vsp_export,
        "_build_aerosandbox_airplane_from_sections",
        lambda **_kwargs: FakeAirplane(),
    )

    result = vsp_export.export_cadquery_step_from_section_geometry(
        section_geometry=object(),
        config=object(),
        step_path=step_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        symmetric=True,
    )

    assert not result.succeeded
    assert result.step_exists is False
    assert not step_path.exists()
    assert "forced export failure" in stderr_path.read_text(encoding="utf-8")
