"""Export S0 surfaces as VTK for ParaView inspection.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S0_cap4/export_s0_vtk.py

Writes one legacy-VTK unstructured grid per surface level, every block merged,
with per-CELL arrays so bad cells are found by thresholding rather than by hunting
visually:

    scaled_jacobian   minimum corner scaled Jacobian, signed. NEGATIVE = folded.
    shape_metric      minimum corner shape metric. Near zero = degenerate.
    skewness          equiangle skewness. 0 good, 1 degenerate.
    block_id          integer index of the source block.
    is_tip            1 for tip-cap blocks, 0 for OML blocks.

The volume meshes need no export — ParaView reads the pyHyp CGNS directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _p in (str(REPO_ROOT / "src"), str(STUDIES), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import strategy_s0 as S0  # noqa: E402
from shared import geometry_sets  # noqa: E402
from shared.export_paraview import write_vtk  # noqa: E402
from shared.qc import qc_blocks  # noqa: E402

OUT = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/strategy_studies/S0_cap4/paraview"
GEOM = 0
SET = "lhs100_seed42"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    wing = geometry_sets.wing(SET, GEOM)
    gid = geometry_sets.geometry_id(SET, GEOM)
    for level in ("L1_coarse", "L3_medium"):
        blocks, info = S0.build_surface(wing, level=level)
        qc = qc_blocks(blocks)
        path = OUT / f"S0_{level}_{gid}_surface.vtk"
        stats = write_vtk(path, blocks)
        print(
            f"{path.name:44s} cells {stats['cells']:6d}  folded {stats['folded_cells']:3d}  "
            f"minJac {stats['min_scaled_jacobian']:+.5f}  skew {qc['global']['max_equiangle_skewness']:.3f}"
        )
        for b in sorted(qc["blocks"], key=lambda x: x["min_scaled_jacobian"])[:3]:
            print(f"    worst: {b['name']:20s} jac {b['min_scaled_jacobian']:+.5f} "
                  f"skew {b['max_equiangle_skewness']:.3f} cells {b['cells']}")
    print(f"\nwritten to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
