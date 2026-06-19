"""Verify polar-bridge fields flow from aero_result scalars into the dataset row."""
from __future__ import annotations

from aeris.dataset.aero_dataset_run import _flatten_success_row


def _payload() -> dict:
    return {
        "status": "success",
        "runtime_sec": 1.0,
        "scalars": {
            "cl": 0.4,
            "cd": 0.02,
            "cm": -0.01,
            "cd_ind": 0.008,
            "l_over_d": 20.0,
            "x_np": 0.3,
            "cd_profile": 0.011,
            "cd_total": 0.019,
            "l_over_d_viscous": 21.05,
        },
        "solver_metadata": {
            "profile_drag_n_extrapolated_strips": 3,
            "profile_drag_cd_total_vs_avl_cdtot_rel_diff": 0.04,
        },
        "failure": None,
    }


def _sweep_case() -> dict:
    return {
        "case_label": "c0",
        "case_index": 0,
        "control_input_deg": 0.0,
        "diff_input_deg": 0.0,
        "flight_condition": {
            "alpha_deg": 2.0,
            "beta_deg": 0.0,
            "velocity_mps": 28.0,
            "altitude_m": 1500.0,
            "p_rad_s": 0.0,
            "q_rad_s": 0.0,
            "r_rad_s": 0.0,
        },
    }


def test_profile_drag_columns_present_in_row():
    row = _flatten_success_row(
        geometry_row={"geometry_id": "g1", "c1_m": 1.6},
        sweep_case=_sweep_case(),
        aero_payload=_payload(),
    )
    assert row["cd_profile"] == 0.011
    assert row["cd_total"] == 0.019
    assert row["l_over_d_viscous"] == 21.05
    assert row["profile_drag_n_extrapolated_strips"] == 3
    assert row["profile_drag_cd_total_vs_avl_cdtot_rel_diff"] == 0.04


def test_profile_drag_columns_none_when_bridge_off():
    payload = _payload()
    payload["scalars"].pop("cd_total")
    payload["scalars"].pop("cd_profile")
    payload["scalars"].pop("l_over_d_viscous")
    payload["solver_metadata"] = {}
    row = _flatten_success_row(
        geometry_row={"geometry_id": "g1", "c1_m": 1.6},
        sweep_case=_sweep_case(),
        aero_payload=payload,
    )
    assert row["cd_total"] is None
    assert row["cd_profile"] is None
    assert row["profile_drag_n_extrapolated_strips"] is None
