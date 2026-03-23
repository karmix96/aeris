from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import build_aerosandbox_geometry
from aeris.generators.bwb_segmented_v1.sections import SectionGeometryResult, SectionRecord
from aeris.generators.bwb_segmented_v1.params import BWBGeneratorConfig, GeneratorConfig, ControlsConfig, PlanformBoundsConfig, SectionBoundsConfig, PlotOutputsConfig, RangeConfig

def make_config():
    return BWBGeneratorConfig(
        name="test",
        generator=GeneratorConfig(family="bwb_segmented", version="v1", seed=1),
        controls=ControlsConfig(
            n_points=10,
            n_spline_inboard=10,
            n_spline_outboard=5,
            curvature_strength=1.0,
            spline_split_ratio=0.55,
            segment_length_variation=0.0,
            sweep_variation=0.0,
        ),
        planform_bounds=PlanformBoundsConfig(
            c1_m=RangeConfig(1, 1),
            c2_ratio=RangeConfig(0.5, 0.5),
            c3_ratio=RangeConfig(0.4, 0.4),
            c4_ratio=RangeConfig(0.2, 0.2),
            b_total_m=RangeConfig(2, 2),
            b3_ratio=RangeConfig(0.5, 0.5),
            split_ratio=RangeConfig(0.5, 0.5),
            sw1_deg=RangeConfig(20, 20),
            sw2_deg=RangeConfig(10, 10),
            sw3_deg=RangeConfig(5, 5),
        ),
        section_bounds=SectionBoundsConfig(
            airfoil_name="naca4412",
            dihedral_root_deg=0.0,
            twist_b0_deg=RangeConfig(0, 0),
            twist_b1_deg=RangeConfig(0, 0),
            twist_b2_deg=RangeConfig(0, 0),
            twist_b3_deg=RangeConfig(0, 0),
            dihedral_b1_deg=RangeConfig(0, 0),
            dihedral_b2_deg=RangeConfig(0, 0),
            dihedral_b3_deg=RangeConfig(0, 0),
        ),
        outputs=PlotOutputsConfig(),
    )

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