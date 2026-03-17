from __future__ import annotations

import csv
import hashlib
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aeris.common.config import load_yaml_config
from aeris.geometry.case import generate_geometry_case_from_sample
from aeris.geometry.params import BWBDesignSample, build_bwb_generator_config


DATASET_ROOT = PROJECT_ROOT / "data" / "datasets" / "wing_bwb_bwb_segmented_v1_n10_lhs123"


DESIGN_FIELDS = [
    "c1_m",
    "c2_ratio",
    "c3_ratio",
    "c4_ratio",
    "b_total_m",
    "b3_ratio",
    "split_ratio",
    "sw1_deg",
    "sw2_deg",
    "sw3_deg",
    "twist_b0_deg",
    "twist_b1_deg",
    "twist_b2_deg",
    "twist_b3_deg",
    "dihedral_b1_deg",
    "dihedral_b2_deg",
    "dihedral_b3_deg",
]


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _to_plain(obj: Any) -> Any:
    if is_dataclass(obj):
        return {k: _to_plain(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    return obj


def _stable_hash(obj: Any) -> str:
    payload = json.dumps(_to_plain(obj), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_metadata_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _sample_from_row(row: dict[str, str]) -> BWBDesignSample:
    kwargs = {field: float(row[field]) for field in DESIGN_FIELDS}
    return BWBDesignSample(**kwargs)


def _stored_case_signature(row: dict[str, str]) -> dict[str, Any]:
    summary = json.loads(Path(row["summary_path"]).read_text(encoding="utf-8"))

    return {
        "sample": {field: float(row[field]) for field in DESIGN_FIELDS},
        "planform_metrics": {
            "semi_span_m": float(row["semi_span_m"]),
            "full_span_m": float(row["full_span_m"]),
            "approx_area_m2": float(row["approx_area_m2"]),
            "approx_aspect_ratio_planform": float(row["approx_aspect_ratio_planform"]),
            "num_sections": int(float(row["num_sections"])),
        },
        "section_stats": {
            "twist_min_deg": float(row["twist_min_deg"]),
            "twist_max_deg": float(row["twist_max_deg"]),
            "twist_mean_deg": float(row["twist_mean_deg"]),
            "dihedral_min_deg": float(row["dihedral_min_deg"]),
            "dihedral_max_deg": float(row["dihedral_max_deg"]),
            "dihedral_mean_deg": float(row["dihedral_mean_deg"]),
        },
        "summary_core": {
            "generator_family": summary.get("generator", {}).get("family"),
            "generator_version": summary.get("generator", {}).get("version"),
        },
    }


def _regenerated_case_signature(result) -> dict[str, Any]:
    twists = np.asarray(result.section_geometry.twist_array_deg, dtype=float)
    dihedrals = np.asarray(result.section_geometry.dihedral_array_deg, dtype=float)

    return {
        "sample": _to_plain(result.sample),
        "planform_metrics": {
            "semi_span_m": float(result.planform.semi_span_m),
            "full_span_m": float(result.planform.full_span_m),
            "approx_area_m2": float(result.planform.approx_area_m2),
            "approx_aspect_ratio_planform": float(result.planform.approx_aspect_ratio),
            "num_sections": int(result.planform.num_sections),
        },
        "section_stats": {
            "twist_min_deg": float(np.min(twists)),
            "twist_max_deg": float(np.max(twists)),
            "twist_mean_deg": float(np.mean(twists)),
            "dihedral_min_deg": float(np.min(dihedrals)),
            "dihedral_max_deg": float(np.max(dihedrals)),
            "dihedral_mean_deg": float(np.mean(dihedrals)),
        },
        "summary_core": {
            "generator_family": result.summary.get("generator", {}).get("family"),
            "generator_version": result.summary.get("generator", {}).get("version"),
        },
    }


def main() -> None:
    metadata_path = DATASET_ROOT / "metadata.csv"
    config_path = DATASET_ROOT / "configs" / "input_config.yaml"
    regen_root = DATASET_ROOT / "_regen_check"

    _assert(DATASET_ROOT.exists(), f"Dataset does not exist: {DATASET_ROOT}")
    _assert(metadata_path.exists(), f"Missing metadata: {metadata_path}")
    _assert(config_path.exists(), f"Missing input config: {config_path}")

    raw = load_yaml_config(config_path)
    cfg = build_bwb_generator_config(raw)

    rows = _read_metadata_rows(metadata_path)
    _assert(rows, "Metadata is empty")

    regen_root.mkdir(parents=True, exist_ok=True)

    print("=== METADATA REGENERATION CHECK ===")
    print(f"Dataset: {DATASET_ROOT}")
    print(f"Rows: {len(rows)}")

    for row in rows:
        geometry_id = row["geometry_id"]
        sample = _sample_from_row(row)

        result = generate_geometry_case_from_sample(
            config=cfg,
            sample=sample,
            output_dir=regen_root / geometry_id,
            save_plot=False,
            build_aerosandbox=cfg.outputs.build_aerosandbox,
        )

        stored_sig = _stored_case_signature(row)
        regen_sig = _regenerated_case_signature(result)

        _assert(
            _stable_hash(stored_sig) == _stable_hash(regen_sig),
            f"Regenerated geometry does not match stored metadata for {geometry_id}",
        )
        print(f"OK: {geometry_id}")

    print("ALL ROWS MATCH REGENERATED GEOMETRY.")


if __name__ == "__main__":
    main()