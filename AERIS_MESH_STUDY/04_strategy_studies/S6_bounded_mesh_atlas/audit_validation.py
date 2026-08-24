#!/usr/bin/env python3
"""Independently check a completed S6 development-validation report."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

REPORT_SCHEMA = "aeris.mesh.s6_atlas_development_validation.v2"
AUDIT_SCHEMA = "aeris.mesh.s6_atlas_development_report_audit.v2"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def audit_report(report_path: Path, *, expected_count: int | None = None) -> dict[str, Any]:
    """Check report invariants and return a compact, reproducible summary."""
    report_path = Path(report_path).resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    require(report.get("schema") == REPORT_SCHEMA, "unexpected report schema")
    require(
        report.get("campaign_equivalent_written_cgns_audit") is True,
        "written-CGNS audit flag is not true",
    )
    rows = report.get("rows")
    require(isinstance(rows, list), "rows must be a list")
    rows = rows if isinstance(rows, list) else []
    indices = [row.get("geometry_index") for row in rows]
    declared_indices = report.get("geometry_indices", [])
    require(indices == declared_indices, "row indices differ from declared geometry indices")
    require(len(indices) == len(set(indices)), "geometry indices are not unique")
    if expected_count is not None:
        require(len(rows) == expected_count, f"expected {expected_count} rows, found {len(rows)}")
    require(report.get("attempted") == len(rows), "attempted count does not match rows")

    template_indices = set(report.get("template_indices", []))
    candidate_count = int(report.get("candidate_count", 0))
    preferred_quality = float(report.get("preferred_quality", 0.15))
    selected_qualities: list[float] = []
    selected_wall_errors: list[float] = []
    selected_interface_errors: list[float] = []
    selected_fidelity_errors: list[float] = []
    selected_first_layer_min: list[float] = []
    selected_first_layer_p95: list[float] = []
    attempt_state_counts: Counter[str] = Counter()
    selected_template_counts: Counter[int] = Counter()
    preferred_misses: list[int] = []
    total_attempts = 0
    first_try = 0
    total_cells = 0
    cells_below_0_10 = 0
    cells_below_0_15 = 0
    minimum_volume: float | None = None
    identity_target_count = 0
    selected_identity_count = 0

    for row_number, row in enumerate(rows):
        label = f"row {row_number} geometry {row.get('geometry_index')}"
        attempts = row.get("attempts")
        if not isinstance(attempts, list):
            errors.append(f"{label}: attempts must be a list")
            attempts = []
        total_attempts += len(attempts)
        first_try += int(row.get("state") == "PASS" and len(attempts) == 1)
        require(
            candidate_count <= 0 or len(attempts) <= candidate_count,
            f"{label}: attempts exceed candidate_count",
        )
        attempt_state_counts.update(str(item.get("state")) for item in attempts)
        selected = [item for item in attempts if item.get("selected") is True]

        if row.get("state") != "PASS":
            require(not selected, f"{label}: failed row has a selected attempt")
            require(
                row.get("accepted_template_index") is None,
                f"{label}: failed row has an accepted template",
            )
            continue

        require(len(selected) == 1, f"{label}: PASS row must have exactly one selected attempt")
        if len(selected) != 1:
            continue
        attempt = selected[0]
        require(attempt.get("state") == "PASS", f"{label}: selected attempt is not PASS")
        template_index = attempt.get("template_index")
        require(template_index in template_indices, f"{label}: selected template is not in atlas")
        require(
            row.get("accepted_template_index") == template_index,
            f"{label}: accepted template differs from selected attempt",
        )

        quality = attempt.get("min_scaled_quality")
        require(_finite(quality), f"{label}: accepted quality is not finite")
        if _finite(quality):
            quality = float(quality)
            selected_qualities.append(quality)
            require(quality >= 0.10, f"{label}: accepted quality is below 0.10")
            require(
                math.isclose(
                    float(row.get("accepted_min_scaled_quality", float("nan"))),
                    quality,
                    rel_tol=0.0,
                    abs_tol=1.0e-14,
                ),
                f"{label}: row quality differs from selected attempt",
            )
            if quality < preferred_quality:
                preferred_misses.append(int(row["geometry_index"]))

        independent = attempt.get("independent_written_acceptance", {})
        require(
            independent.get("production_floor_passed") is True,
            f"{label}: independent written audit did not pass production floor",
        )
        require(
            independent.get("hard_gate_passed") is True,
            f"{label}: independent written hard gates did not pass",
        )
        independent_quality = independent.get("quality", {}).get("min_scaled_quality")
        require(
            _finite(independent_quality)
            and _finite(quality)
            and math.isclose(
                float(independent_quality),
                float(quality),
                rel_tol=0.0,
                abs_tol=1.0e-14,
            ),
            f"{label}: selected and independent written quality differ",
        )
        written_quality = independent.get("quality", {})
        require(written_quality.get("inverted_cells") == 0, f"{label}: inverted cells remain")
        volume = written_quality.get("min_volume")
        require(_finite(volume) and float(volume) > 0.0, f"{label}: minimum volume is not positive")
        if _finite(volume):
            minimum_volume = (
                float(volume) if minimum_volume is None else min(minimum_volume, float(volume))
            )
        row_total_cells = written_quality.get("total_cells")
        row_below_0_10 = written_quality.get("cells_below_0_10")
        row_below_0_15 = written_quality.get("cells_below_0_15")
        require(
            isinstance(row_total_cells, int) and row_total_cells > 0,
            f"{label}: total cell count is missing or invalid",
        )
        require(row_below_0_10 == 0, f"{label}: cells exist below the hard 0.10 floor")
        require(
            isinstance(row_below_0_15, int) and row_below_0_15 >= 0,
            f"{label}: cells-below-0.15 count is missing or invalid",
        )
        if isinstance(row_total_cells, int):
            total_cells += row_total_cells
        if isinstance(row_below_0_10, int):
            cells_below_0_10 += row_below_0_10
        if isinstance(row_below_0_15, int):
            cells_below_0_15 += row_below_0_15

        fidelity = attempt.get("surface_fidelity", {})
        require(fidelity.get("passed") is True, f"{label}: surface fidelity did not pass")
        fidelity_error = fidelity.get("max_fraction_of_local_chord")
        require(_finite(fidelity_error), f"{label}: surface fidelity value is not finite")
        if _finite(fidelity_error):
            selected_fidelity_errors.append(float(fidelity_error))

        wall_error = attempt.get("wall_error_m")
        interface_error = attempt.get("interface_max_mismatch_m")
        require(_finite(wall_error), f"{label}: wall error is not finite")
        require(_finite(interface_error), f"{label}: interface error is not finite")
        if _finite(wall_error):
            selected_wall_errors.append(float(wall_error))
            require(float(wall_error) <= 1.0e-10, f"{label}: wall error exceeds tolerance")
        if _finite(interface_error):
            selected_interface_errors.append(float(interface_error))
            require(
                float(interface_error) <= 1.0e-10,
                f"{label}: interface mismatch exceeds tolerance",
            )
        require(
            isinstance(attempt.get("interface_pair_count"), int)
            and attempt["interface_pair_count"] > 0,
            f"{label}: interface pair count is missing or invalid",
        )

        spacing = attempt.get("first_layer_spacing", {}).get("deformed", {})
        require(spacing.get("nonfinite_count") == 0, f"{label}: nonfinite first-layer spacing")
        require(spacing.get("nonpositive_count") == 0, f"{label}: nonpositive first-layer spacing")
        for key, values in (
            ("min_fraction_characteristic", selected_first_layer_min),
            ("p95_fraction_characteristic", selected_first_layer_p95),
        ):
            value = spacing.get(key)
            require(_finite(value), f"{label}: {key} is not finite")
            if _finite(value):
                values.append(float(value))

        accepted_hash = row.get("accepted_cgns_sha256")
        require(
            accepted_hash == attempt.get("candidate_cgns_sha256"),
            f"{label}: accepted CGNS hash differs from selected attempt",
        )
        candidate_path = Path(str(row.get("accepted_cgns", "")))
        retained = row.get("accepted_cgns_retained") is True
        if retained:
            require(candidate_path.is_file(), f"{label}: retained CGNS is missing")
            if candidate_path.is_file():
                require(
                    _sha256(candidate_path) == accepted_hash,
                    f"{label}: retained CGNS hash mismatch",
                )
        else:
            require(not candidate_path.exists(), f"{label}: pruned CGNS still exists")
        if isinstance(template_index, int):
            selected_template_counts[template_index] += 1
        identity_target_count += int(row.get("is_atlas_template_target") is True)
        selected_identity_count += int(row.get("selected_identity_deformation") is True)

    passed = sum(row.get("state") == "PASS" for row in rows)
    require(report.get("passed") == passed, "passed count does not match rows")
    expected_fraction = passed / len(rows) if rows else 0.0
    require(
        _finite(report.get("pass_fraction"))
        and math.isclose(float(report["pass_fraction"]), expected_fraction, abs_tol=1.0e-15),
        "pass fraction does not match rows",
    )
    if selected_qualities:
        require(
            math.isclose(
                float(report.get("worst_min_scaled_quality", float("nan"))),
                min(selected_qualities),
                rel_tol=0.0,
                abs_tol=1.0e-14,
            ),
            "reported worst quality does not match selected attempts",
        )

    quality_array = np.asarray(selected_qualities, dtype=float)
    summary = {
        "attempted": len(rows),
        "passed": passed,
        "first_try_passes": first_try,
        "total_template_attempts": total_attempts,
        "maximum_attempts_for_one_target": max(
            (len(row.get("attempts", [])) for row in rows), default=0
        ),
        "preferred_quality_miss_indices": preferred_misses,
        "identity_target_count": identity_target_count,
        "selected_identity_deformation_count": selected_identity_count,
        "attempt_state_counts": dict(sorted(attempt_state_counts.items())),
        "selected_template_counts": {
            str(key): value for key, value in sorted(selected_template_counts.items())
        },
        "quality": {
            "minimum": float(np.min(quality_array)) if quality_array.size else None,
            "p05": float(np.quantile(quality_array, 0.05)) if quality_array.size else None,
            "median": float(np.median(quality_array)) if quality_array.size else None,
            "mean": float(np.mean(quality_array)) if quality_array.size else None,
            "maximum": float(np.max(quality_array)) if quality_array.size else None,
            "minimum_volume": minimum_volume,
            "total_cells_across_selected_meshes": total_cells,
            "cells_below_0_10_across_selected_meshes": cells_below_0_10,
            "cells_below_0_15_across_selected_meshes": cells_below_0_15,
        },
        "maximum_wall_error_m": max(selected_wall_errors, default=None),
        "maximum_interface_mismatch_m": max(selected_interface_errors, default=None),
        "maximum_surface_fidelity_fraction_local_chord": max(
            selected_fidelity_errors, default=None
        ),
        "first_layer_fraction_characteristic": {
            "minimum_over_selected_meshes": min(selected_first_layer_min, default=None),
            "maximum_p95_over_selected_meshes": max(selected_first_layer_p95, default=None),
        },
    }
    integrity_passed = not errors
    all_targets_passed = bool(rows) and passed == len(rows)
    return {
        "schema": AUDIT_SCHEMA,
        "source_report": str(report_path),
        "source_report_sha256": _sha256(report_path),
        "passed": integrity_passed and all_targets_passed,
        "report_integrity_passed": integrity_passed,
        "all_targets_passed": all_targets_passed,
        "errors": errors,
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    audit = audit_report(args.report, expected_count=args.expected_count)
    rendered = json.dumps(audit, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if audit["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
