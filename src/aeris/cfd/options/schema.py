"""
Curated option schemas for external tools (pyHyp, ADflow, SU2, ...).

A ``CuratedOption`` describes one validated knob: its AERIS snake_case name,
the tool-native key it maps to, its type, the AERIS default (if any), a doc
string, a citation for why the default is what it is, and an optional value
validator.  A ``ToolOptionSchema`` bundles the curated options of one tool.

Curation is deliberately partial: only knobs AERIS has validated (or must
control) are curated.  Every other tool option reaches the tool through a
raw pass-through layer (see ``aeris.cfd.options.layers``), so users keep
full authority without AERIS mirroring entire third-party option catalogs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CuratedOption:
    """One validated tool option.

    ``default=None`` means AERIS ships no default for this option: the value
    is either computed at build time (e.g. from a grid level) or left to the
    tool's own default.
    """

    name: str
    native: str
    type_: type | tuple[type, ...]
    default: object = None
    doc: str = ""
    citation: str = ""
    validate: Callable[[object], str | None] | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.native:
            raise ValueError("CuratedOption requires non-empty name and native key")


@dataclass(frozen=True)
class ToolOptionSchema:
    """Curated option set for one external tool."""

    tool: str
    curated: tuple[CuratedOption, ...]
    by_name: dict[str, CuratedOption] = field(init=False, repr=False)
    by_native: dict[str, CuratedOption] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        by_name: dict[str, CuratedOption] = {}
        by_native: dict[str, CuratedOption] = {}
        for opt in self.curated:
            if opt.name in by_name:
                raise ValueError(f"[{self.tool}] duplicate curated option name {opt.name!r}")
            if opt.native in by_native:
                raise ValueError(f"[{self.tool}] duplicate curated native key {opt.native!r}")
            by_name[opt.name] = opt
            by_native[opt.native] = opt
        object.__setattr__(self, "by_name", by_name)
        object.__setattr__(self, "by_native", by_native)

    def aeris_defaults(self) -> dict[str, object]:
        """Aeris-default values keyed by aeris name (mutable containers copied)."""
        defaults: dict[str, object] = {}
        for opt in self.curated:
            if opt.default is None:
                continue
            value = opt.default
            if isinstance(value, dict):
                value = dict(value)
            elif isinstance(value, list):
                value = list(value)
            defaults[opt.name] = value
        return defaults
