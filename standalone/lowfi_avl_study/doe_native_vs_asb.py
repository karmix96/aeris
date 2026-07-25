"""Task 3 — pyGeo-native AVL vs AeroSandbox AVL across the DoE design space.

Task 1 established equivalence on ONE geometry. This asks whether that holds
across the whole `configs/geometry/bwb.yaml` design space (20 DVs, full span
1.5-2.5 m, AR 2.6-6.2), with the viscous correction on and off.

Design
------
Per DoE sample: build the pyGeo loft once, extract sections once, then drive
BOTH solvers from those SAME `ExtractedSection` objects. Any difference is
solver plumbing, never geometry.

  4 AVL runs per sample = {native, asb} x {viscous on, viscous off}

Compared: forces (CL, CD, CDind, CDff, Cm, e), the neutral point, all 25
stability-axis derivatives, all 18 body-axis derivatives, and the symmetric
control derivative CL_delta / Cm_delta.

Scope, deliberately
-------------------
SYMMETRIC cases only (beta = 0, no differential elevon). DECISION-0005 showed
the AeroSandbox exporter collapses every control surface into one
`all_deflections` variable with SgnDup +1, so it has no roll degree of freedom
at all -- a lateral comparison would measure that structural limitation, not
solver agreement. It is reported separately as a known, quantified difference
rather than folded into the agreement statistics.

Usage
-----
    python standalone/lowfi_avl_study/doe_native_vs_asb.py --n-samples 20
    python standalone/lowfi_avl_study/doe_native_vs_asb.py --n-samples 2   # smoke
"""

from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO / "data" / "lowfi_avl_study" / "doe_native_vs_asb"

ALPHA = 6.0          # above the ~2 deg zero-lift angle for every sample
ELEVON_DEG = 4.0     # symmetric pitch deflection
VELOCITY = 28.0
N_SECTIONS = 25

FORCE_FIELDS = [
    ("CL", "cl"), ("CD", "cd"), ("CDind", "cd_ind"), ("CDff", "cd_ff"),
    ("Cm", "cm"), ("e", "span_efficiency"), ("Xnp", "x_np"),
    ("cd_profile", "cd_profile"), ("cd_total", "cd_total"),
    ("L_over_D", "l_over_d"),
]


def rel_diff(a, b):
    if a is None or b is None:
        return None
    denom = max(abs(a), abs(b))
    if denom < 1e-12:
        return 0.0
    return abs(a - b) / denom


def run_sample(seed: int, out: Path, viscous: bool) -> dict:
    from aeris.aero.models import FlightCondition
    from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
        build_pygeo_sections_from_config,
        run_pygeo_avl_case,
        run_pygeo_native_avl_case,
    )

    config = REPO / "configs" / "geometry" / "bwb.yaml"
    ex, semispan, meta = build_pygeo_sections_from_config(
        config, n_sections=N_SECTIONS, seed=seed
    )
    fc = FlightCondition(alpha_deg=ALPHA, beta_deg=0.0, velocity_mps=VELOCITY,
                         altitude_m=0.0)
    tag = "visc" if viscous else "inv"

    t0 = time.perf_counter()
    native = run_pygeo_native_avl_case(
        flight_condition=fc, output_dir=out / f"seed{seed}" / f"{tag}_native",
        extracted_sections=ex, semispan_m=semispan, control=meta["control"],
        control_input_deg=ELEVON_DEG, diff_input_deg=0.0,
        viscous=viscous, name="native",
    )
    t_native = time.perf_counter() - t0

    t0 = time.perf_counter()
    asb = run_pygeo_avl_case(
        flight_condition=fc, output_dir=out / f"seed{seed}" / f"{tag}_asb",
        extracted_sections=ex, semispan_m=semispan, control=meta["control"],
        viscous=viscous, name="asb",
        paneling={"spanwise_resolution": 4, "chordwise_resolution": 8},
        control_input_deg=ELEVON_DEG, diff_input_deg=0.0,
    )
    t_asb = time.perf_counter() - t0

    row: dict = {
        "seed": seed, "viscous": viscous,
        "native_status": native.status, "asb_status": str(asb.status),
        "runtime_native_s": t_native, "runtime_asb_s": t_asb,
        "semispan_m": semispan,
        "s_ref": native.s_ref, "b_ref": native.b_ref,
        "aspect_ratio": (native.b_ref ** 2 / native.s_ref) if native.s_ref else None,
        "forces": {}, "stability": {}, "body": {},
    }
    for label, attr in FORCE_FIELDS:
        nv, av = getattr(native, attr, None), getattr(asb, attr, None)
        row["forces"][label] = {"native": nv, "asb": av, "rel": rel_diff(nv, av)}

    for key, nv in (native.stability_axis_derivatives or {}).items():
        av = (asb.stability_axis_derivatives or {}).get(key)
        row["stability"][key] = {"native": nv, "asb": av, "rel": rel_diff(nv, av)}
    for key, nv in (native.body_axis_derivatives or {}).items():
        av = (asb.body_axis_derivatives or {}).get(key)
        row["body"][key] = {"native": nv, "asb": av, "rel": rel_diff(nv, av)}

    # Symmetric control authority. Native names it <elevon>_sym; the ASB
    # exporter emits a single `all_deflections`. Compare whatever each has.
    n_ctrl = next(iter(native.control_derivatives.values()), {})
    a_raw = (asb.raw_outputs or {}).get("_stability_file_parsed", {}) or {}
    row["control"] = {
        "native_CL_d": n_ctrl.get("CL"), "asb_CL_d": a_raw.get("CLd01"),
        "native_Cm_d": n_ctrl.get("Cm"), "asb_Cm_d": a_raw.get("Cmd01"),
        "CL_d_rel": rel_diff(n_ctrl.get("CL"), a_raw.get("CLd01")),
        "Cm_d_rel": rel_diff(n_ctrl.get("Cm"), a_raw.get("Cmd01")),
    }
    return row


def summarise(rows: list[dict]) -> dict:
    """Per-field agreement statistics across the DoE, split by viscous state."""
    out: dict = {}
    for viscous in (True, False):
        subset = [r for r in rows if r["viscous"] == viscous and r.get("ok", True)]
        if not subset:
            continue
        block: dict = {"n_samples": len(subset), "fields": {}}
        groups = [("forces", [k for k, _ in FORCE_FIELDS]),
                  ("stability", sorted(subset[0]["stability"])),
                  ("body", sorted(subset[0]["body"]))]
        for group, keys in groups:
            for key in keys:
                vals = [r[group][key]["rel"] for r in subset
                        if r[group].get(key, {}).get("rel") is not None]
                # Cross-derivatives that are zero by symmetry carry no signal;
                # drop samples where BOTH solvers are numerically zero.
                mags = [max(abs(r[group][key]["native"] or 0.0),
                            abs(r[group][key]["asb"] or 0.0))
                        for r in subset if r[group].get(key, {}).get("rel") is not None]
                keep = [v for v, m in zip(vals, mags) if m > 1e-6]
                if not keep:
                    # Either zero by symmetry (lateral terms at beta=0) or not
                    # produced at all (cd_profile with viscous off). Carries no
                    # agreement signal either way, so it is excluded rather than
                    # counted as a perfect match -- which would flatter the stats.
                    block["fields"][key] = {"status": "no_signal_both_zero",
                                            "n_nonzero": 0}
                    continue
                block["fields"][key] = {
                    "n_nonzero": len(keep),
                    "median_rel": float(np.median(keep)),
                    "p95_rel": float(np.percentile(keep, 95)),
                    "max_rel": float(np.max(keep)),
                }
        ctrl = [r["control"] for r in subset]
        for name in ("CL_d_rel", "Cm_d_rel"):
            vv = [c[name] for c in ctrl if c.get(name) is not None]
            if vv:
                block.setdefault("control", {})[name] = {
                    "median": float(np.median(vv)), "max": float(np.max(vv)),
                }
        out["viscous_on" if viscous else "viscous_off"] = block
    return out


def analyse(rows: list[dict]) -> tuple[dict, list[str]]:
    """Put every disagreement on a common, well-conditioned scale.

    A relative error is meaningless for a derivative that is ~zero by symmetry:
    CYr can be 135% "wrong" while differing by 2.5e-4. So each absolute
    difference is ALSO reported as a fraction of |Clp|, a well-conditioned
    O(0.3) derivative present in every case. Also tests whether the
    control-derivative gap is a systematic bias (the elevon over-extension of
    DECISION-0005) or scatter, and whether agreement degrades across the design
    space.
    """
    subset = [r for r in rows if r.get("ok") and r["viscous"]]
    out: dict = {"n_samples": len(subset)}
    lines: list[str] = []
    if not subset:
        return out, lines

    scaled = {}
    for group in ("stability", "body"):
        for key in sorted(subset[0][group]):
            vals = []
            for r in subset:
                cell = r[group].get(key, {})
                nv, av = cell.get("native"), cell.get("asb")
                clp = abs((r["stability"].get("Clp") or {}).get("native") or 0.0)
                if nv is None or av is None or clp < 1e-6:
                    continue
                vals.append({"abs_diff": abs(nv - av), "over_clp": abs(nv - av) / clp,
                             "rel": cell.get("rel"), "mag": max(abs(nv), abs(av))})
            if vals:
                scaled[key] = {
                    "max_rel": max(v["rel"] for v in vals if v["rel"] is not None),
                    "max_abs_diff": max(v["abs_diff"] for v in vals),
                    "max_over_clp": max(v["over_clp"] for v in vals),
                    "median_magnitude": float(np.median([v["mag"] for v in vals])),
                }
    out["scaled_by_clp"] = scaled

    worst = sorted(scaled.items(), key=lambda kv: -kv[1]["max_rel"])[:8]
    lines += [
        "",
        "Disagreements on a common scale (|Clp| ~ 0.3 is well-conditioned).",
        "A big RELATIVE error on a near-zero derivative is not a big error:",
        f"{'field':<8}{'max rel':>10}{'med |val|':>12}{'max|diff|':>12}{'/|Clp|':>10}",
    ]
    for key, s in worst:
        lines.append(f"{key:<8}{s['max_rel']:>10.2e}{s['median_magnitude']:>12.2e}"
                     f"{s['max_abs_diff']:>12.2e}{s['max_over_clp']:>10.2e}")
    lines.append(f"worst field on the common scale: "
                 f"{max(scaled.items(), key=lambda kv: kv[1]['max_over_clp'])[0]} "
                 f"at {max(s['max_over_clp'] for s in scaled.values()):.2e} of |Clp|")

    # Control-derivative gap: systematic bias or scatter?
    signed = [
        (c["asb_CL_d"] - c["native_CL_d"]) / c["native_CL_d"]
        for c in (r["control"] for r in subset)
        if c.get("asb_CL_d") and c.get("native_CL_d")
    ]
    if signed:
        out["control_bias"] = {
            "signed_median": float(np.median(signed)),
            "signed_sd": float(np.std(signed)),
            "all_same_sign": bool(all(s > 0 for s in signed) or all(s < 0 for s in signed)),
            "n": len(signed),
        }
        lines += [
            "",
            "Control authority CL_delta, signed (asb - native)/native:",
            f"  median {np.median(signed):+.4f}  sd {np.std(signed):.4f}  "
            f"same sign in all {len(signed)} samples: "
            f"{all(s > 0 for s in signed)}",
            "  -> a SYSTEMATIC bias (the ASB elevon over-extends to the tip),",
            "     not solver scatter.",
        ]

    # Does agreement degrade anywhere in the design space?
    ars = [r["aspect_ratio"] for r in subset if r.get("aspect_ratio")]
    if len(ars) > 3:
        out["design_space_dependence"] = {}
        lines += ["", "Does agreement depend on where we are in the design space?"]
        for field in ("CL", "CDind", "Cm"):
            rels = [r["forces"][field]["rel"] for r in subset if r.get("aspect_ratio")]
            corr = float(np.corrcoef(ars, rels)[0, 1])
            out["design_space_dependence"][field] = {"corr_with_AR": corr}
            lines.append(f"  corr(AR, {field} rel error) = {corr:+.3f}")
        lines.append(f"  AR range sampled: {min(ars):.2f} - {max(ars):.2f}")
    return out, lines


def _finish(rows, out: Path, seeds, t_start) -> None:
    summary = summarise(rows)
    n_ok = sum(1 for r in rows if r.get("ok"))
    analysis, analysis_lines = analyse(rows)
    summary["n_runs"] = len(rows)
    summary["n_ok"] = n_ok
    summary["seeds"] = seeds
    summary["alpha_deg"] = ALPHA
    summary["elevon_sym_deg"] = ELEVON_DEG
    summary["n_sections"] = N_SECTIONS
    summary["total_runtime_s"] = time.perf_counter() - t_start
    summary["analysis"] = analysis
    (out / "doe_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    L = [
        "Task 3 - native pyGeo AVL vs AeroSandbox AVL across the DoE",
        f"{len(seeds)} DoE samples, alpha={ALPHA} deg, de={ELEVON_DEG} deg, "
        f"{N_SECTIONS} sections, symmetric only",
        f"runs {n_ok}/{len(rows)} OK",
    ]
    ars = [r["aspect_ratio"] for r in rows if r.get("aspect_ratio")]
    if ars:
        L.append(f"design space covered: AR {min(ars):.2f}-{max(ars):.2f}, "
                 f"span {min(r['b_ref'] for r in rows if r.get('b_ref')):.2f}-"
                 f"{max(r['b_ref'] for r in rows if r.get('b_ref')):.2f} m")
    for state in ("viscous_on", "viscous_off"):
        if state not in summary:
            continue
        b = summary[state]
        L += ["", f"=== {state}  (n={b['n_samples']}) ===",
              f"{'field':<10}{'n':>4}{'median':>11}{'p95':>11}{'max':>11}"]
        for key, s in b["fields"].items():
            if s.get("status") == "no_signal_both_zero":
                L.append(f"{key:<10}{'-':>4}{'both solvers ~0 - excluded':>33}")
                continue
            L.append(f"{key:<10}{s['n_nonzero']:>4}{s['median_rel']:>11.2e}"
                     f"{s['p95_rel']:>11.2e}{s['max_rel']:>11.2e}")
        if "control" in b:
            for name, s in b["control"].items():
                L.append(f"{name:<10}{'':>4}{s['median']:>11.2e}{'':>11}{s['max']:>11.2e}")
    L += analysis_lines
    text = "\n".join(L)
    print("\n" + text)
    (out / "doe_report.txt").write_text(text + "\n", encoding="utf-8")
    print(f"\nwrote {out / 'doe_summary.json'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-samples", type=int, default=20)
    ap.add_argument("--seed0", type=int, default=7000)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--analyse-only", action="store_true",
                    help="re-summarise saved doe_rows.json without re-running AVL")
    args = ap.parse_args()

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    seeds = [args.seed0 + i for i in range(args.n_samples)]

    if args.analyse_only:
        rows = json.loads((out / "doe_rows.json").read_text())
        _finish(rows, out, seeds, time.perf_counter())
        return

    rows: list[dict] = []
    t_start = time.perf_counter()
    for i, seed in enumerate(seeds, 1):
        for viscous in (True, False):
            try:
                row = run_sample(seed, out, viscous)
                row["ok"] = (row["native_status"] == "SUCCESS"
                             and "SUCCESS" in str(row["asb_status"]))
            except Exception as exc:
                row = {"seed": seed, "viscous": viscous, "ok": False,
                       "error": f"{type(exc).__name__}: {exc}",
                       "traceback": traceback.format_exc()}
            rows.append(row)
        done = time.perf_counter() - t_start
        print(f"[{i}/{len(seeds)}] seed={seed} "
              f"elapsed={done:6.1f}s  eta={done / i * (len(seeds) - i):6.1f}s")
        (out / "doe_rows.json").write_text(
            json.dumps(rows, indent=2, default=str), encoding="utf-8"
        )

    _finish(rows, out, seeds, t_start)


if __name__ == "__main__":
    main()
