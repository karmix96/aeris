from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from aeris.common.config import load_yaml_config
from aeris.generators.bwb_segmented_v1.generator import BwbSegmentedV1Generator
from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config
from aeris.generators.bwb_segmented_v1.pygeo_adapter import (
    StationDefinition,
    pygeo_frame_inputs,
)
from aeris.generators.bwb_segmented_v1.services import (
    compare_backend_reference_values,
    generate_geometry_case_from_sample,
)
from aeris.generators.bwb_segmented_v1.validation import (
    validate_bwb_generator_config,
)

PYGEO_CONFIG = Path("configs/geometry/paper1_bwb_pygeo.yaml")
BASELINE_CONFIG = Path("configs/geometry/baseline_bwb_25.yaml")


def test_existing_configs_keep_pygeo_disabled() -> None:
    config = build_bwb_generator_config(load_yaml_config(BASELINE_CONFIG))
    assert config.pygeo.enabled is False


def test_pygeo_example_parses_as_independent_backend() -> None:
    config = build_bwb_generator_config(load_yaml_config(PYGEO_CONFIG))
    validate_bwb_generator_config(config)

    assert config.pygeo.enabled is True
    assert config.outputs.build_aerosandbox is False
    assert config.pygeo.frame_mode == "aeris_frame"
    assert config.pygeo.physical_cad.enabled is True
    assert config.section_bounds.dihedral_root_deg == 0.0
    assert config.section_bounds.dihedral_b1_deg.min == 0.0
    assert config.section_bounds.dihedral_b1_deg.max == 0.0


def test_pygeo_rejects_nonflat_root_panel() -> None:
    raw = load_yaml_config(PYGEO_CONFIG)
    raw["geometry"]["section_bounds"]["dihedral_b1_deg"]["max"] = 0.1
    config = build_bwb_generator_config(raw)

    with pytest.raises(ValueError, match="flat_root_panel"):
        validate_bwb_generator_config(config)


def test_backend_comparison_is_direct_and_numerical() -> None:
    comparison = compare_backend_reference_values(
        {
            "span_m": 3.2,
            "area_m2": 2.0,
            "aspect_ratio": 5.12,
        },
        {
            "span_m": 3.21,
            "area_m2": 2.02,
            "aspect_ratio": 5.10,
        },
    )

    assert comparison["geometry_translation_used"] is False
    assert comparison["metrics"]["span_m"]["delta_pygeo_minus_aerosandbox"] == (pytest.approx(0.01))
    assert comparison["metrics"]["area_m2"]["relative_delta_percent"] == (pytest.approx(1.0))


def test_aeris_frame_alias_reconstructs_without_aerosandbox_object() -> None:
    stations = [
        StationDefinition(
            index=0,
            x_le_m=0.0,
            y_m=0.0,
            z_le_m=0.0,
            chord_m=1.0,
            twist_deg=0.0,
            dihedral_deg=0.0,
            airfoil_name="root",
            airfoil_path=Path("root.dat"),
        ),
        StationDefinition(
            index=1,
            x_le_m=0.2,
            y_m=0.5,
            z_le_m=0.0,
            chord_m=0.7,
            twist_deg=-2.0,
            dihedral_deg=0.0,
            airfoil_name="tip",
            airfoil_path=Path("tip.dat"),
        ),
    ]

    rot_x, rot_y, rot_z, thickness, error = pygeo_frame_inputs(stations, "asb_frame")

    assert len(rot_x) == len(rot_y) == len(rot_z) == len(thickness) == 2
    assert error < 1.0e-12


@dataclass
class _DummyControl:
    def to_dict(self) -> dict:
        return {"enabled": True, "name": "elevon"}


@dataclass
class _DummyPyGeoResult:
    output_dir: Path
    geometry_id: str = "dummy_pygeo"

    def __post_init__(self) -> None:
        self.metrics = {
            "aspect_ratio_xy": 4.5,
            "n_extracted_sections": 25,
            "volume_m3": 0.2,
            "wetted_area_m2": 4.0,
        }
        self.reference_values = {
            "span_m": 3.2,
            "area_m2": 2.2,
            "aspect_ratio": 4.5,
        }
        self.artifacts = {"pygeo_manifest": str(self.output_dir / "pygeo_manifest.json")}
        self.control = _DummyControl()
        self.stations = (object(), object())
        self.extracted = tuple(object() for _ in range(25))

    def summary_dict(self) -> dict:
        return {
            "enabled": True,
            "geometry_id": "dummy_pygeo",
            "reference_values": self.reference_values,
            "metrics": self.metrics,
        }


def test_services_wires_pygeo_without_requiring_aerosandbox(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    generator = BwbSegmentedV1Generator()
    config = generator.build_config(load_yaml_config(PYGEO_CONFIG))
    sample = generator.sample_one(config, seed=1001)
    calls: list[dict] = []

    def fake_build_pygeo_geometry(**kwargs):
        calls.append(kwargs)
        output = Path(kwargs["output_dir"])
        output.mkdir(parents=True)
        return _DummyPyGeoResult(output)

    monkeypatch.setattr(
        "aeris.generators.bwb_segmented_v1.services.build_pygeo_geometry",
        fake_build_pygeo_geometry,
    )

    result = generate_geometry_case_from_sample(
        config=config,
        sample=sample,
        output_dir=tmp_path / "geometry",
        save_plot=False,
    )

    assert len(calls) == 1
    assert result.aerosandbox_result is None
    assert result.pygeo_result is not None
    assert result.summary["realization_backends"]["pygeo"]["enabled"] is True
    assert result.summary["realization_backends"]["aerosandbox"]["enabled"] is False
    assert result.summary["reference_values"]["aspect_ratio"] == 4.5
    assert result.artifact_paths.pygeo_dir == tmp_path / "geometry" / "pygeo"
