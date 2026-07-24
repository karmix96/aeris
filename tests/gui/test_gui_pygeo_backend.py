from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

from aeris.geometry import visualization
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.gui.geometry_support import (
    DUAL_BACKEND,
    PYGEO_ONLY,
    aerosandbox_override_for_policy,
    backend_policy_options,
    load_geometry_run_evidence,
    read_geometry_backend_state,
)


def test_gui_reads_production_pygeo_backend_config() -> None:
    state = read_geometry_backend_state("configs/geometry/paper1_bwb_pygeo.yaml")

    assert state.pygeo_enabled is True
    assert state.aerosandbox_enabled is False
    assert state.physical_cad_enabled is True
    assert state.station_airfoils == {
        "b0": "naca23012",
        "b1": "naca4412",
        "b2": "naca2412",
        "b3": "naca0012",
    }
    assert PYGEO_ONLY in backend_policy_options(state)
    assert DUAL_BACKEND in backend_policy_options(state)
    assert aerosandbox_override_for_policy(PYGEO_ONLY) is False
    assert aerosandbox_override_for_policy(DUAL_BACKEND) is True


def test_gui_loads_canonical_pygeo_run_evidence(tmp_path: Path) -> None:
    geometry = tmp_path / "artifacts" / "geometry"
    pygeo = geometry / "pygeo"
    plots = geometry / "plots"
    pygeo.mkdir(parents=True)
    plots.mkdir(parents=True)
    (pygeo / "geometry_3d.png").write_bytes(b"png")
    (pygeo / "pygeo_surface.npz").write_bytes(b"npz")
    (plots / "pygeo_vs_aerosandbox.png").write_bytes(b"png")
    summary = {
        "realization_backends": {
            "aerosandbox": {"enabled": True},
            "pygeo": {"enabled": True},
        },
        "metrics": {"aspect_ratio_pygeo": 4.5},
        "pygeo": {
            "quality_status": "accepted",
            "artifacts": {"pygeo_surface_npz": str(pygeo / "pygeo_surface.npz")},
        },
        "backend_comparison": {
            "geometry_translation_used": False,
            "metrics": {"span_m": {"relative_delta_percent": 0.01}},
        },
    }
    (geometry / "geometry_summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps({"status": "success"}), encoding="utf-8"
    )

    evidence = load_geometry_run_evidence(tmp_path)

    assert evidence.pygeo["quality_status"] == "accepted"
    assert evidence.comparison["geometry_translation_used"] is False
    assert evidence.pygeo_surface_npz == (pygeo / "pygeo_surface.npz").resolve()
    assert {path.name for path in evidence.preview_images} == {
        "geometry_3d.png",
        "pygeo_vs_aerosandbox.png",
    }


def test_pygeo_only_visualize_writes_native_interactive_view(
    monkeypatch,
    tmp_path: Path,
) -> None:
    upper = np.zeros((4, 5, 3), dtype=float)
    lower = np.zeros_like(upper)
    upper[:, :, 0] = np.linspace(0.0, 1.0, 4)[:, None]
    lower[:, :, 0] = upper[:, :, 0]
    upper[:, :, 1] = np.linspace(0.0, 2.0, 5)[None, :]
    lower[:, :, 1] = upper[:, :, 1]
    upper[:, :, 2] = 0.05
    lower[:, :, 2] = -0.05
    pygeo_result = SimpleNamespace(
        geometry_id="test_pygeo",
        upper_surface=upper,
        lower_surface=lower,
        artifacts={},
    )

    class FakeGenerator:
        def sample_one(self, config, seed=None):
            return {"seed": seed}

        def run_full_case(self, **kwargs):
            return SimpleNamespace(
                pygeo_result=pygeo_result,
                aerosandbox_result=None,
            )

    config = SimpleNamespace(generator=SimpleNamespace(seed=7))
    monkeypatch.setattr(
        visualization, "load_yaml_config", lambda path: {"name": "test"}
    )
    monkeypatch.setattr(
        visualization,
        "resolve_generator_and_config",
        lambda raw: ("fake", config),
    )
    monkeypatch.setattr(
        visualization, "get_geometry_generator", lambda name: FakeGenerator()
    )

    result = visualization.visualize_geometry_from_config(
        tmp_path / "config.yaml",
        output_dir=tmp_path / "view",
        build_aerosandbox=False,
        draw_3d=True,
    )

    assert result.has_aerosandbox_airplane is False
    assert result.has_pygeo_geometry is True
    assert result.visualization_backend == "pygeo"
    assert result.interactive_3d_path is not None
    assert result.interactive_3d_path.is_file()
    assert "Aeris native pyGeo loft" in result.interactive_3d_path.read_text(
        encoding="utf-8"
    )


def test_aeris_gui_source_exposes_pygeo_backend_workflow() -> None:
    app_text = Path("src/aeris/gui/app.py").read_text(encoding="utf-8")
    support_text = Path("src/aeris/gui/geometry_support.py").read_text(encoding="utf-8")
    text = app_text + support_text

    for marker in (
        "Geometry realization",
        "Both backends + comparison",
        "Native pyGeo realization from this Aeris run",
        "pyGeo realization evidence",
        "Geometry-object translation used: false",
        "pyGeo CAD from standard Aeris geometry runs",
        "--no-build-aerosandbox",
    ):
        assert marker in text


def test_interactive_builder_emits_valid_aeris_pygeo_yaml() -> None:
    streamlit_testing = pytest.importorskip("streamlit.testing.v1")
    from aeris.gui import app as gui_app

    app = streamlit_testing.AppTest.from_file(gui_app.__file__, default_timeout=90)
    app.session_state["sb_root"] = str(Path.cwd())
    app.session_state["sb_exe"] = "aeris"
    app.session_state["sb_dry"] = True
    app.session_state["active_page"] = "dataset"
    app.session_state["ds_mode2"] = "Build config interactively"
    app.run(timeout=90)

    assert not app.exception
    generated = yaml.safe_load(app.code[0].value)
    generator_id, config = resolve_generator_and_config(generated)
    assert generator_id == "bwb_segmented_v1"
    assert config.pygeo.enabled is True
    assert config.outputs.build_aerosandbox is True
    assert config.pygeo.physical_cad.enabled is False
    assert config.section_bounds.dihedral_b1_deg.min == 0.0
    assert config.section_bounds.dihedral_b1_deg.max == 0.0
    assert config.section_bounds.station_airfoils.to_dict() == {
        "b0": "naca23012",
        "b1": "naca4412",
        "b2": "naca2412",
        "b3": "naca0012",
    }
