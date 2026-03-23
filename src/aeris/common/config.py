"""
Module: config

Purpose:
    Load YAML configuration files safely.

Responsibilities:
    - Validate file existence and extension
    - Parse YAML into dictionary
    - Perform minimal structural validation

Guarantees:
    - Output is a dictionary
    - Invalid files fail early

Caveats:
    - No schema validation
    - No type enforcement

Future Improvements:
    - Add schema validation layer (Pydantic/dataclasses)
    - Validate parameter bounds
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml_config(config_path: str | Path) -> dict[str, Any]:
    """Load a YAML config file into a dictionary."""
    path = Path(config_path).expanduser().resolve()

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    if path.suffix.lower() not in {".yaml", ".yml"}:
        raise ValueError(f"Config file must be .yaml or .yml: {path}")

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if data is None:
        return {}

    if not isinstance(data, dict):
        raise ValueError(f"Top-level config must be a mapping/dictionary: {path}")

    for key in data:
        if not isinstance(key, str):
            raise ValueError(f"Config keys must be strings: {path}")

    return data  # ✅ THIS MUST EXIST
