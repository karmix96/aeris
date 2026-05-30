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

__all__ = [
    "load_yaml_config",
    "file_sha256",
]

_LOGGER = logging.getLogger(__name__)


def file_sha256(path: str | Path) -> str:
    """Compute the SHA256 hex digest of a file.

    Reads the file in 1 MiB chunks to bound memory usage on large inputs.

    Raises:
        FileNotFoundError: if the path does not exist.
        OSError: if the file cannot be read.
    """
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
        OSError:
            If the file cannot be opened or read.
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
    except yaml.YAMLError:
        _LOGGER.exception("Invalid YAML syntax in config: %s", path)
        raise
    except OSError:
        _LOGGER.exception("Filesystem error loading config: %s", path)
        raise

    if data is None:
        _LOGGER.info("Loaded empty YAML config: %s", path)
        return {}

    if not isinstance(data, dict):
        raise ValueError(f"Top-level config must be a mapping/dictionary: {path}")

    for key in data:
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"Config keys must be non-empty strings: {path}")

    _LOGGER.info(
        "Loaded YAML config: %s | top_level_keys=%d",
        path,
        len(data),
    )

    # SHA256 is expensive (full file read). Only compute it when DEBUG is active
    # or when an explicit caller asks via file_sha256() — e.g. the manifest writer.
    if _LOGGER.isEnabledFor(logging.DEBUG):
        _LOGGER.debug(
            "Config sha256: %s | %s",
            file_sha256(path),
            path,
        )

    return data