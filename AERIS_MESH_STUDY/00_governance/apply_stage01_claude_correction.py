#!/usr/bin/env python3
# ruff: noqa: E501
"""Apply the Stage 01 correction from the Claude threshold audit."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

REPORT_PATHS = [
    Path("AERIS_MESH_STUDY/00_governance/stage_01_report.md"),
    Path("AERIS_MESH_STUDY/reports/stage_01_report.md"),
]


OLD_DECISION = "Stage 01 is not approval-ready. Do not begin Stage 02. The current failure finding rests on real marches of lhs7_00 only; `epse_calibration_report.json` is dry-run packaging evidence, not volume-quality evidence. Post-gate follow-up has now found a missing surface validity check, fixed it, re-audited the locked L3 surfaces under the tightened gate, and diagnosed the upstream lhs7_00 tip-section cause. The L1 prevalence and L3 overnight commands remain prepared only and should stay on hold until a Stage 01 replan explicitly reauthorizes them."

NEW_DECISION = "Stage 01 is not approval-ready. Do not begin Stage 02. The current failure finding rests on real marches of lhs7_00 only; `epse_calibration_report.json` is dry-run packaging evidence, not volume-quality evidence. Post-gate follow-up found a missing surface validity check and fixed it. The unsupported shape/angle threshold tightening was rescinded, so Stage 01 is blocked at the cap4/pyHyp volume gate and upstream lhs7_00 tip-section geometry, not at surface generation."

OLD_POST_GATE_BLOCK = """- Surface acceptance now enforces `min_scaled_jacobian > 0.0` as a hard pre-pyHyp failure, with Variant B represented by a regression test.
- ADR-0005 tightened the Stage 01 cap4 surface policy to `min_shape_metric > 0.03`, `min_scaled_jacobian > 0.0`, and `max_adjacent_normal_angle_deg <= 170.0`.
- Locked L3 surface re-audit under the fixed gate: 10/10 locked seed-7 surfaces fail; all fail by `minimum_shape_metric`, and none of those ten fail the new positive scaled-Jacobian check.
- Upstream tip-section cause diagnostic for lhs7_00: the global worst cell is `tip_center_0` at `leading_edge_shoulder_lower_side`, with a worst-corner angle of 179.737357 deg. The trailing-edge shoulder is secondary, not the primary cause.
- New artifacts: `03_cap4_epse/locked_l3_surface_reaudit_fixed_gate.json`, `03_cap4_epse/locked_l3_surface_reaudit_fixed_gate.md`, `03_cap4_epse/lhs7_00_tip_section_cause_diagnostic.json`, and `03_cap4_epse/lhs7_00_tip_section_cause_diagnostic.md`.
- Prepared commands: `03_cap4_epse/prepared_stage01_commands.md`, currently on hold after the fixed-gate re-audit.
"""

NEW_POST_GATE_BLOCK = """- Surface acceptance now enforces `min_scaled_jacobian > 0.0` as a hard pre-pyHyp failure. Variant B in the tip-topology probe fails this corrected gate.
- ADR-0005 now accepts only the scaled-Jacobian enforcement. The unsupported `min_shape_metric > 0.03` and `max_adjacent_normal_angle_deg <= 170.0` changes were rescinded; Stage 01 recipes are restored to `min_shape_metric > 1.0e-6` and `max_adjacent_normal_angle_deg <= 180.0`.
- Corrected locked L3 surface re-audit: 0/10 locked seed-7 surfaces fail the current surface gate. The superseded 10/10 failure report was caused by the rejected post-hoc thresholds.
- Test coverage note: `test_surface_qc_rejects_negative_scaled_jacobian` is a mocked unit test for acceptance enforcement, not an end-to-end BWB folding regression.
- Upstream tip-section cause diagnostic for lhs7_00: the global worst cell is `tip_center_0` at `leading_edge_shoulder_lower_side`, with a worst-corner angle of 179.737357 deg. The trailing-edge shoulder is secondary, not the primary cause.
- New corrected artifacts: `03_cap4_epse/locked_l3_surface_reaudit_scaled_jac_only.json`, `03_cap4_epse/locked_l3_surface_reaudit_scaled_jac_only.md`, `03_cap4_epse/lhs7_00_tip_section_cause_diagnostic.json`, and `03_cap4_epse/lhs7_00_tip_section_cause_diagnostic.md`.
- Prepared commands: `03_cap4_epse/prepared_stage01_commands.md`, currently on hold pending Stage 01 replan.
"""


def update_reports() -> None:
    for path in REPORT_PATHS:
        text = path.read_text()
        if OLD_DECISION not in text:
            raise RuntimeError(f"decision block not found in {path}")
        if OLD_POST_GATE_BLOCK not in text:
            raise RuntimeError(f"post-gate block not found in {path}")
        path.write_text(
            text.replace(OLD_DECISION, NEW_DECISION).replace(
                OLD_POST_GATE_BLOCK, NEW_POST_GATE_BLOCK
            )
        )


def update_prepared_commands() -> None:
    path = Path("AERIS_MESH_STUDY/03_cap4_epse/prepared_stage01_commands.md")
    text = path.read_text()
    old = "Current status: HOLD after ADR-0005 and the fixed-gate locked-surface re-audit. Do not launch either command unless a Stage 01 replan explicitly reauthorizes it or replaces the surface policy. The referenced Stage 01 recipes now enforce min_shape_metric > 0.03, min_scaled_jacobian > 0.0, and max_adjacent_normal_angle_deg <= 170.0."
    new = "Current status: HOLD after the Claude/Codex threshold audit and corrected surface re-audit. Do not launch either command unless a Stage 01 replan explicitly reauthorizes it. The referenced Stage 01 recipes now use the restored study values min_shape_metric > 1.0e-6 and max_adjacent_normal_angle_deg <= 180.0, plus the hard min_scaled_jacobian > 0.0 validity floor."
    if old not in text:
        raise RuntimeError("prepared command hold text not found")
    path.write_text(text.replace(old, new))


def update_stage_status() -> None:
    path = Path("AERIS_MESH_STUDY/00_governance/stage_status.json")
    data = json.loads(path.read_text())
    data["updated_local"] = datetime.now().astimezone().isoformat(timespec="seconds")
    notes = []
    for note in data["notes"]:
        if note.startswith("ADR-0005 tightens Stage 01 cap4 surface policy"):
            notes.append(
                "ADR-0005 accepts only min_scaled_jacobian > 0.0 as a hard "
                "mathematical surface-validity floor; the post-hoc min_shape_metric "
                "0.03 and max normal angle 170.0 thresholds are rescinded."
            )
        elif note.startswith("Locked L3 surface re-audit with the fixed/tightened gate"):
            notes.append(
                "Corrected locked L3 surface re-audit with restored study shape/angle "
                "thresholds: 0/10 locked seed-7 surfaces fail surface QC; Variant B "
                "smooth20 probe fails positive_scaled_jacobian."
            )
        elif note.startswith(
            "Replan scope should be decided from the fixed surface-gate evidence"
        ):
            notes.append(
                "Replan scope should be decided from the corrected scaled-Jacobian "
                "gate evidence, volume-gate failures, and lhs7_00 upstream tip-section "
                "cause diagnostic; Stage 02 remains unauthorized."
            )
        else:
            notes.append(note)
    extra = (
        "Stage 01 is blocked at cap4/pyHyp volume quality and upstream tip-station "
        "boundary geometry, not at surface generation under the corrected surface gate."
    )
    if extra not in notes:
        notes.append(extra)
    data["notes"] = notes
    path.write_text(json.dumps(data, indent=2) + "\n")


def supersede_old_reaudit() -> None:
    old_json = Path("AERIS_MESH_STUDY/03_cap4_epse/locked_l3_surface_reaudit_fixed_gate.json")
    if old_json.exists():
        data = json.loads(old_json.read_text())
        data["status"] = "superseded"
        data["superseded_by"] = "locked_l3_surface_reaudit_scaled_jac_only.json"
        data["superseded_reason"] = (
            "Used unsupported post-hoc min_shape_metric 0.03 and "
            "max_adjacent_normal_angle_deg 170.0 thresholds; corrected policy "
            "restores 1e-6 and 180.0 and keeps only min_scaled_jacobian > 0.0."
        )
        old_json.write_text(json.dumps(data, indent=2) + "\n")
    old_md = Path("AERIS_MESH_STUDY/03_cap4_epse/locked_l3_surface_reaudit_fixed_gate.md")
    if old_md.exists():
        text = old_md.read_text()
        prefix = (
            "# SUPERSEDED\n\n"
            "This report used unsupported post-hoc min_shape_metric 0.03 and "
            "max normal angle 170.0 thresholds. Use "
            "locked_l3_surface_reaudit_scaled_jac_only.* instead.\n\n"
        )
        if not text.startswith("# SUPERSEDED"):
            old_md.write_text(prefix + text)


def main() -> None:
    update_reports()
    update_prepared_commands()
    update_stage_status()
    supersede_old_reaudit()
    print("applied Stage 01 Claude correction")


if __name__ == "__main__":
    main()
