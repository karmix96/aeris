from __future__ import annotations

import json
from pathlib import Path

from aeris.dynamics.models import DynamicsFoundationResult


def write_dynamics_foundation_result(result: DynamicsFoundationResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "dynamics_foundation.json"
    path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return path


def read_dynamics_foundation_result(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))