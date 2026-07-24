"""pyGeo lofting, section extraction, and CST utilities for the Aeris BWB generator.

This is the reusable production layer behind the optional pyGeo realization
backend. It consumes Aeris section records and uses Aeris's CST implementation
without registering a second geometry family.

The central operation is:

    authored stations -> pyGeo B-spline loft -> realised 3-D slices
    -> normalised 2-D section -> CST fit -> downstream aerodynamic geometry

The realised slices, rather than the authored control sections, are used for
AVL.  This is essential for kSpan > 2 because the pyGeo B-spline surface does
not generally pass through every interior authored section.
"""

from __future__ import annotations

import io
import math
import warnings
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
from scipy.spatial.transform import Rotation

from aeris.airfoil.cst_generator import CSTAirfoil, cosine_spacing

_EPS = 1.0e-12


@dataclass(frozen=True)
class StationDefinition:
    """Minimal station contract accepted by pyGeo."""

    index: int
    x_le_m: float
    y_m: float
    z_le_m: float
    chord_m: float
    twist_deg: float
    dihedral_deg: float
    airfoil_name: str
    airfoil_path: Path


@dataclass(frozen=True)
class PyGeoBuild:
    """pyGeo object plus the exact station-frame inputs used to create it."""

    geometry: Any
    stdout: str
    k_span: int
    frame_mode: str
    rot_x_deg: np.ndarray
    rot_y_deg: np.ndarray
    rot_z_deg: np.ndarray
    thickness_scale: np.ndarray
    frame_reconstruction_error: float


@dataclass
class ExtractedSection:
    """A physical fixed-span slice extracted from the realised pyGeo loft."""

    index: int
    span_fraction: float
    v_parameter: float
    le_xyz_m: np.ndarray
    te_xyz_m: np.ndarray
    chord_m: float
    twist_deg: float
    local_span_axis: np.ndarray
    chord_axis: np.ndarray
    thickness_axis: np.ndarray
    upper_xyz_m: np.ndarray
    lower_xyz_m: np.ndarray
    x_upper: np.ndarray
    z_upper: np.ndarray
    x_lower: np.ndarray
    z_lower: np.ndarray
    direct_coordinates: np.ndarray
    cst: CSTAirfoil
    cst_order: int
    cst_rms_chord: float
    cst_max_chord: float
    plane_warp_rms_chord: float
    plane_warp_max_chord: float
    thickness_ratio: float
    max_camber_ratio: float
    cst_valid: bool
    cst_failures: tuple[str, ...]

    @property
    def y_m(self) -> float:
        return float(self.le_xyz_m[1])

    @property
    def z_le_m(self) -> float:
        return float(self.le_xyz_m[2])

    @property
    def x_le_m(self) -> float:
        return float(self.le_xyz_m[0])

    def as_metrics_row(self) -> dict[str, float | int | str | bool]:
        return {
            "section_index": self.index,
            "span_fraction": self.span_fraction,
            "v_parameter": self.v_parameter,
            "x_le_m": self.x_le_m,
            "y_le_m": self.y_m,
            "z_le_m": self.z_le_m,
            "chord_m": self.chord_m,
            "twist_deg": self.twist_deg,
            "cst_order": self.cst_order,
            "cst_rms_chord": self.cst_rms_chord,
            "cst_max_chord": self.cst_max_chord,
            "plane_warp_rms_chord": self.plane_warp_rms_chord,
            "plane_warp_max_chord": self.plane_warp_max_chord,
            "thickness_ratio": self.thickness_ratio,
            "max_camber_ratio": self.max_camber_ratio,
            "cst_valid": self.cst_valid,
            "cst_failures": "|".join(self.cst_failures),
        }


def read_airfoil_coordinates(path: Path) -> np.ndarray:
    """Read a header-tolerant two-column Selig airfoil file."""

    rows: list[tuple[float, float]] = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.replace(",", " ").split()
        if len(fields) < 2:
            continue
        try:
            rows.append((float(fields[0]), float(fields[1])))
        except ValueError:
            continue
    points = np.asarray(rows, dtype=float)
    if points.ndim != 2 or points.shape[0] < 5 or points.shape[1] != 2:
        raise ValueError(f"{path}: not a valid two-column airfoil file")
    if not np.all(np.isfinite(points)):
        raise ValueError(f"{path}: airfoil contains non-finite coordinates")
    return points


def resolve_airfoil_path(name: str, airfoil_database: Path) -> Path:
    """Resolve an AeroSandbox-style name against the project airfoil database."""

    raw = Path(name).expanduser()
    candidates = (
        raw,
        Path(airfoil_database) / raw,
        Path(airfoil_database) / f"{name}.dat",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    checked = ", ".join(str(p.resolve()) for p in candidates)
    raise FileNotFoundError(f"Could not resolve airfoil {name!r}; checked {checked}")


def stations_from_records(
    records: Iterable[Any],
    airfoil_database: Path,
) -> list[StationDefinition]:
    """Convert Aeris ``SectionRecord``-like objects to the local contract."""

    stations: list[StationDefinition] = []
    for fallback_index, record in enumerate(records):
        name = str(record.airfoil_name)
        station = StationDefinition(
            index=int(getattr(record, "index", fallback_index)),
            x_le_m=float(record.x_le_m),
            y_m=float(record.y_m),
            z_le_m=float(record.z_le_m),
            chord_m=float(record.chord_m),
            twist_deg=float(record.twist_deg),
            dihedral_deg=float(getattr(record, "dihedral_deg", 0.0)),
            airfoil_name=name,
            airfoil_path=resolve_airfoil_path(name, airfoil_database),
        )
        stations.append(station)
    _validate_stations(stations)
    return stations


def _validate_stations(stations: Sequence[StationDefinition]) -> None:
    if len(stations) < 2:
        raise ValueError("At least two stations are required")
    y = np.asarray([s.y_m for s in stations])
    chord = np.asarray([s.chord_m for s in stations])
    if np.any(np.diff(y) <= 0.0):
        raise ValueError("Station y coordinates must be strictly increasing")
    if np.any(chord <= 0.0):
        raise ValueError("All station chords must be positive")


def _unit(vector: np.ndarray, label: str) -> np.ndarray:
    vector = np.asarray(vector, dtype=float)
    magnitude = float(np.linalg.norm(vector))
    if not np.isfinite(magnitude) or magnitude <= _EPS:
        raise ValueError(f"Cannot normalise degenerate {label}: {vector}")
    return vector / magnitude


def _axis_angle_matrix(axis: np.ndarray, angle_deg: float) -> np.ndarray:
    """Right-hand active rotation, matching AeroSandbox and pyGeo."""

    return Rotation.from_rotvec(
        _unit(axis, "rotation axis") * math.radians(float(angle_deg))
    ).as_matrix()


def _asb_station_frames(
    stations: Sequence[StationDefinition],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Reproduce AeroSandbox's WingXSec frames.

    Returns ``(rotation_matrices, thickness_miter_scales, span_axes)``.
    The miter scale is the magnitude AeroSandbox applies to the local
    thickness axis at an interior dihedral break.
    """

    xyz = np.asarray([[s.x_le_m, s.y_m, s.z_le_m] for s in stations], dtype=float)
    n = len(stations)
    segment_axes: list[np.ndarray] = []
    for delta in np.diff(xyz, axis=0):
        yz = np.array([0.0, delta[1], delta[2]])
        segment_axes.append(_unit(yz, "station-to-station YZ direction"))

    frames = np.empty((n, 3, 3), dtype=float)
    span_axes = np.empty((n, 3), dtype=float)
    thickness_scales = np.ones(n, dtype=float)
    global_x = np.array([1.0, 0.0, 0.0])

    for i, station in enumerate(stations):
        if i == 0:
            span_axis = segment_axes[0]
            miter_scale = 1.0
        elif i == n - 1:
            span_axis = segment_axes[-1]
            miter_scale = 1.0
        else:
            before = segment_axes[i - 1]
            after = segment_axes[i]
            span_axis = _unit(0.5 * (before + after), "averaged station span axis")
            cosine = float(np.clip(np.dot(before, after), -1.0, 1.0))
            miter_scale = math.sqrt(2.0 / (cosine + 1.0))

        untwisted_z = _unit(np.cross(global_x, span_axis), "untwisted thickness axis")
        twist_rotation = _axis_angle_matrix(span_axis, station.twist_deg)
        chord_axis = twist_rotation @ global_x
        thickness_axis = twist_rotation @ untwisted_z

        # The input airfoil is in pyGeo's x-y plane.  The third column is
        # -span_axis so [x, thickness, -span] remains right-handed.
        frame = np.column_stack([chord_axis, thickness_axis, -span_axis])
        frames[i] = frame
        span_axes[i] = span_axis
        thickness_scales[i] = miter_scale

    return frames, thickness_scales, span_axes


def pygeo_frame_inputs(
    stations: Sequence[StationDefinition],
    frame_mode: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
    """Return pyGeo Euler inputs and a reconstruction audit metric.

    pyGeo applies ``R_y(rotY) @ R_x(rotX) @ R_z(rotZ)``.  SciPy's intrinsic
    ``YXZ`` convention is the same matrix product, so it provides a stable
    matrix-to-Euler conversion for the exact AeroSandbox frame.
    """

    n = len(stations)
    mode = str(frame_mode).strip().lower()
    if mode == "global_y":
        rot_x = np.full(n, 90.0)
        rot_y = np.asarray([s.twist_deg for s in stations], dtype=float)
        rot_z = np.zeros(n)
        thickness_scale = np.ones(n)
        return rot_x, rot_y, rot_z, thickness_scale, 0.0

    if mode == "dihedral_euler":
        rot_x = 90.0 + np.asarray([s.dihedral_deg for s in stations], dtype=float)
        rot_y = np.asarray([s.twist_deg for s in stations], dtype=float)
        rot_z = np.zeros(n)
        thickness_scale = np.ones(n)
        return rot_x, rot_y, rot_z, thickness_scale, 0.0

    if mode != "asb_frame":
        raise ValueError("frame_mode must be one of: asb_frame, global_y, dihedral_euler")

    desired, thickness_scale, _ = _asb_station_frames(stations)
    angles = np.empty((n, 3), dtype=float)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Gimbal lock detected")
        for i, matrix in enumerate(desired):
            # Returned columns are rotY, rotX, rotZ for intrinsic YXZ.
            angles[i] = Rotation.from_matrix(matrix).as_euler("YXZ", degrees=True)

    reconstructed = Rotation.from_euler("YXZ", angles, degrees=True).as_matrix()
    reconstruction_error = float(np.max(np.abs(reconstructed - desired)))
    rot_y = angles[:, 0]
    rot_x = angles[:, 1]
    rot_z = angles[:, 2]
    return rot_x, rot_y, rot_z, thickness_scale, reconstruction_error


def build_pygeo(
    stations: Sequence[StationDefinition],
    *,
    k_span: int = 3,
    frame_mode: str = "asb_frame",
    n_ctl: int | None = None,
    tip: str = "none",
    tip_scale: float = 0.25,
) -> PyGeoBuild:
    """Build a pyGeo lifting surface from authored station definitions."""

    _validate_stations(stations)
    if not 2 <= int(k_span) <= len(stations):
        raise ValueError(f"k_span must be in [2, {len(stations)}]")
    if tip not in {"none", "rounded", "pinched"}:
        raise ValueError("tip must be one of: none, rounded, pinched")

    try:
        from pygeo import pyGeo
    except ImportError as exc:
        raise RuntimeError("pyGeo is not installed in this environment") from exc

    rot_x, rot_y, rot_z, thickness_scale, frame_error = pygeo_frame_inputs(stations, frame_mode)
    capture = io.StringIO()
    with redirect_stdout(capture):
        geometry = pyGeo(
            "liftingSurface",
            xsections=[str(s.airfoil_path) for s in stations],
            x=[s.x_le_m for s in stations],
            y=[s.y_m for s in stations],
            z=[s.z_le_m for s in stations],
            scale=[s.chord_m for s in stations],
            offset=np.zeros((len(stations), 2)),
            rotX=rot_x,
            rotY=rot_y,
            rotZ=rot_z,
            thickness=thickness_scale,
            nCtl=n_ctl,
            kSpan=int(k_span),
            bluntTe=False,
            roundedTe=False,
            squareTeTip=True,
            tip=tip,
            tipScale=float(tip_scale),
        )
    return PyGeoBuild(
        geometry=geometry,
        stdout=capture.getvalue(),
        k_span=int(k_span),
        frame_mode=frame_mode,
        rot_x_deg=np.asarray(rot_x),
        rot_y_deg=np.asarray(rot_y),
        rot_z_deg=np.asarray(rot_z),
        thickness_scale=np.asarray(thickness_scale),
        frame_reconstruction_error=frame_error,
    )


def sample_main_surfaces(
    build: PyGeoBuild,
    *,
    chordwise_points: int = 121,
    spanwise_points: int = 121,
) -> tuple[np.ndarray, np.ndarray]:
    """Sample pyGeo's main upper/lower B-spline patches."""

    if chordwise_points < 3 or spanwise_points < 2:
        raise ValueError("Need at least 3 chordwise and 2 spanwise points")
    u = np.linspace(0.0, 1.0, int(chordwise_points))
    v = np.linspace(0.0, 1.0, int(spanwise_points))
    v_grid, u_grid = np.meshgrid(v, u)
    upper = np.asarray(build.geometry.surfs[0](u_grid, v_grid), dtype=float)
    lower = np.asarray(build.geometry.surfs[1](u_grid, v_grid), dtype=float)
    return upper, lower


def _section_endpoints_at_v(build: PyGeoBuild, v: float) -> tuple[np.ndarray, np.ndarray]:
    """Return physical LE and TE midpoints at a pyGeo span parameter."""
    top = build.geometry.surfs[0]
    bottom = build.geometry.surfs[1]
    end_0 = 0.5 * (np.asarray(top(0.0, v), dtype=float) + np.asarray(bottom(0.0, v), dtype=float))
    end_1 = 0.5 * (np.asarray(top(1.0, v), dtype=float) + np.asarray(bottom(1.0, v), dtype=float))
    if end_0[0] >= end_1[0]:
        return end_1, end_0
    return end_0, end_1


def span_parameters_for_fractions(
    build: PyGeoBuild,
    span_fractions: Sequence[float],
    *,
    inversion_points: int = 4001,
) -> np.ndarray:
    """Invert the loft's physical quarter-chord y(v) relation."""
    fractions = np.asarray(span_fractions, dtype=float)
    if np.any(~np.isfinite(fractions)) or np.any((fractions < 0.0) | (fractions > 1.0)):
        raise ValueError("span_fractions must be finite and within [0, 1]")
    if inversion_points < 101:
        raise ValueError("inversion_points must be at least 101")

    dense_v = np.linspace(0.0, 1.0, int(inversion_points))
    y_quarter = np.empty_like(dense_v)
    for i, v in enumerate(dense_v):
        le, te = _section_endpoints_at_v(build, float(v))
        y_quarter[i] = (0.75 * le + 0.25 * te)[1]
    dy = np.diff(y_quarter)
    if np.any(dy < -1.0e-9):
        raise ValueError(
            "pyGeo quarter-chord y(v) is non-monotonic; a unique spanwise "
            "section extraction is not possible"
        )
    keep = np.concatenate([[True], dy > 1.0e-12])
    y_unique = y_quarter[keep]
    v_unique = dense_v[keep]
    if len(y_unique) < 2:
        raise ValueError("Degenerate pyGeo span: quarter-chord y is constant")
    y_target = y_unique[0] + fractions * (y_unique[-1] - y_unique[0])
    return np.interp(y_target, y_unique, v_unique)


def _quarter_chord_at_v(build: PyGeoBuild, v: float) -> np.ndarray:
    le, te = _section_endpoints_at_v(build, float(np.clip(v, 0.0, 1.0)))
    return 0.75 * le + 0.25 * te


def _collapse_surface_samples(x: np.ndarray, z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Sort a surface LE->TE and average repeated x locations."""
    x = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    z = np.asarray(z, dtype=float)
    order = np.argsort(x)
    x = x[order]
    z = z[order]
    rounded = np.round(x, decimals=12)
    unique, inverse = np.unique(rounded, return_inverse=True)
    z_sum = np.zeros(len(unique), dtype=float)
    counts = np.zeros(len(unique), dtype=float)
    np.add.at(z_sum, inverse, z)
    np.add.at(counts, inverse, 1.0)
    return unique, z_sum / counts


def _signed_twist_deg(chord_axis: np.ndarray, span_axis: np.ndarray) -> float:
    """Measure chord incidence about AeroSandbox's local YZ span axis."""
    reference = np.array([1.0, 0.0, 0.0])
    chord_projected = chord_axis - span_axis * float(np.dot(chord_axis, span_axis))
    chord_projected = _unit(chord_projected, "projected chord axis")
    sine = float(np.dot(span_axis, np.cross(reference, chord_projected)))
    cosine = float(np.clip(np.dot(reference, chord_projected), -1.0, 1.0))
    return math.degrees(math.atan2(sine, cosine))


def extract_section(
    build: PyGeoBuild,
    *,
    v_parameter: float,
    span_fraction: float,
    index: int,
    cst_order: int = 8,
    chordwise_points: int = 181,
) -> ExtractedSection:
    """Extract, planarise, normalise, and CST-fit one realised pyGeo slice."""
    v = float(v_parameter)
    if not 0.0 <= v <= 1.0:
        raise ValueError("v_parameter must be in [0, 1]")
    if chordwise_points < max(21, cst_order + 3):
        raise ValueError("chordwise_points is too small for the requested CST order")

    beta = np.linspace(0.0, math.pi, int(chordwise_points))
    u = 0.5 * (1.0 - np.cos(beta))
    vv = np.full_like(u, v)
    raw_top = np.asarray(build.geometry.surfs[0](u, vv), dtype=float)
    raw_bottom = np.asarray(build.geometry.surfs[1](u, vv), dtype=float)
    if raw_top.shape != (len(u), 3) or raw_bottom.shape != (len(u), 3):
        raise ValueError(f"Unexpected pyGeo slice shapes: {raw_top.shape}, {raw_bottom.shape}")

    end_0 = 0.5 * (raw_top[0] + raw_bottom[0])
    end_1 = 0.5 * (raw_top[-1] + raw_bottom[-1])
    if end_0[0] >= end_1[0]:
        te_xyz, le_xyz = end_0, end_1
        top_te_to_le, bottom_te_to_le = raw_top, raw_bottom
    else:
        te_xyz, le_xyz = end_1, end_0
        top_te_to_le, bottom_te_to_le = raw_top[::-1], raw_bottom[::-1]

    dv = 2.5e-4
    v_minus = max(0.0, v - dv)
    v_plus = min(1.0, v + dv)
    if v_plus == v_minus:
        raise ValueError("Could not form a local span derivative")
    span_delta = _quarter_chord_at_v(build, v_plus) - _quarter_chord_at_v(build, v_minus)
    span_axis = _unit(np.array([0.0, span_delta[1], span_delta[2]]), "local YZ span axis")

    raw_chord = te_xyz - le_xyz
    chord_in_plane = raw_chord - span_axis * float(np.dot(raw_chord, span_axis))
    chord_axis = _unit(chord_in_plane, "section chord")
    if chord_axis[0] < 0.0:
        chord_axis = -chord_axis
    chord_m = float(np.dot(raw_chord, chord_axis))
    if chord_m <= _EPS:
        raise ValueError(f"Degenerate extracted chord at v={v:.6f}")
    thickness_axis = _unit(np.cross(chord_axis, span_axis), "section thickness axis")
    if thickness_axis[2] < 0.0:
        thickness_axis = -thickness_axis

    all_points = np.vstack([top_te_to_le, bottom_te_to_le])
    normal_offsets = (all_points - le_xyz) @ span_axis
    plane_warp_rms = float(np.sqrt(np.mean(normal_offsets**2)) / chord_m)
    plane_warp_max = float(np.max(np.abs(normal_offsets)) / chord_m)

    def project(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        delta = points - le_xyz
        return (delta @ chord_axis) / chord_m, (delta @ thickness_axis) / chord_m

    x_top, z_top = project(top_te_to_le)
    x_bottom, z_bottom = project(bottom_te_to_le)
    if float(np.mean(z_top - z_bottom)) >= 0.0:
        upper_xyz, lower_xyz = top_te_to_le, bottom_te_to_le
        x_upper_raw, z_upper_raw = x_top, z_top
        x_lower_raw, z_lower_raw = x_bottom, z_bottom
    else:
        upper_xyz, lower_xyz = bottom_te_to_le, top_te_to_le
        x_upper_raw, z_upper_raw = x_bottom, z_bottom
        x_lower_raw, z_lower_raw = x_top, z_top

    x_upper, z_upper = _collapse_surface_samples(x_upper_raw, z_upper_raw)
    x_lower, z_lower = _collapse_surface_samples(x_lower_raw, z_lower_raw)
    if len(x_upper) < cst_order + 1 or len(x_lower) < cst_order + 1:
        raise ValueError("Too few unique projected x coordinates for CST fitting")
    te_upper = float(np.interp(1.0, x_upper, z_upper))
    te_lower = float(np.interp(1.0, x_lower, z_lower))
    dz_te = max(0.0, te_upper - te_lower)
    cst, cst_rms = CSTAirfoil.fit(
        x_upper,
        z_upper,
        x_lower,
        z_lower,
        order=int(cst_order),
        dz_te=dz_te,
        name=f"pygeo_v{v:.8f}_cst{cst_order}",
    )
    residuals = np.concatenate([cst.upper(x_upper) - z_upper, cst.lower(x_lower) - z_lower])
    cst_max = float(np.max(np.abs(residuals)))
    validation = cst.validate()

    x_check = cosine_spacing(1001)
    z_upper_check = np.interp(x_check, x_upper, z_upper)
    z_lower_check = np.interp(x_check, x_lower, z_lower)
    thickness = z_upper_check - z_lower_check
    camber = 0.5 * (z_upper_check + z_lower_check)
    direct_coordinates = np.vstack(
        [
            np.column_stack([x_upper[::-1], z_upper[::-1]]),
            np.column_stack([x_lower[1:], z_lower[1:]]),
        ]
    )

    return ExtractedSection(
        index=int(index),
        span_fraction=float(span_fraction),
        v_parameter=v,
        le_xyz_m=np.asarray(le_xyz),
        te_xyz_m=np.asarray(te_xyz),
        chord_m=chord_m,
        twist_deg=_signed_twist_deg(chord_axis, span_axis),
        local_span_axis=span_axis,
        chord_axis=chord_axis,
        thickness_axis=thickness_axis,
        upper_xyz_m=np.asarray(upper_xyz),
        lower_xyz_m=np.asarray(lower_xyz),
        x_upper=x_upper,
        z_upper=z_upper,
        x_lower=x_lower,
        z_lower=z_lower,
        direct_coordinates=direct_coordinates,
        cst=cst,
        cst_order=int(cst_order),
        cst_rms_chord=float(cst_rms),
        cst_max_chord=cst_max,
        plane_warp_rms_chord=plane_warp_rms,
        plane_warp_max_chord=plane_warp_max,
        thickness_ratio=float(np.max(thickness)),
        max_camber_ratio=float(np.max(np.abs(camber))),
        cst_valid=bool(validation.valid),
        cst_failures=tuple(validation.failures),
    )


def extract_sections(
    build: PyGeoBuild,
    span_fractions: Sequence[float],
    *,
    cst_order: int = 8,
    chordwise_points: int = 181,
) -> list[ExtractedSection]:
    """Extract a sorted set of equal-physical-span slices."""
    fractions = np.asarray(span_fractions, dtype=float)
    if len(fractions) < 2:
        raise ValueError("At least two extracted sections are required")
    if np.any(np.diff(fractions) <= 0.0):
        raise ValueError("span_fractions must be strictly increasing")
    parameters = span_parameters_for_fractions(build, fractions)
    return [
        extract_section(
            build,
            v_parameter=float(v),
            span_fraction=float(frac),
            index=i,
            cst_order=cst_order,
            chordwise_points=chordwise_points,
        )
        for i, (frac, v) in enumerate(zip(fractions, parameters, strict=False))
    ]


def realised_reference_metrics(
    sections: Sequence[ExtractedSection],
    *,
    symmetric: bool = True,
) -> dict[str, float]:
    """Compute reference values from the realised extracted loft."""
    if len(sections) < 2:
        raise ValueError("At least two sections are required")
    ordered = sorted(sections, key=lambda s: s.y_m)
    y = np.asarray([s.y_m for s in ordered])
    z = np.asarray([s.z_le_m for s in ordered])
    chord = np.asarray([s.chord_m for s in ordered])
    factor = 2.0 if symmetric else 1.0
    semi_area_xy = float(np.trapezoid(chord, y))
    yz_s = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(y), np.diff(z)))])
    semi_area_yz = float(np.trapezoid(chord, yz_s))
    full_span_y = factor * float(y[-1] - y[0])
    full_span_yz = factor * float(yz_s[-1] - yz_s[0])
    area_xy = factor * semi_area_xy
    area_yz = factor * semi_area_yz
    int_c2 = factor * float(np.trapezoid(chord**2, y))
    return {
        "s_ref_xy_m2": area_xy,
        "s_ref_yz_m2": area_yz,
        "b_ref_y_m": full_span_y,
        "b_ref_yz_m": full_span_yz,
        "c_ref_m": int_c2 / area_xy,
        "aspect_ratio_xy": full_span_y**2 / area_xy,
        "aspect_ratio_yz": full_span_yz**2 / area_yz,
    }


def build_aerosandbox_airplane(
    sections: Sequence[ExtractedSection],
    *,
    name: str,
    representation: str = "cst",
    symmetric: bool = True,
    control: dict[str, float | str | bool] | None = None,
) -> tuple[Any, Any]:
    """Create an AVL carrier from realised sections.

    AeroSandbox is used here as a serializer/runner, not as the master loft.
    """
    try:
        import aerosandbox as asb
    except ImportError as exc:
        raise RuntimeError("AeroSandbox is required to serialize AVL geometry") from exc

    mode = representation.strip().lower()
    if mode not in {"cst", "direct"}:
        raise ValueError("representation must be 'cst' or 'direct'")
    if len(sections) < 2:
        raise ValueError("At least two sections are required")

    xsecs = []
    for i, section in enumerate(sections):
        coordinates = (
            section.cst.coordinates(n_per_surface=181)
            if mode == "cst"
            else section.direct_coordinates
        )
        control_surfaces = []
        if control is not None and i != len(sections) - 1:
            start = float(control.get("start_frac", 0.0))
            end = float(control.get("end_frac", 1.0))
            if start <= section.span_fraction <= end:
                control_surfaces.append(
                    asb.ControlSurface(
                        name=str(control.get("name", "elevon")),
                        trailing_edge=True,
                        hinge_point=float(control.get("hinge_point", 0.75)),
                        deflection=1.0,
                        symmetric=bool(control.get("symmetric", True)),
                    )
                )
        xsecs.append(
            asb.WingXSec(
                xyz_le=section.le_xyz_m.tolist(),
                chord=section.chord_m,
                twist=section.twist_deg,
                airfoil=asb.Airfoil(
                    name=f"{name}_sec_{i:03d}_{mode}",
                    coordinates=coordinates,
                ),
                control_surfaces=control_surfaces,
            )
        )

    wing = asb.Wing(name=name, symmetric=bool(symmetric), xsecs=xsecs)
    airplane = asb.Airplane(
        name=name,
        xyz_ref=[0.0, 0.0, 0.0],
        wings=[wing],
        s_ref=float(wing.area()),
        c_ref=float(wing.mean_aerodynamic_chord()),
        b_ref=float(wing.span()),
    )
    return wing, airplane
