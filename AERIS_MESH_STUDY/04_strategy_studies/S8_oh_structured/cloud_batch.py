#!/usr/bin/env python
"""Plan the high-fidelity cloud batch: cases, memory, time, and what to upload.

    .venv/bin/python .../cloud_batch.py --out reports/s8_cloud_batch.json

PLAN step 4. Everything here is arithmetic done BEFORE money is spent, because
the failure mode this whole sequence exists to avoid is paying to generate
eighty expensive versions of one mistake.

Sizing, from measurements rather than the datasheet
---------------------------------------------------
Two memory laws, both fitted to runs on this host:

    ANK->NK (governed)   1.51 GiB + 9.46 GiB per million cells
    ANK only             2.69 GiB + 7.23 GiB per million cells

The second is the one to size on, and not as a convenience: **NK failed at
1.11M cells with this project's lean preconditioner** (NKSubspaceSize 20,
NKPCILUFill 1 against ADflow's 60 and 2), freezing with Step 0.01 and
LinRes 1.000 while ANK alone converged the same case in a fifth of the time.
Restoring ADflow's defaults would converge but needs the memory the lean
settings were chosen to save. So the cloud choice is:

  * ANK-only at the lean settings -- PROVEN here at 1.11M, uses less memory
  * or ANK->NK with restored defaults -- needs sizing on the 9.46 law with a
    larger subspace on top, and is NOT proven at these cell counts

This plans the first and says so. Anything else needs a run to justify it.

Timing
------
Scaled from measured four-angle sweeps on 6 ranks: 54.6 min at 567k and 137.8
min at 1.11M, so about 2.5x the cell ratio -- superlinear, because the finer
grid needs more iterations as well as more work per iteration. Parallel
efficiency is assumed at 0.75 beyond 6 ranks, which is deliberately pessimistic;
if the cloud does better the batch finishes early, which is the direction to be
wrong in.

The GCI constraint that is easy to miss
----------------------------------------
PLAN step 6's grid-convergence study needs three or more levels OF THE SAME
GEOMETRY. A batch of "ten geometries at the fine level" does not contain a GCI.
So index 83 -- which already has gci_C and gci_M -- is carried at every level,
and this refuses to emit a batch where the reference geometry is missing from
one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))

QUAL = REPO / "AERIS_MESH_STUDY/05_s6_cfd_qualification"

#: measured cell counts where known; the finer two scale as r^3 from gci_M
CELLS = {"gci_C": 567_256, "gci_M": 1_111_152, "gci_F": 2_217_680, "gci_FF": 4_504_420}  # gci_FF measured: 2026-09-11 build of index 83, 0 folded cells
CELLS_MEASURED = {"gci_C", "gci_M", "gci_F"}

MEM_ANK = (2.69, 7.23)          # GiB base, GiB per million cells
MEM_NK = (1.51, 9.46)
#: cells vary by geometry -- 567,256 to 573,312 was the spread at gci_C over ten
#: designs, about 1 %. Sizing on the maximum seen plus margin.
CELL_VARIATION = 1.05
#: measured four-angle wall times on 6 ranks, minutes
MEASURED_MIN = {"gci_C": 54.6, "gci_M": 137.8}
#: measured on this desktop, index 83 gci_C alpha 0, time to the 1e-6 target at
#: 1/2/4/6 ranks (reports/s8_rank_scaling_time_to_answer.json): efficiency 1.00,
#: 0.95, 0.62, 0.43. Extrapolating that curve, 24 ranks on one case is worth about
#: 0.3 -- not 0.75. The estimate below is therefore optimistic, and the batch's
#: real lever is CONCURRENCY: several cases at 2-4 ranks each, memory permitting.
#: run_campaign.py probe measures the rented host before the batch bills.
PARALLEL_EFFICIENCY = 0.75
REFERENCE_INDEX = 83

ALPHAS = (-2.0, 0.0, 4.0, 8.0)


def memory_gib(cells: int, ank_only: bool = True) -> float:
    base, per = MEM_ANK if ank_only else MEM_NK
    return base + per * cells * CELL_VARIATION / 1.0e6


def four_angle_minutes(cells: int, ranks: int) -> float:
    """Scaled from the two measured sweeps, superlinearly in cells."""
    c0, t0 = CELLS["gci_M"], MEASURED_MIN["gci_M"]
    exponent = 1.3          # (137.8/54.6) / (1111152/567256) -> ~1.29
    on_six = t0 * (cells / c0) ** exponent
    if ranks <= 6:
        return on_six * 6 / max(ranks, 1)
    return on_six * 6 / (ranks * PARALLEL_EFFICIENCY)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--levels", nargs="+", default=["gci_F", "gci_FF"],
                    help="levels to run in the cloud")
    ap.add_argument("--all-geometry-level", default="gci_F",
                    help="the level run on ALL ten geometries; finer levels are "
                         "carried on the reference only unless --fine-geometries")
    ap.add_argument("--fine-geometries", type=int, nargs="*", default=[REFERENCE_INDEX],
                    help="geometries to carry at levels finer than "
                         "--all-geometry-level")
    ap.add_argument("--ranks", type=int, default=24)
    ap.add_argument("--ank-only", action="store_true", default=True)
    ap.add_argument("--out", type=Path, default=QUAL / "reports/s8_cloud_batch.json")
    args = ap.parse_args()

    selection = QUAL / "reports/s8_pilot_geometries.json"
    if not selection.exists():
        raise SystemExit(f"{selection} missing; run select_pilot_geometries.py")
    geometries = json.loads(selection.read_text())["selected"]

    cases = []
    for level in args.levels:
        indices = geometries if level == args.all_geometry_level else args.fine_geometries
        for index in indices:
            for alpha in ALPHAS:
                cases.append({"index": index, "level": level, "alpha_deg": alpha})

    # PLAN step 6 needs >= 3 levels of ONE geometry. Check it, do not assume it.
    have = {"gci_C", "gci_M"}                     # already run on this desktop
    reference_levels = sorted(have | {c["level"] for c in cases
                                      if c["index"] == REFERENCE_INDEX})
    if len(reference_levels) < 3:
        raise SystemExit(
            f"index {REFERENCE_INDEX} would end up with only {reference_levels}. "
            f"A grid-convergence study needs three levels OF THE SAME GEOMETRY, "
            f"and a batch of ten geometries at one fine level contains none. "
            f"Refusing to emit this batch.")

    by_level: dict = {}
    for level in args.levels:
        cells = int(CELLS[level] * CELL_VARIATION)
        n = len({(c["index"]) for c in cases if c["level"] == level})
        minutes = four_angle_minutes(CELLS[level], args.ranks)
        by_level[level] = {
            "cells_nominal": CELLS[level],
            "cells_measured": level in CELLS_MEASURED,
            "cells_sized_for": cells,
            "memory_gib_ank_only": round(memory_gib(CELLS[level], True), 1),
            "memory_gib_with_nk": round(memory_gib(CELLS[level], False), 1),
            "geometries": n,
            "four_angle_minutes_at_ranks": round(minutes, 1),
            "level_hours": round(n * minutes / 60.0, 1),
        }

    total_hours = sum(v["level_hours"] for v in by_level.values())
    report = {
        "plan_step": "4 - prepare the high-fidelity batch",
        "ranks_per_case": args.ranks,
        "parallel_efficiency_assumed": PARALLEL_EFFICIENCY,
        "solver": {
            "configuration": "ANK only (--no-nk), L2Convergence 1e-6",
            "why_ank_only": ("NK froze at 1,111,152 cells with this project's lean "
                             "preconditioner -- Step 0.01, LinRes 1.000 -- while "
                             "ANK alone converged the same case in a fifth of the "
                             "time. ANK-only is the configuration PROVEN at these "
                             "cell counts and it uses about 2 GiB less."),
            "l2_evidence": "reports/s8_l2_sensitivity.json",
        },
        "memory_laws": {
            "ank_only": f"{MEM_ANK[0]} + {MEM_ANK[1]} GiB per million cells",
            "ank_then_nk": f"{MEM_NK[0]} + {MEM_NK[1]} GiB per million cells",
            "cell_variation_margin": CELL_VARIATION,
            "note": "both fitted to runs on the development host, not datasheet values",
        },
        "levels": by_level,
        "reference_geometry": {
            "index": REFERENCE_INDEX,
            "levels_after_batch": reference_levels,
            "note": ("PLAN step 6 needs three or more levels of ONE geometry. "
                     "gci_C and gci_M already exist on the development host and "
                     "must be carried to the cloud, or re-run there, for the GCI "
                     "to be computable at all."),
        },
        "cases": cases,
        "case_count": len(cases),
        "total_solver_hours": round(total_hours, 1),
        "upload": {
            "meshes": ("BUILD IN THE CLOUD, do not upload. build_volume.py needs "
                       "only the project venv and takes about 12 s per design; a "
                       "gci_F CGNS is roughly 56 MB and gci_FF 120 MB, so ten of "
                       "each is gigabytes of transfer to avoid seconds of compute."),
            "required_repo_paths": [
                "AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/",
                "AERIS_MESH_STUDY/04_strategy_studies/shared/",
                "AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/",
                "AERIS_MESH_STUDY/05_s6_cfd_qualification/POLICY.yaml",
                "AERIS_MESH_STUDY/05_s6_cfd_qualification/policies/",
                "AERIS_MESH_STUDY/05_s6_cfd_qualification/reports/s8_pilot_geometries.json",
                "src/aeris/",
            ],
            "environment": ("MACH-Aero (ADflow + cgnsutilities) and the project "
                            "venv. env_s8.py resolves both by VERIFYING them -- it "
                            "imports adflow to confirm -- so the hard-coded paths "
                            "in the plan documents do not need editing per host."),
            "trap": ("the MPI launcher must be the one the MACH-Aero env's mpi4py "
                     "was built against. A mismatched runtime does not error: the "
                     "ranks fail to form a communicator, every process believes it "
                     "is rank 0 of 1, and they overwrite each other's output while "
                     "reporting success."),
        },
        "acceptance": {
            "gate": "convergence_gate.py, unchanged from the pilot",
            "routes": "(residual target met AND healthy) OR (orders AND forces settled)",
            "provenance": "dataset_row.py 53-field schema; collect_dataset.py archive",
            "rule": ("check the gate after EVERY geometry, not at the end. A "
                     "geometry that stalls should surface in minutes, not after "
                     "the batch."),
        },
        "authorization": {
            "current": "POLICY.yaml heavy_work.exceptions.run-s8-campaign",
            "covers": "gci_C and gci_M on the ten pilot geometries",
            "REQUIRED": ("This batch runs gci_F and gci_FF, which the current "
                         "entry does NOT authorize -- it names grid_levels "
                         "[gci_C, gci_M]. A new signed entry is needed before any "
                         "cloud run, on the same terms as PLAN 6."),
        },
    }

    print(f"cases: {len(cases)}  ({', '.join(args.levels)})  on {args.ranks} ranks\n")
    print(f"{'level':>8}{'cells':>11}{'GiB (ANK)':>11}{'GiB (+NK)':>11}"
          f"{'geoms':>7}{'h/geom':>9}{'hours':>8}")
    for level, v in by_level.items():
        mark = "" if v["cells_measured"] else "  est"
        print(f"{level:>8}{v['cells_nominal']:>11,}{v['memory_gib_ank_only']:>11.1f}"
              f"{v['memory_gib_with_nk']:>11.1f}{v['geometries']:>7}"
              f"{v['four_angle_minutes_at_ranks'] / 60:>9.2f}"
              f"{v['level_hours']:>8.1f}{mark}")
    print(f"\n  total solver time: {total_hours:.1f} h on {args.ranks} ranks")
    print(f"  index {REFERENCE_INDEX} ends with levels {reference_levels} "
          f"-> a {len(reference_levels)}-level GCI is computable")
    print(f"\n  AUTHORIZATION: {report['authorization']['REQUIRED']}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\n  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
