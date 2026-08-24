"""
Tests for differential elevon wiring (Step 1 of AERIS control surface expansion).

Covers:
  - FlightConditionSweep.diff_input_deg_values field exists
  - AeroSweepCaseInput.diff_input_deg + sweep_type fields exist
  - expand_aero_sweep produces sym + diff cases independently (not product)
  - diff cases have control_input_deg=0.0 and sweep_type='diff'
  - sym cases have diff_input_deg=None and sweep_type='sym'
  - AVL keystroke includes d2 d2 when diff_input_deg is set
  - bwb_training_v2.yaml is valid YAML with two control surfaces
"""
from __future__ import annotations

from dataclasses import fields

import pytest
import yaml

from aeris.aero.models import AeroSweepCaseInput, FlightConditionSweep, FlightCondition
from aeris.aero.sweep import expand_aero_sweep


def _base_fc() -> FlightCondition:
    return FlightCondition(
        alpha_deg=0.0, beta_deg=0.0, mach=None,
        velocity_mps=28.0, altitude_m=0.0,
        p_rad_s=0.0, q_rad_s=0.0, r_rad_s=0.0,
    )


# ── Model field tests ─────────────────────────────────────────────────────────

def test_flight_condition_sweep_has_diff_field():
    sweep = FlightConditionSweep()
    assert hasattr(sweep, "diff_input_deg_values")
    assert sweep.diff_input_deg_values == []


def test_aero_sweep_case_input_has_diff_field():
    fc = _base_fc()
    case = AeroSweepCaseInput(flight_condition=fc)
    assert hasattr(case, "diff_input_deg")
    assert case.diff_input_deg is None
    assert hasattr(case, "sweep_type")
    assert case.sweep_type == "sym"


# ── expand_aero_sweep independence tests ─────────────────────────────────────

def test_sym_only_sweep_produces_correct_cases():
    """Symmetric sweep only — no diff values → no diff cases."""
    sweep = FlightConditionSweep(
        alpha_deg_values=[-4.0, 0.0, 4.0],
        control_input_deg_values=[-5.0, 0.0, 5.0],
    )
    cases = expand_aero_sweep(_base_fc(), sweep, max_cases=500)
    assert len(cases) == 9  # 3 alpha × 3 sym
    assert all(c.sweep_type == "sym" for c in cases)
    assert all(c.diff_input_deg is None for c in cases)


def test_diff_only_sweep_produces_correct_cases():
    """Differential sweep only — sym list empty → only diff cases."""
    sweep = FlightConditionSweep(
        alpha_deg_values=[-4.0, 0.0, 4.0],
        control_input_deg_values=[0.0],   # sym fixed at 0
        diff_input_deg_values=[-5.0, 0.0, 5.0],
    )
    cases = expand_aero_sweep(_base_fc(), sweep, max_cases=500)
    # 3 alpha × 1 sym(=0) = 3 sym cases, plus 3 alpha × 3 diff = 9 diff cases
    sym_cases  = [c for c in cases if c.sweep_type == "sym"]
    diff_cases = [c for c in cases if c.sweep_type == "diff"]
    assert len(sym_cases)  == 3   # 3 alpha × 1 sym
    assert len(diff_cases) == 9   # 3 alpha × 3 diff
    assert len(cases) == 12       # NOT 9×3=27 (no product)


def test_independent_sweep_not_product():
    """
    sym_values=[−5,0,5] + diff_values=[−5,0,5] + 2 alpha
    = 2×3 + 2×3 = 12 cases, NOT 2×3×3 = 18.
    """
    sweep = FlightConditionSweep(
        alpha_deg_values=[-4.0, 4.0],
        control_input_deg_values=[-5.0, 0.0, 5.0],
        diff_input_deg_values=[-5.0, 0.0, 5.0],
    )
    cases = expand_aero_sweep(_base_fc(), sweep, max_cases=500)
    assert len(cases) == 12
    assert sum(1 for c in cases if c.sweep_type == "sym")  == 6
    assert sum(1 for c in cases if c.sweep_type == "diff") == 6


def test_diff_cases_have_sym_locked_at_zero():
    """During diff sweep, control_input_deg (sym) must be 0.0."""
    sweep = FlightConditionSweep(
        alpha_deg_values=[0.0],
        control_input_deg_values=[0.0],
        diff_input_deg_values=[-10.0, 0.0, 10.0],
    )
    cases = expand_aero_sweep(_base_fc(), sweep, max_cases=500)
    diff_cases = [c for c in cases if c.sweep_type == "diff"]
    assert all(c.control_input_deg == 0.0 for c in diff_cases)
    diff_values = sorted(c.diff_input_deg for c in diff_cases)
    assert diff_values == [-10.0, 0.0, 10.0]


def test_sym_cases_have_no_diff():
    """During sym sweep, diff_input_deg must be None."""
    sweep = FlightConditionSweep(
        alpha_deg_values=[0.0],
        control_input_deg_values=[-5.0, 5.0],
        diff_input_deg_values=[-5.0, 5.0],
    )
    cases = expand_aero_sweep(_base_fc(), sweep, max_cases=500)
    sym_cases = [c for c in cases if c.sweep_type == "sym"]
    assert all(c.diff_input_deg is None for c in sym_cases)


# ── YAML config test ──────────────────────────────────────────────────────────

def test_bwb_yaml_declares_one_physical_elevon():
    """bwb.yaml declares ONE physical elevon; the two AVL slots are made by the writer.

    Retargeted twice. Originally this asserted that bwb_training_v2.yaml listed two
    control surfaces (elevon_sym + elevon_diff) -- that config encoded the AVL
    control SLOTS in the geometry file. Both the config (DECISION-0001) and the
    architecture (DECISION-0005) moved on: the geometry now describes the physical
    hardware, and native_avl.py emits the symmetric/differential pair from it. The
    invariant worth testing is that pairing, which is asserted in the test below.
    """
    from pathlib import Path
    config_path = Path(__file__).resolve().parents[2] / "configs" / "geometry" / "bwb.yaml"
    assert config_path.exists(), f"bwb.yaml not found at {config_path}"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    cs = data["geometry"]["control_surfaces"]
    assert cs["enabled"] is True
    assert len(cs["surfaces"]) == 1, "one physical elevon, not one per AVL slot"
    surf = cs["surfaces"][0]
    assert surf["name"] == "elevon"
    assert surf["family"] == "trailing_edge"
    assert surf["symmetric"] is True
    assert 0.0 < surf["hinge_point"] < 1.0
    span = surf["spanwise"]
    assert 0.0 <= span["start_frac"] < span["end_frac"] <= 1.0


def test_bwb_parses_correctly():
    """bwb.yaml must be accepted by the BWB generator config parser."""
    from pathlib import Path
    from aeris.common.config import load_yaml_config
    from aeris.geometry.config_resolver import resolve_generator_and_config
    config_path = Path(__file__).resolve().parents[2] / "configs" / "geometry" / "bwb.yaml"
    raw = load_yaml_config(config_path)
    generator_id, typed_config = resolve_generator_and_config(raw)
    assert generator_id == "bwb_segmented"
    cs = typed_config.control_surfaces
    assert cs is not None and cs.enabled is True
    assert len(cs.surfaces) == 1


def test_writer_turns_the_one_elevon_into_two_avl_controls(tmp_path):
    """The real invariant: one physical elevon -> two AVL controls, SgnDup +1 / -1.

    Net deflection is right = de_sym + da_diff, left = de_sym - da_diff, so the
    signs must be opposite and both must sit on the same hinge x.
    """
    import dataclasses
    from pathlib import Path
    from aeris.common.config import load_yaml_config
    from aeris.geometry.config_resolver import resolve_generator_and_config
    from aeris.geometry.registry import get_geometry_generator
    from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
        build_pygeo_sections_from_config)
    from aeris.aero.solvers.native_avl import write_native_avl

    cfg = Path(__file__).resolve().parents[2] / "configs" / "geometry" / "bwb.yaml"
    gid, gc = resolve_generator_and_config(load_yaml_config(cfg))
    sample = get_geometry_generator(gid).sample_one(gc, seed=7000)
    ex, semi, meta = build_pygeo_sections_from_config(cfg, sample=sample)

    avl = tmp_path / "t.avl"
    write_native_avl(ex, avl, control=meta["control"])
    text = avl.read_text(encoding="utf-8")

    sym = [l for l in text.splitlines() if "_sym" in l and "CONTROL" not in l]
    dif = [l for l in text.splitlines() if "_diff" in l and "CONTROL" not in l]
    assert sym and dif, "writer must emit both control slots"
    assert len(sym) == len(dif), "every controlled section carries both slots"
    assert sym[0].split()[-1] == "1", "symmetric slot must have SgnDup +1"
    assert dif[0].split()[-1] == "-1", "differential slot must have SgnDup -1"
    assert sym[0].split()[2] == dif[0].split()[2], "both slots share one hinge x"
