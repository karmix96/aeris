"""Production pyGeo -> AVL adapter: assembly + (optional) end-to-end viscous run.

The assembly test needs pyGeo/pySpline (loft), AeroSandbox (AVL serializer +
coords->Kulfan), and NeuralFoil (polar store); it is skipped when any is absent.
It verifies the adapter wires section_map + polar_store into solver_options and
builds a valid ASB carrier — without requiring the AVL binary. The end-to-end
viscous run additionally needs the `avl` binary and is skipped otherwise.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("pygeo")
pytest.importorskip("aerosandbox")
pytest.importorskip("neuralfoil")

from aeris.aero.models import FlightCondition  # noqa: E402
from aeris.common.config import load_yaml_config  # noqa: E402
from aeris.generators.bwb_segmented_v1.pygeo_adapter import (  # noqa: E402
    build_pygeo,
    extract_sections,
    stations_from_records,
)
from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (  # noqa: E402
    build_pygeo_aero_input,
    run_pygeo_avl_case,
)
from aeris.generators.bwb_segmented_v1.pygeo_backend import (  # noqa: E402
    _resolve_airfoil_database,
)
from aeris.generators.bwb_segmented_v1.services import (  # noqa: E402
    build_section_geometry_from_sample,
    generate_bwb_planform_from_sample,
)
from aeris.geometry.config_resolver import resolve_generator_and_config  # noqa: E402
from aeris.geometry.registry import get_geometry_generator  # noqa: E402

CONFIG = Path("configs/geometry/paper1_bwb_pygeo.yaml")


def _extract(n_sections: int = 9):
    raw = load_yaml_config(CONFIG)
    gid, g = resolve_generator_and_config(raw)
    gen = get_geometry_generator(gid)
    s = gen.sample_one(g, seed=g.generator.seed)
    pf = generate_bwb_planform_from_sample(s, g)
    sg = build_section_geometry_from_sample(pf, s, g)
    st = tuple(stations_from_records(sg.sections, _resolve_airfoil_database(g)))
    frame_mode = "asb_frame" if g.pygeo.frame_mode == "aeris_frame" else g.pygeo.frame_mode
    b = build_pygeo(st, k_span=g.pygeo.k_span, frame_mode=frame_mode, n_ctl=g.pygeo.n_ctl,
                    tip=g.pygeo.tip, tip_scale=g.pygeo.tip_scale)
    ex = extract_sections(b, np.linspace(0.03, 0.97, n_sections), cst_order=8,
                          chordwise_points=181)
    return ex


def test_adapter_wires_viscous_solver_options() -> None:
    ex = _extract()
    semispan = max(float(s.y_m) for s in ex)
    fc = FlightCondition(alpha_deg=4.0, velocity_mps=28.0, altitude_m=0.0)
    ai = build_pygeo_aero_input(
        extracted_sections=ex, flight_condition=fc, semispan_m=semispan,
        name="pygeo_test", viscous=True,
    )

    # geometry view carries the pyGeo-backed ASB airplane
    assert ai.geometry.source_generator == "bwb_segmented_v1_pygeo"
    assert ai.geometry.airplane is not None
    assert len(ai.geometry.airplane.wings[0].xsecs) == len(ex)

    # viscous correction is wired via solver_options
    so = ai.settings.solver_options
    assert "section_map" in so and "polar_store" in so
    # section_map resolves an airfoil id at an interior span station
    aid = so["section_map"].get_airfoil_id(0.5 * semispan)
    assert aid is not None
    assert so["polar_store"].has_airfoil(aid)


def test_adapter_viscous_can_be_disabled() -> None:
    ex = _extract()
    semispan = max(float(s.y_m) for s in ex)
    fc = FlightCondition(alpha_deg=2.0, velocity_mps=28.0, altitude_m=0.0)
    ai = build_pygeo_aero_input(
        extracted_sections=ex, flight_condition=fc, semispan_m=semispan, viscous=False,
    )
    assert "section_map" not in ai.settings.solver_options
    assert "polar_store" not in ai.settings.solver_options


@pytest.mark.skipif(shutil.which("avl") is None, reason="avl binary not available")
def test_pygeo_avl_end_to_end_viscous(tmp_path: Path) -> None:
    ex = _extract(n_sections=11)
    fc = FlightCondition(alpha_deg=4.0, velocity_mps=28.0, altitude_m=0.0)
    res = run_pygeo_avl_case(
        flight_condition=fc, output_dir=tmp_path, extracted_sections=ex,
        viscous=True, name="pygeo_e2e",
    )
    assert res.status.name == "SUCCESS"
    assert res.cl is not None and res.cl > 0.0
    # viscous total = induced + profile, both positive and finite
    assert res.cd_ind is not None and res.cd_ind > 0.0
    assert res.cd_profile is not None and res.cd_profile > 0.0
    assert res.cd_total == pytest.approx(res.cd_ind + res.cd_profile, rel=1e-6)
    assert res.l_over_d_viscous is not None and res.l_over_d_viscous > 0.0
