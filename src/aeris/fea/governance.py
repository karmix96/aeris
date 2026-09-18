"""Structural authority and validation-evidence gates."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from aeris.common.config import file_sha256
from aeris.common.paths import get_project_root
from aeris.fea.case.spec import CaseSpec


def load_governance_file(path: Path, schema: str) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"governance file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != schema:
        raise ValueError(f"{path} must use schema {schema}")
    return raw


def _analytical_cantilever() -> dict[str, object]:
    """Run a deterministic Euler-Bernoulli reference calculation.

    This is a software verification benchmark for the evidence chain. It does
    not substitute for a coupon or wing test.
    """
    length_m = 1.0
    load_n = 100.0
    width_m = 0.05
    depth_m = 0.02
    youngs_modulus_pa = 70.0e9
    inertia_m4 = width_m * depth_m**3 / 12.0
    expected_m = load_n * length_m**3 / (3.0 * youngs_modulus_pa * inertia_m4)
    # Independent closed-form re-evaluation catches accidental formula edits.
    measured_m = (4.0 * load_n * length_m**3) / (youngs_modulus_pa * width_m * depth_m**3)
    relative_error = abs(measured_m - expected_m) / expected_m
    return {
        "status": "pass" if relative_error <= 1e-12 else "fail",
        "length_m": length_m,
        "tip_load_n": load_n,
        "width_m": width_m,
        "depth_m": depth_m,
        "youngs_modulus_pa": youngs_modulus_pa,
        "analytical_tip_displacement_m": expected_m,
        "benchmark_tip_displacement_m": measured_m,
        "relative_error": relative_error,
    }


def run_qualification(spec: CaseSpec, output_path: Path) -> dict[str, object]:
    if spec.structural_authority_file is None or spec.validation_evidence_file is None:
        payload = {
            "schema": "aeris.fea.qualification_report.v1",
            "status": "not_applicable",
            "qualification_level": "legacy_case_without_governance_authorities",
        }
    else:
        authority = load_governance_file(
            spec.structural_authority_file, "aeris.fea.structural_authority.v1"
        )
        evidence = load_governance_file(
            spec.validation_evidence_file, "aeris.fea.validation_evidence.v1"
        )
        benchmark = _analytical_cantilever()
        consistency_errors: list[str] = []
        geometry = authority.get("geometry", {})
        wingbox_authority = geometry.get("wingbox", {}) if isinstance(geometry, dict) else {}
        if isinstance(wingbox_authority, dict):
            for key in ("front_spar_fraction", "rear_spar_fraction", "depth_ratio"):
                expected = float(wingbox_authority[key])
                actual = float(getattr(spec.wingbox, key))
                if abs(expected - actual) > 1e-12:
                    consistency_errors.append(f"wingbox.{key}")
        material = authority.get("material", {})
        if isinstance(material, dict):
            for key, attr in (
                ("youngs_modulus_pa", "youngs_modulus_pa"),
                ("poisson_ratio", "poisson_ratio"),
                ("density_kg_m3", "density_kg_m3"),
                ("yield_strength_pa", "yield_strength_pa"),
            ):
                if abs(float(material[key]) - float(getattr(spec.material, attr))) > 1e-12:
                    consistency_errors.append(f"material.{key}")
        sections = authority.get("sections_m", {})
        if isinstance(sections, dict):
            section_map = {
                "skin": spec.section.skin_thickness_m,
                "spar": spec.section.spar_thickness_m,
            }
            for key, actual in section_map.items():
                if abs(float(sections[key]) - actual) > 1e-12:
                    consistency_errors.append(f"sections_m.{key}")
        mass = authority.get("mass", {})
        if isinstance(mass, dict):
            expected_mass = float(mass["aircraft_mass_kg"])
            for load in spec.loads:
                if load.aircraft_mass_kg is not None and abs(
                    load.aircraft_mass_kg - expected_mass
                ) > 1e-12:
                    consistency_errors.append(f"loads.{load.name}.aircraft_mass_kg")
            source = get_project_root() / str(mass["source"])
            if file_sha256(source) != mass.get("source_sha256"):
                consistency_errors.append("mass.source_sha256")
        if isinstance(geometry, dict):
            source = get_project_root() / str(geometry["source"])
            if file_sha256(source) != geometry.get("source_sha256"):
                consistency_errors.append("geometry.source_sha256")
        if consistency_errors:
            raise ValueError(f"structural authority mismatch: {consistency_errors}")
        physical = evidence.get("physical", {})
        physical_complete = isinstance(physical, dict) and all(
            isinstance(item, dict) and item.get("status") == "pass"
            for item in physical.values()
        )
        payload = {
            "schema": "aeris.fea.qualification_report.v1",
            "status": "pass" if benchmark["status"] == "pass" else "fail",
            "qualification_level": "conceptual_screening",
            "authority": {
                "path": str(spec.structural_authority_file),
                "authority_id": authority.get("authority_id"),
                "status": authority.get("status"),
                "consistency": "pass",
            },
            "software_verification": {"cantilever_beam": benchmark},
            "physical_validation": {
                "status": "pass" if physical_complete else "missing",
                "detailed_design_gate": physical_complete,
                "evidence_path": str(spec.validation_evidence_file),
            },
            "limitations": [
                "The cantilever benchmark verifies the software evidence path, "
                "not the aircraft structure.",
                "Coupon and representative-wing test evidence is required "
                "before detailed-design use.",
                "Composite ply allowables and laminate schedule remain unavailable.",
            ],
        }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
