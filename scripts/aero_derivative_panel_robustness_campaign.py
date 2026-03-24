from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from aeris.aero.models import AeroInput, AeroSolverSettings, FlightCondition
from aeris.aero.solvers.aerosandbox_avl import AeroSandboxAVLSolver
from aeris.aero.views import geometry_view_from_case
from aeris.common.config import load_yaml_config
from aeris.generators.bwb_segmented_v1.generator import BwbSegmentedV1Generator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run derivative robustness vs paneling campaign for AERIS aero."
    )

    parser.add_argument("--geometry-config", type=str, required=True)
    parser.add_argument("--output-dir", type=str, required=True)
    parser.add_argument("--avl-command", type=str, default=None)
    parser.add_argument("--generator-id", type=str, default="bwb_segmented_v1")

    parser.add_argument(
        "--alpha-values",
        type=float,
        nargs="+",
        default=[0.0, 4.0],
        help="Alpha values to evaluate.",
    )
    parser.add_argument("--velocity", type=float, default=28.0)
    parser.add_argument("--altitude", type=float, default=1500.0)

    parser.add_argument(
        "--panel-levels",
        type=str,
        nargs="+",
        default=["4x8", "6x10", "8x12"],
        help="Panel levels as spanwise x chordwise, e.g. 4x8 6x10 8x12",
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

    geometry_view = geometry_view_from_case(
        case=case,
        generator_id=args.generator_id,
        source_policy="native",
    )

    panel_levels = [parse_panel_level(s) for s in args.panel_levels]

    rows: list[dict[str, Any]] = []

    for alpha in args.alpha_values:
        for panel in panel_levels:
            panel_name = f"{panel['spanwise_resolution']}x{panel['chordwise_resolution']}"
            case_dir = output_dir / f"a{alpha:+.1f}_{panel_name}".replace("+", "p").replace("-", "m")

            row = run_single_case(
                geometry_view=geometry_view,
                output_dir=case_dir,
                alpha_deg=alpha,
                beta_deg=0.0,
                velocity_mps=args.velocity,
                altitude_m=args.altitude,
                p_rad_s=0.0,
                q_rad_s=0.0,
                r_rad_s=0.0,
                avl_command=args.avl_command,
                panel_cfg=panel,
                panel_name=panel_name,
            )
            rows.append(row)

    write_csv(output_dir / "derivative_panel_robustness_summary.csv", rows)
    write_json(output_dir / "derivative_panel_robustness_summary.json", rows)
    print_summary(rows, alpha_values=args.alpha_values)


def parse_panel_level(text: str) -> dict[str, int]:
    cleaned = text.strip().lower()
    if "x" not in cleaned:
        raise ValueError(f"Invalid panel level '{text}'. Expected format like 4x8.")
    span_s, chord_s = cleaned.split("x", 1)
    span = int(span_s)
    chord = int(chord_s)
    if span <= 0 or chord <= 0:
        raise ValueError(f"Invalid panel level '{text}'. Resolutions must be positive.")
    return {
        "spanwise_resolution": span,
        "chordwise_resolution": chord,
    }


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
    panel_name: str,
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
            "campaign": "derivative_panel_robustness",
            "panel_name": panel_name,
        },
    )

    result = solver.run_case(aero_input=aero_input, output_dir=output_dir)

    return {
        "case_dir": str(output_dir),
        "status": result.status.value,
        "panel_name": panel_name,
        "alpha_deg": alpha_deg,
        "beta_deg": beta_deg,
        "velocity_mps": velocity_mps,
        "altitude_m": altitude_m,
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
    print("\n=== AERIS DERIVATIVE PANEL ROBUSTNESS CAMPAIGN ===")
    print(f"Total cases: {len(rows)}")

    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1

    print("Status counts:")
    for status, count in sorted(by_status.items()):
        print(f"  - {status}: {count}")

    for alpha in alpha_values:
        print(f"\n--- alpha = {alpha:+.1f} deg ---")
        subset = [r for r in rows if r["alpha_deg"] == alpha and r["status"] == "success"]
        subset = sorted(subset, key=lambda r: panel_key(r["panel_name"]))

        for row in subset:
            print(
                f"  {row['panel_name']}: "
                f"CL={fmt(row['cl'])}, CD={fmt(row['cd'])}, Cm={fmt(row['cm'])}, "
                f"Clb={fmt(row['clb'])}, Cnb={fmt(row['cnb'])}, "
                f"Clr={fmt(row['clr'])}, Cnr={fmt(row['cnr'])}, "
                f"Spiral={fmt(row['spiral_metric'])}"
            )

        if len(subset) >= 2:
            base = subset[0]
            for other in subset[1:]:
                print(
                    f"  delta {base['panel_name']} -> {other['panel_name']}: "
                    f"dCL={diff(base['cl'], other['cl'])}, "
                    f"dCD={diff(base['cd'], other['cd'])}, "
                    f"dCm={diff(base['cm'], other['cm'])}, "
                    f"dClb={diff(base['clb'], other['clb'])}, "
                    f"dCnb={diff(base['cnb'], other['cnb'])}, "
                    f"dClr={diff(base['clr'], other['clr'])}, "
                    f"dCnr={diff(base['cnr'], other['cnr'])}, "
                    f"dSpiral={diff(base['spiral_metric'], other['spiral_metric'])}"
                )


def panel_key(name: str) -> tuple[int, int]:
    span_s, chord_s = name.lower().split("x", 1)
    return int(span_s), int(chord_s)


def fmt(value: Any) -> str:
    if value is None:
        return "None"
    try:
        return f"{float(value):+.6f}"
    except Exception:
        return str(value)


def diff(a: Any, b: Any) -> str:
    try:
        return f"{(float(b) - float(a)):+.6f}"
    except Exception:
        return "nan"


if __name__ == "__main__":
    main()