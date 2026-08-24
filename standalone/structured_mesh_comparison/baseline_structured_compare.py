"""Baseline flat-tip structured wing mesh comparison.

Builds one deterministic BWB baseline and runs the structured surface
approaches available in ``aeris.mesh.surface``.  The intent is inspection and
triage, not a production DOE: every case writes a ParaView-readable
``surface.vtk`` plus ``surface_report.json``; optional pyHyp canaries write
``wing_vol_*.cgns`` and ``volume_report.json`` for the surface cases that pass
pre-pyHyp QC.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import (  # noqa: E402
    build_aerosandbox_geometry,
)
from aeris.generators.bwb_segmented_v1.planform import (  # noqa: E402
    generate_bwb_planform_from_sample,
)
from aeris.generators.bwb_segmented_v1.sections import (  # noqa: E402
    build_section_geometry_from_sample,
)
from aeris.generators.bwb_segmented_v1.validation import (  # noqa: E402
    validate_planform_result,
    validate_section_geometry,
)
from aeris.mesh.pyhyp_runner import subprocess_run_pyhyp  # noqa: E402
from aeris.mesh.surface import MeshBuildError, export_surface_mesh, select_wing  # noqa: E402
from standalone.pygeo_surface_mesh_study.runner import (  # noqa: E402
    build_geometry,
    load_generator_config,
    make_sample,
)
from standalone.pygeo_surface_mesh_study.spec import load_study_spec  # noqa: E402


@dataclass(frozen=True)
class Variant:
    name: str
    source: str
    params: dict[str, Any]
    volume_level: str
    n_coarsen: int
    notes: str


def _common() -> dict[str, Any]:
    return {
        "dense_airfoil_points_per_surface": 301,
        "minimum_te_thickness": 2.0e-3,
        "te_thickness": 0.005,
        "te_thickness_abs_floor": 0.0,
        "te_base_points": 0,
        "minimum_shape_metric": 1.0e-6,
        "maximum_adjacent_normal_angle_deg": 180.0,
        "tip_dome_scale": 0.0,
        "tip_conformal_ring": False,
        "chordwise_distribution": "uniform",
        "chordwise_beta": 2.0,
        "spanwise_distribution": "uniform",
        "spanwise_beta": 2.0,
    }


def _variants() -> list[Variant]:
    common = _common()
    cap_v2 = {
        **common,
        "oml_topology": "cap4",
        "tip_topology": "airfoil_face",
        "points_per_block_side": 49,
        "spanwise_panels_per_section": 16,
        "spanwise_allocation": "proportional",
        "cap_wrap_x": 0.15,
        "cap_width_frac": 0.50,
        "cap_wrap_points": 21,
        "tip_radial_points": 9,
        "tip_smooth_iters": 20,
    }
    return [
        Variant(
            "asb_mid4_ring_flat",
            "asb",
            {
                **common,
                "oml_topology": "mid4",
                "tip_topology": "ring",
                "points_per_block_side": 49,
                "spanwise_panels_per_section": 16,
                "spanwise_allocation": "proportional",
                "tip_radial_points": 9,
                "tip_inner_scale": 0.60,
                "split_x_fore": 0.20,
            },
            "L4",
            4,
            "historical 4-block OML with flat ring + center tip cap",
        ),
        Variant(
            "asb_split8_ring_flat",
            "asb",
            {
                **common,
                "oml_topology": "split8",
                "tip_topology": "ring",
                "points_per_block_side": 49,
                "spanwise_panels_per_section": 16,
                "spanwise_allocation": "proportional",
                "tip_radial_points": 9,
                "tip_inner_scale": 0.60,
                "split_x_fore": 0.20,
            },
            "L4",
            4,
            "split LE/TE O-type with flat ring + center tip cap",
        ),
        Variant(
            "asb_cap4_airfoil_face_current_flat",
            "asb",
            {
                **common,
                "oml_topology": "cap4",
                "tip_topology": "airfoil_face",
                "points_per_block_side": 49,
                "spanwise_panels_per_section": 4,
                "spanwise_allocation": "uniform",
                "cap_wrap_x": 0.015,
                "cap_width_frac": 0.50,
                "cap_wrap_points": 17,
                "tip_radial_points": 3,
                "tip_smooth_iters": 0,
            },
            "smoke",
            1,
            "current registered smoke-style cap4 surface with flat full-airfoil tip cap",
        ),
        Variant(
            "asb_cap4_airfoil_face_v2_flat",
            "asb",
            cap_v2,
            "smoke",
            1,
            "cap4 wide-wrap v2-style flat full-airfoil tip cap",
        ),
        Variant(
            "asb_cap4_ring_v2_flat",
            "asb",
            {**cap_v2, "tip_topology": "ring", "tip_inner_scale": 0.60},
            "smoke",
            1,
            "same cap4 OML as v2-style case, but with the older flat ring tip closure",
        ),
        Variant(
            "asb_cap4_single_v2_flat",
            "asb",
            {**cap_v2, "tip_topology": "single"},
            "smoke",
            1,
            "single flat transfinite tip patch; kept because it is implemented, expected poor",
        ),
        Variant(
            "pygeo_cap4_airfoil_face_study_L3_flat",
            "pygeo",
            {
                **common,
                "oml_topology": "cap4",
                "tip_topology": "airfoil_face",
                "points_per_block_side": 49,
                "spanwise_panels_per_section": 16,
                "spanwise_allocation": "proportional",
                "cap_wrap_x": 0.40,
                "cap_width_frac": 0.50,
                "cap_wrap_points": 9,
                "tip_radial_points": 7,
                "tip_smooth_iters": 0,
            },
            "smoke",
            1,
            "pyGeo-sampled OML source with flat full-airfoil tip cap",
        ),
    ]


def _build_baseline_geometry(study_config: Path, geometry_dir: Path) -> dict[str, Any]:
    spec = load_study_spec(study_config)
    generator_config = load_generator_config(spec)
    case = spec.baseline_case()
    sample = make_sample(spec, case)

    planform = generate_bwb_planform_from_sample(sample, generator_config)
    validate_planform_result(planform)
    section_geometry = build_section_geometry_from_sample(planform, sample, generator_config)
    validate_section_geometry(section_geometry)
    asb_result = build_aerosandbox_geometry(section_geometry, generator_config)
    asb_wing = select_wing(asb_result.airplane, 0)

    pygeo_carrier, _pygeo_build, geometry = build_geometry(spec, generator_config, case)
    payload = {
        "study_config": str(study_config),
        "geometry_config": str(spec.geometry_config),
        "case_id": case.case_id,
        "tip_policy": "flat: pygeo.tip=none and tip_dome_scale=0.0 in every variant",
        "sample": sample.to_dict(),
        "planform": geometry.get("planform", {}),
        "airfoils": geometry.get("airfoils", {}),
    }
    geometry_dir.mkdir(parents=True, exist_ok=True)
    (geometry_dir / "baseline_geometry.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"asb_wing": asb_wing, "pygeo_carrier": pygeo_carrier, "metadata": payload}


def _summarize_surface(report: dict[str, Any]) -> dict[str, Any]:
    global_metrics = dict(report.get("global") or {})
    free_edges = dict(report.get("free_edges") or {})
    tip_cap = dict(report.get("tip_cap") or {})
    return {
        "accepted_pre_pyhyp": bool(report.get("accepted_pre_pyhyp")),
        "block_count": report.get("block_count"),
        "cells": global_metrics.get("total_cells"),
        "min_shape_metric": global_metrics.get("min_shape_metric"),
        "min_scaled_jacobian": global_metrics.get("min_scaled_jacobian"),
        "max_skewness": global_metrics.get("max_equiangle_skewness"),
        "max_aspect_ratio": global_metrics.get("max_aspect_ratio"),
        "max_growth_ratio": global_metrics.get("max_growth_ratio"),
        "max_adjacent_normal_angle_deg": global_metrics.get("max_adjacent_normal_angle_deg"),
        "closed_except_root": free_edges.get("closed_except_root"),
        "off_root_free_edges": free_edges.get("off_root_free_edges"),
        "tip_topology": report.get("tip_topology"),
        "tip_has_collar_ring": tip_cap.get("collar_ring"),
        "tip_cap_topology": tip_cap.get("topology"),
        "surface_vtk": (report.get("artifacts") or {}).get("vtk", {}).get("path"),
    }


def _summarize_volume(report: dict[str, Any] | None, error: str | None) -> dict[str, Any]:
    if report is None:
        return {"attempted": False, "status": "not_run", "error": error}
    audit = report.get("volume_audit") or {}
    march = report.get("march_metrics") or {}
    return {
        "attempted": True,
        "status": "ok" if error is None else "failed",
        "error": error,
        "output_cgns": report.get("output_cgns"),
        "N": report.get("N"),
        "coarsen": report.get("coarsen"),
        "elapsed_seconds": report.get("elapsed_seconds"),
        "min_march_quality": march.get("min_quality"),
        "low_quality_layers": march.get("low_quality_layers"),
        "volume_audit_classification": audit.get("classification"),
        "inverted_cells": audit.get("inverted_cells"),
        "inverted_fraction": audit.get("inverted_fraction"),
    }


def run(args: argparse.Namespace) -> int:
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    geometry = _build_baseline_geometry(args.study_config.resolve(), out / "geometry")

    rows: list[dict[str, Any]] = []
    for variant in _variants():
        t0 = time.perf_counter()
        case_dir = out / variant.name
        surface_dir = case_dir / "surface"
        source = geometry["asb_wing"] if variant.source == "asb" else geometry["pygeo_carrier"]
        row: dict[str, Any] = {
            "name": variant.name,
            "source": variant.source,
            "notes": variant.notes,
            "surface_dir": str(surface_dir),
            "params": variant.params,
            "volume_level": variant.volume_level,
            "n_coarsen": variant.n_coarsen,
        }
        print(f"[surface] {variant.name}")
        try:
            surface_report = export_surface_mesh(source, surface_dir, **variant.params)
            row["surface"] = _summarize_surface(surface_report)
            row["surface_status"] = "ok"
        except Exception as exc:  # noqa: BLE001 - compare every implemented approach
            row["surface_status"] = "failed"
            row["surface"] = {"accepted_pre_pyhyp": False}
            row["surface_error"] = f"{type(exc).__name__}: {exc}"
            row["traceback"] = traceback.format_exc()
            rows.append(row)
            print(f"  surface failed: {row['surface_error']}")
            continue

        if args.volume and row["surface"].get("accepted_pre_pyhyp"):
            print(f"[volume]  {variant.name}")
            try:
                volume_report = subprocess_run_pyhyp(
                    surface_dir,
                    level=variant.volume_level,
                    n_grid=args.n_grid,
                    n_coarsen=variant.n_coarsen,
                    c_max=0.5,
                    eps_e_far=args.eps_e_far,
                    eps_i_far=args.eps_i_far,
                    vol_smooth_iter=1200,
                    n_constant_start=3,
                    march_dist_factor=args.march_dist_factor,
                )
                row["volume"] = _summarize_volume(volume_report, None)
            except Exception as exc:  # noqa: BLE001 - failed march is a result
                row["volume"] = _summarize_volume(None, f"{type(exc).__name__}: {exc}")
                print(f"  volume failed: {row['volume']['error']}")
        else:
            row["volume"] = _summarize_volume(None, "surface failed or --no-volume")

        row["elapsed_seconds"] = time.perf_counter() - t0
        rows.append(row)

    report = {
        "schema": "aeris.structured_mesh_baseline_comparison.v1",
        "baseline": geometry["metadata"],
        "volume_canary": {
            "enabled": bool(args.volume),
            "n_grid": args.n_grid,
            "eps_e_far": args.eps_e_far,
            "eps_i_far": args.eps_i_far,
            "march_dist_factor": args.march_dist_factor,
        },
        "rows": rows,
    }
    (out / "comparison_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"\nwrote {out / 'comparison_report.json'}")
    print("\nsummary")
    for row in rows:
        surface = row.get("surface") or {}
        volume = row.get("volume") or {}
        print(
            f"  {row['name']:<42} surface={row['surface_status']:<6} "
            f"closed={surface.get('closed_except_root')} "
            f"cells={surface.get('cells')} "
            f"shape={surface.get('min_shape_metric')} "
            f"volume={volume.get('status')}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--study-config",
        type=Path,
        default=ROOT / "configs/cfd/pygeo_surface_mesh_study.yaml",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data/meshes/baseline_structured_comparison",
    )
    parser.add_argument("--volume", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument(
        "--n-grid",
        type=int,
        default=17,
        help="pyHyp canary normal-layer count; use 129+ for full smoke volumes.",
    )
    parser.add_argument("--eps-e-far", type=float, default=3.0)
    parser.add_argument("--eps-i-far", type=float, default=6.0)
    parser.add_argument("--march-dist-factor", type=float, default=8.0)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
