"""Local mesh refinement for the Gmsh side, in the terms commercial tools use.

Gmsh has no "refinement region" object.  It has SIZE FIELDS: a field returns a
target element size at a point, several fields are combined by taking the
minimum, and the result is the background mesh size.  Every control a commercial
mesher offers is one of those fields wearing a friendlier name:

  workbench control      ANSYS / Fluent Meshing   Star-CCM+                Gmsh field
  Leading edge sizing    Edge Sizing              Curve custom control     Distance/Threshold
  Trailing edge sizing   Edge Sizing              Curve custom control     Distance/Threshold
  Tip sizing             Face Sizing              Surface custom control   Distance/Threshold
  Refinement box         Body of Influence        Volumetric control       Box
  Refinement sphere      Body of Influence        Volumetric control       Ball
  Curvature refinement   Curvature Normal Angle   Surface curvature        FromCurvature

A Threshold is the part worth understanding: below DistMin it returns SizeMin,
above DistMax it returns SizeMax, and in between it interpolates.  So a control
is a size AND the distance over which that size is allowed to grow back to the
surrounding mesh.  Asking for a small size with no room to grow produces cells
that cannot be built next to their neighbours, which is where most "the mesher
ignored my refinement" reports come from.

S7's study pipeline is NOT modified.  Its `_set_background_field` is wrapped for
the duration of one mesh: the original runs and returns its field set, extra
fields are added, and the background is re-pointed at a Min over both.  The
wrapper is removed afterwards.
"""

from __future__ import annotations

import contextlib
import threading
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

_WRAP_LOCK = threading.Lock()


@dataclass
class RegionControl:
    """A body of influence: everything inside gets `size`, outside is untouched."""

    shape: str = "box"                # box | sphere
    size_over_L: float = 0.02
    centre: tuple[float, float, float] = (0.0, 0.0, 0.0)
    extent: tuple[float, float, float] = (1.0, 1.0, 1.0)   # box half-sizes, or radius in x
    enabled: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RefinementSettings:
    """Local controls, all sizes as fractions of the mean aerodynamic chord."""

    # Edge sizing at the leading edge
    le_enabled: bool = False
    le_size_over_L: float = 0.004
    le_distance_over_L: float = 0.05

    # Edge sizing at the trailing edge
    te_enabled: bool = False
    te_size_over_L: float = 0.004
    te_distance_over_L: float = 0.05

    # Face sizing over the tip
    tip_enabled: bool = False
    tip_size_over_L: float = 0.006
    tip_distance_over_L: float = 0.08

    # Curvature refinement, measured off the triangulation rather than asked of
    # Gmsh, which cannot compute it for a discrete surface.
    curvature_enabled: bool = False
    curvature_angle_deg: float = 25.0
    curvature_size_over_L: float = 0.02
    curvature_distance_over_L: float = 0.05

    # Two bodies of influence, which is as many as anyone uses at once
    region_a: RegionControl = field(default_factory=RegionControl)
    region_b: RegionControl = field(default_factory=lambda: RegionControl(shape="sphere"))

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        return out

    @property
    def any_enabled(self) -> bool:
        return bool(self.le_enabled or self.te_enabled or self.tip_enabled
                    or self.curvature_enabled
                    or self.region_a.enabled or self.region_b.enabled)


# --------------------------------------------------------------------------- #
# Feature extraction                                                            #
# --------------------------------------------------------------------------- #

def leading_edge_points(surface: Any, samples: int = 120) -> np.ndarray:
    """The leading-edge line, as the most-forward point of each spanwise slice.

    The surface carries a per-triangle span fraction, so the slices follow the
    wing rather than a global axis, which matters on a swept planform.
    """
    points = np.asarray(surface.points, dtype=float)
    triangles = np.asarray(surface.triangles, dtype=np.int64)
    spans = np.asarray(surface.triangle_span_fraction, dtype=float)

    node_span = np.zeros(len(points))
    counts = np.zeros(len(points))
    for column in range(3):
        np.add.at(node_span, triangles[:, column], spans)
        np.add.at(counts, triangles[:, column], 1.0)
    node_span = np.divide(node_span, np.maximum(counts, 1.0))

    edges = np.linspace(node_span.min(), node_span.max(), samples + 1)
    picked: list[np.ndarray] = []
    for low, high in zip(edges[:-1], edges[1:], strict=True):
        band = (node_span >= low) & (node_span <= high)
        if not band.any():
            continue
        candidates = points[band]
        picked.append(candidates[np.argmin(candidates[:, 0])])
    return np.asarray(picked) if picked else np.empty((0, 3))


def high_curvature_points(surface: Any, *, angle_deg: float = 25.0,
                          limit: int = 4000) -> np.ndarray:
    """Vertices where the surface actually turns, measured off the triangles.

    Gmsh's own `Mesh.MeshSizeFromCurvature` needs analytic CAD curvature and does
    nothing here - the wall is a fixed discrete triangulation, and enabling that
    option changed the cell count by 0.0 percent.  Faceted geometry has to be
    measured instead, which is what snappyHexMesh and Fluent Meshing do on an
    STL: take the angle between the normals of the faces meeting at a vertex,
    and treat a large angle as a tight radius.
    """
    points = np.asarray(surface.points, dtype=float)
    triangles = np.asarray(surface.triangles, dtype=np.int64)
    a = points[triangles[:, 1]] - points[triangles[:, 0]]
    b = points[triangles[:, 2]] - points[triangles[:, 0]]
    normals = np.cross(a, b)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = normals / np.maximum(lengths, 1e-30)

    accumulated = np.zeros((len(points), 3))
    counts = np.zeros(len(points))
    for column in range(3):
        np.add.at(accumulated, triangles[:, column], normals)
        np.add.at(counts, triangles[:, column], 1.0)
    mean_normal = accumulated / np.maximum(counts[:, None], 1.0)
    mean_length = np.linalg.norm(mean_normal, axis=1)
    # A vertex whose face normals all agree has a mean normal of length one; the
    # more they disagree, the shorter it gets.  Convert that back to an angle.
    spread = np.degrees(np.arccos(np.clip(mean_length, -1.0, 1.0)))

    selected = points[spread >= float(angle_deg)]
    if len(selected) > limit:
        step = int(np.ceil(len(selected) / limit))
        selected = selected[::step]
    return selected


def label_points(surface: Any, label: str, limit: int = 4000) -> np.ndarray:
    """Unique vertices of every triangle carrying one surface label."""
    triangles = np.asarray(surface.triangles, dtype=np.int64)
    labels = np.asarray(surface.labels)
    selected = triangles[labels == label]
    if not len(selected):
        return np.empty((0, 3))
    nodes = np.unique(selected.ravel())
    points = np.asarray(surface.points, dtype=float)[nodes]
    if len(points) > limit:
        step = int(np.ceil(len(points) / limit))
        points = points[::step]
    return points


# --------------------------------------------------------------------------- #
# Field construction                                                            #
# --------------------------------------------------------------------------- #

def _ramp_length(small: float, large: float, growth: float) -> float:
    """Distance a size needs to grow from `small` to `large` one cell at a time."""
    if large <= small or growth <= 1.0:
        return max(large - small, 0.0)
    return small * (large / small - 1.0) / (growth - 1.0)


def _distance_threshold(gmsh: Any, points: np.ndarray, *, size_min: float,
                        size_max: float, dist_min: float, dist_max: float) -> int | None:
    if not len(points):
        return None
    field = gmsh.model.mesh.field
    tags = [gmsh.model.geo.addPoint(float(x), float(y), float(z)) for x, y, z in points]
    gmsh.model.geo.synchronize()
    distance = field.add("Distance")
    field.setNumbers(distance, "PointsList", tags)
    threshold = field.add("Threshold")
    field.setNumber(threshold, "InField", distance)
    field.setNumber(threshold, "SizeMin", float(size_min))
    field.setNumber(threshold, "SizeMax", float(size_max))
    field.setNumber(threshold, "DistMin", float(dist_min))
    field.setNumber(threshold, "DistMax", float(dist_max))
    return threshold


def _region_field(gmsh: Any, region: RegionControl, *, L: float,
                  outside: float, growth: float) -> int | None:
    if not region.enabled:
        return None
    field = gmsh.model.mesh.field
    size = float(region.size_over_L) * L
    cx, cy, cz = (float(v) * L for v in region.centre)
    if region.shape == "sphere":
        radius = float(region.extent[0]) * L
        tag = field.add("Ball")
        field.setNumber(tag, "Radius", radius)
        field.setNumber(tag, "XCenter", cx)
        field.setNumber(tag, "YCenter", cy)
        field.setNumber(tag, "ZCenter", cz)
    else:
        half = [float(v) * L for v in region.extent]
        tag = field.add("Box")
        field.setNumber(tag, "XMin", cx - half[0])
        field.setNumber(tag, "XMax", cx + half[0])
        field.setNumber(tag, "YMin", cy - half[1])
        field.setNumber(tag, "YMax", cy + half[1])
        field.setNumber(tag, "ZMin", cz - half[2])
        field.setNumber(tag, "ZMax", cz + half[2])
    field.setNumber(tag, "VIn", size)
    field.setNumber(tag, "VOut", outside)
    # Without a transition the field steps by the full ratio across the region
    # face, and neighbouring cells differ by that whole jump in one step.
    field.setNumber(tag, "Thickness", _ramp_length(size, outside, growth))
    return tag


def add_fields(gmsh: Any, settings: RefinementSettings, *, surface: Any,
               L: float, near_size: float, far_size: float,
               bl_thickness: float, growth: float,
               log: Any = None) -> list[int]:
    """Every enabled control, as Gmsh field tags ready to join the Min."""
    tags: list[int] = []

    def note(message: str) -> None:
        if log:
            log(f"refinement: {message}")

    edge_specs = [
        ("leading edge", settings.le_enabled, settings.le_size_over_L,
         settings.le_distance_over_L, lambda: leading_edge_points(surface)),
        ("trailing edge", settings.te_enabled, settings.te_size_over_L,
         settings.te_distance_over_L, lambda: label_points(surface, "wall_te")),
        ("tip", settings.tip_enabled, settings.tip_size_over_L,
         settings.tip_distance_over_L, lambda: label_points(surface, "wall_tip")),
        ("curvature", settings.curvature_enabled, settings.curvature_size_over_L,
         settings.curvature_distance_over_L,
         lambda: high_curvature_points(surface, angle_deg=settings.curvature_angle_deg)),
    ]
    for name, enabled, size_over_L, distance_over_L, getter in edge_specs:
        if not enabled:
            continue
        points = getter()
        if not len(points):
            note(f"{name}: no points found, control skipped")
            continue
        size = float(size_over_L) * L
        # The refinement starts at the prism cap, not at the wall: the core mesh
        # does not exist inside the boundary layer.
        dist_min = bl_thickness
        dist_max = bl_thickness + max(float(distance_over_L) * L,
                                      _ramp_length(size, near_size, growth))
        tag = _distance_threshold(gmsh, points, size_min=size, size_max=near_size,
                                  dist_min=dist_min, dist_max=dist_max)
        if tag is not None:
            tags.append(tag)
            note(f"{name}: {len(points)} seed points, size {size:.4g} m "
                 f"grading to {near_size:.4g} m over {dist_max - dist_min:.4g} m")

    for label, region in (("region A", settings.region_a), ("region B", settings.region_b)):
        tag = _region_field(gmsh, region, L=L, outside=far_size, growth=growth)
        if tag is not None:
            tags.append(tag)
            note(f"{label}: {region.shape}, size {region.size_over_L * L:.4g} m")

    return tags


@contextlib.contextmanager
def applied(pipeline_module: Any, settings: RefinementSettings, *, surface: Any,
            L: float, growth: float, log: Any = None):
    """Wrap S7's background-field builder for the duration of one mesh.

    The study function runs untouched and returns its own field identifiers; the
    extra controls are then added and the background mesh is re-pointed at a Min
    over the original result and the new fields.  Gmsh accepts a later
    `setAsBackgroundMesh`, so this composes rather than replaces.
    """
    if not settings.any_enabled:
        yield {}
        return

    original = pipeline_module._set_background_field
    record: dict[str, Any] = {}

    def wrapper(gmsh: Any, **kwargs: Any) -> dict[str, int]:
        identifiers = original(gmsh, **kwargs)
        extra = add_fields(
            gmsh, settings, surface=surface, L=L,
            near_size=float(kwargs["near_size"]), far_size=float(kwargs["far_size"]),
            bl_thickness=float(kwargs["bl_thickness"]), growth=growth, log=log,
        )
        if extra:
            field = gmsh.model.mesh.field
            combined = field.add("Min")
            field.setNumbers(combined, "FieldsList", [identifiers["minimum"], *extra])
            field.setAsBackgroundMesh(combined)
            identifiers["workbench_refinement"] = extra
            identifiers["workbench_minimum"] = combined
        record.update(identifiers)
        return identifiers

    with _WRAP_LOCK:
        pipeline_module._set_background_field = wrapper
        try:
            yield record
        finally:
            pipeline_module._set_background_field = original
