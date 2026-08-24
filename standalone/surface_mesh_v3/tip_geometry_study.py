"""What does a ROUNDED master tip actually give us?

The wing tip is the worst region of every AERIS surface mesh built so far, and
``SURFACE_MESH_LAWS.md`` law 13 concluded with evidence that no *blocking*
arrangement fixes it: capping a flat, 13:1 aspect airfoil face with structured
quads has no good solution. The remaining directions it named were geometric
(round the tip) or overset.

pyGeo's ``liftingSurface`` already accepts ``tip="rounded"``. AERIS has always
passed ``tip="none"`` — a square-cut tip. This script measures what changes:
the surface count and parameterisation, the planform/area consequences, and
whether the tip stops being a separate capping problem.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from aeris.generators.bwb_segmented_v1.planform import (  # noqa: E402
    generate_bwb_planform_from_sample,
)
from aeris.generators.bwb_segmented_v1.pygeo_adapter import build_pygeo, stations_from_records  # noqa: E402
from aeris.generators.bwb_segmented_v1.sections import (  # noqa: E402
    build_section_geometry_from_sample,
)
from aeris.generators.bwb_segmented_v1.validation import (  # noqa: E402
    validate_planform_result,
    validate_section_geometry,
)

from standalone.pygeo_surface_mesh_study.runner import load_generator_config, make_sample  # noqa: E402
from standalone.pygeo_surface_mesh_study.spec import load_study_spec  # noqa: E402


def stations():
    spec = load_study_spec("configs/cfd/pygeo_surface_mesh_study.yaml")
    cfg = load_generator_config(spec)
    sample = make_sample(spec, spec.baseline_case())
    planform = generate_bwb_planform_from_sample(sample, cfg)
    validate_planform_result(planform)
    section_geometry = build_section_geometry_from_sample(planform, sample, cfg)
    validate_section_geometry(section_geometry)
    return stations_from_records(section_geometry.sections, spec.airfoil_database), cfg


def describe(geometry, label: str) -> None:
    print(f"\n--- tip = {label}:  {len(geometry.surfs)} surface patch(es)")
    for i, s in enumerate(geometry.surfs):
        coef = np.asarray(s.coef, float).reshape(-1, 3)
        print(
            f"    surf {i}: nCtl {s.nCtlu:>4d} x {s.nCtlv:<3d}  order {s.ku}x{s.kv}   "
            f"y [{coef[:,1].min():.4f}, {coef[:,1].max():.4f}]  "
            f"x [{coef[:,0].min():.4f}, {coef[:,0].max():.4f}]"
        )


def main() -> None:
    st, cfg = stations()
    for tip in ("none", "rounded", "pinched"):
        try:
            build = build_pygeo(
                st,
                k_span=cfg.pygeo.k_span,
                frame_mode="asb_frame",
                n_ctl=cfg.pygeo.n_ctl,
                tip=tip,
                tip_scale=cfg.pygeo.tip_scale,
            )
        except Exception as exc:  # a tip mode that pyGeo cannot build is a result
            print(f"\n--- tip = {tip}: FAILED {type(exc).__name__}: {exc}")
            continue
        describe(build.geometry, tip)

        # Where does the outboard-most surface actually end, and is the tip
        # closed there?
        surf = build.geometry.surfs[0]
        u = np.linspace(0, 1, 9)
        for v in (0.98, 1.0):
            pu = np.asarray(surf(u, np.full_like(u, v)), float)
            pl = np.asarray(build.geometry.surfs[1](u, np.full_like(u, v)), float)
            gap = np.linalg.norm(pu - pl, axis=1)
            print(f"      v={v:.2f}: y={pu[:,1].mean():.5f}  "
                  f"upper-lower gap min {gap.min()*1e3:.4f} mm  max {gap.max()*1e3:.4f} mm")


if __name__ == "__main__":
    main()
