"""S0 volume marching — get a volume at all, then refine.

    prepare  [--surface L1_coarse] [--level smoke] [--geom N]   stage + write run inputs
    collect  [--surface L1_coarse] [--level smoke] [--geom N]   apply the frozen checklist

Order of business, and it is deliberate: **make a volume exist before making it
good.** ADR-0010 is the reason. Stage 02 spent an entire stage driving the minimum
scaled Jacobian up and produced a surface that could not march at all, while cap4
— seventy times worse on shape — marched to a usable volume. Surface quality and
marchability are different properties, and only one of them is the deliverable.

So the first target is a completed march with zero inverted cells, at the cheapest
settings that mean anything. Quality comes after.

Heavy compute is prepared here, not launched: `prepare` writes the pyHyp inputs and
prints the commands; the user runs them; `collect` reads them back and applies the
ADR-0008 checklist verbatim.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _p in (str(REPO_ROOT / "src"), str(STUDIES), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import strategy_s0 as S0  # noqa: E402
from shared import gates, geometry_sets, pyhyp_runner  # noqa: E402
from shared.qc import qc_blocks  # noqa: E402

# Volume artifacts are large and fully regenerable, so they live in the
# regenerable artifacts area rather than in the tracked study folder.
WORK = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/strategy_studies/S0_cap4"
DEV_SET = "lhs100_seed42"


def _blocks(surface_level: str, geom: int):
    wing = geometry_sets.wing(DEV_SET, geom)
    blocks, info = S0.build_surface(wing, level=surface_level)
    return wing, blocks, info


def _extreme_blocks(surface_level: str, name: str):
    sys.path.insert(0, str(HERE))
    from validate_s0 import EXTREMES, extreme_wing

    wing = extreme_wing(name, EXTREMES[name])
    blocks, info = S0.build_surface(wing, level=surface_level)
    return wing, blocks, info


def prepare(surface_level: str, level: str, geoms: list[int], extreme: str | None = None) -> int:
    out = WORK / surface_level / level
    commands: list[str] = []
    cases = [("extreme_" + extreme, None)] if extreme else [
        (geometry_sets.geometry_id(DEV_SET, g), g) for g in geoms
    ]
    for gid, g in cases:
        if g is None:
            _wing, blocks, info = _extreme_blocks(surface_level, extreme)
        else:
            _wing, blocks, info = _blocks(surface_level, g)
        qc = qc_blocks(blocks)
        manifest = pyhyp_runner.prepare(
            strategy_id=S0.STRATEGY_ID,
            geometry_id=gid,
            blocks=blocks,
            out_dir=out,
            level=level,
        )
        commands += manifest["commands"]
        march = manifest["runs"][0]["marchability"]
        print(
            f"{gid}  blocks {qc['block_count']}  cells {qc['total_cells']}  "
            f"minJac {qc['global']['min_scaled_jacobian']:+.5f}  "
            f"range {march.get('cell_size_range', float('nan')):.1f}  "
            f"min/s0 {march.get('min_cell_over_s0', float('nan')):.1f}"
        )

    (out / "commands.sh").parent.mkdir(parents=True, exist_ok=True)
    (out / "commands.sh").write_text("\n".join(commands) + "\n")
    print(f"\n{len(commands)} marches prepared. Run them:\n")
    for c in commands:
        print(f"  {c}")
    print(f"\n  (all of them: bash {out / 'commands.sh'})")
    print(
        "\nReference to beat — cap4 at Stage 01 on the same protocol: "
        f"{gates.CAP4_REFERENCE['bad_layers']}/{gates.CAP4_REFERENCE['layer_count']} "
        f"bad layers, min quality {gates.CAP4_REFERENCE['min_quality']}"
    )
    return 0


def collect(surface_level: str, level: str, geoms: list[int]) -> int:
    out = WORK / surface_level / level
    gids = [geometry_sets.geometry_id(DEV_SET, g) for g in geoms]
    report = pyhyp_runner.collect(
        strategy_id=S0.STRATEGY_ID, out_dir=out, geometry_ids=gids, level=level
    )
    report["surface_level"] = surface_level
    print(f"{'geometry':22s} {'epsE':>5s} {'state':>7s} {'bad':>5s} {'layers':>7s} {'minQ':>10s}")
    for r in report["rows"]:
        if r["state"] == "NOT_RUN":
            print(f"{r['geometry']:22s} {r['epsE']:5.1f} {'NOT_RUN':>7s}")
            continue
        mq = r["min_quality"]
        print(
            f"{r['geometry']:22s} {r['epsE']:5.1f} {r['state']:>7s} "
            f"{str(r['low_quality_layers']):>5s} {str(r['layer_count']):>7s} "
            f"{(f'{mq:+.5f}' if mq is not None else 'n/a'):>10s}"
        )
        for f in r["failures"]:
            print(f"    - {f}")
    print(f"\nepsE passing every geometry: {report['epse_passing_all_geometries']}")
    print(f"selected: {report['epse_selected']}   ({report['not_final_until']})")
    print(
        f"cap4 reference: {gates.CAP4_REFERENCE['bad_layers']}/"
        f"{gates.CAP4_REFERENCE['layer_count']} bad, "
        f"min quality {gates.CAP4_REFERENCE['min_quality']}"
    )
    (out / "s0_collect.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["prepare", "collect"])
    ap.add_argument("--surface", default="L1_coarse", choices=list(S0.LEVELS))
    ap.add_argument("--level", default="smoke")
    ap.add_argument("--geom", type=int, nargs="+", default=[0])
    ap.add_argument("--extreme", default=None)
    a = ap.parse_args()
    if a.command == "prepare":
        return prepare(a.surface, a.level, a.geom, a.extreme)
    return collect(a.surface, a.level, a.geom)


if __name__ == "__main__":
    raise SystemExit(main())
