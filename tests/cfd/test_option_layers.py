"""Layered option resolution: order, provenance, raw pass-through, validation."""

from __future__ import annotations

import pytest

from aeris.cfd.options.layers import OptionLayer, aeris_defaults_layer, resolve_options
from aeris.cfd.options.schema import CuratedOption, ToolOptionSchema


def _positive(value: object) -> str | None:
    return None if float(value) > 0 else "must be > 0"  # type: ignore[arg-type]


TOY = ToolOptionSchema(
    tool="toy",
    curated=(
        CuratedOption("c_max", "cMax", float, 0.7, validate=_positive),
        CuratedOption("n_grid", "N", int),
        CuratedOption("family", "families", str, "wall"),
        CuratedOption("auto", "autoConnect", bool, True),
    ),
)


def test_later_layers_win_and_provenance_is_recorded():
    effective = resolve_options(
        TOY,
        [
            aeris_defaults_layer(TOY),
            OptionLayer("preset:smoke", {"c_max": 0.5, "n_grid": 129}),
            OptionLayer("cli", {"c_max": 0.6}),
        ],
    )
    assert effective.values == {"cMax": 0.6, "N": 129, "families": "wall", "autoConnect": True}
    assert effective.provenance == {
        "cMax": "cli",
        "N": "preset:smoke",
        "families": "aeris-default",
        "autoConnect": "aeris-default",
    }
    assert effective.warnings == ()
    assert effective.overridden_curated_keys == ()


def test_none_values_are_skipped():
    effective = resolve_options(
        TOY,
        [
            aeris_defaults_layer(TOY),
            OptionLayer("cli", {"c_max": None, "n_grid": 65}),
        ],
    )
    assert effective.values["cMax"] == 0.7
    assert effective.provenance["cMax"] == "aeris-default"
    assert effective.values["N"] == 65


def test_raw_layer_passes_native_keys_verbatim():
    effective = resolve_options(
        TOY,
        [aeris_defaults_layer(TOY), OptionLayer("raw", {"splay": 0.25}, raw=True)],
    )
    assert effective.values["splay"] == 0.25
    assert effective.provenance["splay"] == "raw"
    assert effective.warnings == ()


def test_raw_shadowing_curated_wins_but_warns():
    effective = resolve_options(
        TOY,
        [aeris_defaults_layer(TOY), OptionLayer("raw", {"cMax": -5.0}, raw=True)],
    )
    # user authority is absolute: the (invalid-by-curated-rules) value lands
    assert effective.values["cMax"] == -5.0
    assert effective.provenance["cMax"] == "raw"
    assert effective.overridden_curated_keys == ("c_max",)
    assert any("cMax" in w and "bypassed" in w for w in effective.warnings)


def test_unknown_aeris_name_raises():
    with pytest.raises(ValueError, match="unknown option 'c_mxa'"):
        resolve_options(TOY, [OptionLayer("cli", {"c_mxa": 0.5})])


def test_type_mismatch_raises_and_bool_is_not_int():
    with pytest.raises(ValueError, match="expected"):
        resolve_options(TOY, [OptionLayer("cli", {"n_grid": 1.5})])
    with pytest.raises(ValueError, match="expected"):
        resolve_options(TOY, [OptionLayer("cli", {"n_grid": True})])
    # ints are acceptable where floats are expected
    effective = resolve_options(TOY, [OptionLayer("cli", {"c_max": 1})])
    assert effective.values["cMax"] == 1


def test_validator_failure_raises_with_field_name():
    with pytest.raises(ValueError, match="c_max=-1.0"):
        resolve_options(TOY, [OptionLayer("cli", {"c_max": -1.0})])


def test_duplicate_curated_names_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        ToolOptionSchema(
            tool="bad",
            curated=(
                CuratedOption("c_max", "cMax", float),
                CuratedOption("c_max", "cMax2", float),
            ),
        )


def test_mutable_defaults_are_copied_per_call():
    schema = ToolOptionSchema(tool="mut", curated=(CuratedOption("bc", "BC", dict, {}),))
    first = schema.aeris_defaults()
    first["bc"]["wall"] = 1
    assert schema.aeris_defaults() == {"bc": {}}
