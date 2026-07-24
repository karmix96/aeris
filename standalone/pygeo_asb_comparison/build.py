"""Build BOTH backends from one config + seed, from the SAME sampled sections.

The single design sample flows to both realizations, so any downstream difference
is purely the two tools (smooth pyGeo loft vs AeroSandbox piecewise), never a
different design. No CAD / STEP / mesh / file exports are produced — geometry only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class BothBackends:
    seed: int
    config: Any
    sample: Any
    extracted: list          # pyGeo realized ExtractedSections
    pygeo_build: Any         # PyGeoBuild (for surface sampling)
    asb_result: Any          # AeroSandboxGeometryResult
    semispan_m: float


def build_both(config_path: "Path | str", *, seed: int, n_sections: int = 25,
               span_margin: float = 1.0e-4) -> BothBackends:
    # NOTE: span_margin must be tiny here. Metrics (span/area/volume) are
    # integrated over the extracted span, so extracting only [margin, 1-margin]
    # would understate the pyGeo span by ~2*margin and bias every integral. Use a
    # near-zero margin so pyGeo spans the FULL loft, comparable to the ASB wing.
    from aeris.common.config import load_yaml_config
    from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import build_aerosandbox_geometry
    from aeris.generators.bwb_segmented_v1.pygeo_adapter import (
        build_pygeo,
        extract_sections,
        stations_from_records,
    )
    from aeris.generators.bwb_segmented_v1.pygeo_backend import _resolve_airfoil_database
    from aeris.generators.bwb_segmented_v1.services import (
        build_section_geometry_from_sample,
        generate_bwb_planform_from_sample,
    )
    from aeris.geometry.config_resolver import resolve_generator_and_config
    from aeris.geometry.registry import get_geometry_generator

    raw = load_yaml_config(Path(config_path))
    gid, gcfg = resolve_generator_and_config(raw)
    gen = get_geometry_generator(gid)
    sample = gen.sample_one(gcfg, seed=seed)
    planform = generate_bwb_planform_from_sample(sample, gcfg)
    sg = build_section_geometry_from_sample(planform, sample, gcfg)

    # AeroSandbox realization
    asb_result = build_aerosandbox_geometry(sg, gcfg)

    # pyGeo realization (loft + realized-section extraction)
    stations = tuple(stations_from_records(sg.sections, _resolve_airfoil_database(gcfg)))
    frame_mode = "asb_frame" if gcfg.pygeo.frame_mode == "aeris_frame" else gcfg.pygeo.frame_mode
    build = build_pygeo(stations, k_span=gcfg.pygeo.k_span, frame_mode=frame_mode,
                        n_ctl=gcfg.pygeo.n_ctl, tip=gcfg.pygeo.tip, tip_scale=gcfg.pygeo.tip_scale)
    lo, hi = float(span_margin), float(1.0 - span_margin)
    extracted = list(extract_sections(
        build, np.linspace(lo, hi, int(n_sections)),
        cst_order=gcfg.pygeo.extraction.cst_order,
        chordwise_points=gcfg.pygeo.extraction.chordwise_points,
    ))
    semispan = max(float(s.y_m) for s in extracted)
    return BothBackends(seed=seed, config=gcfg, sample=sample, extracted=extracted,
                        pygeo_build=build, asb_result=asb_result, semispan_m=semispan)
