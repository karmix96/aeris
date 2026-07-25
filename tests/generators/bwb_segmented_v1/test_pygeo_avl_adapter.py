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
    run_pygeo_native_avl_case,
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

# The one unified geometry config (DECISION-0001).
CONFIG = Path("configs/geometry/bwb.yaml")


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
    # FULL span: an inset leaves a centreline gap under YDUPLICATE (DECISION-0005).
    ex = extract_sections(b, np.linspace(0.0, 1.0, n_sections), cst_order=8,
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


@pytest.mark.skipif(shutil.which("avl") is None, reason="avl binary not available")
def test_native_avl_end_to_end_matches_asb(tmp_path: Path) -> None:
    """Native (no asb.Airplane) path reproduces the asb-serialized numbers."""
    ex = _extract(n_sections=11)
    fc = FlightCondition(alpha_deg=4.0, velocity_mps=28.0, altitude_m=0.0)
    native = run_pygeo_native_avl_case(
        flight_condition=fc, output_dir=tmp_path / "native", extracted_sections=ex,
        viscous=True, name="native_e2e",
    )
    asb = run_pygeo_avl_case(
        flight_condition=fc, output_dir=tmp_path / "asb", extracted_sections=ex,
        viscous=True, name="asb_e2e",
    )
    assert native.status == "SUCCESS"
    assert native.cd_total == pytest.approx(native.cd_ind + native.cd_profile, rel=1e-6)
    # Native vs asb-serialized agree to sub-percent (airfoil-resolution diff only).
    assert native.cl == pytest.approx(asb.cl, rel=2e-2)
    assert native.cd_total == pytest.approx(asb.cd_total, rel=3e-2)


@pytest.mark.skipif(shutil.which("avl") is None, reason="avl binary not available")
def test_native_avl_captures_full_output_family(tmp_path: Path) -> None:
    """DECISION-0005 §1: the native runner must capture everything AVL exports."""
    import json

    from aeris.aero.solvers.avl_output import (
        BODY_DERIVATIVE_KEYS,
        STABILITY_DERIVATIVE_KEYS,
    )

    ex = _extract(n_sections=11)
    fc = FlightCondition(alpha_deg=4.0, beta_deg=2.0, velocity_mps=28.0, altitude_m=0.0)
    control = {"name": "elevon", "hinge_point": 0.75, "symmetric": True,
               "start_frac": 0.6, "end_frac": 0.95}
    res = run_pygeo_native_avl_case(
        flight_condition=fc, output_dir=tmp_path, extracted_sections=ex,
        control=control, control_input_deg=3.0, diff_input_deg=2.0,
        viscous=True, name="native_capture",
    )
    assert res.status == "SUCCESS"

    # span efficiency + neutral point
    assert res.span_efficiency is not None and 0.0 < res.span_efficiency <= 1.5
    assert res.x_np is not None
    assert res.x_np_over_c_ref is not None
    # static margin must NOT be invented when the moment ref is not the CG
    assert res.static_margin is None

    # every stability- and body-axis derivative present
    for key in STABILITY_DERIVATIVE_KEYS:
        assert res.stability_axis_derivatives.get(key) is not None, key
    for key in BODY_DERIVATIVE_KEYS:
        assert res.body_axis_derivatives.get(key) is not None, key

    # Control authority: symmetric drives pitch, differential drives roll.
    # Cross-coupling is compared as a RATIO, not against an absolute floor —
    # in sideslip the differential elevon does produce a small real pitch moment.
    assert set(res.control_derivatives) == {"elevon_sym", "elevon_diff"}
    sym, diff = res.control_derivatives["elevon_sym"], res.control_derivatives["elevon_diff"]
    assert abs(sym["Cm"]) > 1e-4
    assert abs(diff["Cl"]) > 1e-4
    assert abs(diff["Cm"]) < 0.1 * abs(sym["Cm"])
    assert abs(sym["Cl"]) < 0.1 * abs(diff["Cl"])
    assert set(res.hinge_moments) == {"elevon_sym", "elevon_diff"}

    # per-surface breakdown, discretisation counts, derived metrics
    assert len(res.surface_forces["referred_to_sref"]) == 2
    assert res.n_strips and res.n_vortices and res.n_surfaces == 2
    assert "spiral_metric" in res.derived_metrics

    # artifacts on disk, including the parsed strip + shear/bending tables
    for key in ("strips_parsed", "strip_shear_moment_parsed", "stability",
                "body_derivs", "hinge_moments", "surface_forces",
                "native_avl_result_json"):
        assert key in res.artifact_paths, key
        assert Path(res.artifact_paths[key]).exists(), key

    payload = json.loads(Path(res.artifact_paths["native_avl_result_json"]).read_text())
    assert payload["stability_axis_derivatives"]["CLa"] is not None
    assert payload["control_derivatives"]["elevon_sym"]["Cm"] is not None


@pytest.mark.skipif(shutil.which("avl") is None, reason="avl binary not available")
def test_native_avl_elevon_spans_exactly_the_requested_band(tmp_path: Path) -> None:
    """DECISION-0005 §3: both band-edge sections carry the control."""
    from aeris.aero.solvers.native_avl import write_native_avl

    ex = _extract(n_sections=21)
    control = {"name": "elevon", "hinge_point": 0.75, "symmetric": True,
               "start_frac": 0.6, "end_frac": 0.95}
    avl_path = tmp_path / "airplane.avl"
    write_native_avl(sorted(ex, key=lambda s: s.y_m), avl_path, control=control)

    tagged = [
        s.span_fraction for s in sorted(ex, key=lambda s: s.y_m)
        if 0.6 - 1e-9 <= s.span_fraction <= 0.95 + 1e-9
    ]
    text = avl_path.read_text()
    assert text.count("elevon_sym") == len(tagged)
    assert text.count("elevon_diff") == len(tagged)
    # the outboard boundary section must be tagged, not skipped
    assert max(tagged) <= 0.95 + 1e-9
    assert len(tagged) >= 2


@pytest.mark.skipif(shutil.which("avl") is None, reason="avl binary not available")
def test_native_avl_warns_on_centreline_gap(tmp_path: Path) -> None:
    """DECISION-0005 §2: an inset root must not pass silently."""
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
    inset = extract_sections(b, np.linspace(0.02, 0.98, 9), cst_order=8,
                             chordwise_points=181)

    fc = FlightCondition(alpha_deg=2.0, velocity_mps=28.0, altitude_m=0.0)
    res = run_pygeo_native_avl_case(
        flight_condition=fc, output_dir=tmp_path, extracted_sections=inset,
        viscous=False, name="native_gap",
    )
    assert any("centreline gap" in w for w in res.warnings)
    assert res.solver_metadata["root_gap_m"] > 0.0


@pytest.mark.skipif(shutil.which("avl") is None, reason="avl binary not available")
def test_native_avl_builds_no_asb_airplane(tmp_path: Path, monkeypatch) -> None:
    """The native path must never construct an asb.Airplane."""
    import aerosandbox as asb

    def _boom(*a, **k):
        raise AssertionError("native path constructed an asb.Airplane")

    monkeypatch.setattr(asb, "Airplane", _boom)
    ex = _extract(n_sections=9)
    # 6 deg: comfortably above this washed-out wing's ~2 deg zero-lift angle, so
    # a positive CL is a meaningful check rather than an accident of the sign.
    fc = FlightCondition(alpha_deg=6.0, velocity_mps=28.0, altitude_m=0.0)
    res = run_pygeo_native_avl_case(
        flight_condition=fc, output_dir=tmp_path, extracted_sections=ex,
        viscous=True, name="native_noasb",
    )
    assert res.status == "SUCCESS"
    assert res.cl is not None and res.cl > 0.0
