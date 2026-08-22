"""Surface-only comparison of cap4 tip-cap variants on one geometry.

Stage 01 found that the worst surface cell on every locked geometry sits at the
corners of the one-block `airfoil_face` tip cap, with scale-invariant metrics
identical to 11-12 significant figures across differently sized aircraft. That
makes the defect structural rather than geometry dependent.

This probe rebuilds the same geometry with several tip treatments and compares
the tip-block quality. It is surface-only: no pyHyp march, no solver.

Run from the repository root:

    .venv/bin/python AERIS_MESH_STUDY/03_cap4_epse/tip_topology_probe.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import yaml  # noqa: E402

from aeris.cfd.meshing.registry import get_topology  # noqa: E402
from aeris.cfd.presets.registry import get_preset  # noqa: E402
from aeris.dataset.sampling.samplers.lhs_v1 import build_lhs_design_matrix  # noqa: E402
from aeris.generators.bwb_segmented_v1.params import (  # noqa: E402
    BWBDesignSample,
    build_bwb_generator_config,
)
from aeris.geometry.registry import get_geometry_generator  # noqa: E402

GEOMETRY_CONFIG = REPO_ROOT / "configs/geometry/bwb.yaml"
OUT_DIR = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/stage01/tip_topology_probe"
REPORT_JSON = Path(__file__).resolve().parent / "tip_topology_probe_report.json"
REPORT_MD = Path(__file__).resolve().parent / "tip_topology_probe_report.md"

# Stage 01 L3 recipe, held fixed except for the tip treatment under test.
BASE_PARAMS: dict[str, object] = {
    "oml_topology": "cap4",
    "points_per_side": 49,
    "spanwise_panels": 16,
    "cap_wrap_points": 9,
    "tip_radial_points": 7,
    "cap_wrap_x": 0.40,
    "tip_smooth_iters": 0,
    "te_thickness": 0.005,
    "te_thickness_abs_floor": 0.0,
    "te_base_points": 0,
    "min_shape_metric": 1.0e-6,
    "max_adjacent_normal_angle": 180.0,
    "chordwise_distribution": "uniform",
    "chordwise_beta": 2.0,
    "spanwise_distribution": "uniform",
    "spanwise_beta": 2.0,
    "spanwise_allocation": "proportional",
}

VARIANTS: list[tuple[str, str, dict[str, object], str]] = [
    ("A_baseline", "wing_cap4_v1", {}, "Stage 01 L3 control: airfoil_face cap, no tip smoothing"),
    (
        "B_smooth20",
        "wing_cap4_v1",
        {"tip_smooth_iters": 20},
        "airfoil_face cap + 20 tip smoothing iterations",
    ),
    ("C_cgrid", "wing_cap4_cgrid_face_v1", {}, "two-block C-grid tip face, no tip smoothing"),
    (
        "D_cgrid_smooth20",
        "wing_cap4_cgrid_face_v1",
        {"tip_smooth_iters": 20},
        "C-grid tip face + 20 tip smoothing iterations",
    ),
]


def build_sample_zero() -> BWBDesignSample:
    """Rebuild lhs7_00, the first frozen epsE calibration geometry."""
    config = build_bwb_generator_config(yaml.safe_load(GEOMETRY_CONFIG.read_text()))
    matrix = build_lhs_design_matrix(config, 10, np.random.default_rng(7))
    names = config.active_design_variable_names()
    return BWBDesignSample(
        **{name: float(v) for name, v in zip(names, matrix[0], strict=True)}
    ), config


def tip_blocks(report: dict) -> list[dict]:
    return [b for b in report.get("blocks", []) if "tip" in b["name"]]


def main() -> int:
    sample, config = build_sample_zero()
    generator = get_geometry_generator("bwb_segmented")

    preset_surface = dict(get_preset("smoke").surface)

    results = []
    for name, topology_id, overrides, description in VARIANTS:
        params = dict(preset_surface)
        params.update(BASE_PARAMS)
        params.update(overrides)
        work = OUT_DIR / name
        work.mkdir(parents=True, exist_ok=True)

        entry: dict[str, object] = {
            "variant": name,
            "topology_id": topology_id,
            "description": description,
            "overrides": overrides,
        }
        try:
            case = generator.run_full_case(
                sample=sample,
                config=config,
                output_dir=work / "geometry",
                save_plot=False,
                build_aerosandbox=True,
            )
            get_topology(topology_id).generate(case.wing, work / "surface", params)
            report = json.loads((work / "surface" / "surface_report.json").read_text())
        except Exception as exc:  # noqa: BLE001 - record per-variant failure
            entry["error"] = f"{type(exc).__name__}: {exc}"
            results.append(entry)
            print(f"{name:18s} FAILED: {entry['error']}")
            continue

        g = report["global"]
        tips = tip_blocks(report)
        worst_tip = min(tips, key=lambda b: b["min_shape_metric"]) if tips else None
        entry.update(
            {
                "error": None,
                "accepted_pre_pyhyp": report.get("accepted_pre_pyhyp"),
                "tip_topology": report.get("tip_topology"),
                "tip_cap_info": report.get("tip_cap"),
                "global_min_shape_metric": g["min_shape_metric"],
                "global_max_equiangle_skewness": g["max_equiangle_skewness"],
                "global_min_scaled_jacobian": g["min_scaled_jacobian"],
                "global_max_adjacent_normal_angle_deg": g["max_adjacent_normal_angle_deg"],
                "tip_block_names": [b["name"] for b in tips],
                "worst_tip_block": worst_tip["name"] if worst_tip else None,
                "worst_tip_min_shape_metric": worst_tip["min_shape_metric"] if worst_tip else None,
                "worst_tip_max_equiangle_skewness": (
                    max(b["max_equiangle_skewness"] for b in tips) if tips else None
                ),
                "worst_tip_min_scaled_jacobian": (
                    min(b["min_scaled_jacobian"] for b in tips) if tips else None
                ),
                "total_cells": g.get("total_cells"),
            }
        )
        results.append(entry)
        print(
            f"{name:18s} shape={entry['global_min_shape_metric']:.4e} "
            f"skew={entry['global_max_equiangle_skewness']:.4f} "
            f"jac={entry['global_min_scaled_jacobian']:.4e} "
            f"tip={entry['worst_tip_block']}"
        )

    payload = {
        "schema": "aeris.mesh_study.stage01_tip_topology_probe.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "surface-only comparison of cap4 tip-cap variants on lhs7_00",
        "geometry_config": str(GEOMETRY_CONFIG),
        "sample_id": "lhs7_00",
        "base_params": BASE_PARAMS,
        "variants": results,
    }
    REPORT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    lines = [
        "# lhs7_00 Tip-Topology Probe",
        "",
        "Surface-only. No pyHyp march, no solver. Everything except the tip",
        "treatment is held at the Stage 01 L3 recipe.",
        "",
        (
            "| variant | topology | min shape | max skew | min scaled jac | "
            "worst tip block | accepted |"
        ),
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for r in results:
        if r.get("error"):
            lines.append(f"| {r['variant']} | {r['topology_id']} | ERROR | ERROR | ERROR | - | - |")
            continue
        lines.append(
            f"| {r['variant']} | {r['topology_id']} | {r['global_min_shape_metric']:.4e} | "
            f"{r['global_max_equiangle_skewness']:.4f} | {r['global_min_scaled_jacobian']:.4e} | "
            f"{r['worst_tip_block']} | {r['accepted_pre_pyhyp']} |"
        )
    lines.append("")
    REPORT_MD.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {REPORT_JSON}\nwrote {REPORT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
