from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import AeroSandboxGeometryResult
from aeris.generators.bwb_segmented_v1.export import build_geometry_summary
from aeris.generators.bwb_segmented_v1.params import (
    BWBGeneratorConfig,
    ControlsConfig,
    GeneratorConfig,
    PlotOutputsConfig,
    PlanformBoundsConfig,
    RangeConfig,
    SectionBoundsConfig,
)
from aeris.generators.bwb_segmented_v1.planform import PlanformResult
from aeris.generators.bwb_segmented_v1.sections import SectionGeometryResult, SectionRecord


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
            c1_m=RangeConfig(min=1.6, max=1.6),
            c2_ratio=RangeConfig(min=0.55, max=0.55),
            c3_ratio=RangeConfig(min=0.38, max=0.38),
            c4_ratio=RangeConfig(min=0.12, max=0.12),
            b_total_m=RangeConfig(min=1.6, max=1.6),
            b3_ratio=RangeConfig(min=0.5, max=0.5),
            split_ratio=RangeConfig(min=0.45, max=0.45),
            sw1_deg=RangeConfig(min=40.0, max=40.0),
            sw2_deg=RangeConfig(min=25.0, max=25.0),
            sw3_deg=RangeConfig(min=10.0, max=10.0),
        ),
        section_bounds=SectionBoundsConfig(
            airfoil_name="naca4412",
            dihedral_root_deg=0.0,
            twist_b0_deg=RangeConfig(min=0.0, max=0.0),
            twist_b1_deg=RangeConfig(min=0.0, max=0.0),
            twist_b2_deg=RangeConfig(min=0.0, max=0.0),
            twist_b3_deg=RangeConfig(min=0.0, max=0.0),
            dihedral_b1_deg=RangeConfig(min=0.0, max=0.0),
            dihedral_b2_deg=RangeConfig(min=0.0, max=0.0),
            dihedral_b3_deg=RangeConfig(min=0.0, max=0.0),
        ),
        outputs=PlotOutputsConfig(
        save_plot=False,
        build_aerosandbox=True,
    ),
    )


def make_planform():
    import numpy as np

    return PlanformResult(
        n_points=10,
        n_spline_inboard=10,
        n_spline_outboard=5,
        split_idx=5,
        c1=1.6,
        c2=0.88,
        c3=0.608,
        c4=0.192,
        c2_ratio=0.55,
        c3_ratio=0.38,
        c4_ratio=0.12,
        b_total=1.6,
        b1=0.36,
        b2=0.44,
        b3=0.8,
        b3_ratio=0.5,
        split_ratio=0.45,
        sw1_deg=-40.0,
        sw2_deg=-25.0,
        sw3_deg=-10.0,
        N1=2,
        N2=2,
        N3=5,
        x_le=np.array([0.0, 0.1, 0.2]),
        y_le=np.array([0.0, 0.8, 1.6]),
        x_te=np.array([1.6, 1.1, 0.392]),
        y_te=np.array([0.0, 0.8, 1.6]),
        chords=np.array([1.6, 1.0, 0.192]),
        b_le=np.array([0.0, 0.8, 1.6]),
        s_rad_le=np.array([0.0, 0.1, 0.2]),
        key_indices=np.array([0, 1, 2]),
        key_chords=np.array([1.6, 1.0, 0.192]),
        group_boundary_y=np.array([0.0, 0.36, 0.8, 1.6]),
        front_y_fine=np.array([0.0, 0.8, 1.6]),
        front_x_fine=np.array([0.0, 0.1, 0.2]),
        rear_y_fine=np.array([0.0, 0.8, 1.6]),
        rear_x_fine=np.array([1.6, 1.1, 0.392]),
        front_x_mirrored=np.array([0.2, 0.1, 0.0, 0.1, 0.2]),
        front_y_mirrored=np.array([-1.6, -0.8, 0.0, 0.8, 1.6]),
        rear_x_mirrored=np.array([0.392, 1.1, 1.6, 1.1, 0.392]),
        rear_y_mirrored=np.array([-1.6, -0.8, 0.0, 0.8, 1.6]),
        num_sections=3,
        semi_span_m=1.6,
        full_span_m=3.2,
        approx_area_m2=2.18,
        approx_aspect_ratio=4.69,
    )


def make_section_geometry():
    return SectionGeometryResult(
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


def make_aerosandbox_result():
    return AeroSandboxGeometryResult(
        aspect_ratio=4.69,
        airfoil_name="naca4412",
        n_xsecs=3,
        reference_values={
            "span_m": 3.2,
            "area_m2": 2.18,
            "aspect_ratio": 4.69,
            "mean_geometric_chord_m": 0.68,
            "mean_aerodynamic_chord_m": 0.90,
            "taper_ratio": 0.12,
            "volume_m3": 0.1,
        },
        mean_angles_deg={
            "twist_deg": 0.0,
            "sweep_le_deg": -40.0,
            "sweep_c4_deg": -25.0,
            "sweep_te_deg": -10.0,
            "dihedral_c4_deg": 0.0,
        },
        aerodynamic_center={
            "x_m": 0.4,
            "y_m": 0.0,
            "z_m": 0.0,
        },
        sectional_metrics={
            "section_spans_m": [0.4, 0.4],
            "section_areas_m2": [0.5, 0.3],
            "section_ac_xyz_m": [[0.2, 0.2, 0.0], [0.4, 0.6, 0.0]],
        },
        geometry_info={
            "wing_name": "BWB",
            "n_xsecs": 3,
            "symmetric": True,
        },
        wing=None,
        airplane=None,
    )


def test_build_geometry_summary_includes_enriched_fields():
    summary = build_geometry_summary(
        config=make_config(),
        planform=make_planform(),
        section_geometry=make_section_geometry(),
        aerosandbox_result=make_aerosandbox_result(),
        artifact_paths={"summary_path": "dummy.json"},
    )

    assert "metrics" in summary
    assert "reference_values" in summary
    assert "mean_angles_deg" in summary
    assert "aerodynamic_center" in summary
    assert "sectional_metrics" in summary
    assert summary["reference_values"]["mean_aerodynamic_chord_m"] > 0.0