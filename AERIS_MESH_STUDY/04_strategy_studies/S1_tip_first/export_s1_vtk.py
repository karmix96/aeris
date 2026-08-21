"""Export S1 surfaces as VTK for ParaView, at the confirmed configuration.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S1_tip_first/export_s1_vtk.py

Per-CELL arrays, so bad cells are found by thresholding rather than by eye:

    scaled_jacobian   signed. NEGATIVE = folded. Same definition the QC table uses.
    shape_metric      minimum corner shape metric.
    skewness          equiangle skewness, 0 good, 1 degenerate.
    block_id          integer index of the source block.
    is_tip            1 for the seven tip-cap domains, 0 for the six OML blocks.

Volumes need no export — ParaView reads the pyHyp CGNS directly.
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

import strategy_s1 as S1  # noqa: E402
from shared import geometry_sets  # noqa: E402
from shared.export_paraview import write_vtk  # noqa: E402
from shared.qc import qc_blocks  # noqa: E402

OUT = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/paraview_inspection/S1_surface"
GEOMS = (1, 2, 5)  # best, mid, worst by confirmed min volume quality


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for i in GEOMS:
        wing = geometry_sets.wing("lhs100_seed42", i)
        blocks, info = S1.build_surface(wing, level="L2_smoke")
        qc = qc_blocks(blocks)
        path = OUT / f"S1_{i:03d}_surface.vtk"
        stats = write_vtk(path, blocks)
        print(
            f"{path.name:28s} cells {stats['cells']:6d}  folded {stats['folded_cells']:3d}  "
            f"minJac {stats['min_scaled_jacobian']:+.5f}  "
            f"skew {qc['global']['max_equiangle_skewness']:.3f}  "
            f"range {qc['cell_size_range']:.1f}"
        )
    print(f"\nwritten to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
