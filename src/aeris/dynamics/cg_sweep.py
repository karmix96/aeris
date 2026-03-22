from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json

from aeris.aero.io import read_aero_result
from aeris.dynamics.analysis import build_dynamics_foundation_result
from aeris.dynamics.models import InertiaPlaceholders, MassProperties, TrimDefinition


def linspace(start: float, stop: float, n: int) -> list[float]:
    if n < 2:
        return [float(start)]
    step = (stop - start) / (n - 1)
    return [float(start + i * step) for i in range(n)]

def estimate_zero_crossing(cases: list[dict]) -> float | None:
    """
    Linear interpolation estimate of CG location where static_margin crosses zero.
    """
    for a, b in zip(cases[:-1], cases[1:]):
        sm_a = a.get("static_margin")
        sm_b = b.get("static_margin")
        if sm_a is None or sm_b is None:
            continue

        if sm_a == 0.0:
            return float(a["x_cg_m"])
        if sm_b == 0.0:
            return float(b["x_cg_m"])

        if sm_a * sm_b < 0.0:
            x_a = float(a["x_cg_m"])
            x_b = float(b["x_cg_m"])
            return x_a + (0.0 - sm_a) * (x_b - x_a) / (sm_b - sm_a)

    return None

def run_cg_sweep(
    *,
    run_dir: str | Path,
    mass_kg: float,
    cg_min_m: float,
    cg_max_m: float,
    n: int,
    y_cg_m: float = 0.0,
    z_cg_m: float = 0.0,
    ixx_kg_m2: float | None = None,
    iyy_kg_m2: float | None = None,
    izz_kg_m2: float | None = None,
    x_positive_aft: bool = True,
) -> dict:
    run_dir = Path(run_dir)
    aero_result = read_aero_result(run_dir)

    cg_values = linspace(cg_min_m, cg_max_m, n)
    cases = []

    for x_cg_m in cg_values:
        mass = MassProperties(
            mass_kg=mass_kg,
            x_cg_m=x_cg_m,
            y_cg_m=y_cg_m,
            z_cg_m=z_cg_m,
            inertia=InertiaPlaceholders(
                ixx_kg_m2=ixx_kg_m2,
                iyy_kg_m2=iyy_kg_m2,
                izz_kg_m2=izz_kg_m2,
            ),
        )

        result = build_dynamics_foundation_result(
            aero_result=aero_result,
            mass_properties=mass,
            trim_definition=TrimDefinition(
                enabled=False,
                notes="Schema only. No trim solver implemented.",
            ),
            source_run_dir=str(run_dir),
            x_positive_aft=x_positive_aft,
        )

        cases.append(
            {
                "x_cg_m": x_cg_m,
                "static_margin": result.stability_metrics.static_margin,
                "static_margin_percent_mac": result.stability_metrics.static_margin_percent_mac,
                "cma": result.stability_metrics.cma,
                "cma_consistent_with_static_margin": result.stability_metrics.cma_consistent_with_static_margin,
                "longitudinal_interpretation": result.stability_metrics.longitudinal_interpretation,
                "x_np_m": result.stability_metrics.x_np_m,
                "mac_m": result.stability_metrics.mac_m,
            }
        )

    positive_cases = [
        c for c in cases
        if c["static_margin"] is not None and c["static_margin"] > 0.0
    ]

    zero_crossing_estimate_m = estimate_zero_crossing(cases)
    
    summary = {
        "run_dir": str(run_dir),
        "mass_kg": mass_kg,
        "cg_min_m": cg_min_m,
        "cg_max_m": cg_max_m,
        "n": n,
        "x_positive_aft": x_positive_aft,
        "cases": cases,
        "stable_cg_min_m": None if not positive_cases else min(c["x_cg_m"] for c in positive_cases),
        "stable_cg_max_m": None if not positive_cases else max(c["x_cg_m"] for c in positive_cases),
        "static_margin_zero_crossing_estimate_m": zero_crossing_estimate_m,
    }

    return summary


def write_cg_sweep(summary: dict, output_dir: str | Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "cg_sweep.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return path

import csv


def write_cg_sweep_csv(summary: dict, output_dir: str | Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "cg_sweep.csv"

    cases = summary.get("cases", [])
    if not cases:
        path.write_text("", encoding="utf-8")
        return path

    fieldnames = [
        "x_cg_m",
        "static_margin",
        "static_margin_percent_mac",
        "cma",
        "cma_consistent_with_static_margin",
        "longitudinal_interpretation",
        "x_np_m",
        "mac_m",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for case in cases:
            writer.writerow({k: case.get(k) for k in fieldnames})

    return path