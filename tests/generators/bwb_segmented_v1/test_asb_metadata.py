from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import build_aerosandbox_geometry
from aeris.generators.bwb_segmented_v1.sections import SectionGeometryResult, SectionRecord
from aeris.generators.bwb_segmented_v1.params import BWBGeneratorConfig, GeneratorConfig, ControlsConfig, PlanformBoundsConfig, SectionBoundsConfig, PlotOutputsConfig, RangeConfig

def make_config():
    from tests.generators.bwb_segmented_v1.test_params import make_raw_config
    from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config

    return build_bwb_generator_config(make_raw_config())

def test_asb_metadata_contains_mac():
    section_geometry = SectionGeometryResult(
        sections=[
            SectionRecord(0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, "naca4412"),
            SectionRecord(1, 0.2, 0.5, 0.0, 0.8, 0.0, 0.0, "naca4412"),
            SectionRecord(2, 0.4, 1.0, 0.0, 0.5, 0.0, 0.0, "naca4412"),
        ],
        twist_b0_deg=0.0,
        twist_b1_deg=0.0,
        twist_b2_deg=0.0,
        twist_b3_deg=0.0,
        dihedral_b0_deg=0.0,
        dihedral_b1_deg=0.0,
        dihedral_b2_deg=0.0,
        dihedral_b3_deg=0.0,
        twist_boundaries_deg=None,
        dihedral_boundaries_deg=None,
        twist_array_deg=None,
        dihedral_array_deg=None,
        group_boundary_y=None,
    )

    result = build_aerosandbox_geometry(section_geometry, make_config())
    assert result.reference_values["mean_aerodynamic_chord_m"] > 0.0