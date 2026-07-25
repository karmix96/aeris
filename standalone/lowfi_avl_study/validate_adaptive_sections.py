"""Task 6 — does the geometric-information metric earn its place?

Two claims, deliberately SEPARABLE so one can fail without taking the other down:

  CLAIM 1 (predictive). The metric's concentration score, computed from the
      geometry alone in milliseconds, predicts which designs are hard to
      discretise -- i.e. which will show large error at a fixed section budget.
      If true, the metric is useful as a diagnostic even if adaptive placement
      is never adopted.

  CLAIM 2 (prescriptive). At an IDENTICAL section budget, placing sections by
      equidistributing the information density beats uniform spacing.

Both are tested on the Task 5 design set, which includes the case uniform
spacing fails on (a narrow elevon band, 4.34 % CL_delta error) and the benign
case where it does not.

The measured target is DECISION-0010's criterion: ramp fraction <~ 15 %, where
ramp fraction = (gain-ramp width outside the band edges) / (band width), which
correlated r = +0.978 with CL_delta error.

Usage:
    python standalone/lowfi_avl_study/validate_adaptive_sections.py
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs" / "geometry" / "bwb.yaml"
OUT = REPO / "data" / "lowfi_avl_study" / "adaptive_sections"

ALPHA, ELEVON_DEG, VELOCITY = 6.0, 4.0, 28.0
N_BUDGET = 25
NCHORD, SPANWISE = 24, 4
REF_SECTIONS = 49          # 49/2/24 = 96 strips x 24 = 2304 vortices, fits

CASES = {
    "benign": dict(sw1_deg=-20.0, sw2_deg=-15.0, sw3_deg=-5.0, twist_b0_deg=0.0,
                   twist_b1_deg=-0.5, twist_b2_deg=-1.5, twist_b3_deg=-2.0,
                   dihedral_b2_deg=0.0, dihedral_b3_deg=0.0, c2_ratio=0.70,
                   c3_ratio=0.45, c4_ratio=0.15, b_total_m=1.0, c1_m=0.9),
    "nominal": {},
    "elevon_narrow": dict(elevon_start_frac=0.70, elevon_end_frac=0.85),
    "elevon_wide": dict(elevon_start_frac=0.50, elevon_end_frac=0.98),
    "max_gradient": dict(sw1_deg=-40.0, sw2_deg=-15.0, sw3_deg=-25.0,
                         c2_ratio=0.80, c3_ratio=0.30, c4_ratio=0.08,
                         twist_b0_deg=1.0, twist_b3_deg=-8.0,
                         split_ratio=0.40, b3_ratio=0.55),
    "max_ar": dict(b_total_m=1.25, c1_m=0.70, c4_ratio=0.08, twist_b3_deg=-8.0),
}


def build_loft(sample):
    from aeris.common.config import load_yaml_config
    from aeris.generators.bwb_segmented_v1.pygeo_adapter import (
        build_pygeo, stations_from_records)
    from aeris.generators.bwb_segmented_v1.pygeo_backend import _resolve_airfoil_database
    from aeris.generators.bwb_segmented_v1.services import (
        build_section_geometry_from_sample, generate_bwb_planform_from_sample)
    from aeris.geometry.config_resolver import resolve_generator_and_config

    gcfg = resolve_generator_and_config(load_yaml_config(CONFIG))[1]
    pl = generate_bwb_planform_from_sample(sample, gcfg)
    sg = build_section_geometry_from_sample(pl, sample, gcfg)
    st = tuple(stations_from_records(sg.sections, _resolve_airfoil_database(gcfg)))
    fm = "asb_frame" if gcfg.pygeo.frame_mode == "aeris_frame" else gcfg.pygeo.frame_mode
    return build_pygeo(st, k_span=gcfg.pygeo.k_span, frame_mode=fm,
                       n_ctl=gcfg.pygeo.n_ctl, tip=gcfg.pygeo.tip,
                       tip_scale=gcfg.pygeo.tip_scale), gcfg


def extract_at(build, gcfg, fractions):
    from aeris.generators.bwb_segmented_v1.pygeo_adapter import extract_sections
    ex = list(extract_sections(build, np.asarray(fractions),
                               cst_order=gcfg.pygeo.extraction.cst_order,
                               chordwise_points=gcfg.pygeo.extraction.chordwise_points))
    return ex, max(float(s.y_m) for s in ex)


def run(ex, semi, ctl, tag, spanwise=SPANWISE):
    from aeris.aero.models import FlightCondition
    from aeris.aero.solvers.native_avl import run_native_avl_case
    from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
        build_realized_section_polar_bridge)
    smap, ps = build_realized_section_polar_bridge(ex, semispan_m=semi, mach=0.0)
    fc = FlightCondition(alpha_deg=ALPHA, beta_deg=0.0, velocity_mps=VELOCITY,
                         altitude_m=0.0)
    r = run_native_avl_case(sorted(ex, key=lambda s: float(s.y_m)),
                            flight_condition=fc, output_dir=OUT / tag,
                            section_map=smap, polar_store=ps, control=ctl,
                            control_input_deg=ELEVON_DEG, diff_input_deg=0.0,
                            nchordwise=NCHORD, spanwise_panels_per_section=spanwise,
                            name="ad")
    s = r.stability_axis_derivatives or {}
    c = next(iter(r.control_derivatives.values()), {})
    return {"CL": r.cl, "CDind": r.cd_ind, "Cm": r.cm, "Xnp": r.x_np,
            "CLa": s.get("CLa"), "Cma": s.get("Cma"), "Clp": s.get("Clp"),
            "CL_de": c.get("CL"), "Cm_de": c.get("Cm"), "status": r.status}


def main() -> None:
    from aeris.common.config import load_yaml_config
    from aeris.geometry.config_resolver import resolve_generator_and_config
    from aeris.geometry.geometric_information import (
        adaptive_span_fractions, ramp_fraction, spanwise_information_profile)
    from aeris.geometry.registry import get_geometry_generator

    OUT.mkdir(parents=True, exist_ok=True)
    raw = load_yaml_config(CONFIG)
    gid, g = resolve_generator_and_config(raw)
    base = get_geometry_generator(gid).sample_one(g, seed=7000)

    results = {}
    for name, over in CASES.items():
        sample = dataclasses.replace(base, **over)
        build, gcfg = build_loft(sample)
        band = (float(sample.elevon_start_frac), float(sample.elevon_end_frac))
        ctl = {"name": "elevon", "hinge_point": float(sample.elevon_hinge_frac),
               "symmetric": True, "start_frac": band[0], "end_frac": band[1]}

        # --- the metric, from geometry alone -----------------------------
        prof = spanwise_information_profile(build, n_probe=301, chordwise_probe=21,
                                            control_band=band)
        conc = prof.concentration()

        uni = np.unique(np.concatenate([np.linspace(0, 1, N_BUDGET), list(band)]))
        ada = adaptive_span_fractions(prof, N_BUDGET, must_include=band)
        ref = np.unique(np.concatenate([np.linspace(0, 1, REF_SECTIONS), list(band)]))

        entry = {"band": band, "concentration": conc,
                 "n_uniform": len(uni), "n_adaptive": len(ada),
                 "ramp_uniform": ramp_fraction(uni, band),
                 "ramp_adaptive": ramp_fraction(ada, band)}
        try:
            ex_u, s_u = extract_at(build, gcfg, uni)
            ex_a, s_a = extract_at(build, gcfg, ada)
            ex_r, s_r = extract_at(build, gcfg, ref)
            entry["uniform"] = run(ex_u, s_u, ctl, f"{name}_uniform")
            entry["adaptive"] = run(ex_a, s_a, ctl, f"{name}_adaptive")
            entry["reference"] = run(ex_r, s_r, ctl, f"{name}_reference", spanwise=2)
            for which in ("uniform", "adaptive"):
                errs = {}
                for k in ("CL", "CDind", "Cm", "Xnp", "CLa", "Cma", "Clp",
                          "CL_de", "Cm_de"):
                    a, b = entry[which].get(k), entry["reference"].get(k)
                    if a is None or b is None:
                        continue
                    d = max(abs(a), abs(b))
                    if d > 1e-9:
                        errs[k] = abs(a - b) / d
                entry[f"err_{which}"] = errs
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
        results[name] = entry
        eu = entry.get("err_uniform", {}).get("CL_de", float("nan"))
        ea = entry.get("err_adaptive", {}).get("CL_de", float("nan"))
        print(f"{name:<15} conc={conc:.4f} ramp {entry['ramp_uniform']:.1%}->"
              f"{entry['ramp_adaptive']:.1%}  CL_de err {eu*100:.2f}% -> {ea*100:.2f}%")

    (OUT / "adaptive.json").write_text(json.dumps(results, indent=2, default=str),
                                       encoding="utf-8")

    ok = [(n, e) for n, e in results.items() if "err_uniform" in e]
    L = ["Task 6 — adaptive section placement from the geometric-information metric",
         f"budget {N_BUDGET} sections in BOTH cases; nchordwise {NCHORD}; "
         f"reference {REF_SECTIONS} uniform", "",
         "CLAIM 2 (prescriptive): same budget, better placement",
         f"{'case':<15}{'band':>12}{'ramp unif':>11}{'ramp adap':>11}"
         f"{'CL_de unif':>12}{'CL_de adap':>12}{'gain':>8}"]
    for n, e in ok:
        eu = e["err_uniform"].get("CL_de", float("nan"))
        ea = e["err_adaptive"].get("CL_de", float("nan"))
        L.append(f"{n:<15}{f'{e[chr(98)+chr(97)+chr(110)+chr(100)][0]:.2f}-{e[chr(98)+chr(97)+chr(110)+chr(100)][1]:.2f}':>12}"
                 f"{e['ramp_uniform']:>10.1%}{e['ramp_adaptive']:>10.1%}"
                 f"{eu*100:>11.2f}%{ea*100:>11.2f}%{eu/ea if ea else float('nan'):>7.2f}x")
    L += ["", "worst-case over all tracked quantities:",
          f"{'case':<15}{'uniform':>10}{'adaptive':>10}"]
    for n, e in ok:
        wu = max(e["err_uniform"].values()) * 100
        wa = max(e["err_adaptive"].values()) * 100
        L.append(f"{n:<15}{wu:>9.2f}%{wa:>9.2f}%")
    if len(ok) > 2:
        c = [e["concentration"] for _, e in ok]
        u = [e["err_uniform"].get("CL_de", np.nan) for _, e in ok]
        r = [e["ramp_uniform"] for _, e in ok]
        L += ["", "CLAIM 1 (predictive): does the metric forecast difficulty?",
              f"  corr(concentration, uniform CL_de err) = {np.corrcoef(c, u)[0, 1]:+.3f}",
              f"  corr(ramp fraction, uniform CL_de err) = {np.corrcoef(r, u)[0, 1]:+.3f}"]
    text = "\n".join(L)
    print("\n" + text)
    (OUT / "adaptive.txt").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
