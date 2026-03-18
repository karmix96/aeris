from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from aeris.common.config import load_yaml_config
from aeris.generators.bwb_segmented_v1.case import generate_geometry_case_from_sample
from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config
from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design
from aeris.generators.bwb_segmented_v1.validation import validate_bwb_generator_config


def pick_column(df: pd.DataFrame, candidates: list[str]) -> str:
    for name in candidates:
        if name in df.columns:
            return name
    raise KeyError(
        f"Could not find any of these columns: {candidates}\n"
        f"Available columns: {list(df.columns)}"
    )


def naca0012_airfoil(n=100):
    x = np.linspace(0, 1, n)
    t = 0.12
    yt = 5 * t * (
        0.2969 * np.sqrt(x)
        - 0.1260 * x
        - 0.3516 * x**2
        + 0.2843 * x**3
        - 0.1015 * x**4
    )
    xu = x
    yu = yt
    xl = x[::-1]
    yl = -yt[::-1]

    x_coords = np.concatenate([xu, xl])
    z_coords = np.concatenate([yu, yl])

    return x_coords, z_coords


def plot_section_3d_csv(
    csv_path: Path,
    *,
    title: str = "3D Wing",
    mirror: bool = True,
    save_path: Path | None = None,
    show: bool = True,
):
    df = pd.read_csv(csv_path)

    fig = plt.figure(figsize=(11, 8))
    ax = fig.add_subplot(111, projection="3d")

    for _, row in df.iterrows():
        x_le = row["x_le_m"]
        y = row["y_m"]
        z_le = row["z_le_m"]
        chord = row["chord_m"]
        twist = np.deg2rad(row["twist_deg"])
        dihedral = np.deg2rad(row["dihedral_deg"])

        # airfoil
        x_af, z_af = naca0012_airfoil()

        # scale
        x_af = x_af * chord
        z_af = z_af * chord

        # twist (rotation around y-axis)
        x_tw = x_af * np.cos(twist) + z_af * np.sin(twist)
        z_tw = -x_af * np.sin(twist) + z_af * np.cos(twist)

        # dihedral (rotation around x-axis)
        y_d = y + z_tw * np.sin(dihedral)
        z_d = z_le + z_tw * np.cos(dihedral)

        # translate
        x_final = x_le + x_tw

        ax.plot(x_final, y_d, z_d, linewidth=1.2)

        if mirror:
            ax.plot(x_final, -y_d, z_d, linewidth=1.2)

    ax.set_title(title)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_zlabel("z [m]")

    ax.view_init(elev=20, azim=-130)

    plt.tight_layout()

    if save_path is not None:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=200)
        print(f"Saved 3D plot to: {save_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)


def run_single_case(
    *,
    config_path: Path,
    output_dir: Path,
    seed_override: int | None,
    save_planform_plot: bool,
    build_aerosandbox: bool,
) -> Path:
    raw_config = load_yaml_config(config_path)
    bwb_config = build_bwb_generator_config(raw_config)
    validate_bwb_generator_config(bwb_config)

    seed = bwb_config.generator.seed if seed_override is None else seed_override
    rng = np.random.default_rng(seed)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sample = sample_bwb_design(bwb_config, rng)

    result = generate_geometry_case_from_sample(
        config=bwb_config,
        sample=sample,
        output_dir=output_dir,
        save_plot=save_planform_plot,
        build_aerosandbox=build_aerosandbox,
    )

    section_csv = result.artifact_paths.section_3d_path
    print(f"Single case generated in: {output_dir}")
    print(f"section_3d.csv: {section_csv}")
    return section_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one AERIS geometry case and plot the 3D wing."
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to geometry YAML config, e.g. configs/geometry/wing_bwb.yaml",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/debug/single_case_3d"),
        help="Folder where the single-case artifacts will be written.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional override for generator seed.",
    )
    parser.add_argument(
        "--save-planform-plot",
        action="store_true",
        help="Also save the normal 2D planform plot from the geometry pipeline.",
    )
    parser.add_argument(
        "--no-build-aerosandbox",
        action="store_true",
        help="Skip AeroSandbox object creation for this single case.",
    )
    parser.add_argument(
        "--save-3d-plot",
        type=Path,
        default=None,
        help="Optional path to save the 3D matplotlib figure as PNG.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not open the interactive matplotlib window.",
    )
    parser.add_argument(
        "--no-mirror",
        action="store_true",
        help="Plot only the generated side instead of mirroring to both sides.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    section_csv = run_single_case(
        config_path=args.config.expanduser().resolve(),
        output_dir=args.output_dir.expanduser().resolve(),
        seed_override=args.seed,
        save_planform_plot=args.save_planform_plot,
        build_aerosandbox=not args.no_build_aerosandbox,
    )

    plot_section_3d_csv(
        section_csv,
        title="AERIS Single-Case 3D Wing",
        mirror=not args.no_mirror,
        save_path=None if args.save_3d_plot is None else args.save_3d_plot.expanduser().resolve(),
        show=not args.no_show,
    )


if __name__ == "__main__":
    main()