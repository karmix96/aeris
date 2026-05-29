"""
Module: config

Purpose:
    Safe YAML configuration loading for AERIS.

Responsibilities:
    - Validate file existence and extension
    - Parse YAML into a dictionary
    - Perform minimal structural validation
    - Fail early with clear errors

Design boundary:
    This module is intentionally generic. It does not validate BWB geometry
    bounds, aero solver settings, ML feature schemas, QC policies, or dynamics
    models. Domain-specific validation belongs in domain-specific config/model
    layers.

Guarantees:
    - Output is always a dictionary.
    - Empty YAML files return an empty dictionary.
    - Top-level config keys must be non-empty strings.
    - yaml.safe_load is used, so arbitrary Python object construction is not allowed.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import yaml

_LOGGER = logging.getLogger(__name__)


def file_sha256(path: str | Path) -> str:
    """Compute SHA256 hash for a file."""
    file_path = Path(path).expanduser().resolve()
    hasher = hashlib.sha256()

    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)

    return hasher.hexdigest()


def load_yaml_config(config_path: str | Path) -> dict[str, Any]:
    """Load a YAML config file into a dictionary.

    Raises:
        FileNotFoundError:
            If the path does not exist.
        ValueError:
            If the file extension is not .yaml/.yml, if the path is not a file,
            if the top-level YAML object is not a mapping, or if top-level keys
            are not non-empty strings.
        yaml.YAMLError:
            If the file is not valid YAML.
    """
    path = Path(config_path).expanduser().resolve()

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    if not path.is_file():
        raise ValueError(f"Config path is not a file: {path}")

    if path.suffix.lower() not in {".yaml", ".yml"}:
        raise ValueError(f"Config file must be .yaml or .yml: {path}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except Exception:
        _LOGGER.exception("Failed to load YAML config: %s", path)
        raise

    if data is None:
        _LOGGER.debug("Loaded empty YAML config: %s", path)
        return {}

    if not isinstance(data, dict):
        raise ValueError(f"Top-level config must be a mapping/dictionary: {path}")

    for key in data:
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"Config keys must be non-empty strings: {path}")

    _LOGGER.debug(
        "Loaded YAML config: %s | top_level_keys=%d | sha256=%s",
        path,
        len(data),
        file_sha256(path),
    )

    return data