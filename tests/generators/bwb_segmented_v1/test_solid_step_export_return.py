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
    assert payload["solid_count"] >= 1
    assert payload["face_count"] > 0
    assert payload["volume_m3"] is not None
    assert payload["volume_m3"] > 0.0
    assert payload["bbox_y_m"] is not None
    assert 3.0 < payload["bbox_y_m"] < 3.4
