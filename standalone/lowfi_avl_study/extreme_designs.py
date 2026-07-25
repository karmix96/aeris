"""Task 5 — does the discretisation hold at the EDGES of the design space?

Why constructed, not sampled
----------------------------
The convergence studies that set 25/4/24 used 5 random DoE seeds. Those cover
only part of each design variable's range (sw1 34 %, c1_m 40 %, b_total_m 47 %),
and random sampling in 19 dimensions essentially never lands near a corner: with
19 independent uniforms, the chance that every one falls in its outer 10 % is
0.2^19 ~ 5e-14. So "run more DoE samples" cannot answer the question. The extreme
cases here are BUILT, by replacing design variables with their bound values.

Each case stresses the specific MECHANISM that sets one panelling number, rather
than being vaguely "extreme":

    hinge_min / hinge_max   -> nchordwise. The elevon error is a hinge/panel-edge
                               coincidence; the DV range is 0.652-0.814 and the
                               recommendation was tuned at 0.75.
    elevon_wide / _narrow   -> n_sections. The +-1.5 % control-authority floor is
                               set by where sections fall against the BAND EDGES.
    max_gradient            -> n_sections. Fastest spanwise change: biggest sweep
                               break, sharpest taper, largest twist gradient.
    max_ar                  -> spanwise panels. Steepest outboard loading
                               gradient (max span, min root chord, max washout).
    min_ar                  -> the stubby end of the space.
    benign                  -> the SIMPLE case. Low sweep, low twist, mid taper.
                               If the discretisation is wrong here it is wrong
                               everywhere.

Every case is checked at the production grid against a finer reference, so the
question answered is "does the recommended discretisation still deliver its
claimed accuracy on this design?" -- not "what is the answer on this design?".

Usage:
    python standalone/lowfi_avl_study/extreme_designs.py
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs" / "geometry" / "bwb.yaml"
OUT = REPO / "data" / "lowfi_avl_study" / "extreme_designs"

ALPHA = 6.0
ELEVON_DEG = 4.0
VELOCITY = 28.0

# Production grid and the finest reference that fits AVL's arrays at 33 sections.
PROD = {"n_sections": 25, "spanwise": 4, "nchordwise": 24}
ECON = {"n_sections": 25, "spanwise": 4, "nchordwise": 16}
REF = {"n_sections": 33, "spanwise": 4, "nchordwise": 20}

TRACK = ["CL", "cd_total", "CDind", "Cm", "e", "Xnp", "CLa", "Cma", "Clp",
         "Cnb", "Cmq", "CL_de", "Cm_de"]

# Bound values, in the sampler's own sign convention (sweeps are negative).
EXTREMES = {
    "benign": dict(sw1_deg=-20.0, sw2_deg=-15.0, sw3_deg=-5.0,
                   twist_b0_deg=0.0, twist_b1_deg=-0.5, twist_b2_deg=-1.5,
                   twist_b3_deg=-2.0, dihedral_b2_deg=0.0, dihedral_b3_deg=0.0,
                   c2_ratio=0.70, c3_ratio=0.45, c4_ratio=0.15,
                   b_total_m=1.0, c1_m=0.9, elevon_hinge_frac=0.75),
    "hinge_min": dict(elevon_hinge_frac=0.65),
    "hinge_max": dict(elevon_hinge_frac=0.82),
    "elevon_wide": dict(elevon_start_frac=0.50, elevon_end_frac=0.98),
    "elevon_narrow": dict(elevon_start_frac=0.70, elevon_end_frac=0.85),
    "max_gradient": dict(sw1_deg=-40.0, sw2_deg=-15.0, sw3_deg=-25.0,
                         c2_ratio=0.80, c3_ratio=0.30, c4_ratio=0.08,
                         twist_b0_deg=1.0, twist_b3_deg=-8.0,
                         split_ratio=0.40, b3_ratio=0.55),
    "max_ar": dict(b_total_m=1.25, c1_m=0.70, c4_ratio=0.08,
                   twist_b3_deg=-8.0, dihedral_b3_deg=10.0),
    "min_ar": dict(b_total_m=0.75, c1_m=1.10, c2_ratio=0.80, c3_ratio=0.55,
                   c4_ratio=0.20),
    "max_dihedral": dict(dihedral_b2_deg=6.0, dihedral_b3_deg=10.0),
}


def extract(res) -> dict:
    s = res.stability_axis_derivatives or {}
    c = next(iter(res.control_derivatives.values()), {})
    return {"CL": res.cl, "cd_total": res.cd_total, "CDind": res.cd_ind,
            "Cm": res.cm, "e": res.span_efficiency, "Xnp": res.x_np,
            "CLa": s.get("CLa"), "Cma": s.get("Cma"), "Clp": s.get("Clp"),
            "Cnb": s.get("Cnb"), "Cmq": s.get("Cmq"),
            "CL_de": c.get("CL"), "Cm_de": c.get("Cm"),
            "n_strips": res.n_strips, "n_vortices": res.n_vortices,
            "status": res.status}


def run_grid(sample, grid, tag):
    from aeris.aero.models import FlightCondition
    from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
        build_pygeo_sections_from_config, run_pygeo_native_avl_case)

    ex, semi, meta = build_pygeo_sections_from_config(
        CONFIG, n_sections=grid["n_sections"], sample=sample)
    fc = FlightCondition(alpha_deg=ALPHA, beta_deg=0.0, velocity_mps=VELOCITY,
                         altitude_m=0.0)
    res = run_pygeo_native_avl_case(
        flight_condition=fc, output_dir=OUT / tag, extracted_sections=ex,
        semispan_m=semi, control=meta["control"], control_input_deg=ELEVON_DEG,
        diff_input_deg=0.0, viscous=True, nchordwise=grid["nchordwise"],
        spanwise_panels_per_section=grid["spanwise"], name="ext")
    out = extract(res)
    out["control"] = meta["control"]
    return out, meta


def main() -> None:
    from aeris.common.config import load_yaml_config
    from aeris.generators.bwb_segmented_v1.pygeo_adapter import (
        realised_reference_metrics)
    from aeris.geometry.config_resolver import resolve_generator_and_config
    from aeris.geometry.registry import get_geometry_generator

    OUT.mkdir(parents=True, exist_ok=True)
    raw = load_yaml_config(CONFIG)
    gid, g = resolve_generator_and_config(raw)
    base = get_geometry_generator(gid).sample_one(g, seed=7000)

    results = {}
    for name, over in EXTREMES.items():
        sample = dataclasses.replace(base, **over)
        entry = {"overrides": over}
        for gname, grid in (("prod", PROD), ("econ", ECON), ("ref", REF)):
            try:
                r, meta = run_grid(sample, grid, f"{name}_{gname}")
                entry[gname] = r
                if gname == "prod":
                    from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
                        build_pygeo_sections_from_config as _b)
                    ex, semi, _ = _b(CONFIG, n_sections=25, sample=sample)
                    m = realised_reference_metrics(sorted(ex, key=lambda s: s.y_m),
                                                   symmetric=True)
                    entry["geometry"] = {"AR": m["aspect_ratio_xy"],
                                         "span_m": m["b_ref_y_m"],
                                         "s_ref": m["s_ref_xy_m2"],
                                         "control": r["control"]}
            except Exception as exc:
                entry[gname] = {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
        # errors of prod / econ vs ref
        for gname in ("prod", "econ"):
            errs = {}
            for k in TRACK:
                a = entry.get(gname, {}).get(k)
                b = entry.get("ref", {}).get(k)
                if a is None or b is None:
                    continue
                d = max(abs(a), abs(b))
                if d > 1e-9:
                    errs[k] = abs(a - b) / d
            entry[f"err_{gname}"] = errs
        results[name] = entry
        e = entry.get("err_prod", {})
        print(f"{name:<15} AR={entry.get('geometry',{}).get('AR',float('nan')):5.2f} "
              f"hinge={entry.get('geometry',{}).get('control',{}).get('hinge_point',0):.3f} "
              f"CL_de_err={e.get('CL_de', float('nan'))*100:6.2f}%  "
              f"worst={max(e.values())*100 if e else float('nan'):6.2f}%")

    (OUT / "extremes.json").write_text(json.dumps(results, indent=2, default=str),
                                       encoding="utf-8")

    L = ["Task 5 — CONSTRUCTED extreme + simple designs",
         f"production grid {PROD['n_sections']}/{PROD['spanwise']}/{PROD['nchordwise']}"
         f"  vs reference {REF['n_sections']}/{REF['spanwise']}/{REF['nchordwise']}",
         f"alpha={ALPHA} deg, de={ELEVON_DEG} deg, viscous on", "",
         f"{'case':<15}{'AR':>6}{'span':>7}{'hinge':>7}{'band':>13}" +
         "".join(f"{k:>9}" for k in ("CL", "CDind", "Cm", "Cmq", "CL_de", "WORST"))]
    for name, e in results.items():
        gm = e.get("geometry", {}) or {}
        ctl = gm.get("control", {}) or {}
        er = e.get("err_prod", {})
        worst = max(er.values()) if er else float("nan")
        L.append(f"{name:<15}{gm.get('AR', float('nan')):>6.2f}"
                 f"{gm.get('span_m', float('nan')):>7.2f}"
                 f"{ctl.get('hinge_point', float('nan')):>7.3f}"
                 f"{f'{ctl.get(chr(115)+chr(116)+chr(97)+chr(114)+chr(116)+chr(95)+chr(102)+chr(114)+chr(97)+chr(99), 0):.2f}-{ctl.get(chr(101)+chr(110)+chr(100)+chr(95)+chr(102)+chr(114)+chr(97)+chr(99), 0):.2f}':>13}" +
                 "".join(f"{er.get(k, float('nan'))*100:8.2f}%"
                         for k in ("CL", "CDind", "Cm", "Cmq", "CL_de")) +
                 f"{worst*100:8.2f}%")
    L += ["", "Same, at the ECONOMY grid (nchordwise 16):",
          f"{'case':<15}" + "".join(f"{k:>9}" for k in ("CL", "CDind", "CL_de", "WORST"))]
    for name, e in results.items():
        er = e.get("err_econ", {})
        worst = max(er.values()) if er else float("nan")
        L.append(f"{name:<15}" +
                 "".join(f"{er.get(k, float('nan'))*100:8.2f}%"
                         for k in ("CL", "CDind", "CL_de")) + f"{worst*100:8.2f}%")
    text = "\n".join(L)
    print("\n" + text)
    (OUT / "extremes.txt").write_text(text + "\n", encoding="utf-8")
    print(f"\nwrote {OUT / 'extremes.json'}")


if __name__ == "__main__":
    main()
