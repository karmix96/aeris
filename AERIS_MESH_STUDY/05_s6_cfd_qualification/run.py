#!/usr/bin/env python3
"""Governed S6 qualification entry point.

This deliberately starts as a safe, audit-first orchestrator.  Heavy commands
write a blocked execution record until the M0--M2 gates authorize them.
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
    mission = REPO / "AERIS_MESH_STUDY/00_governance/operating_points.yaml"
    mission_authority_present = mission.exists() and "mission_config_found: true" in mission.read_text(encoding="utf-8")
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


def dispatch(command: str, dry: bool) -> int:
    if command == "audit-contract": return audit_contract(dry)
    if command == "audit-geometry-space": return audit_geometry(dry)
    if command == "check-holdout-lock": return holdout_lock(dry)
    if command in HEAVY:
        return result(command, "DRY_RUN" if dry else "BLOCKED",
                      details={"reason": "M0-M2 gates and measured campaign forecast incomplete"}, dry_run=dry)
    if command in {"inventory-host", "propose-wsl-config", "verify-host-policy", "write-plan",
                   "test-identity", "check-resources", "screen-grid-family", "screen-tip-smoothing",
                   "freeze-nuisance-policy", "freeze-production", "classify", "render-report",
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
    return dispatch(args.command, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
