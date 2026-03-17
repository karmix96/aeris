from __future__ import annotations
import numpy as np
import csv
import hashlib
import inspect
import json
import shutil
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aeris.common.config import load_yaml_config
from aeris.dataset.dataset_run import run_dataset_generation
from aeris.dataset.inspect import inspect_dataset
from aeris.dataset.lhs import generate_lhs_samples
from aeris.geometry.case import generate_geometry_case_from_sample
from aeris.geometry.params import build_bwb_generator_config
from aeris.geometry.planform import generate_bwb_planform_from_sample
from aeris.geometry.sampling import sample_bwb_design
from aeris.geometry.sections import build_section_geometry_from_sample
from aeris.geometry.validation import (
    validate_bwb_generator_config,
    validate_planform_result,
    validate_section_geometry,
)
from aeris.pipeline.geometry_run import run_geometry_generation


GEOMETRY_CONFIG = PROJECT_ROOT / "configs" / "geometry" / "wing_bwb.yaml"
DATASETS_DIR = PROJECT_ROOT / "data" / "datasets"
RUNS_DIR = PROJECT_ROOT / "data" / "runs"


def _to_plain(obj: Any) -> Any:
    if is_dataclass(obj):
        return {k: _to_plain(v) for k, v in asdict(obj).items()}

    if isinstance(obj, dict):
        return {str(k): _to_plain(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]

    if isinstance(obj, set):
        return sorted(_to_plain(v) for v in obj)

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


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _latest_subdir(root: Path) -> Path:
    subdirs = [p for p in root.iterdir() if p.is_dir()]
    if not subdirs:
        raise FileNotFoundError(f"No subdirectories found in: {root}")
    return max(subdirs, key=lambda p: p.stat().st_mtime)


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def check_function_signatures() -> None:
    print("\n[1] Checking signatures...")

    case_sig = inspect.signature(generate_geometry_case_from_sample)
    _assert("rng" not in case_sig.parameters, "generate_geometry_case_from_sample() still accepts rng")

    planform_sig = inspect.signature(generate_bwb_planform_from_sample)
    _assert("rng" not in planform_sig.parameters, "generate_bwb_planform_from_sample() still accepts rng")

    sections_sig = inspect.signature(build_section_geometry_from_sample)
    _assert("rng" not in sections_sig.parameters, "build_section_geometry_from_sample() should not accept rng")

    print("    OK: deterministic core signatures are clean.")


def check_single_case_determinism() -> None:
    print("\n[2] Checking single-case determinism...")

    raw = load_yaml_config(GEOMETRY_CONFIG)
    cfg = build_bwb_generator_config(raw)
    validate_bwb_generator_config(cfg)

    import numpy as np

    rng = np.random.default_rng(cfg.generator.seed)
    sample = sample_bwb_design(cfg, rng)

    planform_1 = generate_bwb_planform_from_sample(sample, cfg)
    validate_planform_result(planform_1)
    sections_1 = build_section_geometry_from_sample(planform_1, sample, cfg)
    validate_section_geometry(sections_1)

    planform_2 = generate_bwb_planform_from_sample(sample, cfg)
    validate_planform_result(planform_2)
    sections_2 = build_section_geometry_from_sample(planform_2, sample, cfg)
    validate_section_geometry(sections_2)

    h1 = _stable_hash({"sample": sample, "planform": planform_1, "sections": sections_1})
    h2 = _stable_hash({"sample": sample, "planform": planform_2, "sections": sections_2})

    _assert(h1 == h2, "Same explicit sample does not produce identical geometry twice")

    print("    OK: same explicit sample -> same geometry.")


def check_lhs_determinism() -> None:
    print("\n[3] Checking LHS determinism...")

    raw = load_yaml_config(GEOMETRY_CONFIG)
    cfg = build_bwb_generator_config(raw)
    validate_bwb_generator_config(cfg)

    samples_a = generate_lhs_samples(cfg, n_samples=8, lhs_seed=123)
    samples_b = generate_lhs_samples(cfg, n_samples=8, lhs_seed=123)
    samples_c = generate_lhs_samples(cfg, n_samples=8, lhs_seed=124)

    hash_a = _stable_hash(samples_a)
    hash_b = _stable_hash(samples_b)
    hash_c = _stable_hash(samples_c)

    _assert(hash_a == hash_b, "Same lhs_seed does not reproduce the same LHS samples")
    _assert(hash_a != hash_c, "Different lhs_seed produced the same LHS samples")

    print("    OK: LHS is reproducible and seed-sensitive in the right place.")


def check_geometry_pipeline_run() -> None:
    print("\n[4] Checking geometry pipeline run...")

    before = {p.name for p in RUNS_DIR.iterdir() if p.is_dir()} if RUNS_DIR.exists() else set()
    rc = run_geometry_generation(GEOMETRY_CONFIG)
    _assert(rc == 0, f"run_geometry_generation() failed with code {rc}")

    after = {p.name for p in RUNS_DIR.iterdir() if p.is_dir()}
    new_runs = sorted(after - before)
    _assert(new_runs, "No new run directory was created")

    run_dir = RUNS_DIR / new_runs[-1]
    manifest_path = run_dir / "manifest.json"
    _assert(manifest_path.exists(), f"Missing manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _assert(manifest["status"] == "success", "Geometry run manifest status is not success")
    _assert("geometry" in manifest and manifest["geometry"] is not None, "Geometry manifest payload missing")

    geometry_info = manifest["geometry"]
    _assert(geometry_info.get("geometry_deterministic") is True, "Manifest does not mark geometry as deterministic")
    _assert("design_sample" in geometry_info, "Manifest does not store explicit design_sample")
    _assert("design_sampling_seed" in geometry_info, "Manifest does not store design_sampling_seed")

    for key in ["summary_path", "control_points_path", "planform_sections_path", "section_3d_path"]:
        p = Path(geometry_info[key])
        _assert(p.exists(), f"Missing geometry artifact: {p}")

    print(f"    OK: geometry pipeline run succeeded -> {run_dir}")


def check_dataset_pipeline_run() -> None:
    print("\n[5] Checking dataset pipeline run...")

    dataset_name = "zz_check_architecture_integrity"
    dataset_root = DATASETS_DIR / dataset_name
    if dataset_root.exists():
        shutil.rmtree(dataset_root)

    rc = run_dataset_generation(
        config_path=GEOMETRY_CONFIG,
        n_samples=6,
        lhs_seed=777,
        dataset_name=dataset_name,
        save_plot=False,
        build_aerosandbox=False,
    )
    _assert(rc == 0, f"run_dataset_generation() failed with code {rc}")
    _assert(dataset_root.exists(), f"Dataset root was not created: {dataset_root}")

    manifest_path = dataset_root / "dataset_manifest.json"
    metadata_path = dataset_root / "metadata.csv"
    failures_path = dataset_root / "failures.csv"

    _assert(manifest_path.exists(), "Missing dataset manifest")
    _assert(metadata_path.exists(), "Missing metadata.csv")
    _assert(failures_path.exists(), "Missing failures.csv")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _assert(manifest["status"] == "success", "Dataset manifest status is not success")
    _assert(manifest["requested_n"] == 6, "Requested sample count mismatch")
    _assert(manifest["succeeded_n"] == 6, "Succeeded sample count mismatch")
    _assert(manifest["failed_n"] == 0, "Expected zero failures in check dataset")
    _assert(manifest.get("geometry_deterministic") is True, "Dataset manifest should say geometry_deterministic=True")

    rows = _read_csv_rows(metadata_path)
    _assert(len(rows) == 6, f"Expected 6 metadata rows, found {len(rows)}")

    seed_col = "realization_seed" if rows and "realization_seed" in rows[0] else "case_seed"
    mode_col = "realization_mode" if rows and "realization_mode" in rows[0] else None

    for i, row in enumerate(rows, start=1):
        _assert(row["geometry_id"] == f"geom_{i:05d}", f"Unexpected geometry_id at row {i}")
        _assert(row["lhs_seed"] == "777", f"Unexpected lhs_seed at row {i}")
        if mode_col is not None:
            _assert(
                row[mode_col] == "deterministic_from_sample",
                f"Unexpected realization_mode at row {i}: {row[mode_col]}",
            )
        if seed_col in row:
            _assert(
                row[seed_col] in ("", "None", None),
                f"{seed_col} should be empty/None in deterministic mode, got {row[seed_col]!r}",
            )

        for artifact_col in ["summary_path", "control_points_path", "planform_sections_path", "section_3d_path"]:
            artifact_path = Path(row[artifact_col])
            _assert(artifact_path.exists(), f"Missing dataset artifact: {artifact_path}")

    qc = inspect_dataset(dataset_root)
    _assert(qc["manifest_status"] == "success", "inspect_dataset() manifest status mismatch")
    _assert(qc["metadata_rows"] == 6, "inspect_dataset() metadata_rows mismatch")
    _assert(qc["failure_rows"] == 0, "inspect_dataset() failure_rows mismatch")
    _assert(qc["missing_file_count"] == 0, "inspect_dataset() found missing files")

    print(f"    OK: dataset pipeline run succeeded -> {dataset_root}")


def check_dataset_reproducibility() -> None:
    print("\n[6] Checking dataset reproducibility across repeated runs...")

    name_a = "zz_check_repro_a"
    name_b = "zz_check_repro_b"

    for name in [name_a, name_b]:
        root = DATASETS_DIR / name
        if root.exists():
            shutil.rmtree(root)

    rc_a = run_dataset_generation(
        config_path=GEOMETRY_CONFIG,
        n_samples=5,
        lhs_seed=999,
        dataset_name=name_a,
        save_plot=False,
        build_aerosandbox=False,
    )
    rc_b = run_dataset_generation(
        config_path=GEOMETRY_CONFIG,
        n_samples=5,
        lhs_seed=999,
        dataset_name=name_b,
        save_plot=False,
        build_aerosandbox=False,
    )

    _assert(rc_a == 0 and rc_b == 0, "Repeated reproducibility runs failed")

    rows_a = _read_csv_rows(DATASETS_DIR / name_a / "metadata.csv")
    rows_b = _read_csv_rows(DATASETS_DIR / name_b / "metadata.csv")

    comparable_a = []
    comparable_b = []

    comparable_fields = [
        "geometry_id",
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
        "semi_span_m",
        "full_span_m",
        "approx_area_m2",
        "approx_aspect_ratio_planform",
        "num_sections",
        "twist_min_deg",
        "twist_max_deg",
        "twist_mean_deg",
        "dihedral_min_deg",
        "dihedral_max_deg",
        "dihedral_mean_deg",
    ]

    for row in rows_a:
        comparable_a.append({k: row[k] for k in comparable_fields if k in row})
    for row in rows_b:
        comparable_b.append({k: row[k] for k in comparable_fields if k in row})

    _assert(
        _stable_hash(comparable_a) == _stable_hash(comparable_b),
        "Two dataset runs with the same lhs_seed produced different geometry/metadata",
    )

    print("    OK: repeated dataset runs with same lhs_seed are reproducible.")


def main() -> None:
    print("=== AERIS ARCHITECTURE INTEGRITY CHECK ===")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Geometry config: {GEOMETRY_CONFIG}")

    _assert(GEOMETRY_CONFIG.exists(), f"Missing config file: {GEOMETRY_CONFIG}")

    check_function_signatures()
    check_single_case_determinism()
    check_lhs_determinism()
    check_geometry_pipeline_run()
    check_dataset_pipeline_run()
    check_dataset_reproducibility()

    print("\nALL CHECKS PASSED.")
    print("Your RNG/LHS/deterministic architecture is behaving correctly.")


if __name__ == "__main__":
    main()