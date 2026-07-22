"""Free-edge audit: an unclosed tip must not pass as a symmetry plane."""

from __future__ import annotations

import numpy as np

from aeris.mesh.surface import SurfaceBlock, _free_edge_audit


def _panel(y0: float, y1: float, x0: float, x1: float, name: str) -> SurfaceBlock:
    x, y = np.meshgrid(np.linspace(x0, x1, 4), np.linspace(y0, y1, 4), indexing="ij")
    return SurfaceBlock(name=name, xyz=np.stack([x, y, np.zeros_like(x)], axis=-1))


def test_root_plane_edges_are_allowed():
    """A half-model is legitimately open at y=0 and nowhere else."""
    audit = _free_edge_audit([_panel(0.0, 1.0, 0.0, 1.0, "oml_0")], tol=1e-9)
    root = [e for e in audit["edges"] if e["on_root_plane"]]
    assert len(root) == 1
    assert root[0]["side"] == "j0"


def test_edge_off_the_root_plane_is_flagged():
    """The bug this exists for: an open boundary away from y=0."""
    audit = _free_edge_audit([_panel(0.5, 1.5, 0.0, 1.0, "oml_0")], tol=1e-9)
    assert audit["closed_except_root"] is False
    assert audit["off_root_free_edges"] > 0


def test_shared_edges_are_not_free():
    """Two panels meeting at y=1 share that edge, so neither reports it."""
    blocks = [_panel(0.0, 1.0, 0.0, 1.0, "a"), _panel(1.0, 2.0, 0.0, 1.0, "b")]
    audit = _free_edge_audit(blocks, tol=1e-9)
    shared_y = [e for e in audit["edges"] if abs(e["mean_y"] - 1.0) < 1e-9]
    assert shared_y == []


def test_unclosed_tip_is_caught():
    """Two spanwise panels with no tip cap: the outboard end stays open."""
    blocks = [_panel(0.0, 1.0, 0.0, 1.0, "oml_0"), _panel(1.0, 2.0, 0.0, 1.0, "oml_1")]
    audit = _free_edge_audit(blocks, tol=1e-9)
    off_root = [e for e in audit["edges"] if not e["on_root_plane"]]
    # the y=2 tip edge is open and must be reported, not silently accepted
    assert any(abs(e["mean_y"] - 2.0) < 1e-9 for e in off_root)
    assert audit["closed_except_root"] is False
