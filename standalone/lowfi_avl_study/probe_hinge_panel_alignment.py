"""Can the elevon's 6 % discretisation error be fixed by ALIGNING a panel edge
with the hinge, instead of by brute-force chordwise refinement?

Task 4b found that at the production chordwise resolution (8 panels, cosine
spacing) the elevon control derivative CL_de carries a **6.0 % worst-seed error**
against a 20-panel reference — larger than any other discretisation error in the
low-fidelity chain, and comparable to the AeroSandbox elevon defect that
DECISION-0007 called disqualifying.

Diagnosis. With AVL's cosine chordwise spacing (Cspace = 1.0) and 8 panels the
panel edges land at

    x/c = (1 - cos(pi*i/8))/2  =  0, .038, .146, .309, .500, .691, .854, .962, 1

The elevon hinge sits at x/c = 0.75, which is **between** edges (.691, .854). AVL
must then represent a flap whose hinge falls mid-panel, and the control gain is
smeared over that panel.

Hypothesis. With UNIFORM chordwise spacing (Cspace = 0) and 8 panels the edges are
at multiples of 0.125 -- so x/c = 0.750 is EXACTLY an edge. If hinge alignment is
what matters, uniform-8 should beat cosine-8 on CL_de by a wide margin, at
identical cost.

Trade-off to measure, not assume: cosine spacing clusters panels at the leading
edge, which is where the suction peak and hence the LIFT is resolved. Uniform
spacing gives that up. So this probe reports BOTH CL_de and CL/CLa, against a
common high-resolution reference, and reports the hinge fraction of each
configuration so the alignment claim is checked rather than asserted.

Usage:
    python standalone/lowfi_avl_study/probe_hinge_panel_alignment.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data" / "lowfi_avl_study" / "hinge_panel_alignment"

ALPHA = 6.0
ELEVON_DEG = 4.0
VELOCITY = 28.0
N_SECTIONS = 25
SEEDS = [7000, 7001, 7002]
# AVL's vortex array (NVMAX ~6000) binds: n_strips x nchordwise. With 25 sections
# and 2 spanwise panels/interval we get 96 strips, so chordwise 40 -> 3840
# vortices fits and a genuinely fine reference is affordable. The spanwise grid is
# held FIXED across every level, so its own (small) error cancels in the
# chordwise comparison.
SPANWISE_PANELS = 2

# (nchordwise, cspace, label). cspace 1.0 = cosine, 0.0 = uniform.
CONFIGS = [
    (8, 1.0, "cosine-8 (production)"),
    (8, 0.0, "uniform-8"),
    (12, 1.0, "cosine-12"),
    (12, 0.0, "uniform-12"),
    (16, 1.0, "cosine-16"),
    (16, 0.0, "uniform-16"),
    (20, 1.0, "cosine-20"),
    (24, 1.0, "cosine-24"),
    (40, 0.0, "uniform-40 (cross-check)"),
    (40, 1.0, "cosine-40 (REFERENCE)"),
]
REFERENCE = (40, 1.0)

TRACK = ["CL_de", "Cm_de", "CL", "CLa", "CDind", "Cm", "Cmq", "Xnp"]


def panel_edges(n: int, cspace: float) -> np.ndarray:
    """Chordwise panel edge locations AVL will use, for the alignment check."""
    i = np.arange(n + 1)
    if cspace >= 0.99:                       # cosine
        return 0.5 * (1.0 - np.cos(math.pi * i / n))
    return i / n                             # uniform


def hinge_distance(n: int, cspace: float, hinge: float = 0.75) -> float:
    """Distance from the hinge to the nearest panel edge, in fractions of chord."""
    return float(np.min(np.abs(panel_edges(n, cspace) - hinge)))


def extract(res) -> dict:
    cd = next(iter(res.control_derivatives.values()), {})
    stab = res.stability_axis_derivatives or {}
    return {
        "CL_de": cd.get("CL"), "Cm_de": cd.get("Cm"),
        "CL": res.cl, "CLa": stab.get("CLa"), "CDind": res.cd_ind,
        "Cm": res.cm, "Cmq": stab.get("Cmq"), "Xnp": res.x_np,
        "n_vortices": res.n_vortices, "n_strips": res.n_strips,
    }


def main() -> None:
    from aeris.aero.models import FlightCondition
    from aeris.aero.solvers import native_avl as na
    from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
        build_pygeo_sections_from_config,
        build_realized_section_polar_bridge,
    )

    OUT.mkdir(parents=True, exist_ok=True)
    config = REPO / "configs" / "geometry" / "bwb.yaml"
    results: dict = {"configs": {}, "hinge_alignment": {}}

    for n, cs, label in CONFIGS:
        results["hinge_alignment"][label] = {
            "nchordwise": n, "cspace": cs,
            "nearest_edge_distance_from_hinge": hinge_distance(n, cs),
            "edges": panel_edges(n, cs).round(4).tolist(),
        }

    per_seed: dict = {}
    for seed in SEEDS:
        ex, semi, meta = build_pygeo_sections_from_config(
            config, n_sections=N_SECTIONS, seed=seed)
        ordered = sorted(ex, key=lambda s: float(s.y_m))
        section_map, polar_store = build_realized_section_polar_bridge(
            ex, semispan_m=semi, mach=0.0)
        fc = FlightCondition(alpha_deg=ALPHA, beta_deg=0.0, velocity_mps=VELOCITY,
                             altitude_m=0.0)
        entry = {}
        for n, cs, label in CONFIGS:
            # cspace is a write_native_avl argument; patch the module default so
            # the production runner path is exercised unchanged otherwise.
            orig = na.write_native_avl

            def writer(*a, _cs=cs, **kw):
                kw["cspace"] = _cs
                return orig(*a, **kw)

            na.write_native_avl = writer
            try:
                res = na.run_native_avl_case(
                    ordered, flight_condition=fc,
                    output_dir=OUT / f"s{seed}" / label.split()[0],
                    section_map=section_map, polar_store=polar_store,
                    control=meta["control"], control_input_deg=ELEVON_DEG,
                    diff_input_deg=0.0, nchordwise=n,
                    spanwise_panels_per_section=SPANWISE_PANELS, name="hinge",
                )
            finally:
                na.write_native_avl = orig
            entry[label] = extract(res)
            entry[label]["status"] = res.status
        per_seed[seed] = entry
        print(f"seed {seed} done")

    ref_label = next(lb for n, cs, lb in CONFIGS if (n, cs) == REFERENCE)
    errors: dict = {}
    for n, cs, label in CONFIGS:
        if label == ref_label:
            continue
        block = {}
        for key in TRACK:
            errs = []
            for seed in SEEDS:
                a = per_seed[seed][label].get(key)
                b = per_seed[seed][ref_label].get(key)
                if a is None or b is None:
                    continue
                d = max(abs(a), abs(b))
                if d < 1e-9:
                    continue
                errs.append(abs(a - b) / d)
            if errs:
                block[key] = {"median": float(np.median(errs)),
                              "worst": float(np.max(errs))}
        errors[label] = block

    results["per_seed"] = per_seed
    results["errors_vs_reference"] = errors
    results["reference"] = ref_label
    (OUT / "hinge_alignment.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8")

    L = ["Hinge / panel-edge alignment probe",
         f"elevon hinge at x/c = 0.75; {N_SECTIONS} sections, 4 spanwise "
         f"panels/interval, {len(SEEDS)} seeds",
         f"reference = {ref_label}", "",
         "Panel-edge alignment with the hinge:",
         f"{'config':<24}{'nearest edge dist':>19}{'vortices':>10}"]
    for n, cs, label in CONFIGS:
        h = results["hinge_alignment"][label]["nearest_edge_distance_from_hinge"]
        nv = per_seed[SEEDS[0]][label].get("n_vortices")
        L.append(f"{label:<24}{h:>19.4f}{(nv or 0):>10}")
    L += ["", "Worst-seed relative error vs the reference:",
          f"{'config':<24}" + "".join(f"{k:>10}" for k in TRACK)]
    for n, cs, label in CONFIGS:
        if label == ref_label:
            continue
        cells = "".join(
            f"{errors[label].get(k, {}).get('worst', float('nan')):>10.2e}"
            for k in TRACK)
        L.append(f"{label:<24}" + cells)

    # the verdict
    def w(label, key):
        return errors.get(label, {}).get(key, {}).get("worst")

    c8, u8 = w("cosine-8 (production)", "CL_de"), w("uniform-8", "CL_de")
    L.append("")
    if c8 and u8:
        L.append(f"CL_de worst-seed error:  cosine-8 = {c8:.2%}   "
                 f"uniform-8 = {u8:.2%}   ({c8 / u8:.1f}x better with uniform)")
    L += ["", "Lift-side cost of giving up leading-edge clustering:"]
    for key in ("CL", "CLa", "CDind"):
        a, b = w("cosine-8 (production)", key), w("uniform-8", key)
        if a and b:
            L.append(f"  {key:<6} cosine-8 {a:.2e}   uniform-8 {b:.2e}   "
                     f"-> uniform is {'WORSE' if b > a else 'better'}")
    L += ["", "Spacing cross-check at the finest level (do both spacings agree?):"]
    for key in ("CL_de", "CL", "CLa"):
        v = w("uniform-40 (cross-check)", key)
        if v:
            L.append(f"  {key:<6} uniform-40 vs cosine-40: {v:.2e}")
    text = "\n".join(L)
    print("\n" + text)
    (OUT / "hinge_alignment.txt").write_text(text + "\n", encoding="utf-8")
    print(f"\nwrote {OUT / 'hinge_alignment.json'}")


if __name__ == "__main__":
    main()
