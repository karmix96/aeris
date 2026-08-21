"""Export every buildable strategy's surface on ONE geometry, into one folder.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/export_all_surfaces.py [--geom N]

Purpose: side-by-side ParaView inspection. Same geometry, same level, same
exporter (`shared/export_paraview.py`, ADR-0011 section 4), so the only thing that
differs between the files is the strategy's topology.

Not every strategy produces a surface:

  S0  yes    S1  yes    S3  yes (S1's surface with S3's spanwise sweep)   S4  yes
  S2  no     rejected on measurement; no deterministic block set to export
  S5  no     not started
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for _p in (str(REPO_ROOT / "src"), str(HERE), str(HERE / "S0_cap4"),
           str(HERE / "S1_tip_first"), str(HERE / "S3_station_sweep"),
           str(HERE / "S4_analytic_multiblock")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import strategy_s0 as S0  # noqa: E402
import strategy_s1 as S1  # noqa: E402
import strategy_s3 as S3  # noqa: E402
import strategy_s4 as S4  # noqa: E402
from shared import geometry_sets  # noqa: E402
from shared.export_paraview import write_vtk  # noqa: E402
from shared.qc import qc_blocks  # noqa: E402

from aeris.dataset.sampling.samplers.lhs_v1 import build_lhs_design_matrix  # noqa: E402
from aeris.generators.bwb_segmented_v1.params import (  # noqa: E402
    BWBDesignSample,
    build_bwb_generator_config,
)
from aeris.generators.bwb_segmented_v1.planform import (  # noqa: E402
    generate_bwb_planform_from_sample,
)

OUT = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/paraview_inspection/all_strategies_surface"
DEV_SET = "lhs100_seed42"
LEVEL = "L2_smoke"


def _group_boundary_y(geom: int):
    cfg = build_bwb_generator_config(
        yaml.safe_load((REPO_ROOT / "configs/geometry/bwb.yaml").read_text())
    )
    matrix = build_lhs_design_matrix(cfg, 100, np.random.default_rng(42))
    names = cfg.active_design_variable_names()
    sample = BWBDesignSample(**{k: float(v) for k, v in zip(names, matrix[geom], strict=True)})
    return generate_bwb_planform_from_sample(sample, cfg).group_boundary_y


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geom", type=int, default=0)
    a = ap.parse_args()

    gid = geometry_sets.geometry_id(DEV_SET, a.geom)
    wing = geometry_sets.wing(DEV_SET, a.geom)
    OUT.mkdir(parents=True, exist_ok=True)

    builds = {
        "S0_cap4": lambda: S0.build_surface(wing, level=LEVEL),
        "S1_tip_first": lambda: S1.build_surface(wing, level=LEVEL),
        "S3_station_sweep": lambda: S3.build_surface(
            wing, _group_boundary_y(a.geom), level=LEVEL, sigma=1.0, layers_per_interval=30
        ),
        "S4_analytic_multiblock": lambda: S4.build_surface(wing, level=LEVEL),
    }

    print(f"geometry {gid}, level {LEVEL}\n")
    print(f"{'strategy':20s} {'blk':>4s} {'cells':>8s} {'minJac':>10s} {'range':>8s}  file")
    for name, build in builds.items():
        try:
            blocks, _info = build()
        except Exception as exc:  # a strategy that cannot build says so, and we go on
            print(f"{name:20s} BUILD FAILED: {exc}")
            continue
        qc = qc_blocks(blocks)
        path = OUT / f"{name}_{gid}_surface.vtk"
        write_vtk(path, blocks)
        print(
            f"{name:20s} {qc['block_count']:4d} {qc['total_cells']:8d} "
            f"{qc['global']['min_scaled_jacobian']:+10.5f} "
            f"{qc['cell_size_range']:8.1f}  {path.name}"
        )

    print(f"\n{OUT}")
    print("Open all files, colour by `scaled_jacobian`, Threshold -1..0 to isolate folds.")
    print("S2 rejected and S5 not started — nothing to export for either.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
