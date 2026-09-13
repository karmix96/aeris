#!/usr/bin/env python
"""The S8 dataset schema, and the emitter that fills it from a run's artefacts.

    .venv/bin/python .../dataset_row.py --run-dir <geometry dir> --level gci_C \
        --index 83 --out <dir>/dataset_rows.json

PLAN_desktop_campaign.md 4.4, fixed before the first pilot case, because
"retrofitting provenance is far harder than recording it" and every field below
is cheap now and expensive or impossible later.

Scalars are not the deliverable
-------------------------------
The eventual goal is AI field prediction, which needs the FIELDS and their
IDENTITY: a surface solution is worthless to a learner that cannot say which
geometry it belongs to, at what operating point, on which mesh, from which
solver build.  So the row carries paths to the field files, a hash of the mesh
connectivity, and the node ordering convention -- not because anything today
reads them, but because a dataset assembled without them cannot be repaired.

Every field is either filled or explicitly absent
--------------------------------------------------
A missing value is recorded as null AND listed in `missing_fields` with the
reason.  This matters more here than the usual argument for it: PLAN 0.4 is the
record of a quantity that drifted 2.6x between stations while the acceptance
metric reported success, because the number that would have shown it "was
computed and discarded".  A schema that silently omits what it could not find
reproduces exactly that failure, one level up.  A row that cannot say why a
field is empty is not a record, it is a rumour.

What this deliberately does NOT do
-----------------------------------
It does not compute a verdict.  The gate decides acceptance, gci.py decides
whether a triplet is usable, and this only transcribes what they said, including
when they said no.  A dataset row for a REJECTED run is still written, with the
verdict on it: the runs that failed are training data about the solver, and
dropping them silently is how a dataset comes to describe a solver that always
converges.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
for extra in (HERE, HERE.parent, HERE.parent / "S6_bounded_mesh_atlas", REPO / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

#: The schema, in the order PLAN 4.4 gives it.  This tuple IS the contract:
#: a row is built by filling these keys and nothing else, so a field that is
#: added here without an emitter shows up as an explicit gap rather than
#: quietly not existing.
SCHEMA: dict[str, tuple[str, ...]] = {
    "identity_and_provenance": (
        "geometry_set", "geometry_index", "geometry_hash", "design_vector",
        "mesher", "frame_mode", "grid_level", "cells", "mesh_hash",
        "git_commit", "adflow_version", "turbulence_model", "solver_options_hash"),
    "operating_point_and_references": (
        "alpha_deg", "beta_deg", "mach", "reynolds", "temperature_K",
        "area_ref", "chord_ref", "moment_ref_xyz",
        # The mission fixes ONE flight condition -- 28 m/s at 1500 m, Re 1.70e6 per
        # metre -- and every design flies it. The "reynolds" above is that condition
        # quoted on a 0.9 m reference chord, which is nobody's actual chord: the ten
        # wings run 0.71 to 1.09 m at the root and 0.46 to 0.71 m on the mean chord.
        # Reading 1.53e6 as "this wing's Reynolds number" is wrong by up to 50 %.
        "reynolds_per_metre", "reynolds_mac", "reynolds_root_chord", "mac_m"),
    "results": ("CL", "CD", "CDp", "CDv", "CMy", "CMx", "CMz"),
    "convergence": (
        "gate_verdict", "relative_residual", "orders_dropped", "equation_orders",
        "iterations",
        "cl_pct", "cd_pct", "cmy_abs",
        "lift_index_realised", "velocity_direction_error"),
    "mesh_state": (
        "wall_layer_error_m", "inverted_cells", "worst_le_turn_deg",
        "min_cell_over_s0", "scaled_jacobian_min_p001_p01"),
    "physics_checks": (
        "yplus_min_p50_p95_p99_max", "cp_cells_over_bound", "cp_peak_excess"),
    "fields": (
        "surface_field_path", "volume_field_path", "node_ordering",
        "connectivity_hash"),
    "low_fidelity": ("avl_cl", "avl_cd", "avl_cm", "avl_status"),
}
FLAT_SCHEMA = tuple(f for group in SCHEMA.values() for f in group)

#: isentropic stagnation cp at the mission Mach number, from check_cp_bound.py
CP_PHYSICAL_MAX = 1.0018
#: how solve_s8.py orders the volume block indices, recorded so a learner that
#: reads the field files knows what the axes mean without guessing
NODE_ORDERING = "structured (i=xi around the ring, j=eta wall-normal, k=zeta spanwise), C-order in the npz, Fortran-order in the CGNS"


def repo_relative(path: Path) -> str:
    """A repo-relative path string, whatever form the caller passed.

    relative_to() raises when the argument is relative and REPO is absolute, so
    a run directory given as a relative path made every row fail on the FIELD
    PATH -- the one thing the AI work needs most.
    """
    try:
        return str(Path(path).resolve().relative_to(REPO))
    except ValueError:
        return str(path)


def sha256_file(path: Path, limit: int | None = None) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
            if limit and h.block_size and fh.tell() > limit:
                break
    return h.hexdigest()


def git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=60)
        return out.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def solver_options_hash() -> str:
    """Hash the literal option block in solve_s8.py.

    Hashing the SOURCE rather than a copied dict means the hash changes when the
    solver setup changes, including changes nobody remembered to mirror here.
    A dataset whose provenance field can drift away from the thing it describes
    is not carrying provenance.
    """
    text = (HERE / "solve_s8.py").read_text()
    block = re.search(r"solver = ADFLOW\(options=\{(.*?)\n    \}\)", text, re.S)
    body = block.group(1) if block else text
    stripped = "\n".join(line.split("#")[0].rstrip()
                         for line in body.splitlines() if line.split("#")[0].strip())
    return hashlib.sha256(stripped.encode()).hexdigest()[:16]


def adflow_version(mach_python: str | None) -> str | None:
    if not mach_python:
        return None
    try:
        out = subprocess.run(
            [mach_python, "-c", "import adflow; print(getattr(adflow,'__version__','unknown'))"],
            capture_output=True, text=True, timeout=180)
        return out.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def cgns_variable(path: Path, name: str) -> np.ndarray | None:
    """One field, whichever CGNS container the file uses.

    This was a private h5py reader -- the THIRD copy of one in this directory,
    after check_cp_bound.py and analyse_refinement.py. ADflow writes ADF here,
    h5py cannot open it, and every copy therefore returned None silently: the
    cp panel came out blank, the refinement analysis printed "no cp", and every
    dataset row recorded cp_cells_over_bound and yplus as absent. Three separate
    places, one cause, because the reader was copied instead of shared.
    """
    import cgns_read
    return cgns_read.read_variable(path, name)


def surface_file(run: Path) -> Path | None:
    candidates = sorted(run.glob("*_surf.cgns")) or sorted(run.glob("*surf*.cgns"))
    return candidates[0] if candidates else None


def volume_file(run: Path) -> Path | None:
    candidates = [p for p in sorted(run.glob("*_vol.cgns")) + sorted(run.glob("*vol*.cgns"))]
    return candidates[0] if candidates else None


def _own_area(index: int) -> float | None:
    table = HERE / "reference_areas.json"
    if not table.exists():
        return None
    entry = json.loads(table.read_text()).get("areas", {}).get(str(index))
    return float(entry["half_area_m2"]) if entry else None


def build_row(*, run: Path, level: str, index: int, set_name: str,
              mesh_dir: Path, gate: dict | None, avl: dict | None,
              mach_python: str | None, cache: dict) -> dict:
    row = dict.fromkeys(FLAT_SCHEMA)
    missing: dict[str, str] = {}

    def absent(field: str, why: str) -> None:
        missing[field] = why

    # ---- identity and provenance -------------------------------------------
    row["geometry_set"] = set_name
    row["geometry_index"] = index
    row["mesher"] = "S8_OH_STRUCTURED"
    row["grid_level"] = level
    row["turbulence_model"] = "SA"
    row["git_commit"] = git_commit() or absent("git_commit", "git rev-parse failed")
    row["solver_options_hash"] = solver_options_hash()
    if "adflow_version" not in cache:
        cache["adflow_version"] = adflow_version(mach_python)
    row["adflow_version"] = cache["adflow_version"]
    if row["adflow_version"] is None:
        absent("adflow_version", "the MACH-Aero interpreter could not be queried")

    if "design" not in cache:
        try:
            from shared.geometry_sets import design_matrix
            X, names = design_matrix(set_name)
            cache["design"] = (np.asarray(X, float), list(names))
        except Exception as exc:  # noqa: BLE001
            cache["design"] = None
            cache["design_error"] = f"{type(exc).__name__}: {exc}"
    if cache["design"]:
        X, names = cache["design"]
        vector = X[index].tolist()
        row["design_vector"] = dict(zip(names, vector))
        row["geometry_hash"] = hashlib.sha256(
            json.dumps({"set": set_name, "index": index, "dv": vector},
                       sort_keys=True).encode()).hexdigest()[:16]
    else:
        absent("design_vector", cache.get("design_error", "design matrix unavailable"))
        absent("geometry_hash", cache.get("design_error", "design matrix unavailable"))

    # ---- mesh state ---------------------------------------------------------
    summary_path = mesh_dir / f"{level}_summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
        row["frame_mode"] = summary["volume"]["frame_mode"]
        row["cells"] = summary["cells"]
        row["wall_layer_error_m"] = summary["volume"]["wall_layer_error_m"]
        row["inverted_cells"] = summary["negative_cells_all_blocks"]
        row["worst_le_turn_deg"] = summary["surface"]["worst_le_turn_per_cell_deg"]
        row["min_cell_over_s0"] = summary["surface"]["min_cell_over_s0"]
        blocks = mesh_dir / f"{level}_blocks.npz"
        row["mesh_hash"] = sha256_file(blocks)
        key = str(mesh_dir / level)
        if key not in cache:
            try:
                import compare_meshes
                cache[key] = compare_meshes.metrics(mesh_dir, level)
            except Exception as exc:  # noqa: BLE001
                cache[key] = None
                cache[key + "_error"] = f"{type(exc).__name__}: {exc}"
        quality = cache[key]
        if quality:
            row["scaled_jacobian_min_p001_p01"] = [
                quality.get("quality/o_wing/scaled_jacobian_min"),
                quality.get("quality/o_wing/scaled_jacobian_p001"),
                quality.get("quality/o_wing/scaled_jacobian_p01")]
            row["connectivity_hash"] = hashlib.sha256(json.dumps(
                {k: v for k, v in quality.items() if k.startswith("topology/")},
                sort_keys=True).encode()).hexdigest()[:16]
        else:
            absent("scaled_jacobian_min_p001_p01",
                   cache.get(key + "_error", "compare_meshes.metrics unavailable"))
            absent("connectivity_hash", "block topology unavailable")
    else:
        for field in ("frame_mode", "cells", "wall_layer_error_m", "inverted_cells",
                      "worst_le_turn_deg", "min_cell_over_s0", "mesh_hash",
                      "scaled_jacobian_min_p001_p01", "connectivity_hash"):
            absent(field, f"no {summary_path.name} beside the run")

    # ---- operating point and results ---------------------------------------
    result_path = run / "result.json"
    if not result_path.exists():
        for field in SCHEMA["operating_point_and_references"] + SCHEMA["results"]:
            absent(field, "the run wrote no result.json -- it did not finish")
        row["gate_verdict"] = "NO_RESULT"
    else:
        result = json.loads(result_path.read_text())
        mission = result.get("mission", {})
        row.update(alpha_deg=result.get("alpha_deg"), beta_deg=0.0,
                   mach=mission.get("mach"), reynolds=mission.get("reynolds"),
                   temperature_K=mission.get("temperature_K"),
                   area_ref=result.get("area_ref_m2"),
                   chord_ref=mission.get("chord_ref_m"),
                   moment_ref_xyz=result.get("moment_ref_xyz_m"),
                   relative_residual=result.get("relative_residual"))
        wanted = {"cl": "CL", "cd": "CD", "cdp": "CDp", "cdv": "CDv",
                  "cmy": "CMy", "cmx": "CMx", "cmz": "CMz"}
        for key, value in result.get("functions", {}).items():
            for short, field in wanted.items():
                if key.endswith("_" + short):
                    row[field] = float(value)
        for field in wanted.values():
            if row[field] is None:
                absent(field, "not in solve_s8.py evalFuncs for this run")
        directions = result.get("flow_directions", {})
        row["lift_index_realised"] = directions.get("lift_index_realised")
        row["velocity_direction_error"] = directions.get("velocity_direction_error")

    # ---- defect 23: this geometry's OWN area -------------------------------
    # The solver was given index 83's area for every pilot geometry. Forces were
    # right; coefficients were scaled by solver_area / own_area. Every moment
    # and force coefficient divides by the same S, so one factor corrects all of
    # them, and the original is kept so the correction is visible, not silent.
    own = _own_area(index)
    used = row.get("area_ref")
    if own and used and abs(used / own - 1.0) > 0.005:
        factor = used / own
        for field in ("CL", "CD", "CDp", "CDv", "CMy", "CMx", "CMz"):
            if row[field] is not None:
                row[field] *= factor
        row["coefficients_rescaled"] = {
            "solver_area_m2": used, "own_area_m2": own, "factor": factor,
            "reason": "defect 23: solved against index 83's area; rescaled to this geometry's own"}
        row["area_ref"] = own

    # ---- convergence, from the gate rather than from the run ---------------
    entry = None
    if gate:
        entry = next((r for r in gate.get("results", [])
                      if Path(r["directory"]).resolve() == run.resolve()), None)
    if entry:
        checks = entry["checks"]
        row.update(gate_verdict=entry["verdict"], iterations=entry["iterations"],
                   orders_dropped=checks["residual_orders"]["value"],
                   # Fluent's per-equation test: continuity, each momentum
                   # component, energy and turbulence, each against its own limit
                   equation_orders=entry.get("equation_orders"),
                   cl_pct=checks["cl_percent"]["value"],
                   cd_pct=checks["cd_percent"]["value"],
                   cmy_abs=checks["cmy_absolute"]["value"])
    else:
        for field in ("gate_verdict", "iterations", "orders_dropped",
                      "equation_orders", "cl_pct", "cd_pct", "cmy_abs"):
            if row[field] is None:
                absent(field, "convergence_gate.py has not judged this run")

    # ---- physics checks -----------------------------------------------------
    surface = surface_file(run)
    if surface:
        row["surface_field_path"] = repo_relative(surface)
        cp = cgns_variable(surface, "CoefPressure")
        if cp is not None and cp.size:
            over = cp > CP_PHYSICAL_MAX
            row["cp_cells_over_bound"] = int(over.sum())
            row["cp_peak_excess"] = float(cp.max() - CP_PHYSICAL_MAX)
        else:
            absent("cp_cells_over_bound", "no CoefPressure in the surface solution")
            absent("cp_peak_excess", "no CoefPressure in the surface solution")
        yplus = cgns_variable(surface, "YPlus")
        if yplus is not None and yplus.size:
            row["yplus_min_p50_p95_p99_max"] = [
                float(yplus.min()), float(np.quantile(yplus, 0.50)),
                float(np.quantile(yplus, 0.95)), float(np.quantile(yplus, 0.99)),
                float(yplus.max())]
        else:
            absent("yplus_min_p50_p95_p99_max", "no YPlus in the surface solution")
    else:
        for field in ("surface_field_path", "cp_cells_over_bound", "cp_peak_excess",
                      "yplus_min_p50_p95_p99_max"):
            absent(field, "no surface CGNS beside the run")
    vol = volume_file(run)
    if vol:
        row["volume_field_path"] = repo_relative(vol)
    else:
        absent("volume_field_path", "no volume CGNS beside the run")
    row["node_ordering"] = NODE_ORDERING

    # ---- low fidelity -------------------------------------------------------
    if avl:
        # `row["alpha_deg"] or 1e9` is wrong and was wrong here: 0.0 is FALSY,
        # so alpha 0 -- the cruise point, the one every comparison is anchored
        # on -- fell through to the sentinel and never matched its AVL point,
        # while every other angle matched fine. A guard that fails for exactly
        # one value is worse than one that fails for all of them.
        alpha = row["alpha_deg"]
        point = None
        if alpha is not None:
            point = next((p for p in avl.get("points", [])
                          if abs(float(p.get("alpha_deg", 1e9)) - alpha) < 1e-6), None)
        if point and point.get("s_ref") and row.get("area_ref") and \
                abs((float(point["s_ref"]) / 2.0) / row["area_ref"] - 1.0) > 0.005:
            for field in SCHEMA["low_fidelity"]:
                absent(field, "CFD and AVL reference areas differ (defect 23); not paired")
            point = None
        if point:
            row.update(avl_cl=point.get("cl"), avl_cd=point.get("cd"),
                       avl_cm=point.get("cm") if "cm" in point else point.get("cmy"),
                       avl_status=avl.get("status", "ok"))
        else:
            for field in SCHEMA["low_fidelity"]:
                absent(field, f"AVL has no point at alpha {row['alpha_deg']}")
    else:
        for field in SCHEMA["low_fidelity"]:
            absent(field, "verify_against_avl.py has not been run for this geometry")

    row["missing_fields"] = missing
    # each design's own Reynolds numbers, from the one flight condition
    try:
        from cg_limits import planform, sections
        shape = planform(index)
        root_chord = max(s["chord"] for s in sections(index))
        per_metre = float(row["reynolds"]) / float(row["chord_ref"])
        row["reynolds_per_metre"] = per_metre
        row["mac_m"] = shape["mac_m"]
        row["reynolds_mac"] = per_metre * shape["mac_m"]
        row["reynolds_root_chord"] = per_metre * root_chord
    except Exception as exc:  # noqa: BLE001 - recorded as absent, never guessed
        for field in ("reynolds_per_metre", "reynolds_mac", "reynolds_root_chord", "mac_m"):
            absent(field, f"planform unavailable: {type(exc).__name__}")

    row["schema_version"] = "aeris.s8.dataset_row.v2"
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path,
                    help="a geometry directory holding a*/ run subdirectories, "
                         "or a single run directory")
    ap.add_argument("--level")
    ap.add_argument("--index", type=int)
    ap.add_argument("--set-name", default="lhs100_seed42")
    ap.add_argument("--mesh-dir", type=Path, default=None,
                    help="where <level>_summary.json lives; defaults to --run-dir")
    ap.add_argument("--gate", type=Path, default=None,
                    help="a convergence_gate.py report covering these runs")
    ap.add_argument("--avl", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--print-schema", action="store_true")
    args = ap.parse_args()

    if args.print_schema:
        for group, fields in SCHEMA.items():
            print(f"\n# {group}")
            for field in fields:
                print(f"  {field}")
        print(f"\n{len(FLAT_SCHEMA)} fields in {len(SCHEMA)} groups")
        return 0

    if args.run_dir is None or args.level is None or args.index is None:
        ap.error("--run-dir, --level and --index are required unless --print-schema")

    mesh_dir = args.mesh_dir or args.run_dir
    # `a*` also matches the avl/ directory the pilot writes beside the runs,
    # which became a fifth "run" row with 29 empty fields. A run is a directory
    # that actually holds a run.
    # Runs for THIS level only. Globbing a* picked up every level's runs in a
    # shared geometry directory, and the avl/ directory besides.
    runs = sorted(p for p in args.run_dir.glob(f"{args.level}_a*")
                  if p.is_dir() and ((p / "result.json").exists()
                                     or (p / "run.log").exists()))
    if not runs:
        runs = sorted(p for p in args.run_dir.glob("a*")
                      if p.is_dir() and ((p / "result.json").exists()
                                         or (p / "run.log").exists()))
    if not runs:
        runs = [args.run_dir]

    gate = None
    gate_path = args.gate or (args.run_dir / "gate.json")
    if gate_path.exists():
        gate = json.loads(gate_path.read_text())
    # verify_against_avl.py writes avl_sweep.json (a LIST of {alpha_deg, raw})
    # beside avl_reference.json (the moment reference). Taking the
    # alphabetically first json picked the reference file, which has no points,
    # so every row lost its low-fidelity counterpart -- and those are what the
    # multifidelity correction this campaign exists to build is fitted on.
    avl = None
    for candidate in ([args.avl] if args.avl else []) + [
            args.run_dir / "avl" / "avl_sweep.json",
            args.run_dir / "avl" / "avl_verification.json"]:
        if candidate and candidate.exists():
            raw = json.loads(candidate.read_text())
            if isinstance(raw, list):
                avl = {"points": [{"alpha_deg": r["alpha_deg"], **r.get("raw", {})}
                                  for r in raw], "status": "ok",
                       "source": str(candidate)}
            else:
                avl = raw
            break

    try:
        import env_s8
        mach_python = env_s8.resolve()["mach_python"]
    except SystemExit:
        mach_python = None

    cache: dict = {}
    rows = [build_row(run=run, level=args.level, index=args.index,
                      set_name=args.set_name, mesh_dir=mesh_dir, gate=gate,
                      avl=avl, mach_python=mach_python, cache=cache)
            for run in runs]

    print(f"{len(rows)} row(s) from {args.run_dir}\n")
    print(f"{'alpha':>7}{'CL':>11}{'CD':>11}{'CMy':>11}  {'verdict':<24} missing")
    for row in rows:
        alpha = row["alpha_deg"]
        print(f"{alpha if alpha is not None else float('nan'):>7.1f}"
              f"{row['CL'] if row['CL'] is not None else float('nan'):>11.6f}"
              f"{row['CD'] if row['CD'] is not None else float('nan'):>11.6f}"
              f"{row['CMy'] if row['CMy'] is not None else float('nan'):>11.6f}  "
              f"{str(row['gate_verdict']):<24} {len(row['missing_fields'])}")
    gaps: dict[str, str] = {}
    for row in rows:
        gaps.update(row["missing_fields"])
    if gaps:
        print(f"\nfields not filled, and why -- PLAN 0.4: a number that is computed "
              f"and discarded is how a 2.6x drift stayed invisible")
        for field, why in sorted(gaps.items()):
            print(f"  {field:<32} {why}")
    else:
        print("\nevery schema field filled")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(
            {"schema_version": "aeris.s8.dataset_row.v2", "schema": SCHEMA,
             "rows": rows}, indent=2) + "\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
