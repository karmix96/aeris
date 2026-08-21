#!/usr/bin/env python3
"""Stage 01 NACA0012 TMR anchor runner.

This is study-local glue around the existing ``aeris.cfd`` case runner. It
does not define a new mesh method; it records the exact evidence Stage 01
needs from the pinned TMR case.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from aeris.cfd.case.loader import load_case_spec  # noqa: E402
from aeris.cfd.case.runner import CaseError, run_case  # noqa: E402
from aeris.cfd.env import mach_aero_mpirun, mach_aero_python  # noqa: E402
from aeris.common.config import file_sha256  # noqa: E402

REFERENCE = {
    "case": "configs/cfd/validation_naca0012_tmr.yaml",
    "surface_fmt_sha256": "6625b41253dd527207e796c10f08ade30676b055625c7e9baefd30131962b6d4",
    "topology": "airfoil_ogrid_v1",
    "n_loop_points": 513,
    "characteristic_length": 1.0,
    "pyhyp": {"N": 193, "s0": 5.0e-6, "marchDist": 100.0, "coarsen": 1},
    "historical_adflow": {
        "cl": 1.0917740093456412,
        "cd": 0.013164679005086222,
    },
    "tmr_cfl3d": {"cl": 1.0909, "cd": 0.01231},
    "force_tolerance": {"cl_abs": 0.003, "cd_abs": 0.0010},
}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _git_value(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip()


def _env() -> dict[str, Any]:
    def _path_text(func: Any) -> str | None:
        try:
            return str(func())
        except Exception:
            return None

    return {
        "python": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "git_head": _git_value("rev-parse", "HEAD"),
        "git_branch": _git_value("rev-parse", "--abbrev-ref", "HEAD"),
        "mach_aero_python": _path_text(mach_aero_python),
        "mach_aero_mpirun": _path_text(mach_aero_mpirun),
    }


def _hashes(root: Path, names: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for name in names:
        path = root / name
        out[name] = file_sha256(path) if path.is_file() else None
    return out


def _check(checks: list[dict[str, Any]], name: str, passed: bool | None, detail: Any) -> None:
    checks.append({"name": name, "passed": passed, "detail": detail})


def _collect_checks(workdir: Path, *, mode: str, run_error: str | None) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    surface_dir = workdir / "surface"
    surface_report = _read_json(surface_dir / "surface_report.json") or {}
    pyhyp_options = _read_json(surface_dir / "pyhyp_options.json") or {}
    volume_report = _read_json(surface_dir / "volume_report.json") or {}
    solve_report = _read_json(workdir / "solve" / "solve_report.json") or {}

    surface_fmt = surface_dir / "surface.fmt"
    surface_sha = file_sha256(surface_fmt) if surface_fmt.is_file() else None
    _check(
        checks,
        "surface_fmt_sha256_matches_reference",
        surface_sha == REFERENCE["surface_fmt_sha256"] if surface_sha else False,
        {"actual": surface_sha, "expected": REFERENCE["surface_fmt_sha256"]},
    )
    _check(
        checks,
        "surface_topology_matches_reference",
        surface_report.get("topology") == REFERENCE["topology"] if surface_report else False,
        {"actual": surface_report.get("topology"), "expected": REFERENCE["topology"]},
    )
    _check(
        checks,
        "surface_loop_dimensions_match_reference",
        surface_report.get("n_loop_points") == REFERENCE["n_loop_points"]
        if surface_report
        else False,
        {"actual": surface_report.get("n_loop_points"), "expected": REFERENCE["n_loop_points"]},
    )
    _check(
        checks,
        "surface_characteristic_length_matches_reference",
        abs(float(surface_report.get("characteristic_length", -1.0)) - 1.0) < 1e-12
        if surface_report
        else False,
        {
            "actual": surface_report.get("characteristic_length"),
            "expected": REFERENCE["characteristic_length"],
        },
    )

    if pyhyp_options:
        for key, expected in REFERENCE["pyhyp"].items():
            actual = pyhyp_options.get(key)
            if isinstance(expected, float):
                passed = abs(float(actual) - expected) <= max(1e-12, abs(expected) * 1e-12)
            else:
                passed = actual == expected
            _check(checks, f"pyhyp_option_{key}_matches_reference", passed, {
                "actual": actual,
                "expected": expected,
            })
    else:
        _check(checks, "pyhyp_options_written", False, "missing surface/pyhyp_options.json")

    if mode in {"mesh", "solve"}:
        audit = volume_report.get("volume_audit") or {}
        march = volume_report.get("march_metrics") or {}
        _check(
            checks,
            "volume_report_status_valid",
            volume_report.get("status") == "valid" if volume_report else False,
            volume_report.get("status"),
        )
        _check(
            checks,
            "volume_audit_clean",
            audit.get("classification") == "clean" if audit else False,
            audit.get("classification"),
        )
        _check(
            checks,
            "no_negative_quality_layers",
            int(march.get("low_quality_layers") or 0) == 0 if march else False,
            march.get("low_quality_layers"),
        )
    else:
        _check(checks, "volume_execution", None, "not requested in dry-run mode")

    if mode == "solve":
        forces = solve_report.get("forces") or {}
        for key, expected in REFERENCE["historical_adflow"].items():
            tol = REFERENCE["force_tolerance"][f"{key}_abs"]
            actual = forces.get(key)
            passed = actual is not None and abs(float(actual) - expected) <= tol
            _check(checks, f"adflow_{key}_matches_historical_anchor", passed, {
                "actual": actual,
                "expected": expected,
                "abs_tolerance": tol,
            })
    else:
        _check(checks, "solver_force_comparison", None, f"not requested in {mode} mode")

    if run_error is not None:
        _check(checks, "runner_completed", False, run_error)

    return checks


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    checks = report["checks"]
    passed = sum(1 for item in checks if item["passed"] is True)
    failed = sum(1 for item in checks if item["passed"] is False)
    skipped = sum(1 for item in checks if item["passed"] is None)
    lines = [
        "# Stage 01 TMR Anchor Report",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Status: `{report['status']}`",
        f"- Workdir: `{report['workdir']}`",
        f"- Checks: {passed} passed, {failed} failed, {skipped} skipped",
        "",
        "## Checks",
    ]
    for item in checks:
        state = "PASS" if item["passed"] is True else "FAIL" if item["passed"] is False else "SKIP"
        lines.append(f"- `{state}` {item['name']}: {item['detail']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    case_path = (REPO_ROOT / args.case).resolve()
    workdir = (REPO_ROOT / args.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    stages = {
        "dry-run": ("surface", "volume"),
        "mesh": ("surface", "volume"),
        "solve": ("surface", "volume", "solve", "post"),
    }[args.mode]

    run_error = None
    try:
        spec = load_case_spec(case_path)
        run_case(
            spec,
            workdir=workdir,
            stages=stages,
            dry_run=args.mode == "dry-run",
            echo=print,
        )
    except (CaseError, Exception) as exc:  # noqa: BLE001 - report partial evidence
        run_error = f"{type(exc).__name__}: {exc}"
        print(f"[tmr] failed: {run_error}", file=sys.stderr)

    checks = _collect_checks(workdir, mode=args.mode, run_error=run_error)
    failed = [item for item in checks if item["passed"] is False]
    hard_fail = [item for item in failed if item["name"] != "runner_completed"]
    status = "PASS" if run_error is None and not hard_fail else "FAIL"

    report = {
        "schema": "aeris.mesh_study.stage01_tmr_anchor_report.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "status": status,
        "case": str(case_path),
        "case_sha256": file_sha256(case_path),
        "workdir": str(workdir),
        "reference": REFERENCE,
        "environment": _env(),
        "artifacts": {
            "surface": _hashes(workdir / "surface", [
                "surface.fmt",
                "surface_report.json",
                "pyhyp_options.json",
                "pyhyp_effective_options.json",
                "volume_report.json",
            ]),
            "solve": _hashes(workdir / "solve", [
                "solve_report.json",
                "verification.json",
                "adflow_options.json",
                "adflow_case.json",
            ]),
        },
        "checks": checks,
        "error": run_error,
    }

    report_json = (REPO_ROOT / args.report_json).resolve()
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_markdown(report, report_json.with_suffix(".md"))
    print(f"[tmr] report: {report_json}")
    return 0 if status == "PASS" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="configs/cfd/validation_naca0012_tmr.yaml")
    parser.add_argument(
        "--workdir",
        default="AERIS_MESH_STUDY/artifacts/stage01/tmr_anchor",
    )
    parser.add_argument(
        "--report-json",
        default="AERIS_MESH_STUDY/02_tmr/tmr_anchor_report.json",
    )
    parser.add_argument(
        "--mode",
        choices=("dry-run", "mesh", "solve"),
        default="dry-run",
        help="dry-run writes options only; mesh executes pyHyp; solve also runs ADflow/post.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
