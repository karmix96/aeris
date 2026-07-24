"""Physical split-control CAD reconstructed from the realised pyGeo loft.

pyGeo remains the master neutral outer-mould-line (OML).  This module samples
the already-extracted realised sections, builds a closed neutral solid, removes
an aft control cove, creates a separate elevon solid, and rigidly rotates the
elevon about a three-dimensional hinge axis.

The result is deliberately an assembly:

    right fixed wing + right elevon + left fixed wing + left elevon

That topology is suitable for a CAD-aware mesher.  The facet exports written
here are inspection/handoff artifacts, not a replacement for a quality-gated
CFD surface mesh.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

PHYSICAL_CAD_SCHEMA = "pygeo_bwb_physical_cad.v1"
MESH_HANDOFF_SCHEMA = "pygeo_bwb_mesh_handoff.v1"


@dataclass(frozen=True)
class PhysicalCadSpec:
    """Settings that define the physical control geometry and its tessellation."""

    enabled: bool = False
    topology: str = "split_elevon"
    hinge_gap_fraction: float = 0.005
    boundary_clearance_fraction: float = 0.005
    design_deflection_limit_deg: float = 20.0
    chordwise_points: int = 81
    minimum_te_thickness_fraction: float = 5.0e-4
    tessellation_tolerance_m: float = 7.5e-4
    tessellation_angular_tolerance_rad: float = 0.12
    max_master_to_cad_deviation_cref: float = 0.005
    fail_on_invalid: bool = True

    def identity_dict(self) -> dict[str, Any]:
        """Fields that change the manufactured neutral geometry."""

        return {
            "enabled": self.enabled,
            "topology": self.topology,
            "hinge_gap_fraction": self.hinge_gap_fraction,
            "boundary_clearance_fraction": self.boundary_clearance_fraction,
            "design_deflection_limit_deg": self.design_deflection_limit_deg,
            "chordwise_points": self.chordwise_points,
            "minimum_te_thickness_fraction": self.minimum_te_thickness_fraction,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SectionProfile:
    """One planarised realised pyGeo section on a common normalized x grid."""

    eta: float
    le_xyz_m: np.ndarray
    chord_m: float
    chord_axis: np.ndarray
    span_axis: np.ndarray
    thickness_axis: np.ndarray
    x: np.ndarray
    z_upper: np.ndarray
    z_lower: np.ndarray

    def xyz(self, x: np.ndarray, z: np.ndarray) -> np.ndarray:
        return (
            self.le_xyz_m
            + np.asarray(x)[:, None] * self.chord_m * self.chord_axis
            + np.asarray(z)[:, None] * self.chord_m * self.thickness_axis
        )

    def point(self, x: float, z: float) -> np.ndarray:
        return (
            self.le_xyz_m
            + float(x) * self.chord_m * self.chord_axis
            + float(z) * self.chord_m * self.thickness_axis
        )

    def surface_z(self, x: float) -> tuple[float, float]:
        return (
            float(np.interp(float(x), self.x, self.z_upper)),
            float(np.interp(float(x), self.x, self.z_lower)),
        )


@dataclass
class PhysicalCadModel:
    """In-memory OCC shapes and the evidence needed to export them."""

    state_id: str
    spec: PhysicalCadSpec
    neutral_bodies: dict[str, Any]
    neutral_split_bodies: dict[str, Any]
    deflected_bodies: dict[str, Any]
    report: dict[str, Any]
    neutral_mesh: dict[str, Any]


def _mapping(value: object, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return dict(value)


def _bool(value: object, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    raise ValueError(f"{label} must be boolean")


def resolve_physical_cad_spec(
    geometry: Mapping[str, Any],
    *,
    control_enabled: bool,
) -> PhysicalCadSpec:
    """Resolve and validate ``geometry.control_surfaces.physical_cad``."""

    controls = _mapping(geometry.get("control_surfaces"), "geometry.control_surfaces")
    raw = _mapping(controls.get("physical_cad"), "control_surfaces.physical_cad")
    spec = PhysicalCadSpec(
        enabled=_bool(raw.get("enabled", False), "physical_cad.enabled") if raw else False,
        topology=str(raw.get("topology", "split_elevon")).strip().lower(),
        hinge_gap_fraction=float(raw.get("hinge_gap_fraction", 0.005)),
        boundary_clearance_fraction=float(raw.get("boundary_clearance_fraction", 0.005)),
        design_deflection_limit_deg=float(raw.get("design_deflection_limit_deg", 20.0)),
        chordwise_points=int(raw.get("chordwise_points", 81)),
        minimum_te_thickness_fraction=float(raw.get("minimum_te_thickness_fraction", 5.0e-4)),
        tessellation_tolerance_m=float(raw.get("tessellation_tolerance_m", 7.5e-4)),
        tessellation_angular_tolerance_rad=float(
            raw.get("tessellation_angular_tolerance_rad", 0.12)
        ),
        max_master_to_cad_deviation_cref=float(raw.get("max_master_to_cad_deviation_cref", 0.005)),
        fail_on_invalid=_bool(
            raw.get("fail_on_invalid", True),
            "physical_cad.fail_on_invalid",
        ),
    )
    if spec.enabled and not control_enabled:
        raise ValueError("physical_cad.enabled requires an enabled control surface")
    if spec.topology != "split_elevon":
        raise ValueError("physical_cad.topology currently supports only 'split_elevon'")
    if not 0.0 <= spec.hinge_gap_fraction < 0.15:
        raise ValueError("physical_cad.hinge_gap_fraction must be in [0, 0.15)")
    if not 0.0 <= spec.boundary_clearance_fraction < 0.05:
        raise ValueError("physical_cad.boundary_clearance_fraction must be in [0, 0.05)")
    if not 0.0 <= spec.design_deflection_limit_deg <= 60.0:
        raise ValueError("physical_cad.design_deflection_limit_deg must be in [0, 60]")
    if spec.chordwise_points < 21:
        raise ValueError("physical_cad.chordwise_points must be at least 21")
    if not 0.0 <= spec.minimum_te_thickness_fraction <= 0.02:
        raise ValueError("physical_cad.minimum_te_thickness_fraction must be in [0, 0.02]")
    if spec.tessellation_tolerance_m <= 0.0:
        raise ValueError("physical_cad.tessellation_tolerance_m must be positive")
    if spec.tessellation_angular_tolerance_rad <= 0.0:
        raise ValueError("physical_cad.tessellation_angular_tolerance_rad must be positive")
    if spec.max_master_to_cad_deviation_cref <= 0.0:
        raise ValueError("physical_cad.max_master_to_cad_deviation_cref must be positive")
    return spec


def physical_state_id(
    geometry_id: str,
    control: Any,
    spec: PhysicalCadSpec,
) -> str:
    """Hash the neutral geometry plus operational control commands."""

    payload = {
        "geometry_id": str(geometry_id),
        "physical_cad": spec.identity_dict(),
        "delta_e_sym_deg": float(control.delta_e_sym_deg),
        "delta_a_diff_deg": float(control.delta_a_diff_deg),
        "right_deflection_deg": float(control.right_deflection_deg),
        "left_deflection_deg": float(control.left_deflection_deg),
    }
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"pygeo_state_{digest[:20]}"


def _unit(vector: np.ndarray, label: str) -> np.ndarray:
    vector = np.asarray(vector, dtype=float)
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or norm <= 1.0e-12:
        raise ValueError(f"Cannot normalize degenerate {label}")
    return vector / norm


def _cosine_x(count: int) -> np.ndarray:
    beta = np.linspace(0.0, math.pi, int(count))
    return 0.5 * (1.0 - np.cos(beta))


def _profile_from_section(section: Any, spec: PhysicalCadSpec) -> SectionProfile:
    x = _cosine_x(spec.chordwise_points)
    z_upper = np.interp(x, section.x_upper, section.z_upper)
    z_lower = np.interp(x, section.x_lower, section.z_lower)

    # Make every wire use the same robust closed topology.  The leading edge
    # is one point, while a minimum finite trailing-edge base is recorded and
    # used only by the reconstructed solid/mesh representation.
    z_le = 0.5 * float(z_upper[0] + z_lower[0])
    z_upper[0] = z_le
    z_lower[0] = z_le
    z_te_mid = 0.5 * float(z_upper[-1] + z_lower[-1])
    te_gap = float(z_upper[-1] - z_lower[-1])
    effective_gap = max(te_gap, spec.minimum_te_thickness_fraction)
    z_upper[-1] = z_te_mid + 0.5 * effective_gap
    z_lower[-1] = z_te_mid - 0.5 * effective_gap

    chord_axis = _unit(np.asarray(section.chord_axis, dtype=float), "chord axis")
    span_axis = _unit(np.asarray(section.local_span_axis, dtype=float), "span axis")
    thickness_axis = _unit(
        np.asarray(section.thickness_axis, dtype=float),
        "thickness axis",
    )
    eta = float(section.span_fraction)
    le_xyz_m = np.asarray(section.le_xyz_m, dtype=float)
    if eta <= 1.0e-12:
        # A finite-thickness half-wing must terminate exactly on the XZ
        # symmetry plane. Projecting only this root frame removes numerical
        # or frame-induced penetration without changing the realised loft
        # away from the centerline.
        le_xyz_m = le_xyz_m.copy()
        le_xyz_m[1] = 0.0
        chord_axis = chord_axis.copy()
        chord_axis[1] = 0.0
        chord_axis = _unit(chord_axis, "root chord axis")
        span_axis = np.array([0.0, 1.0, 0.0])
        root_thickness = _unit(
            np.cross(chord_axis, span_axis),
            "root thickness axis",
        )
        if float(np.dot(root_thickness, thickness_axis)) < 0.0:
            root_thickness = -root_thickness
        thickness_axis = root_thickness
    return SectionProfile(
        eta=eta,
        le_xyz_m=le_xyz_m,
        chord_m=float(section.chord_m),
        chord_axis=chord_axis,
        span_axis=span_axis,
        thickness_axis=thickness_axis,
        x=x,
        z_upper=np.asarray(z_upper, dtype=float),
        z_lower=np.asarray(z_lower, dtype=float),
    )


def _interpolate_profile(
    profiles: Sequence[SectionProfile],
    eta: float,
) -> SectionProfile:
    ordered = sorted(profiles, key=lambda profile: profile.eta)
    target = float(eta)
    if target <= ordered[0].eta + 1.0e-12:
        return ordered[0]
    if target >= ordered[-1].eta - 1.0e-12:
        return ordered[-1]
    for profile in ordered:
        if abs(profile.eta - target) <= 1.0e-12:
            return profile
    for left, right in zip(ordered[:-1], ordered[1:], strict=True):
        if left.eta < target < right.eta:
            fraction = (target - left.eta) / (right.eta - left.eta)

            def blend(
                a: np.ndarray,
                b: np.ndarray,
                weight: float = fraction,
            ) -> np.ndarray:
                return (1.0 - weight) * np.asarray(a) + weight * np.asarray(b)

            chord_axis = _unit(
                blend(left.chord_axis, right.chord_axis),
                "interpolated chord axis",
            )
            span_axis = _unit(
                blend(left.span_axis, right.span_axis),
                "interpolated span axis",
            )
            thickness_axis = _unit(
                np.cross(chord_axis, span_axis),
                "interpolated thickness axis",
            )
            if float(np.dot(thickness_axis, left.thickness_axis)) < 0.0:
                thickness_axis = -thickness_axis
            return SectionProfile(
                eta=target,
                le_xyz_m=blend(left.le_xyz_m, right.le_xyz_m),
                chord_m=float((1.0 - fraction) * left.chord_m + fraction * right.chord_m),
                chord_axis=chord_axis,
                span_axis=span_axis,
                thickness_axis=thickness_axis,
                x=left.x.copy(),
                z_upper=blend(left.z_upper, right.z_upper),
                z_lower=blend(left.z_lower, right.z_lower),
            )
    raise ValueError(f"Could not interpolate section at eta={target:.8f}")


def _profiles_in_interval(
    profiles: Sequence[SectionProfile],
    start: float,
    end: float,
) -> list[SectionProfile]:
    values = {
        float(start),
        float(end),
        *[float(profile.eta) for profile in profiles if float(start) < profile.eta < float(end)],
    }
    return [_interpolate_profile(profiles, eta) for eta in sorted(values)]


def _wire_from_profile(
    profile: SectionProfile,
    *,
    x_start: float,
    x_end: float = 1.0,
) -> Any:
    import cadquery as cq

    if not 0.0 <= x_start < x_end <= 1.0:
        raise ValueError(f"Invalid profile interval [{x_start}, {x_end}]")
    beta = np.linspace(0.0, math.pi, len(profile.x))
    x = x_start + (x_end - x_start) * 0.5 * (1.0 - np.cos(beta))
    zu = np.interp(x, profile.x, profile.z_upper)
    zl = np.interp(x, profile.x, profile.z_lower)
    upper = profile.xyz(x, zu)
    lower = profile.xyz(x[::-1], zl[::-1])

    def vectors(points: np.ndarray) -> list[Any]:
        return [cq.Vector(*[float(value) for value in point]) for point in points]

    tolerance = max(1.0e-12, profile.chord_m * 1.0e-10)
    edges = [cq.Edge.makeSpline(vectors(upper), tol=tolerance)]
    if float(np.linalg.norm(upper[-1] - lower[0])) > tolerance:
        edges.append(cq.Edge.makeLine(vectors(upper[-1:])[0], vectors(lower[:1])[0]))
    edges.append(cq.Edge.makeSpline(vectors(lower), tol=tolerance))
    if float(np.linalg.norm(lower[-1] - upper[0])) > tolerance:
        edges.append(cq.Edge.makeLine(vectors(lower[-1:])[0], vectors(upper[:1])[0]))
    wire = cq.Wire.assembleEdges(edges)
    if not wire.IsClosed():
        raise ValueError("OCC section wire is not closed")
    return wire


def _wedge_wire(
    profile: SectionProfile,
    *,
    x_cut: float,
) -> Any:
    import cadquery as cq

    x_forward = max(0.001, float(x_cut))
    x_aft = 1.55
    z_extent = 0.80
    corners = (
        profile.point(x_forward, -z_extent),
        profile.point(x_aft, -z_extent),
        profile.point(x_aft, z_extent),
        profile.point(x_forward, z_extent),
    )
    return cq.Wire.makePolygon(
        [cq.Vector(*[float(value) for value in point]) for point in corners],
        close=True,
    )


def _loft(wires: Sequence[Any], label: str) -> Any:
    import cadquery as cq

    if len(wires) < 2:
        raise ValueError(f"{label} needs at least two section wires")
    try:
        shape = cq.Solid.makeLoft(list(wires), ruled=True)
    except Exception as ruled_error:
        try:
            shape = cq.Solid.makeLoft(list(wires), ruled=False)
        except Exception as smooth_error:
            raise RuntimeError(
                f"{label} loft failed in ruled and smooth modes: "
                f"{type(ruled_error).__name__}: {ruled_error}; "
                f"{type(smooth_error).__name__}: {smooth_error}"
            ) from smooth_error
    if shape is None:
        raise RuntimeError(f"{label} loft returned no shape")
    return shape


def _line_distance(points: np.ndarray, start: np.ndarray, end: np.ndarray) -> np.ndarray:
    direction = _unit(end - start, "hinge axis")
    offsets = np.asarray(points) - start
    return np.linalg.norm(offsets - np.outer(offsets @ direction, direction), axis=1)


def _shape_report(shape: Any) -> dict[str, Any]:
    bbox = shape.BoundingBox()
    return {
        "valid": bool(shape.isValid()),
        "solid_count": len(shape.Solids()),
        "face_count": len(shape.Faces()),
        "volume_m3": float(shape.Volume()),
        "surface_area_m2": float(shape.Area()),
        "bounding_box_m": {
            "xmin": float(bbox.xmin),
            "xmax": float(bbox.xmax),
            "ymin": float(bbox.ymin),
            "ymax": float(bbox.ymax),
            "zmin": float(bbox.zmin),
            "zmax": float(bbox.zmax),
        },
    }


def _intersection_volume(first: Any, second: Any) -> float:
    try:
        return max(0.0, float(first.intersect(second).Volume()))
    except Exception:
        return float("nan")


def _shape_distance(first: Any, second: Any) -> float:
    try:
        return max(0.0, float(first.distance(second)))
    except Exception:
        return float("nan")


def build_physical_cad(
    case: Any,
    control: Any,
    spec: PhysicalCadSpec,
) -> PhysicalCadModel:
    """Build neutral and physically deflected OCC solids from realised sections."""

    if not spec.enabled:
        raise ValueError("Physical CAD is disabled")
    if not control.enabled:
        raise ValueError("Physical CAD requires an enabled control surface")
    max_command = max(
        abs(float(control.right_deflection_deg)),
        abs(float(control.left_deflection_deg)),
    )
    if max_command > spec.design_deflection_limit_deg + 1.0e-12:
        raise ValueError(
            "Current control command exceeds physical_cad.design_deflection_limit_deg: "
            f"{max_command:.3f} > {spec.design_deflection_limit_deg:.3f}"
        )

    profiles = [_profile_from_section(section, spec) for section in case.extracted]
    profiles = sorted(profiles, key=lambda profile: profile.eta)
    if len(profiles) < 3:
        raise ValueError("At least three realised sections are required for physical CAD")

    control_profiles = _profiles_in_interval(
        profiles,
        float(control.start_frac),
        float(control.end_frac),
    )
    boundary = float(spec.boundary_clearance_fraction)
    removal_start = max(profiles[0].eta, float(control.start_frac) - boundary)
    removal_end = min(profiles[-1].eta, float(control.end_frac) + boundary)
    removal_profiles = _profiles_in_interval(profiles, removal_start, removal_end)

    hinge_samples = []
    max_half_thickness = 0.0
    for profile in control_profiles:
        zu, zl = profile.surface_z(float(control.hinge_point))
        hinge_samples.append(profile.point(float(control.hinge_point), 0.5 * (zu + zl)))
        max_half_thickness = max(
            max_half_thickness,
            0.5 * abs(float(zu - zl)),
        )
    hinge_samples_array = np.asarray(hinge_samples, dtype=float)
    hinge_axis_start = hinge_samples_array[0]
    hinge_axis_end = hinge_samples_array[-1]
    hinge_straightness = _line_distance(
        hinge_samples_array,
        hinge_axis_start,
        hinge_axis_end,
    )

    # The fixed-body cove is sized for the configured design deflection limit.
    # This keeps the fixed geometry independent of each operational command.
    relief = max_half_thickness * math.sin(math.radians(spec.design_deflection_limit_deg))
    fixed_cut = float(control.hinge_point) - 0.5 * spec.hinge_gap_fraction - relief
    control_cut = float(control.hinge_point) + 0.5 * spec.hinge_gap_fraction
    if fixed_cut <= 0.05 or control_cut >= 0.98 or fixed_cut >= control_cut:
        raise ValueError(
            "Control cove is invalid; adjust hinge, gap, or design deflection limit "
            f"({fixed_cut=:.5f}, {control_cut=:.5f})"
        )

    full_wires = [_wire_from_profile(profile, x_start=0.0) for profile in profiles]
    right_full = _loft(full_wires, "right neutral full wing")
    wedge = _loft(
        [_wedge_wire(profile, x_cut=fixed_cut) for profile in removal_profiles],
        "right fixed-body cove cutter",
    )
    right_fixed = right_full.cut(wedge)
    right_control_neutral = _loft(
        [_wire_from_profile(profile, x_start=control_cut) for profile in control_profiles],
        "right neutral elevon",
    )
    right_control = right_control_neutral.rotate(
        tuple(float(value) for value in hinge_axis_start),
        tuple(float(value) for value in hinge_axis_end),
        float(control.right_deflection_deg),
    )

    def right_to_left(shape: Any) -> Any:
        return shape.mirror("XZ")

    left_full = right_to_left(right_full)
    left_fixed = right_to_left(right_fixed)
    left_control_neutral = right_to_left(right_control_neutral)
    # Build on the positive side and mirror afterwards.  This preserves the
    # convention that positive physical deflection is trailing-edge down on
    # both sides while allowing independent right/left commands.
    left_control = right_to_left(
        right_control_neutral.rotate(
            tuple(float(value) for value in hinge_axis_start),
            tuple(float(value) for value in hinge_axis_end),
            float(control.left_deflection_deg),
        )
    )

    neutral_bodies = {
        "right_full_neutral": right_full,
        "left_full_neutral": left_full,
    }
    neutral_split_bodies = {
        "right_fixed": right_fixed,
        "right_elevon_neutral": right_control_neutral,
        "left_fixed": left_fixed,
        "left_elevon_neutral": left_control_neutral,
    }
    deflected_bodies = {
        "right_fixed": right_fixed,
        "right_elevon": right_control,
        "left_fixed": left_fixed,
        "left_elevon": left_control,
    }

    body_reports = {name: _shape_report(shape) for name, shape in deflected_bodies.items()}
    neutral_reports = {name: _shape_report(shape) for name, shape in neutral_bodies.items()}
    right_full_volume = float(right_full.Volume())
    right_fixed_volume = float(right_fixed.Volume())
    right_control_volume = float(right_control_neutral.Volume())
    partition_residual = right_full_volume - right_fixed_volume - right_control_volume
    overlap_right = _intersection_volume(right_fixed, right_control)
    overlap_left = _intersection_volume(left_fixed, left_control)
    overlap_limit = max(1.0e-12, right_full_volume * 1.0e-7)
    symmetry_overlap = _intersection_volume(right_full, left_full)
    symmetry_overlap_limit = max(1.0e-12, right_full_volume * 1.0e-10)
    symmetry_ok = math.isfinite(symmetry_overlap) and symmetry_overlap <= symmetry_overlap_limit
    validity_ok = all(report["valid"] for report in body_reports.values())
    solid_count_ok = all(report["solid_count"] >= 1 for report in body_reports.values())
    overlap_ok = all(
        math.isfinite(value) and value <= overlap_limit for value in (overlap_right, overlap_left)
    )
    hinge_straightness_max = float(np.max(hinge_straightness))
    hinge_length = float(np.linalg.norm(hinge_axis_end - hinge_axis_start))
    warp_rms_m = float(
        math.sqrt(
            np.mean(
                [
                    (float(section.plane_warp_rms_chord) * float(section.chord_m)) ** 2
                    for section in case.extracted
                ]
            )
        )
    )
    warp_max_m = float(
        max(
            float(section.plane_warp_max_chord) * float(section.chord_m)
            for section in case.extracted
        )
    )
    right_center_neutral = np.asarray(
        right_control_neutral.Center().toTuple(),
        dtype=float,
    )
    right_center_deflected = np.asarray(right_control.Center().toTuple(), dtype=float)
    left_center_neutral = np.asarray(
        left_control_neutral.Center().toTuple(),
        dtype=float,
    )
    left_center_deflected = np.asarray(left_control.Center().toTuple(), dtype=float)
    right_center_delta = right_center_deflected - right_center_neutral
    left_center_delta = left_center_deflected - left_center_neutral

    def deflection_sign_ok(command_deg: float, delta_z_m: float) -> bool:
        if abs(float(command_deg)) <= 1.0e-12:
            return abs(float(delta_z_m)) <= 1.0e-9
        return float(command_deg) * float(delta_z_m) < 0.0

    kinematic_sign_ok = deflection_sign_ok(
        control.right_deflection_deg,
        right_center_delta[2],
    ) and deflection_sign_ok(
        control.left_deflection_deg,
        left_center_delta[2],
    )
    right_rotation_volume_error = abs(float(right_control.Volume()) - right_control_volume) / max(
        right_control_volume, 1.0e-12
    )
    left_control_volume = float(left_control_neutral.Volume())
    left_rotation_volume_error = abs(float(left_control.Volume()) - left_control_volume) / max(
        left_control_volume, 1.0e-12
    )
    rigid_rotation_ok = (
        max(
            right_rotation_volume_error,
            left_rotation_volume_error,
        )
        <= 1.0e-9
    )
    neutral_mesh = tessellate_bodies(neutral_bodies, spec)
    master_cad_audit = audit_master_to_neutral_cad(
        case.upper_surface,
        case.lower_surface,
        neutral_mesh,
        reference_chord_m=float(case.metrics["c_ref_m"]),
        max_deviation_cref=spec.max_master_to_cad_deviation_cref,
    )
    master_cad_ok = master_cad_audit.get("accepted") is not False
    accepted = (
        validity_ok
        and solid_count_ok
        and overlap_ok
        and symmetry_ok
        and kinematic_sign_ok
        and rigid_rotation_ok
        and master_cad_ok
    )
    state_id = physical_state_id(case.geometry_id, control, spec)
    report = {
        "schema": PHYSICAL_CAD_SCHEMA,
        "status": "accepted" if accepted else "rejected",
        "geometry_id": str(case.geometry_id),
        "state_id": state_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "master_geometry": {
            "engine": "pyGeo",
            "state": "neutral",
            "reconstruction_source": "realised fixed-span sections",
            "section_representation": "direct planarised coordinates",
            "loft_model": "piecewise ruled OCC solids",
            "native_pygeo_iges_remains_master_neutral_oml": True,
            "reconstruction_plane_warp_rms_m": warp_rms_m,
            "reconstruction_plane_warp_max_m": warp_max_m,
            "neutral_cad_surface_deviation": master_cad_audit,
        },
        "topology": {
            "id": spec.topology,
            "body_model": "fixed wing plus separate rigid elevon per side",
            "root_symmetry_plane": "XZ (y=0)",
            "root_panel_dihedral_deg": 0.0,
            "control_gap_model": "simple_clearance_cove",
            "fidelity_role": "robust screening CAD, not a resolved hinge mechanism",
            "gap_is_fluid_domain": True,
            "n_deflected_bodies": len(deflected_bodies),
            "neutral_full_body_count": len(neutral_bodies),
            "fixed_cove_cut_x_over_c": fixed_cut,
            "elevon_le_cut_x_over_c": control_cut,
            "hinge_gap_fraction": spec.hinge_gap_fraction,
            "boundary_clearance_fraction": spec.boundary_clearance_fraction,
            "design_deflection_limit_deg": spec.design_deflection_limit_deg,
            "minimum_te_thickness_fraction": (spec.minimum_te_thickness_fraction),
        },
        "commands": {
            "delta_e_sym_deg": float(control.delta_e_sym_deg),
            "delta_a_diff_deg": float(control.delta_a_diff_deg),
            "right_deflection_deg": float(control.right_deflection_deg),
            "left_deflection_deg": float(control.left_deflection_deg),
            "mixing": {
                "right": "delta_e_sym_deg + delta_a_diff_deg",
                "left": "delta_e_sym_deg - delta_a_diff_deg",
            },
            "sign_convention": "positive is trailing-edge down",
        },
        "hinge": {
            "axis_model": "single straight rigid-body axis between end stations",
            "axis_start_m": hinge_axis_start.tolist(),
            "axis_end_m": hinge_axis_end.tolist(),
            "axis_length_m": hinge_length,
            "sample_count": len(hinge_samples_array),
            "max_source_curve_deviation_m": hinge_straightness_max,
            "max_source_curve_deviation_fraction_axis": (
                hinge_straightness_max / max(hinge_length, 1.0e-12)
            ),
        },
        "kinematics": {
            "right_neutral_center_m": right_center_neutral.tolist(),
            "right_deflected_center_m": right_center_deflected.tolist(),
            "right_center_displacement_m": right_center_delta.tolist(),
            "left_neutral_center_m": left_center_neutral.tolist(),
            "left_deflected_center_m": left_center_deflected.tolist(),
            "left_center_displacement_m": left_center_delta.tolist(),
            "positive_command_moves_center_down": kinematic_sign_ok,
            "right_rotation_volume_relative_error": right_rotation_volume_error,
            "left_rotation_volume_relative_error": left_rotation_volume_error,
            "rigid_rotation_preserves_volume": rigid_rotation_ok,
        },
        "bodies": body_reports,
        "neutral_bodies": neutral_reports,
        "qc": {
            "all_bodies_valid": validity_ok,
            "all_bodies_contain_solids": solid_count_ok,
            "right_fixed_control_intersection_m3": overlap_right,
            "left_fixed_control_intersection_m3": overlap_left,
            "intersection_volume_limit_m3": overlap_limit,
            "no_material_intersection": overlap_ok,
            "right_left_neutral_intersection_m3": symmetry_overlap,
            "right_left_neutral_intersection_limit_m3": symmetry_overlap_limit,
            "no_right_left_material_intersection": symmetry_ok,
            "kinematic_sign_ok": kinematic_sign_ok,
            "rigid_rotation_preserves_volume": rigid_rotation_ok,
            "master_to_neutral_cad_deviation_ok": master_cad_ok,
            "right_fixed_control_clearance_m": _shape_distance(
                right_fixed,
                right_control,
            ),
            "left_fixed_control_clearance_m": _shape_distance(
                left_fixed,
                left_control,
            ),
            "right_neutral_full_volume_m3": right_full_volume,
            "right_fixed_volume_m3": right_fixed_volume,
            "right_neutral_elevon_volume_m3": right_control_volume,
            "right_partition_residual_or_cove_volume_m3": partition_residual,
            "right_partition_residual_fraction_full": (
                partition_residual / max(right_full_volume, 1.0e-12)
            ),
            "accepted": accepted,
        },
        "spec": spec.to_dict(),
    }
    if not accepted and spec.fail_on_invalid:
        raise RuntimeError(
            "Physical CAD QC rejected the model: "
            f"valid={validity_ok}, solids={solid_count_ok}, "
            f"overlap_right={overlap_right:.6e}, overlap_left={overlap_left:.6e}, "
            f"root_overlap={symmetry_overlap:.6e}, root_symmetry={symmetry_ok}, "
            f"kinematics={kinematic_sign_ok}, rigid_rotation={rigid_rotation_ok}, "
            f"master_to_cad={master_cad_ok}"
        )
    return PhysicalCadModel(
        state_id=state_id,
        spec=spec,
        neutral_bodies=neutral_bodies,
        neutral_split_bodies=neutral_split_bodies,
        deflected_bodies=deflected_bodies,
        report=report,
        neutral_mesh=neutral_mesh,
    )


def _scale_shape_for_step(shape: Any) -> Any:
    # Aeris geometry is in metres; STEP is written with millimetre coordinates
    # and the standard STEP millimetre unit.
    return shape.scale(1000.0)


def _export_step_assembly(
    bodies: Mapping[str, Any],
    path: Path,
    *,
    assembly_name: str,
) -> None:
    import cadquery as cq

    assembly = cq.Assembly(name=assembly_name)
    palette = (
        cq.Color(0.23, 0.49, 0.68),
        cq.Color(0.95, 0.55, 0.12),
        cq.Color(0.30, 0.65, 0.50),
        cq.Color(0.72, 0.31, 0.28),
    )
    for index, (name, shape) in enumerate(bodies.items()):
        assembly.add(
            _scale_shape_for_step(shape),
            name=name,
            color=palette[index % len(palette)],
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    assembly.export(str(path), exportType="STEP", mode="default")


def _export_step_body(shape: Any, path: Path) -> None:
    from cadquery import exporters

    path.parent.mkdir(parents=True, exist_ok=True)
    exporters.export(
        _scale_shape_for_step(shape),
        fname=str(path),
        exportType="STEP",
    )


def audit_step_with_gmsh(
    path: Path,
    *,
    expected_volumes: int,
) -> dict[str, Any]:
    """Re-import a STEP assembly and count the solids seen by Gmsh OCC."""

    report: dict[str, Any] = {
        "status": "unavailable",
        "path": str(path),
        "expected_volume_count": int(expected_volumes),
        "imported_volume_count": None,
        "imported_surface_count": None,
        "accepted": None,
    }
    try:
        import gmsh
    except Exception as exc:
        report["reason"] = f"{type(exc).__name__}: {exc}"
        return report

    if bool(gmsh.isInitialized()):
        report["status"] = "skipped_existing_gmsh_session"
        report["reason"] = "Refusing to disturb a caller-owned Gmsh model."
        return report

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add(f"pygeo_step_audit_{sha256(str(path).encode()).hexdigest()[:10]}")
        gmsh.model.occ.importShapes(str(path))
        gmsh.model.occ.synchronize()
        volume_count = len(gmsh.model.getEntities(3))
        surface_count = len(gmsh.model.getEntities(2))
        accepted = volume_count == int(expected_volumes)
        report.update(
            {
                "status": "accepted" if accepted else "rejected",
                "imported_volume_count": volume_count,
                "imported_surface_count": surface_count,
                "accepted": accepted,
            }
        )
    except Exception as exc:
        report.update(
            {
                "status": "failed",
                "reason": f"{type(exc).__name__}: {exc}",
                "accepted": False,
            }
        )
    finally:
        gmsh.finalize()
    return report


def _export_brep_body(shape: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    shape.exportBrep(str(path))


def tessellate_bodies(
    bodies: Mapping[str, Any],
    spec: PhysicalCadSpec,
) -> dict[str, Any]:
    """Tessellate named OCC bodies in metres for diagnostics and handoff."""

    vertices_all: list[np.ndarray] = []
    faces_all: list[np.ndarray] = []
    body_ids: list[np.ndarray] = []
    body_names = list(bodies)
    offset = 0
    for body_id, name in enumerate(body_names):
        vertices, faces = bodies[name].tessellate(
            spec.tessellation_tolerance_m,
            spec.tessellation_angular_tolerance_rad,
        )
        xyz = np.asarray([vertex.toTuple() for vertex in vertices], dtype=float)
        triangles = np.asarray(faces, dtype=np.int64)
        if xyz.ndim != 2 or xyz.shape[1] != 3 or triangles.ndim != 2:
            raise RuntimeError(f"Unexpected tessellation for body {name!r}")
        vertices_all.append(xyz)
        faces_all.append(triangles + offset)
        body_ids.append(np.full(len(triangles), body_id, dtype=np.int32))
        offset += len(xyz)
    return {
        "vertices_m": np.vstack(vertices_all),
        "triangles": np.vstack(faces_all),
        "triangle_body_id": np.concatenate(body_ids),
        "body_names": body_names,
    }


def audit_master_to_neutral_cad(
    upper_surface_m: np.ndarray,
    lower_surface_m: np.ndarray,
    neutral_mesh: Mapping[str, Any],
    *,
    reference_chord_m: float,
    max_deviation_cref: float,
) -> dict[str, Any]:
    """Measure sampled native-pyGeo OML points against the neutral OCC surface."""

    report: dict[str, Any] = {
        "status": "unavailable",
        "measurement": "native pyGeo sample points to tessellated neutral OCC surface",
        "distance_units": "m",
        "reference_chord_m": float(reference_chord_m),
        "max_allowed_cref": float(max_deviation_cref),
        "accepted": None,
    }
    try:
        import pyvista as pv
    except Exception as exc:
        report["reason"] = f"{type(exc).__name__}: {exc}"
        return report

    try:
        vertices = np.asarray(neutral_mesh["vertices_m"], dtype=float)
        triangles = np.asarray(neutral_mesh["triangles"], dtype=np.int64)
        master_points = np.vstack(
            (
                np.asarray(upper_surface_m, dtype=float).reshape(-1, 3),
                np.asarray(lower_surface_m, dtype=float).reshape(-1, 3),
            )
        )
        master_points = master_points[np.all(np.isfinite(master_points), axis=1)]
        faces = np.column_stack((np.full(len(triangles), 3, dtype=np.int64), triangles)).reshape(-1)
        cad_surface = pv.PolyData(vertices, faces)
        measured = pv.PolyData(master_points).compute_implicit_distance(cad_surface)
        distances = np.abs(np.asarray(measured["implicit_distance"], dtype=float))
        if not len(distances) or not np.all(np.isfinite(distances)):
            raise RuntimeError("Surface-distance calculation returned invalid values")
        reference = max(float(reference_chord_m), 1.0e-12)
        rms_m = float(np.sqrt(np.mean(np.square(distances))))
        p95_m = float(np.quantile(distances, 0.95))
        p99_m = float(np.quantile(distances, 0.99))
        max_m = float(np.max(distances))
        max_cref = max_m / reference
        accepted = max_cref <= float(max_deviation_cref)
        report.update(
            {
                "status": "accepted" if accepted else "rejected",
                "sample_count": int(len(distances)),
                "cad_triangle_count": int(len(triangles)),
                "rms_m": rms_m,
                "p95_m": p95_m,
                "p99_m": p99_m,
                "max_m": max_m,
                "rms_cref": rms_m / reference,
                "p95_cref": p95_m / reference,
                "p99_cref": p99_m / reference,
                "max_cref": max_cref,
                "accepted": accepted,
            }
        )
    except Exception as exc:
        report.update(
            {
                "status": "failed",
                "reason": f"{type(exc).__name__}: {exc}",
                "accepted": False,
            }
        )
    return report


def _write_ascii_stl(path: Path, mesh: Mapping[str, Any], solid_name: str) -> None:
    vertices = np.asarray(mesh["vertices_m"], dtype=float)
    triangles = np.asarray(mesh["triangles"], dtype=np.int64)
    body_ids = np.asarray(mesh["triangle_body_id"], dtype=np.int32)
    body_names = list(mesh["body_names"])
    lines: list[str] = []
    for body_id, body_name in enumerate(body_names):
        lines.append(f"solid {solid_name}_{body_name}")
        for triangle in triangles[body_ids == body_id]:
            points = vertices[triangle]
            normal = np.cross(points[1] - points[0], points[2] - points[0])
            norm = float(np.linalg.norm(normal))
            if norm > 0.0:
                normal /= norm
            lines.append("  facet normal " + " ".join(f"{float(value):.10e}" for value in normal))
            lines.append("    outer loop")
            for point in points:
                lines.append("      vertex " + " ".join(f"{float(value):.10e}" for value in point))
            lines.extend(("    endloop", "  endfacet"))
        lines.append(f"endsolid {solid_name}_{body_name}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_obj(path: Path, mesh: Mapping[str, Any]) -> None:
    vertices = np.asarray(mesh["vertices_m"], dtype=float)
    triangles = np.asarray(mesh["triangles"], dtype=np.int64)
    body_ids = np.asarray(mesh["triangle_body_id"], dtype=np.int32)
    body_names = list(mesh["body_names"])
    lines = [
        "# pyGeo physical control geometry",
        "# units: metres",
        *["v " + " ".join(f"{float(value):.10e}" for value in point) for point in vertices],
    ]
    for body_id, body_name in enumerate(body_names):
        lines.append(f"g {body_name}")
        lines.extend(
            "f " + " ".join(str(int(index) + 1) for index in triangle)
            for triangle in triangles[body_ids == body_id]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_vtk(path: Path, mesh: Mapping[str, Any]) -> None:
    vertices = np.asarray(mesh["vertices_m"], dtype=float)
    triangles = np.asarray(mesh["triangles"], dtype=np.int64)
    body_ids = np.asarray(mesh["triangle_body_id"], dtype=np.int32)
    lines = [
        "# vtk DataFile Version 3.0",
        "pyGeo physical control geometry; units=m",
        "ASCII",
        "DATASET POLYDATA",
        f"POINTS {len(vertices)} double",
        *[" ".join(f"{float(value):.10e}" for value in point) for point in vertices],
        f"POLYGONS {len(triangles)} {4 * len(triangles)}",
        *["3 " + " ".join(str(int(index)) for index in triangle) for triangle in triangles],
        f"CELL_DATA {len(triangles)}",
        "SCALARS body_id int 1",
        "LOOKUP_TABLE default",
        *[str(int(value)) for value in body_ids],
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_mesh_npz(path: Path, mesh: Mapping[str, Any]) -> None:
    np.savez_compressed(
        path,
        vertices_m=np.asarray(mesh["vertices_m"], dtype=float),
        triangles=np.asarray(mesh["triangles"], dtype=np.int64),
        triangle_body_id=np.asarray(mesh["triangle_body_id"], dtype=np.int32),
        body_names=np.asarray(mesh["body_names"], dtype=str),
    )


def plot_physical_cad(
    mesh: Mapping[str, Any],
    path: Path,
    *,
    title: str,
    dpi: int,
) -> None:
    """Write isometric, top, and rear views of the exact tessellated bodies."""

    vertices = np.asarray(mesh["vertices_m"], dtype=float)
    triangles = np.asarray(mesh["triangles"], dtype=np.int64)
    body_ids = np.asarray(mesh["triangle_body_id"], dtype=np.int32)
    body_names = list(mesh["body_names"])
    colors = ("#3A78A1", "#E28E2C", "#4E9F78", "#C44E52")
    fig = plt.figure(figsize=(15, 6.5))
    axis_3d = fig.add_subplot(1, 3, 1, projection="3d")
    axis_top = fig.add_subplot(1, 3, 2)
    axis_rear = fig.add_subplot(1, 3, 3)

    for body_id, body_name in enumerate(body_names):
        selected = triangles[body_ids == body_id]
        if len(selected) == 0:
            continue
        color = colors[body_id % len(colors)]
        polygons = vertices[selected]
        # Matplotlib remains responsive on large tessellations while the full
        # mesh is still preserved in STL/OBJ/VTK/NPZ.
        stride = max(1, int(math.ceil(len(polygons) / 4500)))
        collection = Poly3DCollection(
            polygons[::stride],
            facecolor=color,
            edgecolor="none",
            alpha=0.92,
            label=body_name,
        )
        axis_3d.add_collection3d(collection)
        body_vertices = vertices[np.unique(selected)]
        axis_top.scatter(
            body_vertices[:: max(1, len(body_vertices) // 2500), 0],
            body_vertices[:: max(1, len(body_vertices) // 2500), 1],
            s=0.4,
            color=color,
            label=body_name,
        )
        axis_rear.scatter(
            body_vertices[:: max(1, len(body_vertices) // 2500), 1],
            body_vertices[:: max(1, len(body_vertices) // 2500), 2],
            s=0.4,
            color=color,
        )

    mins = np.min(vertices, axis=0)
    maxs = np.max(vertices, axis=0)
    center = 0.5 * (mins + maxs)
    span = np.maximum(maxs - mins, 1.0e-6)
    radius = 0.53 * float(np.max(span))
    axis_3d.set_xlim(center[0] - radius, center[0] + radius)
    axis_3d.set_ylim(center[1] - radius, center[1] + radius)
    axis_3d.set_zlim(center[2] - 0.45 * radius, center[2] + 0.45 * radius)
    axis_3d.set_box_aspect((1.0, 1.0, 0.45))
    axis_3d.view_init(elev=25, azim=-128)
    axis_3d.set_xlabel("x [m]")
    axis_3d.set_ylabel("y [m]")
    axis_3d.set_zlabel("z [m]")
    axis_3d.set_title("Physical split assembly")

    axis_top.set_aspect("equal", adjustable="box")
    axis_top.set_xlabel("x [m]")
    axis_top.set_ylabel("y [m]")
    axis_top.set_title("Top")
    axis_top.grid(True, alpha=0.2)
    axis_top.legend(loc="best", fontsize=7)
    axis_rear.set_aspect("equal", adjustable="box")
    axis_rear.set_xlabel("y [m]")
    axis_rear.set_ylabel("z [m]")
    axis_rear.set_title("Rear")
    axis_rear.grid(True, alpha=0.2)
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, dpi=int(dpi), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def mesh_handoff_payload(
    *,
    model: PhysicalCadModel,
    case_dir: Path,
    artifacts: Mapping[str, str],
) -> dict[str, Any]:
    """Describe the supported neutral and deflected CFD mesh routes."""

    return {
        "schema": MESH_HANDOFF_SCHEMA,
        "geometry_id": model.report["geometry_id"],
        "state_id": model.state_id,
        "units": {
            "step": "millimetres encoded by STEP; Aeris geometry was scaled from metres",
            "stl_obj_vtk_npz": "numeric coordinates are metres",
        },
        "neutral_geometry": {
            "recommended_route": (
                "realised pyGeo sections -> Aeris structured surface topology "
                "-> PLOT3D surface -> pyHyp volume -> ADflow"
            ),
            "reason": (
                "The current pyHyp topology is a connected, single-body half-wing "
                "with a symmetry root and closed tip."
            ),
            "master_surface_npz": str(case_dir / "pygeo_surface.npz"),
            "neutral_step": artifacts.get("neutral_step"),
            "master_to_cad_surface_audit": model.report["master_geometry"][
                "neutral_cad_surface_deviation"
            ],
        },
        "physical_deflected_geometry": {
            "gap_model": model.report["topology"]["control_gap_model"],
            "gap_is_fluid_domain": model.report["topology"]["gap_is_fluid_domain"],
            "fidelity_role": model.report["topology"]["fidelity_role"],
            "gap_drag_validated_as_aircraft_truth": False,
            "requires_gap_resolution_study": True,
            "recommended_route": (
                "named multi-solid STEP assembly -> CAD-aware surface/volume mesher "
                "-> SU2; use Aeris cad_gmsh_tet_v1 for geometry/Euler or wall-function "
                "validation, then add a prism-layer production backend"
            ),
            "step_assembly": artifacts.get("deflected_step"),
            "body_steps": artifacts.get("body_step_directory"),
            "diagnostic_surface_mesh": artifacts.get("deflected_npz"),
            "facet_exports_solver_ready": False,
            "reason": (
                "A split/gapped control has multiple wall bodies and moving gap/cove "
                "topology. Reusing or merely rotating the neutral structured surface "
                "mesh does not preserve connectivity, gap resolution, or cell quality."
            ),
        },
        "pyhyp_policy": {
            "neutral": "supported after a pyGeo-to-structured-surface adapter",
            "deflected_split_elevon": (
                "not supported by the existing Aeris single-body surface topology"
            ),
            "future_options": [
                "dedicated multi-block surface topology regenerated per deflection",
                "overset moving-control grids for ADflow",
                "mesh deformation only for sealed, small-deflection controls",
            ],
        },
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def export_physical_cad(
    model: PhysicalCadModel,
    case_dir: Path,
    *,
    output_flags: Mapping[str, Any],
    visualization_enabled: bool,
    dpi: int,
) -> dict[str, Any]:
    """Export CAD, named facet meshes, QC metadata, and visual evidence."""

    cad_dir = Path(case_dir) / "cad"
    body_dir = cad_dir / "bodies"
    mesh_dir = Path(case_dir) / "mesh_handoff"
    cad_dir.mkdir(parents=True, exist_ok=True)
    body_dir.mkdir(parents=True, exist_ok=True)
    mesh_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}
    export_status: dict[str, str] = {}
    step_import_audit: dict[str, Any] | None = None

    def enabled(key: str, default: bool = True) -> bool:
        return bool(output_flags.get(key, default))

    if enabled("write_step"):
        try:
            neutral_path = cad_dir / "neutral_full.step"
            neutral_split_path = cad_dir / "neutral_split_assembly.step"
            deflected_path = cad_dir / "deflected_split_assembly.step"
            _export_step_assembly(
                model.neutral_bodies,
                neutral_path,
                assembly_name="pygeo_neutral_full",
            )
            _export_step_assembly(
                model.neutral_split_bodies,
                neutral_split_path,
                assembly_name="pygeo_neutral_split",
            )
            _export_step_assembly(
                model.deflected_bodies,
                deflected_path,
                assembly_name="pygeo_physical_deflected",
            )
            for name, shape in model.deflected_bodies.items():
                _export_step_body(shape, body_dir / f"{name}.step")
            artifacts.update(
                {
                    "neutral_step": str(neutral_path),
                    "neutral_split_step": str(neutral_split_path),
                    "deflected_step": str(deflected_path),
                    "body_step_directory": str(body_dir),
                }
            )
            export_status["step"] = "written"
            if enabled("verify_step_import", True):
                step_import_audit = audit_step_with_gmsh(
                    deflected_path,
                    expected_volumes=len(model.deflected_bodies),
                )
                audit_path = cad_dir / "step_import_audit.json"
                _write_json(audit_path, step_import_audit)
                artifacts["step_import_audit"] = str(audit_path)
                export_status["step_import_audit"] = str(step_import_audit["status"])
                if step_import_audit.get("accepted") is False:
                    raise RuntimeError(f"Gmsh STEP audit rejected the export: {step_import_audit}")
        except Exception as exc:
            export_status["step"] = f"failed: {type(exc).__name__}: {exc}"
            if model.spec.fail_on_invalid:
                raise

    if enabled("write_brep", False):
        try:
            for name, shape in model.deflected_bodies.items():
                _export_brep_body(shape, body_dir / f"{name}.brep")
            artifacts["body_brep_directory"] = str(body_dir)
            export_status["brep"] = "written"
        except Exception as exc:
            export_status["brep"] = f"failed: {type(exc).__name__}: {exc}"
            if model.spec.fail_on_invalid:
                raise

    needs_mesh = (
        any(enabled(key) for key in ("write_stl", "write_obj", "write_vtk", "write_cad_npz"))
        or visualization_enabled
    )
    neutral_mesh = model.neutral_mesh
    deflected_mesh: dict[str, Any] | None = None
    if needs_mesh:
        deflected_mesh = tessellate_bodies(model.deflected_bodies, model.spec)

    if enabled("write_stl") and deflected_mesh is not None:
        path = mesh_dir / "deflected_split_surface_m.stl"
        _write_ascii_stl(path, deflected_mesh, "pygeo_deflected")
        artifacts["deflected_stl"] = str(path)
        export_status["stl"] = "written"
    if enabled("write_obj") and deflected_mesh is not None:
        path = mesh_dir / "deflected_split_surface_m.obj"
        _write_obj(path, deflected_mesh)
        artifacts["deflected_obj"] = str(path)
        export_status["obj"] = "written"
    if enabled("write_vtk") and deflected_mesh is not None:
        path = mesh_dir / "deflected_split_surface_m.vtk"
        _write_vtk(path, deflected_mesh)
        artifacts["deflected_vtk"] = str(path)
        export_status["vtk"] = "written"
    if enabled("write_cad_npz") and deflected_mesh is not None:
        deflected_path = mesh_dir / "deflected_split_surface_m.npz"
        _write_mesh_npz(deflected_path, deflected_mesh)
        artifacts["deflected_npz"] = str(deflected_path)
        if neutral_mesh is not None:
            neutral_path = mesh_dir / "neutral_full_surface_m.npz"
            _write_mesh_npz(neutral_path, neutral_mesh)
            artifacts["neutral_npz"] = str(neutral_path)
        export_status["cad_npz"] = "written"

    if visualization_enabled and deflected_mesh is not None:
        path = Path(case_dir) / "physical_deflected_geometry.png"
        plot_physical_cad(
            deflected_mesh,
            path,
            title=(
                f"pyGeo physical controls · "
                f"right {model.report['commands']['right_deflection_deg']:+.1f}° · "
                f"left {model.report['commands']['left_deflection_deg']:+.1f}°"
            ),
            dpi=dpi,
        )
        artifacts["physical_deflected_visualization"] = str(path)
        export_status["visualization"] = "written"

    handoff = mesh_handoff_payload(
        model=model,
        case_dir=Path(case_dir),
        artifacts=artifacts,
    )
    handoff["physical_deflected_geometry"]["step_import_audit"] = step_import_audit
    handoff_path = mesh_dir / "mesh_handoff.json"
    _write_json(handoff_path, handoff)
    artifacts["mesh_handoff_manifest"] = str(handoff_path)

    manifest = dict(model.report)
    manifest["exports"] = export_status
    manifest["artifacts"] = artifacts
    manifest["mesh_handoff"] = handoff
    manifest["step_import_audit"] = step_import_audit
    manifest_path = cad_dir / "physical_control_manifest.json"
    _write_json(manifest_path, manifest)
    artifacts["physical_control_manifest"] = str(manifest_path)
    return {
        "status": manifest["status"],
        "state_id": model.state_id,
        "exports": export_status,
        "artifacts": artifacts,
        "metrics": {
            "physical_cad_accepted": bool(manifest["qc"]["accepted"]),
            "physical_cad_body_count": len(model.deflected_bodies),
            "physical_cad_gap_model": str(manifest["topology"]["control_gap_model"]),
            "physical_cad_nominal_hinge_gap_fraction": float(
                manifest["topology"]["hinge_gap_fraction"]
            ),
            "physical_cad_fixed_cove_cut_xc": float(
                manifest["topology"]["fixed_cove_cut_x_over_c"]
            ),
            "physical_cad_elevon_le_cut_xc": float(manifest["topology"]["elevon_le_cut_x_over_c"]),
            "physical_cad_effective_cove_width_fraction": float(
                manifest["topology"]["elevon_le_cut_x_over_c"]
                - manifest["topology"]["fixed_cove_cut_x_over_c"]
            ),
            "physical_cad_step_import_status": (
                step_import_audit["status"] if step_import_audit is not None else "not_run"
            ),
            "physical_cad_step_import_volume_count": (
                step_import_audit.get("imported_volume_count")
                if step_import_audit is not None
                else None
            ),
            "physical_cad_hinge_axis_length_m": float(manifest["hinge"]["axis_length_m"]),
            "physical_cad_hinge_straightness_max_m": float(
                manifest["hinge"]["max_source_curve_deviation_m"]
            ),
            "physical_cad_right_intersection_m3": float(
                manifest["qc"]["right_fixed_control_intersection_m3"]
            ),
            "physical_cad_left_intersection_m3": float(
                manifest["qc"]["left_fixed_control_intersection_m3"]
            ),
            "physical_cad_root_intersection_m3": float(
                manifest["qc"]["right_left_neutral_intersection_m3"]
            ),
            "physical_cad_root_symmetry_ok": bool(
                manifest["qc"]["no_right_left_material_intersection"]
            ),
            "physical_cad_right_center_delta_z_m": float(
                manifest["kinematics"]["right_center_displacement_m"][2]
            ),
            "physical_cad_left_center_delta_z_m": float(
                manifest["kinematics"]["left_center_displacement_m"][2]
            ),
            "physical_cad_right_clearance_m": float(
                manifest["qc"]["right_fixed_control_clearance_m"]
            ),
            "physical_cad_left_clearance_m": float(
                manifest["qc"]["left_fixed_control_clearance_m"]
            ),
            "physical_cad_kinematic_sign_ok": bool(manifest["qc"]["kinematic_sign_ok"]),
            "physical_cad_reconstruction_warp_rms_m": float(
                manifest["master_geometry"]["reconstruction_plane_warp_rms_m"]
            ),
            "physical_cad_reconstruction_warp_max_m": float(
                manifest["master_geometry"]["reconstruction_plane_warp_max_m"]
            ),
            "physical_cad_master_to_cad_status": str(
                manifest["master_geometry"]["neutral_cad_surface_deviation"]["status"]
            ),
            "physical_cad_master_to_cad_rms_m": manifest["master_geometry"][
                "neutral_cad_surface_deviation"
            ].get("rms_m"),
            "physical_cad_master_to_cad_p95_m": manifest["master_geometry"][
                "neutral_cad_surface_deviation"
            ].get("p95_m"),
            "physical_cad_master_to_cad_max_m": manifest["master_geometry"][
                "neutral_cad_surface_deviation"
            ].get("max_m"),
            "physical_cad_master_to_cad_max_cref": manifest["master_geometry"][
                "neutral_cad_surface_deviation"
            ].get("max_cref"),
        },
    }
