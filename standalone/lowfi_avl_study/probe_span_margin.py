"""Probe: does the section-extraction span margin change the AVL answer?

The pyGeo->AVL chain extracts sections at span fractions
``linspace(span_margin, 1-span_margin, n)``. With the default margin 0.02 the
AVL geometry (a) stops 2% short of the tip and (b) starts 2% outboard of the
symmetry plane, so YDUPLICATE leaves a physical GAP of 2*y_min between the two
half-wings -- AVL then sheds a spurious inboard tip vortex pair.

This probe runs the native chain at several margins and reports the sensitivity
of CL / CDind / e / Cm / Bref. Inviscid (--no-viscous equivalent) to isolate the
VLM geometry effect and keep it fast.

Usage:
    python standalone/lowfi_avl_study/probe_span_margin.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data" / "lowfi_avl_study" / "span_margin_probe"

MARGINS = [0.02, 0.01, 0.005, 0.001, 1e-4, 0.0]
ALPHA = 3.0
N_SECTIONS = 25


def main() -> None:
    from aeris.aero.models import FlightCondition
    from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
        build_pygeo_sections_from_config,
        run_pygeo_native_avl_case,
    )

    config = REPO / "configs" / "geometry" / "bwb.yaml"
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []

    for margin in MARGINS:
        ex, semispan, meta = build_pygeo_sections_from_config(
            config, n_sections=N_SECTIONS, span_margin=margin
        )
        run_dir = OUT / f"margin_{margin:g}"
        fc = FlightCondition(alpha_deg=ALPHA, velocity_mps=28.0, altitude_m=0.0)
        res = run_pygeo_native_avl_case(
            flight_condition=fc,
            output_dir=run_dir,
            extracted_sections=ex,
            semispan_m=semispan,
            control=meta["control"],
            viscous=True,
            name="pygeo_native",
        )
        y_min = min(float(s.y_m) for s in ex)
        y_max = max(float(s.y_m) for s in ex)
        stab = res.stability_axis_derivatives or {}
        rows.append(
            {
                "span_margin": margin,
                "y_min_m": y_min,
                "y_max_m": y_max,
                "centreline_gap_m": 2.0 * y_min,
                "status": res.status,
                "CL": res.cl,
                "CDind": res.cd_ind,
                "cd_profile": res.cd_profile,
                "cd_total": res.cd_total,
                "L_over_D_viscous": res.l_over_d_viscous,
                "Cm": res.cm,
                "span_efficiency": res.span_efficiency,
                "CLa_per_rad": stab.get("CLa"),
                "Cma_per_rad": stab.get("Cma"),
                "Clp": stab.get("Clp"),
                "Xnp": res.x_np,
                "Sref": res.s_ref,
                "Cref": res.c_ref,
                "Bref": res.b_ref,
            }
        )
        print(json.dumps(rows[-1], indent=None, default=str))

    (OUT / "span_margin_probe.json").write_text(
        json.dumps(rows, indent=2, default=str), encoding="utf-8"
    )

    ref = rows[-1]  # margin 0.0 = the correct full-span model
    lines = [
        "Span-margin sensitivity of the native pyGeo->AVL model",
        f"baseline seed, alpha={ALPHA} deg, {N_SECTIONS} sections, viscous on",
        "(margin 0.0 = full span = the correct model; % = deviation from it)",
        "",
        f"{'margin':>8}{'gap_m':>10}{'CL':>10}{'CLa':>9}{'e':>8}"
        f"{'L/D':>8}{'Bref':>9}{'CL err':>9}{'CLa err':>9}",
    ]
    for r in rows:
        cl_err = (r["CL"] - ref["CL"]) / ref["CL"] * 100
        cla_err = (r["CLa_per_rad"] - ref["CLa_per_rad"]) / ref["CLa_per_rad"] * 100
        lines.append(
            f"{r['span_margin']:>8g}{r['centreline_gap_m']:>10.4f}{r['CL']:>10.5f}"
            f"{r['CLa_per_rad']:>9.4f}{r['span_efficiency']:>8.4f}"
            f"{r['L_over_D_viscous']:>8.3f}{r['Bref']:>9.4f}"
            f"{cl_err:>8.1f}%{cla_err:>8.1f}%"
        )
    text = "\n".join(lines)
    print("\n" + text)
    (OUT / "span_margin_probe.txt").write_text(text + "\n", encoding="utf-8")
    print(f"\nwrote {OUT / 'span_margin_probe.json'}")


if __name__ == "__main__":
    main()
