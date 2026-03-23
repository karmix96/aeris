"""Tests for geometry case orchestration in bwb_segmented_v1.services."""

import numpy as np

from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config
from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design
from aeris.generators.bwb_segmented_v1.services import generate_geometry_case_from_sample


def make_config():
    from tests.generators.bwb_segmented_v1.test_params import make_raw_config
    return build_bwb_generator_config(make_raw_config())


def test_generate_geometry_case_without_plot(tmp_path):
    config = make_config()
    rng = np.random.default_rng(10)
    sample = sample_bwb_design(config, rng)

    result = generate_geometry_case_from_sample(
        config=config,
        sample=sample,
        output_dir=tmp_path,
        save_plot=False,
        build_aerosandbox=False,
    )

    assert result.aerosandbox_result is None
    assert result.artifact_paths.plot_path is None
    assert result.artifact_paths.summary_path.exists()
    assert result.artifact_paths.control_points_path.exists()
    assert result.artifact_paths.planform_sections_path.exists()
    assert result.artifact_paths.section_3d_path.exists()


def test_generate_geometry_case_with_aerosandbox(tmp_path):
    config = make_config()
    rng = np.random.default_rng(11)
    sample = sample_bwb_design(config, rng)

    result = generate_geometry_case_from_sample(
        config=config,
        sample=sample,
        output_dir=tmp_path,
        save_plot=False,
        build_aerosandbox=True,
    )

    assert result.aerosandbox_result is not None
    assert result.airplane is not None
    assert result.wing is not None