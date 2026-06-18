"""Tests for physics-aligned QC threshold improvements.

Each test validates a specific physical rationale documented in the
AERIS QC Decision Document.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aeris.quality.pipeline_api import run_aero_dataset_qc, run_geometry_dataset_qc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_aero_ds(dataset_root: Path, rows: list[dict]) -> None:
    dataset_root.mkdir(parents=True, exist_ok=True)
    manifest = {"status": "success", "successful_aero_rows": len(rows)}
    (dataset_root / "aero_dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    pd.DataFrame(rows).to_csv(dataset_root / "aero_dataset.csv", index=False)


def _healthy_row(alpha=2.0, ctrl=0.0, cl=0.50, cd=0.025, cm=-0.08) -> dict:
    return {
        "geometry_id": "g1",
        "alpha_deg": alpha,
        "beta_deg": 0.0,
        "velocity_mps": 28.0,
        "altitude_m": 1500.0,
        "control_input_deg": ctrl,
        "delta_e_sym_deg": ctrl,
        "delta_a_diff_deg": 0.0,
        "cl": cl,
        "cd": cd,
        "cm": cm,
        "cy": 0.0,
        "cl_roll": 0.0,
        "cn": 0.0,
        "geometry_declares_controls": True,
        "airplane_has_controls": True,
        "diag_airplane_has_control_surfaces": True,
        "diag_airplane_avl_has_control_blocks": True,
        "diag_keystrokes_has_d1_command": True,
        "diag_stdout_control_variables": 1,
    }


def _three_ctrl_rows(alpha=2.0):
    """Minimal valid 3-control sweep for one alpha."""
    return [
        _healthy_row(alpha=alpha, ctrl=-5.0, cl=0.48, cd=0.024, cm=-0.06),
        _healthy_row(alpha=alpha, ctrl= 0.0, cl=0.50, cd=0.025, cm=-0.08),
        _healthy_row(alpha=alpha, ctrl=+5.0, cl=0.52, cd=0.026, cm=-0.10),
    ]


def _make_geom_ds(dataset_root: Path, rows: list[dict]) -> None:
    from pathlib import Path as P
    dataset_root.mkdir(parents=True, exist_ok=True)
    manifest = {"status": "success", "requested_n": len(rows),
                "attempted_n": len(rows), "succeeded_n": len(rows), "failed_n": 0}
    (dataset_root / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    pd.DataFrame(rows).to_csv(dataset_root / "metadata.csv", index=False)


def _touch(p: Path) -> str:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    return str(p)


def _healthy_geom_row(dataset_root: Path, gid: str = "g1") -> dict:
    root = dataset_root / "geometry" / gid
    ar = (3.2 ** 2) / 1.7
    return {
        "geometry_id": gid,
        "c1_m": 1.60, "c2_ratio": 0.60, "c3_ratio": 0.40, "c4_ratio": 0.15,
        "b_total_m": 1.60, "b3_ratio": 0.50, "split_ratio": 0.45,
        "sw1_deg": -40.0, "sw2_deg": -25.0, "sw3_deg": -10.0,
        "twist_b0_deg": 0.0, "twist_b1_deg": -2.0, "twist_b2_deg": -3.0, "twist_b3_deg": -4.0,
        "dihedral_b1_deg": 2.0, "dihedral_b2_deg": 4.0, "dihedral_b3_deg": 6.0,
        "semi_span_m": 1.60, "full_span_m": 3.20, "approx_area_m2": 1.70,
        "approx_aspect_ratio_planform": ar,
        "aspect_ratio_aerosandbox": ar + 0.05,
        "summary_path": _touch(root / "geometry_summary.json"),
        "control_points_path": _touch(root / "control_points.csv"),
        "planform_sections_path": _touch(root / "planform_sections.csv"),
        "section_3d_path": _touch(root / "section_3d.csv"),
    }


# ===========================================================================
# A7a: Zero drag is valid for inviscid AVL
# ===========================================================================

def test_a7a_zero_drag_is_valid_for_inviscid_solver(tmp_path: Path) -> None:
    """A7a: cd=0.0 must NOT trigger an error.

    Physical basis: AVL produces CDi = CL²/(π·AR·e). At the zero-lift angle of
    attack (α ≈ -4° for NACA 4412), CL=0 exactly and therefore CDi=0 exactly.
    Rejecting cd=0 would incorrectly flag physically valid data.
    """
    rows = _three_ctrl_rows(alpha=0.0)
    rows[1]["cd"] = 0.0   # zero-lift operating point: CDi = 0 exactly
    _make_aero_ds(tmp_path / "ds", rows)
    report = run_aero_dataset_qc(tmp_path / "ds", profile="basic")
    cd_errors = [e for e in report.get("errors", []) if "CD" in e and "egative" in e]
    assert cd_errors == [], f"cd=0.0 must not be flagged as error: {cd_errors}"


def test_a7a_negative_drag_is_still_an_error(tmp_path: Path) -> None:
    """A7a: cd < 0 must still be an error (sign convention failure)."""
    rows = _three_ctrl_rows()
    rows[0]["cd"] = -0.005
    _make_aero_ds(tmp_path / "ds", rows)
    report = run_aero_dataset_qc(tmp_path / "ds", profile="basic")
    assert report["passed"] is False
    assert any("Negative CD" in e for e in report["errors"])


# ===========================================================================
# A7b: |CL| threshold tightened 5 → 3
# ===========================================================================

def test_a7b_cl_between_1p5_and_3_passes(tmp_path: Path) -> None:
    """A7b: CL in (1.5, 3.0) should now pass — previously was an error at >5.

    Physical basis: actual max CL for BWB at α=+8° is ~1.5. Threshold 3.0
    provides a 2× safety margin while still blocking genuine blowups.
    This test verifies we haven't tightened so hard that realistic extreme
    conditions (e.g. control fully deployed at high alpha) become errors.
    """
    rows = _three_ctrl_rows(alpha=8.0)
    rows[0]["cl"] = 2.0   # above physical max but below new threshold
    _make_aero_ds(tmp_path / "ds", rows)
    report = run_aero_dataset_qc(tmp_path / "ds", profile="basic")
    cl_errors = [e for e in report.get("errors", []) if "CL" in e and "bsurd" in e]
    assert cl_errors == [], f"CL=2.0 should pass new threshold of 3.0: {cl_errors}"


def test_a7b_cl_above_3_is_an_error(tmp_path: Path) -> None:
    """A7b: CL > 3.0 must be an error (AVL blowup)."""
    rows = _three_ctrl_rows()
    rows[0]["cl"] = 3.5
    _make_aero_ds(tmp_path / "ds", rows)
    report = run_aero_dataset_qc(tmp_path / "ds", profile="basic")
    assert report["passed"] is False
    assert any("CL" in e and "bsurd" in e for e in report["errors"])


# ===========================================================================
# A7c: |Cm| threshold tightened 5 → 2
# ===========================================================================

def test_a7c_cm_between_0p8_and_2_passes(tmp_path: Path) -> None:
    """A7c: Cm in (-2.0, 2.0) must pass.

    Physical basis: NACA 4412 Cm_ac ≈ -0.10; with twist and elevon ±15°
    the worst-case Cm ≈ ±0.8. Threshold 2.0 gives >2× margin.
    """
    rows = _three_ctrl_rows()
    rows[0]["cm"] = -1.5  # extreme but below new threshold
    _make_aero_ds(tmp_path / "ds", rows)
    report = run_aero_dataset_qc(tmp_path / "ds", profile="basic")
    cm_errors = [e for e in report.get("errors", []) if "Cm" in e and "bsurd" in e]
    assert cm_errors == [], f"Cm=-1.5 should pass new threshold of 2.0: {cm_errors}"


def test_a7c_cm_above_2_is_an_error(tmp_path: Path) -> None:
    """A7c: |Cm| > 2.0 must be an error."""
    rows = _three_ctrl_rows()
    rows[0]["cm"] = 2.5
    _make_aero_ds(tmp_path / "ds", rows)
    report = run_aero_dataset_qc(tmp_path / "ds", profile="basic")
    assert report["passed"] is False
    assert any("Cm" in e and "bsurd" in e for e in report["errors"])


# ===========================================================================
# A9: Cmδe sign check
# ===========================================================================

def test_a9_correct_negative_cmde_passes(tmp_path: Path) -> None:
    """A9: dCm/d(ctrl) < 0 must pass (trailing-edge elevon ↓ → nose-down Cm)."""
    rows = []
    for alpha in [0.0, 2.0, 4.0]:
        for ctrl, cm in [(-5.0, -0.05), (0.0, -0.08), (5.0, -0.11)]:
            rows.append(_healthy_row(alpha=alpha, ctrl=ctrl, cm=cm))
    _make_aero_ds(tmp_path / "ds", rows)
    report = run_aero_dataset_qc(tmp_path / "ds", profile="strict")
    sign_errors = [e for e in report.get("errors", []) if "sign" in e.lower() and "Cm" in e]
    assert sign_errors == [], f"Correct negative Cmde should not error: {sign_errors}"


def test_a9_positive_cmde_is_an_error(tmp_path: Path) -> None:
    """A9: dCm/d(ctrl) > 0 must be an error (inverted elevon sign convention)."""
    rows = []
    for alpha in [0.0, 2.0, 4.0]:
        # Positive slope: more positive control → more positive (nose-up) Cm
        for ctrl, cm in [(-5.0, -0.11), (0.0, -0.08), (5.0, -0.05)]:
            rows.append(_healthy_row(alpha=alpha, ctrl=ctrl, cm=cm))
    _make_aero_ds(tmp_path / "ds", rows)
    report = run_aero_dataset_qc(tmp_path / "ds", profile="strict")
    sign_errors = [e for e in report.get("errors", []) if "sign" in e.lower() or "inverted" in e.lower()]
    assert len(sign_errors) > 0, (
        f"Positive Cmde (inverted elevon) must be flagged as error. "
        f"errors={report['errors']}"
    )


# ===========================================================================
# A11b: L/D threshold and near-zero-lift exclusion
# ===========================================================================

def test_a11b_high_ld_at_low_alpha_is_warning_not_error(tmp_path: Path) -> None:
    """A11b: High L/D at near-zero-lift must NOT be an error.

    Physical basis: AVL inviscid → CDi → 0 near zero-lift alpha.
    At CL=0.05, CDi≈0.0002 → L/D=250. This is physically correct.
    Old threshold (200, ERROR) would have rejected valid data.
    New behaviour: WARNING at 500, and rows with |CL|<0.05 are excluded.
    """
    rows = _three_ctrl_rows()
    # Near-zero-lift: CL=0.04, CD=0.0001 → L/D=400 (above old 200 threshold)
    rows[1]["cl"] = 0.04
    rows[1]["cd"] = 0.0001
    _make_aero_ds(tmp_path / "ds", rows)
    report = run_aero_dataset_qc(tmp_path / "ds", profile="strict")
    ld_errors = [e for e in report.get("errors", []) if "L/D" in e and ("large" in e or ">200" in e)]
    assert ld_errors == [], (
        f"L/D at near-zero-lift must not be an error: {ld_errors}\n"
        f"full errors: {report['errors']}"
    )


def test_a11b_genuine_ld_blowup_above_500_is_a_warning(tmp_path: Path) -> None:
    """A11b: |L/D| > 500 at non-near-zero-lift must be a WARNING."""
    rows = _three_ctrl_rows()
    # High CL, near-zero CD: L/D >> 500
    rows[0]["cl"] = 1.0
    rows[0]["cd"] = 0.001   # CDi should be ~0.04 for AR=3.7, CL=1.0; 0.001 is blowup
    _make_aero_ds(tmp_path / "ds", rows)
    report = run_aero_dataset_qc(tmp_path / "ds", profile="strict")
    ld_warnings = [w for w in report.get("warnings", []) if "L/D" in w and "500" in w]
    assert len(ld_warnings) > 0, (
        f"L/D blowup (L/D=1000) must trigger a WARNING. "
        f"warnings={report['warnings']}, errors={report['errors']}"
    )
    ld_errors = [e for e in report.get("errors", []) if "L/D" in e and "large" in e]
    assert ld_errors == [], f"L/D blowup should be WARNING not ERROR: {ld_errors}"


# ===========================================================================
# G7b: AR bounds [1.0, 20.0] → [1.5, 8.0]
# ===========================================================================

def test_g7b_ar_in_bwb_range_passes(tmp_path: Path) -> None:
    """G7b: AR=6.0 (within BWB design space) must pass strict geometry QC."""
    row = _healthy_geom_row(tmp_path / "ds")
    # AR = 3.2²/1.7 = 6.02 — within [1.5, 8.0]
    _make_geom_ds(tmp_path / "ds", [row])
    report = run_geometry_dataset_qc(tmp_path / "ds", profile="strict")
    ar_errors = [e for e in report.get("errors", []) if "aspect ratio" in e.lower()]
    assert ar_errors == [], f"AR=6.0 must pass new bounds [1.5, 8.0]: {ar_errors}"


def test_g7b_ar_above_8_is_an_error(tmp_path: Path) -> None:
    """G7b: AR > 8.0 must be an error (outside BWB design space)."""
    row = _healthy_geom_row(tmp_path / "ds")
    row["approx_aspect_ratio_planform"] = 9.5
    row["full_span_m"] = 4.0
    row["approx_area_m2"] = 1.70
    _make_geom_ds(tmp_path / "ds", [row])
    report = run_geometry_dataset_qc(tmp_path / "ds", profile="strict")
    assert report["passed"] is False
    ar_errors = [e for e in report["errors"] if "aspect ratio" in e.lower()]
    assert len(ar_errors) > 0, f"AR=9.5 must fail G7b. errors={report['errors']}"


def test_g7b_ar_below_1p5_is_an_error(tmp_path: Path) -> None:
    """G7b: AR < 1.5 must be an error (degenerate planform / unit error)."""
    row = _healthy_geom_row(tmp_path / "ds")
    row["approx_aspect_ratio_planform"] = 1.2
    _make_geom_ds(tmp_path / "ds", [row])
    report = run_geometry_dataset_qc(tmp_path / "ds", profile="strict")
    assert report["passed"] is False


# ===========================================================================
# Twist/dihedral range validator
# ===========================================================================

def test_twist_dihedral_within_bounds_passes(tmp_path: Path) -> None:
    """Twist/dihedral within physical bounds must pass strict geometry QC."""
    row = _healthy_geom_row(tmp_path / "ds")
    # All twist in [-4, 0], dihedral in [0, 6] — well within limits
    _make_geom_ds(tmp_path / "ds", [row])
    report = run_geometry_dataset_qc(tmp_path / "ds", profile="strict")
    td_errors = [e for e in report.get("errors", []) if "Twist" in e or "Dihedral" in e]
    assert td_errors == [], f"Valid twist/dihedral must pass: {td_errors}"


def test_absurd_twist_is_an_error(tmp_path: Path) -> None:
    """Twist > 15° must be flagged — indicates unit error or sampler escape."""
    row = _healthy_geom_row(tmp_path / "ds")
    row["twist_b3_deg"] = -20.0   # likely a unit error (radians vs degrees)
    _make_geom_ds(tmp_path / "ds", [row])
    report = run_geometry_dataset_qc(tmp_path / "ds", profile="strict")
    assert report["passed"] is False
    assert any("Twist" in e for e in report["errors"])


def test_absurd_dihedral_is_an_error(tmp_path: Path) -> None:
    """Dihedral > 25° must be flagged — outside any realistic BWB config."""
    row = _healthy_geom_row(tmp_path / "ds")
    row["dihedral_b3_deg"] = 30.0
    _make_geom_ds(tmp_path / "ds", [row])
    report = run_geometry_dataset_qc(tmp_path / "ds", profile="strict")
    assert report["passed"] is False
    assert any("Dihedral" in e for e in report["errors"])


def test_twist_dihedral_validator_in_strict_not_basic(tmp_path: Path) -> None:
    """geometry_twist_dihedral_ranges_v1 must be in strict profile, not basic."""
    row = _healthy_geom_row(tmp_path / "ds")
    _make_geom_ds(tmp_path / "ds", [row])

    basic_report  = run_geometry_dataset_qc(tmp_path / "ds", profile="basic")
    strict_report = run_geometry_dataset_qc(tmp_path / "ds", profile="strict")

    basic_ids  = {c["validator_id"] for c in basic_report["checks"]}
    strict_ids = {c["validator_id"] for c in strict_report["checks"]}

    assert "geometry_twist_dihedral_ranges_v1" not in basic_ids
    assert "geometry_twist_dihedral_ranges_v1" in strict_ids
