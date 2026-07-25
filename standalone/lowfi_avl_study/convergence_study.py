"""Task 4 — TWO separate convergence studies, deliberately un-conflated.

The prior `scripts/section_study.py` varied the number of extraction sections and
read off "convergence". That measures two things at once, because in the native
writer the AVL spanwise panel count is

    total spanwise panels per side = (n_sections - 1) * spanwise_panels_per_section

so adding sections silently refines the VLM grid as well. Any "section
convergence" curve from that design is really a superposition of

  (a) GEOMETRY-section independence — how many spanwise slices of the pyGeo loft
      are needed before the *shape handed to AVL* stops changing, and
  (b) AVL-panel independence — how fine the *vortex-lattice grid* on that shape
      must be before the VLM solution stops changing.

They are separated here by construction:

  MODE "geometry": vary n_sections while holding the TOTAL spanwise panel count
      FIXED at 96 per side. n_sections is chosen so (n-1) divides 96 exactly, so
      every level has exactly 96 spanwise panels and 8 chordwise. Only the
      geometric fidelity of the AVL model changes.

  MODE "panels": hold n_sections FIXED at the value (a) converged to, and sweep
      spanwise panels per interval and chordwise panels one at a time. Only the
      VLM grid changes.

Run (a) THEN (b) — (b) needs (a)'s answer as its fixed section count.

Both modes run across MULTIPLE DoE seeds, not one geometry, and report the
worst case over seeds as well as the median: a discretisation is only converged
if it is converged everywhere in the design space.

Usage
-----
    python standalone/lowfi_avl_study/convergence_study.py --mode geometry
    python standalone/lowfi_avl_study/convergence_study.py --mode panels --n-sections 25
"""

from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT_ROOT = REPO / "data" / "lowfi_avl_study"

ALPHA = 6.0
ELEVON_DEG = 4.0
VELOCITY = 28.0

# (n_sections - 1) divides 96, so every level has exactly 96 spanwise panels.
GEOMETRY_LEVELS = [5, 7, 9, 13, 17, 25, 33, 49]
TOTAL_SPANWISE_PANELS = 96

# AVL's NSMAX=500 strips total (both halves): (n-1)*panels <= 250.
PANEL_SPANWISE_LEVELS = [1, 2, 3, 4, 6, 8, 10]
PANEL_CHORDWISE_LEVELS = [4, 6, 8, 12, 16, 20]
BASELINE_SPANWISE = 4
BASELINE_CHORDWISE = 8   # overridable via --nchordwise (see __main__)

# Quantities the downstream multifidelity workflow actually consumes.
TRACKED = [
    ("CL", lambda r: r.cl),
    ("CD", lambda r: r.cd_total if r.cd_total is not None else r.cd),
    ("CDind", lambda r: r.cd_ind),
    ("cd_profile", lambda r: r.cd_profile),
    ("Cm", lambda r: r.cm),
    ("e", lambda r: r.span_efficiency),
    ("Xnp", lambda r: r.x_np),
    ("CLa", lambda r: (r.stability_axis_derivatives or {}).get("CLa")),
    ("Cma", lambda r: (r.stability_axis_derivatives or {}).get("Cma")),
    ("Clp", lambda r: (r.stability_axis_derivatives or {}).get("Clp")),
    ("Cnb", lambda r: (r.stability_axis_derivatives or {}).get("Cnb")),
    ("Cmq", lambda r: (r.stability_axis_derivatives or {}).get("Cmq")),
    ("CL_de", lambda r: next(iter(r.control_derivatives.values()), {}).get("CL")),
    ("Cm_de", lambda r: next(iter(r.control_derivatives.values()), {}).get("Cm")),
]

# Purely geometric quantities -- no VLM involved. These isolate how fast the
# SHAPE converges, independently of anything AVL does with it.
GEOM_TRACKED = ["s_ref_xy_m2", "b_ref_y_m", "c_ref_m", "aspect_ratio_xy"]


def _one_run(seed, n_sections, nchordwise, spanwise_panels, out_dir):
    from aeris.aero.models import FlightCondition
    from aeris.generators.bwb_segmented_v1.pygeo_adapter import (
        realised_reference_metrics,
    )
    from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
        build_pygeo_sections_from_config,
        run_pygeo_native_avl_case,
    )

    config = REPO / "configs" / "geometry" / "bwb.yaml"
    ex, semispan, meta = build_pygeo_sections_from_config(
        config, n_sections=n_sections, seed=seed
    )
    ordered = sorted(ex, key=lambda s: float(s.y_m))
    geom = realised_reference_metrics(ordered, symmetric=True)

    fc = FlightCondition(alpha_deg=ALPHA, beta_deg=0.0, velocity_mps=VELOCITY,
                         altitude_m=0.0)
    res = run_pygeo_native_avl_case(
        flight_condition=fc, output_dir=out_dir, extracted_sections=ex,
        semispan_m=semispan, control=meta["control"],
        control_input_deg=ELEVON_DEG, diff_input_deg=0.0, viscous=True,
        nchordwise=nchordwise, spanwise_panels_per_section=spanwise_panels,
        name="conv",
    )
    row = {
        "seed": seed, "n_sections_requested": n_sections,
        "n_sections_actual": len(ordered),
        "nchordwise": nchordwise, "spanwise_panels_per_section": spanwise_panels,
        "total_spanwise_panels_per_side": (len(ordered) - 1) * spanwise_panels,
        "n_strips": res.n_strips, "n_vortices": res.n_vortices,
        "status": res.status,
        "geometry": {k: geom[k] for k in GEOM_TRACKED},
        "aero": {name: fn(res) for name, fn in TRACKED},
        "warnings": res.warnings,
    }
    return row


def _errors_vs_reference(rows_by_level, levels, ref_level):
    """Relative error of every tracked quantity against the finest level, per seed."""
    out = {}
    for level in levels:
        block = {"level": level, "aero": {}, "geometry": {}}
        for group, keys in (("aero", [n for n, _ in TRACKED]),
                            ("geometry", GEOM_TRACKED)):
            for key in keys:
                errs = []
                for seed, ref_row in rows_by_level[ref_level].items():
                    row = rows_by_level[level].get(seed)
                    if row is None:
                        continue
                    a, b = row[group].get(key), ref_row[group].get(key)
                    if a is None or b is None:
                        continue
                    denom = max(abs(a), abs(b))
                    if denom < 1e-9:
                        continue
                    errs.append(abs(a - b) / denom)
                if errs:
                    block[group][key] = {
                        "n_seeds": len(errs),
                        "median": float(np.median(errs)),
                        "worst": float(np.max(errs)),
                    }
        out[level] = block
    return out


def _format(title, errors, levels, ref_level, extra_lines=None):
    L = [title, ""]
    L += extra_lines or []
    keys = [n for n, _ in TRACKED]
    L.append("AERO -- relative error vs the finest level "
             f"({ref_level}); 'worst' = worst seed")
    header = f"{'level':>7}" + "".join(f"{k:>11}" for k in keys)
    L.append(header)
    for tag, stat in (("median", "median"), ("WORST", "worst")):
        L.append(f"-- {tag} over seeds " + "-" * (len(header) - 18))
        for level in levels:
            if level == ref_level:
                continue
            cells = "".join(
                f"{errors[level]['aero'].get(k, {}).get(stat, float('nan')):>11.2e}"
                for k in keys
            )
            L.append(f"{level:>7}" + cells)
    if any(errors[level]["geometry"] for level in levels if level != ref_level):
        L += ["", "GEOMETRY (no VLM involved) -- relative error vs the finest level",
              f"{'level':>7}" + "".join(f"{k:>18}" for k in GEOM_TRACKED)]
        for level in levels:
            if level == ref_level:
                continue
            cells = "".join(
                f"{errors[level]['geometry'].get(k, {}).get('worst', float('nan')):>18.2e}"
                for k in GEOM_TRACKED
            )
            L.append(f"{level:>7}" + cells)
    return "\n".join(L)


def run_geometry_mode(seeds, out: Path):
    """(a) Vary geometry sections at FIXED total panel count."""
    rows_by_level: dict = {n: {} for n in GEOMETRY_LEVELS}
    all_rows = []
    t0 = time.perf_counter()
    for n in GEOMETRY_LEVELS:
        panels = TOTAL_SPANWISE_PANELS // (n - 1)
        for seed in seeds:
            try:
                row = _one_run(seed, n, BASELINE_CHORDWISE, panels,
                               out / f"n{n}_seed{seed}")
                rows_by_level[n][seed] = row
                all_rows.append(row)
            except Exception as exc:
                all_rows.append({"seed": seed, "n_sections_requested": n,
                                 "status": "ERROR",
                                 "error": f"{type(exc).__name__}: {exc}",
                                 "traceback": traceback.format_exc()})
        print(f"  n_sections={n:>3} (panels/interval={panels:>2}) "
              f"elapsed={time.perf_counter() - t0:6.1f}s")

    ref = GEOMETRY_LEVELS[-1]
    errors = _errors_vs_reference(rows_by_level, GEOMETRY_LEVELS, ref)
    checks = []
    for n in GEOMETRY_LEVELS:
        row = next(iter(rows_by_level[n].values()), None)
        if row:
            checks.append(f"  n={n:>3}: {row['n_sections_actual']:>3} actual sections, "
                          f"{row['total_spanwise_panels_per_side']:>3} spanwise panels/side, "
                          f"{row['n_strips']} strips, {row['n_vortices']} vortices")
    text = _format(
        "Task 4a — GEOMETRY-section independence (AVL panel count held FIXED)",
        errors, GEOMETRY_LEVELS, ref,
        [f"seeds: {seeds}",
         f"total spanwise panels per side held at {TOTAL_SPANWISE_PANELS}, "
         f"chordwise {BASELINE_CHORDWISE}",
         "panel count is CONSTANT across levels, so this isolates geometry:",
         *checks, ""],
    )
    return all_rows, errors, text


def run_panel_mode(seeds, n_sections: int, out: Path):
    """(b) Vary the VLM grid at FIXED geometry sections."""
    span_rows: dict = {p: {} for p in PANEL_SPANWISE_LEVELS}
    chord_rows: dict = {c: {} for c in PANEL_CHORDWISE_LEVELS}
    all_rows = []
    t0 = time.perf_counter()

    for p in PANEL_SPANWISE_LEVELS:
        for seed in seeds:
            try:
                row = _one_run(seed, n_sections, BASELINE_CHORDWISE, p,
                               out / f"span{p}_seed{seed}")
                span_rows[p][seed] = row
                all_rows.append(row)
            except Exception as exc:
                all_rows.append({"seed": seed, "spanwise_panels_per_section": p,
                                 "status": "ERROR", "error": str(exc)})
        print(f"  spanwise panels/interval={p:>3} "
              f"elapsed={time.perf_counter() - t0:6.1f}s")

    for c in PANEL_CHORDWISE_LEVELS:
        for seed in seeds:
            try:
                row = _one_run(seed, n_sections, c, BASELINE_SPANWISE,
                               out / f"chord{c}_seed{seed}")
                chord_rows[c][seed] = row
                all_rows.append(row)
            except Exception as exc:
                all_rows.append({"seed": seed, "nchordwise": c,
                                 "status": "ERROR", "error": str(exc)})
        print(f"  chordwise panels={c:>3} elapsed={time.perf_counter() - t0:6.1f}s")

    span_ref, chord_ref = PANEL_SPANWISE_LEVELS[-1], PANEL_CHORDWISE_LEVELS[-1]
    span_err = _errors_vs_reference(span_rows, PANEL_SPANWISE_LEVELS, span_ref)
    chord_err = _errors_vs_reference(chord_rows, PANEL_CHORDWISE_LEVELS, chord_ref)

    text = "\n\n".join([
        _format(
            "Task 4b(i) — AVL SPANWISE panel independence "
            f"(geometry fixed at {n_sections} sections, chordwise {BASELINE_CHORDWISE})",
            span_err, PANEL_SPANWISE_LEVELS, span_ref, [f"seeds: {seeds}", ""],
        ),
        _format(
            "Task 4b(ii) — AVL CHORDWISE panel independence "
            f"(geometry fixed at {n_sections} sections, "
            f"spanwise {BASELINE_SPANWISE}/interval)",
            chord_err, PANEL_CHORDWISE_LEVELS, chord_ref, [f"seeds: {seeds}", ""],
        ),
    ])
    return all_rows, {"spanwise": span_err, "chordwise": chord_err}, text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("geometry", "panels"), required=True)
    ap.add_argument("--seeds", type=int, nargs="+",
                    default=[7000, 7001, 7002, 7003, 7004])
    ap.add_argument("--n-sections", type=int, default=25,
                    help="panels mode only: the section count 4a converged to")
    ap.add_argument("--nchordwise", type=int, default=None,
                    help="override the fixed chordwise panel count (geometry mode: "
                         "used to confirm 4a is not an artefact of a coarse "
                         "chordwise grid)")
    ap.add_argument("--tag", type=str, default="",
                    help="suffix for the output directory")
    args = ap.parse_args()

    global BASELINE_CHORDWISE
    if args.nchordwise:
        BASELINE_CHORDWISE = int(args.nchordwise)

    out = OUT_ROOT / f"convergence_{args.mode}{args.tag}"
    out.mkdir(parents=True, exist_ok=True)
    print(f"Task 4 convergence — mode={args.mode} seeds={args.seeds}")

    if args.mode == "geometry":
        rows, errors, text = run_geometry_mode(args.seeds, out)
    else:
        rows, errors, text = run_panel_mode(args.seeds, args.n_sections, out)

    (out / "rows.json").write_text(json.dumps(rows, indent=2, default=str),
                                   encoding="utf-8")
    (out / "errors.json").write_text(json.dumps(errors, indent=2, default=str),
                                     encoding="utf-8")
    (out / "report.txt").write_text(text + "\n", encoding="utf-8")
    print("\n" + text)
    print(f"\nwrote {out / 'report.txt'}")


if __name__ == "__main__":
    main()
