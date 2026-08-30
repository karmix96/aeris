"""The governed S6 route: the study's own atlas path, driven from the interface.

The old workbench had ONE mesh button and it marched pyHyp directly on the
surface the geometry tab had built.  That is a useful development tool and a
misleading one, because it is not what S6 does.  S6 does not march a new volume
per design: it ranks FROZEN templates by design distance, deforms the nearest
one onto the exact target surface, audits the deformation, writes the CGNS,
REOPENS it and audits it again, and only then calls the mesh accepted.  A direct
march skips every one of those steps, and a direct march presented as an S6
result is evidence of nothing.

So there are two modes now and they are labelled.  This module is the governed
one, and it does not reimplement any of the above - it calls
`campaign.make_manifest`, `campaign.mesh_case` and `campaign.solve_case`, which
carry template ranking, the automatic target-specific fallback, the written-CGNS
re-audit, the production floor and the CFD gates.  What it adds is the part a
batch job does not need: finding out whether the artifacts exist at all, and
turning the study's reports into something a person can read.

When the artifacts are missing the mode is DISABLED and says what is missing.
It never falls back to the direct march - that would be the original problem
wearing a governed label.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .environment import (
    REPO_ROOT,
    S6_CAMPAIGN_ROOT,
    S6_DIR,
    S6_FLOWS_CSV,
    S6_REGISTRY,
    STRATEGY_DIR,
)

for _path in (str(REPO_ROOT / "src"), str(STRATEGY_DIR), str(S6_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

GOVERNED = "governed"
EXPERIMENTAL = "experimental"
MODES = (GOVERNED, EXPERIMENTAL)
MODE_LABELS = {
    GOVERNED: "Governed S6 Atlas",
    EXPERIMENTAL: "Experimental direct pyHyp march",
}
MODE_HELP = {
    GOVERNED: ("The evidence path. Ranks frozen atlas templates by design "
               "distance, deforms the nearest onto this exact surface, audits "
               "the written CGNS and applies S6's production floor."),
    EXPERIMENTAL: ("Development only. Marches pyHyp directly on the structured "
                   "surface. No atlas, no deformation, no S6 acceptance - the "
                   "result is a mesh to look at, not evidence."),
}


@dataclass
class Availability:
    """Whether the governed route can run, and precisely what is missing."""

    available: bool = False
    registry_path: Path | None = None
    registry_status: str = ""
    template_count: int = 0
    volume_level: str = ""
    eps_e: float | None = None
    first_cell_fraction: float | None = None
    production_floor: float | None = None
    preferred_quality: float | None = None
    flows_path: Path | None = None
    campaign_root: Path | None = None
    missing: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.available:
            return (f"{self.template_count} frozen templates, volume level "
                    f"{self.volume_level}, status {self.registry_status}")
        return "; ".join(self.missing) or "not configured"

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "registry": str(self.registry_path) if self.registry_path else "",
            "registry_status": self.registry_status,
            "template_count": self.template_count,
            "volume_level": self.volume_level,
            "eps_e": self.eps_e,
            "first_cell_fraction": self.first_cell_fraction,
            "production_floor": self.production_floor,
            "preferred_quality": self.preferred_quality,
            "flows": str(self.flows_path) if self.flows_path else "",
            "campaign_root": str(self.campaign_root) if self.campaign_root else "",
            "missing": list(self.missing),
            "summary": self.summary(),
        }


def availability(*, registry_path: Path | None = None,
                 flows_path: Path | None = None,
                 campaign_root: Path | None = None) -> Availability:
    """Ask the study's own verifier whether its artifacts are usable.

    `campaign.verify_registry` resolves every template asset and re-hashes it,
    so this is not a file-existence check dressed up as one: a registry whose
    CGNS has been moved, truncated or regenerated fails here rather than half
    way through a mesh.
    """
    registry_path = Path(registry_path or S6_REGISTRY)
    flows_path = Path(flows_path or S6_FLOWS_CSV)
    campaign_root = Path(campaign_root or S6_CAMPAIGN_ROOT)
    found = Availability(registry_path=registry_path, flows_path=flows_path,
                         campaign_root=campaign_root)

    if not registry_path.is_file():
        found.missing.append(
            f"template registry not found at {registry_path} (set S6_REGISTRY, or "
            "build one with campaign.py build-registry)")
    if not flows_path.is_file():
        found.missing.append(
            f"flow definitions not found at {flows_path} (set S6_FLOWS_CSV)")
    if found.missing:
        return found

    try:
        import campaign  # noqa: PLC0415

        campaign.verify_registry(registry_path)
        registry = campaign._read_json(registry_path)
    except Exception as error:  # noqa: BLE001 - the reason is what the user needs
        found.missing.append(f"{type(error).__name__}: {error}")
        return found

    found.available = True
    found.registry_status = str(registry.get("registry_status", ""))
    found.template_count = int(registry.get("template_count", 0))
    found.volume_level = str(registry.get("volume_level", ""))
    found.eps_e = float(registry["eps_e"]) if "eps_e" in registry else None
    found.first_cell_fraction = (
        float(registry["first_cell_fraction_characteristic"])
        if "first_cell_fraction_characteristic" in registry else None)
    found.production_floor = (
        float(registry["production_floor"]) if "production_floor" in registry else None)
    found.preferred_quality = (
        float(registry["preferred_quality"]) if "preferred_quality" in registry else None)
    return found


def write_designs_csv(values: dict[str, float], design_id: str, path: Path) -> Path:
    """One design, in the CSV shape `campaign.make_manifest` reads.

    Going through the CSV rather than hand-building a manifest dict is
    deliberate: `make_manifest` is where design normalisation, the mesh-distance
    variable list and the input hashes are decided, and a manifest assembled any
    other way would be missing exactly the provenance the governed route relies
    on.
    """
    from shared.geometry_sets import _config as study_config  # noqa: PLC0415

    names = study_config().active_design_variable_names()
    missing = [name for name in names if name not in values]
    if missing:
        raise ValueError(f"design is missing required variables: {missing}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["design_id", *names])
        writer.writerow([design_id, *(float(values[name]) for name in names)])
    return path


def design_values_for_campaign(case: Any) -> dict[str, float]:
    """The design in the sign convention the campaign stores.

    The sliders show sweeps as positive magnitudes and the sample stores them
    negative-aft, so handing slider values straight to `make_manifest` would
    describe a forward-swept aircraft and rank templates against it.
    """
    from . import geometry as geo  # noqa: PLC0415

    values = dict(case.values)
    for key in geo.SWEEP_VARIABLES:
        if key in values:
            values[key] = -abs(float(values[key]))
    return values


def prepare_manifest(case: Any, run_dir: Path, *,
                     flows_path: Path | None = None) -> tuple[Path, dict[str, Any]]:
    """A one-design campaign manifest for this exact geometry."""
    import campaign  # noqa: PLC0415

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    designs_csv = write_designs_csv(
        design_values_for_campaign(case), case.geometry_id, run_dir / "designs.csv")
    manifest_path = run_dir / "campaign_manifest.json"
    manifest = campaign.make_manifest(
        designs_csv, Path(flows_path or S6_FLOWS_CSV), manifest_path)
    return manifest_path, manifest


def mesh(case: Any, run_dir: Path, *, registry_path: Path | None = None,
         flows_path: Path | None = None, campaign_root: Path | None = None,
         max_templates: int = 0, allow_remesh: bool = True,
         remesh_timeout_s: float = 3600.0, log: Any = None) -> dict[str, Any]:
    """Mesh one design through S6's own campaign, unmodified.

    `allow_remesh` is S6's automatic target-specific fallback: when no frozen
    template reaches the preferred quality, the campaign marches a fresh S1
    surface for this design and deforms THAT.  It is part of the governed route,
    not an escape from it - the fallback mesh goes through the same written-CGNS
    audit and the same production floor as any template.
    """
    import campaign  # noqa: PLC0415

    found = availability(registry_path=registry_path, flows_path=flows_path,
                         campaign_root=campaign_root)
    if not found.available:
        raise RuntimeError(
            "the governed S6 atlas is unavailable: " + found.summary())

    run_dir = Path(run_dir)
    manifest_path, manifest = prepare_manifest(case, run_dir, flows_path=found.flows_path)
    if log:
        log(f"Governed S6: registry {found.registry_path.name} "
            f"({found.template_count} templates, volume level {found.volume_level})")
        log(f"Governed S6: manifest {manifest_path.name}, "
            f"{manifest['counts']['cases']} case(s)")

    report = campaign.mesh_case(
        manifest_path=manifest_path,
        registry_path=Path(found.registry_path),
        campaign_root=run_dir / "campaign",
        case_index=0,
        max_templates=int(max_templates),
        allow_remesh=bool(allow_remesh),
        remesh_timeout_s=float(remesh_timeout_s),
    )
    report["workbench_manifest"] = str(manifest_path)
    report["workbench_campaign_root"] = str(run_dir / "campaign")
    report["workbench_registry"] = str(found.registry_path)
    if log:
        for row in mesh_attempt_rows(report):
            log(f"   template {row['template_id']} d={row['distance_rms']} "
                f"-> {row['state']}{(' — ' + row['reason']) if row['reason'] else ''}")
        log(f"Governed S6: {report['state']}")
    return report


def solve(case_index: int, run_dir: Path, *, mpi_np: int = 1,
          retain_surface_solution: bool = True, log: Any = None) -> dict[str, Any]:
    """Solve one meshed case through S6's own CFD acceptance."""
    import campaign  # noqa: PLC0415

    run_dir = Path(run_dir)
    manifest_path = run_dir / "campaign_manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("this run has no governed manifest; mesh it first")
    report = campaign.solve_case(
        manifest_path=manifest_path,
        campaign_root=run_dir / "campaign",
        case_index=int(case_index),
        mpi_np=int(mpi_np),
        dry_run=False,
        retain_surface_solution=bool(retain_surface_solution),
        retry_rejected=True,
    )
    if log:
        log(f"Governed S6: {report['state']}")
    return report


# --------------------------------------------------------------------------- #
# Reading the study's reports back                                              #
# --------------------------------------------------------------------------- #

REJECTION_REASONS = {
    "FAIL": "deformed mesh below the production quality floor",
    "FAIL_SURFACE_GATE": "target surface failed S6's pre-pyHyp surface gate",
    "FAIL_WRITTEN_AUDIT": "written CGNS failed its independent re-audit",
    "SURFACE_BUILD_ERROR": "the target surface could not be built",
    "TEMPLATE_ATTEMPT_ERROR": "the deformation raised",
    "FALLBACK_ATTEMPT_ERROR": "the fallback deformation raised",
    "PASS": "",
}


def _attempt_reason(attempt: dict[str, Any]) -> str:
    state = str(attempt.get("state", ""))
    base = REJECTION_REASONS.get(state, state)
    if state == "FAIL":
        quality = (attempt.get("acceptance") or {}).get("quality") or {}
        if "min_scaled_quality" in quality:
            return f"{base} (min scaled quality {quality['min_scaled_quality']:.4f})"
    if state == "FAIL_SURFACE_GATE":
        reasons = attempt.get("surface_failure_reasons") or []
        return f"{base}: {', '.join(str(r) for r in reasons[:3])}" if reasons else base
    for key in ("error", "written_audit_error"):
        if attempt.get(key):
            return f"{base}: {attempt[key]}"[:200]
    return base


def mesh_attempt_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    """EVERY template attempted and why each was rejected.

    The campaign records this; the old workbench had nowhere to show it, which
    meant a rejected design looked the same as a design nobody had tried.
    """
    rows = []
    for attempt in report.get("attempts") or []:
        acceptance = (attempt.get("independent_written_acceptance")
                      or attempt.get("acceptance") or {})
        quality = acceptance.get("quality") or {}
        rows.append({
            "template_id": str(attempt.get("template_id", "?")),
            "distance_rms": round(float(attempt.get("distance_rms", 0.0)), 5),
            "state": str(attempt.get("state", "?")),
            "min_scaled_quality": quality.get("min_scaled_quality"),
            "inverted_cells": quality.get("inverted_cells"),
            "reason": _attempt_reason(attempt),
            "elapsed_s": round(float(attempt.get("elapsed_s", 0.0)), 1),
        })
    return rows


def mesh_verdict(report: dict[str, Any]) -> dict[str, Any]:
    """The governed mesh result, flattened into gates a panel can render.

    Each row is one of S6's real acceptance conditions, taken from the report
    the campaign wrote - not recomputed here, because a second implementation of
    a gate is a second opinion, and the study's is the one that counts.
    """
    accepted = report.get("accepted_mesh")
    state = str(report.get("state", "MESH_REJECTED"))
    rows: list[dict[str, Any]] = []
    if accepted:
        acceptance = accepted.get("acceptance") or {}
        quality = acceptance.get("quality") or {}
        deformation = (accepted.get("deformation_replay") or {}).get("metadata") or {}
        floor = float(report.get("production_floor", 0.10))
        rows = [
            _gate("wall coordinate error", deformation.get("max_wall_error_m"),
                  "<= 1e-10 m",
                  _le(deformation.get("max_wall_error_m"), 1.0e-10)),
            _gate("block interface conformity",
                  (deformation.get("deformed_interfaces") or {}).get("max_mismatch_m"),
                  "<= 1e-10 m",
                  _le((deformation.get("deformed_interfaces") or {}).get("max_mismatch_m"),
                      1.0e-10)),
            _gate("written CGNS re-audit", acceptance.get("production_floor_passed"),
                  "independent re-read passes",
                  bool(acceptance.get("production_floor_passed"))),
            _gate("inverted cells", quality.get("inverted_cells"), "0",
                  quality.get("inverted_cells") == 0),
            _gate("minimum volume", quality.get("min_volume"), "> 0",
                  _gt(quality.get("min_volume"), 0.0)),
            _gate("min scaled Jacobian", quality.get("min_scaled_quality"),
                  f"> {floor:.2f}", _ge(quality.get("min_scaled_quality"), floor)),
        ]
    return {
        "mode": GOVERNED,
        "state": state,
        "accepted": state == "MESH_ACCEPTED",
        "design_id": report.get("design_id", ""),
        "template_id": (accepted or {}).get("template_id", ""),
        "distance_rms": (accepted or {}).get("distance_rms"),
        "cgns": (accepted or {}).get("cgns", ""),
        "cgns_sha256": (accepted or {}).get("cgns_sha256", ""),
        "production_floor": report.get("production_floor"),
        "preferred_quality": report.get("preferred_quality"),
        "preferred_quality_met": report.get("preferred_quality_met"),
        "registry_sha256": report.get("registry_sha256", ""),
        "manifest_sha256": report.get("manifest_sha256", ""),
        "implementation_sha256": report.get("mesh_implementation_sha256", ""),
        "attempts": mesh_attempt_rows(report),
        "fallback": report.get("target_specific_fallback"),
        "rows": rows,
        "failed": [row["gate"] for row in rows if not row["passed"]],
    }


def cfd_verdict(report: dict[str, Any]) -> dict[str, Any]:
    """The governed CFD result, as the gates S6 actually applies.

    A zero exit code appears here as one row among six.  It is what the process
    did, not what the solution is worth.
    """
    forces = report.get("forces") or {}
    rows = [
        _gate("solver return code", report.get("solver_return_code"), "0",
              report.get("solver_return_code") == 0),
        _gate("solver status", report.get("solver_status"), "converged",
              str(report.get("solver_status")) == "converged"),
        _gate("residual reduction", report.get("residual_orders_dropped"),
              ">= 6 orders", bool(report.get("residual_gate_passed"))),
        _gate("finite forces", report.get("finite_forces"), "cl, cd, cmy finite",
              bool(report.get("finite_forces"))),
        _gate("positive drag", forces.get("cd"), "> 0",
              bool((report.get("force_plausibility_gate") or {}).get("positive_drag"))),
        _gate("force tail stability",
              (report.get("force_tail_gate") or {}).get("relative_ranges"),
              "relative range <= 1e-3",
              bool((report.get("force_tail_gate") or {}).get("passed"))),
        _gate("wall y+", (report.get("wall_yplus_gate") or {}).get("percentiles"),
              "p95 <= 1, p99 <= 2, max <= 5",
              bool((report.get("wall_yplus_gate") or {}).get("passed"))),
        _gate("artifact provenance",
              (report.get("artifact_provenance_gate") or {}).get("missing"),
              "no missing artifacts",
              bool((report.get("artifact_provenance_gate") or {}).get("passed"))),
    ]
    state = str(report.get("state", "CFD_REJECTED"))
    return {
        "mode": GOVERNED,
        "state": state,
        "accepted": state == "CFD_ACCEPTED",
        "case_id": report.get("case_id", ""),
        "forces": {k: v for k, v in forces.items() if isinstance(v, (int, float))},
        "mesh_sha256": report.get("mesh_sha256", ""),
        "rows": rows,
        "failed": [row["gate"] for row in rows if not row["passed"]],
    }


def _gate(name: str, actual: Any, limit: str, passed: bool) -> dict[str, Any]:
    if isinstance(actual, float):
        shown = f"{actual:.6g}"
    elif isinstance(actual, dict):
        shown = ", ".join(f"{k} {v:.3g}" if isinstance(v, float) else f"{k} {v}"
                          for k, v in list(actual.items())[:3])
    elif isinstance(actual, list):
        shown = ", ".join(str(v) for v in actual[:3]) or "none"
    else:
        shown = "—" if actual is None else str(actual)
    return {"gate": name, "actual": shown, "limit": limit, "passed": bool(passed)}


def _le(value: Any, limit: float) -> bool:
    return isinstance(value, (int, float)) and float(value) <= limit


def _ge(value: Any, limit: float) -> bool:
    return isinstance(value, (int, float)) and float(value) >= limit


def _gt(value: Any, limit: float) -> bool:
    return isinstance(value, (int, float)) and float(value) > limit
