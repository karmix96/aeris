"""Data-only presets: validated recipes shipped as YAML package data."""

from aeris.cfd.presets.registry import (
    PRESET_SCHEMA_VERSION,
    CfdPreset,
    get_preset,
    list_presets,
)

__all__ = ["PRESET_SCHEMA_VERSION", "CfdPreset", "get_preset", "list_presets"]
