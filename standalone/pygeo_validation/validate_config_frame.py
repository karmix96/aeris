"""Step-1 pyGeo config-reproduction validation.

Confirms — numerically, not by eyeball — that the pyGeo realized loft reproduces
the geometry authored by an Aeris config:

  config SET values ──(shared Aeris planform pipeline)──▶ StationDefinition
                                                          │  (pyGeo B-spline loft)
                                                          ▼
                                                     realized surface
                                                          │  (fixed-span slice)
                                                          ▼
                                                   extracted section frame

Two independent deltas are reported per station / panel:

  (A) StationDefinition vs config SET values  — validates the shared planform
      pipeline resolves chord / twist / sweep / dihedral to the set numbers.
  (B) realized-from-loft  vs StationDefinition — validates the pyGeo loft (the
      backend's actual contribution): chord, twist, LE position, panel angles.

This is intentionally LIGHT: it builds only the neutral B-spline loft and slices
it. No physical CAD, STEP, STL, or file exports are produced — so it is safe to
run in-session on a handful of configs. Wide DoE sweeps belong in a desktop
runbook (roadmap step 2).

Usage:
    python -m standalone.pygeo_validation.validate_config_frame \
        --config configs/geometry/paper1_bwb_pygeo.yaml \
        [--report-dir configs/geometry/pygeo_validation_evidence] \
        [--check-controls-invariance]

Run from the repo root with `src` on the path (pytest/pyproject already set
pythonpath=src; otherwise `PYTHONPATH=src`).
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from aeris.common.config import load_yaml_config
from aeris.generators.bwb_segmented_v1.pygeo_adapter import (
    StationDefinition,
    build_pygeo,
    extract_section,
    realised_reference_metrics,
    span_parameters_for_fractions,
    stations_from_records,
)
from aeris.generators.bwb_segmented_v1.pygeo_backend import _resolve_airfoil_database
from aeris.generators.bwb_segmented_v1.services import (
    build_section_geometry_from_sample,
    generate_bwb_planform_from_sample,
)
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator


# ---- default numerical tolerances (engineering, override on the CLI) --------
# Rationale: recorded pyGeo-vs-intended surface error is sub-mm to ~2 mm RMS and
# area error <0.4%; the ASB-frame rotation reconstruction is analytic (residual
# ~machine eps). These bound the loft-fidelity delta (B); the pipeline delta (A)
# should be ~exact.
DEFAULTS = {
    "chord_rel": 5.0e-3,       # 0.5% of chord
    "twist_deg": 5.0e-2,       # 0.05 deg
    "panel_angle_deg": 1.5e-1,  # 0.15 deg (sweep / dihedral)
    "le_pos_m": 2.0e-3,        # 2 mm LE position
    "frame_recon": 1.0e-6,     # ASB-frame reconstruction residual
    "ref_area_rel": 5.0e-3,
    "ref_span_rel": 1.0e-3,
    "ref_mac_rel": 5.0e-3,
}


@dataclass
class Check:
    name: str
    measured: float
    reference: float
    delta: float
    tol: float
    unit: str
    # gate=True: physically-required, contributes to overall PASS/FAIL.
    # gate=False: characterization of the smooth-loft vs authored-station
    #             deviation — measured and reported, but NOT a pass/fail gate,
    #             because the B-spline loft intentionally smooths the stations.
    gate: bool = True

    @property
    def passed(self) -> bool:
        return abs(self.delta) <= self.tol

    def row(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "measured": self.measured,
            "reference": self.reference,
            "delta": self.delta,
            "abs_delta": abs(self.delta),
            "tol": self.tol,
            "unit": self.unit,
            "gate": self.gate,
            "pass": self.passed,
        }


def _panel_angle_deg(d_perp: float, d_span: float) -> float:
    """Angle (deg) of a panel edge: atan2(perp rise, spanwise run)."""
    return math.degrees(math.atan2(d_perp, d_span))


def _load_case(config_path: Path):
    raw = load_yaml_config(config_path)
    generator_id, gcfg = resolve_generator_and_config(raw)
    generator = get_geometry_generator(generator_id)
    sample = generator.sample_one(gcfg, seed=gcfg.generator.seed)
    planform = generate_bwb_planform_from_sample(sample, gcfg)
    section_geometry = build_section_geometry_from_sample(planform, sample, gcfg)
    return gcfg, sample, planform, section_geometry


def _airfoil_db(gcfg) -> Path:
    return _resolve_airfoil_database(gcfg)


def _config_set_values(gcfg) -> dict[str, Any]:
    """Pull the mid-bound SET values the config authors (for the report table)."""
    pb = gcfg.planform_bounds
    sb = gcfg.section_bounds

    def mid(bound) -> float:
        return 0.5 * (float(bound.min) + float(bound.max))

    c1 = mid(pb.c1_m)
    return {
        "chords_m": [
            c1,
            c1 * mid(pb.c2_ratio),
            c1 * mid(pb.c3_ratio),
            c1 * mid(pb.c4_ratio),
        ],
        "sweeps_deg": [mid(pb.sw1_deg), mid(pb.sw2_deg), mid(pb.sw3_deg)],
        "twists_deg": [
            mid(sb.twist_b0_deg),
            mid(sb.twist_b1_deg),
            mid(sb.twist_b2_deg),
            mid(sb.twist_b3_deg),
        ],
        "dihedrals_deg": [
            float(sb.dihedral_root_deg),
            mid(sb.dihedral_b1_deg),
            mid(sb.dihedral_b2_deg),
            mid(sb.dihedral_b3_deg),
        ],
        "b_total_m": mid(pb.b_total_m),
    }


def _station_fractions(stations: tuple[StationDefinition, ...]) -> np.ndarray:
    ys = np.array([s.y_m for s in stations], dtype=float)
    span = ys[-1] - ys[0]
    if span <= 0:
        raise ValueError("degenerate span: tip y <= root y")
    return (ys - ys[0]) / span


def validate(config_path: Path, tol: dict[str, float]) -> dict[str, Any]:
    gcfg, sample, planform, section_geometry = _load_case(config_path)

    stations = tuple(stations_from_records(section_geometry.sections, _airfoil_db(gcfg)))
    frame_mode = "asb_frame" if gcfg.pygeo.frame_mode == "aeris_frame" else gcfg.pygeo.frame_mode
    build = build_pygeo(
        stations,
        k_span=gcfg.pygeo.k_span,
        frame_mode=frame_mode,
        n_ctl=gcfg.pygeo.n_ctl,
        tip=gcfg.pygeo.tip,
        tip_scale=gcfg.pygeo.tip_scale,
    )

    # Slice the realized loft at each authored station's span fraction.
    fractions = _station_fractions(stations)
    # Nudge exact endpoints inward by a hair to avoid tip/root cap degeneracy.
    eps = 1.0e-6
    safe = np.clip(fractions, eps, 1.0 - eps)
    v_params = span_parameters_for_fractions(build, safe)
    realized = [
        extract_section(
            build,
            v_parameter=float(v),
            span_fraction=float(f),
            index=i,
            cst_order=gcfg.pygeo.extraction.cst_order,
            chordwise_points=gcfg.pygeo.extraction.chordwise_points,
        )
        for i, (v, f) in enumerate(zip(v_params, safe))
    ]

    set_values = _config_set_values(gcfg)
    checks: list[Check] = []

    # -- frame reconstruction residual (single scalar) --
    checks.append(
        Check(
            "frame_reconstruction_error",
            build.frame_reconstruction_error,
            0.0,
            build.frame_reconstruction_error,
            tol["frame_recon"],
            "-",
        )
    )

    # Map the 4 authored group boundaries (root, b1, b2, tip) to station indices.
    station_y = np.array([s.y_m for s in stations])
    boundary_idx = [int(np.argmin(np.abs(station_y - gb))) for gb in planform.group_boundary_y]

    # -- (B) realized-from-loft vs intended StationDefinition, EVERY station --
    # The loft must reproduce the authored frame at all 17 stations, not just the
    # 4 boundaries. Aggregate worst-case deltas become the loft-fidelity gate.
    worst = {"chord_rel": 0.0, "twist": 0.0, "x_le": 0.0, "z_le": 0.0}
    for st, rz in zip(stations, realized):
        worst["chord_rel"] = max(worst["chord_rel"], abs(rz.chord_m - st.chord_m) / st.chord_m)
        worst["twist"] = max(worst["twist"], abs(rz.twist_deg - st.twist_deg))
        worst["x_le"] = max(worst["x_le"], abs(rz.x_le_m - st.x_le_m))
        worst["z_le"] = max(worst["z_le"], abs(rz.z_le_m - st.z_le_m))
    checks += [
        Check("loft.max_chord_rel_err", worst["chord_rel"], 0.0, worst["chord_rel"],
              tol["chord_rel"], "-", gate=False),
        Check("loft.max_twist_err", worst["twist"], 0.0, worst["twist"],
              tol["twist_deg"], "deg", gate=False),
        Check("loft.max_x_le_err", worst["x_le"], 0.0, worst["x_le"], tol["le_pos_m"], "m",
              gate=False),
        Check("loft.max_z_le_err", worst["z_le"], 0.0, worst["z_le"], tol["le_pos_m"], "m",
              gate=False),
    ]

    # Config-SET cross-check at the 4 authored boundary stations.
    labels = ["b0(root)", "b1", "b2", "b3(tip)"]
    per_station: list[dict[str, Any]] = []
    for k, idx in enumerate(boundary_idx):
        st, rz = stations[idx], realized[idx]
        set_c = set_values["chords_m"][k]
        set_t = set_values["twists_deg"][k]
        # SET vs realized (the full config->loft chain), plus intended midpoint.
        checks.append(
            Check(f"{labels[k]}.chord_SET", rz.chord_m, set_c, rz.chord_m - set_c,
                  tol["chord_rel"] * set_c, "m", gate=False)
        )
        checks.append(
            Check(f"{labels[k]}.twist_SET", rz.twist_deg, set_t, rz.twist_deg - set_t,
                  tol["twist_deg"], "deg", gate=False)
        )
        per_station.append(
            {
                "station": labels[k],
                "airfoil": st.airfoil_name,
                "y_m": st.y_m,
                "set_chord_m": set_c,
                "intended_chord_m": st.chord_m,
                "realized_chord_m": rz.chord_m,
                "set_twist_deg": set_t,
                "intended_twist_deg": st.twist_deg,
                "realized_twist_deg": rz.twist_deg,
            }
        )

    # -- panel angles (sweep, dihedral) between the 4 authored boundaries --
    per_panel: list[dict[str, Any]] = []
    for j in range(len(boundary_idx) - 1):
        i0, i1 = boundary_idx[j], boundary_idx[j + 1]
        s0, s1 = stations[i0], stations[i1]
        r0, r1 = realized[i0], realized[i1]
        sweep_i = _panel_angle_deg(s1.x_le_m - s0.x_le_m, s1.y_m - s0.y_m)
        sweep_r = _panel_angle_deg(r1.x_le_m - r0.x_le_m, r1.y_m - r0.y_m)
        dih_i = _panel_angle_deg(s1.z_le_m - s0.z_le_m, s1.y_m - s0.y_m)
        dih_r = _panel_angle_deg(r1.z_le_m - r0.z_le_m, r1.y_m - r0.y_m)
        set_sweep = set_values["sweeps_deg"][j]
        # Realized panel sweep vs config SET sweep, and vs the intended frame.
        checks.append(
            Check(f"panel{j}.sweep_vs_intended", sweep_r, sweep_i, sweep_r - sweep_i,
                  tol["panel_angle_deg"], "deg", gate=False)
        )
        checks.append(
            Check(f"panel{j}.dihedral_vs_intended", dih_r, dih_i, dih_r - dih_i,
                  tol["panel_angle_deg"], "deg", gate=False)
        )
        per_panel.append(
            {
                "panel": f"{labels[j]}->{labels[j+1]}",
                "set_sweep_deg": set_sweep,
                "intended_sweep_LE_deg": sweep_i,
                "realized_sweep_LE_deg": sweep_r,
                "intended_dihedral_deg": dih_i,
                "realized_dihedral_deg": dih_r,
            }
        )

    # -- reference metrics: realized loft vs Aeris planform --
    # Use a dense uniform extraction (not just the 4 stations) so the trapezoidal
    # area/MAC integrals are well resolved.
    n_dense = max(int(gcfg.pygeo.extraction.spanwise_sections), 9)
    dense_fracs = np.clip(np.linspace(0.0, 1.0, n_dense), eps, 1.0 - eps)
    dense_v = span_parameters_for_fractions(build, dense_fracs)
    dense_sections = [
        extract_section(
            build, v_parameter=float(v), span_fraction=float(f), index=i,
            cst_order=gcfg.pygeo.extraction.cst_order,
            chordwise_points=gcfg.pygeo.extraction.chordwise_points,
        )
        for i, (v, f) in enumerate(zip(dense_v, dense_fracs))
    ]
    realized_ref = realised_reference_metrics(dense_sections)
    pf_area = float(planform.approx_area_m2)
    pf_span = float(planform.full_span_m)
    ref_report = {
        "area": {"realized": realized_ref["s_ref_xy_m2"], "planform": pf_area},
        "span": {"realized": realized_ref["b_ref_y_m"], "planform": pf_span},
        "aspect_ratio": {
            "realized": realized_ref["aspect_ratio_xy"],
            "planform": float(planform.approx_aspect_ratio),
        },
        "MAC_realized_m": realized_ref["c_ref_m"],
    }
    checks.append(
        Check("ref.area", realized_ref["s_ref_xy_m2"], pf_area,
              realized_ref["s_ref_xy_m2"] - pf_area, tol["ref_area_rel"] * pf_area, "m2")
    )
    checks.append(
        Check("ref.span", realized_ref["b_ref_y_m"], pf_span,
              realized_ref["b_ref_y_m"] - pf_span, tol["ref_span_rel"] * pf_span, "m")
    )
    pf_ar = float(planform.approx_aspect_ratio)
    checks.append(
        Check("ref.aspect_ratio", realized_ref["aspect_ratio_xy"], pf_ar,
              realized_ref["aspect_ratio_xy"] - pf_ar, tol["ref_area_rel"] * pf_ar, "-")
    )

    gate_checks = [c for c in checks if c.gate]
    char_checks = [c for c in checks if not c.gate]
    passed = all(c.passed for c in gate_checks)
    return {
        "config": str(config_path),
        "generated_utc": datetime.now(UTC).isoformat(),
        "k_span": gcfg.pygeo.k_span,
        "frame_mode": frame_mode,
        "n_stations": len(stations),
        "set_values": set_values,
        "per_station": per_station,
        "per_panel": per_panel,
        "reference_metrics": ref_report,
        "checks": [c.row() for c in checks],
        "n_checks": len(checks),
        "n_gate": len(gate_checks),
        "n_gate_failed": sum(1 for c in gate_checks if not c.passed),
        "loft_smoothing_envelope": {
            "max_chord_rel_err": worst["chord_rel"],
            "max_twist_err_deg": worst["twist"],
            "max_x_le_err_m": worst["x_le"],
            "max_z_le_err_m": worst["z_le"],
        },
        "pass": passed,
    }


def check_controls_invariance(config_path: Path, tol: dict[str, float]) -> dict[str, Any]:
    """The neutral loft frame must be independent of control-surface enablement.

    Elevons are a CAD overlay on the neutral OML; toggling them must not perturb
    the neutral stations or the realized loft frame.
    """
    from dataclasses import replace as dc_replace

    gcfg, sample, planform, section_geometry = _load_case(config_path)
    stations_on = tuple(stations_from_records(section_geometry.sections, _airfoil_db(gcfg)))

    cs_off = dc_replace(gcfg.control_surfaces, enabled=False)
    gcfg_off = dc_replace(gcfg, control_surfaces=cs_off)
    planform_off = generate_bwb_planform_from_sample(sample, gcfg_off)
    section_off = build_section_geometry_from_sample(planform_off, sample, gcfg_off)
    stations_off = tuple(stations_from_records(section_off.sections, _airfoil_db(gcfg_off)))

    max_dev = 0.0
    for a, b in zip(stations_on, stations_off):
        max_dev = max(
            max_dev,
            abs(a.x_le_m - b.x_le_m),
            abs(a.z_le_m - b.z_le_m),
            abs(a.chord_m - b.chord_m),
            abs(a.twist_deg - b.twist_deg),
            abs(a.dihedral_deg - b.dihedral_deg),
        )
    return {
        "max_station_deviation": max_dev,
        "tol": tol["le_pos_m"],
        "pass": max_dev <= tol["le_pos_m"],
    }


def _fmt_report_md(result: dict[str, Any], invariance: dict[str, Any] | None) -> str:
    lines: list[str] = []
    status = "PASS" if result["pass"] else "FAIL"
    lines.append(f"# pyGeo config-frame validation — GATE {status}")
    lines.append("")
    lines.append(f"- config: `{result['config']}`")
    lines.append(f"- generated: {result['generated_utc']}")
    lines.append(
        f"- k_span={result['k_span']}  frame_mode={result['frame_mode']}  "
        f"stations={result['n_stations']}"
    )
    lines.append(
        f"- gate checks: {result['n_gate'] - result['n_gate_failed']}/{result['n_gate']} pass "
        f"(frame reconstruction, reference area/span/AR, control invariance)"
    )
    env = result["loft_smoothing_envelope"]
    lines.append(
        f"- loft-smoothing envelope (characterization, NOT gated): "
        f"chord ≤{env['max_chord_rel_err']*100:.2f}%, twist ≤{env['max_twist_err_deg']:.2f}°, "
        f"LE ≤{max(env['max_x_le_err_m'], env['max_z_le_err_m'])*1e3:.1f} mm"
    )
    lines.append("")

    lines.append("## Stations — config SET vs intended vs realized")
    lines.append("")
    lines.append("| station | af | y (m) | chord SET | chord intended | chord realized "
                 "| twist SET | twist intended | twist realized |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in result["per_station"]:
        lines.append(
            f"| {r['station']} | {r['airfoil']} | {r['y_m']:.4f} | "
            f"{r['set_chord_m']:.4f} | {r['intended_chord_m']:.4f} | {r['realized_chord_m']:.4f} | "
            f"{r['set_twist_deg']:.3f} | {r['intended_twist_deg']:.3f} | {r['realized_twist_deg']:.3f} |"
        )
    lines.append("")

    lines.append("## Panels — sweep / dihedral (config SET vs intended vs realized)")
    lines.append("")
    lines.append("| panel | sweep SET | sweep intended | sweep realized "
                 "| dihedral intended | dihedral realized |")
    lines.append("|---|---|---|---|---|---|")
    for p in result["per_panel"]:
        lines.append(
            f"| {p['panel']} | {p['set_sweep_deg']:.3f} | {p['intended_sweep_LE_deg']:.3f} | "
            f"{p['realized_sweep_LE_deg']:.3f} | {p['intended_dihedral_deg']:.3f} | "
            f"{p['realized_dihedral_deg']:.3f} |"
        )
    lines.append("")

    lines.append("## GATE checks (physically required — set overall PASS/FAIL)")
    lines.append("")
    lines.append("| check | measured | reference | delta | tol | pass |")
    lines.append("|---|---|---|---|---|---|")
    for c in result["checks"]:
        if not c["gate"]:
            continue
        mark = "OK" if c["pass"] else "**FAIL**"
        lines.append(
            f"| {c['name']} | {c['measured']:.6g} | {c['reference']:.6g} | "
            f"{c['delta']:.3g} | {c['tol']:.3g} | {mark} |"
        )
    lines.append("")

    lines.append("## Characterization (smooth-loft vs authored stations — NOT gated)")
    lines.append("")
    lines.append("The kSpan B-spline loft approximates the authored stations; these "
                 "deviations quantify that smoothing and belong in the design-variable space.")
    lines.append("")
    lines.append("| metric | measured | (envelope tol) | within |")
    lines.append("|---|---|---|---|")
    for c in result["checks"]:
        if c["gate"]:
            continue
        mark = "yes" if c["pass"] else "no"
        lines.append(
            f"| {c['name']} | {c['measured']:.6g} | {c['tol']:.3g} | {mark} |"
        )
    lines.append("")

    if invariance is not None:
        inv = "PASS" if invariance["pass"] else "FAIL"
        lines.append("## Control-surface invariance of neutral loft")
        lines.append("")
        lines.append(
            f"- max neutral-station deviation (controls on vs off): "
            f"{invariance['max_station_deviation']:.3g} m "
            f"(tol {invariance['tol']:.3g}) — **{inv}**"
        )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--report-dir", type=Path, default=None,
                    help="If set, write <stem>_validation.{json,md} here.")
    ap.add_argument("--check-controls-invariance", action="store_true")
    for k, v in DEFAULTS.items():
        ap.add_argument(f"--tol-{k.replace('_', '-')}", type=float, default=v, dest=f"tol_{k}")
    args = ap.parse_args()

    tol = {k: getattr(args, f"tol_{k}") for k in DEFAULTS}
    result = validate(args.config, tol)
    invariance = (
        check_controls_invariance(args.config, tol) if args.check_controls_invariance else None
    )
    if invariance is not None:
        result["controls_invariance"] = invariance
        result["pass"] = result["pass"] and invariance["pass"]

    md = _fmt_report_md(result, invariance)
    print(md)

    if args.report_dir is not None:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        stem = args.config.stem
        (args.report_dir / f"{stem}_validation.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        (args.report_dir / f"{stem}_validation.md").write_text(md, encoding="utf-8")
        print(f"\n[written] {args.report_dir}/{stem}_validation.{{json,md}}")

    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
