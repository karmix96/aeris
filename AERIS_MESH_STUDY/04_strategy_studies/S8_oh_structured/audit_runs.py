"""One command that says whether the archive is sound.

Every check this campaign learned to make, applied to every archived row at
once. It re-reads the archive rather than the runs, because the archive is what
a surrogate would be trained on: if a defect survives into `rows.json`, it is
the defect that matters.

Each check below exists because something once got past its absence:
reference area (defect 23), moment reference (defect 22), grid label (the
pilot's directory bug), folded cells (defect 19), one-iteration convergence
(Menter SST), per-equation convergence (this audit), y+ (the tip cap).

    python audit_runs.py
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from convergence_gate import EQUATION_LIMITS

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
ROWS = STUDY / "05_s6_cfd_qualification/dataset/rows.json"
AREAS = HERE / "reference_areas.json"
#: the governed contract every campaign row must satisfy
X_REF, C_REF, L2, YPLUS_LIMIT = 0.40, 0.9, 1.0e-6, 1.0
BOUNDS = {"CL": (-3.0, 3.0), "CD": (0.0, 0.5), "CDp": (-0.05, 0.5), "CDv": (0.0, 0.1)}
#: Friction drag against a turbulent flat plate at the MAC Reynolds number
#: (Prandtl-Schlichting, 0.455 / log10(Re)^2.58) on a wetted area of 2.04 x the planform
#: (Raymer, 1.977 + 0.52 t/c at 12 %). A fully turbulent RANS wing sits near 1; a
#: laminar plate is about 0.3. ADflow's SA-Edwards reached 0.33 -- a third of every
#: other run's friction -- and the gate, the bounds and the residuals all called it
#: converged. Wide on purpose: this catches a boundary layer that is not turbulent,
#: not a few per cent of friction.
WETTED_OVER_PLANFORM = 2.04
FRICTION_RATIO = (0.6, 1.6)


def turbulent_friction_estimate(reynolds: float) -> float:
    return WETTED_OVER_PLANFORM * 0.455 / math.log10(reynolds) ** 2.58


#: Fields that must be PRESENT and finite before any physical check runs.
#:
#: Defect 29. Every check below was written as "if the field is there and it is
#: bad, complain", which makes an absent field indistinguishable from a passing
#: one. An external review demonstrated it on 2026-09-16 by deleting fields from
#: a real row one at a time; it was reproduced here on 2026-09-18, and deleting
#: `inverted_cells`, `wall_layer_error_m`, `velocity_direction_error` or
#: `reynolds_mac`, or setting the last three to NaN, produced NO FINDING AT ALL.
#: So "the audit passed" did not mean the checks passed -- it could mean they
#: never ran. The state "I cannot check this" must be a finding, never silence.
REQUIRED = {
    "gate_verdict": "the gate's verdict",
    "relative_residual": "the stopping-rule residual",
    "equation_orders": "per-equation convergence",
    "area_ref": "the reference area the forces were divided by",
    "moment_ref_xyz": "the moment reference point",
    "chord_ref": "the reference chord",
    "inverted_cells": "the folded-cell count",
    "wall_layer_error_m": "the wall-layer position error",
    "yplus_min_p50_p95_p99_max": "wall y+ statistics",
    "iterations": "the iteration count",
    "velocity_direction_error": "the realised freestream direction error",
    "reynolds_mac": "Reynolds on the MAC, which the friction check needs",
    "CD": "drag", "CDv": "viscous drag", "CL": "lift", "CMy": "pitching moment",
}


def _unusable(value) -> bool:
    """True when a value cannot be checked: absent, NaN, or an empty container."""
    if value is None:
        return True
    if isinstance(value, float) and not math.isfinite(value):
        return True
    if isinstance(value, (list, tuple, dict)) and not value:
        return True
    if isinstance(value, (list, tuple)):
        return any(isinstance(v, float) and not math.isfinite(v) for v in value)
    if isinstance(value, dict):
        return any(isinstance(v, float) and not math.isfinite(v) for v in value.values())
    return False


def schema_findings(row: dict) -> list[str]:
    """INCOMPLETE is not PASS.  Runs before every physical check."""
    return [f"{name} missing or unusable ({description}): {row.get(name, '<absent>')!r}"
            for name, description in REQUIRED.items() if _unusable(row.get(name))]


def checks(row: dict, areas: dict) -> list[str]:
    """Every way this row could be wrong. Empty list means sound."""
    bad = schema_findings(row)
    index = row.get("geometry_index")

    if row.get("gate_verdict") != "ACCEPTED":
        bad.append(f"gate verdict {row.get('gate_verdict')}")

    for name, value in ((k, row.get(k)) for k in BOUNDS):
        if value is None or not math.isfinite(value):
            bad.append(f"{name} is {value}")
        elif not BOUNDS[name][0] <= value <= BOUNDS[name][1]:
            bad.append(f"{name} = {value:.4g}, outside anything physical")

    orders = row.get("equation_orders")
    if orders:
        short = {k: round(v, 2) for k, v in orders.items()
                 if k in EQUATION_LIMITS and v < EQUATION_LIMITS[k]}
        if short:
            bad.append(f"equations short of their limit: {short}")
    else:
        bad.append("no per-equation convergence recorded")

    residual = row.get("relative_residual")
    if residual is None or not math.isfinite(residual):
        bad.append("no residual recorded")
    elif residual > L2:
        bad.append(f"residual {residual:.2e} above the {L2:g} rule")

    own = areas.get(str(index))
    if own is None:
        bad.append("geometry has no recorded reference area")
    elif row.get("area_ref") is None or abs(row["area_ref"] / own["half_area_m2"] - 1) > 0.005:
        bad.append(f"area {row.get('area_ref')} is not this geometry's {own['half_area_m2']}")

    # All three components. Checking only x accepted [0.4, 3, 4] -- a moment
    # taken about a point three metres out along the span and four metres up,
    # on a wing whose half-span is under 1.25 m. The review found this by
    # feeding exactly that vector to this function.
    if list(row.get("moment_ref_xyz") or [None, None, None]) != [X_REF, 0.0, 0.0]:
        bad.append(f"moment reference {row.get('moment_ref_xyz')}, want [{X_REF}, 0.0, 0.0]")
    if row.get("chord_ref") != C_REF:
        bad.append(f"reference chord {row.get('chord_ref')}")

    if row.get("inverted_cells"):
        bad.append(f"{row['inverted_cells']} folded cells in the grid")
    wall = row.get("wall_layer_error_m")
    if wall is not None and wall > 1.0e-9:
        bad.append(f"grid sits {wall:.2e} m off the design surface")

    # The 99th percentile was the wrong statistic: it passes a mesh whose worst
    # one per cent sits in the buffer layer, which is exactly where the tip cap
    # was. A wall-resolved RANS needs EVERY wall cell at y+ <= 1; the alternative,
    # wall functions at y+ >= 30, is not available (useWallFunctions is False).
    yplus = row.get("yplus_min_p50_p95_p99_max")
    if yplus and len(yplus) >= 5 and yplus[4] > YPLUS_LIMIT:
        bad.append(f"worst y+ {yplus[4]:.2f} above {YPLUS_LIMIT:g} "
                   f"(p99 {yplus[3]:.2f}; the tip cap is the usual culprit)")

    re_mac, cdv = row.get("reynolds_mac"), row.get("CDv")
    if not re_mac:
        # rows written before dataset_row recorded it: computed the way dataset_row does
        try:
            import cg_limits
            re_mac = (float(row["reynolds"]) / float(row["chord_ref"])
                      * cg_limits.planform(int(row["geometry_index"]))["mac_m"])
        except Exception:  # noqa: BLE001 - no AVL geometry or no fields: check not run
            re_mac = None
    if re_mac and re_mac > 1.0e4 and cdv is not None and math.isfinite(cdv):
        ratio = cdv / turbulent_friction_estimate(re_mac)
        if not FRICTION_RATIO[0] <= ratio <= FRICTION_RATIO[1]:
            bad.append(f"friction drag {1e4 * cdv:.1f} counts is {ratio:.2f} x a turbulent flat "
                       f"plate at Re_MAC {re_mac:.3g} (a laminar plate is about 0.3)")

    if row.get("iterations") is not None and row["iterations"] < 10:
        bad.append(f"converged in {row['iterations']} iterations")

    if row.get("velocity_direction_error") not in (None, 0) and \
            row["velocity_direction_error"] > 1.0e-9:
        bad.append(f"freestream direction off by {row['velocity_direction_error']:.1e}")

    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rows", type=Path, default=ROWS)
    ap.add_argument("--out", type=Path, default=STUDY /
                    "05_s6_cfd_qualification/reports/s8_archive_audit.json")
    args = ap.parse_args()

    data = json.loads(args.rows.read_text())
    rows = data if isinstance(data, list) else data["rows"]
    areas = json.loads(AREAS.read_text())["areas"]

    findings = []
    for row in rows:
        bad = checks(row, areas)
        if bad:
            findings.append({"run": row.get("run_name"), "geometry": row.get("geometry_index"),
                             "level": row.get("grid_level"), "alpha_deg": row.get("alpha_deg"),
                             "problems": bad})
    sound = len(rows) - len(findings)
    print(f"{sound}/{len(rows)} rows sound on every check")
    for f in findings:
        print(f"  g{f['geometry']} {f['level']} a{f['alpha_deg']}: " + "; ".join(f["problems"]))
    report = {"schema": "aeris.s8.archive_audit.v1", "rows": len(rows), "sound": sound,
              "checks": ["gate verdict", "physical force bounds and finiteness",
                         "per-equation convergence", "residual against the stopping rule",
                         "reference area is this geometry's own", "moment reference and chord",
                         "no folded cells", "grid on the design surface", "y+ below 1",
                         "friction drag 0.6-1.6 x a turbulent flat plate at Re_MAC",
                         "not converged in fewer than ten iterations", "freestream direction"],
              "findings": findings}
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"  wrote {args.out}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
