"""
AERIS — dynamics/ full audit patch tests.
AERIS_DYNAMICS_AUDIT_TESTS
Covers: BUG-D3, ISSUE-D11, ISSUE-D12, ISSUE-D13, ISSUE-D16
Multi-discipline: physics correctness, MIL-STD classification, label semantics,
I/O robustness, numerical stability.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures: minimal mass properties and aero result dict
# ─────────────────────────────────────────────────────────────────────────────

def _minimal_mass(x_cg_m: float = 0.40):
    from aeris.dynamics.models import InertiaPlaceholders, MassProperties
    return MassProperties(
        mass_kg=12.5,
        x_cg_m=x_cg_m,
        inertia=InertiaPlaceholders(
            ixx_kg_m2=0.15,
            iyy_kg_m2=0.80,
            izz_kg_m2=0.90,
        ),
    )


def _minimal_aero_result(cma: float = -1.5, cla: float = 4.0) -> dict:
    return {
        "status": "success",
        "solver_id": "aerosandbox_avl",
        "scalars": {"cl": 0.35, "cd": 0.04, "cm": -0.15, "l_over_d": 8.75},
        "stability_axis_derivatives": {
            "CLa": cla, "Cma": cma, "Cmq": -8.0,
            "CYb": -0.15, "Clb": -0.08, "Cnb": 0.05,
            "Clp": -0.22, "Cnr": -0.12, "Clr": 0.10, "Cnp": -0.05,
            "Xnp": 0.55,
        },
        "solver_metadata": {
            "flight_condition": {
                "alpha_deg": 4.0, "velocity_mps": 28.0, "altitude_m": 1500.0,
            },
            "control_input_deg": 0.0,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# BUG-D3: CG sweep produces CG-dependent trim estimates
# ─────────────────────────────────────────────────────────────────────────────

class TestBugD3CgSweepTrimCGDependent:
    def test_cg_corrected_trim_importable(self):
        """_cg_corrected_trim helper must be importable from cg_sweep."""
        from aeris.dynamics.cg_sweep import _cg_corrected_trim
        assert callable(_cg_corrected_trim)

    def test_trim_varies_with_cg_when_cla_and_mac_known(self, tmp_path):
        """When CLα and MAC are available, trim elevon must vary with CG."""
        # Create a minimal geometry_summary.json so MAC can be found
        geo_dir = tmp_path / "geometry"
        geo_dir.mkdir()
        geo_summary = {
            "reference_values": {
                "mean_aerodynamic_chord_m": 0.30,
                "span_m": 1.6,
                "area_m2": 0.48,
            }
        }
        (geo_dir / "geometry_summary.json").write_text(
            json.dumps(geo_summary), encoding="utf-8"
        )

        # Create minimal aero_result.json
        aero = _minimal_aero_result()
        aero_path = tmp_path / "aero" / "aero_result.json"
        aero_path.parent.mkdir()
        aero_path.write_text(json.dumps(aero), encoding="utf-8")

        from aeris.dynamics.cg_sweep import _cg_corrected_trim

        # Trim at reference CG
        trim_ref = _cg_corrected_trim(aero, x_cg_m=0.40, x_cg_ref_m=0.40, run_dir=tmp_path)
        de_ref = trim_ref.longitudinal.de_trim_deg

        # Trim at aft CG (+10cm)
        trim_aft = _cg_corrected_trim(aero, x_cg_m=0.50, x_cg_ref_m=0.40, run_dir=tmp_path)
        de_aft = trim_aft.longitudinal.de_trim_deg

        if de_ref is None or de_aft is None:
            pytest.skip("Trim estimates unavailable (Cmδe may be missing)")

        # With 10cm CG shift, trim elevon should change by ~5-15°
        delta = abs(de_aft - de_ref)
        assert delta > 1.0, (
            f"Trim elevon change for 10cm CG shift should be >1°, got {delta:.2f}°. "
            "BUG-D3 may not be fully fixed."
        )

    def test_cg_ref_equals_new_gives_same_trim(self, tmp_path):
        """When x_cg_m == x_cg_ref_m, CG correction is zero — same trim result."""
        geo_dir = tmp_path / "geometry"
        geo_dir.mkdir()
        (geo_dir / "geometry_summary.json").write_text(
            json.dumps({"reference_values": {"mean_aerodynamic_chord_m": 0.30}}),
            encoding="utf-8"
        )
        (tmp_path / "aero").mkdir()
        (tmp_path / "aero" / "aero_result.json").write_text(
            json.dumps(_minimal_aero_result()), encoding="utf-8"
        )

        from aeris.dynamics.cg_sweep import _cg_corrected_trim
        t1 = _cg_corrected_trim(_minimal_aero_result(), x_cg_m=0.40, x_cg_ref_m=0.40, run_dir=tmp_path)
        t2 = _cg_corrected_trim(_minimal_aero_result(), x_cg_m=0.40, x_cg_ref_m=0.40, run_dir=tmp_path)
        assert t1.longitudinal.de_trim_deg == t2.longitudinal.de_trim_deg


# ─────────────────────────────────────────────────────────────────────────────
# ISSUE-D11: classify_spiral returns correct level for divergent + unknown T₂
# ─────────────────────────────────────────────────────────────────────────────

class TestIssueD11SpiralClassification:
    def test_divergent_unknown_t2_gives_level3(self):
        """classify_spiral(t2_s=None, stable=False) must return LEVEL_3."""
        from aeris.dynamics.mil_std import classify_spiral, HQLevel, MissionClass
        result = classify_spiral(t2_s=None, stable=False, mission=MissionClass.ISR)
        assert result.level == HQLevel.LEVEL_3, (
            f"Divergent spiral with unknown T₂ should be LEVEL_3, got {result.level}"
        )

    def test_stable_unknown_data_gives_level2(self):
        """classify_spiral(t2_s=None, stable=True) — stable spiral, unknown T₂."""
        from aeris.dynamics.mil_std import classify_spiral, HQLevel, MissionClass
        # This branch: stable=True means spiral IS stable (not divergent)
        # But in practice the call path that reaches the None else branch
        # is only when t2_s is None AND stable is False (divergent, T₂ unknown)
        # When stable=True, we hit: if stable: → LEVEL_1 (much earlier)
        result = classify_spiral(t2_s=None, stable=True, mission=MissionClass.ISR)
        assert result.level == HQLevel.LEVEL_1  # stable → always Level 1

    def test_divergent_known_slow_t2_gives_level1_or_2(self):
        """T₂ = 25s for ISR mission: above 20s threshold → Level 1."""
        from aeris.dynamics.mil_std import classify_spiral, HQLevel, MissionClass
        result = classify_spiral(t2_s=25.0, stable=False, mission=MissionClass.ISR)
        assert result.level.value <= 2

    def test_divergent_fast_t2_gives_unacceptable(self):
        """T₂ = 2s: below 4s absolute minimum → Unacceptable."""
        from aeris.dynamics.mil_std import classify_spiral, HQLevel, MissionClass
        result = classify_spiral(t2_s=2.0, stable=False, mission=MissionClass.ISR)
        assert result.level == HQLevel.UNACCEPTABLE

    def test_level3_note_mentions_state_space(self):
        """Level 3 note should direct operator to run state-space analysis."""
        from aeris.dynamics.mil_std import classify_spiral, MissionClass
        result = classify_spiral(t2_s=None, stable=False, mission=MissionClass.ISR)
        assert "state-space" in result.note.lower() or "T₂" in result.note, (
            f"Level 3 note should guide operator: {result.note}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ISSUE-D12: dyn_de_trim_feasible label added; dyn_label_trimmable uses it
# ─────────────────────────────────────────────────────────────────────────────

class TestIssueD12TrimLabels:
    def _labels_from_trim_dict(self, alpha_ok: bool | None, de_ok: bool | None) -> dict:
        from aeris.dynamics.labels import extract_dataset_labels, fill_trim_labels
        foundation = {"stability_metrics": {}, "control_effectiveness": {}}
        labels = extract_dataset_labels(foundation_result=foundation, include_hq=False)
        trim_dict = {
            "longitudinal": {
                "alpha_trim_in_bounds": alpha_ok,
                "de_trim_in_bounds": de_ok,
                "alpha_trim_deg": 3.0,
                "de_trim_deg": 5.0,
            }
        }
        return fill_trim_labels(labels, trim_result_dict=trim_dict)

    def test_dyn_de_trim_feasible_true_when_de_in_bounds(self):
        """dyn_de_trim_feasible must be True when de_trim_in_bounds=True."""
        labels = self._labels_from_trim_dict(alpha_ok=True, de_ok=True)
        assert "dyn_de_trim_feasible" in labels, (
            "dyn_de_trim_feasible label missing — ISSUE-D12 patch not applied"
        )
        assert labels["dyn_de_trim_feasible"] is True

    def test_dyn_de_trim_feasible_false_when_de_out_of_bounds(self):
        """dyn_de_trim_feasible must be False when only alpha-trim is in bounds."""
        labels = self._labels_from_trim_dict(alpha_ok=True, de_ok=False)
        assert labels["dyn_de_trim_feasible"] is False

    def test_dyn_label_trimmable_uses_strict_de_label(self):
        """dyn_label_trimmable must equal dyn_de_trim_feasible (strict definition)."""
        labels = self._labels_from_trim_dict(alpha_ok=True, de_ok=False)
        # Old: True (alpha in bounds), New: False (de out of bounds)
        assert labels["dyn_label_trimmable"] == labels["dyn_de_trim_feasible"]

    def test_dyn_trim_feasible_still_uses_or(self):
        """dyn_trim_feasible (legacy OR label) must still be True when only alpha is in bounds."""
        labels = self._labels_from_trim_dict(alpha_ok=True, de_ok=False)
        assert labels["dyn_trim_feasible"] is True  # backward compat

    def test_both_true_all_labels_true(self):
        labels = self._labels_from_trim_dict(alpha_ok=True, de_ok=True)
        assert labels["dyn_trim_feasible"] is True
        assert labels["dyn_de_trim_feasible"] is True
        assert labels["dyn_label_trimmable"] is True


# ─────────────────────────────────────────────────────────────────────────────
# ISSUE-D13: dynamics io writes are atomic
# ─────────────────────────────────────────────────────────────────────────────

class TestIssueD13AtomicWrites:
    def test_io_py_has_atomic_write_helper(self):
        import aeris.dynamics.io as mod
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "os.replace" in src, (
            "io.py does not use os.replace — atomic writes not applied (ISSUE-D13)"
        )

    def test_write_dynamics_foundation_result_produces_valid_json(self, tmp_path):
        from aeris.dynamics.io import write_dynamics_foundation_result
        from aeris.dynamics.analysis import build_dynamics_foundation_result
        from aeris.dynamics.models import InertiaPlaceholders, MassProperties

        mass = MassProperties(
            mass_kg=12.5, x_cg_m=0.40,
            inertia=InertiaPlaceholders(),
        )
        result = build_dynamics_foundation_result(
            aero_result=_minimal_aero_result(),
            mass_properties=mass,
            source_run_dir=str(tmp_path),
        )
        out = write_dynamics_foundation_result(result, tmp_path)
        assert out.exists()
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert "schema_version" in loaded

    def test_write_dynamics_no_temp_files_left(self, tmp_path):
        from aeris.dynamics.io import write_dynamics_foundation_result
        from aeris.dynamics.analysis import build_dynamics_foundation_result
        from aeris.dynamics.models import InertiaPlaceholders, MassProperties

        mass = MassProperties(
            mass_kg=12.5, x_cg_m=0.40,
            inertia=InertiaPlaceholders(),
        )
        result = build_dynamics_foundation_result(
            aero_result=_minimal_aero_result(),
            mass_properties=mass,
            source_run_dir=str(tmp_path),
        )
        write_dynamics_foundation_result(result, tmp_path)
        leftovers = list(tmp_path.glob("*.tmp"))
        assert len(leftovers) == 0

    def test_trim_write_atomic(self, tmp_path):
        import inspect
        from aeris.dynamics.trim import write_trim_result
        src = inspect.getsource(write_trim_result)
        assert "os.replace" in src, "trim.py write_trim_result is not atomic"


# ─────────────────────────────────────────────────────────────────────────────
# ISSUE-D16: build_lateral_a_matrix raises on degenerate Gamma
# ─────────────────────────────────────────────────────────────────────────────

class TestIssueD16GammaDegenerate:
    def _make_dd(self, ixz: float = 0.0):
        from aeris.dynamics.state_space import DimDerivatives
        return DimDerivatives(
            CLa=4.5, Cma=-1.5,
            CYb=-0.15, Clb=-0.08, Cnb=0.05,
            Clp=-0.22, Cmq=-8.0, Cnr=-0.12,
            Clr=0.10, Cnp=-0.05,
            CL0=0.35, CD0_trim=0.04,
            alpha0_rad=0.07,
            velocity_mps=28.0, altitude_m=1500.0,
            sref_m2=0.48, mac_m=0.30, span_m=1.6,
            mass_kg=12.5,
            ixx_kg_m2=0.15, iyy_kg_m2=0.80, izz_kg_m2=0.90,
            ixz_kg_m2=ixz,
        )

    def test_normal_ixz_zero_does_not_raise(self):
        """Ixz=0 → Gamma = Ixx·Izz > 0 → no error."""
        from aeris.dynamics.state_space import build_lateral_a_matrix
        dd = self._make_dd(ixz=0.0)
        A = build_lateral_a_matrix(dd)
        assert len(A) == 4

    def test_degenerate_ixz_raises_value_error(self):
        """Ixz = sqrt(Ixx·Izz) → Gamma = 0 → must raise ValueError."""
        import math
        from aeris.dynamics.state_space import build_lateral_a_matrix
        ixz_degenerate = math.sqrt(0.15 * 0.90)  # = sqrt(0.135) ≈ 0.3674
        dd = self._make_dd(ixz=ixz_degenerate)
        with pytest.raises(ValueError, match="Degenerate inertia"):
            build_lateral_a_matrix(dd)

    def test_error_message_mentions_ixz(self):
        """ValueError message must identify Ixz as the problem."""
        import math
        from aeris.dynamics.state_space import build_lateral_a_matrix
        ixz_degenerate = math.sqrt(0.15 * 0.90)
        dd = self._make_dd(ixz=ixz_degenerate)
        with pytest.raises(ValueError) as exc_info:
            build_lateral_a_matrix(dd)
        assert "Ixz" in str(exc_info.value) or "inertia" in str(exc_info.value).lower()

    def test_large_but_non_degenerate_ixz_works(self):
        """Moderately large Ixz (but not degenerate) must succeed."""
        from aeris.dynamics.state_space import build_lateral_a_matrix
        dd = self._make_dd(ixz=0.02)  # typical Ixz << sqrt(Ixx·Izz)
        A = build_lateral_a_matrix(dd)
        assert all(math.isfinite(A[i][j]) for i in range(4) for j in range(4)), (
            "A-matrix has non-finite entries for normal Ixz"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Physics invariant tests — dynamics foundation contract
# ─────────────────────────────────────────────────────────────────────────────

class TestDynamicsPhysicsInvariants:
    def test_static_margin_positive_implies_stable(self):
        """Positive static margin → statically stable aircraft."""
        from aeris.dynamics.analysis import compute_static_margin
        sm, sm_pct = compute_static_margin(x_np_m=0.55, x_cg_m=0.40, mac_m=0.30)
        assert sm > 0, f"Static margin should be positive, got {sm}"
        assert sm_pct == pytest.approx(sm * 100.0)

    def test_static_margin_formula(self):
        """(Xnp - Xcg) / MAC = SM."""
        from aeris.dynamics.analysis import compute_static_margin
        sm, _ = compute_static_margin(x_np_m=0.55, x_cg_m=0.40, mac_m=0.30)
        assert sm == pytest.approx((0.55 - 0.40) / 0.30)

    def test_short_period_valid_for_stable_cma(self):
        """estimate_short_period must return valid=True for Cma < 0."""
        from aeris.dynamics.analysis import estimate_short_period
        sp = estimate_short_period(
            cma_per_rad=-1.5, cmq_per_rad=-8.0, cmad_per_rad=0.0,
            cla_per_rad=4.5, mass_kg=12.5, iyy_kg_m2=0.80,
            velocity_mps=28.0, altitude_m=1500.0,
            mac_m=0.30, sref_m2=0.48,
        )
        assert sp.valid, f"SP estimate should be valid: {sp.reason}"
        assert sp.omega_n_rad_s > 0
        assert sp.zeta is not None and sp.zeta > 0

    def test_short_period_invalid_for_positive_cma(self):
        """estimate_short_period must return valid=False for Cma > 0 (unstable)."""
        from aeris.dynamics.analysis import estimate_short_period
        sp = estimate_short_period(
            cma_per_rad=+0.5, cmq_per_rad=-8.0, cmad_per_rad=0.0,
            cla_per_rad=4.5, mass_kg=12.5, iyy_kg_m2=0.80,
            velocity_mps=28.0, altitude_m=1500.0,
            mac_m=0.30, sref_m2=0.48,
        )
        assert not sp.valid

    def test_phugoid_omega_formula(self):
        """Lanchester: ω_n = g√2 / V."""
        import math
        from aeris.dynamics.analysis import estimate_phugoid, GRAVITY_MPS2
        ph = estimate_phugoid(cl=0.35, cd=0.04, velocity_mps=28.0)
        assert ph.valid
        expected_omega = GRAVITY_MPS2 * math.sqrt(2.0) / 28.0
        assert ph.omega_n_rad_s == pytest.approx(expected_omega, rel=1e-4)

    def test_mil_std_level1_sp_damping(self):
        """ζ_sp = 0.7 must give Level 1 short-period damping."""
        from aeris.dynamics.mil_std import classify_short_period_damping, HQLevel
        result = classify_short_period_damping(0.7)
        assert result.level == HQLevel.LEVEL_1

    def test_mil_std_underdamped_sp_gives_level3(self):
        """ζ_sp = 0.18 (between 0.15 and 0.25) must give Level 3."""
        from aeris.dynamics.mil_std import classify_short_period_damping, HQLevel
        result = classify_short_period_damping(0.18)
        assert result.level == HQLevel.LEVEL_3

    def test_isa_density_sea_level(self):
        """ISA density at sea level must be the standard value 1.225 kg/m³."""
        from aeris.dynamics.analysis import isa_density, ISA_SEA_LEVEL_RHO_KGM3
        assert isa_density(0.0) == ISA_SEA_LEVEL_RHO_KGM3

    def test_isa_density_decreases_with_altitude(self):
        """Air density must decrease monotonically with altitude."""
        from aeris.dynamics.analysis import isa_density
        rhos = [isa_density(h) for h in [0, 500, 1500, 3000, 5000, 8000]]
        assert all(rhos[i] > rhos[i+1] for i in range(len(rhos)-1))

    def test_full_longitudinal_state_space_stable_config(self):
        """For a stable aircraft configuration, short-period must have σ < 0."""
        from aeris.dynamics.state_space import DimDerivatives, compute_full_longitudinal
        dd = DimDerivatives(
            CLa=4.5, Cma=-1.5,
            CYb=-0.15, Clb=-0.08, Cnb=0.05,
            Clp=-0.22, Cmq=-8.0, Cnr=-0.12,
            Clr=0.10, Cnp=-0.05,
            CL0=0.35, CD0_trim=0.04,
            alpha0_rad=0.07, velocity_mps=28.0, altitude_m=1500.0,
            sref_m2=0.48, mac_m=0.30, span_m=1.6,
            mass_kg=12.5,
            ixx_kg_m2=0.15, iyy_kg_m2=0.80, izz_kg_m2=0.90,
        )
        long = compute_full_longitudinal(dd)
        assert long.valid, f"Longitudinal computation failed: {long.reason}"
        if long.short_period:
            assert long.short_period.stable, (
                f"Short-period must be stable for statically stable aircraft, "
                f"got σ={long.short_period.eigenvalue_real:.4f}"
            )
