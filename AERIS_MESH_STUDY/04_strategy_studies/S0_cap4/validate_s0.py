"""S0 robustness validation — 10 development geometries + design-space extremes.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S0_cap4/validate_s0.py

**The Round C hold-out `round_c_lhs10_seed42` is NOT touched here.** ADR-0011 §7.4:
no strategy sees it during development, it is run once after the user's freeze
signal, and `shared.geometry_sets` refuses it unless the caller declares the
strategy frozen. The ten LHS geometries below are the *development* set
`lhs100_seed42`.

The extremes are built from the frozen design-space bounds in
`00_governance/design_space_snapshot.yaml`, following the five difficult cases
RUNBOOK §7 Round A names: thin/small tip, large sweep, strong taper, maximum
twist/dihedral, and the strongest planform-break/elevon combination. They are a
**stress test constructed here**, not one of the three locked geometry sets, and
they are not a substitute for the eight Round C validation extremes, which remain
ungenerated and deferred to Stage 04 (ADR-0011 §3.2).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _p in (str(REPO_ROOT / "src"), str(STUDIES), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import yaml  # noqa: E402

import strategy_s0 as S0  # noqa: E402
from shared import gates, geometry_sets, verify  # noqa: E402
from shared.qc import qc_blocks, worst_corner_angle_deg  # noqa: E402

ART = HERE / "artifacts"
LEVEL = "L3_medium"

#: RUNBOOK §7 Round A's five difficult cases, expressed against the frozen bounds.
#: "lo"/"hi" pick that variable's minimum/maximum; anything unnamed stays nominal.
EXTREMES = {
    "thin_small_tip": {"c4_ratio": "lo", "c1_m": "lo", "b_total_m": "hi"},
    "large_sweep": {"sw1_deg": "hi", "sw2_deg": "hi", "sw3_deg": "hi"},
    "strong_taper": {"c1_m": "hi", "c2_ratio": "lo", "c3_ratio": "lo", "c4_ratio": "lo"},
    "max_twist_dihedral": {
        "twist_b0_deg": "lo", "twist_b1_deg": "lo", "twist_b2_deg": "lo",
        "twist_b3_deg": "lo", "dihedral_b2_deg": "hi", "dihedral_b3_deg": "hi",
    },
    "break_elevon": {
        "b3_ratio": "hi", "split_ratio": "hi", "elevon_start_frac": "lo",
        "elevon_end_frac": "hi", "elevon_hinge_frac": "hi",
    },
    "min_everything": {k: "lo" for k in ("c1_m", "c2_ratio", "c3_ratio", "c4_ratio", "b_total_m")},
    "max_everything": {k: "hi" for k in ("c1_m", "c2_ratio", "c3_ratio", "c4_ratio", "b_total_m")},
}


def _bounds():
    from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config

    from aeris.dataset.sampling.samplers.lhs_v1 import _bwb_bounds

    cfg = build_bwb_generator_config(
        yaml.safe_load((REPO_ROOT / "configs/geometry/bwb.yaml").read_text())
    )
    names = cfg.active_design_variable_names()
    # The sampler's own bounds, so the extremes sit on exactly the box the locked
    # geometry sets are drawn from rather than on a second reading of the config.
    bounds = np.asarray(_bwb_bounds(cfg), dtype=float)
    return cfg, names, bounds[:, 0], bounds[:, 1]


def extreme_wing(name: str, spec: dict):
    from aeris.generators.bwb_segmented_v1.params import BWBDesignSample
    from aeris.geometry.registry import get_geometry_generator

    cfg, names, lo, hi = _bounds()
    values = 0.5 * (lo + hi)
    for var, side in spec.items():
        if var not in names:
            raise KeyError(f"{var!r} is not an active design variable")
        i = names.index(var)
        values[i] = lo[i] if side == "lo" else hi[i]
    sample = BWBDesignSample(**{n: float(v) for n, v in zip(names, values, strict=True)})
    case = get_geometry_generator("bwb_segmented").run_full_case(
        sample=sample,
        config=cfg,
        output_dir=REPO_ROOT / f"AERIS_MESH_STUDY/artifacts/strategy_studies/geom/extreme_{name}",
        save_plot=False,
        build_aerosandbox=True,
    )
    return case.wing


def _row(label: str, wing) -> dict:
    blocks, info = S0.build_surface(wing, level=LEVEL)
    qc = qc_blocks(blocks)
    fid = verify.oml_fidelity(wing, blocks, info["te_thickness"])
    water = verify.watertight_tip(blocks)
    tip = [b for b in blocks if b.name.startswith("tip")]
    passed, reasons = gates.surface_gate_checklist(
        qc, fid, info["orientation"], water["watertight_tip"], deterministic_connectivity=True
    )
    hard = [r for r in reasons if "unverified" not in r]
    return {
        "case": label,
        "blocks": qc["block_count"],
        "cells": qc["total_cells"],
        "min_scaled_jacobian": qc["global"]["min_scaled_jacobian"],
        "max_skewness": qc["global"]["max_equiangle_skewness"],
        "cell_size_range": qc["cell_size_range"],
        "min_cell_edge_m": qc["min_cell_edge_m"],
        "worst_tip_corner_deg": max(worst_corner_angle_deg(b.xyz) for b in tip),
        "watertight": water["watertight_tip"],
        "fidelity_frac_of_chord": fid["worst_frac_of_local_chord"],
        "measured_station_columns": fid["measured_station_columns"],
        "all_finite": bool(all(np.isfinite(b.xyz).all() for b in blocks)),
        "surface_gate": "PASS" if passed else "FAIL",
        "hard_gate_failures": hard,
        "verify": verify.verify_geometry(wing, blocks, te_thickness=info["te_thickness"]),
    }


def main() -> int:
    rows, per_geometry = [], {}
    hdr = (f"{'case':22s} {'blk':>3s} {'cells':>7s} {'minJac':>9s} {'skew':>6s} "
           f"{'range':>7s} {'tipCnr':>8s} {'water':>6s} {'fid%c':>9s} {'hard':>5s}")

    print("=== 10 development geometries — lhs100_seed42 ===")
    print(hdr)
    for i in range(10):
        gid = geometry_sets.geometry_id("lhs100_seed42", i)
        r = _row(gid, geometry_sets.wing("lhs100_seed42", i))
        per_geometry[gid] = r.pop("verify")
        rows.append(r)
        print(f"{gid[-7:]:22s} {r['blocks']:3d} {r['cells']:7d} {r['min_scaled_jacobian']:9.5f} "
              f"{r['max_skewness']:6.3f} {r['cell_size_range']:7.1f} {r['worst_tip_corner_deg']:8.2f} "
              f"{str(r['watertight']):>6s} {r['fidelity_frac_of_chord']*100:9.6f} "
              f"{('ok' if not r['hard_gate_failures'] else 'FAIL'):>5s}")

    print("\n=== design-space extremes (constructed stress cases) ===")
    print(hdr)
    for name, spec in EXTREMES.items():
        try:
            r = _row(name, extreme_wing(name, spec))
        except Exception as exc:  # a build failure IS the result
            print(f"{name:22s}  BUILD FAILED  {type(exc).__name__}: {str(exc)[:60]}")
            rows.append({"case": name, "build_failed": f"{type(exc).__name__}: {exc}"})
            continue
        per_geometry[name] = r.pop("verify")
        rows.append(r)
        print(f"{name:22s} {r['blocks']:3d} {r['cells']:7d} {r['min_scaled_jacobian']:9.5f} "
              f"{r['max_skewness']:6.3f} {r['cell_size_range']:7.1f} {r['worst_tip_corner_deg']:8.2f} "
              f"{str(r['watertight']):>6s} {r['fidelity_frac_of_chord']*100:9.6f} "
              f"{('ok' if not r['hard_gate_failures'] else 'FAIL'):>5s}")

    ok = [r for r in rows if "build_failed" not in r]
    det = verify.verify_set(per_geometry)
    worst = min(r["min_scaled_jacobian"] for r in ok)
    print(f"\ncases built                : {len(ok)}/{len(rows)}")
    print(f"worst min scaled Jacobian  : {worst:+.5f}")
    print(f"worst cell-size range      : {max(r['cell_size_range'] for r in ok):.1f}")
    print(f"all watertight             : {all(r['watertight'] for r in ok)}")
    print(f"all finite                 : {all(r['all_finite'] for r in ok)}")
    print(f"hard-gate failures         : {sum(1 for r in ok if r['hard_gate_failures'])}")
    print(f"deterministic connectivity : {det['deterministic_connectivity']} "
          f"({det['distinct_connectivity_signatures']} signature/s)")

    ART.mkdir(parents=True, exist_ok=True)
    (ART / "s0_validation.json").write_text(
        json.dumps(
            {
                "strategy_id": S0.STRATEGY_ID,
                "level": LEVEL,
                "development_set": "lhs100_seed42 (first 10)",
                "extremes": "constructed from frozen design-space bounds; NOT a locked set",
                "hold_out_touched": False,
                "determinism": det,
                "worst_min_scaled_jacobian": worst,
                "rows": rows,
            },
            indent=2,
            default=str,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
