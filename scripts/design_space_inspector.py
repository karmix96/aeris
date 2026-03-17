from __future__ import annotations

import json
from pathlib import Path

from aeris.common.config import load_yaml_config
from aeris.geometry.params import build_bwb_generator_config


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config_path = project_root / "configs" / "geometry" / "wing_bwb.yaml"

    raw = load_yaml_config(config_path)
    cfg = build_bwb_generator_config(raw)

    pb = cfg.planform_bounds
    sb = cfg.section_bounds

    independent = [
        {"name": "c1_m", "group": "planform", "min": pb.c1_m.min, "max": pb.c1_m.max, "units": "m"},
        {"name": "c2_ratio", "group": "planform", "min": pb.c2_ratio.min, "max": pb.c2_ratio.max, "units": "-"},
        {"name": "c3_ratio", "group": "planform", "min": pb.c3_ratio.min, "max": pb.c3_ratio.max, "units": "-"},
        {"name": "c4_ratio", "group": "planform", "min": pb.c4_ratio.min, "max": pb.c4_ratio.max, "units": "-"},
        {"name": "b_total_m", "group": "planform", "min": pb.b_total_m.min, "max": pb.b_total_m.max, "units": "m"},
        {"name": "b3_ratio", "group": "planform", "min": pb.b3_ratio.min, "max": pb.b3_ratio.max, "units": "-"},
        {"name": "split_ratio", "group": "planform", "min": pb.split_ratio.min, "max": pb.split_ratio.max, "units": "-"},
        {"name": "sw1_deg", "group": "planform", "min": pb.sw1_deg.min, "max": pb.sw1_deg.max, "units": "deg"},
        {"name": "sw2_deg", "group": "planform", "min": pb.sw2_deg.min, "max": pb.sw2_deg.max, "units": "deg"},
        {"name": "sw3_deg", "group": "planform", "min": pb.sw3_deg.min, "max": pb.sw3_deg.max, "units": "deg"},
        {"name": "twist_b0_deg", "group": "sections", "min": sb.twist_b0_deg.min, "max": sb.twist_b0_deg.max, "units": "deg"},
        {"name": "twist_b1_deg", "group": "sections", "min": sb.twist_b1_deg.min, "max": sb.twist_b1_deg.max, "units": "deg"},
        {"name": "twist_b2_deg", "group": "sections", "min": sb.twist_b2_deg.min, "max": sb.twist_b2_deg.max, "units": "deg"},
        {"name": "twist_b3_deg", "group": "sections", "min": sb.twist_b3_deg.min, "max": sb.twist_b3_deg.max, "units": "deg"},
        {"name": "dihedral_b1_deg", "group": "sections", "min": sb.dihedral_b1_deg.min, "max": sb.dihedral_b1_deg.max, "units": "deg"},
        {"name": "dihedral_b2_deg", "group": "sections", "min": sb.dihedral_b2_deg.min, "max": sb.dihedral_b2_deg.max, "units": "deg"},
        {"name": "dihedral_b3_deg", "group": "sections", "min": sb.dihedral_b3_deg.min, "max": sb.dihedral_b3_deg.max, "units": "deg"},
    ]

    fixed = [
        {"name": "airfoil_name", "value": sb.airfoil_name},
        {"name": "dihedral_root_deg", "value": sb.dihedral_root_deg},
        {"name": "generator_family", "value": cfg.generator.family},
        {"name": "generator_version", "value": cfg.generator.version},
    ]

    derived = [
        "c2_m = c1_m * c2_ratio",
        "c3_m = c1_m * c3_ratio",
        "c4_m = c1_m * c4_ratio",
        "b3_m = b_total_m * b3_ratio",
        "b1_m = (b_total_m - b3_m) * split_ratio",
        "b2_m = (b_total_m - b3_m) - b1_m",
        "semi_span_m",
        "full_span_m",
        "approx_area_m2",
        "approx_aspect_ratio",
        "section twist/dihedral interpolated arrays",
    ]

    payload = {
        "config_name": cfg.name,
        "generator": {
            "family": cfg.generator.family,
            "version": cfg.generator.version,
        },
        "dimension": len(independent),
        "independent_variables": independent,
        "fixed_parameters": fixed,
        "derived_quantities": derived,
    }

    print("\n=== DESIGN SPACE INSPECTOR ===\n")
    print(f"Config: {cfg.name}")
    print(f"Generator: {cfg.generator.family} {cfg.generator.version}")
    print(f"Independent design variables: {len(independent)}\n")

    for item in independent:
        print(
            f"{item['group']:>8} | {item['name']:<18} | "
            f"[{item['min']:.4f}, {item['max']:.4f}] {item['units']}"
        )

    print("\nFixed parameters:")
    for item in fixed:
        print(f"  {item['name']}: {item['value']}")

    print("\nDerived quantities:")
    for item in derived:
        print(f"  - {item}")

    out_path = project_root / "data" / "debug" / "design_space_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()