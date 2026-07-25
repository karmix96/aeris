"""The 5-level ladder and the convergence machinery built on it."""

from __future__ import annotations

import math

import pytest

from aeris.mesh.fidelity import (
    LEVELS, P_REF, REFINEMENT_RATIO, cell_size_ratio, convergence_study,
    grid_convergence_index, level, observed_order, structured_params,
    unstructured_params,
)


def test_ladder_has_five_levels_at_a_constant_ratio():
    """A constant ratio is what Richardson/GCI assume. The old 3-level family
    drifted 1.449 -> 1.366; this must not."""
    assert len(LEVELS) == 5
    ratios = [LEVELS[k].h_ratio / LEVELS[k + 1].h_ratio for k in range(4)]
    for r in ratios:
        assert r == pytest.approx(REFINEMENT_RATIO, rel=1e-12)


def test_anchor_reproduces_the_validated_production_preset():
    s = structured_params("L2")
    assert s["points_per_side"] == P_REF == 97
    assert s["spanwise_panels"] == 8
    assert s["s0_frac"] == pytest.approx(4.4e-6, rel=1e-9)


def test_coarsest_reproduces_the_validated_smoke_preset():
    assert structured_params(0)["points_per_side"] == 49


def test_levels_get_finer_monotonically():
    pts = [structured_params(k)["points_per_side"] for k in range(5)]
    assert pts == sorted(pts)
    s0 = [structured_params(k)["s0_frac"] for k in range(5)]
    assert s0 == sorted(s0, reverse=True)  # finer mesh -> smaller wall spacing


def test_tip_cap_is_held_constant_and_says_so():
    """A deliberate departure from uniform refinement must be declared, because
    it affects how a GCI on this family may be read."""
    caps = {structured_params(k)["cap_wrap_points"] for k in range(5)}
    assert caps == {17}
    for k in range(5):
        assert structured_params(k)["uniform_refinement"] is False
        assert "cap" in structured_params(k)["uniform_refinement_note"]


def test_unstructured_tracks_the_same_ladder():
    """One level = one nominal cell size in BOTH families; that is what makes a
    structured-vs-unstructured comparison controlled rather than arbitrary."""
    hs = [unstructured_params(k, reference_length=1.0)["characteristic_length"]
          for k in range(5)]
    for a, b in zip(hs, hs[1:]):
        assert a / b == pytest.approx(REFINEMENT_RATIO, rel=1e-9)
    # and it matches the structured cell count at the anchor
    u = unstructured_params("L2", reference_length=1.0)
    assert u["cells_per_reference_length"] == pytest.approx(97.0, rel=1e-9)


def test_unstructured_boundary_layer_is_derived_not_chosen():
    """Layer count follows from first height, growth and target thickness, so it
    refines WITH the family instead of being a free knob."""
    for k in range(5):
        u = unstructured_params(k, reference_length=0.5)
        assert u["bl_thickness"] >= 0.02 * 0.5 * 0.99
        assert u["bl_layers"] >= 5
    coarse = unstructured_params(0, reference_length=0.5)
    fine = unstructured_params(4, reference_length=0.5)
    assert fine["first_layer_height"] < coarse["first_layer_height"]


def test_observed_order_recovers_a_known_second_order_sequence():
    exact = 1.0
    f = {k: exact + 0.05 * (REFINEMENT_RATIO ** (2 - k)) ** 2 for k in range(5)}
    p = observed_order(f[0], f[1], f[2])
    assert p == pytest.approx(2.0, abs=1e-6)


def test_gci_refuses_a_non_monotone_triplet():
    """Fabricating an order for an oscillating sequence would be worse than
    reporting nothing."""
    g = grid_convergence_index(1.0, 1.2, 0.9)
    assert g["converging"] is False
    assert g["observed_order"] is None
    assert g["gci_fine"] is None


def test_five_levels_give_three_checkable_triplets():
    """The whole point of 5 over 3: the order is measured three times, so its
    consistency is evidence rather than assertion."""
    exact = 2.5
    vals = {k: exact + 0.1 * (REFINEMENT_RATIO ** (2 - k)) ** 2 for k in range(5)}
    r = convergence_study(vals)
    assert r["n_triplets"] == 3
    assert r["order_mean"] == pytest.approx(2.0, abs=1e-6)
    assert r["order_spread"] < 1e-6
    assert r["orders_consistent"] is True
    assert r["gci_finest"] > 0


def test_convergence_study_flags_an_inconsistent_sequence():
    r = convergence_study({0: 1.0, 1: 1.2, 2: 0.9, 3: 1.15, 4: 0.95})
    assert r["orders_consistent"] is False


def test_cell_size_ratio_is_what_a_gci_must_use():
    assert cell_size_ratio(0, 1) == pytest.approx(REFINEMENT_RATIO)
    assert cell_size_ratio(0, 2) == pytest.approx(REFINEMENT_RATIO**2)


def test_level_lookup_accepts_index_and_name():
    assert level(2) is level("L2") is level("L2_production")
    with pytest.raises(ValueError):
        level(9)
    with pytest.raises(ValueError):
        level("nonsense")
