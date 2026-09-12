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


def checks(row: dict, areas: dict) -> list[str]:
    """Every way this row could be wrong. Empty list means sound."""
    bad = []
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

    if list(row.get("moment_ref_xyz") or [None])[0] != X_REF:
        bad.append(f"moment reference {row.get('moment_ref_xyz')}")
    if row.get("chord_ref") != C_REF:
        bad.append(f"reference chord {row.get('chord_ref')}")

    if row.get("inverted_cells"):
        bad.append(f"{row['inverted_cells']} folded cells in the grid")
    wall = row.get("wall_layer_error_m")
    if wall is not None and wall > 1.0e-9:
        bad.append(f"grid sits {wall:.2e} m off the design surface")

    yplus = row.get("yplus_min_p50_p95_p99_max")
    if yplus and len(yplus) >= 4 and yplus[3] > YPLUS_LIMIT:
        bad.append(f"y+ p99 {yplus[3]:.2f} above {YPLUS_LIMIT:g}")

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
                         "not converged in fewer than ten iterations", "freestream direction"],
              "findings": findings}
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"  wrote {args.out}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
