"""Execute independently reproducible structural sensitivity variants."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from aeris.common.config import file_sha256
from aeris.fea.case.runner import CaseError, run_case
from aeris.fea.case.spec import CaseSpec
from aeris.fea.study.loader import build_variant_case_spec
from aeris.fea.study.spec import StudySpec


def _metrics(run_dir: Path) -> dict[str, float]:
    path = run_dir / "verification.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    loads = payload.get("loads", {})
    mesh_path = run_dir / "mesh" / "mesh_report.json"
    mesh = json.loads(mesh_path.read_text(encoding="utf-8")) if mesh_path.is_file() else {}
    result = {
        "full_structural_mass_kg": float(payload["full_structural_mass_kg"]),
        "element_count": float(mesh.get("element_count", 0)),
        "node_count": float(mesh.get("node_count", 0)),
    }
    if isinstance(loads, dict) and loads:
        result["max_displacement_m"] = max(float(v["max_displacement_m"]) for v in loads.values())
        result["max_von_mises_pa"] = max(float(v["max_von_mises_pa"]) for v in loads.values())
        result["minimum_safety_factor"] = min(
            float(v["safety_factor_yield"]) for v in loads.values()
        )
    return result


def _convergence(study: StudySpec, rows: list[dict[str, object]]) -> dict[str, object] | None:
    if not study.convergence.enabled:
        return None
    if any(row.get("status") != "ok" for row in rows):
        return {"status": "fail", "reason": "one or more mesh levels did not pass"}
    ordered = sorted(rows, key=lambda row: float(row["metrics"]["element_count"]))  # type: ignore[index]
    medium, fine = ordered[-2:]
    medium_metrics = medium["metrics"]
    fine_metrics = fine["metrics"]
    assert isinstance(medium_metrics, dict) and isinstance(fine_metrics, dict)
    tolerances = {
        "max_displacement_m": study.convergence.maximum_displacement_relative_change,
        "max_von_mises_pa": study.convergence.maximum_stress_relative_change,
        "full_structural_mass_kg": study.convergence.maximum_mass_relative_change,
    }
    changes = {
        name: abs(float(fine_metrics[name]) - float(medium_metrics[name]))
        / max(abs(float(fine_metrics[name])), 1e-30)
        for name in tolerances
    }
    checks = {name: changes[name] <= limit for name, limit in tolerances.items()}
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "coarse_to_fine": [str(row["name"]) for row in ordered],
        "element_counts": [int(row["metrics"]["element_count"]) for row in ordered],  # type: ignore[index]
        "medium_to_fine_relative_change": changes,
        "tolerances": tolerances,
        "checks": checks,
        "note": "A passed change gate establishes mesh stability, not model-form validity.",
    }


def run_study(
    study: StudySpec,
    *,
    workdir: Path,
    dry_run: bool = False,
    echo: Callable[[str], None] | None = None,
    prepare: Callable[[CaseSpec, Path], CaseSpec] | None = None,
) -> dict[str, object]:
    say = echo or (lambda _message: None)
    root = workdir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for variant in study.variants:
        variant_dir = root / variant.name
        try:
            spec = build_variant_case_spec(study, variant)
            if prepare is not None:
                spec = prepare(spec, variant_dir)
            run_case(
                spec,
                workdir=variant_dir,
                stages=study.stages,
                dry_run=dry_run,
                echo=say,
            )
            verification = variant_dir / "verification.json"
            status = (
                "dry_run"
                if dry_run
                else (
                    "ok"
                    if verification.is_file()
                    and json.loads(verification.read_text(encoding="utf-8")).get("status") == "pass"
                    else "failed"
                )
            )
            rows.append({"name": variant.name, "status": status, "metrics": _metrics(variant_dir)})
        except (ValueError, CaseError, OSError) as exc:
            rows.append(
                {"name": variant.name, "status": "failed", "metrics": {}, "error": str(exc)}
            )

    baseline_row = next((row for row in rows if row["name"] == study.baseline), None)
    baseline_metrics = baseline_row.get("metrics", {}) if baseline_row else {}
    deltas: dict[str, object] = {}
    if isinstance(baseline_metrics, dict) and baseline_metrics:
        for row in rows:
            metrics = row.get("metrics", {})
            if row["name"] == study.baseline or not isinstance(metrics, dict):
                continue
            deltas[str(row["name"])] = {
                key: float(value) - float(baseline_metrics[key])
                for key, value in metrics.items()
                if key in baseline_metrics
            }
    convergence = _convergence(study, rows)
    payload = {
        "schema": "aeris.fea.study_report.v1",
        "status": (
            "fail"
            if any(row["status"] == "failed" for row in rows)
            or (convergence is not None and convergence.get("status") != "pass")
            else "pass"
        ),
        "study": study.name,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "study_yaml": str(study.source_path) if study.source_path else None,
        "study_yaml_sha256": file_sha256(study.source_path) if study.source_path else None,
        "baseline": study.baseline,
        "variants": rows,
        "deltas_vs_baseline": deltas,
        "mesh_convergence": convergence,
    }
    (root / "study_report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload
