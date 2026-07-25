"""Wing-level (aircraft) drag increment from the blunt-TE floor.

Section drag is NOT the driver — the aircraft ΔCD is. This integrates the per-section
blunt-TE drag increment over the actual wing, area-weighted:

    ΔCD_wing = (2 / S_ref) · ∫_0^semispan  ΔCd(y) · c(y)  dy

Each section is blunted to ITS floor t(y)/c = max(0.25%c, 0.5 mm / c(y)), evaluated
at ITS local Re and ITS airfoil (mh91 inboard, e374 outboard, per the station map),
at the operating CL. The tip carries the largest %c TE but the least area, so its
contribution is small — this quantifies exactly that.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from standalone.te_thickness_study.study import _cd_at_cl, _load_airfoil, _polar, blunt_te


def _airfoil_at_y(y: float, gby, station) -> str:
    eps = 1e-9
    if y >= float(gby[3]) - eps:
        return station.b3
    if y >= float(gby[2]) - eps:
        return station.b2
    if y >= float(gby[1]) - eps:
        return station.b1
    return station.b0


def run(config_path: str, seed: int, cl_op: float, te_frac: float, te_abs_m: float,
        velocity: float, nu: float) -> dict:
    from aeris.common.config import load_yaml_config
    from aeris.generators.bwb_segmented_v1.services import (
        build_section_geometry_from_sample,
        generate_bwb_planform_from_sample,
    )
    from aeris.geometry.config_resolver import resolve_generator_and_config
    from aeris.geometry.registry import get_geometry_generator

    raw = load_yaml_config(Path(config_path))
    gid, g = resolve_generator_and_config(raw)
    gen = get_geometry_generator(gid)
    s = gen.sample_one(g, seed=seed)
    pf = generate_bwb_planform_from_sample(s, g)
    sg = build_section_geometry_from_sample(pf, s, g)
    gby = np.asarray(pf.group_boundary_y, dtype=float)
    station = g.section_bounds.station_airfoils

    # One representative section per fine station (chord + y + airfoil).
    recs = sorted(sg.sections, key=lambda r: r.y_m)
    ys = np.array([r.y_m for r in recs])
    chords = np.array([r.chord_m for r in recs])
    names = [_airfoil_at_y(r.y_m, gby, station) for r in recs]

    s_ref = float(pf.approx_area_m2)
    # cache polars per (airfoil, rounded chord bucket) to limit NeuralFoil calls
    coord_cache: dict[str, np.ndarray] = {}
    d_cd = np.zeros(len(recs))
    te_frac_used = np.zeros(len(recs))
    for i, (c, name) in enumerate(zip(chords, names)):
        if name not in coord_cache:
            coord_cache[name] = _load_airfoil(name)
        base = coord_cache[name]
        t = max(te_frac, te_abs_m / max(c, 1e-6))     # TE gap as fraction of chord
        te_frac_used[i] = t
        re = max(c * velocity / nu, 3.0e4)
        sharp = _cd_at_cl(_polar(blunt_te(base, 0.0), re), cl_op)
        blunt = _cd_at_cl(_polar(blunt_te(base, t), re), cl_op)
        d_cd[i] = (blunt - sharp) if (np.isfinite(blunt) and np.isfinite(sharp)) else 0.0

    valid = np.isfinite(d_cd)
    # ΔCD = (2/Sref) ∫ ΔCd·c dy  (2 = both halves)
    dCD = 2.0 * float(np.trapezoid((d_cd * chords)[valid], ys[valid])) / s_ref
    # Also the sharp-vs-uniform check: section-worst vs wing-average
    return {
        "config": config_path, "seed": seed, "cl_op": cl_op,
        "te_frac_floor_pct": te_frac * 100, "te_abs_mm": te_abs_m * 1000,
        "s_ref_m2": s_ref, "n_sections": len(recs),
        "chord_root_tip_m": [float(chords[0]), float(chords[-1])],
        "te_pct_root_tip": [float(te_frac_used[0] * 100), float(te_frac_used[-1] * 100)],
        "section_d_cd_counts_min_max": [float(np.min(d_cd) * 1e4), float(np.max(d_cd) * 1e4)],
        "wing_dCD": dCD,
        "wing_dCD_counts": dCD * 1e4,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="configs/geometry/bwb.yaml")
    ap.add_argument("--seed", type=int, default=1001)
    ap.add_argument("--cl-op", type=float, default=0.4)
    ap.add_argument("--te-frac", type=float, default=0.0025, help="fractional floor (of chord)")
    ap.add_argument("--te-abs-mm", type=float, default=0.5, help="absolute floor [mm]")
    ap.add_argument("--velocity", type=float, default=28.0)
    ap.add_argument("--report-dir", type=Path, default=None)
    args = ap.parse_args()

    d = run(args.config, args.seed, args.cl_op, args.te_frac, args.te_abs_mm / 1000.0,
            args.velocity, 1.46e-5)
    d["generated_utc"] = datetime.now(UTC).isoformat()
    print(json.dumps(d, indent=2))
    print(f"\n>>> WING-LEVEL ΔCD from the blunt-TE floor: {d['wing_dCD_counts']:.2f} drag counts"
          f"  (section worst {d['section_d_cd_counts_min_max'][1]:.1f} counts)")
    if args.report_dir is not None:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        (args.report_dir / "te_thickness_wing.json").write_text(
            json.dumps(d, indent=2), encoding="utf-8")
        print(f"[written] {args.report_dir}/te_thickness_wing.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
