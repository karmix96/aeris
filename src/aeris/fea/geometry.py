"""Geometry boundary between canonical AERIS wings and structural stations."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml


def generate_aeris_stations(
    config_path: Path,
    output_path: Path,
    *,
    seed: int | None = None,
    wing_index: int = 0,
    design_matrix_file: Path | None = None,
    design_set: str | None = None,
    design_index: int | None = None,
    freeze_authority_file: Path | None = None,
    holdout_authorized: bool = False,
) -> dict[str, object]:
    """Generate structural stations without invoking CAD or proprietary tools.

    The canonical BWB generator currently exposes one symmetric main wing.  The
    explicit wing-index check prevents silently analyzing a different component
    when future geometry families contain multiple lifting surfaces.
    """
    if wing_index != 0:
        raise ValueError("bwb_segmented currently exposes only structural wing_index=0")

    from aeris.common.config import file_sha256, load_yaml_config
    from aeris.generators.bwb_segmented_v1.params import BWBDesignSample
    from aeris.generators.bwb_segmented_v1.planform import generate_bwb_planform_from_sample
    from aeris.generators.bwb_segmented_v1.sections import build_section_geometry_from_sample
    from aeris.geometry.config_resolver import resolve_generator_and_config
    from aeris.geometry.registry import get_geometry_generator

    path = config_path.expanduser().resolve()
    if design_set and design_set.startswith("round_c"):
        if not holdout_authorized or freeze_authority_file is None:
            raise ValueError(
                "Round C hold-out is sealed; provide an explicitly frozen structural authority"
            )
        freeze = yaml.safe_load(
            freeze_authority_file.expanduser().resolve().read_text(encoding="utf-8")
        )
        if not isinstance(freeze, dict) or freeze.get("status") != "frozen" or not freeze.get(
            "holdout_access_authorized", False
        ):
            raise ValueError("hold-out freeze authority is not frozen and authorized")
    raw = load_yaml_config(path)
    generator_id, generator_config = resolve_generator_and_config(raw)
    if generator_id not in {"bwb_segmented", "bwb_segmented_v1"}:
        raise ValueError(
            "FEA station extraction currently supports the canonical "
            f"bwb_segmented generator, got {generator_id!r}"
        )
    generator = get_geometry_generator(generator_id)
    design_identity: dict[str, object] = {}
    if design_matrix_file is not None:
        if design_set is None or design_index is None:
            raise ValueError("locked design geometry requires design_set and design_index")
        matrix_path = design_matrix_file.expanduser().resolve()
        if not matrix_path.is_file():
            raise ValueError(f"locked design matrix not found: {matrix_path}")
        with matrix_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        matches = [row for row in rows if int(row.get("sample_index", -1)) == design_index]
        if len(matches) != 1:
            raise ValueError(
                f"locked design matrix must contain exactly one sample_index={design_index}, "
                f"found {len(matches)}"
            )
        names = generator_config.active_design_variable_names()
        missing = [name for name in names if not matches[0].get(name)]
        if missing:
            raise ValueError(f"locked design row is missing active variables: {missing}")
        sample = BWBDesignSample(**{name: float(matches[0][name]) for name in names})
        effective_seed = None
        design_identity = {
            "design_set": design_set,
            "design_index": design_index,
            "design_matrix_file": str(matrix_path),
            "design_matrix_sha256": file_sha256(matrix_path),
            "design_vector": {name: float(matches[0][name]) for name in names},
        }
    else:
        if design_set is not None or design_index is not None:
            raise ValueError("design_set/design_index require design_matrix_file")
        effective_seed = generator_config.generator.seed if seed is None else seed
        sample = generator.sample_one(generator_config, seed=effective_seed)
    planform = generate_bwb_planform_from_sample(sample, generator_config)
    sections = build_section_geometry_from_sample(planform, sample, generator_config)

    payload: dict[str, object] = {
        "schema": "aeris.fea.stations.v1",
        "source_config": str(path),
        "source_config_sha256": file_sha256(path),
        "generator": generator_id,
        "seed": effective_seed,
        **design_identity,
        "symmetric": True,
        "stations": [
            {
                "x_le_m": station.x_le_m,
                "y_m": station.y_m,
                "z_le_m": station.z_le_m,
                "chord_m": station.chord_m,
                "twist_deg": station.twist_deg,
                "dihedral_deg": station.dihedral_deg,
                "airfoil_name": station.airfoil_name,
            }
            for station in sections.sections
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def load_stations(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "aeris.fea.stations.v1":
        raise ValueError(f"structural stations schema is invalid in {path}")
    stations = payload.get("stations")
    if not isinstance(stations, list) or len(stations) < 2:
        raise ValueError("structural station file must contain at least two stations")
    last_y = float("-inf")
    for index, station in enumerate(stations):
        if not isinstance(station, dict):
            raise ValueError(f"stations[{index}] must be a mapping")
        for key in ("x_le_m", "y_m", "z_le_m", "chord_m", "twist_deg"):
            if not isinstance(station.get(key), (int, float)):
                raise ValueError(f"stations[{index}].{key} must be numeric")
        y = float(station["y_m"])
        if y <= last_y:
            raise ValueError("structural stations must be strictly increasing in y")
        if float(station["chord_m"]) <= 0.0:
            raise ValueError(f"stations[{index}].chord_m must be positive")
        last_y = y
    return payload
