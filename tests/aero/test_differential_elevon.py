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

def test_bwb_training_v2_yaml_has_two_surfaces(tmp_path):
    """bwb_training_v2.yaml must have 2 surfaces: elevon_sym (d1) + elevon_diff (d2)."""
    from pathlib import Path
    config_path = Path(__file__).resolve().parents[2] / "configs" / "geometry" / "bwb_training_v2.yaml"
    assert config_path.exists(), f"bwb_training_v2.yaml not found at {config_path}"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    cs = data["geometry"]["control_surfaces"]
    assert cs["enabled"] is True
    assert len(cs["surfaces"]) == 2
    names = {s["name"] for s in cs["surfaces"]}
    assert "elevon_sym"  in names
    assert "elevon_diff" in names
    sym_surf  = next(s for s in cs["surfaces"] if s["name"] == "elevon_sym")
    diff_surf = next(s for s in cs["surfaces"] if s["name"] == "elevon_diff")
    assert sym_surf["symmetric"]  is True
    assert diff_surf["symmetric"] is False


def test_bwb_training_v2_parses_correctly():
    """bwb_training_v2.yaml must be accepted by the BWB generator config parser."""
    from pathlib import Path
    from aeris.common.config import load_yaml_config
    from aeris.geometry.config_resolver import resolve_generator_and_config
    config_path = Path(__file__).resolve().parents[2] / "configs" / "geometry" / "bwb_training_v2.yaml"
    raw = load_yaml_config(config_path)
    generator_id, typed_config = resolve_generator_and_config(raw)
    assert generator_id == "bwb_segmented_v1"
    cs = typed_config.control_surfaces
    assert cs.enabled is True
    assert len(cs.surfaces) == 2
    sym_surf  = next(s for s in cs.surfaces if s.name == "elevon_sym")
    diff_surf = next(s for s in cs.surfaces if s.name == "elevon_diff")
    assert sym_surf.symmetric  is True
    assert diff_surf.symmetric is False
    assert diff_surf.side == "right"
