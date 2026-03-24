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
        description="Run a derivative sign sanity campaign for AERIS aero."
    )

    parser.add_argument(
        "--geometry-config",
        type=str,
        required=True,
        help="Path to baseline geometry config YAML.",
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
        help="Currently supports only bwb_segmented_v1.",
    )
    parser.add_argument(
        "--alpha-values",
        type=float,
        nargs="+",
        default=[0.0, 4.0],
        help="Baseline alpha values to probe.",
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
        "--beta-perturb",
        type=float,
        default=2.0,
        help="Beta perturbation in degrees.",
    )
    parser.add_argument(
        "--p-perturb",
        type=float,
        default=0.05,
        help="Roll-rate perturbation in rad/s.",
    )
    parser.add_argument(
        "--r-perturb",
        type=float,
        default=0.05,
        help="Yaw-rate perturbation in rad/s.",
    )
    parser.add_argument(
        "--panel-spanwise",
        type=int,
        default=4,
        help="Spanwise resolution.",
    )
    parser.add_argument(
        "--panel-chordwise",
        type=int,
        default=8,
        help="Chordwise resolution.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_config = load_yaml_config(args.geometry_config)

    if args.generator_id != "bwb_segmented_v1":
        raise ValueError(
            f"This script currently supports only generator_id='bwb_segmented_v1', "
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

    panel_cfg = {
        "spanwise_resolution": args.panel_spanwise,
        "chordwise_resolution": args.panel_chordwise,
    }

    rows: list[dict[str, Any]] = []

    for mode_name, geometry_view in [
        ("native", native_view),
        ("reconstruct", reconstruct_view),
    ]:
        mode_root = output_dir / mode_name
        mode_root.mkdir(parents=True, exist_ok=True)

        for alpha in args.alpha_values:
            cases = [
                ("baseline", alpha, 0.0, 0.0, 0.0, 0.0),
                ("beta_pos", alpha, +args.beta_perturb, 0.0, 0.0, 0.0),
                ("beta_neg", alpha, -args.beta_perturb, 0.0, 0.0, 0.0),
                ("p_pos", alpha, 0.0, +args.p_perturb, 0.0, 0.0),
                ("p_neg", alpha, 0.0, -args.p_perturb, 0.0, 0.0),
                ("r_pos", alpha, 0.0, 0.0, 0.0, +args.r_perturb),
                ("r_neg", alpha, 0.0, 0.0, 0.0, -args.r_perturb),
            ]

            for case_name, alpha_deg, beta_deg, p_rad_s, q_rad_s, r_rad_s in cases:
                case_dir = mode_root / f"a{alpha_deg:+.1f}_{case_name}".replace("+", "p").replace("-", "m")
                row = run_single_case(
                    geometry_view=geometry_view,
                    output_dir=case_dir,
                    alpha_deg=alpha_deg,
                    beta_deg=beta_deg,
                    velocity_mps=args.velocity,
                    altitude_m=args.altitude,
                    p_rad_s=p_rad_s,
                    q_rad_s=q_rad_s,
                    r_rad_s=r_rad_s,
                    avl_command=args.avl_command,
                    panel_cfg=panel_cfg,
                    mode=mode_name,
                    case_name=case_name,
                )
                rows.append(row)

    write_csv(output_dir / "derivative_sanity_summary.csv", rows)
    write_json(output_dir / "derivative_sanity_summary.json", rows)
    print_summary(rows, alpha_values=args.alpha_values)


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
    mode: str,
    case_name: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    solver = AeroSandboxAVLSolver()

    flight_condition = FlightCondition(
        alpha_deg=alpha_deg,
        beta_deg=beta_deg,
        mach=None,
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
            "campaign": "derivative_sign_sanity",
            "mode": mode,
            "case_name": case_name,
        },
    )

    result = solver.run_case(aero_input=aero_input, output_dir=output_dir)

    return {
        "mode": mode,
        "case_name": case_name,
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
        "cy": result.cy,
        "cl_roll": result.cl_roll,
        "cn": result.cn,
        "clb": result.stability_axis_derivatives.get("Clb"),
        "cnb": result.stability_axis_derivatives.get("Cnb"),
        "clr": result.stability_axis_derivatives.get("Clr"),
        "cnr": result.stability_axis_derivatives.get("Cnr"),
        "cyp": result.stability_axis_derivatives.get("CYp"),
        "cyr": result.stability_axis_derivatives.get("CYr"),
        "cnp": result.stability_axis_derivatives.get("Cnp"),
        "spiral_metric": result.derived_metrics.get("spiral_metric"),
        "runtime_sec": result.runtime_sec,
        "warning_count": len(result.warnings),
        "warnings": " | ".join(result.warnings),
        "failure_reason": None if result.failure is None else result.failure.reason,
        "failure_message": None if result.failure is None else result.failure.message,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
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
            writer.writerow({key: row.get(key) for key in fieldnames})


def write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    payload = {"n_cases": len(rows), "rows": rows}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def print_summary(rows: list[dict[str, Any]], *, alpha_values: list[float]) -> None:
    print("\n=== AERIS DERIVATIVE SIGN SANITY CAMPAIGN ===")
    print(f"Total cases: {len(rows)}")

    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1

    print("Status counts:")
    for status, count in sorted(by_status.items()):
        print(f"  - {status}: {count}")

    for alpha in alpha_values:
        print(f"\n--- alpha = {alpha:+.1f} deg ---")
        for mode in ("native", "reconstruct"):
            subset = [
                r for r in rows
                if r["mode"] == mode and r["alpha_deg"] == alpha and r["status"] == "success"
            ]
            by_name = {r["case_name"]: r for r in subset}

            baseline = by_name.get("baseline")
            beta_pos = by_name.get("beta_pos")
            beta_neg = by_name.get("beta_neg")
            p_pos = by_name.get("p_pos")
            p_neg = by_name.get("p_neg")
            r_pos = by_name.get("r_pos")
            r_neg = by_name.get("r_neg")

            print(f"Mode: {mode}")

            if baseline is not None:
                print(
                    f"  baseline -> CY={fmt(baseline['cy'])}, "
                    f"Cl={fmt(baseline['cl_roll'])}, "
                    f"Cn={fmt(baseline['cn'])}, "
                    f"Clb={fmt(baseline['clb'])}, "
                    f"Cnb={fmt(baseline['cnb'])}, "
                    f"Clr={fmt(baseline['clr'])}, "
                    f"Cnr={fmt(baseline['cnr'])}"
                )

            if beta_pos is not None and beta_neg is not None:
                print(
                    f"  beta +/- -> dCY={sym_diff(beta_pos['cy'], beta_neg['cy'])}, "
                    f"dCl={sym_diff(beta_pos['cl_roll'], beta_neg['cl_roll'])}, "
                    f"dCn={sym_diff(beta_pos['cn'], beta_neg['cn'])}"
                )

            if p_pos is not None and p_neg is not None:
                print(
                    f"  p +/-    -> dCY={sym_diff(p_pos['cy'], p_neg['cy'])}, "
                    f"dCl={sym_diff(p_pos['cl_roll'], p_neg['cl_roll'])}, "
                    f"dCn={sym_diff(p_pos['cn'], p_neg['cn'])}"
                )

            if r_pos is not None and r_neg is not None:
                print(
                    f"  r +/-    -> dCY={sym_diff(r_pos['cy'], r_neg['cy'])}, "
                    f"dCl={sym_diff(r_pos['cl_roll'], r_neg['cl_roll'])}, "
                    f"dCn={sym_diff(r_pos['cn'], r_neg['cn'])}"
                )


def fmt(value: Any) -> str:
    if value is None:
        return "None"
    try:
        return f"{float(value):+.6f}"
    except Exception:
        return str(value)


def sym_diff(pos: Any, neg: Any) -> str:
    try:
        return f"{(float(pos) - float(neg)):+.6f}"
    except Exception:
        return "nan"


if __name__ == "__main__":
    main()