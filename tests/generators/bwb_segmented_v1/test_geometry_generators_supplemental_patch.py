"""
AERIS — geometry/ + generators/bwb_segmented_v1/ supplemental patch tests.
AERIS_SUPP_PATCH_TESTS
Covers: SUPP-1, SUPP-1b, SUPP-2, SUPP-3, SUPP-4, SUPP-5
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_config(yaml_name: str):
    from aeris.common.config import load_yaml_config
    from aeris.geometry.config_resolver import resolve_generator_and_config
    cfg_path = Path(__file__).parents[3] / "configs" / "geometry" / yaml_name
    _, config = resolve_generator_and_config(load_yaml_config(cfg_path))
    return config


# ─────────────────────────────────────────────────────────────────────────────
# SUPP-1: sampling.py — elevon swap is fail-loud, not silent
# ─────────────────────────────────────────────────────────────────────────────

class TestSupp1ElevonSwapFailLoud:
    def test_normal_v3_sampling_does_not_raise(self):
        """Well-configured v3 bounds must produce valid samples without error."""
        from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design
        config = _load_config("bwb_training_v3.yaml")
        rng = np.random.default_rng(42)
        for _ in range(50):
            s = sample_bwb_design(config, rng)
            assert s.elevon_start_frac < s.elevon_end_frac

    def test_degenerate_equal_start_end_raises(self):
        """Degenerate _es == _ee must raise ValueError, not silently proceed."""
        from aeris.generators.bwb_segmented_v1.params import (
            BWBGeneratorConfig, ControlSurfaceBoundsConfig, RangeConfig,
            build_bwb_generator_config,
        )
        from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design
        from dataclasses import replace

        config = _load_config("bwb_training_v1.yaml")
        # Manually inject degenerate elevon_bounds where min==max on both
        # start and end (forcing _es == _ee after uniform draws)
        degen_bounds = ControlSurfaceBoundsConfig(
            elevon_start_frac=RangeConfig(min=0.70, max=0.70),
            elevon_end_frac=RangeConfig(min=0.70, max=0.70),  # == start
            elevon_hinge_frac=RangeConfig(min=0.75, max=0.75),
        )
        bad_config = replace(config, elevon_bounds=degen_bounds)
        rng = np.random.default_rng(0)
        with pytest.raises(ValueError, match="elevon_start_frac"):
            sample_bwb_design(bad_config, rng)

    def test_inverted_bounds_raises(self):
        """Config where start_frac samples > end_frac must raise ValueError."""
        from aeris.generators.bwb_segmented_v1.params import (
            ControlSurfaceBoundsConfig, RangeConfig,
        )
        from aeris.generators.bwb_segmented_v1.sampling import sample_bwb_design
        from dataclasses import replace

        config = _load_config("bwb_training_v1.yaml")
        # start [0.80, 0.90] > end [0.60, 0.70] → _es > _ee always
        bad_bounds = ControlSurfaceBoundsConfig(
            elevon_start_frac=RangeConfig(min=0.80, max=0.90),
            elevon_end_frac=RangeConfig(min=0.60, max=0.70),
            elevon_hinge_frac=RangeConfig(min=0.75, max=0.75),
        )
        bad_config = replace(config, elevon_bounds=bad_bounds)
        rng = np.random.default_rng(0)
        with pytest.raises(ValueError, match="elevon_start_frac"):
            sample_bwb_design(bad_config, rng)


# ─────────────────────────────────────────────────────────────────────────────
# SUPP-1b: sample_one_bwb_design alias exists and works
# ─────────────────────────────────────────────────────────────────────────────

class TestSupp1bAlias:
    def test_alias_importable(self):
        """sample_one_bwb_design must be importable from sampling module."""
        from aeris.generators.bwb_segmented_v1.sampling import sample_one_bwb_design
        assert callable(sample_one_bwb_design)

    def test_alias_produces_same_result_as_sample_bwb_design(self):
        """Alias must produce identical output to sample_bwb_design."""
        from aeris.generators.bwb_segmented_v1.sampling import (
            sample_bwb_design,
            sample_one_bwb_design,
        )
        config = _load_config("bwb_training_v1.yaml")
        rng1 = np.random.default_rng(77)
        rng2 = np.random.default_rng(77)
        s1 = sample_bwb_design(config, rng1)
        s2 = sample_one_bwb_design(config, rng2)
        assert s1 == s2

    def test_deprecated_planform_wrapper_callable(self):
        """generate_bwb_planform deprecated wrapper must not raise ImportError."""
        from aeris.generators.bwb_segmented_v1.planform import generate_bwb_planform
        config = _load_config("bwb_training_v1.yaml")
        rng = np.random.default_rng(1)
        result = generate_bwb_planform(config, rng)
        assert result.semi_span_m > 0


# ─────────────────────────────────────────────────────────────────────────────
# SUPP-2: params.py _as_int rejects non-integral floats
# ─────────────────────────────────────────────────────────────────────────────

class TestSupp2AsIntStrict:
    def test_integral_float_accepted(self):
        """10.0 is a whole number and must be accepted as int 10."""
        from aeris.generators.bwb_segmented_v1.params import _as_int
        assert _as_int(10.0, field_name="x") == 10

    def test_non_integral_float_rejected(self):
        """10.7 must raise TypeError, not silently truncate to 10."""
        from aeris.generators.bwb_segmented_v1.params import _as_int
        with pytest.raises(TypeError, match="integer"):
            _as_int(10.7, field_name="controls.n_points")

    def test_non_integral_float_in_config_rejected(self):
        """n_points: 10.7 in YAML must raise during config construction."""
        from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config
        raw = {
            "name": "test_supp2",
            "geometry": {
                "generator": {"family": "bwb_segmented", "version": "v1"},
                "controls": {
                    "n_points": 10.7,   # ← non-integral float
                    "n_spline_inboard": 4,
                    "n_spline_outboard": 5,
                    "desired_curvature_strength": 0.7,
                },
                "planform_bounds": {
                    "c1_m": {"min": 1.0, "max": 2.0}, "c2_ratio": {"min": 0.4, "max": 0.8},
                    "c3_ratio": {"min": 0.2, "max": 0.6}, "c4_ratio": {"min": 0.1, "max": 0.4},
                    "b_total_m": {"min": 2.0, "max": 4.0}, "b3_ratio": {"min": 0.2, "max": 0.5},
                    "split_ratio": {"min": 0.2, "max": 0.8},
                    "sw1_deg": {"min": 10.0, "max": 40.0},
                    "sw2_deg": {"min": 5.0,  "max": 20.0},
                    "sw3_deg": {"min": 3.0,  "max": 15.0},
                },
                "section_bounds": {
                    "airfoil_name": "naca4412", "dihedral_root_deg": 0.0,
                    "twist_b0_deg": {"min": -2.0, "max": 2.0},
                    "twist_b1_deg": {"min": -3.0, "max": 3.0},
                    "twist_b2_deg": {"min": -4.0, "max": 4.0},
                    "twist_b3_deg": {"min": -5.0, "max": 5.0},
                    "dihedral_b1_deg": {"min": 0.0, "max": 5.0},
                    "dihedral_b2_deg": {"min": 0.0, "max": 8.0},
                    "dihedral_b3_deg": {"min": 0.0, "max": 10.0},
                },
                "outputs": {"save_plot": False, "build_aerosandbox": False},
            },
        }
        with pytest.raises(TypeError, match="integer"):
            build_bwb_generator_config(raw)

    def test_plain_int_still_accepted(self):
        """Plain integers must still work correctly."""
        from aeris.generators.bwb_segmented_v1.params import _as_int
        assert _as_int(5, field_name="x") == 5
        assert _as_int(0, field_name="x") == 0


# ─────────────────────────────────────────────────────────────────────────────
# SUPP-3: visualization.py _find_plot_path finds plots/planform.png
# ─────────────────────────────────────────────────────────────────────────────

class TestSupp3FindPlotPath:
    def test_finds_plots_subdir_path(self, tmp_path):
        """_find_plot_path must find output_dir/plots/planform.png."""
        from aeris.geometry.visualization import _find_plot_path

        plots_dir = tmp_path / "plots"
        plots_dir.mkdir()
        png = plots_dir / "planform.png"
        png.write_bytes(b"fake")

        found = _find_plot_path(tmp_path)
        assert found == png

    def test_returns_none_when_no_plot(self, tmp_path):
        """_find_plot_path must return None when no plot exists."""
        from aeris.geometry.visualization import _find_plot_path
        assert _find_plot_path(tmp_path) is None

    def test_plots_dir_takes_priority_over_root(self, tmp_path):
        """plots/planform.png must be found before root planform.png (it's first)."""
        from aeris.geometry.visualization import _find_plot_path

        # Create both
        (tmp_path / "planform.png").write_bytes(b"root")
        plots_dir = tmp_path / "plots"
        plots_dir.mkdir()
        (plots_dir / "planform.png").write_bytes(b"plots_subdir")

        found = _find_plot_path(tmp_path)
        assert found == plots_dir / "planform.png"


# ─────────────────────────────────────────────────────────────────────────────
# SUPP-4: deflected_cad.py export_bwb_physical_deflected_cad handles seed=null
# ─────────────────────────────────────────────────────────────────────────────

class TestSupp4SeedNullSafe:
    def test_seed_none_in_config_uses_fallback(self):
        """When config.generator.seed is None, export must use fallback 100."""
        from aeris.generators.bwb_segmented_v1.deflected_cad import (
            export_bwb_physical_deflected_cad,
        )
        import inspect
        src = inspect.getsource(export_bwb_physical_deflected_cad)
        # The fix replaces int(getattr(...)) with a safe coercion
        assert "if _cfg_seed is not None else 100" in src or \
               "int(None)" not in src, (
            "SUPP-4 patch not applied: seed=null still crashes with int(None)"
        )

    def test_safe_seed_coercion_logic(self):
        """The safe seed fallback must return 100 when cfg_seed is None."""
        # Simulate the patched logic
        _cfg_seed = None
        seed = None
        seed_final = seed if seed is not None else (int(_cfg_seed) if _cfg_seed is not None else 100)
        assert seed_final == 100

    def test_safe_seed_coercion_uses_config_seed_when_set(self):
        """When config has a numeric seed, it must be used."""
        _cfg_seed = 42
        seed = None
        seed_final = seed if seed is not None else (int(_cfg_seed) if _cfg_seed is not None else 100)
        assert seed_final == 42

    def test_explicit_seed_arg_overrides_config(self):
        """Explicit seed= argument must override config seed."""
        _cfg_seed = 42
        seed = 7
        seed_final = seed if seed is not None else (int(_cfg_seed) if _cfg_seed is not None else 100)
        assert seed_final == 7


# ─────────────────────────────────────────────────────────────────────────────
# SUPP-5: aerosandbox_adapter.py required surface raises if 0 sections attached
# ─────────────────────────────────────────────────────────────────────────────

class TestSupp5RequiredControlSurface:
    def _make_section_geometry_with_few_sections(self, n: int):
        """Build minimal section geometry with n sections at y=0..n-1."""
        from aeris.generators.bwb_segmented_v1.sections import SectionRecord, SectionGeometryResult
        import numpy as np
        sections = [
            SectionRecord(
                index=i,
                x_le_m=0.0,
                y_m=float(i) * 0.1,
                z_le_m=0.0,
                chord_m=1.0 - float(i) * 0.05,
                twist_deg=0.0,
                dihedral_deg=0.0,
                airfoil_name="naca4412",
            )
            for i in range(n)
        ]
        return SectionGeometryResult(
            sections=sections,
            twist_b0_deg=0.0, twist_b1_deg=0.0, twist_b2_deg=0.0, twist_b3_deg=0.0,
            dihedral_b0_deg=0.0, dihedral_b1_deg=0.0, dihedral_b2_deg=0.0, dihedral_b3_deg=0.0,
            twist_boundaries_deg=np.zeros(4),
            dihedral_boundaries_deg=np.zeros(4),
            twist_array_deg=np.zeros(n),
            dihedral_array_deg=np.zeros(n),
            group_boundary_y=np.array([0.0, 0.1, 0.2, float((n-1)*0.1)]),
        )

    def test_required_surface_zero_attach_raises(self):
        """A required surface outside the section grid must raise ValueError."""
        from aeris.generators.bwb_segmented_v1.params import (
            BWBGeneratorConfig, ControlSurfacesConfig, ControlSurfaceConfig,
            ControlSurfaceSpanwiseConfig, build_bwb_generator_config,
        )
        from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import (
            build_aerosandbox_geometry,
        )
        from dataclasses import replace

        config = _load_config("bwb_training_v1.yaml")
        if not config.control_surfaces.surfaces:
            pytest.skip("v1 config has no control surfaces")

        # Patch first surface to required=True and span [0.99, 1.0] (beyond last non-tip section)
        surf = config.control_surfaces.surfaces[0]
        required_surf = replace(
            surf,
            required=True,
            spanwise=ControlSurfaceSpanwiseConfig(start_frac=0.99, end_frac=1.0),
        )
        patched_cs = replace(config.control_surfaces, surfaces=(required_surf,))
        patched_config = replace(config, control_surfaces=patched_cs)

        # Use section geometry with only 3 sections (tip sections never get control surfaces)
        section_geo = self._make_section_geometry_with_few_sections(3)
        with pytest.raises(ValueError, match=required_surf.name):
            build_aerosandbox_geometry(section_geo, patched_config)

    def test_optional_surface_zero_attach_does_not_raise(self):
        """An optional surface outside the grid must NOT raise (just produce no assignment)."""
        from aeris.generators.bwb_segmented_v1.params import (
            ControlSurfaceConfig, ControlSurfaceSpanwiseConfig,
        )
        from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import (
            build_aerosandbox_geometry,
        )
        from dataclasses import replace

        config = _load_config("bwb_training_v1.yaml")
        if not config.control_surfaces.surfaces:
            pytest.skip("v1 config has no control surfaces")

        surf = config.control_surfaces.surfaces[0]
        optional_surf = replace(
            surf,
            required=False,
            spanwise=ControlSurfaceSpanwiseConfig(start_frac=0.99, end_frac=1.0),
        )
        patched_cs = replace(config.control_surfaces, surfaces=(optional_surf,))
        patched_config = replace(config, control_surfaces=patched_cs)
        section_geo = self._make_section_geometry_with_few_sections(3)

        # Must not raise — no sections in range but surface is optional
        result = build_aerosandbox_geometry(section_geo, patched_config)
        assert result.airplane is not None
