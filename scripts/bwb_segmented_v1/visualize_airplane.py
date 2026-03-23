from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aeris.common.config import load_yaml_config
from aeris.generators.bwb_segmented_v1.case import generate_geometry_case_from_sample
from aeris.generators.bwb_segmented_v1.params import (
    BWBDesignSample,
    build_bwb_generator_config,
)

import copy
import math
import numpy as np


def rotate_point_about_y(xyz, alpha_deg):
    a = math.radians(alpha_deg)
    x, y, z = xyz
    x_new = x * math.cos(a) + z * math.sin(a)
    y_new = y
    z_new = -x * math.sin(a) + z * math.cos(a)
    return np.array([x_new, y_new, z_new])


def rotate_airplane_geometry_about_y(airplane, alpha_deg):
    """
    Returns a deep-copied airplane with wing/fuselage geometry rotated about the global y-axis.
    This is for visualization only.
    """
    rotated = copy.deepcopy(airplane)

    for wing in rotated.wings:
        for xsec in wing.xsecs:
            xsec.xyz_le = rotate_point_about_y(xsec.xyz_le, alpha_deg)

    for fuse in rotated.fuselages:
        for xsec in fuse.xsecs:
            xsec.xyz_c = rotate_point_about_y(xsec.xyz_c, alpha_deg)

    if hasattr(rotated, "xyz_ref"):
        rotated.xyz_ref = rotate_point_about_y(rotated.xyz_ref, alpha_deg)

    return rotated

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


def load_config_from_dataset(dataset_root: Path):
    candidates = [
        dataset_root / "configs" / "input_config.yaml",
        dataset_root / "input_config.yaml",
        dataset_root / "configs" / "resolved_dataset_config.json",
        dataset_root / "resolved_config.json",
    ]

    last_error = None

    for path in candidates:
        if not path.exists():
            continue

        try:
            if path.suffix == ".json":
                raw = json.loads(path.read_text(encoding="utf-8"))
            else:
                raw = load_yaml_config(path)

            return build_bwb_generator_config(raw)

        except Exception as exc:
            last_error = exc
            continue

    searched = "\n".join(str(p) for p in candidates)
    raise FileNotFoundError(
        f"Could not reconstruct generator config from dataset at {dataset_root}.\n"
        f"Searched:\n{searched}\n"
        f"Last error: {last_error}"
    )


def build_tag(mode: str, config_path: Path | None, dataset_root: Path | None, geometry_id: str | None) -> str:
    if mode == "baseline":
        cfg_name = "default" if config_path is None else config_path.stem
        return f"baseline_{cfg_name}"
    if mode == "config":
        if config_path is None:
            raise ValueError("config_path is required for config mode")
        return f"config_{config_path.stem}"
    if mode == "dataset":
        if dataset_root is None or geometry_id is None:
            raise ValueError("dataset_root and geometry_id are required for dataset mode")
        return f"{dataset_root.name}_{geometry_id}"
    raise ValueError(f"Unsupported mode: {mode}")

def sample_from_run(run_root: Path) -> BWBDesignSample:
    summary_path = run_root / "geometry" / "geometry_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing geometry summary: {summary_path}")

    data = json.loads(summary_path.read_text(encoding="utf-8"))

    sampled_planform = data["sampled_planform"]
    sampled_sections = data["sampled_sections"]

    return BWBDesignSample(
        c1_m=float(sampled_planform["c1_m"]),
        c2_ratio=float(sampled_planform["c2_ratio"]),
        c3_ratio=float(sampled_planform["c3_ratio"]),
        c4_ratio=float(sampled_planform["c4_ratio"]),
        b_total_m=float(sampled_planform["b_total_m"]),
        b3_ratio=float(sampled_planform["b3_ratio"]),
        split_ratio=float(sampled_planform["split_ratio"]),
        sw1_deg=float(abs(sampled_planform["sw1_deg"])),
        sw2_deg=float(abs(sampled_planform["sw2_deg"])),
        sw3_deg=float(abs(sampled_planform["sw3_deg"])),
        twist_b0_deg=float(sampled_sections["twist_b0_deg"]),
        twist_b1_deg=float(sampled_sections["twist_b1_deg"]),
        twist_b2_deg=float(sampled_sections["twist_b2_deg"]),
        twist_b3_deg=float(sampled_sections["twist_b3_deg"]),
        dihedral_b1_deg=float(sampled_sections["dihedral_b1_deg"]),
        dihedral_b2_deg=float(sampled_sections["dihedral_b2_deg"]),
        dihedral_b3_deg=float(sampled_sections["dihedral_b3_deg"]),
    )

def trim_alpha_from_run(run_root: Path) -> float | None:
    trim_path = run_root / "dynamics" / "trim_result.json"
    if not trim_path.exists():
        return None

    data = json.loads(trim_path.read_text(encoding="utf-8"))
    longitudinal = data.get("longitudinal", {})
    if not longitudinal.get("valid", False):
        return None

    return longitudinal.get("alpha_trim_deg")

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
        choices=["baseline", "config", "dataset", "run"],
        default="baseline",
        help="Visualization source: hardcoded baseline, direct config, or dataset metadata.",
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
    parser.add_argument(
    "--run-dir",
    type=Path,
    default=None,
    help="AERIS run directory containing geometry/ and optionally dynamics/trim_result.json (used only in --mode run).",
    )
    parser.add_argument(
        "--rotate-alpha-deg",
        type=float,
        default=None,
        help="Rotate the displayed airplane by this angle in degrees for visualization. If omitted in run mode, uses trim_result.json if available.",
    )
    args = parser.parse_args()

    config_path = args.config.expanduser().resolve()

    if args.mode == "baseline":
        raw = load_yaml_config(config_path)
        cfg = build_bwb_generator_config(raw)
        cfg = baseline_config_override(cfg)
        sample = baseline_sample()
        tag = build_tag("baseline", config_path=config_path, dataset_root=None, geometry_id=None)

    elif args.mode == "config":
        raw = load_yaml_config(config_path)
        cfg = build_bwb_generator_config(raw)
        sample = cfg.sample_one() if hasattr(cfg, "sample_one") else None  # kept defensive, but likely unused
        raise RuntimeError(
            "Config mode requires an explicit sample definition path. "
            "Use baseline mode or dataset mode for now, or extend this script to define how config-only sampling should work."
        )
    elif args.mode == "run":
        if args.run_dir is None:
            raise ValueError("--run-dir is required when --mode run")

        run_root = args.run_dir.expanduser().resolve()
        if not run_root.exists():
            raise FileNotFoundError(f"Run directory does not exist: {run_root}")

        cfg_path = run_root / "baseline_bwb_25.yaml"
        if cfg_path.exists():
            raw = load_yaml_config(cfg_path)
            cfg = build_bwb_generator_config(raw)
        else:
            raw = load_yaml_config(config_path)
            cfg = build_bwb_generator_config(raw)

        sample = sample_from_run(run_root)
        tag = f"run_{run_root.name}"
    else:
        dataset_root = args.dataset.expanduser().resolve()
        if not args.geometry_id:
            raise ValueError("--geometry-id is required when --mode dataset")
        if not dataset_root.exists():
            raise FileNotFoundError(f"Dataset root does not exist: {dataset_root}")

        cfg = load_config_from_dataset(dataset_root)
        sample = sample_from_metadata(dataset_root, args.geometry_id)
        tag = build_tag("dataset", config_path=None, dataset_root=dataset_root, geometry_id=args.geometry_id)

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
    print(f"output_dir: {output_dir}")

    if result.aerosandbox_result is None:
        raise RuntimeError("AeroSandbox result was not built.")

    airplane = result.aerosandbox_result.airplane

    alpha_to_show_deg = args.rotate_alpha_deg
    if alpha_to_show_deg is None and args.mode == "run":
        alpha_to_show_deg = trim_alpha_from_run(run_root)

    if alpha_to_show_deg is not None:
        print(f"\nApplying visualization rotation of alpha = {alpha_to_show_deg:.6f} deg")
        airplane = rotate_airplane_geometry_about_y(airplane, alpha_to_show_deg)

    print("\nOpening AeroSandbox draw window...")
    airplane.draw()


if __name__ == "__main__":
    main()