from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aeris.common.config import load_yaml_config
from aeris.generators.bwb_segmented_v1.case import generate_geometry_case_from_sample
from aeris.generators.bwb_segmented_v1.params import BWBDesignSample, build_bwb_generator_config
from aeris.generators.bwb_segmented_v1.validators import audit_geometry_result


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


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _sample_from_row(row: dict[str, str]) -> BWBDesignSample:
    kwargs = {field: float(row[field]) for field in DESIGN_FIELDS}
    return BWBDesignSample(**kwargs)


def _float(row: dict[str, str], key: str) -> float:
    return float(row[key])


def _int(row: dict[str, str], key: str) -> int:
    return int(float(row[key]))


def audit_dataset(
    *,
    dataset_root: Path,
    regen_check_count: int = 0,
    seed: int = 12345,
) -> dict[str, Any]:
    dataset_root = dataset_root.expanduser().resolve()

    metadata_path = dataset_root / "metadata.csv"
    manifest_path = dataset_root / "dataset_manifest.json"
    config_path = dataset_root / "configs" / "input_config.yaml"

    _assert(dataset_root.exists(), f"Dataset root not found: {dataset_root}")
    _assert(metadata_path.exists(), f"Missing metadata.csv: {metadata_path}")
    _assert(manifest_path.exists(), f"Missing dataset_manifest.json: {manifest_path}")
    _assert(config_path.exists(), f"Missing input_config.yaml: {config_path}")

    rows = _read_rows(metadata_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    raw_cfg = load_yaml_config(config_path)
    cfg = build_bwb_generator_config(raw_cfg)

    total_rows = len(rows)
    error_rows: list[dict[str, Any]] = []
    warning_rows: list[dict[str, Any]] = []

    ar_deltas: list[float] = []
    min_chords: list[float] = []
    max_chords: list[float] = []

    for row in rows:
        gid = row["geometry_id"]

        # basic file existence
        for artifact_col in [
            "summary_path",
            "control_points_path",
            "planform_sections_path",
            "section_3d_path",
        ]:
            p = Path(row[artifact_col])
            if not p.exists():
                error_rows.append(
                    {"geometry_id": gid, "kind": "missing_artifact", "message": f"{artifact_col}: {p}"}
                )

        plot_path = row.get("plot_path", "")
        if plot_path.strip():
            p = Path(plot_path)
            if not p.exists():
                error_rows.append(
                    {"geometry_id": gid, "kind": "missing_plot", "message": f"plot_path: {p}"}
                )

        # simple metadata-level checks
        full_span = _float(row, "full_span_m")
        semi_span = _float(row, "semi_span_m")
        area = _float(row, "approx_area_m2")
        ar_planform = _float(row, "approx_aspect_ratio_planform")
        ar_asb = _float(row, "aspect_ratio_aerosandbox")
        num_sections = _int(row, "num_sections")
        n_xsecs = _int(row, "n_xsecs_aerosandbox")

        if full_span <= 0:
            error_rows.append({"geometry_id": gid, "kind": "bad_scalar", "message": "full_span_m <= 0"})
        if semi_span <= 0:
            error_rows.append({"geometry_id": gid, "kind": "bad_scalar", "message": "semi_span_m <= 0"})
        if area <= 0:
            error_rows.append({"geometry_id": gid, "kind": "bad_scalar", "message": "approx_area_m2 <= 0"})
        if abs(full_span - 2.0 * semi_span) > 1e-9:
            error_rows.append(
                {"geometry_id": gid, "kind": "span_mismatch", "message": "full_span != 2 * semi_span"}
            )
        if num_sections <= 0:
            error_rows.append({"geometry_id": gid, "kind": "bad_scalar", "message": "num_sections <= 0"})
        if n_xsecs != num_sections:
            warning_rows.append(
                {
                    "geometry_id": gid,
                    "kind": "section_count_warning",
                    "message": f"n_xsecs_aerosandbox={n_xsecs} vs num_sections={num_sections}",
                }
            )

        ar_delta = abs(ar_planform - ar_asb)
        ar_deltas.append(ar_delta)
        if ar_delta > 0.25:
            warning_rows.append(
                {
                    "geometry_id": gid,
                    "kind": "ar_delta_warning",
                    "message": f"|AR_planform - AR_aerosandbox| = {ar_delta:.6f}",
                }
            )

    # regeneration checks on a subset
    regen_results: list[dict[str, Any]] = []
    if regen_check_count > 0 and total_rows > 0:
        rng = random.Random(seed)
        chosen = rows[:] if regen_check_count >= total_rows else rng.sample(rows, regen_check_count)

        regen_root = dataset_root / "_audit_regen"
        regen_root.mkdir(parents=True, exist_ok=True)

        for row in chosen:
            gid = row["geometry_id"]
            sample = _sample_from_row(row)

            result = generate_geometry_case_from_sample(
                config=cfg,
                sample=sample,
                output_dir=regen_root / gid,
                save_plot=False,
                build_aerosandbox=True,
            )

            audit = audit_geometry_result(
                planform=result.planform,
                section_geometry=result.section_geometry,
            )

            regen_results.append(
                {
                    "geometry_id": gid,
                    "passed": audit.passed,
                    "errors": audit.errors,
                    "warnings": audit.warnings,
                    "metrics": audit.metrics,
                }
            )

            if not audit.passed:
                error_rows.append(
                    {
                        "geometry_id": gid,
                        "kind": "regen_geometry_audit_failed",
                        "message": "; ".join(audit.errors),
                    }
                )

    report = {
        "dataset_root": str(dataset_root),
        "manifest_status": manifest.get("status"),
        "metadata_rows": total_rows,
        "error_count": len(error_rows),
        "warning_count": len(warning_rows),
        "max_ar_delta": None if not ar_deltas else float(max(ar_deltas)),
        "mean_ar_delta": None if not ar_deltas else float(sum(ar_deltas) / len(ar_deltas)),
        "errors_preview": error_rows[:20],
        "warnings_preview": warning_rows[:20],
        "regen_checked_n": len(regen_results),
        "regen_results_preview": regen_results[:10],
        "passed": len(error_rows) == 0,
    }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit an existing AERIS dataset.")
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Path to dataset root.",
    )
    parser.add_argument(
        "--regen-check-count",
        type=int,
        default=5,
        help="How many random rows to regenerate and audit.",
    )
    args = parser.parse_args()

    report = audit_dataset(
        dataset_root=args.dataset,
        regen_check_count=args.regen_check_count,
    )

    print(json.dumps(report, indent=2))

    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()