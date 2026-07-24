"""QC gate over the pyGeo->AVL viscous cross-check (pure logic, no deps).

Importing pygeo_avl_adapter needs neither pygeo, aerosandbox, nor neuralfoil
(those are lazy), so this always runs in CI.
"""

from __future__ import annotations

from types import SimpleNamespace

from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import summarize_pygeo_avl_qc


def _result(rel_diff=None, n_extrap=None, cd_avl=0.012, cd_total=0.0122):
    return SimpleNamespace(
        solver_metadata={
            "profile_drag_cd_total_vs_avl_cdtot_rel_diff": rel_diff,
            "profile_drag_n_extrapolated_strips": n_extrap,
            "cd_avl_cdtot": cd_avl,
        },
        cd_total=cd_total,
    )


def test_qc_passes_within_tolerance() -> None:
    q = summarize_pygeo_avl_qc(_result(rel_diff=0.041, n_extrap=0))
    assert q["pass"] is True
    assert q["drag_agreement_ok"] and q["reliability_ok"]
    assert q["drag_agreement_rel_diff"] == 0.041


def test_qc_fails_on_drag_disagreement() -> None:
    q = summarize_pygeo_avl_qc(_result(rel_diff=0.20, n_extrap=0))
    assert q["pass"] is False
    assert q["drag_agreement_ok"] is False
    assert q["reliability_ok"] is True


def test_qc_fails_on_extrapolated_strips() -> None:
    q = summarize_pygeo_avl_qc(_result(rel_diff=0.02, n_extrap=3))
    assert q["pass"] is False
    assert q["reliability_ok"] is False
    assert q["drag_agreement_ok"] is True


def test_qc_tolerances_are_configurable() -> None:
    r = _result(rel_diff=0.12, n_extrap=2)
    assert summarize_pygeo_avl_qc(r)["pass"] is False
    q = summarize_pygeo_avl_qc(r, drag_agreement_tol=0.15, max_extrapolated_strips=5)
    assert q["pass"] is True


def test_qc_tolerant_of_missing_metadata() -> None:
    # No polar bridge ran (inviscid) — nothing to gate, should pass.
    q = summarize_pygeo_avl_qc(SimpleNamespace(solver_metadata={}, cd_total=None))
    assert q["pass"] is True
    assert q["drag_agreement_rel_diff"] is None
