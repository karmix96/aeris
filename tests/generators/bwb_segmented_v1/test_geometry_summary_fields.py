from aeris.generators.bwb_segmented_v1.export import build_geometry_summary
from tests.generators.bwb_segmented_v1.test_export_summary_enriched import (
    make_aerosandbox_result,
    make_config,
    make_planform,
    make_section_geometry,
)


def test_geometry_summary_contains_reference_values():
    summary = build_geometry_summary(
        config=make_config(),
        planform=make_planform(),
        section_geometry=make_section_geometry(),
        aerosandbox_result=make_aerosandbox_result(),
        artifact_paths={"summary_path": "dummy.json"},
    )

    assert "reference_values" in summary
    assert summary["reference_values"]["mean_aerodynamic_chord_m"] > 0.0