from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from aeris.aero.models import FlightCondition
from aeris.aero.sweep_io import build_aero_sweep_summary, write_aero_sweep_manifest


def _records() -> list[dict]:
    rows = []
    for control_input_deg, cm in [(-5.0, 0.05), (0.0, 0.0), (5.0, -0.05)]:
        rows.append(
            {
                "case_label": f"ctrl_{control_input_deg:+.1f}",
                "case_dir": f"/tmp/ctrl_{control_input_deg:+.1f}",
                "status": "success",
                "alpha_deg": 0.0,
                "beta_deg": 0.0,
                "velocity_mps": 28.0,
                "altitude_m": 1500.0,
                "p_rad_s": 0.0,
                "q_rad_s": 0.0,
                "r_rad_s": 0.0,
                "control_input_deg": control_input_deg,
                "cl": 0.40 + 0.01 * control_input_deg,
                "cd": 0.03,
                "cm": cm,
            }
        )
    return rows


def test_sweep_summary_exposes_explicit_control_aliases() -> None:
    records = _records()
    fcs = [FlightCondition(alpha_deg=0.0, velocity_mps=28.0, altitude_m=1500.0) for _ in records]

    summary = build_aero_sweep_summary(fcs, records)

    assert summary["control_input_deg_values"] == [-5.0, 0.0, 5.0]
    assert summary["delta_e_sym_deg_values"] == [-5.0, 0.0, 5.0]
    assert summary["delta_a_diff_deg_values"] == [0.0]

    assert summary["control_metadata"]["legacy_aliases"]["control_input_deg"] == "delta_e_sym_deg"

    rows = summary["control_effectiveness_rows"]
    assert rows
    assert all("delta_e_sym_deg" in row for row in rows)
    assert all("delta_a_diff_deg" in row for row in rows)


def test_sweep_manifest_writes_case_aliases(tmp_path: Path) -> None:
    records = _records()
    fcs = [FlightCondition(alpha_deg=0.0, velocity_mps=28.0, altitude_m=1500.0) for _ in records]
    summary = build_aero_sweep_summary(fcs, records)

    out = tmp_path / "aero_sweep_manifest.json"
    write_aero_sweep_manifest(
        out,
        SimpleNamespace(cases=records, summary=summary),
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    sweep = payload["aero_sweep_result"]

    assert sweep["summary"]["control_metadata"]["legacy_aliases"]["control_input_deg"] == "delta_e_sym_deg"

    first = sweep["cases"][0]
    assert first["control_input_deg"] == -5.0
    assert first["delta_e_sym_deg"] == -5.0
    assert first["delta_a_diff_deg"] == 0.0
