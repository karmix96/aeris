"""Tests for the explicit boundary-layer marcher."""

from __future__ import annotations

import numpy as np
import pytest

from . import prism_layer as pl


def _tilted_wall():
    """Two triangles meeting the y=0 plane at an angle, as a swept wall does.

    The tilt is the whole point: a wall perpendicular to the symmetry plane would
    march in-plane by accident, and would not test the constraint at all.
    """
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.3, 1.0, 0.4],
            [1.3, 1.0, 0.4],
        ]
    )
    triangles = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
    return points, triangles


def test_root_nodes_march_along_the_symmetry_plane():
    points, triangles = _tilted_wall()
    layer = pl.march(points, triangles, [0.1, 0.25], symmetry_axis=1)

    assert layer.diagnostics["root_nodes_constrained"] == 2
    # Nothing may cross, and the constrained columns must stay exactly on it.
    assert layer.points[:, 1].min() == pytest.approx(0.0, abs=1e-15)
    on_plane = np.abs(points[:, 1]) <= 1e-9
    for level in range(1, 3):
        marched = layer.points[len(points) * level : len(points) * (level + 1)]
        assert np.allclose(marched[on_plane][:, 1], 0.0, atol=1e-15)


def test_unconstrained_march_would_have_left_the_plane():
    """Without the constraint the same wall leaves the domain - the bug's cause."""
    points, triangles = _tilted_wall()
    free = pl.march(points, triangles, [0.1, 0.25], symmetry_axis=None)
    assert free.points[:, 1].min() < -1e-6


def test_prisms_are_positively_oriented():
    points, triangles = _tilted_wall()
    layer = pl.march(points, triangles, [0.1, 0.25], symmetry_axis=1)
    volumes = pl.prism_signed_volumes(layer.points, layer.prisms)
    assert len(volumes) == len(triangles) * 2
    assert (volumes > 0).all()


def test_node_layout_is_the_documented_one():
    points, triangles = _tilted_wall()
    layer = pl.march(points, triangles, [0.1, 0.25], symmetry_axis=1)
    assert layer.wall_count == len(points)
    assert layer.top_node_offset == len(points) * 2
    assert np.array_equal(layer.top_triangles, triangles + len(points) * 2)
    assert len(layer.points) == len(points) * 3


def test_tangential_wall_is_refused_rather_than_guessed():
    """A wall meeting the plane tangentially has no in-plane direction left."""
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, 0.0, 1.0]])
    triangles = np.array([[0, 1, 2]], dtype=np.int64)
    with pytest.raises(ValueError, match="no in-plane marching direction"):
        pl.march(points, triangles, [0.1], symmetry_axis=1)


def test_heights_must_increase():
    points, triangles = _tilted_wall()
    with pytest.raises(ValueError, match="increase strictly"):
        pl.march(points, triangles, [0.2, 0.1], symmetry_axis=1)


def test_symmetry_quads_are_the_root_end_of_the_layer():
    points, triangles = _tilted_wall()
    layer = pl.march(points, triangles, [0.1, 0.25], symmetry_axis=1)
    quads = pl.symmetry_quads(layer, axis=1)

    # One root edge per layer: the tilted wall has a single edge on the plane.
    assert len(quads) == 2
    assert np.allclose(layer.points[quads.ravel()][:, 1], 0.0, atol=1e-15)


def test_symmetry_quads_vanish_without_the_constraint():
    """A free march tilts the same faces off the plane, so none qualify."""
    points, triangles = _tilted_wall()
    free = pl.march(points, triangles, [0.1, 0.25], symmetry_axis=None)
    assert len(pl.symmetry_quads(free, axis=1)) == 0


def test_top_boundary_comes_back_as_one_ordered_loop():
    points, triangles = _tilted_wall()
    layer = pl.march(points, triangles, [0.1, 0.25], symmetry_axis=1)
    loops = pl.top_boundary_loops(layer)

    assert len(loops) == 1
    loop = loops[0]
    assert len(loop) == 4
    assert len(set(loop)) == len(loop)
    # Consecutive entries must be real edges of the capping surface.
    edges = set()
    for a, b, c in layer.top_triangles:
        for e in ((a, b), (b, c), (c, a)):
            edges.add((int(min(e)), int(max(e))))
    for i, node in enumerate(loop):
        nxt = loop[(i + 1) % len(loop)]
        assert (min(node, nxt), max(node, nxt)) in edges
