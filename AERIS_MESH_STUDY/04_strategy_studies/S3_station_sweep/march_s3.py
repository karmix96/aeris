"""S3 volume marching — the ADR-0013 controlled sweep comparison against S1.

    prepare [--geom N ...]     stage surfaces + write pyHyp inputs
    collect [--geom N ...]     apply the frozen checklist

S3 holds S1's chordwise blocking and tip closure fixed and varies only the spanwise
sweep, so a difference in march outcome is a difference in the SWEEP. That is the
whole point of the ADR-0013 scoping, and it is why this comparison is worth running
even though S3 is unranked as a topology.

S1's result to beat, same geometries, same level: **10/10 at epsE 1.5 and 2.0**,
confirmed at `fine`, min quality +0.193 to +0.364.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _p in (str(REPO_ROOT / "src"), str(STUDIES), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import strategy_s3 as S3  # noqa: E402
from aeris.dataset.sampling.samplers.lhs_v1 import build_lhs_design_matrix  # noqa: E402
from aeris.generators.bwb_segmented_v1.params import (  # noqa: E402
    BWBDesignSample,
    build_bwb_generator_config,
)
from aeris.generators.bwb_segmented_v1.planform import (  # noqa: E402
    generate_bwb_planform_from_sample,
)
from shared import gates, geometry_sets, pyhyp_runner  # noqa: E402
from shared.qc import qc_blocks  # noqa: E402

WORK = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/strategy_studies/S3_station_sweep"
DEV_SET = "lhs100_seed42"
SURFACE_LEVEL = "L2_smoke"
SIGMA = 1.0          # Eq. 5 density; 1.0 = uniform, measured best (STUDY.md §5)
LAYERS = 30          # per interval, even per the paper's requirement


def _blocks(geom: int):
    cfg = build_bwb_generator_config(
        yaml.safe_load((REPO_ROOT / "configs/geometry/bwb.yaml").read_text())
    )
    matrix = build_lhs_design_matrix(cfg, 100, np.random.default_rng(42))
    names = cfg.active_design_variable_names()
    sample = BWBDesignSample(
        **{k: float(v) for k, v in zip(names, matrix[geom], strict=True)}
    )
    planform = generate_bwb_planform_from_sample(sample, cfg)
    wing = geometry_sets.wing(DEV_SET, geom)
    return S3.build_surface(
        wing, planform.group_boundary_y,
        level=SURFACE_LEVEL, sigma=SIGMA, layers_per_interval=LAYERS,
    )


def prepare(geoms: list[int], level: str) -> int:
    out = WORK / SURFACE_LEVEL / level
    commands: list[str] = []
    for g in geoms:
        gid = geometry_sets.geometry_id(DEV_SET, g)
        blocks, info = _blocks(g)
        qc = qc_blocks(blocks)
        manifest = pyhyp_runner.prepare(
            strategy_id=S3.STRATEGY_ID, geometry_id=gid, blocks=blocks,
            out_dir=out, level=level,
        )
        commands += manifest["commands"]
        march = manifest["runs"][0]["marchability"]
        print(
            f"{gid}  blocks {qc['block_count']}  cells {qc['total_cells']}  "
            f"span {info['sweep']['spanwise_cells']}  "
            f"minJac {qc['global']['min_scaled_jacobian']:+.5f}  "
            f"range {march.get('cell_size_range', float('nan')):.1f}  "
            f"min/s0 {march.get('min_cell_over_s0', float('nan')):.1f}"
        )
    (out / "commands.sh").write_text("\n".join(commands) + "\n")
    print(f"\n{len(commands)} marches prepared:\n  bash {out / 'commands.sh'}")
    return 0


def collect(geoms: list[int], level: str) -> int:
    out = WORK / SURFACE_LEVEL / level
    gids = [geometry_sets.geometry_id(DEV_SET, g) for g in geoms]
    report = pyhyp_runner.collect(
        strategy_id=S3.STRATEGY_ID, out_dir=out, geometry_ids=gids, level=level
    )
    print(f"{'geometry':22s} {'epsE':>5s} {'state':>7s} {'bad':>5s} {'minQ':>10s}")
    for r in report["rows"]:
        if r["state"] == "NOT_RUN":
            print(f"{r['geometry']:22s} {r['epsE']:5.1f} {'NOT_RUN':>7s}")
            continue
        mq = r["min_quality"]
        print(
            f"{r['geometry']:22s} {r['epsE']:5.1f} {r['state']:>7s} "
            f"{str(r['low_quality_layers']):>5s} "
            f"{(f'{mq:+.5f}' if mq is not None else 'n/a'):>10s}"
        )
    print(f"\nepsE passing every geometry: {report['epse_passing_all_geometries']}")
    print("S1 on the same geometries and level: 10/10 at epsE 1.5 and 2.0")
    (out / "s3_collect.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["prepare", "collect"])
    ap.add_argument("--level", default="smoke")
    ap.add_argument("--geom", type=int, nargs="+", default=list(range(10)))
    a = ap.parse_args()
    return prepare(a.geom, a.level) if a.command == "prepare" else collect(a.geom, a.level)


if __name__ == "__main__":
    raise SystemExit(main())
