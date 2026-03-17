from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aeris.pipeline.geometry_run import run_geometry_generation


BAD_CONFIG = PROJECT_ROOT / "configs" / "smoke" / "bad.yaml"
RUNS_DIR = PROJECT_ROOT / "data" / "runs"


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _latest_subdir(root: Path) -> Path:
    subdirs = [p for p in root.iterdir() if p.is_dir()]
    if not subdirs:
        raise FileNotFoundError(f"No run folders found in {root}")
    return max(subdirs, key=lambda p: p.stat().st_mtime)


def main() -> None:
    before = {p.name for p in RUNS_DIR.iterdir() if p.is_dir()} if RUNS_DIR.exists() else set()

    print("=== BAD CONFIG FAILURE CHECK ===")
    rc = run_geometry_generation(BAD_CONFIG)
    _assert(rc != 0, "Bad config unexpectedly succeeded")

    after = {p.name for p in RUNS_DIR.iterdir() if p.is_dir()}
    new_runs = sorted(after - before)
    _assert(new_runs, "No run directory created for bad config")

    run_dir = RUNS_DIR / new_runs[-1]
    manifest_path = run_dir / "manifest.json"
    _assert(manifest_path.exists(), f"Missing manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _assert(manifest["status"] == "failed", "Manifest status should be failed")
    _assert(manifest["error"] is not None, "Manifest error payload missing")
    _assert("type" in manifest["error"], "Manifest error type missing")
    _assert("message" in manifest["error"], "Manifest error message missing")
    _assert("traceback" in manifest["error"], "Manifest traceback missing")

    print(f"Run folder: {run_dir}")
    print(json.dumps(manifest["error"], indent=2))
    print("BAD CONFIG FAILURE CHECK PASSED.")


if __name__ == "__main__":
    main()