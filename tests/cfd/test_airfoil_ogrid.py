"""2-D airfoil geometry, O-grid loop generation, and case integration."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from aeris.cfd.case.loader import load_case_spec
from aeris.cfd.case.runner import run_case
from aeris.cfd.meshing.airfoil_geometry import (
    load_airfoil_dat,
    naca4_coordinates,
    resample_selig_loop,
)
from aeris.cfd.meshing.airfoil_ogrid import AirfoilOGridV1, write_plot3d_curve


def test_naca0012_shape_properties():
    loop = naca4_coordinates("0012", n_per_surface=200)
    x, y = loop[:, 0], loop[:, 1]
    # closed sharp TE (TMR -0.1036 form)
    assert np.allclose(loop[0], loop[-1], atol=1e-12)
    # symmetric section
    upper = loop[: len(loop) // 2 + 1]
    lower = loop[len(loop) // 2 :]
    assert np.max(np.abs(upper[:, 1][::-1] + lower[:, 1])) < 1e-12
    # max thickness ~12% chord near x ~ 0.30
    thickness = 2.0 * np.max(y)
    assert thickness == pytest.approx(0.12, abs=0.002)
    assert x[np.argmax(y)] == pytest.approx(0.30, abs=0.05)


def test_naca_cambered_has_camber():
    loop = naca4_coordinates("2412", n_per_surface=100)
    assert np.max(loop[:, 1]) > -np.min(loop[:, 1])  # asymmetric


def test_bad_naca_code_rejected():
    with pytest.raises(ValueError, match="4-digit"):
        naca4_coordinates("00123")


def test_dat_roundtrip(tmp_path: Path):
    loop = naca4_coordinates("0012", n_per_surface=80)
    dat = tmp_path / "n0012.dat"
    dat.write_text("NACA 0012\n" + "\n".join(f"{x:.8f} {y:.8f}" for x, y in loop) + "\n")
    loaded = load_airfoil_dat(dat)
    assert loaded.shape == loop.shape
    assert np.allclose(loaded, loop, atol=1e-8)


def test_resample_preserves_shape():
    coarse = naca4_coordinates("0012", n_per_surface=400)
    resampled = resample_selig_loop(coarse, n_per_surface=60)
    assert len(resampled) == 119  # 2n - 1
    # thickness preserved within interpolation error
    assert 2.0 * np.max(resampled[:, 1]) == pytest.approx(0.12, abs=0.003)


def test_ogrid_generate_writes_surface_and_hints(tmp_path: Path):
    report = AirfoilOGridV1().generate("naca0012", tmp_path, {"n_per_surface": 65})
    assert report["characteristic_length"] == pytest.approx(1.0, abs=1e-6)
    assert report["pyhyp_hints"] == {
        "unattached_edges_are_symmetry": False,
        "bc": {1: {"jLow": "zSymm", "jHigh": "zSymm"}},
    }
    assert (tmp_path / "surface.fmt").is_file()
    on_disk = json.loads((tmp_path / "surface_report.json").read_text())
    assert on_disk["topology"] == "airfoil_ogrid_v1"
    assert on_disk["quality"]["min_scaled_jacobian"] > 0


def test_ogrid_cosine_clustering_at_le_and_te(tmp_path: Path):
    report = AirfoilOGridV1().generate("naca0012", tmp_path, {"n_per_surface": 129})
    # cosine spacing: tightest segments at LE/TE, coarsest near mid-chord
    assert report["min_segment_length"] < 0.2 * report["max_segment_length"]


def test_ogrid_closes_blunt_te(tmp_path: Path):
    # open the TE: trim the closing point and lift the first one
    loop = naca4_coordinates("0012", n_per_surface=100)
    blunt = loop[:-1].copy()
    blunt[0, 1] += 0.002
    report = AirfoilOGridV1().generate(blunt, tmp_path, {"te_base_points": 5})
    assert report["blunt_te_closed"] is True


def test_ogrid_rejects_unknown_params(tmp_path: Path):
    with pytest.raises(ValueError, match="unknown params"):
        AirfoilOGridV1().generate("naca0012", tmp_path, {"n_points": 100})


def test_plot3d_curve_format(tmp_path: Path):
    loop = naca4_coordinates("0012", n_per_surface=30)
    path = tmp_path / "surface.fmt"
    write_plot3d_curve(path, loop)
    lines = path.read_text().splitlines()
    assert lines[0] == "1"
    assert lines[1] == f"{len(loop)} 2 1"
    x_values = [float(v) for v in lines[2].split()]
    assert len(x_values) == len(loop)
    z0 = [float(v) for v in lines[6].split()]
    z1 = [float(v) for v in lines[7].split()]
    assert set(z0) == {0.0} and set(z1) == {1.0}


def test_airfoil_case_dry_run_applies_2d_hints(tmp_path: Path):
    case = tmp_path / "case.yaml"
    case.write_text(
        yaml.safe_dump(
            {
                "schema": "aeris.cfd.case.v1",
                "case": {
                    "name": "n0012",
                    "geometry": {"airfoil": "naca0012"},
                    "surface_mesh": {
                        "topology": "airfoil_ogrid_v1",
                        "overrides": {"n_per_surface": 65},
                    },
                    "volume_mesh": {
                        "level": "smoke",
                        "march_dist_factor": 100.0,
                        "overrides": {"s0": 5.0e-6},
                    },
                },
            }
        )
    )
    spec = load_case_spec(case)
    workdir = tmp_path / "run"
    results = run_case(spec, workdir=workdir, dry_run=True)
    assert results["surface"].status == "ok"
    assert results["surface"].details["mode"] == "generated"

    options = json.loads((workdir / "surface" / "pyhyp_options.json").read_text())
    assert options["unattachedEdgesAreSymmetry"] is False
    assert options["BC"] == {"1": {"jLow": "zSymm", "jHigh": "zSymm"}}
    assert options["s0"] == 5.0e-6
    assert options["marchDist"] == pytest.approx(100.0, rel=1e-5)

    manifest = json.loads((workdir / "surface" / "pyhyp_effective_options.json").read_text())
    assert manifest["options"]["BC"]["source"] == "topology"
    assert manifest["options"]["unattachedEdgesAreSymmetry"]["source"] == "topology"
    assert manifest["options"]["s0"]["source"] == "config"


def test_tmr_validation_config_loads():
    spec = load_case_spec(
        Path(__file__).resolve().parents[2] / "configs/cfd/validation_naca0012_tmr.yaml"
    )
    assert spec.geometry.airfoil == "naca0012"
    assert spec.solve is not None and spec.solve.flow.mach == 0.15
    assert spec.solve.flow.reynolds == 6.0e6
