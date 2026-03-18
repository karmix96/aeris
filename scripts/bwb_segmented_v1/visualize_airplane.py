from __future__ import annotations
from dataclasses import replace
import argparse
import csv
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aeris.common.config import load_yaml_config
from aeris.generators.bwb_segmented_v1.case import generate_geometry_case_from_sample
from aeris.generators.bwb_segmented_v1.params import BWBDesignSample, build_bwb_generator_config


DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "geometry" / "wing_bwb.yaml"
DEFAULT_DATASET = PROJECT_ROOT / "data" / "datasets" / "wing_bwb_bwb_segmented_v1_n10_lhs123"


DESIGN_FIELDS = [
    "c1_m",
    "c2_ratio",
    "c3_ratio",
    "c4_ratio",
    "b_total_m",
    "b3_ratio",
    "split_ratio",
    "sw1_deg",
    "sw2_deg",
    "sw3_deg",
    "twist_b0_deg",
    "twist_b1_deg",
    "twist_b2_deg",
    "twist_b3_deg",
    "dihedral_b1_deg",
    "dihedral_b2_deg",
    "dihedral_b3_deg",
]


def baseline_sample() -> BWBDesignSample:
    c1 = 1.3
    c2 = 0.65
    c3 = 0.5
    c4 = 0.17

    b1 = 0.46
    b2 = 0.56
    b3 = 1.01
    b_total = b1 + b2 + b3

    sw1_rad = -0.85
    sw2_rad = -1.10
    sw3_rad = -1.22

    return BWBDesignSample(
        c1_m=c1,
        c2_ratio=c2 / c1,
        c3_ratio=c3 / c1,
        c4_ratio=c4 / c1,
        b_total_m=b_total,
        b3_ratio=b3 / b_total,
        split_ratio=b1 / (b1 + b2),
        sw1_deg=90.0 - math.degrees(sw1_rad),
        sw2_deg=90.0 - math.degrees(sw2_rad),
        sw3_deg=90.0 - math.degrees(sw3_rad),
        twist_b0_deg=0.0,
        twist_b1_deg=0.0,
        twist_b2_deg=0.0,
        twist_b3_deg=0.0,
        dihedral_b1_deg=0.0,
        dihedral_b2_deg=0.0,
        dihedral_b3_deg=0.0,
    )


def sample_from_metadata(dataset_root: Path, geometry_id: str) -> BWBDesignSample:
    metadata_path = dataset_root / "metadata.csv"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing metadata.csv: {metadata_path}")

    with metadata_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row["geometry_id"] == geometry_id:
                kwargs = {field: float(row[field]) for field in DESIGN_FIELDS}
                return BWBDesignSample(**kwargs)

    raise ValueError(f"geometry_id not found in metadata.csv: {geometry_id}")

def baseline_config_override(cfg):
    """
    Override the full project config with controls that better match
    the old baseline script.
    """
    controls = replace(
        cfg.controls,
        n_points=10,
        n_spline_inboard=150,
        n_spline_outboard=50,
        curvature_strength=1.0,
        spline_split_ratio=0.55,
        segment_length_variation=0.0,
        sweep_variation=0.0,
    )

    section_bounds = replace(
        cfg.section_bounds,
        airfoil_name="naca4412",
        dihedral_root_deg=0.0,
    )

    return replace(cfg, controls=controls, section_bounds=section_bounds)

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visualize a BWB candidate using the current AERIS architecture and AeroSandbox.draw()."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to geometry YAML config.",
    )
    parser.add_argument(
        "--mode",
        choices=["baseline", "dataset"],
        default="baseline",
        help="Visualize the hardcoded baseline sample or a candidate from dataset metadata.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Dataset root (used only in --mode dataset).",
    )
    parser.add_argument(
        "--geometry-id",
        type=str,
        default=None,
        help="Geometry ID in metadata.csv, e.g. geom_00001 (used only in --mode dataset).",
    )
    parser.add_argument(
        "--save-plot",
        action="store_true",
        help="Also save the 2D planform plot/artifacts under data/debug/visualization_runs/.",
    )
    args = parser.parse_args()

    raw = load_yaml_config(args.config)
    cfg = build_bwb_generator_config(raw)

    if args.mode == "baseline":
        cfg = baseline_config_override(cfg)
        sample = baseline_sample()
        tag = "baseline"
    else:
        if not args.geometry_id:
            raise ValueError("--geometry-id is required when --mode dataset")
        sample = sample_from_metadata(args.dataset, args.geometry_id)
        tag = args.geometry_id

    output_dir = PROJECT_ROOT / "data" / "debug" / "visualization_runs" / tag

    result = generate_geometry_case_from_sample(
        config=cfg,
        sample=sample,
        output_dir=output_dir,
        save_plot=args.save_plot,
        build_aerosandbox=True,
    )

    print("\n=== VISUALIZATION SAMPLE ===")
    for field in DESIGN_FIELDS:
        print(f"{field}: {getattr(sample, field):.10f}")

    print("\n=== GEOMETRY SUMMARY ===")
    print(f"full_span_m: {result.planform.full_span_m:.6f}")
    print(f"approx_area_m2: {result.planform.approx_area_m2:.6f}")
    print(f"approx_aspect_ratio: {result.planform.approx_aspect_ratio:.6f}")

    if result.aerosandbox_result is None:
        raise RuntimeError("AeroSandbox result was not built.")

    airplane = result.aerosandbox_result.airplane
    print("\nOpening AeroSandbox draw window...")
    airplane.draw()
    

if __name__ == "__main__":
    main()