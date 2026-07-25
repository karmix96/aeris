"""Task 1 verification: does the native pyGeo->AVL runner capture everything the
AeroSandbox reference solver does, with the same values?

Both solvers are driven from the SAME pyGeo realized sections and the same
flight condition, so any difference is solver-plumbing, not geometry. We compare
field by field:

  * force/moment scalars   CL CD CDind CDff Cm Cl Cn CY  + e
  * neutral point          Xnp
  * stability-axis derivs  CLa CLb ... Cnr        (25 of them)
  * body-axis derivs       CXu ... Cnw            (18 of them)
  * viscous chain          cd_profile, cd_total, n_extrapolated_strips
  * capture-only fields    control derivatives, hinge moments, surface forces,
                           strip table, shear/bending  (native must have them)

Usage:
    python standalone/lowfi_avl_study/verify_native_vs_asb.py [--alpha 3.0]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO / "data" / "lowfi_avl_study" / "native_vs_asb_verification"

SCALARS = [
    ("CL", "cl", "cl"),
    ("CD", "cd", "cd"),
    ("CDind", "cd_ind", "cd_ind"),
    ("CDff", "cd_ff", "cd_ff"),
    ("Cm", "cm", "cm"),
    ("Cl_roll", "cl_roll", "cl_roll"),
    ("Cn", "cn", "cn"),
    ("CY", "cy", "cy"),
    ("e", "span_efficiency", "span_efficiency"),
    ("Xnp", "x_np", "x_np"),
    ("cd_profile", "cd_profile", "cd_profile"),
    ("cd_total", "cd_total", "cd_total"),
    ("L/D_viscous", "l_over_d_viscous", "l_over_d_viscous"),
]


def _rel(a, b):
    if a is None or b is None:
        return None
    denom = max(abs(a), abs(b))
    if denom < 1e-12:
        return 0.0
    return abs(a - b) / denom


# Three cases decompose the comparison: pure geometry, pitch control, lateral.
CASES = [
    {"name": "A_clean_symmetric", "alpha": 3.0, "beta": 0.0, "de": 0.0, "da": 0.0},
    {"name": "B_pitch_control", "alpha": 3.0, "beta": 0.0, "de": 4.0, "da": 0.0},
    {"name": "C_lateral", "alpha": 3.0, "beta": 2.0, "de": 0.0, "da": 2.0},
]


def run_case(case, ex, semispan, meta, out, velocity):
    from aeris.aero.models import FlightCondition
    from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
        run_pygeo_avl_case,
        run_pygeo_native_avl_case,
    )

    fc = FlightCondition(
        alpha_deg=case["alpha"], beta_deg=case["beta"], velocity_mps=velocity,
        altitude_m=0.0,
    )
    native = run_pygeo_native_avl_case(
        flight_condition=fc, output_dir=out / case["name"] / "native",
        extracted_sections=ex, semispan_m=semispan, control=meta["control"],
        control_input_deg=case["de"], diff_input_deg=case["da"],
        viscous=True, name="pygeo_native",
    )
    asb = run_pygeo_avl_case(
        flight_condition=fc, output_dir=out / case["name"] / "asb",
        extracted_sections=ex, semispan_m=semispan, control=meta["control"],
        viscous=True, name="pygeo_asb",
        paneling={"spanwise_resolution": 4, "chordwise_resolution": 8},
        control_input_deg=case["de"], diff_input_deg=case["da"],
    )
    return native, asb


def build_report(case, native, asb, n_sections) -> dict:
    report: dict = {
        "case": case["name"], "alpha_deg": case["alpha"], "beta_deg": case["beta"],
        "elevon_sym_deg": case["de"], "elevon_diff_deg": case["da"],
        "n_sections": n_sections,
        "native_status": native.status, "asb_status": str(asb.status),
        "scalars": [], "stability_derivatives": [], "body_derivatives": [],
        "native_only_capture": {}, "missing_in_native": [],
    }

    for label, n_attr, a_attr in SCALARS:
        nv = getattr(native, n_attr, None)
        av = getattr(asb, a_attr, None)
        report["scalars"].append(
            {"field": label, "native": nv, "asb": av, "rel_diff": _rel(nv, av)}
        )

    for key in sorted(set(native.stability_axis_derivatives) | set(asb.stability_axis_derivatives or {})):
        nv = native.stability_axis_derivatives.get(key)
        av = (asb.stability_axis_derivatives or {}).get(key)
        report["stability_derivatives"].append(
            {"field": key, "native": nv, "asb": av, "rel_diff": _rel(nv, av)}
        )
        if nv is None and av is not None:
            report["missing_in_native"].append(f"stability:{key}")

    for key in sorted(set(native.body_axis_derivatives) | set(asb.body_axis_derivatives or {})):
        nv = native.body_axis_derivatives.get(key)
        av = (asb.body_axis_derivatives or {}).get(key)
        report["body_derivatives"].append(
            {"field": key, "native": nv, "asb": av, "rel_diff": _rel(nv, av)}
        )
        if nv is None and av is not None:
            report["missing_in_native"].append(f"body:{key}")

    report["native_only_capture"] = {
        "control_derivatives": native.control_derivatives,
        "hinge_moments": native.hinge_moments,
        "surface_forces_n_rows": len(native.surface_forces.get("referred_to_sref", [])),
        "derived_metrics": native.derived_metrics,
        "n_strips": native.n_strips,
        "n_vortices": native.n_vortices,
        "artifact_paths": sorted(native.artifact_paths),
        "asb_artifact_paths": sorted(asb.artifact_paths or {}),
    }
    report["native_warnings"] = native.warnings
    report["asb_warnings"] = list(asb.warnings or [])
    return report


def format_report(report) -> str:
    def _fmt(v):
        return "None" if v is None else f"{v: .6g}"

    lines = [
        "",
        f"=== {report['case']}  alpha={report['alpha_deg']} beta={report['beta_deg']} "
        f"de={report['elevon_sym_deg']} da={report['elevon_diff_deg']} ===",
        f"{'field':<14}{'native':>14}{'asb':>14}{'rel_diff':>12}",
        "-" * 54,
    ]
    for grp in ("scalars", "stability_derivatives", "body_derivatives"):
        lines.append(f"[{grp}]")
        for row in report[grp]:
            rd = row["rel_diff"]
            lines.append(
                f"{row['field']:<14}{_fmt(row['native']):>14}{_fmt(row['asb']):>14}"
                f"{('None' if rd is None else f'{rd:.2e}'):>12}"
            )
    lines.append(f"missing in native: {report['missing_in_native'] or 'NONE'}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--velocity", type=float, default=28.0)
    ap.add_argument("--sections", type=int, default=25)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
        build_pygeo_sections_from_config,
    )

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    config = REPO / "configs" / "geometry" / "bwb.yaml"

    ex, semispan, meta = build_pygeo_sections_from_config(
        config, n_sections=args.sections
    )
    print(f"sections={len(ex)} semispan={semispan:.4f} control={bool(meta['control'])}")

    reports = []
    texts = []
    for case in CASES:
        native, asb = run_case(case, ex, semispan, meta, out, args.velocity)
        print(f"{case['name']}: native CL={native.cl}  asb CL={asb.cl}")
        rep = build_report(case, native, asb, len(ex))
        reports.append(rep)
        texts.append(format_report(rep))

    (out / "verification_report.json").write_text(
        json.dumps(reports, indent=2, default=str), encoding="utf-8"
    )
    text = "\n".join(texts)
    print(text)
    (out / "verification_report.txt").write_text(text, encoding="utf-8")
    print(f"\nwrote {out / 'verification_report.json'}")


if __name__ == "__main__":
    main()
