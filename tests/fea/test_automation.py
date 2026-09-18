from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest
import yaml

from aeris.fea.calculix import parse_calculix_dat, pressure_for_element
from aeris.fea.calibration import run_calibration
from aeris.fea.case.loader import load_case_spec
from aeris.fea.case.runner import CASE_MANIFEST_SCHEMA_VERSION, run_case
from aeris.fea.case.spec import LoadCaseSpec, MeshSpec, SectionSpec, WingboxSpec
from aeris.fea.geometry import generate_aeris_stations
from aeris.fea.governance import run_qualification
from aeris.fea.holdout import promote_holdout
from aeris.fea.mesh import build_wingbox_mesh, write_mesh_artifacts
from aeris.fea.mission import load_mission_authority
from aeris.fea.openaerostruct import build_oas_mesh, run_oas_validation
from aeris.fea.study.loader import load_study_spec
from aeris.fea.visualize import plot_mesh


def _stations() -> dict[str, object]:
    return {
        "schema": "aeris.fea.stations.v1",
        "symmetric": True,
        "stations": [
            {
                "x_le_m": 0.0,
                "y_m": 0.0,
                "z_le_m": 0.0,
                "chord_m": 1.0,
                "twist_deg": 0.0,
                "dihedral_deg": 0.0,
            },
            {
                "x_le_m": 0.15,
                "y_m": 1.0,
                "z_le_m": 0.05,
                "chord_m": 0.5,
                "twist_deg": -3.0,
                "dihedral_deg": 3.0,
            },
        ],
    }


def _case_body(stations_file: Path) -> dict[str, object]:
    return {
        "name": "structural_test",
        "geometry": {"stations_file": str(stations_file)},
        "wingbox": {"front_spar_fraction": 0.15, "rear_spar_fraction": 0.65, "depth_ratio": 0.12},
        "mesh": {
            "target_size_m": 0.25,
            "chordwise_elements": 4,
            "depth_elements": 2,
            "max_aspect_ratio": 50.0,
            "min_corner_angle_deg": 10.0,
        },
        "material": {
            "name": "aluminum",
            "youngs_modulus_pa": 70e9,
            "poisson_ratio": 0.33,
            "density_kg_m3": 2700.0,
            "yield_strength_pa": 250e6,
        },
        "section": {"skin_thickness_m": 0.002, "spar_thickness_m": 0.0025},
        "loads": [
            {
                "name": "limit",
                "pressure_pa": 1000.0,
                "distribution": "elliptical",
                "load_factor": 3.0,
            }
        ],
    }


def _write_case(tmp_path: Path) -> Path:
    stations = tmp_path / "stations.json"
    stations.write_text(json.dumps(_stations()), encoding="utf-8")
    path = tmp_path / "case.yaml"
    path.write_text(
        yaml.safe_dump({"schema": "aeris.fea.case.v1", "case": _case_body(stations)}),
        encoding="utf-8",
    )
    return path


def test_case_loader_enforces_open_source_solver_and_spar_order(tmp_path: Path) -> None:
    path = _write_case(tmp_path)
    spec = load_case_spec(path)
    assert spec.solver.solver == "calculix"
    assert spec.loads[0].load_factor == 3.0
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["case"]["solver"] = {"name": "abaqus"}
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="open-source policy"):
        load_case_spec(path)
    raw["case"]["solver"] = {"name": "calculix"}
    raw["case"]["wingbox"] = {"front_spar_fraction": 0.8, "rear_spar_fraction": 0.2}
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="spar fractions"):
        load_case_spec(path)


def test_wingbox_mesh_is_closed_shared_and_writes_open_formats(tmp_path: Path) -> None:
    mesh = build_wingbox_mesh(
        _stations(),
        WingboxSpec(),
        MeshSpec(
            target_size_m=0.25,
            chordwise_elements=4,
            depth_elements=2,
            max_aspect_ratio=50.0,
            min_corner_angle_deg=10.0,
        ),
        SectionSpec(skin_thickness_m=0.002, spar_thickness_m=0.0025),
        2700.0,
    )
    assert len(mesh.nodes) < 4 * len(mesh.elements)
    assert len(mesh.root_nodes) == 2 * (4 + 1) + 2 * (2 - 1)
    assert mesh.mass_kg > 0.0
    artifacts = write_mesh_artifacts(mesh, tmp_path / "mesh")
    assert Path(artifacts["gmsh_mesh"]).read_text().startswith("$MeshFormat")
    assert "*ELEMENT, TYPE=S4" in Path(artifacts["calculix_mesh"]).read_text()


def test_elliptical_pressure_tapers_and_preserves_sign() -> None:
    load = LoadCaseSpec("positive", pressure_pa=100.0, distribution="elliptical", load_factor=2.0)
    assert pressure_for_element(load, 0.0) == pytest.approx(200.0)
    assert pressure_for_element(load, 1.0) == pytest.approx(0.0)
    negative = LoadCaseSpec("negative", pressure_pa=-100.0, distribution="uniform")
    assert pressure_for_element(negative, 0.5) == pytest.approx(-100.0)


def test_oas_mesh_uses_canonical_le_and_local_twist() -> None:
    stations = _stations()
    stations["stations"][0]["twist_deg"] = 5.0  # type: ignore[index]
    mesh = build_oas_mesh(stations, 5)
    root_le = mesh[0, -1]
    root_te = mesh[-1, -1]
    assert root_le.tolist() == pytest.approx([0.0, 0.0, 0.0])
    assert root_te[2] < root_le[2]
    assert (root_te[0] - root_le[0]) == pytest.approx(0.996194698, rel=1e-8)


def test_calculix_dat_parser_extracts_vector_norm_and_von_mises(tmp_path: Path) -> None:
    path = tmp_path / "model.dat"
    path.write_text(
        """
 displacements (vx,vy,vz) for set NALL and time 1.0
 1  3.0E-03  4.0E-03  0.0
 forces (fx,fy,fz) for set ROOT and time 1.0
 1  -3.0E+02  0.0  -4.0E+02
 stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set EALL and time 1.0
 1  1  1.0E+08  0.0  0.0  0.0  0.0  0.0
""",
        encoding="utf-8",
    )
    parsed = parse_calculix_dat(path)
    assert parsed["max_displacement_m"] == pytest.approx(0.005)
    assert parsed["max_von_mises_pa"] == pytest.approx(1.0e8)
    assert parsed["reaction_force_n"] == pytest.approx([-300.0, 0.0, -400.0])


def test_dry_run_writes_mesh_deck_and_hashed_manifest(tmp_path: Path) -> None:
    spec = load_case_spec(_write_case(tmp_path))
    run_dir = tmp_path / "run"
    results = run_case(spec, workdir=run_dir, dry_run=True)
    assert results["geometry"].status == "ok"
    assert results["mesh"].status == "ok"
    assert results["solve"].status == "dry_run"
    assert results["post"].status == "skipped"
    assert (run_dir / "solve" / "limit" / "model.inp").is_file()
    manifest = json.loads((run_dir / "case_manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == CASE_MANIFEST_SCHEMA_VERSION
    assert manifest["open_source_stack"]["solver"] == "CalculiX"
    assert len(manifest["stages"]["mesh"]["sha256"]["gmsh_mesh"]) == 64


@pytest.mark.integration
@pytest.mark.skipif(
    importlib.util.find_spec("openaerostruct") is None,
    reason="OpenAeroStruct optional dependency not installed",
)
def test_s8_openaerostruct_comparison_is_governed_and_passes(tmp_path: Path) -> None:
    spec = load_case_spec(Path("configs/fea/bwb_baseline.yaml"))
    assert spec.geometry.design_index == 83
    stations = generate_aeris_stations(
        spec.geometry.aeris_config,
        tmp_path / "stations.json",
        design_matrix_file=spec.geometry.design_matrix_file,
        design_set=spec.geometry.design_set,
        design_index=spec.geometry.design_index,
    )
    assert spec.mission is not None
    mission = load_mission_authority(spec.mission.authority_file)
    report = run_oas_validation(
        stations,
        mission,
        spec.openaerostruct_validation,
        tmp_path / "oas.json",
    )
    assert report["status"] == "pass"
    assert report["lift_curve"]["relative_error"] < 0.02
    assert max(abs(row["cl_error"]) for row in report["comparisons"]) < 0.08


def test_governed_studies_cover_convergence_and_s8_pilot() -> None:
    convergence = load_study_spec("configs/fea/study_mesh_convergence.yaml")
    assert convergence.convergence.enabled
    assert [variant.name for variant in convergence.variants] == ["coarse", "medium", "fine"]
    pilot = load_study_spec("configs/fea/study_s8_pilot.yaml")
    assert len(pilot.variants) == 10
    assert pilot.baseline == "index83"


def test_rich_topology_and_qualification_authority_are_exercised(tmp_path: Path) -> None:
    spec = load_case_spec("configs/fea/bwb_baseline.yaml")
    stations = generate_aeris_stations(
        spec.geometry.aeris_config,
        tmp_path / "stations.json",
        design_matrix_file=spec.geometry.design_matrix_file,
        design_set=spec.geometry.design_set,
        design_index=spec.geometry.design_index,
    )
    mesh = build_wingbox_mesh(
        stations,
        spec.wingbox,
        spec.mesh,
        spec.section,
        spec.material.density_kg_m3,
    )
    regions = {element.region for element in mesh.elements}
    assert "RIB" in regions
    assert "SPAR_REAR_HINGE" in regions
    assert any(region.endswith("CUTOUT_REINFORCEMENT") for region in regions)
    report = run_qualification(spec, tmp_path / "qualification.json")
    assert report["status"] == "pass"
    assert report["physical_validation"]["detailed_design_gate"] is False


def test_holdout_geometry_requires_a_frozen_authority(tmp_path: Path) -> None:
    source = Path("configs/geometry/bwb.yaml")
    matrix = Path("AERIS_MESH_STUDY/00_governance/round_c_lhs10_seed42_samples.csv")
    with pytest.raises(ValueError, match="hold-out"):
        generate_aeris_stations(
            source,
            tmp_path / "holdout.json",
            design_matrix_file=matrix,
            design_set="round_c_lhs10_seed42",
            design_index=0,
        )


def test_mesh_visualization_is_reproducible(tmp_path: Path) -> None:
    mesh = build_wingbox_mesh(
        _stations(),
        WingboxSpec(),
        MeshSpec(target_size_m=0.25, chordwise_elements=4, depth_elements=2,
                 max_aspect_ratio=50.0, min_corner_angle_deg=10.0),
        SectionSpec(skin_thickness_m=0.002, spar_thickness_m=0.0025),
        2700.0,
    )
    artifacts = write_mesh_artifacts(mesh, tmp_path / "mesh")
    case_dir = tmp_path / "case"
    (case_dir / "mesh").mkdir(parents=True)
    target = case_dir / "mesh" / "wingbox_mesh.inp"
    target.write_text(
        Path(artifacts["calculix_mesh"]).read_text(encoding="utf-8"), encoding="utf-8"
    )
    image = plot_mesh(case_dir, tmp_path / "visuals")
    assert image.is_file()
    assert image.stat().st_size > 1000


def test_calibration_requires_released_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.yaml"
    evidence.write_text(
        yaml.safe_dump(
            {
                "schema": "aeris.fea.calibration_evidence.v1",
                "status": "released",
                "records": [
                    {
                        "name": "coupon_modulus",
                        "quantity": "modulus_pa",
                        "predicted": 70.0,
                        "measured": 70.5,
                        "tolerance": 0.01,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report = run_calibration(evidence, tmp_path / "calibration.json")
    assert report["status"] == "pass"
    assert report["detailed_design_gate"] is True


def test_holdout_promotion_fails_closed_without_freeze_and_evidence(tmp_path: Path) -> None:
    study = tmp_path / "study.json"
    study.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
    authority = tmp_path / "freeze.yaml"
    authority.write_text(
        yaml.safe_dump(
            {
                "schema": "aeris.fea.freeze_authority.v1",
                "status": "development",
                "holdout_set": "round_c",
                "holdout_access_authorized": False,
            }
        ),
        encoding="utf-8",
    )
    qualification = tmp_path / "qualification.json"
    qualification.write_text(
        json.dumps({"physical_validation": {"detailed_design_gate": False}}),
        encoding="utf-8",
    )
    report = promote_holdout(study, authority, qualification, tmp_path / "promotion.json")
    assert report["status"] == "blocked"
    assert len(report["blocking_checks"]) == 3


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("ccx") is None, reason="CalculiX not installed")
def test_real_calculix_smoke_case(tmp_path: Path) -> None:
    spec = load_case_spec(_write_case(tmp_path))
    results = run_case(spec, workdir=tmp_path / "real")
    assert results["solve"].status == "ok"
    assert results["post"].status == "ok"
    verification = json.loads((tmp_path / "real" / "verification.json").read_text())
    assert verification["status"] == "pass"
    assert verification["loads"]["limit"]["max_von_mises_pa"] > 0.0
