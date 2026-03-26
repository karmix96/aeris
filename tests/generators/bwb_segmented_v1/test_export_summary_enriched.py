from __future__ import annotations

from dataclasses import dataclass

from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import AeroSandboxGeometryResult
from aeris.generators.bwb_segmented_v1.export import build_geometry_summary
from aeris.generators.bwb_segmented_v1.params import (
    BWBGeneratorConfig,
    ControlSurfaceConfig,
    ControlSurfaceSpanwiseConfig,
    ControlSurfacesConfig,
    ControlsConfig,
    GeneratorConfig,
    PlanformBoundsConfig,
    PlotOutputsConfig,
    RangeConfig,
    SectionBoundsConfig,
)


@dataclass(frozen=True)
class DummyPlanformResult:
    c1: float = 1.6
    c2_ratio: float = 0.55
    c3_ratio: float = 0.38
    c4_ratio: float = 0.12
    c2: float = 0.88
    c3: float = 0.608
    c4: float = 0.192
    b_total: float = 1.6
    b3_ratio: float = 0.5
    b1: float = 0.36
    b2: float = 0.44
    b3: float = 0.8
    split_ratio: float = 0.45
    sw1_deg: float = 40.0
    sw2_deg: float = 25.0
    sw3_deg: float = 10.0
    N1: int = 20
    N2: int = 20
    N3: int = 20
    split_idx: int = 20
    num_sections: int = 61
    semi_span_m: float = 1.6
    full_span_m: float = 3.2
    approx_area_m2: float = 2.18
    approx_aspect_ratio: float = 4.69


@dataclass(frozen=True)
class DummySectionGeometryResult:
    twist_b0_deg: float = 0.0
    twist_b1_deg: float = 0.0
    twist_b2_deg: float = 0.0
    twist_b3_deg: float = 0.0
    dihedral_b0_deg: float = 0.0
    dihedral_b1_deg: float = 0.0
    dihedral_b2_deg: float = 0.0
    dihedral_b3_deg: float = 0.0
    twist_boundaries_deg: object = None
    dihedral_boundaries_deg: object = None
    group_boundary_y: object = None


def make_config() -> BWBGeneratorConfig:
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
        control_surfaces=ControlSurfacesConfig(
            enabled=False,
            surfaces=(),
        ),
    )


def make_planform() -> DummyPlanformResult:
    return DummyPlanformResult()


def make_section_geometry() -> DummySectionGeometryResult:
    return DummySectionGeometryResult()


def make_aerosandbox_result() -> AeroSandboxGeometryResult:
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
        metadata={
            "has_control_surfaces": True,
            "control_surface_count": 1,
            "applied_control_surfaces": [
                {
                    "name": "elevon",
                    "family": "trailing_edge",
                    "hinge_point": 0.75,
                    "symmetric": True,
                    "side": None,
                    "start_frac": 0.60,
                    "end_frac": 0.95,
                    "applied_xsec_indices": [1],
                }
            ],
        },
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


def test_build_geometry_summary_includes_control_surface_summary():
    cfg = make_config()
    cfg = cfg.__class__(
        name=cfg.name,
        generator=cfg.generator,
        controls=cfg.controls,
        planform_bounds=cfg.planform_bounds,
        section_bounds=cfg.section_bounds,
        outputs=cfg.outputs,
        control_surfaces=ControlSurfacesConfig(
            enabled=True,
            surfaces=(
                ControlSurfaceConfig(
                    name="elevon",
                    family="trailing_edge",
                    hinge_point=0.75,
                    symmetric=True,
                    spanwise=ControlSurfaceSpanwiseConfig(
                        start_frac=0.60,
                        end_frac=0.95,
                    ),
                    deflection_sign="standard",
                    side=None,
                    required=False,
                ),
            ),
        ),
    )

    summary = build_geometry_summary(
        config=cfg,
        planform=make_planform(),
        section_geometry=make_section_geometry(),
        aerosandbox_result=make_aerosandbox_result(),
        artifact_paths={"summary_path": "dummy.json"},
    )

    css = summary["control_surface_summary"]
    assert css["configured"]["enabled"] is True
    assert css["configured"]["count"] == 1
    assert css["configured"]["names"] == ["elevon"]

    definition = css["configured"]["definitions"][0]
    assert definition["name"] == "elevon"
    assert definition["hinge_point"] == 0.75
    assert definition["start_frac"] == 0.60
    assert definition["end_frac"] == 0.95

    assert css["applied"]["has_control_surfaces"] is True
    assert css["applied"]["control_surface_count"] == 1
    assert css["applied"]["applied_control_surfaces"][0]["name"] == "elevon"