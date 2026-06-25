from pathlib import Path

from aeris.common.config import load_yaml_config
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator
from aeris.generators.bwb_segmented_v1.vsp_export import (
    build_bwb_cad_source,
    export_solid_step_from_section_geometry,
)


def test_solid_step_export_returns_result_object(tmp_path: Path) -> None:
    raw = load_yaml_config(Path("configs/geometry/baseline_bwb_25.yaml"))
    generator_id, generator_config = resolve_generator_and_config(raw)
    assert generator_id == "bwb_segmented_v1"

    generator = get_geometry_generator(generator_id)
    seed = generator_config.generator.seed
    sample = generator.sample_one(generator_config, seed=seed)

    source = build_bwb_cad_source(
        config=generator_config,
        sample=sample,
        output_dir=tmp_path,
    )

    result = export_solid_step_from_section_geometry(
        section_geometry=source.section_geometry,
        config=generator_config,
        step_path=tmp_path / "geometry.step",
        stdout_path=tmp_path / "solid_stdout.txt",
        stderr_path=tmp_path / "solid_stderr.txt",
        symmetric=True,
    )

    assert result is not None
    assert result.attempted is True
    assert result.backend == "solid"
    assert result.step_exists is True
    assert result.is_solid is True
    assert result.succeeded is True
    assert result.step_path.exists()

    payload = result.to_dict()
    assert payload["succeeded"] is True
    assert payload["solid_count"] == 1
    assert payload["face_count"] > 0
    assert payload["volume_m3"] is not None
    assert payload["volume_m3"] > 0.0
    assert payload["bbox_y_m"] is not None
    assert 3.0 < payload["bbox_y_m"] < 3.4


def test_solid_step_export_paper1_doe_single_airfoil_is_one_solid(tmp_path: Path) -> None:
    """Paper1 DoE geometry should export as one fused volumetric solid.

    Regression guard for the root-plate / two-solid failure mode seen in FreeCAD.
    This intentionally removes station_airfoils to prove the issue is not caused
    by mixed airfoil stations.
    """
    raw = load_yaml_config(Path("configs/geometry/paper1_bwb_doe_naca_stations.yaml"))
    raw["geometry"]["section_bounds"].pop("station_airfoils", None)
    raw["geometry"]["section_bounds"]["airfoil_name"] = "naca4412"

    generator_id, generator_config = resolve_generator_and_config(raw)
    assert generator_id == "bwb_segmented_v1"

    generator = get_geometry_generator(generator_id)
    sample = generator.sample_one(generator_config, seed=generator_config.generator.seed)

    source = build_bwb_cad_source(
        config=generator_config,
        sample=sample,
        output_dir=tmp_path / "paper1_source",
    )

    result = export_solid_step_from_section_geometry(
        section_geometry=source.section_geometry,
        config=generator_config,
        step_path=tmp_path / "paper1_geometry.step",
        stdout_path=tmp_path / "paper1_solid_stdout.txt",
        stderr_path=tmp_path / "paper1_solid_stderr.txt",
        symmetric=True,
    )

    assert result.succeeded is True, result.skipped_reason
    payload = result.to_dict()
    assert payload["solid_count"] == 1
    assert payload["face_count"] > 0
    assert payload["volume_m3"] is not None and payload["volume_m3"] > 0.0
    assert payload["bbox_y_m"] is not None
    assert 3.0 < payload["bbox_y_m"] < 5.0

    stdout = (tmp_path / "paper1_solid_stdout.txt").read_text(encoding="utf-8")
    assert "export_cadquery_geometry_mike" in stdout
    assert "full_span" in stdout

