from __future__ import annotations

import json
from types import SimpleNamespace

import aerosandbox as asb
import pytest

from aeris.aero.views import (
    _extract_native_airplane,
    build_asb_airplane_from_paths,
    geometry_view_from_case,
    geometry_view_from_run_dir,
)


def _make_airplane_with_control_surface() -> asb.Airplane:
    airfoil = asb.Airfoil("naca4412")

    wing = asb.Wing(
        name="main",
        symmetric=True,
        xsecs=[
            asb.WingXSec(
                xyz_le=[0.0, 0.0, 0.0],
                chord=1.0,
                twist=0.0,
                airfoil=airfoil,
                control_surfaces=[],
            ),
            asb.WingXSec(
                xyz_le=[0.1, 0.7, 0.0],
                chord=0.8,
                twist=0.0,
                airfoil=airfoil,
                control_surfaces=[
                    asb.ControlSurface(
                        name="elevon",
                        trailing_edge=True,
                        hinge_point=0.75,
                        deflection=0.0,
                        symmetric=True,
                    )
                ],
            ),
            asb.WingXSec(
                xyz_le=[0.2, 1.4, 0.0],
                chord=0.5,
                twist=0.0,
                airfoil=airfoil,
                control_surfaces=[],
            ),
        ],
    )

    return asb.Airplane(
        name="test_airplane",
        xyz_ref=[0.0, 0.0, 0.0],
        wings=[wing],
    )


def test_extract_native_airplane_from_attribute():
    airplane = object()
    case = SimpleNamespace(airplane=airplane)
    assert _extract_native_airplane(case) is airplane


def test_build_asb_airplane_from_paths_raises_on_missing_airfoil(tmp_path):
    case_dir = tmp_path / "case"
    csv_path = case_dir / "airfoils" / "openvsp_sections.csv"
    airfoil_dir = case_dir / "airfoils" / "xfoil"
    airfoil_dir.mkdir(parents=True)

    csv_path.write_text(
        "idx,y_span_m,le_x_m,chord_m,twist_deg_segment,dihedral_deg_segment\n"
        "0,0.0,0.0,1.0,0.0,0.0\n"
        "1,1.0,0.1,0.8,0.0,0.0\n",
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="Missing reconstructed airfoil file"):
        build_asb_airplane_from_paths(csv_path, airfoil_dir)


def test_build_asb_airplane_from_paths_raises_on_duplicate_span_station(tmp_path):
    case_dir = tmp_path / "case"
    csv_path = case_dir / "airfoils" / "openvsp_sections.csv"
    airfoil_dir = case_dir / "airfoils" / "xfoil"
    airfoil_dir.mkdir(parents=True)

    csv_path.write_text(
        "idx,y_span_m,le_x_m,chord_m,twist_deg_segment,dihedral_deg_segment\n"
        "0,0.0,0.0,1.0,0.0,0.0\n"
        "1,0.0,0.1,0.8,0.0,0.0\n",
        encoding="utf-8",
    )

    for idx, y in [(0, 0.0), (1, 0.0)]:
        (airfoil_dir / f"airfoil_{idx:03d}_y{y:.4f}m.dat").write_text(
            "dummy\n0.0 0.0\n0.5 0.1\n1.0 0.0\n",
            encoding="utf-8",
        )

    with pytest.raises(RuntimeError, match="Duplicate span stations"):
        build_asb_airplane_from_paths(csv_path, airfoil_dir)


def test_geometry_view_from_case_exposes_control_surface_flags():
    airplane = _make_airplane_with_control_surface()

    case = SimpleNamespace(
        aerosandbox_result=SimpleNamespace(
            airplane=airplane,
            metadata={
                "has_control_surfaces": True,
                "control_surface_count": 1,
                "applied_control_surfaces": [
                    {
                        "name": "elevon",
                        "family": "trailing_edge",
                        "hinge_point": 0.75,
                        "symmetric": True,
                        "side": None,
                        "start_frac": 0.60,
                        "end_frac": 0.95,
                        "applied_xsec_indices": [1],
                    }
                ],
            },
        )
    )

    view = geometry_view_from_case(
        case=case,
        generator_id="bwb_segmented_v1",
        source_policy="native",
    )

    assert view.has_control_surfaces is True
    assert "elevon" in view.control_surface_names
    assert view.metadata["has_control_surfaces"] is True
    assert "elevon" in view.metadata["control_surface_names"]


def test_geometry_view_from_run_dir_reads_control_surface_summary(tmp_path):
    run_dir = tmp_path / "run"
    case_dir = run_dir / "geometry"
    airfoil_dir = case_dir / "airfoils" / "xfoil"
    airfoil_dir.mkdir(parents=True)

    csv_path = case_dir / "airfoils" / "openvsp_sections.csv"
    csv_path.write_text(
        "idx,y_span_m,le_x_m,chord_m,twist_deg_segment,dihedral_deg_segment\n"
        "0,0.0,0.0,1.0,0.0,0.0\n"
        "1,0.7,0.1,0.8,0.0,0.0\n"
        "2,1.4,0.2,0.5,0.0,0.0\n",
        encoding="utf-8",
    )

    for idx, y in [(0, 0.0), (1, 0.7), (2, 1.4)]:
        (airfoil_dir / f"airfoil_{idx:03d}_y{y:.4f}m.dat").write_text(
            "dummy\n0.0 0.0\n0.5 0.1\n1.0 0.0\n",
            encoding="utf-8",
        )

    summary = {
        "control_surface_summary": {
            "configured": {
                "enabled": True,
                "count": 1,
                "names": ["elevon"],
                "definitions": [
                    {
                        "name": "elevon",
                        "family": "trailing_edge",
                        "hinge_point": 0.75,
                        "symmetric": True,
                        "side": None,
                        "start_frac": 0.60,
                        "end_frac": 0.95,
                        "deflection_sign": "standard",
                        "required": False,
                    }
                ],
            },
            "applied": {
                "has_control_surfaces": True,
                "control_surface_count": 1,
                "applied_control_surfaces": [
                    {
                        "name": "elevon",
                        "family": "trailing_edge",
                        "hinge_point": 0.75,
                        "symmetric": True,
                        "side": None,
                        "start_frac": 0.60,
                        "end_frac": 0.95,
                        "applied_xsec_indices": [1],
                    }
                ],
            },
        }
    }
    (case_dir / "geometry_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    view = geometry_view_from_run_dir(
        run_dir=run_dir,
        generator_id="bwb_segmented_v1",
    )

    assert view.has_control_surfaces is True
    assert "elevon" in view.control_surface_names
    assert view.metadata["control_surface_summary"]["configured"]["names"] == ["elevon"]