#!/usr/bin/env python
"""Verify a rented host BEFORE it starts billing.

    .venv/bin/python .../cloud_preflight.py --level gci_F [--smoke]

Every check here is a failure this project has actually hit. On a development
machine each cost hours; on rented compute each costs hours AND money, and
several of them are SILENT -- they produce plausible output rather than an
error, so a batch can complete, bill in full, and be worthless.

  interpreters      the plan documents hard-code /home/mike/miniconda3, which is
                    another machine. env_s8 resolves by VERIFYING (it imports
                    adflow to confirm) rather than by convention.
  MPI runtime       the launcher must be the one mpi4py was built against. A
                    mismatch does NOT error: the ranks never form a
                    communicator, every process believes it is rank 0 of 1, and
                    six of them overwrite each other's output while reporting
                    success. Checked by launching and counting distinct ranks.
  CGNS container    ADflow writes ADF where its CGNS library lacks HDF5, and
                    h5py then reads NOTHING from every solution file in silence.
                    That emptied a plot panel, an analysis and every dataset row
                    before it was noticed.
  memory            sized on the ANK-only law, against what is actually
                    AVAILABLE rather than installed, with the per-geometry cell
                    variation carried. gci_M died at 12.0 GiB predicted against
                    11.8 available.
  disk              a gci_FF volume solution is roughly 250 MB and the batch
                    writes one per run.
  authorization     POLICY.yaml must carry a signed entry covering the levels
                    about to run. gci_F is not in the desktop campaign's entry.
  geometry          the design set must load and produce the authorized indices.
  smoke             optionally solve twenty iterations on the coarsest level, to
                    prove the whole chain end to end before the batch starts.
"""

from __future__ import annotations

import argparse
import json
import collections
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))

QUAL = REPO / "AERIS_MESH_STUDY/05_s6_cfd_qualification"
MEM_ANK = (2.69, 7.23)
CELL_MARGIN = 1.05
#: Cell counts, from the meshes that were actually BUILT rather than from a
#: level definition. Every figure in the old table was stale: the wall-resolved
#: tip cap adds about 6 % and it landed after those numbers were taken, so
#: gci_FF was carried at 4,504,420 when the built mesh is 4,682,524. Sizing a
#: rented machine from a stale cell count is how you rent one that cannot hold
#: the job.
_FALLBACK_CELLS = {"gci_C": 567_256, "gci_M": 1_111_152,
                   "gci_F": 2_217_680, "gci_FF": 4_504_420}
_MESH_MANIFEST = (Path(__file__).resolve().parents[3]
                  / "AERIS_MESH_STUDY/05_s6_cfd_qualification/reports/s8_cloud_meshes.json")


def _measured_cells() -> dict:
    """Largest built mesh per level, from the manifest cloud_prep_build.py writes."""
    out = dict(_FALLBACK_CELLS)
    try:
        import json
        for m in json.loads(_MESH_MANIFEST.read_text())["meshes"]:
            if m.get("clean"):
                out[m["level"]] = max(out.get(m["level"], 0), m["cells"])
    except (OSError, ValueError, KeyError):
        pass
    return out


CELLS = _measured_cells()
#: A gci_FF volume solution is about 1.2 GiB, a gci_F about 0.6. The old
#: estimate of 0.3 GiB a run was taken at gci_C size.
VOLUME_GIB = {"gci_C": 0.3, "gci_M": 0.45, "gci_F": 0.7, "gci_FF": 1.3}


class Check:
    def __init__(self):
        self.results: list[dict] = []

    def add(self, name: str, ok: bool, detail: str, fatal: bool = True) -> bool:
        self.results.append({"check": name, "pass": bool(ok), "detail": detail,
                             "fatal": fatal})
        mark = "PASS" if ok else ("FAIL" if fatal else "WARN")
        print(f"  [{mark}] {name}\n         {detail}")
        return bool(ok)


def check_interpreters(c: Check) -> dict:
    import env_s8
    try:
        env = env_s8.resolve()
    except SystemExit as exc:
        c.add("interpreters", False, str(exc))
        return {}
    c.add("interpreters", True,
          f"mach-aero {env['mach_python']} ({env['mach_python_source']})")
    c.add("mpi launcher", "env's own" in env["mpirun_source"],
          f"{env['mpirun']} -- {env['mpirun_source']}",
          fatal=False)
    return env


def check_mpi_ranks(c: Check, env: dict, ranks: int) -> None:
    """Launch and count DISTINCT ranks. The silent failure gives six rank-0s."""
    code = ("from mpi4py import MPI;c=MPI.COMM_WORLD;"
            "print('RANK', c.Get_rank(), 'OF', c.Get_size())")
    try:
        out = subprocess.run([env["mpirun"], "-np", str(ranks), env["mach_python"],
                              "-c", code], capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        c.add("mpi communicator", False, f"could not launch: {exc}")
        return
    sizes = {line.split()[3] for line in out.stdout.splitlines() if line.startswith("RANK")}
    seen = {line.split()[1] for line in out.stdout.splitlines() if line.startswith("RANK")}
    ok = sizes == {str(ranks)} and len(seen) == ranks
    c.add("mpi communicator", ok,
          f"{len(seen)} distinct ranks reporting size {sizes or '{}'} "
          f"(want {ranks} ranks each reporting {ranks})"
          + ("" if ok else ". Mismatched MPI runtime: every process thinks it is "
                           "rank 0 of 1 and they will overwrite each other."))


def check_memory(c: Check, level: str, ranks: int) -> None:
    import re
    kb = int(re.search(r"^MemAvailable:\s+(\d+) kB",
                       Path("/proc/meminfo").read_text(), re.M).group(1))
    available = kb / 1024 / 1024
    cells = CELLS[level] * CELL_MARGIN
    need = MEM_ANK[0] + MEM_ANK[1] * cells / 1e6
    c.add(f"memory for {level}", available >= need + 0.5,
          f"{available:.1f} GiB available, {need:.1f} GiB needed "
          f"({CELLS[level]:,} cells x {CELL_MARGIN} margin, ANK-only law)")


def check_disk(c: Check, out: Path, cases: int, plan: list[tuple[str, int]] | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(out).free / 1024 ** 3
    if plan:
        need = sum(VOLUME_GIB.get(level, 0.5) * n for level, n in plan)
    else:
        need = cases * 0.30
    c.add("disk", free >= need,
          f"{free:.0f} GiB free at {out}, about {need:.0f} GiB needed "
          f"({cases} runs of volume solution at the per-level sizes)")


def check_authorization(c: Check, levels: list[str], indices: list[int]) -> None:
    import yaml
    policy = yaml.safe_load((QUAL / "POLICY.yaml").read_text())
    exceptions = policy.get("heavy_work", {}).get("exceptions", {})
    covered_levels: set = set()
    covered_indices: set = set()
    signed = []
    for name, entry in exceptions.items():
        detail = QUAL / entry.get("policy", "")
        if not detail.exists():
            continue
        auth = yaml.safe_load(detail.read_text()).get("authorization", {})
        if auth.get("status") != "AUTHORIZED":
            continue
        signed.append(name)
        covered_levels |= set(entry.get("grid_levels", []))
        covered_indices |= set(entry.get("geometry_indices", []))
    missing_l = sorted(set(levels) - covered_levels)
    missing_i = sorted(set(indices) - covered_indices)
    c.add("authorization", not missing_l and not missing_i,
          f"signed entries {signed}; "
          + (f"NOT authorized: levels {missing_l or '-'}, geometries {missing_i or '-'}"
             if (missing_l or missing_i) else
             f"levels {sorted(set(levels))} and {len(indices)} geometries all covered"))


def check_geometry(c: Check, indices: list[int]) -> None:
    try:
        for extra in (HERE, HERE.parent, HERE.parent / "S6_bounded_mesh_atlas",
                      REPO / "src"):
            if str(extra) not in sys.path:
                sys.path.insert(0, str(extra))
        from shared.geometry_sets import design_matrix
        X, _ = design_matrix("lhs100_seed42")
        n = len(X)
        c.add("design set", max(indices) < n,
              f"lhs100_seed42 loads, {n} designs, highest index requested "
              f"{max(indices)}")
    except Exception as exc:  # noqa: BLE001
        c.add("design set", False, f"{type(exc).__name__}: {exc}")


def check_reference_areas(c: Check, indices: list[int]) -> None:
    """Defect 23: every geometry was once normalised by index 83's area, because
    solve_s8.py defaults to it. run_campaign.py now refuses a geometry with no
    recorded area, but only when that geometry's first solve starts -- hours
    into a billed batch. This refuses before anything bills."""
    try:
        areas = json.loads((HERE / "reference_areas.json").read_text())["areas"]
    except Exception as exc:  # noqa: BLE001
        c.add("reference areas", False, f"{type(exc).__name__}: {exc}")
        return
    missing = [i for i in indices if str(i) not in areas]
    values = {i: float(areas[str(i)]["half_area_m2"]) for i in indices if str(i) in areas}
    implausible = [i for i, a in values.items() if not 0.05 < a < 2.0]
    c.add("reference areas", not missing and not implausible,
          f"{len(values)}/{len(indices)} geometries have their own half-area "
          f"({min(values.values(), default=0):.4f}-{max(values.values(), default=0):.4f} m2)"
          + (f"; MISSING {missing}" if missing else "")
          + (f"; IMPLAUSIBLE {implausible}" if implausible else ""))


def check_cgns_reader(c: Check) -> None:
    try:
        import cgns_read
        found = sorted((REPO / "AERIS_MESH_STUDY/artifacts").rglob("*surf*.cgns"))
        if not found:
            c.add("CGNS reader", True,
                  "cgns_read imports; no existing solution here to test against",
                  fatal=False)
            return
        cp = cgns_read.read_variable(found[0], "CoefPressure")
        c.add("CGNS reader", cp is not None and cp.size > 0,
              f"{'ADF' if not cgns_read.is_hdf5(found[0]) else 'HDF5'} container, "
              f"read {cp.size if cp is not None else 0} cp values from {found[0].name}")
    except Exception as exc:  # noqa: BLE001
        c.add("CGNS reader", False, f"{type(exc).__name__}: {exc}")


def check_smoke(c: Check, env: dict, ranks: int, extra: list[str] | None = None) -> None:
    """Build the coarsest mesh and solve twenty iterations. End to end.

    `extra` carries the batch's own solver flags, so a setting that aborts
    the solver -- Menter SST does, in this build -- is caught here rather
    than an hour into a billed batch.
    """
    extra = list(extra or [])
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        build = subprocess.run(
            [env["venv_python"], str(HERE / "build_volume.py"), "--level", "gci_CC",
             "--index", "83", "--out", str(out), "--no-plot3d"],
            capture_output=True, text=True, timeout=1800)
        if build.returncode != 0 or not (out / "gci_CC_blocks.npz").exists():
            c.add("smoke: mesh", False, build.stderr[-300:] or "build failed")
            return
        c.add("smoke: mesh", True, "gci_CC built from the design set")
        cgns = subprocess.run(
            [env["mach_python"], str(HERE / "write_cgns.py"),
             "--blocks", str(out / "gci_CC_blocks.npz")],
            capture_output=True, text=True, timeout=1800)
        if cgns.returncode != 0:
            c.add("smoke: CGNS", False, cgns.stderr[-300:] or "write failed")
            return
        c.add("smoke: CGNS", True, "boundary conditions written and connected")
        solve = subprocess.run(
            [env["mpirun"], "-np", str(ranks), env["mach_python"],
             str(HERE / "solve_s8.py"), "--grid", str(out / "gci_CC_volume.cgns"),
             "--alpha", "0.0", "--out", str(out / "run"), "--n-cycles", "20",
             "--l2", "1e-12", "--no-nk", "--i-have-authorization", *extra],
            capture_output=True, text=True, timeout=3600)
        log = (out / "run" / "run.log")
        ran = "parallel executable running on" in (solve.stdout + (log.read_text() if log.exists() else ""))
        c.add("smoke: solve", ran,
              "ADflow started in parallel and iterated" if ran
              else (solve.stderr[-400:] or "solver did not start"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", type=Path,
                    default=QUAL / "reports/s8_cloud_batch.json")
    ap.add_argument("--level", default=None,
                    help="check memory for this level; default the finest in the batch")
    ap.add_argument("--ranks", type=int, default=6)
    ap.add_argument("--out-dir", type=Path,
                    default=REPO / "AERIS_MESH_STUDY/artifacts")
    ap.add_argument("--smoke", action="store_true",
                    help="also build a mesh and run twenty solver iterations")
    ap.add_argument("--out", type=Path, default=QUAL / "reports/s8_cloud_preflight.json")
    args = ap.parse_args()

    batch = json.loads(args.batch.read_text()) if args.batch.exists() else {}
    levels = sorted(batch.get("levels", {})) or ["gci_F"]
    indices = sorted({c["index"] for c in batch.get("cases", [])}) or [83]
    finest = args.level or max(levels, key=lambda l: CELLS.get(l, 0))

    print(f"preflight for {len(batch.get('cases', []))} cases, "
          f"levels {levels}, {args.ranks} ranks\n")
    c = Check()
    env = check_interpreters(c)
    if env:
        check_mpi_ranks(c, env, args.ranks)
    check_memory(c, finest, args.ranks)
    by_level = collections.Counter(x.get("level") for x in batch.get("cases", []))
    check_disk(c, args.out_dir, len(batch.get("cases", [])) or 44,
               plan=[(lv, n) for lv, n in by_level.items() if lv])
    check_authorization(c, levels, indices)
    check_geometry(c, indices)
    check_reference_areas(c, indices)
    check_cgns_reader(c)
    if args.smoke and env:
        check_smoke(c, env, args.ranks, args.solver_args)

    fatal = [r for r in c.results if not r["pass"] and r["fatal"]]
    warn = [r for r in c.results if not r["pass"] and not r["fatal"]]
    report = {"checks": c.results, "fatal_failures": len(fatal),
              "warnings": len(warn),
              "verdict": "READY" if not fatal else "NOT READY",
              "levels": levels, "geometries": indices, "ranks": args.ranks}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")

    print(f"\n  {len(c.results) - len(fatal) - len(warn)}/{len(c.results)} passed, "
          f"{len(warn)} warning(s), {len(fatal)} fatal")
    print(f"  VERDICT: {report['verdict']}")
    if fatal:
        print("\n  Do not start the batch. Fatal:")
        for r in fatal:
            print(f"    - {r['check']}: {r['detail']}")
    print(f"\n  wrote {args.out}")
    return 0 if not fatal else 1


if __name__ == "__main__":
    raise SystemExit(main())
