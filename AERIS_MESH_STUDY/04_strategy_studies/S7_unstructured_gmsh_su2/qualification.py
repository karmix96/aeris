#!/usr/bin/env python3
"""Read-only, development-only qualification reporting for S7.

This module intentionally never calls the campaign runner.  It plans the frozen
study and collects only already-written method-neutral ``case_result.json``
artifacts, so it is safe on laptops and cannot touch the holdout set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

try:  # package import and direct ``python qualification.py`` are both useful
    from .common import (
        POLICY_PATH,
        SUMMARY_SCHEMA,
        canonical_json,
        load_policy,
        read_json,
        sha256_file,
        source_digest,
        verify_digest_manifest,
        write_json,
    )
except ImportError:  # pragma: no cover - CLI convenience
    from common import (
        POLICY_PATH,
        SUMMARY_SCHEMA,
        canonical_json,
        load_policy,
        read_json,
        sha256_file,
        source_digest,
        verify_digest_manifest,
        write_json,
    )


PLAN_SCHEMA = "aeris.s7.qualification_plan.v1"
SUMMARY_SCHEMA_QUALIFICATION = "aeris.s7.qualification_summary.v1"
DEVELOPMENT_SET = "lhs100_seed42"
# These span the canonical 100-case ordering; they are fixed, not selected from results.
REPRESENTATIVE_INDICES = (0, 24, 49, 74, 99)
BASELINE_TE = "te_1p0mm"
COUPLED_COUNT_FIELDS = (
    "surface_triangles",
    "prisms",
    "tetrahedra",
    "volume_cells",
)


def _canonical_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _force_fields(policy: Mapping[str, Any]) -> tuple[str, ...]:
    fields = tuple(str(x) for x in policy["grid_family"]["grid_convergence"]["force_fields"])
    if not fields or len(set(fields)) != len(fields):
        raise ValueError("policy grid-convergence force_fields must be a non-empty unique list")
    return fields


def build_qualification_plan() -> dict[str, Any]:
    """Return the immutable S7 development qualification plan, without I/O."""
    policy = load_policy()
    levels = tuple(policy["grid_family"]["levels"])
    if levels != ("coarse", "medium", "fine"):
        raise ValueError(
            "S7 qualification requires policy levels coarse, medium, fine in that order"
        )
    if int(policy["grid_family"]["representative_grid_cases"]) != len(REPRESENTATIVE_INDICES):
        raise ValueError(
            "policy representative-grid count does not match the frozen five-case plan"
        )
    variants = tuple(policy["geometry"]["trailing_edge_variants"])
    required_variants = ("te_0p5mm", "te_1p0mm", "te_1p5mm")
    if variants != required_variants:
        raise ValueError("S7 qualification requires exactly the frozen three TE variants")
    return {
        "schema": PLAN_SCHEMA,
        "strategy": "S7_UNSTRUCTURED_GMSH_SU2",
        "mode": "read_only_collection_only",
        "development_set": str(policy["data"]["development_set"]),
        "holdout_accessed": False,
        "representative_indices": list(REPRESENTATIVE_INDICES),
        "grid_study": {
            "levels": list(levels),
            "te_variant": BASELINE_TE,
            "cases": [
                {"index": index, "levels": list(levels), "te_variant": BASELINE_TE}
                for index in REPRESENTATIVE_INDICES
            ],
        },
        "trailing_edge_study": {
            "grid_level": "medium",
            "variants": list(required_variants),
            "cases": [
                {"index": index, "grid_level": "medium", "variants": list(required_variants)}
                for index in REPRESENTATIVE_INDICES
            ],
        },
        "force_fields": list(_force_fields(policy)),
        "effective_h": "actual_volume_cells**(-1/3)",
        "policy_sha256": sha256_file(POLICY_PATH),
        "plan_digest": None,
        "limitations": ["No cases are launched.", "No holdout paths or artifacts are read."],
    }


def write_plan(path: Path) -> dict[str, Any]:
    plan = build_qualification_plan()
    plan["plan_digest"] = _canonical_digest({k: v for k, v in plan.items() if k != "plan_digest"})
    write_json(path, plan)
    return plan


def _finite(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _cell_count(result: Mapping[str, Any]) -> int | None:
    counts = result.get("cell_counts")
    if not isinstance(counts, Mapping):
        return None
    value = _finite(counts.get("volume_cells", counts.get("total_cells")))
    if value is None or value <= 0 or value != int(value):
        return None
    return int(value)


def _coupled_counts(result: Mapping[str, Any]) -> dict[str, int] | None:
    counts = result.get("cell_counts")
    if not isinstance(counts, Mapping):
        return None
    resolved: dict[str, int] = {}
    for name in COUPLED_COUNT_FIELDS:
        value = _finite(counts.get(name))
        if value is None or value <= 0 or value != int(value):
            return None
        resolved[name] = int(value)
    if resolved["prisms"] + resolved["tetrahedra"] != resolved["volume_cells"]:
        return None
    return resolved


def _result_errors(result: Mapping[str, Any], policy: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if result.get("schema") != SUMMARY_SCHEMA:
        errors.append("wrong_summary_schema")
    if result.get("geometry_set") != policy["data"]["development_set"]:
        errors.append("not_development_set")
    if result.get("method") != "unstructured":
        errors.append("wrong_method")
    if not result.get("geometry_id"):
        errors.append("missing_geometry_id")
    if not result.get("geometry_digest"):
        errors.append("missing_geometry_digest")
    if result.get("accepted") is not True:
        errors.append("not_accepted")
    if result.get("technical_accepted") is not True:
        errors.append("technical_gates_not_accepted")
    if result.get("acceptance_scope") != "mesh_and_cfd":
        errors.append("not_mesh_and_cfd_acceptance")
    if result.get("grid_level") not in policy["grid_family"]["levels"]:
        errors.append("unknown_grid_level")
    if result.get("te_variant") not in policy["geometry"]["trailing_edge_variants"]:
        errors.append("unknown_te_variant")
    if _cell_count(result) is None:
        errors.append("missing_or_invalid_actual_volume_cells")
    if _coupled_counts(result) is None:
        errors.append("missing_or_invalid_coupled_cell_counts")
    baseline_flow = policy["flow_conditions"]["baseline"]
    if result.get("flow_id") != baseline_flow["flow_id"]:
        errors.append("wrong_flow_id")
    observed_flow = result.get("flow_condition")
    if not isinstance(observed_flow, Mapping):
        errors.append("missing_flow_condition")
    else:
        for name in policy["flow_conditions"]["required_fields"]:
            observed = observed_flow.get(name)
            expected = baseline_flow[name]
            if isinstance(expected, str):
                matches = observed == expected
            else:
                matches = _finite(observed) == float(expected)
            if not matches:
                errors.append(f"flow_condition_mismatch_{name}")
    y_plus = result.get("y_plus")
    if not isinstance(y_plus, Mapping) or y_plus.get("passed") is not True:
        errors.append("wall_yplus_not_passed")
    provenance = result.get("provenance")
    if not isinstance(provenance, Mapping):
        errors.append("missing_provenance")
    else:
        for field in ("policy_sha256", "source_digest", "tool_versions"):
            if not provenance.get(field):
                errors.append(f"missing_provenance_{field}")
        if provenance.get("policy_sha256") != sha256_file(POLICY_PATH):
            errors.append("policy_provenance_mismatch")
        if provenance.get("source_digest") != source_digest():
            errors.append("source_provenance_mismatch")
        pinned = provenance.get("pinned_versions")
        if not isinstance(pinned, Mapping) or pinned.get("passed") is not True:
            errors.append("software_version_preflight_not_passed")
    forces = result.get("forces")
    if not isinstance(forces, Mapping):
        errors.append("missing_forces")
    else:
        for field in _force_fields(policy):
            if _finite(forces.get(field)) is None:
                errors.append(f"missing_or_nonfinite_force_{field}")
    references = result.get("reference_quantities")
    if not isinstance(references, Mapping) or set(references) != {
        "area_ref",
        "chord_ref",
        "moment_origin",
    }:
        errors.append("missing_or_invalid_reference_quantities")
    else:
        origin = references.get("moment_origin")
        if (
            _finite(references.get("area_ref")) is None
            or _finite(references.get("chord_ref")) is None
            or not isinstance(origin, (list, tuple))
            or len(origin) != 3
            or any(_finite(value) is None for value in origin)
        ):
            errors.append("missing_or_nonfinite_reference_quantities")
    return errors


def _terminal_errors(path: Path, result: Mapping[str, Any]) -> list[str]:
    terminal_path = Path(path).with_name("case_terminal.json")
    if not terminal_path.is_file():
        return ["missing_case_terminal"]
    try:
        terminal = read_json(terminal_path)
    except Exception as exc:
        return [f"unreadable_case_terminal:{type(exc).__name__}"]
    errors: list[str] = []
    if terminal.get("schema") != "aeris.s7.case_terminal.v1":
        errors.append("wrong_case_terminal_schema")
    if terminal.get("case_id") != result.get("case_id"):
        errors.append("case_terminal_identity_mismatch")
    if terminal.get("source_digest") != source_digest():
        errors.append("case_terminal_source_mismatch")
    if terminal.get("policy_sha256") != sha256_file(POLICY_PATH):
        errors.append("case_terminal_policy_mismatch")
    if terminal.get("accepted") != result.get("accepted"):
        errors.append("case_terminal_acceptance_mismatch")
    if terminal.get("acceptance_scope") != result.get("acceptance_scope"):
        errors.append("case_terminal_scope_mismatch")
    manifest = terminal.get("artifact_manifest")
    if not isinstance(manifest, Mapping):
        errors.append("missing_case_terminal_manifest")
        return errors
    verification = verify_digest_manifest(manifest)
    if not verification["passed"]:
        errors.append("case_terminal_artifact_verification_failed")
    result_record = manifest.get("artifacts", {}).get("case_result")
    if (
        not isinstance(result_record, Mapping)
        or Path(str(result_record.get("path", ""))).resolve() != Path(path).resolve()
    ):
        errors.append("case_terminal_result_path_mismatch")
    return errors


def _observed_order(
    coarse: float, medium: float, fine: float, h_coarse: float, h_medium: float, h_fine: float
) -> dict[str, Any]:
    """Solve unequal-grid Richardson order, declining invalid sequences explicitly."""
    dc, df = coarse - medium, medium - fine
    if not all(math.isfinite(x) for x in (coarse, medium, fine, h_coarse, h_medium, h_fine)):
        return {"status": "undefined_nonfinite_input"}
    if not h_coarse > h_medium > h_fine > 0:
        return {"status": "undefined_nonmonotonic_effective_h"}
    if dc == 0 or df == 0 or dc * df <= 0:
        return {"status": "non_asymptotic_nonmonotonic_solution"}
    observed = abs(dc / df)
    r32, r21 = h_coarse / h_medium, h_medium / h_fine

    def ratio(p: float) -> float:
        # For phi(h) = phi_exact + C h**p, the unequal-grid difference
        # ratio is (phi_3-phi_2)/(phi_2-phi_1).  The r21**p factor is
        # essential when the two refinement ratios differ.
        return r21**p * (r32**p - 1.0) / (r21**p - 1.0)

    # positive p is the only physically useful Richardson order here
    lo, hi = 1.0e-8, 50.0
    f_lo = ratio(lo) - observed
    f_hi = ratio(hi) - observed
    if not math.isfinite(f_lo) or not math.isfinite(f_hi) or f_lo * f_hi > 0.0:
        return {"status": "non_asymptotic_no_positive_order", "solution_ratio": observed}
    for _ in range(100):
        mid = (lo + hi) / 2.0
        f_mid = ratio(mid) - observed
        if f_lo * f_mid <= 0.0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    p = (lo + hi) / 2.0
    denom = r21**p - 1.0
    coarse_denom = r32**p - 1.0
    if denom <= 0 or coarse_denom <= 0 or fine == 0 or medium == 0:
        return {"status": "undefined_gci_denominator", "observed_order": p}
    gci_fine = 1.25 * abs((fine - medium) / fine) / denom * 100.0
    gci_medium = 1.25 * abs((medium - coarse) / medium) / coarse_denom * 100.0
    asymptotic_ratio = gci_medium / (r21**p * gci_fine) if gci_fine else None
    if not all(math.isfinite(value) for value in (p, gci_fine, gci_medium, asymptotic_ratio)):
        return {"status": "undefined_nonfinite_gci", "observed_order": p}
    return {
        "status": "ok",
        "observed_order": p,
        "gci_fine_percent": gci_fine,
        "gci_medium_percent": gci_medium,
        "asymptotic_ratio": asymptotic_ratio,
    }


def _grid_report(
    rows: Mapping[tuple[int, str, str], Mapping[str, Any]], policy: Mapping[str, Any]
) -> dict[str, Any]:
    minimum_ratio = float(policy["grid_family"]["minimum_cell_count_ratio_between_levels"])
    tolerance = float(policy["grid_family"]["grid_convergence"]["asymptotic_ratio_tolerance"])
    report: dict[str, Any] = {}
    for index in REPRESENTATIVE_INDICES:
        cases = [rows.get((index, level, BASELINE_TE)) for level in ("coarse", "medium", "fine")]
        if any(case is None for case in cases):
            report[str(index)] = {
                "status": "missing_evidence",
                "missing_levels": [
                    level
                    for level, case in zip(("coarse", "medium", "fine"), cases, strict=True)
                    if case is None
                ],
            }
            continue
        count_records = [_coupled_counts(case) for case in cases]
        if any(record is None for record in count_records):
            report[str(index)] = {"status": "missing_or_invalid_coupled_cell_counts"}
            continue
        geometry_ids = {str(case.get("geometry_id", "")) for case in cases}
        flow_identities = {
            json.dumps(case.get("flow_condition"), sort_keys=True, separators=(",", ":"))
            for case in cases
        }
        reference_identities = {
            json.dumps(case.get("reference_quantities"), sort_keys=True, separators=(",", ":"))
            for case in cases
        }
        if (
            len(geometry_ids) != 1
            or "" in geometry_ids
            or len(flow_identities) != 1
            or len(reference_identities) != 1
        ):
            report[str(index)] = {
                "status": "invalid_mixed_geometry_or_flow",
                "geometry_ids": sorted(geometry_ids),
                "flow_identity_count": len(flow_identities),
                "reference_identity_count": len(reference_identities),
            }
            continue
        coupled = {
            field: [int(record[field]) for record in count_records]
            for field in COUPLED_COUNT_FIELDS
        }
        counts = coupled["volume_cells"]
        components_monotonic = all(values[0] < values[1] < values[2] for values in coupled.values())
        if not (
            components_monotonic
            and counts[1] / counts[0] >= minimum_ratio
            and counts[2] / counts[1] >= minimum_ratio
        ):
            report[str(index)] = {
                "status": "invalid_nonmonotonic_coupled_cell_counts",
                "actual_counts": coupled,
                "minimum_volume_cell_ratio": minimum_ratio,
            }
            continue
        hs = [count ** (-1.0 / 3.0) for count in counts]
        forces = {}
        failed_fields: list[str] = []
        gci_limits = policy["grid_family"]["grid_convergence"]["max_fine_gci_percent"]
        for field in _force_fields(policy):
            metric = _observed_order(*[_finite(case["forces"][field]) for case in cases], *hs)
            if metric.get("status") == "ok":
                asymptotic_ratio = _finite(metric.get("asymptotic_ratio"))
                if asymptotic_ratio is None:
                    metric["status"] = "undefined_nonfinite_asymptotic_ratio"
                elif abs(asymptotic_ratio - 1.0) > tolerance:
                    metric["status"] = "non_asymptotic_gci_ratio"
            if metric.get("status") == "ok":
                limit = _finite(gci_limits.get(field))
                if limit is None:
                    metric["status"] = "undefined_missing_policy_gci_limit"
                elif float(metric["gci_fine_percent"]) > limit:
                    metric["status"] = "failed_fine_gci_limit"
                    metric["fine_gci_limit_percent"] = limit
            if metric.get("status") != "ok":
                failed_fields.append(field)
            forces[field] = metric
        report[str(index)] = {
            "status": "passed" if not failed_fields else "failed_grid_convergence",
            "actual_volume_cells": counts,
            "actual_coupled_counts": coupled,
            "effective_h": hs,
            "forces": forces,
            "failed_fields": failed_fields,
        }
    return report


def collect_qualification(
    result_paths: Iterable[Path], *, output: Path | None = None
) -> dict[str, Any]:
    """Collect existing S7 results only; no runner, mesher, solver, or holdout access."""
    policy = load_policy()
    records, rejected, selected = [], [], {}
    for path in sorted({Path(p) for p in result_paths}, key=str):
        try:
            result = read_json(path)
        except Exception as exc:
            rejected.append({"path": str(path), "errors": [f"unreadable:{type(exc).__name__}"]})
            continue
        errors = [*_result_errors(result, policy), *_terminal_errors(path, result)]
        if errors:
            rejected.append({"path": str(path), "case_id": result.get("case_id"), "errors": errors})
            continue
        index_text = str(result.get("case_id", "")).split("__", 1)[0].removeprefix("dev_")
        try:
            index = int(index_text)
        except ValueError:
            rejected.append(
                {
                    "path": str(path),
                    "case_id": result.get("case_id"),
                    "errors": ["unparseable_development_index"],
                }
            )
            continue
        if index not in REPRESENTATIVE_INDICES:
            rejected.append(
                {
                    "path": str(path),
                    "case_id": result.get("case_id"),
                    "errors": ["out_of_plan_case_result"],
                }
            )
            continue
        if result.get("development_index") != index:
            rejected.append(
                {
                    "path": str(path),
                    "case_id": result.get("case_id"),
                    "errors": ["development_index_identity_mismatch"],
                }
            )
            continue
        expected_case_id = (
            f"dev_{index:03d}__{result['grid_level']}__{result['te_variant']}__cruise"
        )
        if result.get("case_id") != expected_case_id:
            rejected.append(
                {
                    "path": str(path),
                    "case_id": result.get("case_id"),
                    "errors": ["case_id_identity_mismatch"],
                }
            )
            continue
        key = (index, str(result["grid_level"]), str(result["te_variant"]))
        if key in selected:
            rejected.append(
                {
                    "path": str(path),
                    "case_id": result.get("case_id"),
                    "errors": ["duplicate_case_result"],
                }
            )
            continue
        selected[key] = result
        records.append(
            {
                "path": str(path),
                "case_id": result["case_id"],
                "actual_volume_cells": _cell_count(result),
            }
        )
    grid = _grid_report(selected, policy)
    te: dict[str, Any] = {}
    for index in REPRESENTATIVE_INDICES:
        variants = {
            variant: selected.get((index, "medium", variant))
            for variant in ("te_0p5mm", "te_1p0mm", "te_1p5mm")
        }
        unavailable = [variant for variant, row in variants.items() if row is None]
        if unavailable:
            te[str(index)] = {
                "status": "unavailable_missing_case_result",
                "grid_level": "medium",
                "unavailable_variants": unavailable,
            }
            continue
        geometry_ids = {str(row.get("geometry_id", "")) for row in variants.values()}
        flow_identities = {
            json.dumps(row.get("flow_condition"), sort_keys=True, separators=(",", ":"))
            for row in variants.values()
        }
        reference_identities = {
            json.dumps(row.get("reference_quantities"), sort_keys=True, separators=(",", ":"))
            for row in variants.values()
        }
        if (
            len(geometry_ids) != 1
            or "" in geometry_ids
            or len(flow_identities) != 1
            or len(reference_identities) != 1
        ):
            te[str(index)] = {
                "status": "invalid_mixed_geometry_or_flow",
                "grid_level": "medium",
                "geometry_ids": sorted(geometry_ids),
                "flow_identity_count": len(flow_identities),
                "reference_identity_count": len(reference_identities),
            }
            continue
        baseline = variants[BASELINE_TE]
        fields: dict[str, Any] = {}
        for field in _force_fields(policy):
            reference = _finite(baseline.get("forces", {}).get(field))
            if reference is None:
                fields[field] = {"status": "unavailable_nonfinite_baseline"}
                continue
            deltas: dict[str, Any] = {}
            for variant, row in variants.items():
                if variant == BASELINE_TE:
                    continue
                value = _finite(row.get("forces", {}).get(field))
                if value is None:
                    deltas[variant] = {"status": "unavailable_nonfinite_variant"}
                else:
                    change = value - reference
                    deltas[variant] = {
                        "status": "available",
                        "absolute_delta": change,
                        "relative_delta": change / max(abs(reference), 1.0e-30),
                    }
            fields[field] = {
                "status": "available",
                "baseline": reference,
                "deltas": deltas,
            }
        te[str(index)] = {
            "status": "complete",
            "grid_level": "medium",
            "baseline_variant": BASELINE_TE,
            "fields": fields,
        }
    grid_passed_count = sum(row.get("status") == "passed" for row in grid.values())
    summary = {
        "schema": SUMMARY_SCHEMA_QUALIFICATION,
        "mode": "collected_existing_results_only",
        "holdout_accessed": False,
        "policy_sha256": sha256_file(POLICY_PATH),
        "force_fields": list(_force_fields(policy)),
        "accepted_records": records,
        "rejected_records": rejected,
        "grid_convergence": grid,
        "grid_studies_passed": grid_passed_count,
        "grid_studies_required": len(REPRESENTATIVE_INDICES),
        "grid_readiness": "passed"
        if grid_passed_count == len(REPRESENTATIVE_INDICES)
        else "failed_or_incomplete",
        "trailing_edge_sensitivity": te,
    }
    if output is not None:
        write_json(output, summary)
    return summary


def compare_summaries(s6: Mapping[str, Any] | Path, s7: Mapping[str, Any] | Path) -> dict[str, Any]:
    """Compare supplied summaries only when their scientific bases are explicit."""

    def load(value: Mapping[str, Any] | Path) -> Mapping[str, Any]:
        return read_json(value) if isinstance(value, Path) else value

    def evidence(summary: Mapping[str, Any], key: str) -> Any:
        return summary.get(key) if key in summary else {"status": "missing_evidence"}

    left, right = load(s6), load(s7)
    basis_left = left.get("comparison_basis")
    basis_right = right.get("comparison_basis")
    reasons: list[str] = []
    required_basis = (
        "geometry_set",
        "case_ids",
        "flow_condition",
        "full_wing_normalization",
        "force_reference",
    )
    for method, basis in (("S6", basis_left), ("S7", basis_right)):
        if not isinstance(basis, Mapping):
            reasons.append(f"{method}:missing_comparison_basis")
            continue
        for field in required_basis:
            if field not in basis:
                reasons.append(f"{method}:missing_basis_{field}")
        if basis.get("full_wing_normalization") is not True:
            reasons.append(f"{method}:not_full_wing_normalized")
    if isinstance(basis_left, Mapping) and isinstance(basis_right, Mapping):
        for field in ("geometry_set", "case_ids", "flow_condition", "force_reference"):
            if canonical_json(basis_left.get(field)) != canonical_json(basis_right.get(field)):
                reasons.append(f"basis_mismatch:{field}")
    keys = ("robustness", "cells", "runtime", "y_plus", "forces")
    metrics: dict[str, Any] = {}
    for key in keys:
        missing = [
            method for method, summary in (("S6", left), ("S7", right)) if key not in summary
        ]
        if reasons:
            metrics[key] = {
                "status": "incompatible_evidence",
                "reasons": reasons,
            }
        elif missing:
            metrics[key] = {"status": "missing_evidence", "missing": missing}
        else:
            metrics[key] = {
                "status": "comparable_side_by_side",
                "S6": left[key],
                "S7": right[key],
            }
    return {
        "schema": "aeris.mesh.method_comparison.v1",
        "comparison_is_not_a_selection": True,
        "comparability": {
            "status": "compatible" if not reasons else "incompatible_evidence",
            "reasons": reasons,
        },
        "metrics": metrics,
        "S6": {key: evidence(left, key) for key in keys},
        "S7": {key: evidence(right, key) for key in keys},
        "missing_evidence_is_not_zero_or_a_pass": True,
    }


def main() -> int:  # pragma: no cover - small CLI wrapper
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--output", type=Path, required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("results", type=Path, nargs="+")
    collect.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "plan":
        write_plan(args.output)
    else:
        collect_qualification(args.results, output=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
