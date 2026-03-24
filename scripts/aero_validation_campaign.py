from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from aeris.aero.models import AeroInput, AeroSolverSettings, FlightCondition
from aeris.aero.solvers.aerosandbox_avl import AeroSandboxAVLSolver
from aeris.aero.views import (
    geometry_view_from_case,
    geometry_view_from_run_dir,
)
from aeris.common.config import load_yaml_config
from aeris.generators.bwb_segmented_v1.generator import BwbSegmentedV1Generator

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a small manual aero validation campaign for AERIS."
    )

    parser.add_argument(
        "--geometry-config",
        type=str,
        required=True,
        help="Path to geometry config YAML used to generate the baseline geometry.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="Directory where campaign outputs will be written.",
    )
    parser.add_argument(
        "--avl-command",
        type=str,
        default=None,
        help="Optional AVL executable path/command.",
    )
    parser.add_argument(
        "--generator-id",
        type=str,
        default="bwb_segmented_v1",
        help="Geometry generator registry id.",
    )
    parser.add_argument(
        "--alpha-values",
        type=float,
        nargs="+",
        default=[-2.0, 0.0, 2.0, 4.0, 6.0],
        help="Alpha sweep values in degrees.",
    )
    parser.add_argument(
        "--velocity",
        type=float,
        default=28.0,
        help="Velocity in m/s.",
    )
    parser.add_argument(
        "--altitude",
        type=float,
        default=1500.0,
        help="Altitude in meters.",
    )
    parser.add_argument(
        "--beta",
        type=float,
        default=0.0,
        help="Beta in degrees.",
    )
    parser.add_argument(
        "--panel-spanwise",
        type=int,
        nargs=2,
        default=[4, 6],
        help="Two spanwise resolutions for sensitivity check.",
    )
    parser.add_argument(
        "--panel-chordwise",
        type=int,
        nargs=2,
        default=[8, 10],
        help="Two chordwise resolutions for sensitivity check.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_config = load_yaml_config(args.geometry_config)

    if args.generator_id != "bwb_segmented_v1":
        raise ValueError(
            f"This campaign script currently supports only generator_id='bwb_segmented_v1', "
            f"got '{args.generator_id}'."
        )

    generator = BwbSegmentedV1Generator()
    generator_config = generator.build_config(raw_config)

    seed = None
    try:
        seed = generator_config.generator.seed
    except Exception:
        pass

    geometry_case_dir = output_dir / "baseline_geometry_case"
    geometry_case_dir.mkdir(parents=True, exist_ok=True)

    sample = generator.sample_one(generator_config, seed=seed)

    case = generator.run_full_case(
        sample=sample,
        config=generator_config,
        output_dir=geometry_case_dir,
        save_plot=False,
        build_aerosandbox=True,
    )

    native_view = geometry_view_from_case(
        case=case,
        generator_id=args.generator_id,
        source_policy="native",
    )

    reconstruct_view = geometry_view_from_run_dir(
        run_dir=geometry_case_dir,
        generator_id=args.generator_id,
    )

    campaign_rows: list[dict[str, Any]] = []

    # 1) Alpha sweep in native mode
    native_root = output_dir / "native_alpha_sweep"
    native_root.mkdir(parents=True, exist_ok=True)
    for alpha in args.alpha_values:
        row = run_single_case(
            geometry_view=native_view,
            output_dir=native_root / f"alpha_{alpha:+.1f}".replace("+", "p").replace("-", "m"),
            alpha_deg=alpha,
            beta_deg=args.beta,
            velocity_mps=args.velocity,
            altitude_m=args.altitude,
            p_rad_s=0.0,
            q_rad_s=0.0,
            r_rad_s=0.0,
            avl_command=args.avl_command,
            panel_cfg={
                "spanwise_resolution": args.panel_spanwise[0],
                "chordwise_resolution": args.panel_chordwise[0],
            },
            tag="native_alpha_sweep",
            mode="native",
        )
        campaign_rows.append(row)

    # 2) Alpha sweep in reconstructed mode
    reconstruct_root = output_dir / "reconstruct_alpha_sweep"
    reconstruct_root.mkdir(parents=True, exist_ok=True)
    for alpha in args.alpha_values:
        row = run_single_case(
            geometry_view=reconstruct_view,
            output_dir=reconstruct_root / f"alpha_{alpha:+.1f}".replace("+", "p").replace("-", "m"),
            alpha_deg=alpha,
            beta_deg=args.beta,
            velocity_mps=args.velocity,
            altitude_m=args.altitude,
            p_rad_s=0.0,
            q_rad_s=0.0,
            r_rad_s=0.0,
            avl_command=args.avl_command,
            panel_cfg={
                "spanwise_resolution": args.panel_spanwise[0],
                "chordwise_resolution": args.panel_chordwise[0],
            },
            tag="reconstruct_alpha_sweep",
            mode="reconstruct",
        )
        campaign_rows.append(row)

    # 3) Panel sensitivity at one representative alpha
    ref_alpha = 4.0
    sens_root = output_dir / "panel_sensitivity"
    sens_root.mkdir(parents=True, exist_ok=True)

    panel_sets = [
        {
            "name": "low",
            "spanwise_resolution": args.panel_spanwise[0],
            "chordwise_resolution": args.panel_chordwise[0],
        },
        {
            "name": "medium",
            "spanwise_resolution": args.panel_spanwise[1],
            "chordwise_resolution": args.panel_chordwise[1],
        },
    ]

    for panel in panel_sets:
        row = run_single_case(
            geometry_view=native_view,
            output_dir=sens_root / panel["name"],
            alpha_deg=ref_alpha,
            beta_deg=args.beta,
            velocity_mps=args.velocity,
            altitude_m=args.altitude,
            p_rad_s=0.0,
            q_rad_s=0.0,
            r_rad_s=0.0,
            avl_command=args.avl_command,
            panel_cfg={
                "spanwise_resolution": panel["spanwise_resolution"],
                "chordwise_resolution": panel["chordwise_resolution"],
            },
            tag="panel_sensitivity",
            mode="native",
        )
        row["panel_name"] = panel["name"]
        campaign_rows.append(row)

    write_campaign_csv(output_dir / "campaign_summary.csv", campaign_rows)
    write_campaign_json(output_dir / "campaign_summary.json", campaign_rows)
    print_summary(campaign_rows)


def run_single_case(
    *,
    geometry_view,
    output_dir: Path,
    alpha_deg: float,
    beta_deg: float,
    velocity_mps: float,
    altitude_m: float,
    p_rad_s: float,
    q_rad_s: float,
    r_rad_s: float,
    avl_command: str | None,
    panel_cfg: dict[str, Any],
    tag: str,
    mode: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    solver = AeroSandboxAVLSolver()
    flight_condition = FlightCondition(
        alpha_deg=alpha_deg,
        beta_deg=beta_deg,
        mach=None,  # current policy: mach treated as metadata/QC, not controlling input
        velocity_mps=velocity_mps,
        altitude_m=altitude_m,
        p_rad_s=p_rad_s,
        q_rad_s=q_rad_s,
        r_rad_s=r_rad_s,
    )

    settings = AeroSolverSettings(
        avl_command=avl_command,
        timeout_sec=60,
        verbose=False,
        solver_options={
            "paneling": panel_cfg,
            "save_surface_forces": False,
            "save_element_forces": False,
        },
    )

    aero_input = AeroInput(
        geometry=geometry_view,
        flight_condition=flight_condition,
        settings=settings,
        case_id=output_dir.name,
        provenance={
            "campaign_tag": tag,
            "mode": mode,
        },
    )

    result = solver.run_case(aero_input=aero_input, output_dir=output_dir)

    row = {
        "tag": tag,
        "mode": mode,
        "case_dir": str(output_dir),
        "status": result.status.value,
        "alpha_deg": alpha_deg,
        "beta_deg": beta_deg,
        "velocity_mps": velocity_mps,
        "altitude_m": altitude_m,
        "p_rad_s": p_rad_s,
        "q_rad_s": q_rad_s,
        "r_rad_s": r_rad_s,
        "cl": result.cl,
        "cd": result.cd,
        "cm": result.cm,
        "l_over_d": result.l_over_d,
        "cy": result.cy,
        "cl_roll": result.cl_roll,
        "cn": result.cn,
        "x_np": result.x_np,
        "clb": result.stability_axis_derivatives.get("Clb"),
        "cnb": result.stability_axis_derivatives.get("Cnb"),
        "clr": result.stability_axis_derivatives.get("Clr"),
        "cnr": result.stability_axis_derivatives.get("Cnr"),
        "spiral_metric": result.derived_metrics.get("spiral_metric"),
        "runtime_sec": result.runtime_sec,
        "warning_count": len(result.warnings),
        "warnings": " | ".join(result.warnings),
        "failure_reason": None if result.failure is None else result.failure.reason,
        "failure_message": None if result.failure is None else result.failure.message,
    }
    return row


def write_campaign_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    fieldnames: list[str] = []
    seen: set[str] = set()

    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            normalized_row = {key: row.get(key) for key in fieldnames}
            writer.writerow(normalized_row)

def write_campaign_json(path: Path, rows: list[dict[str, Any]]) -> None:
    payload = {
        "n_cases": len(rows),
        "rows": rows,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def print_summary(rows: list[dict[str, Any]]) -> None:
    print("\n=== AERIS AERO VALIDATION CAMPAIGN SUMMARY ===")
    print(f"Total cases: {len(rows)}")

    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1

    print("Status counts:")
    for status, count in sorted(by_status.items()):
        print(f"  - {status}: {count}")

    print("\nNative vs reconstruct quick comparison:")
    native = [r for r in rows if r["tag"] == "native_alpha_sweep" and r["status"] == "success"]
    recon = [r for r in rows if r["tag"] == "reconstruct_alpha_sweep" and r["status"] == "success"]

    native_by_alpha = {r["alpha_deg"]: r for r in native}
    recon_by_alpha = {r["alpha_deg"]: r for r in recon}

    for alpha in sorted(set(native_by_alpha.keys()) & set(recon_by_alpha.keys())):
        n = native_by_alpha[alpha]
        r = recon_by_alpha[alpha]
        print(
            f"  alpha={alpha:+.1f}: "
            f"dCL={safe_diff(n['cl'], r['cl']):+.6f}, "
            f"dCD={safe_diff(n['cd'], r['cd']):+.6f}, "
            f"dCm={safe_diff(n['cm'], r['cm']):+.6f}, "
            f"dSpiral={safe_diff(n['spiral_metric'], r['spiral_metric']):+.6f}"
        )

    print("\nPanel sensitivity quick comparison:")
    panel_rows = [r for r in rows if r["tag"] == "panel_sensitivity" and r["status"] == "success"]
    if len(panel_rows) >= 2:
        base = panel_rows[0]
        for other in panel_rows[1:]:
            print(
                f"  {base.get('panel_name', 'base')} vs {other.get('panel_name', 'other')}: "
                f"dCL={safe_diff(base['cl'], other['cl']):+.6f}, "
                f"dCD={safe_diff(base['cd'], other['cd']):+.6f}, "
                f"dCm={safe_diff(base['cm'], other['cm']):+.6f}, "
                f"dClb={safe_diff(base['clb'], other['clb']):+.6f}, "
                f"dCnb={safe_diff(base['cnb'], other['cnb']):+.6f}, "
                f"dClr={safe_diff(base['clr'], other['clr']):+.6f}, "
                f"dCnr={safe_diff(base['cnr'], other['cnr']):+.6f}"
            )

    print("\nTrend sanity check (native alpha sweep):")
    native_sorted = sorted(native, key=lambda r: r["alpha_deg"])
    for row in native_sorted:
        print(
            f"  alpha={row['alpha_deg']:+.1f} -> "
            f"CL={fmt(row['cl'])}, CD={fmt(row['cd'])}, Cm={fmt(row['cm'])}, "
            f"L/D={fmt(row['l_over_d'])}, Spiral={fmt(row['spiral_metric'])}"
        )


def fmt(value: Any) -> str:
    if value is None:
        return "None"
    try:
        return f"{float(value):+.6f}"
    except Exception:
        return str(value)


def safe_diff(a: Any, b: Any) -> float:
    try:
        return float(b) - float(a)
    except Exception:
        return float("nan")


if __name__ == "__main__":
    main()