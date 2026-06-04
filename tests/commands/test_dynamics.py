"""
AERIS Dynamics — Test Suite
============================
Tests for models, analysis, trim, config, and cg_sweep.
All tests use synthetic data with known analytical answers.
"""
from __future__ import annotations

import math
import pytest

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

def test_mass_properties_inertia_complete():
    from aeris.dynamics.models import InertiaPlaceholders, MassProperties
    mp_full = MassProperties(
        mass_kg=12.5, x_cg_m=0.40,
        inertia=InertiaPlaceholders(ixx_kg_m2=0.15, iyy_kg_m2=0.80, izz_kg_m2=0.90),
    )
    mp_partial = MassProperties(
        mass_kg=12.5, x_cg_m=0.40,
        inertia=InertiaPlaceholders(ixx_kg_m2=0.15),
    )
    assert mp_full.inertia_complete() is True
    assert mp_partial.inertia_complete() is False


def test_dynamics_foundation_result_serialisation():
    from aeris.dynamics.models import (
        DynamicsFoundationResult, InertiaPlaceholders, MassProperties,
        StabilityMetrics, StateSpacePreparation, TrimDefinition,
        StabilityDerivativeSummary, ControlEffectiveness, DynamicModesSummary,
    )
    result = DynamicsFoundationResult(
        schema_version="0.2.0",
        source_run_dir="data/runs/example",
        source_solver_id="aerosandbox_avl",
        operating_point_snapshot={"alpha_deg": 4.0},
        mass_properties=MassProperties(
            mass_kg=12.5, x_cg_m=0.40,
            inertia=InertiaPlaceholders(iyy_kg_m2=0.80),
        ),
        trim_definition=TrimDefinition(),
        stability_metrics=StabilityMetrics(
            x_np_m=0.560, x_cg_m=0.40, mac_m=0.877,
            static_margin=0.182, static_margin_percent_mac=18.2,
            cma=-2.55,
        ),
    )
    d = result.to_dict()
    assert d["schema_version"] == "0.2.0"
    assert d["stability_metrics"]["static_margin_percent_mac"] == 18.2
    assert d["mass_properties"]["inertia"]["iyy_kg_m2"] == 0.80


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def test_config_load_yaml(tmp_path):
    from aeris.dynamics.config import load_mass_properties_config
    p = tmp_path / "mass.yaml"
    p.write_text(
        "mass_properties:\n  mass_kg: 12.5\n  x_cg_m: 0.40\n"
        "  iyy_kg_m2: 0.80\n  izz_kg_m2: 0.90\n",
        encoding="utf-8",
    )
    cfg = load_mass_properties_config(p)
    assert cfg.mass_kg == 12.5
    assert cfg.x_cg_m == 0.40
    assert cfg.iyy_kg_m2 == 0.80


def test_config_rejects_negative_mass(tmp_path):
    from aeris.dynamics.config import load_mass_properties_config
    p = tmp_path / "bad.yaml"
    p.write_text("mass_properties:\n  mass_kg: -1.0\n  x_cg_m: 0.40\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mass_kg must be positive"):
        load_mass_properties_config(p)


def test_config_rejects_missing_fields(tmp_path):
    from aeris.dynamics.config import load_mass_properties_config
    p = tmp_path / "missing.yaml"
    p.write_text("mass_properties:\n  mass_kg: 12.5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required fields"):
        load_mass_properties_config(p)


# ---------------------------------------------------------------------------
# Analysis — ISA atmosphere
# ---------------------------------------------------------------------------

def test_isa_density_sea_level():
    from aeris.dynamics.analysis import isa_density, ISA_SEA_LEVEL_RHO_KGM3
    rho = isa_density(0.0)
    assert abs(rho - ISA_SEA_LEVEL_RHO_KGM3) < 1e-6


def test_isa_density_decreases_with_altitude():
    from aeris.dynamics.analysis import isa_density
    assert isa_density(0.0) > isa_density(1500.0) > isa_density(5000.0)


def test_dynamic_pressure_known_value():
    from aeris.dynamics.analysis import dynamic_pressure, isa_density
    V = 28.0
    alt = 1500.0
    rho = isa_density(alt)
    expected = 0.5 * rho * V**2
    assert abs(dynamic_pressure(V, alt) - expected) < 1e-9


# ---------------------------------------------------------------------------
# Analysis — static margin
# ---------------------------------------------------------------------------

def test_compute_static_margin_positive():
    from aeris.dynamics.analysis import compute_static_margin
    sm, sm_pct = compute_static_margin(x_np_m=0.56, x_cg_m=0.40, mac_m=0.877)
    assert sm > 0           # stable
    assert abs(sm - (0.56 - 0.40) / 0.877) < 1e-9
    assert abs(sm_pct - sm * 100) < 1e-9


def test_compute_static_margin_negative():
    from aeris.dynamics.analysis import compute_static_margin
    sm, _ = compute_static_margin(x_np_m=0.30, x_cg_m=0.50, mac_m=0.877)
    assert sm < 0           # unstable (CG aft of NP)


def test_compute_static_margin_zero_mac_raises():
    from aeris.dynamics.analysis import compute_static_margin
    with pytest.raises(ValueError, match="MAC must be positive"):
        compute_static_margin(x_np_m=0.5, x_cg_m=0.4, mac_m=0.0)


def test_interpret_longitudinal_stable():
    from aeris.dynamics.analysis import interpret_longitudinal
    interp, consistent = interpret_longitudinal(static_margin=0.18, cma=-2.5)
    assert interp == "positive_static_margin"
    assert consistent is True


def test_interpret_longitudinal_unstable():
    from aeris.dynamics.analysis import interpret_longitudinal
    interp, consistent = interpret_longitudinal(static_margin=-0.05, cma=+1.2)
    assert interp == "negative_static_margin"
    assert consistent is True


def test_interpret_longitudinal_inconsistent():
    # SM positive but Cma positive — inconsistent
    from aeris.dynamics.analysis import interpret_longitudinal
    _, consistent = interpret_longitudinal(static_margin=0.10, cma=+0.5)
    assert consistent is False


# ---------------------------------------------------------------------------
# Analysis — stability derivative extraction
# ---------------------------------------------------------------------------

def test_extract_longitudinal_derivatives_from_dict():
    from aeris.dynamics.analysis import extract_longitudinal_derivatives
    aero = {"stability_axis_derivatives": {"CLa": 4.5, "Cma": -2.55, "Cmq": -8.2}}
    ld = extract_longitudinal_derivatives(aero)
    assert ld.cla == 4.5
    assert ld.cma == -2.55
    assert ld.cmq == -8.2
    assert ld.clad is None


def test_extract_control_effectiveness_from_d1():
    from aeris.dynamics.analysis import extract_control_effectiveness
    aero = {"stability_axis_derivatives": {"CLd1": 0.45, "Cmd1": -0.85}}
    ctrl = extract_control_effectiveness(aero)
    assert ctrl.cl_per_de_rad == 0.45
    assert ctrl.cm_per_de_rad == -0.85
    assert ctrl.pitch_authority_adequate is True


def test_control_effectiveness_inadequate_flag():
    from aeris.dynamics.analysis import extract_control_effectiveness, PITCH_AUTHORITY_MIN_PER_RAD
    aero = {"stability_axis_derivatives": {"Cmd1": 0.01}}  # tiny Cmδe
    ctrl = extract_control_effectiveness(aero)
    assert ctrl.pitch_authority_adequate is False


# ---------------------------------------------------------------------------
# Analysis — spiral metric
# ---------------------------------------------------------------------------

def test_spiral_metric_sign():
    from aeris.dynamics.analysis import build_stability_derivative_summary
    from aeris.dynamics.models import (
        LongitudinalStabilityDerivatives, LateralDirectionalStabilityDerivatives
    )
    # Values consistent with a spiral-unstable flying wing (Clr·Cnβ > Clβ·Cnr)
    lat = LateralDirectionalStabilityDerivatives(
        clb=-0.08, cnb=0.05, clr=0.10, cnr=-0.12
    )
    ld  = LongitudinalStabilityDerivatives(cma=-2.5)
    ds  = build_stability_derivative_summary(ld, lat)
    assert ds.spiral_metric is not None
    # spiral = Clβ·Cnr / (Clr·Cnβ)  = (-0.08·-0.12) / (0.10·0.05) = 0.0096/0.005 = 1.92
    expected = (-0.08 * -0.12) / (0.10 * 0.05)
    assert abs(ds.spiral_metric - expected) < 1e-10
    assert ds.spiral_stable is False  # > 1


# ---------------------------------------------------------------------------
# Analysis — short-period approximation
# ---------------------------------------------------------------------------

def test_short_period_valid():
    from aeris.dynamics.analysis import estimate_short_period
    sp = estimate_short_period(
        cma_per_rad=-2.5,
        cmq_per_rad=-8.0,
        cmad_per_rad=-1.5,
        cla_per_rad=4.5,
        mass_kg=12.5,
        iyy_kg_m2=0.80,
        velocity_mps=28.0,
        altitude_m=1500.0,
        mac_m=0.877,
        sref_m2=0.5,
    )
    assert sp.valid is True
    assert sp.omega_n_rad_s > 0
    # zeta should be positive (stable) for these derivatives
    assert sp.zeta > 0
    assert sp.time_to_half_s is not None and sp.time_to_half_s > 0


def test_short_period_unstable_cma():
    from aeris.dynamics.analysis import estimate_short_period
    sp = estimate_short_period(
        cma_per_rad=+1.0,   # pitch-unstable
        cmq_per_rad=None, cmad_per_rad=None, cla_per_rad=None,
        mass_kg=12.5, iyy_kg_m2=0.80,
        velocity_mps=28.0, altitude_m=0.0, mac_m=0.877,
    )
    assert sp.valid is False
    assert "pitch-unstable" in (sp.reason or "")


# ---------------------------------------------------------------------------
# Analysis — phugoid approximation
# ---------------------------------------------------------------------------

def test_phugoid_lanchester():
    from aeris.dynamics.analysis import estimate_phugoid, GRAVITY_MPS2
    import math
    V = 28.0
    CL, CD = 0.35, 0.02
    ph = estimate_phugoid(cl=CL, cd=CD, velocity_mps=V)
    assert ph.valid is True
    expected_omega_n = GRAVITY_MPS2 * math.sqrt(2.0) / V
    assert abs(ph.omega_n_rad_s - round(expected_omega_n, 4)) < 1e-3
    expected_zeta = CD / (CL * math.sqrt(2.0))
    assert abs(ph.zeta - round(expected_zeta, 4)) < 1e-3
    assert ph.stable is True


# ---------------------------------------------------------------------------
# Trim
# ---------------------------------------------------------------------------

def _make_aero_dict(alpha_deg=2.0, cm=-0.42, cma=-2.55, cmde=-0.85, de0=0.0):
    """Helper: build a minimal aero_result dict for trim testing."""
    return {
        "scalars": {"cm": cm},
        "solver_metadata": {
            "flight_condition": {"alpha_deg": alpha_deg, "velocity_mps": 28.0, "altitude_m": 1500.0},
            "control_input_deg": de0,
        },
        "stability_axis_derivatives": {"Cma": cma, "Cmd1": cmde},
    }


def test_trim_alpha_control_fixed():
    """Alpha-trim: Δα = -Cm/Cma should give trim alpha."""
    from aeris.dynamics.trim import estimate_longitudinal_trim
    import math
    aero = _make_aero_dict(alpha_deg=2.0, cm=-0.42, cma=-2.55)
    result = estimate_longitudinal_trim(aero, "/tmp/fake_run")
    est = result.longitudinal
    assert est.valid is True
    expected_dalpha_deg = -(-0.42 / -2.55) * (180.0 / math.pi)
    assert abs(est.delta_alpha_deg - expected_dalpha_deg) < 1e-4
    assert est.alpha_trim_deg == round(2.0 + expected_dalpha_deg, 4)


def test_trim_elevon_alpha_fixed():
    """Elevon-trim: Δδe = -Cm/Cmδe."""
    from aeris.dynamics.trim import estimate_longitudinal_trim
    import math
    aero = _make_aero_dict(alpha_deg=2.0, cm=-0.42, cma=-2.55, cmde=-0.85, de0=0.0)
    result = estimate_longitudinal_trim(aero, "/tmp/fake_run")
    est = result.longitudinal
    assert est.de_trim_deg is not None
    expected_dde_deg = -(-0.42 / -0.85) * (180.0 / math.pi)
    assert abs(est.delta_de_deg - expected_dde_deg) < 1e-4


def test_trim_in_bounds_flag():
    """Trim alpha within [-5°, 15°] → in_bounds=True."""
    from aeris.dynamics.trim import estimate_longitudinal_trim
    # Small Cm → trim alpha close to current alpha
    aero = _make_aero_dict(alpha_deg=4.0, cm=-0.05, cma=-2.55)
    result = estimate_longitudinal_trim(aero, "/tmp")
    assert result.longitudinal.alpha_trim_in_bounds is True


def test_trim_out_of_bounds_flag():
    """Large Cm → trim alpha far out of range → in_bounds=False."""
    from aeris.dynamics.trim import estimate_longitudinal_trim
    aero = _make_aero_dict(alpha_deg=2.0, cm=-5.0, cma=-2.55)
    result = estimate_longitudinal_trim(aero, "/tmp")
    assert result.longitudinal.alpha_trim_in_bounds is False


def test_trim_missing_alpha_invalid():
    from aeris.dynamics.trim import estimate_longitudinal_trim
    aero = {"scalars": {"cm": -0.42}, "stability_axis_derivatives": {"Cma": -2.55}}
    result = estimate_longitudinal_trim(aero, "/tmp")
    assert result.longitudinal.valid is False
    assert "alpha" in result.longitudinal.reason.lower()


def test_trim_zero_cma_invalid():
    from aeris.dynamics.trim import estimate_longitudinal_trim
    aero = _make_aero_dict(alpha_deg=2.0, cm=-0.42, cma=0.0)
    result = estimate_longitudinal_trim(aero, "/tmp")
    assert result.longitudinal.valid is False


# ---------------------------------------------------------------------------
# State-space readiness
# ---------------------------------------------------------------------------

def test_readiness_trim_solver_ready():
    """With Cma + Xnp + MAC → ready_for_trim_solver = True."""
    from aeris.dynamics.analysis import build_state_space_preparation
    from aeris.dynamics.models import InertiaPlaceholders, MassProperties
    mp = MassProperties(mass_kg=12.5, x_cg_m=0.40)
    prep = build_state_space_preparation(
        mass_properties=mp, x_np_m=0.56, mac_m=0.877,
        cma=-2.55, cmde=None, spiral_metric=None,
        cl=0.35, velocity_mps=28.0,
    )
    assert prep.ready_for_trim_solver is True
    assert prep.ready_for_eigenanalysis is False  # no inertia


def test_readiness_eigenanalysis_ready():
    """With full inertia → ready_for_eigenanalysis = True."""
    from aeris.dynamics.analysis import build_state_space_preparation
    from aeris.dynamics.models import InertiaPlaceholders, MassProperties
    mp = MassProperties(
        mass_kg=12.5, x_cg_m=0.40,
        inertia=InertiaPlaceholders(ixx_kg_m2=0.15, iyy_kg_m2=0.80, izz_kg_m2=0.90),
    )
    prep = build_state_space_preparation(
        mass_properties=mp, x_np_m=0.56, mac_m=0.877,
        cma=-2.55, cmde=-0.85, spiral_metric=1.37,
        cl=0.35, velocity_mps=28.0,
    )
    assert prep.ready_for_eigenanalysis is True
    assert prep.ready_for_trim_solver is True
    assert prep.control_derivatives_available is True
    assert len(prep.missing_items) == 0


def test_readiness_short_period_ready():
    from aeris.dynamics.analysis import build_state_space_preparation
    from aeris.dynamics.models import InertiaPlaceholders, MassProperties
    mp = MassProperties(
        mass_kg=12.5, x_cg_m=0.40,
        inertia=InertiaPlaceholders(iyy_kg_m2=0.80),
    )
    prep = build_state_space_preparation(
        mass_properties=mp, x_np_m=0.56, mac_m=0.877,
        cma=-2.55, cmde=None, spiral_metric=None,
        cl=0.35, velocity_mps=28.0,
    )
    assert prep.ready_for_short_period is True
    assert prep.ready_for_phugoid is True
    assert prep.ready_for_eigenanalysis is False


# ---------------------------------------------------------------------------
# I/O round-trip
# ---------------------------------------------------------------------------

def test_io_roundtrip_foundation(tmp_path):
    from aeris.dynamics.models import (
        DynamicsFoundationResult, MassProperties, StabilityMetrics,
        TrimDefinition, InertiaPlaceholders,
    )
    from aeris.dynamics.io import write_dynamics_foundation_result, read_dynamics_foundation_result
    result = DynamicsFoundationResult(
        schema_version="0.2.0",
        source_run_dir="data/runs/test",
        source_solver_id="aerosandbox_avl",
        operating_point_snapshot={"alpha_deg": 4.0},
        mass_properties=MassProperties(mass_kg=12.5, x_cg_m=0.40),
        trim_definition=TrimDefinition(),
        stability_metrics=StabilityMetrics(
            x_np_m=0.56, x_cg_m=0.40, mac_m=0.877,
            static_margin=0.182, static_margin_percent_mac=18.2,
        ),
    )
    path = write_dynamics_foundation_result(result, tmp_path)
    assert path.exists()
    loaded = read_dynamics_foundation_result(path)
    assert loaded["schema_version"] == "0.2.0"
    assert loaded["stability_metrics"]["static_margin_percent_mac"] == 18.2


def test_io_find_helpers(tmp_path):
    from aeris.dynamics.io import find_dynamics_foundation, find_cg_sweep, find_trim_result
    dyn_dir = tmp_path / "dynamics"
    dyn_dir.mkdir()
    (dyn_dir / "dynamics_foundation.json").write_text("{}", encoding="utf-8")
    (dyn_dir / "cg_sweep.json").write_text("{}", encoding="utf-8")
    (dyn_dir / "trim_result.json").write_text("{}", encoding="utf-8")
    assert find_dynamics_foundation(tmp_path) is not None
    assert find_cg_sweep(tmp_path) is not None
    assert find_trim_result(tmp_path) is not None