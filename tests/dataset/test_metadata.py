from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from aeris.dataset.metadata import (
    build_failure_row,
    build_metadata_row,
    failure_fieldnames,
    metadata_fieldnames,
    _sample_to_dict,
)


@dataclass
class DummySample:
    c1_m: float
    c2_ratio: float
    c3_ratio: float
    c4_ratio: float
    b_total_m: float
    b3_ratio: float
    split_ratio: float
    sw1_deg: float
    sw2_deg: float
    sw3_deg: float
    twist_b0_deg: float
    twist_b1_deg: float
    twist_b2_deg: float
    twist_b3_deg: float
    dihedral_b1_deg: float
    dihedral_b2_deg: float
    dihedral_b3_deg: float


class DummySampleWithToDict:
    def to_dict(self) -> dict[str, float]:
        return {
            "c1_m": 1.0,
            "c2_ratio": 0.5,
            "c3_ratio": 0.4,
            "c4_ratio": 0.2,
            "b_total_m": 3.0,
            "b3_ratio": 0.6,
            "split_ratio": 0.35,
            "sw1_deg": 10.0,
            "sw2_deg": 5.0,
            "sw3_deg": 2.0,
            "twist_b0_deg": 1.0,
            "twist_b1_deg": 0.5,
            "twist_b2_deg": 0.0,
            "twist_b3_deg": -1.0,
            "dihedral_b1_deg": 3.0,
            "dihedral_b2_deg": 2.0,
            "dihedral_b3_deg": 1.0,
        }


def _make_config() -> SimpleNamespace:
    return SimpleNamespace(
        name="baseline_cfg",
        generator=SimpleNamespace(family="bwb_segmented", version="v1"),
        section_bounds=SimpleNamespace(airfoil_name="naca0012"),
    )


def _make_sample() -> DummySample:
    return DummySample(
        c1_m=1.0,
        c2_ratio=0.5,
        c3_ratio=0.4,
        c4_ratio=0.2,
        b_total_m=3.0,
        b3_ratio=0.6,
        split_ratio=0.35,
        sw1_deg=10.0,
        sw2_deg=5.0,
        sw3_deg=2.0,
        twist_b0_deg=1.0,
        twist_b1_deg=0.5,
        twist_b2_deg=0.0,
        twist_b3_deg=-1.0,
        dihedral_b1_deg=3.0,
        dihedral_b2_deg=2.0,
        dihedral_b3_deg=1.0,
    )


def _make_result(sample) -> SimpleNamespace:
    return SimpleNamespace(
        sample=sample,
        section_geometry=SimpleNamespace(
            twist_array_deg=[1.0, 0.5, 0.0, -1.0],
            dihedral_array_deg=[3.0, 2.0, 1.0],
        ),
        planform=SimpleNamespace(
            semi_span_m=1.5,
            full_span_m=3.0,
            approx_area_m2=1.2,
            approx_aspect_ratio=7.5,
            num_sections=4,
        ),
        aerosandbox_result=SimpleNamespace(
            aspect_ratio=7.6,
            n_xsecs=4,
        ),
        artifact_paths=SimpleNamespace(
            summary_path=Path("/tmp/summary.json"),
            control_points_path=Path("/tmp/control_points.csv"),
            planform_sections_path=Path("/tmp/planform_sections.csv"),
            section_3d_path=Path("/tmp/section_3d.csv"),
            plot_path=Path("/tmp/plot.png"),
        ),
    )


def test_sample_to_dict_supports_dataclass() -> None:
    sample = _make_sample()
    result = _sample_to_dict(sample)

    assert result["c1_m"] == 1.0
    assert result["dihedral_b3_deg"] == 1.0


def test_sample_to_dict_supports_to_dict() -> None:
    sample = DummySampleWithToDict()
    result = _sample_to_dict(sample)

    assert result["c1_m"] == 1.0
    assert result["sw3_deg"] == 2.0


def test_sample_to_dict_supports_plain_dict() -> None:
    sample = {"c1_m": 1.0, "c2_ratio": 0.5}
    result = _sample_to_dict(sample)

    assert result == sample


def test_sample_to_dict_rejects_unsupported_type() -> None:
    with pytest.raises(TypeError, match="Unsupported sample type"):
        _sample_to_dict(object())


def test_build_metadata_row_matches_schema() -> None:
    config = _make_config()
    sample = _make_sample()
    result = _make_result(sample)

    row = build_metadata_row(
        dataset_name="ds1",
        geometry_id="geom_00001",
        case_index=1,
        sampler_id="lhs_v1",
        sampler_seed=42,
        realization_seed=None,
        generator_id="bwb_segmented_v1",
        config=config,
        result=result,
        geometry_dir=Path("/tmp/geom_00001"),
    )

    assert set(row.keys()) == set(metadata_fieldnames())
    assert row["geometry_id"] == "geom_00001"
    assert row["generator_id"] == "bwb_segmented_v1"
    assert row["twist_min_deg"] == -1.0
    assert row["twist_max_deg"] == 1.0
    assert row["dihedral_mean_deg"] == pytest.approx(2.0)
    assert row["aspect_ratio_aerosandbox"] == 7.6
    assert row["plot_path"] == "/tmp/plot.png"


def test_build_metadata_row_handles_missing_aerosandbox_result() -> None:
    config = _make_config()
    sample = _make_sample()
    result = _make_result(sample)
    result.aerosandbox_result = None

    row = build_metadata_row(
        dataset_name="ds1",
        geometry_id="geom_00001",
        case_index=1,
        sampler_id="lhs_v1",
        sampler_seed=42,
        realization_seed=None,
        generator_id="bwb_segmented_v1",
        config=config,
        result=result,
        geometry_dir=Path("/tmp/geom_00001"),
    )

    assert row["aspect_ratio_aerosandbox"] is None
    assert row["n_xsecs_aerosandbox"] is None


def test_build_metadata_row_rejects_empty_twist_array() -> None:
    config = _make_config()
    sample = _make_sample()
    result = _make_result(sample)
    result.section_geometry.twist_array_deg = []

    with pytest.raises(ValueError, match="twist"):
        build_metadata_row(
            dataset_name="ds1",
            geometry_id="geom_00001",
            case_index=1,
            sampler_id="lhs_v1",
            sampler_seed=42,
            realization_seed=None,
            generator_id="bwb_segmented_v1",
            config=config,
            result=result,
            geometry_dir=Path("/tmp/geom_00001"),
        )


def test_build_metadata_row_rejects_empty_dihedral_array() -> None:
    config = _make_config()
    sample = _make_sample()
    result = _make_result(sample)
    result.section_geometry.dihedral_array_deg = []

    with pytest.raises(ValueError, match="dihedral"):
        build_metadata_row(
            dataset_name="ds1",
            geometry_id="geom_00001",
            case_index=1,
            sampler_id="lhs_v1",
            sampler_seed=42,
            realization_seed=None,
            generator_id="bwb_segmented_v1",
            config=config,
            result=result,
            geometry_dir=Path("/tmp/geom_00001"),
        )


def test_build_failure_row_matches_schema() -> None:
    config = _make_config()

    row = build_failure_row(
        dataset_name="ds1",
        geometry_id="geom_00099",
        case_index=99,
        sampler_id="lhs_v1",
        sampler_seed=42,
        realization_seed=None,
        generator_id="bwb_segmented_v1",
        config=config,
        exc=RuntimeError("boom"),
    )

    assert set(row.keys()) == set(failure_fieldnames())
    assert row["generator_id"] == "bwb_segmented_v1"
    assert row["error_type"] == "RuntimeError"
    assert row["error_message"] == "boom"