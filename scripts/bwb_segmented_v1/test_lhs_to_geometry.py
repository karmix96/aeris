from __future__ import annotations

from pathlib import Path

from aeris.common.config import load_yaml_config
from aeris.dataset.sampling.samplers.lhs_v1 import generate_lhs_samples
from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import build_aerosandbox_geometry
from aeris.generators.bwb_segmented_v1.export import build_geometry_summary
from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config
from aeris.generators.bwb_segmented_v1.planform import generate_bwb_planform_from_sample
from aeris.generators.bwb_segmented_v1.sections import build_section_geometry_from_sample
from aeris.generators.bwb_segmented_v1.validation import (
    validate_bwb_generator_config,
    validate_planform_result,
    validate_section_geometry,
)


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    config_path = project_root / "configs" / "geometry" / "wing_bwb.yaml"

    raw = load_yaml_config(config_path)
    cfg = build_bwb_generator_config(raw)
    validate_bwb_generator_config(cfg)

    lhs_samples = generate_lhs_samples(
        config=cfg,
        n_samples=3,
        sampler_seed=123,
    )

    sample = lhs_samples[0]

    # Keep deterministic geometry by turning off hidden perturbations manually.
    cfg_det = build_bwb_generator_config(raw)
    cfg_det = cfg_det.__class__(
        name=cfg_det.name,
        generator=cfg_det.generator,
        controls=cfg_det.controls.__class__(
            n_points=cfg_det.controls.n_points,
            n_spline_inboard=cfg_det.controls.n_spline_inboard,
            n_spline_outboard=cfg_det.controls.n_spline_outboard,
            curvature_strength=cfg_det.controls.curvature_strength,
            spline_split_ratio=cfg_det.controls.spline_split_ratio,
            segment_length_variation=0.0,
            sweep_variation=0.0,
        ),
        planform_bounds=cfg_det.planform_bounds,
        section_bounds=cfg_det.section_bounds,
        outputs=cfg_det.outputs,
        control_surfaces=cfg_det.control_surfaces,
    )

    planform = generate_bwb_planform_from_sample(sample, cfg_det)
    validate_planform_result(planform)

    section_geometry = build_section_geometry_from_sample(planform, sample, cfg_det)
    validate_section_geometry(section_geometry)

    aerosandbox_result = None
    if cfg_det.outputs.build_aerosandbox:
        aerosandbox_result = build_aerosandbox_geometry(section_geometry, cfg_det)

    summary = build_geometry_summary(
        config=cfg_det,
        planform=planform,
        section_geometry=section_geometry,
        aerosandbox_result=aerosandbox_result,
        artifact_paths={},
    )

    print("\n=== LHS SAMPLE USED ===\n")
    for key, value in sample.to_dict().items():
        print(f"{key}: {value:.6f}")

    print("\n=== RESULTING METRICS ===\n")
    for key, value in summary["metrics"].items():
        print(f"{key}: {value}")

    if "control_surface_summary" in summary:
        print("\n=== CONTROL SURFACE SUMMARY ===\n")
        print(summary["control_surface_summary"])

    print("\nSuccess: LHS sample was converted into a valid geometry.")


if __name__ == "__main__":
    main()