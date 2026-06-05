from __future__ import annotations

from aeris.aero.control_metadata import (
    CONTROL_METADATA_SCHEMA_VERSION,
    control_alias_row,
    default_control_metadata,
)


def test_default_control_metadata_names_legacy_alias() -> None:
    meta = default_control_metadata()

    assert meta["schema_version"] == CONTROL_METADATA_SCHEMA_VERSION
    assert meta["legacy_aliases"]["control_input_deg"] == "delta_e_sym_deg"
    assert "delta_e_sym_deg" in meta["variables"]
    assert "delta_a_diff_deg" in meta["variables"]
    assert meta["variables"]["delta_a_diff_deg"]["status"] == "reserved_not_solver_wired_yet"


def test_control_alias_row_keeps_backward_compatibility() -> None:
    row = control_alias_row(-5.0)

    assert row["control_input_deg"] == -5.0
    assert row["delta_e_sym_deg"] == -5.0
    assert row["delta_a_diff_deg"] == 0.0


def test_control_alias_row_accepts_none() -> None:
    row = control_alias_row(None)

    assert row["control_input_deg"] is None
    assert row["delta_e_sym_deg"] is None
    assert row["delta_a_diff_deg"] == 0.0
