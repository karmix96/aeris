"""
Layered option resolution with per-key provenance.

Layers are applied in order; later layers win.  The canonical order is:

    aeris-default < level/preset < derived < user config < CLI < raw

Non-raw layers use AERIS snake_case names and are validated against the
tool's curated schema — an unknown name is an error (typo protection), a
type or validator failure is an error.  A ``raw`` layer uses tool-native
keys verbatim with no validation: this is the user's escape hatch to any
option the tool supports.  A raw key that shadows a curated key still wins
(user authority is absolute) but is recorded as a warning and listed in
``overridden_curated_keys`` so the bypass is traceable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from aeris.cfd.options.schema import CuratedOption, ToolOptionSchema

AERIS_DEFAULT_SOURCE = "aeris-default"
RAW_SOURCE = "raw"


@dataclass(frozen=True)
class OptionLayer:
    """One source of option values.

    ``raw=True`` layers carry tool-native keys and bypass validation;
    all other layers carry curated aeris names.  ``None`` values mean
    "not set here" and are skipped, so optional CLI flags can forward
    unconditionally.
    """

    source: str
    values: Mapping[str, object]
    raw: bool = False


@dataclass(frozen=True)
class EffectiveOptions:
    """Fully resolved, tool-native options plus per-key provenance."""

    tool: str
    values: dict[str, object]
    provenance: dict[str, str]
    warnings: tuple[str, ...] = ()
    overridden_curated_keys: tuple[str, ...] = field(default=())


def aeris_defaults_layer(schema: ToolOptionSchema) -> OptionLayer:
    return OptionLayer(AERIS_DEFAULT_SOURCE, schema.aeris_defaults())


def _type_matches(value: object, type_: type | tuple[type, ...]) -> bool:
    # bool is an int subclass in Python; keep the two strictly apart so a
    # stray True never lands in an integer tool option (and vice versa).
    if type_ is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_ is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if type_ is bool:
        return isinstance(value, bool)
    return isinstance(value, type_)


def _check_curated(
    schema: ToolOptionSchema, opt: CuratedOption, value: object, source: str
) -> None:
    if not _type_matches(value, opt.type_):
        raise ValueError(
            f"[{schema.tool} options] {opt.name}={value!r} from {source!r} has type "
            f"{type(value).__name__}, expected {opt.type_}"
        )
    if opt.validate is not None:
        message = opt.validate(value)
        if message:
            raise ValueError(
                f"[{schema.tool} options] invalid {opt.name}={value!r} from {source!r}: {message}"
            )


def resolve_options(schema: ToolOptionSchema, layers: Sequence[OptionLayer]) -> EffectiveOptions:
    """Merge layers in order into tool-native options with provenance."""
    values: dict[str, object] = {}
    provenance: dict[str, str] = {}
    warnings: list[str] = []
    overridden: list[str] = []

    for layer in layers:
        for key, value in layer.values.items():
            if value is None:
                continue
            if layer.raw:
                native = key
                curated = schema.by_native.get(native)
                if curated is not None:
                    warnings.append(
                        f"raw pass-through key {native!r} overrides curated option "
                        f"{curated.name!r} (validation bypassed)"
                    )
                    if curated.name not in overridden:
                        overridden.append(curated.name)
            else:
                opt = schema.by_name.get(key)
                if opt is None:
                    known = ", ".join(sorted(schema.by_name))
                    raise ValueError(
                        f"[{schema.tool} options] unknown option {key!r} in layer "
                        f"{layer.source!r}. Curated options: {known}. Use the raw "
                        f"pass-through layer for native tool options."
                    )
                _check_curated(schema, opt, value, layer.source)
                native = opt.native
            values[native] = value
            provenance[native] = layer.source

    return EffectiveOptions(
        tool=schema.tool,
        values=values,
        provenance=provenance,
        warnings=tuple(warnings),
        overridden_curated_keys=tuple(overridden),
    )
