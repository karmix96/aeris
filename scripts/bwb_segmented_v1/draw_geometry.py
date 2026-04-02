from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import aerosandbox as asb
import matplotlib

# Headless-safe backend when we are not showing interactive windows.
if "--no-show" in __import__("sys").argv:
    matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from aeris.common.config import load_yaml_config
from aeris.generators.bwb_segmented_v1.case import generate_geometry_case_from_sample
from aeris.generators.bwb_segmented_v1.params import (
    BWBDesignSample,
    build_bwb_generator_config,
)
from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design
from aeris.generators.bwb_segmented_v1.validation import validate_bwb_generator_config


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "geometry" / "baseline_bwb.yaml"
DEFAULT_DEBUG_ROOT = PROJECT_ROOT / "data" / "debug" / "draw_geometry"


# ---------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------
def pick_column(df: pd.DataFrame, candidates: list[str]) -> str:
    for name in candidates:
        if name in df.columns:
            return name
    raise KeyError(
        f"Could not find any of these columns: {candidates}\n"
        f"Available columns: {list(df.columns)}"
    )


def ensure_exists(path: Path, what: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"{what} not found: {path}")
    return path


def ensure_file(path: Path, what: str) -> Path:
    path = ensure_exists(path, what)
    if not path.is_file():
        raise FileNotFoundError(f"{what} is not a file: {path}")
    return path


def ensure_dir(path: Path, what: str) -> Path:
    path = ensure_exists(path, what)
    if not path.is_dir():
        raise FileNotFoundError(f"{what} is not a directory: {path}")
    return path


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------
def resolve_case_dir_from_run_dir(run_dir: Path) -> Path:
    run_dir = run_dir.expanduser().resolve()
    candidates = [
        run_dir / "geometry",
        run_dir / "artifacts" / "geometry",
        run_dir,
    ]
    for candidate in candidates:
        if (candidate / "section_3d.csv").exists():
            return candidate
    raise FileNotFoundError(
        f"Could not find a geometry case directory under run dir: {run_dir}"
    )


def resolve_case_dir_from_dataset(dataset_root: Path, geometry_id: str) -> Path:
    dataset_root = dataset_root.expanduser().resolve()
    case_dir = dataset_root / "geometry" / geometry_id
    return ensure_dir(case_dir, "Dataset geometry case directory")


def resolve_case_dir_from_geometry_dir(geometry_dir: Path) -> Path:
    geometry_dir = geometry_dir.expanduser().resolve()
    return ensure_dir(geometry_dir, "Geometry directory")


# ---------------------------------------------------------------------
# Manual sample handling
# ---------------------------------------------------------------------
def manual_sample_from_json(path: Path) -> BWBDesignSample:
    data = load_json(path.expanduser().resolve())
    return BWBDesignSample(
        c1_m=float(data["c1_m"]),
        c2_ratio=float(data["c2_ratio"]),
        c3_ratio=float(data["c3_ratio"]),
        c4_ratio=float(data["c4_ratio"]),
        b_total_m=float(data["b_total_m"]),
        b3_ratio=float(data["b3_ratio"]),
        split_ratio=float(data["split_ratio"]),
        sw1_deg=float(data["sw1_deg"]),
        sw2_deg=float(data["sw2_deg"]),
        sw3_deg=float(data["sw3_deg"]),
        twist_b0_deg=float(data["twist_b0_deg"]),
        twist_b1_deg=float(data["twist_b1_deg"]),
        twist_b2_deg=float(data["twist_b2_deg"]),
        twist_b3_deg=float(data["twist_b3_deg"]),
        dihedral_b1_deg=float(data["dihedral_b1_deg"]),
        dihedral_b2_deg=float(data["dihedral_b2_deg"]),
        dihedral_b3_deg=float(data["dihedral_b3_deg"]),
    )


def manual_sample_from_args(args: argparse.Namespace) -> BWBDesignSample:
    required = [
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
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        raise ValueError(
            "Manual mode requires all 17 design variables unless --manual-json is used.\n"
            f"Missing: {missing}"
        )

    return BWBDesignSample(
        c1_m=float(args.c1_m),
        c2_ratio=float(args.c2_ratio),
        c3_ratio=float(args.c3_ratio),
        c4_ratio=float(args.c4_ratio),
        b_total_m=float(args.b_total_m),
        b3_ratio=float(args.b3_ratio),
        split_ratio=float(args.split_ratio),
        sw1_deg=float(args.sw1_deg),
        sw2_deg=float(args.sw2_deg),
        sw3_deg=float(args.sw3_deg),
        twist_b0_deg=float(args.twist_b0_deg),
        twist_b1_deg=float(args.twist_b1_deg),
        twist_b2_deg=float(args.twist_b2_deg),
        twist_b3_deg=float(args.twist_b3_deg),
        dihedral_b1_deg=float(args.dihedral_b1_deg),
        dihedral_b2_deg=float(args.dihedral_b2_deg),
        dihedral_b3_deg=float(args.dihedral_b3_deg),
    )


# ---------------------------------------------------------------------
# Geometry generation source modes
# ---------------------------------------------------------------------
def generate_case_from_config(
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
    sample = sample_bwb_design(bwb_config, rng)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    generate_geometry_case_from_sample(
        config=bwb_config,
        sample=sample,
        output_dir=output_dir,
        save_plot=save_planform_plot,
        build_aerosandbox=build_aerosandbox,
    )
    return output_dir


def generate_case_from_manual_sample(
    *,
    config_path: Path,
    sample: BWBDesignSample,
    output_dir: Path,
    save_planform_plot: bool,
    build_aerosandbox: bool,
) -> Path:
    raw_config = load_yaml_config(config_path)
    bwb_config = build_bwb_generator_config(raw_config)
    validate_bwb_generator_config(bwb_config)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    generate_geometry_case_from_sample(
        config=bwb_config,
        sample=sample,
        output_dir=output_dir,
        save_plot=save_planform_plot,
        build_aerosandbox=build_aerosandbox,
    )
    return output_dir


# ---------------------------------------------------------------------
# CSV plotting helpers
# ---------------------------------------------------------------------
def naca0012_airfoil(n: int = 100) -> tuple[np.ndarray, np.ndarray]:
    x = np.linspace(0.0, 1.0, n)
    t = 0.12
    yt = 5 * t * (
        0.2969 * np.sqrt(x)
        - 0.1260 * x
        - 0.3516 * x**2
        + 0.2843 * x**3
        - 0.1015 * x**4
    )
    xu = x
    zu = yt
    xl = x[::-1]
    zl = -yt[::-1]
    x_coords = np.concatenate([xu, xl])
    z_coords = np.concatenate([zu, zl])
    return x_coords, z_coords


def plot_section_3d_csv(
    csv_path: Path,
    *,
    title: str = "AERIS 3D Wing",
    mirror: bool = True,
    save_path: Path | None = None,
    show: bool = True,
) -> None:
    df = pd.read_csv(csv_path)

    fig = plt.figure(figsize=(11, 8))
    ax = fig.add_subplot(111, projection="3d")

    for _, row in df.iterrows():
        x_le = float(row["x_le_m"])
        y = float(row["y_m"])
        z_le = float(row["z_le_m"])
        chord = float(row["chord_m"])
        twist = np.deg2rad(float(row["twist_deg"]))
        dihedral = np.deg2rad(float(row["dihedral_deg"]))

        x_af, z_af = naca0012_airfoil()
        x_af = x_af * chord
        z_af = z_af * chord

        # Twist about local y-axis.
        x_tw = x_af * np.cos(twist) + z_af * np.sin(twist)
        z_tw = -x_af * np.sin(twist) + z_af * np.cos(twist)

        # Dihedral about local x-axis.
        y_d = y + z_tw * np.sin(dihedral)
        z_d = z_le + z_tw * np.cos(dihedral)
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
        save_path = save_path.expanduser().resolve()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=200)
        print(f"Saved 3D csv replay plot to: {save_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)


def plot_planform(
    *,
    planform_sections_csv: Path,
    control_points_csv: Path | None = None,
    title: str = "AERIS Planform",
    mirror: bool = True,
    save_path: Path | None = None,
    show: bool = True,
) -> None:
    sec = pd.read_csv(planform_sections_csv)

    fig, ax = plt.subplots(figsize=(11, 6))

    fx = pick_column(sec, ["front_x_m", "x_le_m"])
    fy = pick_column(sec, ["front_y_m", "y_m"])
    rx = pick_column(sec, ["rear_x_m", "x_te_m"])
    ry = pick_column(sec, ["rear_y_m", "y_m"])

    for _, row in sec.iterrows():
        x_le = float(row[fx])
        y_le = float(row[fy])
        x_te = float(row[rx])
        y_te = float(row[ry])

        ax.plot([x_le, x_te], [y_le, y_te], linewidth=1.0, color="black")
        if mirror:
            ax.plot([x_le, x_te], [-y_le, -y_te], linewidth=1.0, color="black")

    ax.plot(sec[fx], sec[fy], linewidth=1.5, label="Leading edge")
    ax.plot(sec[rx], sec[ry], linewidth=1.5, label="Trailing edge")
    if mirror:
        ax.plot(sec[fx], -sec[fy], linewidth=1.5)
        ax.plot(sec[rx], -sec[ry], linewidth=1.5)

    if control_points_csv is not None and control_points_csv.exists():
        cp = pd.read_csv(control_points_csv)
        cx_le = pick_column(cp, ["x_le_m"])
        cy_le = pick_column(cp, ["y_le_m"])
        cx_te = pick_column(cp, ["x_te_m"])
        cy_te = pick_column(cp, ["y_te_m"])

        ax.scatter(cp[cx_le], cp[cy_le], s=18, marker="o", label="LE control points")
        ax.scatter(cp[cx_te], cp[cy_te], s=18, marker="x", label="TE control points")
        if mirror:
            ax.scatter(cp[cx_le], -cp[cy_le], s=18, marker="o")
            ax.scatter(cp[cx_te], -cp[cy_te], s=18, marker="x")

    ax.set_title(title)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.axis("equal")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    plt.tight_layout()

    if save_path is not None:
        save_path = save_path.expanduser().resolve()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=200)
        print(f"Saved planform plot to: {save_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)


# ---------------------------------------------------------------------
# AeroSandbox draw() path
# ---------------------------------------------------------------------
def build_airplane_from_section_csv(
    *,
    section_csv: Path,
    airplane_name: str,
    symmetric: bool,
) -> asb.Airplane:
    df = pd.read_csv(section_csv)
    if df.empty:
        raise ValueError(f"section_3d.csv is empty: {section_csv}")

    xsecs: list[asb.WingXSec] = []
    for _, row in df.iterrows():
        airfoil_name = str(row.get("airfoil_name", "naca0012")).strip() or "naca0012"
        xsecs.append(
            asb.WingXSec(
                xyz_le=[
                    float(row["x_le_m"]),
                    float(row["y_m"]),
                    float(row["z_le_m"]),
                ],
                chord=float(row["chord_m"]),
                twist=float(row["twist_deg"]),
                airfoil=asb.Airfoil(airfoil_name),
            )
        )

    wing = asb.Wing(
        name=f"{airplane_name}_wing",
        symmetric=symmetric,
        xsecs=xsecs,
    )

    return asb.Airplane(
        name=airplane_name,
        wings=[wing],
        s_ref=float(wing.area()),
        c_ref=float(wing.mean_aerodynamic_chord()),
        b_ref=float(wing.span()),
    )


def draw_airplane_if_requested(
    airplane: asb.Airplane,
    *,
    do_draw: bool,
) -> None:
    if not do_draw:
        return
    # Honest note:
    # AeroSandbox.draw() is best for interactive inspection, not for deterministic PNG export.
    airplane.draw()


# ---------------------------------------------------------------------
# Case summary
# ---------------------------------------------------------------------
def print_case_summary(case_dir: Path) -> None:
    summary_path = case_dir / "geometry_summary.json"
    if not summary_path.exists():
        print(f"[info] No geometry_summary.json found under {case_dir}")
        return

    data = load_json(summary_path)
    print("\n=== Geometry Summary ===")
    for key in [
        "generator_id",
        "aspect_ratio_aerosandbox",
        "n_xsecs_aerosandbox",
        "span_m",
        "area_m2",
        "mean_aerodynamic_chord_m",
    ]:
        if key in data:
            print(f"{key}: {data[key]}")


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Unified BWB geometry visualizer for AERIS. "
            "Replaces visualize_airplane.py and run_single_case_and_plot_3d.py."
        )
    )

    parser.add_argument(
        "--mode",
        choices=["config", "dataset", "run", "case", "geometry_dir", "manual"],
        required=True,
        help=(
            "Source mode: "
            "config=new generation from YAML, "
            "dataset=dataset root + geometry id, "
            "run=existing run root, "
            "case/direct geometry_dir=already exported geometry folder, "
            "manual=generate from explicit 17-variable design sample."
        ),
    )

    # Source arguments
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to geometry YAML config. Used in config/manual modes.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Dataset root. Used only in --mode dataset.",
    )
    parser.add_argument(
        "--geometry-id",
        type=str,
        default=None,
        help="Geometry ID such as geom_00001. Used only in --mode dataset.",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Existing run root. Used only in --mode run.",
    )
    parser.add_argument(
        "--case-dir",
        type=Path,
        default=None,
        help="Direct geometry case dir. Used only in --mode case.",
    )
    parser.add_argument(
        "--geometry-dir",
        type=Path,
        default=None,
        help="Direct exported geometry dir. Used only in --mode geometry_dir.",
    )

    # Generation arguments
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_DEBUG_ROOT / "generated_case",
        help="Output dir used for config/manual generation modes.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional override for config-mode sampling seed.",
    )
    parser.add_argument(
        "--save-planform-plot",
        action="store_true",
        help="Also save the normal planform plot during config/manual generation.",
    )
    parser.add_argument(
        "--no-build-aerosandbox",
        action="store_true",
        help="Skip AeroSandbox object creation during config/manual generation.",
    )

    # Manual mode arguments
    parser.add_argument(
        "--manual-json",
        type=Path,
        default=None,
        help="Optional JSON file containing the full 17-variable manual sample.",
    )

    parser.add_argument("--c1-m", dest="c1_m", type=float, default=None)
    parser.add_argument("--c2-ratio", dest="c2_ratio", type=float, default=None)
    parser.add_argument("--c3-ratio", dest="c3_ratio", type=float, default=None)
    parser.add_argument("--c4-ratio", dest="c4_ratio", type=float, default=None)
    parser.add_argument("--b-total-m", dest="b_total_m", type=float, default=None)
    parser.add_argument("--b3-ratio", dest="b3_ratio", type=float, default=None)
    parser.add_argument("--split-ratio", dest="split_ratio", type=float, default=None)
    parser.add_argument("--sw1-deg", dest="sw1_deg", type=float, default=None)
    parser.add_argument("--sw2-deg", dest="sw2_deg", type=float, default=None)
    parser.add_argument("--sw3-deg", dest="sw3_deg", type=float, default=None)
    parser.add_argument("--twist-b0-deg", dest="twist_b0_deg", type=float, default=None)
    parser.add_argument("--twist-b1-deg", dest="twist_b1_deg", type=float, default=None)
    parser.add_argument("--twist-b2-deg", dest="twist_b2_deg", type=float, default=None)
    parser.add_argument("--twist-b3-deg", dest="twist_b3_deg", type=float, default=None)
    parser.add_argument("--dihedral-b1-deg", dest="dihedral_b1_deg", type=float, default=None)
    parser.add_argument("--dihedral-b2-deg", dest="dihedral_b2_deg", type=float, default=None)
    parser.add_argument("--dihedral-b3-deg", dest="dihedral_b3_deg", type=float, default=None)

    # Visualization arguments
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not open interactive windows.",
    )
    parser.add_argument(
        "--no-mirror",
        action="store_true",
        help="Do not mirror the csv replay wing to the opposite side.",
    )
    parser.add_argument(
        "--draw",
        action="store_true",
        help="Use AeroSandbox airplane.draw() for interactive inspection.",
    )
    parser.add_argument(
        "--save-3d-plot",
        type=Path,
        default=None,
        help="Optional PNG path for static 3D csv replay plot.",
    )
    parser.add_argument(
        "--save-planform-png",
        type=Path,
        default=None,
        help="Optional PNG path for top-view planform plot.",
    )
    parser.add_argument(
        "--title",
        type=str,
        default="AERIS Geometry Viewer",
        help="Plot title prefix.",
    )

    return parser.parse_args()


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main() -> None:
    args = parse_args()

    mirror = not args.no_mirror
    show = not args.no_show
    build_aerosandbox = not args.no_build_aerosandbox

    if args.mode == "config":
        case_dir = generate_case_from_config(
            config_path=args.config.expanduser().resolve(),
            output_dir=args.output_dir.expanduser().resolve(),
            seed_override=args.seed,
            save_planform_plot=args.save_planform_plot,
            build_aerosandbox=build_aerosandbox,
        )
    elif args.mode == "manual":
        sample = (
            manual_sample_from_json(args.manual_json)
            if args.manual_json is not None
            else manual_sample_from_args(args)
        )
        case_dir = generate_case_from_manual_sample(
            config_path=args.config.expanduser().resolve(),
            sample=sample,
            output_dir=args.output_dir.expanduser().resolve(),
            save_planform_plot=args.save_planform_plot,
            build_aerosandbox=build_aerosandbox,
        )
    elif args.mode == "dataset":
        if args.dataset is None or not args.geometry_id:
            raise ValueError("--mode dataset requires both --dataset and --geometry-id")
        case_dir = resolve_case_dir_from_dataset(args.dataset, args.geometry_id)
    elif args.mode == "run":
        if args.run_dir is None:
            raise ValueError("--mode run requires --run-dir")
        case_dir = resolve_case_dir_from_run_dir(args.run_dir)
    elif args.mode == "case":
        if args.case_dir is None:
            raise ValueError("--mode case requires --case-dir")
        case_dir = resolve_case_dir_from_geometry_dir(args.case_dir)
    elif args.mode == "geometry_dir":
        if args.geometry_dir is None:
            raise ValueError("--mode geometry_dir requires --geometry-dir")
        case_dir = resolve_case_dir_from_geometry_dir(args.geometry_dir)
    else:
        raise ValueError(f"Unsupported mode: {args.mode}")

    section_csv = ensure_file(case_dir / "section_3d.csv", "section_3d.csv")
    planform_sections_csv = case_dir / "planform_sections.csv"
    control_points_csv = case_dir / "control_points.csv"

    print(f"Resolved case dir: {case_dir}")
    print_case_summary(case_dir)

    # Static csv replay path (headless-safe / savable)
    if args.save_3d_plot is not None or not args.draw:
        plot_section_3d_csv(
            section_csv,
            title=f"{args.title} — 3D CSV Replay",
            mirror=mirror,
            save_path=args.save_3d_plot,
            show=show and not args.draw,
        )

    if args.save_planform_png is not None:
        if not planform_sections_csv.exists():
            raise FileNotFoundError(
                f"Requested planform PNG save but planform_sections.csv is missing: {planform_sections_csv}"
            )
        plot_planform(
            planform_sections_csv=planform_sections_csv,
            control_points_csv=control_points_csv if control_points_csv.exists() else None,
            title=f"{args.title} — Planform",
            mirror=mirror,
            save_path=args.save_planform_png,
            show=False,
        )

    # Interactive AeroSandbox draw()
    if args.draw and show:
        airplane = build_airplane_from_section_csv(
            section_csv=section_csv,
            airplane_name=case_dir.name,
            symmetric=mirror,
        )
        draw_airplane_if_requested(airplane, do_draw=True)
    elif args.draw and not show:
        print(
            "[info] --draw was requested together with --no-show. "
            "Skipping interactive AeroSandbox.draw(); use --save-3d-plot for headless output."
        )


if __name__ == "__main__":
    main()