"""Layered option engine: curated schemas, layer resolution, manifests."""

from aeris.cfd.options.layers import EffectiveOptions, OptionLayer, resolve_options
from aeris.cfd.options.manifest import (
    EFFECTIVE_OPTIONS_SCHEMA_VERSION,
    write_effective_options_manifest,
)
from aeris.cfd.options.schema import CuratedOption, ToolOptionSchema

__all__ = [
    "CuratedOption",
    "ToolOptionSchema",
    "OptionLayer",
    "EffectiveOptions",
    "resolve_options",
    "EFFECTIVE_OPTIONS_SCHEMA_VERSION",
    "write_effective_options_manifest",
]
