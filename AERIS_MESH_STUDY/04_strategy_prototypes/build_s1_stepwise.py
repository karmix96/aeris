"""Build one S1 mesh, writing every construction step separately for inspection.

Each stage of the build is exported as its own VTK so the mesh can be stepped
through in ParaView rather than judged only by its final metrics. Per-cell
quality arrays are attached to every file.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_prototypes/build_s1_stepwise.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "S1_tip_first"))

import stage02_common as C  # noqa: E402
import strategy_s1  # noqa: E402
from export_for_paraview import write_vtk  # noqa: E402
from aeris.dataset.sampling.samplers.lhs_v1 import build_lhs_design_matrix  # noqa: E402
from aeris.generators.bwb_segmented_v1.params import (  # noqa: E402
    BWBDesignSample,
    build_bwb_generator_config,
)
from aeris.geometry.registry import get_geometry_generator  # noqa: E402

OUT = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/stage02/s1_stepwise"
GEOMETRY = 0
CHORD_POINTS = 49
TE_BASE_POINTS = 9
TE_THICKNESS = 0.005


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = build_bwb_generator_config(
        yaml.safe_load((REPO_ROOT / "configs/geometry/bwb.yaml").read_text())
    )
    matrix = build_lhs_design_matrix(cfg, 10, np.random.default_rng(7))
    names = cfg.active_design_variable_names()
    sample = BWBDesignSample(**{n: float(v) for n, v in zip(names, matrix[GEOMETRY], strict=True)})
    wing = get_geometry_generator("bwb_segmented").run_full_case(
        sample=sample, config=cfg, output_dir=OUT / "geometry",
        save_plot=False, build_aerosandbox=True,
    ).wing

    steps: list[dict] = []
    xsecs = list(wing.xsecs)

    # --- Step 1: section ingestion --------------------------------------
    coords_tip, le_tip = C.section_loop_2d(xsecs[-1], te_thickness=TE_THICKNESS)
    sides_by_xsec = []
    for xsec in xsecs:
        coords, le = C.section_loop_2d(xsec, te_thickness=TE_THICKNESS)
        sides_by_xsec.append(
            C.feature_split_sides(coords, le, chord_points=CHORD_POINTS,
                                  te_base_points=TE_BASE_POINTS)
        )
    steps.append({
        "step": 1, "name": "section ingestion + feature split",
        "sections": len(xsecs),
        "raw_points_per_section": int(len(coords_tip)),
        "upper_points": int(len(sides_by_xsec[0][0])),
        "lower_points": int(len(sides_by_xsec[0][1])),
        "te_base_points": int(len(sides_by_xsec[0][2])),
        "what": "each section is opened to a blunt TE and split at the LE and the two "
                "TE base corners - features only, never a smooth x/c station",
    })

    # --- Step 2: OML loft ------------------------------------------------
    oml = C._map_sides_to_wing(wing, sides_by_xsec)
    oml_names = ["oml_upper", "oml_lower", "te_base"]
    oml_blocks = [C.SurfaceBlock(name=n, xyz=b, family="wall")
                  for n, b in zip(oml_names, oml, strict=True)]
    st = write_vtk(OUT / "step2_oml_only.vtk", oml_blocks)
    q = C.qc_blocks(oml_blocks)
    steps.append({
        "step": 2, "name": "OML loft (3 blocks, tip still OPEN)",
        "blocks": [f"{b.name} {b.xyz.shape[0]}x{b.xyz.shape[1]}" for b in oml_blocks],
        "cells": st["cells"], "folded": st["folded_cells"],
        "min_scaled_jacobian": q["global"]["min_scaled_jacobian"],
        "max_aspect_ratio": q["global"]["max_aspect_ratio"],
        "vtk": "step2_oml_only.vtk",
        "what": "the 2D section curves are swept through every station by the trusted "
                "aeris mesh_line path; the tip is an open hole at this point",
    })

    # --- Step 3: the tip ring -------------------------------------------
    ring_2d, ring_info = C.oml_tip_ring_2d(sides_by_xsec[-1])
    steps.append({
        "step": 3, "name": "tip ring taken FROM the OML edge",
        "ring_points": ring_info["ring_points"],
        "corner_indices": ring_info["corner_indices"],
        "arc_counts": ring_info["arc_counts"],
        "what": "the ring is the OML's own tip-edge curve, reused node-for-node. "
                "Resampling it instead is what left an 11 mm hole earlier.",
    })

    # --- Step 4: the tip cap --------------------------------------------
    cap_2d, cap_info = C.butterfly_from_ring(ring_2d, ring_info["corner_indices"])
    cap_blocks = [C.SurfaceBlock(name=n, xyz=C.map_2d_patch_to_tip(wing, p), family="wall")
                  for n, p in zip(cap_info["block_names"], cap_2d, strict=True)]
    st = write_vtk(OUT / "step4_tip_cap_only.vtk", cap_blocks)
    steps.append({
        "step": 4, "name": "tip cap: camber-split rectangle + 4 collars",
        "blocks": [f"{b.name} {b.xyz.shape[0]}x{b.xyz.shape[1]}" for b in cap_blocks],
        "cells": st["cells"], "folded": st["folded_cells"],
        "width_frac": cap_info["width_frac"], "chord_inset": cap_info["chord_inset"],
        "collar_points": cap_info["collar_points"],
        "vtk": "step4_tip_cap_only.vtk",
        "what": "inner boundary = camber + width_frac*(surface - camber), so it is inside "
                "the section by construction; inset chordwise so collar ends slant",
    })

    # --- Step 5: assembled, before orientation ---------------------------
    assembled = oml_blocks + cap_blocks
    st = write_vtk(OUT / "step5_assembled_raw.vtk", assembled)
    steps.append({
        "step": 5, "name": "assembled, BEFORE normal orientation",
        "blocks": len(assembled), "cells": st["cells"], "folded": st["folded_cells"],
        "vtk": "step5_assembled_raw.vtk",
        "what": "geometrically complete, but block normals disagree - this is the state "
                "pyHyp rejected with 'Normal directions may be wrong'",
    })

    # --- Step 6: final, oriented ----------------------------------------
    final, info = strategy_s1.build_surface(
        wing, chord_points=CHORD_POINTS, te_base_points=TE_BASE_POINTS,
        te_thickness=TE_THICKNESS,
    )
    st = write_vtk(OUT / "step6_final_oriented.vtk", final)
    q = C.qc_blocks(final)
    steps.append({
        "step": 6, "name": "final: normals propagated across shared edges",
        "blocks": len(final), "cells": st["cells"], "folded": st["folded_cells"],
        "flipped": info["orientation"]["flipped"],
        "all_blocks_connected": info["orientation"]["all_blocks_connected"],
        "min_scaled_jacobian": q["global"]["min_scaled_jacobian"],
        "max_skew": q["global"]["max_equiangle_skewness"],
        "max_aspect_ratio": q["global"]["max_aspect_ratio"],
        "accepted_pre_pyhyp": q["accepted_pre_pyhyp"],
        "vtk": "step6_final_oriented.vtk",
        "what": "orientation propagated by edge adjacency, then flipped globally so the "
                "enclosed volume is positive (normals outward)",
    })

    (OUT / "s1_build_steps.json").write_text(json.dumps(
        {"schema": "aeris.mesh_study.s1_stepwise.v1", "geometry": f"lhs7_{GEOMETRY:02d}",
         "steps": steps}, indent=2) + "\n")

    for s in steps:
        extra = ""
        if "cells" in s:
            extra = f"  cells={s['cells']:5d} folded={s['folded']:3d}"
        print(f"step {s['step']}: {s['name']}{extra}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
