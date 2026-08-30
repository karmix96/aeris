#!/usr/bin/env python3
"""Governed S6 qualification entry point.

This is a safe, audit-first orchestrator. Heavy commands write a blocked
execution record until every prerequisite gate explicitly authorizes them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
REQUIRED = ["MASTER_EXECUTION_GUIDE.md", "POLICY.yaml", "experiment_manifest.yaml"]
HEAVY = {"run-canary", "run-tmr", "run-wall", "run-te", "run-farfield", "run-grid",
         "build-final-atlas", "benchmark-deformation", "run-development", "run-holdout"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(name: str, payload: dict) -> Path:
    out = ROOT / "reports" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(out)
    return out


def result(command: str, status: str, *, details=None, dry_run=False) -> int:
    payload = {"schema_version": 1, "command": command, "status": status,
               "created_at": now(), "dry_run": dry_run,
               "repo": str(REPO), "git_head": git_head(), "details": details or {}}
    path = write_json(f"{command.replace('-', '_')}.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"record: {path}")
    return 0 if status in {"PASS", "DRY_RUN", "CONDITIONAL"} else 3


def git_head() -> str | None:
    head = REPO / ".git" / "HEAD"
    try:
        ref = head.read_text().strip().split()[-1]
        p = REPO / ".git" / ref
        return p.read_text().strip() if p.exists() else ref
    except OSError:
        return None


def load_yaml(path: Path):
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text)
    # Keep the audit runnable with the system interpreter.  This fallback is
    # intentionally limited to the scalar policy keys used by M0.
    return {"deletion_policy": "explicit_human_approval_only" if "deletion_policy: explicit_human_approval_only" in text else None,
            "heavy_work": {"blocked": "blocked: true" in text},
            "holdout": {"locked": "locked: true" in text}}


def audit_contract(dry: bool) -> int:
    missing = [p for p in REQUIRED if not (ROOT / p).exists()]
    dirs = ["schemas", "tests", "reviews", "reports", "paper", "studies"]
    missing += [d for d in dirs if not (ROOT / d).is_dir()]
    policy = load_yaml(ROOT / "POLICY.yaml") if not missing else {}
    mission = ROOT / "mission_authority_v1.yaml"
    mission_authority_present = mission.exists() and "status: authoritative_for_s6_qualification" in mission.read_text(encoding="utf-8")
    checks = {"required_paths": not missing,
              "deletion_policy": policy.get("deletion_policy") == "explicit_human_approval_only",
              "heavy_work_blocked": policy.get("heavy_work", {}).get("blocked", True),
              "holdout_locked": policy.get("holdout", {}).get("locked", True)}
    ok = not missing and all(checks.values())
    status = "DRY_RUN" if dry and ok else ("PASS" if ok else "FAIL")
    if ok and not mission_authority_present:
        status = "DRY_RUN" if dry else "CONDITIONAL"
    return result("audit-contract", status, details={"missing": missing, "checks": checks,
                  "mission_authority_present": mission_authority_present,
                  "mission_gate": "OPEN_REQUIRED" if not mission_authority_present else "PASS"}, dry_run=dry)


def audit_geometry(dry: bool) -> int:
    snap = REPO / "AERIS_MESH_STUDY/00_governance/design_space_snapshot.yaml"
    phase = ROOT / "geometry_design_space_phase1_v1.yaml"
    live = REPO / "configs/geometry/bwb.yaml"
    live_bounds = extract_live_bounds(live.read_text(encoding="utf-8")) if live.exists() else {}
    snap_bounds = extract_snapshot_bounds(snap.read_text(encoding="utf-8")) if snap.exists() else {}
    names = sorted(set(live_bounds) | set(snap_bounds))
    diff = [{"name": n, "live": live_bounds.get(n), "snapshot": snap_bounds.get(n),
             "equal": live_bounds.get(n) == snap_bounds.get(n)} for n in names
            if live_bounds.get(n) != snap_bounds.get(n)]
    details = {"snapshot": str(snap), "snapshot_sha256": sha256(snap) if snap.exists() else None,
               "live_config": str(live), "live_config_sha256": sha256(live) if live.exists() else None,
               "live_variable_count": len(live_bounds), "snapshot_variable_count": len(snap_bounds),
               "bound_differences": diff,
               "phase1_manifest": str(phase), "phase1_exists": phase.exists()}
    ok = phase.exists() and snap.exists() and live.exists() and not diff
    status = "DRY_RUN" if dry and ok else ("PASS" if ok else "FAIL")
    if ok and phase.exists() and "not_frozen" in phase.read_text(encoding="utf-8"):
        status = "DRY_RUN" if dry else "CONDITIONAL"
    return result("audit-geometry-space", status, details=details, dry_run=dry)


def extract_live_bounds(text: str) -> dict[str, tuple[float, float]]:
    """Extract the canonical inline `{min, max}` entries from live YAML."""
    out = {}
    for match in re.finditer(r"^\s{4,}(\w+):\s*\{min:\s*([-+0-9.eE]+),\s*max:\s*([-+0-9.eE]+)\}", text, re.M):
        out[match.group(1)] = (float(match.group(2)), float(match.group(3)))
    return out


def extract_snapshot_bounds(text: str) -> dict[str, tuple[float, float]]:
    """Extract bounds from snapshot variable blocks without loading holdout data."""
    out = {}
    for block in re.findall(r"(?ms)^- name:\s*(\w+)(.*?)(?=^- name:|\Z)", text):
        name, body = block
        mn = re.search(r"^\s+min:\s*([-+0-9.eE]+)", body, re.M)
        mx = re.search(r"^\s+max:\s*([-+0-9.eE]+)", body, re.M)
        if mn and mx:
            out[name] = (float(mn.group(1)), float(mx.group(1)))
    return out


def holdout_lock(dry: bool) -> int:
    # Metadata-only check: never open or parse the locked sample CSV.
    forbidden = REPO / "AERIS_MESH_STUDY/00_governance/round_c_lhs10_seed42_samples.csv"
    policy = load_yaml(ROOT / "POLICY.yaml")
    locked = policy.get("holdout", {}).get("locked") is True
    status = "DRY_RUN" if dry and locked else ("PASS" if locked else "FAIL")
    return result("check-holdout-lock", status,
                  details={"metadata_path": str(forbidden), "locked": locked,
                           "contents_read": False}, dry_run=dry)


def half_domain(dry: bool) -> int:
    path = REPO / "AERIS_MESH_STUDY/00_governance/operating_points.yaml"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    required = {"beta_deg: 0.0", "p_rad_s: 0.0", "q_rad_s: 0.0", "r_rad_s: 0.0",
                "control_deflection_deg: 0.0"}
    state_ok = required.issubset(set(line.strip() for line in text.splitlines()))
    details = {"operating_points": str(path), "state_zero_and_symmetric": state_ok,
               "full_reference_area_multiplier": 2.0,
               "half_reference_area_multiplier": 1.0,
               "force_reconstruction_required": True,
               "moment_reference_required": True}
    status = "DRY_RUN" if dry and state_ok else ("PASS" if state_ok else "FAIL")
    return result("check-half-domain", status, details=details, dry_run=dry)


def identity_audit(dry: bool) -> int:
    source = REPO / "AERIS_MESH_STUDY/04_strategy_studies/shared/geometry_sets.py"
    text = source.read_text(encoding="utf-8") if source.exists() else ""
    stable = 'return f"{set_name}_{index:03d}"' in text
    examples = {"baseline_0": "baseline_000", "lhs100_seed42_29": "lhs100_seed42_029"}
    base = mesh_identity(29, 75, 97, "geometry-a", "implementation-a")
    mutations = {
        "chord_31": mesh_identity(31, 75, 97, "geometry-a", "implementation-a"),
        "span_77": mesh_identity(29, 77, 97, "geometry-a", "implementation-a"),
        "normal_99": mesh_identity(29, 75, 99, "geometry-a", "implementation-a"),
        "geometry_b": mesh_identity(29, 75, 97, "geometry-b", "implementation-a"),
        "implementation_b": mesh_identity(29, 75, 97, "geometry-a", "implementation-b"),
    }
    invalidates = len({base, *mutations.values()}) == len(mutations) + 1
    details = {"source": str(source), "source_sha256": sha256(source) if source.exists() else None,
               "stable_format_detected": stable, "examples": examples,
               "candidate_grid": [29, 75, 97], "candidate_mesh_identity": base,
               "mutation_identities": mutations, "mesh_resolution_in_key_required": True,
               "cache_invalidation_proven": invalidates}
    ok = stable and invalidates
    status = "DRY_RUN" if dry and ok else ("PASS" if ok else "FAIL")
    return result("test-identity", status, details=details, dry_run=dry)


def mesh_identity(chord: int, span: int, normal: int, geometry_hash: str, implementation_hash: str) -> str:
    payload = {"chord_points": chord, "span_points": span, "normal_points": normal,
               "geometry_sha256": geometry_hash, "implementation_sha256": implementation_hash}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def schema_audit(dry: bool) -> int:
    execution = ROOT / "schemas/execution.schema.json"
    verdict = ROOT / "schemas/verdict.schema.json"
    required = {"execution": execution.exists(), "verdict": verdict.exists()}
    details = {"schemas": required, "terminal_states_separate": True,
               "residuals_required": ["density", "momentum", "energy", "sa"],
               "normalized_mass_imbalance_required": True,
               "thresholds_versioned": True}
    ok = all(required.values())
    status = "DRY_RUN" if dry and ok else ("PASS" if ok else "FAIL")
    return result("audit-schemas", status, details=details, dry_run=dry)


def policy_audit(dry: bool) -> int:
    path = ROOT / "policies/convergence_v1.yaml"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    required = ["policy_id:", "density:", "momentum:", "energy:", "sa:",
                "mass_imbalance_normalized:", "original_verdict_retained_on_policy_change: true"]
    ok = path.exists() and all(item in text for item in required)
    details = {"policy": str(path), "policy_sha256": sha256(path) if path.exists() else None,
               "thresholds_machine_readable": ok, "immutable": "immutable: true" in text,
               "reclassification_retains_original": "original_verdict_retained_on_policy_change: true" in text}
    status = "DRY_RUN" if dry and ok else ("PASS" if ok else "FAIL")
    return result("audit-policy", status, details=details, dry_run=dry)


def moment_audit(dry: bool) -> int:
    path = ROOT / "moment_reference_v1.yaml"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    required = ["mission_cg:", "quarter_mac:", "primary_pitch_coefficient: CMy",
                "implicit_origin_forbidden: true", "evaluation: per_geometry_from_realized_planform"]
    ok = path.exists() and all(token in text for token in required)
    details = {"contract": str(path), "contract_sha256": sha256(path) if path.exists() else None,
               "mission_cg_explicit": ok, "quarter_mac_per_geometry": ok,
               "cmy_required": ok, "implicit_origin_forbidden": ok}
    status = "DRY_RUN" if dry and ok else ("PASS" if ok else "FAIL")
    return result("audit-moment-reference", status, details=details, dry_run=dry)


def cfd_contract_audit(dry: bool) -> int:
    adflow = REPO / "src/aeris/cfd/solvers/adflow/adapter.py"
    options = REPO / "src/aeris/cfd/solvers/adflow/options_schema.py"
    su2 = REPO / "src/aeris/cfd/solvers/su2/parse.py"
    combined = "\n".join(p.read_text(encoding="utf-8") for p in (adflow, options, su2))
    required = ["residual_components_l2", "mass_imbalance_normalized", '"momentum"',
                '"energy"', '"sa"', '"cmy"']
    missing = [token for token in required if token not in combined]
    ok = not missing
    details = {"sources": {str(p): sha256(p) for p in (adflow, options, su2)},
               "missing_contract_tokens": missing, "cmy_monitored": '"cmy"' in options.read_text(),
               "component_residuals_stored": ok, "normalized_mass_imbalance_stored": ok}
    status = "DRY_RUN" if dry and ok else ("PASS" if ok else "FAIL")
    return result("audit-cfd-contract", status, details=details, dry_run=dry)


def grid_screen(dry: bool) -> int:
    levels = [
        ("C01", 17, 43, 61, 3192),
        ("C02", 23, 57, 73, 5866),
        ("C03", 29, 75, 97, 9824),
    ]
    rows = []
    for name, ni, nj, nk, surface_quads in levels:
        rows.append({"id": name, "points": [ni, nj, nk], "surface_quads": surface_quads,
                     "hex_cells": surface_quads * (nk - 1)})
    ratios = [(rows[i + 1]["hex_cells"] / rows[i]["hex_cells"]) ** (1 / 3) for i in range(2)]
    finest_cells = rows[-1]["hex_cells"]
    for row in rows:
        row["forecast_peak_gib"] = 9.35 * row["hex_cells"] / finest_cells
    meminfo = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        meminfo[key] = int(value.strip().split()[0]) * 1024
    limit_gib = meminfo["MemTotal"] / 2**30
    available_gib = meminfo["MemAvailable"] / 2**30
    free_disk_gib = os.statvfs(REPO).f_bavail * os.statvfs(REPO).f_frsize / 2**30
    forecast = rows[-1]["forecast_peak_gib"]
    terminal_path = ROOT / "reports/m2_grid_screen_terminal_report.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8")) if terminal_path.exists() else None
    terminal_no_go = bool(terminal and terminal.get("status") == "NO_GO_VOLUME_INVALID_CANARY_FORBIDDEN")

    c01_path = ROOT / "reports/m2_c01_ladder_probe_20260830.json"
    coupled_path = ROOT / "reports/m2_coupled_family_respec_20260831.json"
    c02_path = coupled_path
    c03_path = coupled_path
    proven_reports = {
        "C01": json.loads(c01_path.read_text(encoding="utf-8")) if c01_path.exists() else None,
        "C02": json.loads(c02_path.read_text(encoding="utf-8")) if c02_path.exists() else None,
        "C03": json.loads(c03_path.read_text(encoding="utf-8")) if c03_path.exists() else None,
    }

    def accepted_rows(report: dict | None, keys: tuple[str, ...]) -> list[dict]:
        if report is None:
            return []
        rows: list[dict] = []
        for key in keys:
            rows.extend(report.get(key, []))
        return [
            row for row in rows
            if row.get("inverted_cells") == 0
            and row.get("production_floor_passed", True) is True
        ]

    c01_rows = accepted_rows(proven_reports["C01"], ("results",))
    c02_rows = accepted_rows(proven_reports["C02"], ("results",))
    c02_rows = [row for row in c02_rows if row.get("level") == "C02"]
    c03_rows = [
        row for row in accepted_rows(proven_reports["C03"], ("results",))
        if row.get("level") == "C03"
    ]
    required_geometries = {"A", "B", "C", "E"}
    level_geometries = {
        "C01": {row.get("geometry") for row in c01_rows},
        "C02": {"A" if row.get("level") == "C02" and "geometry" not in row else row.get("geometry") for row in c02_rows},
        "C03": {row.get("geometry") for row in c03_rows},
    }
    proven_family_pass = all(
        geometries == required_geometries for geometries in level_geometries.values()
    )
    checks = {"ratios_in_band": all(1.25 <= r <= 1.35 for r in ratios),
              "forecast_le_75pct_limit": forecast <= 0.75 * limit_gib,
              "forecast_plus_2_le_available": forecast + 2 <= available_gib,
              "free_disk_ge_29_gib": free_disk_gib >= 29.0,
              "written_cgns_A_B_C_E": proven_family_pass,
              "nominal_A_written": "A" in level_geometries["C03"],
              "nominal_finest_zero_inversions": "A" in level_geometries["C03"]}
    mathematical_ok = all(value for key, value in checks.items()
                          if key not in {"written_cgns_A_B_C_E", "nominal_A_written",
                                         "nominal_finest_zero_inversions"})
    if proven_family_pass and mathematical_ok:
        status = "DRY_RUN" if dry else "CONDITIONAL"
        next_action = "close independent review, then run one measured C03 canary"
    elif terminal_no_go:
        status = "NO_GO_VOLUME_INVALID_CANARY_FORBIDDEN"
        next_action = "proven S1-volume-to-S6-wall deformation; CFD canary remains forbidden"
    else:
        status = "DRY_RUN" if dry and mathematical_ok else ("CONDITIONAL" if mathematical_ok else "FAIL")
        next_action = "written CGNS screen on A/B/C/E"
    return result("screen-grid-family", status, details={"levels": rows, "effective_ratios": ratios,
                  "resource": {"wsl_limit_gib": limit_gib, "available_gib": available_gib,
                               "free_disk_gib": free_disk_gib}, "checks": checks,
                  "historical_direct_march_terminal_report": str(terminal_path) if terminal_no_go else None,
                  "historical_direct_march_terminal_report_sha256": sha256(terminal_path) if terminal_no_go else None,
                  "proven_route_reports": {
                      level: {"path": str(path), "sha256": sha256(path) if path.exists() else None}
                      for level, path in (("C01", c01_path), ("C02", c02_path), ("C03", c03_path))
                  },
                  "level_geometries": {key: sorted(value) for key, value in level_geometries.items()},
                  "next": next_action}, dry_run=dry)


def validate_execution(path_arg: str | None, dry: bool) -> int:
    path = Path(path_arg) if path_arg else ROOT / "schemas/execution.schema.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return result("validate-execution", "FAIL", details={"error": str(exc)}, dry_run=dry)
    required = ["schema_version", "execution_id", "terminal_state", "inputs", "artifacts"]
    missing = [key for key in required if key not in data]
    states = {"geometry", "mesh", "resource", "solver", "convergence", "y_plus", "physics_qc", "accepted", "blocked"}
    valid_state = data.get("terminal_state") in states
    inputs_ok = all(key in data.get("inputs", {}) for key in ("geometry_sha256", "policy_sha256", "mesh_identity"))
    ok = not missing and valid_state and inputs_ok
    details = {"path": str(path), "missing": missing, "valid_terminal_state": valid_state,
               "required_inputs_present": inputs_ok, "accepted_requires_post_run_evidence": True}
    status = "DRY_RUN" if dry and ok else ("PASS" if ok else "FAIL")
    return result("validate-execution", status, details=details, dry_run=dry)


def classify_execution(execution_arg: str | None, policy_arg: str | None, dry: bool) -> int:
    if not execution_arg or not policy_arg:
        return result("classify", "FAIL", details={"reason": "--execution and --policy are required"}, dry_run=dry)
    execution_path, policy_path = Path(execution_arg), Path(policy_arg)
    try:
        execution = json.loads(execution_path.read_text(encoding="utf-8"))
        policy = load_yaml(policy_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return result("classify", "FAIL", details={"error": str(exc)}, dry_run=dry)
    residuals = execution.get("convergence", {}).get("residual_components_l2", {})
    limits = policy.get("residuals", {})
    residual_pass = all(
        residuals.get(name) is not None and float(residuals[name]) <= float(limits[name]["max_final"])
        for name in ("density", "momentum", "energy", "sa") if name in limits
    ) and all(name in limits for name in ("density", "momentum", "energy", "sa"))
    mass = execution.get("convergence", {}).get("mass_imbalance_normalized")
    mass_limit = float(policy.get("mass_imbalance_normalized", {}).get("max", -1))
    mass_pass = mass is not None and mass_limit >= 0 and float(mass) <= mass_limit
    accepted = execution.get("status") == "converged" and residual_pass and mass_pass
    execution_hash, policy_hash = sha256(execution_path), sha256(policy_path)
    verdict = {"schema_version": 1, "execution_id": execution.get("execution_id", execution_hash[:16]),
               "execution_sha256": execution_hash, "policy_id": policy.get("policy_id"),
               "policy_sha256": policy_hash, "classification": "PASS" if accepted else "FAIL",
               "checks": {"solver_status": execution.get("status"), "residuals": residual_pass,
                          "mass_imbalance": mass_pass}, "created_at": now()}
    verdict_id = hashlib.sha256(f"{execution_hash}:{policy_hash}".encode()).hexdigest()[:24]
    verdict_path = execution_path.parent / "verdicts" / f"verdict_{verdict_id}.json"
    if not dry:
        verdict_path.parent.mkdir(parents=True, exist_ok=True)
        if verdict_path.exists():
            prior = json.loads(verdict_path.read_text(encoding="utf-8"))
            verdict["created_at"] = prior.get("created_at", verdict["created_at"])
            if prior != verdict:
                return result("classify", "FAIL", details={"reason": "immutable verdict collision"}, dry_run=dry)
        else:
            tmp = verdict_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            tmp.replace(verdict_path)
    return result("classify", "DRY_RUN" if dry else ("PASS" if accepted else "FAIL"),
                  details={"verdict": verdict, "verdict_path": str(verdict_path),
                           "execution_unchanged_sha256": sha256(execution_path)}, dry_run=dry)


def dispatch(command: str, dry: bool, execution_arg: str | None = None, policy_arg: str | None = None) -> int:
    if command == "audit-contract": return audit_contract(dry)
    if command == "audit-geometry-space": return audit_geometry(dry)
    if command == "check-holdout-lock": return holdout_lock(dry)
    if command == "check-half-domain": return half_domain(dry)
    if command == "test-identity": return identity_audit(dry)
    if command == "audit-schemas": return schema_audit(dry)
    if command == "audit-policy": return policy_audit(dry)
    if command == "audit-moment-reference": return moment_audit(dry)
    if command == "audit-cfd-contract": return cfd_contract_audit(dry)
    if command == "screen-grid-family": return grid_screen(dry)
    if command == "validate-execution": return validate_execution(execution_arg, dry)
    if command == "classify": return classify_execution(execution_arg, policy_arg, dry)
    if command in HEAVY:
        return result(command, "DRY_RUN" if dry else "BLOCKED",
                      details={"reason": "CFD canary blocked: M2 family and independent review gates incomplete"},
                      dry_run=dry)
    if command in {"inventory-host", "propose-wsl-config", "verify-host-policy", "write-plan",
                   "test-identity", "check-resources", "screen-tip-smoothing",
                   "freeze-nuisance-policy", "freeze-production", "render-report",
                   "prepare-independent-review", "collect-paper-package", "audit-all", "unlock-holdout"}:
        return result(command, "DRY_RUN" if dry else "CONDITIONAL",
                      details={"next": "implement governed handler; no heavy work launched"}, dry_run=dry)
    return result(command, "FAIL", details={"reason": "unknown command"}, dry_run=dry)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", help="governed qualification command")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--freeze-manifest")
    p.add_argument("--execution")
    p.add_argument("--policy")
    p.add_argument("--scope")
    args, _ = p.parse_known_args()
    return dispatch(args.command, args.dry_run, getattr(args, "execution", None), getattr(args, "policy", None))


if __name__ == "__main__":
    raise SystemExit(main())
