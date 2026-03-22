from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import build_aerosandbox_geometry
from aeris.generators.bwb_segmented_v1.sections import SectionGeometryResult, SectionRecord
from aeris.generators.bwb_segmented_v1.params import (
    BWBGeneratorConfig,
    GeneratorConfig,
    ControlsConfig,
    PlanformBoundsConfig,
    SectionBoundsConfig,
    PlotOutputsConfig,
    RangeConfig,
)


def make_config():
    return BWBGeneratorConfig(
        name="test_case",
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
            c1_m=RangeConfig(1.6, 1.6),
            c2_ratio=RangeConfig(0.55, 0.55),
            c3_ratio=RangeConfig(0.38, 0.38),
            c4_ratio=RangeConfig(0.12, 0.12),
            b_total_m=RangeConfig(1.6, 1.6),
            b3_ratio=RangeConfig(0.5, 0.5),
            split_ratio=RangeConfig(0.45, 0.45),
            sw1_deg=RangeConfig(40.0, 40.0),
            sw2_deg=RangeConfig(25.0, 25.0),
            sw3_deg=RangeConfig(10.0, 10.0),
        ),
        section_bounds=SectionBoundsConfig(
            airfoil_name="naca4412",
            dihedral_root_deg=0.0,
            twist_b0_deg=RangeConfig(0.0, 0.0),
            twist_b1_deg=RangeConfig(0.0, 0.0),
            twist_b2_deg=RangeConfig(0.0, 0.0),
            twist_b3_deg=RangeConfig(0.0, 0.0),
            dihedral_b1_deg=RangeConfig(0.0, 0.0),
            dihedral_b2_deg=RangeConfig(0.0, 0.0),
            dihedral_b3_deg=RangeConfig(0.0, 0.0),
        ),
        outputs=PlotOutputsConfig(save_plot=False, build_aerosandbox=True),
    )


def test_build_aerosandbox_geometry_smoke():
    section_geometry = SectionGeometryResult(
        sections=[
            SectionRecord(0, 0.0, 0.0, 0.0, 1.6, 0.0, 0.0, "naca4412"),
            SectionRecord(1, 0.2, 0.4, 0.0, 1.0, 0.0, 0.0, "naca4412"),
            SectionRecord(2, 0.5, 0.8, 0.0, 0.6, 0.0, 0.0, "naca4412"),
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

    assert result.n_xsecs == 3
    assert result.reference_values["mean_aerodynamic_chord_m"] > 0.0
    assert result.reference_values["span_m"] > 0.0
    assert result.reference_values["area_m2"] > 0.0