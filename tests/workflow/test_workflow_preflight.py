from __future__ import annotations

from pathlib import Path

from aeris.workflow.preflight import (
    build_operational_preflight_report,
    parse_float_list,
)


def test_parse_float_list_defaults_and_values() -> None:
    assert parse_float_list("", default=[1.0]) == [1.0]
    assert parse_float_list("1,2.5,-3", default=[0.0]) == [1.0, 2.5, -3.0]


def test_preflight_reports_case_count_for_medium_plan() -> None:
    report = build_operational_preflight_report(
        workflow_root=None,
        config=Path("configs/geometry/bwb_training_v1.yaml"),
        n_geometries=50,
        alpha_values=[-2.0, 0.0, 4.0, 8.0],
        beta_values=[0.0],
        velocity_values=[20.0, 28.0],
        altitude_values=[0.0, 1500.0],
        control_input_values=[-5.0, 0.0, 5.0],
    )

    assert report["estimated_aero_case_count"] == 50 * 4 * 1 * 2 * 2 * 3
    assert report["report_type"] == "workflow_operational_preflight"
    assert report["coverage_summary"]["all_required_stage_commands_covered"] is True


def test_preflight_blocks_missing_config() -> None:
    report = build_operational_preflight_report(
        workflow_root=None,
        config=Path("configs/geometry/does_not_exist.yaml"),
        n_geometries=1,
        alpha_values=[0.0],
        beta_values=[0.0],
        velocity_values=[28.0],
        altitude_values=[1500.0],
        control_input_values=[0.0],
    )

    assert report["readiness"] == "blocked"
    assert any("Config does not exist" in blocker for blocker in report["blockers"])
