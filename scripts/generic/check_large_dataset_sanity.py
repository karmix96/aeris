from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aeris.dataset.dataset_run import run_dataset_generation
from aeris.dataset.inspect import inspect_dataset


CONFIG_PATH = PROJECT_ROOT / "configs" / "geometry" / "wing_bwb.yaml"
DATASET_NAME = "sanity_n100_lhs2026"
DATASET_ROOT = PROJECT_ROOT / "data" / "datasets" / DATASET_NAME


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    if DATASET_ROOT.exists():
        shutil.rmtree(DATASET_ROOT)

    print("=== LARGE DATASET SANITY CHECK ===")
    rc = run_dataset_generation(
        config_path=CONFIG_PATH,
        n_samples=100,
        lhs_seed=2026,
        dataset_name=DATASET_NAME,
        save_plot=False,
        build_aerosandbox=True,
    )
    _assert(rc == 0, f"Dataset generation failed with code {rc}")

    qc = inspect_dataset(DATASET_ROOT)
    _assert(qc["manifest_status"] == "success", "Manifest status is not success")
    _assert(qc["requested_n"] == 100, "Requested count mismatch")
    _assert(qc["succeeded_n"] == 100, "Not all cases succeeded")
    _assert(qc["failed_n"] == 0, "Expected zero failures")
    _assert(qc["missing_file_count"] == 0, "Missing files detected")
    _assert(qc["duplicate_geometry_ids"] == [], "Duplicate geometry IDs detected")

    rows = _read_rows(DATASET_ROOT / "metadata.csv")
    _assert(len(rows) == 100, f"Expected 100 metadata rows, got {len(rows)}")

    for row in rows:
        gid = row["geometry_id"]

        full_span = float(row["full_span_m"])
        semi_span = float(row["semi_span_m"])
        area = float(row["approx_area_m2"])
        ar_planform = float(row["approx_aspect_ratio_planform"])
        ar_asb = float(row["aspect_ratio_aerosandbox"])
        n_sections = int(float(row["num_sections"]))
        n_xsecs = int(float(row["n_xsecs_aerosandbox"]))

        twist_min = float(row["twist_min_deg"])
        twist_max = float(row["twist_max_deg"])
        dihedral_min = float(row["dihedral_min_deg"])
        dihedral_max = float(row["dihedral_max_deg"])

        _assert(full_span > 0.0, f"{gid}: full_span_m <= 0")
        _assert(semi_span > 0.0, f"{gid}: semi_span_m <= 0")
        _assert(abs(full_span - 2.0 * semi_span) < 1e-9, f"{gid}: full_span != 2 * semi_span")
        _assert(area > 0.0, f"{gid}: approx_area_m2 <= 0")
        _assert(ar_planform > 0.0, f"{gid}: approx_aspect_ratio_planform <= 0")
        _assert(ar_asb > 0.0, f"{gid}: aspect_ratio_aerosandbox <= 0")
        _assert(abs(ar_planform - ar_asb) < 0.25, f"{gid}: AR mismatch too large")
        _assert(n_sections > 0, f"{gid}: num_sections <= 0")
        _assert(n_xsecs == n_sections, f"{gid}: n_xsecs_aerosandbox != num_sections")
        _assert(twist_min <= twist_max, f"{gid}: twist_min > twist_max")
        _assert(dihedral_min <= dihedral_max, f"{gid}: dihedral_min > dihedral_max")

        for artifact_col in [
            "summary_path",
            "control_points_path",
            "planform_sections_path",
            "section_3d_path",
        ]:
            _assert(Path(row[artifact_col]).exists(), f"{gid}: missing {artifact_col}")

    print(json.dumps(qc, indent=2))
    print("LARGE DATASET SANITY CHECK PASSED.")


if __name__ == "__main__":
    main()