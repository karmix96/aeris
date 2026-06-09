"""Physical deflected CAD export for ``bwb_segmented_v1``.

This module is intentionally generator-specific. AVL can use control-surface
metadata and solver control variables. CAD/CFD cannot: they see only the
exported shape.

The production topology used by default here is now **split mechanical elevon**:

    right main fixed wing body
    right separate deflected elevon body
    left main fixed wing body
    left separate deflected elevon body

This avoids the fake connecting plate/wall that appears when trying to force a
single watertight half-wing body with an abrupt control deflection jump.

Sign convention:
    positive physical deflection = trailing edge down.

For BWB elevons:
    right_deflection = delta_e_sym_deg + delta_a_diff_deg
    left_deflection  = delta_e_sym_deg - delta_a_diff_deg
"""

from __future__ import annotations

import json
import math
import platform
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

import numpy as np
import yaml


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_formats(formats: str | Iterable[str]) -> list[str]:
    if isinstance(formats, str):
        raw = [x.strip().lower() for x in formats.split(",")]
    else:
        raw = [str(x).strip().lower() for x in formats]

    out: list[str] = []
    for item in raw:
        if item in {"vsp", "openvsp", "vspscript", ".vspscript"}:
            item = "vspscript"
        elif item in {"stp", ".stp", "step", ".step"}:
            item = "step"
        if item and item not in out:
            out.append(item)

    bad = [x for x in out if x not in {"vspscript", "step"}]
    if bad:
        raise ValueError(f"Unsupported CAD format(s): {bad}. Use vspscript, step, or both.")
    if not out:
        raise ValueError("At least one CAD export format is required.")
    return out


def _normalise_topology(value: str | None) -> str:
    v = (value or "split-elevon").strip().lower().replace("_", "-")
    aliases = {
        "split": "split-elevon",
        "split-elevon": "split-elevon",
        "split-mechanical": "split-elevon",
        "split-mechanical-elevon": "split-elevon",
        "mechanical": "split-elevon",
        "option-c": "split-elevon",
        "unified": "unified-abrupt",
        "unified-abrupt": "unified-abrupt",
        "abrupt": "unified-abrupt",
    }
    if v not in aliases:
        raise ValueError(
            f"Unsupported deflection topology {value!r}. Use 'split-elevon' or 'unified-abrupt'."
        )
    return aliases[v]


@dataclass(frozen=True)
class PhysicalDeflectionSpec:
    delta_e_sym_deg: float = 0.0
    delta_a_diff_deg: float = 0.0
    hinge_point: float = 0.75
    start_frac: float = 0.60
    end_frac: float = 0.95
    hinge_gap_fraction: float = 0.0
    boundary_epsilon_fraction: float = 1.0e-6
    deflection_topology: str = "split-elevon"
    down_positive: bool = True

    @property
    def right_deflection_deg(self) -> float:
        return float(self.delta_e_sym_deg + self.delta_a_diff_deg)

    @property
    def left_deflection_deg(self) -> float:
        return float(self.delta_e_sym_deg - self.delta_a_diff_deg)

    @property
    def topology(self) -> str:
        return _normalise_topology(self.deflection_topology)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["deflection_topology"] = self.topology
        d["right_deflection_deg"] = self.right_deflection_deg
        d["left_deflection_deg"] = self.left_deflection_deg
        if self.topology == "split-elevon":
            d["surface_model"] = "split_mechanical_elevon"
            d["body_model"] = "fixed_wing_plus_separate_elevon_per_side"
            d["boundary_model"] = "true_body_split_no_unified_transition_plate"
        else:
            d["surface_model"] = "abrupt_boundary_full_airfoil"
            d["body_model"] = "one_continuous_half_wing_per_side"
            d["boundary_model"] = "near_coincident_neutral_and_deflected_span_stations"
        d["sign_convention"] = {
            "positive_delta_e_sym_deg": "both elevons trailing-edge down",
            "positive_delta_a_diff_deg": "right elevon trailing-edge down, left elevon trailing-edge up",
            "positive_physical_deflection": "trailing-edge down",
        }
        return d


# ---------------------------------------------------------------------------
# 2-D airfoil utilities
# ---------------------------------------------------------------------------

def rotate_points_2d(points: np.ndarray, origin: np.ndarray, angle_deg: float) -> np.ndarray:
    theta = np.deg2rad(float(angle_deg))
    c = np.cos(theta)
    s = np.sin(theta)
    shifted = np.asarray(points, dtype=float) - np.asarray(origin, dtype=float)
    rotated = np.empty_like(shifted)
    rotated[:, 0] = c * shifted[:, 0] - s * shifted[:, 1]
    rotated[:, 1] = s * shifted[:, 0] + c * shifted[:, 1]
    return rotated + origin


def _airfoil_coords(airfoil: Any) -> np.ndarray:
    coords = np.asarray(getattr(airfoil, "coordinates"), dtype=float)
    if coords.ndim != 2 or coords.shape[1] != 2 or len(coords) < 4:
        raise ValueError(f"Airfoil {getattr(airfoil, 'name', '<unnamed>')} has invalid coordinates.")
    return coords


def deflect_full_airfoil_coordinates(
    airfoil: Any,
    hinge_point: float,
    deflection_deg: float,
    *,
    down_positive: bool = True,
) -> np.ndarray:
    """Rotate the aft part of a full closed airfoil loop about x/c hinge."""
    coords = _airfoil_coords(airfoil).copy()
    if not (0.0 < float(hinge_point) < 1.0):
        raise ValueError(f"hinge_point must be between 0 and 1, got {hinge_point}")
    geom_angle = -float(deflection_deg) if down_positive else float(deflection_deg)
    aft_mask = coords[:, 0] >= float(hinge_point)
    coords[aft_mask] = rotate_points_2d(
        coords[aft_mask],
        np.array([float(hinge_point), 0.0]),
        geom_angle,
    )
    return coords


# Backward-compatible helper name used by focused tests and older patches.
def deflect_control_airfoil_coordinates(
    coords: np.ndarray,
    hinge_point: float,
    deflection_deg: float,
    *,
    down_positive: bool = True,
) -> np.ndarray:
    class _AF:
        name = "coords"
        coordinates = np.asarray(coords, dtype=float)

    return deflect_full_airfoil_coordinates(
        _AF(),
        hinge_point=hinge_point,
        deflection_deg=deflection_deg,
        down_positive=down_positive,
    )


def interpolate_curve_y_at_x(coords: np.ndarray, x_query: float) -> tuple[float, float]:
    coords = np.asarray(coords, dtype=float)
    le_idx = int(np.argmin(coords[:, 0]))
    upper = coords[: le_idx + 1]
    lower = coords[le_idx:]
    upper_sorted = upper[np.argsort(upper[:, 0])]
    lower_sorted = lower[np.argsort(lower[:, 0])]
    y_upper = np.interp(x_query, upper_sorted[:, 0], upper_sorted[:, 1])
    y_lower = np.interp(x_query, lower_sorted[:, 0], lower_sorted[:, 1])
    return float(y_upper), float(y_lower)


def split_airfoil_at_hinge(
    airfoil: Any,
    hinge_point: float,
    gap_fraction: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Split a closed airfoil loop into fixed-front and aft-control loops.

    Returns:
        fixed_coords: closed-like section from LE to hinge cut.
        ctrl_coords:  closed-like section from hinge cut to TE.
    """
    coords = _airfoil_coords(airfoil)
    if not (0.0 < float(hinge_point) < 1.0):
        raise ValueError(f"hinge_point must be between 0 and 1, got {hinge_point}")
    if float(gap_fraction) < 0.0:
        raise ValueError(f"gap_fraction must be >= 0, got {gap_fraction}")

    x_fixed_cut = max(0.001, min(0.999, float(hinge_point) - 0.5 * float(gap_fraction)))
    x_ctrl_cut = max(0.001, min(0.999, float(hinge_point) + 0.5 * float(gap_fraction)))
    if x_fixed_cut >= x_ctrl_cut:
        raise ValueError(f"Bad hinge split: {x_fixed_cut=} {x_ctrl_cut=}")

    le_idx = int(np.argmin(coords[:, 0]))
    upper = coords[: le_idx + 1]
    lower = coords[le_idx:]
    upper_sorted = upper[np.argsort(upper[:, 0])]
    lower_sorted = lower[np.argsort(lower[:, 0])]

    y_fu, y_fl = interpolate_curve_y_at_x(coords, x_fixed_cut)
    upper_fixed = upper_sorted[upper_sorted[:, 0] <= x_fixed_cut]
    lower_fixed = lower_sorted[lower_sorted[:, 0] <= x_fixed_cut]
    upper_fixed = np.vstack([upper_fixed, [x_fixed_cut, y_fu]])
    lower_fixed = np.vstack([lower_fixed, [x_fixed_cut, y_fl]])
    upper_fixed = upper_fixed[np.argsort(upper_fixed[:, 0])][::-1]
    lower_fixed = lower_fixed[np.argsort(lower_fixed[:, 0])][1:]
    fixed_coords = np.vstack([upper_fixed, lower_fixed])

    y_cu, y_cl = interpolate_curve_y_at_x(coords, x_ctrl_cut)
    upper_ctrl = upper_sorted[upper_sorted[:, 0] >= x_ctrl_cut]
    lower_ctrl = lower_sorted[lower_sorted[:, 0] >= x_ctrl_cut]
    upper_ctrl = np.vstack([[x_ctrl_cut, y_cu], upper_ctrl])
    lower_ctrl = np.vstack([[x_ctrl_cut, y_cl], lower_ctrl])
    upper_ctrl = upper_ctrl[np.argsort(upper_ctrl[:, 0])]
    lower_ctrl = lower_ctrl[np.argsort(lower_ctrl[:, 0])]
    ctrl_coords = np.vstack([upper_ctrl, lower_ctrl[::-1]])
    return fixed_coords, ctrl_coords


def make_airfoil_from_coords(name: str, coords: np.ndarray) -> Any:
    import aerosandbox as asb

    return asb.Airfoil(name=name, coordinates=np.asarray(coords, dtype=float))


def _mirror_coords_local_y(coords: np.ndarray) -> np.ndarray:
    out = np.asarray(coords, dtype=float).copy()
    out[:, 1] *= -1.0
    return out


def _make_deflected_airfoil(base_airfoil: Any, *, spec: PhysicalDeflectionSpec, deflection_deg: float, name: str) -> Any:
    return make_airfoil_from_coords(
        name=name,
        coords=deflect_full_airfoil_coordinates(
            base_airfoil,
            hinge_point=spec.hinge_point,
            deflection_deg=deflection_deg,
            down_positive=spec.down_positive,
        ),
    )


# ---------------------------------------------------------------------------
# Spanwise station construction
# ---------------------------------------------------------------------------

def _span_fraction(y_abs: float, max_y: float) -> float:
    if max_y <= 0.0:
        return 0.0
    return abs(float(y_abs)) / float(max_y)


def _interp_section_at_y(sections: list[Any], y_abs: float) -> Any:
    """Linearly interpolate AERIS section geometry at a spanwise station."""
    y = np.asarray([abs(float(s.y_m)) for s in sections], dtype=float)
    order = np.argsort(y)
    y = y[order]
    ordered = [sections[int(i)] for i in order]

    def vals(attr: str) -> np.ndarray:
        return np.asarray([float(getattr(s, attr)) for s in ordered], dtype=float)

    yq = float(np.clip(y_abs, y[0], y[-1]))
    airfoil_name = str(getattr(ordered[0], "airfoil_name", "naca4412") or "naca4412")
    return SimpleNamespace(
        index=-1,
        x_le_m=float(np.interp(yq, y, vals("x_le_m"))),
        y_m=float(yq),
        z_le_m=float(np.interp(yq, y, vals("z_le_m"))),
        chord_m=float(np.interp(yq, y, vals("chord_m"))),
        twist_deg=float(np.interp(yq, y, vals("twist_deg"))),
        dihedral_deg=float(np.interp(yq, y, vals("dihedral_deg"))),
        airfoil_name=airfoil_name,
        synthetic=True,
    )


def _unique_sorted_stations(values: Iterable[float], *, tol: float) -> list[float]:
    out: list[float] = []
    for v in sorted(float(x) for x in values if math.isfinite(float(x))):
        if not out or abs(v - out[-1]) > tol:
            out.append(v)
    return out


def build_piecewise_abrupt_sections(sections: Iterable[Any], spec: PhysicalDeflectionSpec) -> tuple[list[Any], dict[str, Any]]:
    """Add near-coincident boundary sections around control start/end.

    This helper is retained for the older unified-abrupt topology and for tests.
    The default production topology is now split-elevon.
    """
    base = list(sections)
    if len(base) < 3:
        raise ValueError("At least 3 sections are required for abrupt deflected export.")

    max_y = max(abs(float(s.y_m)) for s in base)
    if max_y <= 0.0:
        raise ValueError("Cannot compute control span fractions from zero-span geometry.")

    if not (0.0 <= spec.start_frac < spec.end_frac <= 1.0):
        raise ValueError(
            f"Control span must satisfy 0 <= start < end <= 1, got "
            f"{spec.start_frac=} {spec.end_frac=}."
        )

    y_start = float(spec.start_frac) * max_y
    y_end = float(spec.end_frac) * max_y
    eps = max(max_y * float(spec.boundary_epsilon_fraction), 1.0e-6)
    eps = min(eps, max(1.0e-6, 0.25 * max(y_end - y_start, 1.0e-6)))

    original_y = [abs(float(s.y_m)) for s in base]
    synthetic_y = [
        max(0.0, y_start - eps),
        min(max_y, y_start + eps),
        max(0.0, y_end - eps),
        min(max_y, y_end + eps),
    ]
    tol = max(1.0e-9, eps * 1.0e-3)
    stations = _unique_sorted_stations([*original_y, *synthetic_y], tol=tol)

    piecewise: list[Any] = []
    original_tol = max(1.0e-8, eps * 1.0e-2)
    for y_abs in stations:
        match = None
        for s in base:
            if abs(abs(float(s.y_m)) - y_abs) <= original_tol:
                match = s
                break
        piecewise.append(match if match is not None else _interp_section_at_y(base, y_abs))

    report = {
        "max_y_m": max_y,
        "start_frac": float(spec.start_frac),
        "end_frac": float(spec.end_frac),
        "y_start_m": y_start,
        "y_end_m": y_end,
        "boundary_epsilon_m": eps,
        "boundary_epsilon_fraction": float(spec.boundary_epsilon_fraction),
        "n_original_sections": len(base),
        "n_piecewise_sections": len(piecewise),
        "inserted_boundary_stations_m": synthetic_y,
    }
    return piecewise, report


def build_split_control_span_sections(sections: Iterable[Any], spec: PhysicalDeflectionSpec) -> tuple[list[Any], list[Any], dict[str, Any]]:
    """Return main-body stations and elevon-only stations for split topology.

    Important CAD/topology rule
    ---------------------------
    A split mechanical elevon has three spanwise zones:

        fixed inboard  |  separate elevon  |  fixed outboard

    If the main body jumps directly from a hinge-cut airfoil at ``y_end`` to the
    next full airfoil section, CAD lofting creates a large diagonal web/plate.
    To avoid that, we insert near-coincident stations around the control start
    and end:

        y_start - eps : full fixed airfoil
        y_start + eps : hinge-cut main body + elevon body begins
        y_end   - eps : hinge-cut main body + elevon body ends
        y_end   + eps : full fixed airfoil

    The result is still a separate mechanical elevon, but the end-cap/web is
    compressed into a tiny near-vertical boundary face instead of a long
    diagonal plate between two ordinary spanwise slices.
    """
    base = list(sections)
    if len(base) < 3:
        raise ValueError("At least 3 sections are required for split-elevon export.")
    max_y = max(abs(float(s.y_m)) for s in base)
    if max_y <= 0:
        raise ValueError("Cannot compute control span fractions from zero-span geometry.")
    if not (0.0 <= spec.start_frac < spec.end_frac <= 1.0):
        raise ValueError(f"Invalid control span: {spec.start_frac=} {spec.end_frac=}")

    y_start = float(spec.start_frac) * max_y
    y_end = float(spec.end_frac) * max_y
    span_control = max(y_end - y_start, 1.0e-9)

    # Use boundary_epsilon_fraction for the split topology too.  This controls
    # how thin the spanwise side/end faces are at elevon start/end.
    eps = max(max_y * float(spec.boundary_epsilon_fraction), 1.0e-6)
    eps = min(eps, 0.10 * span_control)

    # If the elevon is extremely close to the tip, keep y_end + eps inside the
    # physical semispan.  Otherwise the outboard fixed region disappears.
    eps = min(eps, max(1.0e-9, 0.45 * max(max_y - y_end, 1.0e-9)))
    eps = min(eps, max(1.0e-9, 0.45 * max(y_start, 1.0e-9)))

    y_start_outer = max(0.0, y_start - eps)
    y_start_inner = min(max_y, y_start + eps)
    y_end_inner = max(0.0, y_end - eps)
    y_end_outer = min(max_y, y_end + eps)

    original_y = [abs(float(s.y_m)) for s in base]
    tol = max(1.0e-10, eps * 1.0e-3, max_y * 1.0e-10)

    # Main body exists across the whole semispan:
    # - full profile outside the control span,
    # - hinge-cut front profile inside the control span.
    main_candidates = [
        *original_y,
        y_start_outer,
        y_start_inner,
        y_end_inner,
        y_end_outer,
    ]

    # Elevon body exists only inside the control span, with its own start/end
    # stations slightly inside the fixed-zone boundary stations.
    elevon_candidates = [
        y_start_inner,
        *[y for y in original_y if (y_start_inner < y < y_end_inner)],
        y_end_inner,
    ]

    main_stations = _unique_sorted_stations(main_candidates, tol=tol)
    elevon_stations = _unique_sorted_stations(elevon_candidates, tol=tol)

    def build(stations: list[float]) -> list[Any]:
        out: list[Any] = []
        original_match_tol = max(1.0e-8, eps * 1.0e-2, max_y * 1.0e-8)
        for y_abs in stations:
            match = None
            for s in base:
                if abs(abs(float(s.y_m)) - y_abs) <= original_match_tol:
                    match = s
                    break
            out.append(match if match is not None else _interp_section_at_y(base, y_abs))
        return out

    main_sections = build(main_stations)
    elevon_sections = build(elevon_stations)

    report = {
        "max_y_m": max_y,
        "start_frac": float(spec.start_frac),
        "end_frac": float(spec.end_frac),
        "y_start_m": y_start,
        "y_end_m": y_end,
        "boundary_epsilon_m": eps,
        "boundary_epsilon_fraction": float(spec.boundary_epsilon_fraction),
        "y_start_outer_full_fixed_m": y_start_outer,
        "y_start_inner_split_m": y_start_inner,
        "y_end_inner_split_m": y_end_inner,
        "y_end_outer_full_fixed_m": y_end_outer,
        "n_original_sections": len(base),
        "n_main_sections": len(main_sections),
        "n_elevon_sections": len(elevon_sections),
        "main_stations_m": main_stations,
        "elevon_stations_m": elevon_stations,
        "topology_note": "fixed inboard | separate elevon | fixed outboard, with near-coincident end-cap stations",
    }
    return main_sections, elevon_sections, report


def _is_deflected_station(y_abs: float, max_y: float, spec: PhysicalDeflectionSpec) -> bool:
    frac = _span_fraction(y_abs, max_y)
    return float(spec.start_frac) <= frac <= float(spec.end_frac)


def _make_xsec(*, xyz_le: list[float], chord: float, twist: float, airfoil: Any) -> Any:
    import aerosandbox as asb

    return asb.WingXSec(
        xyz_le=[float(xyz_le[0]), float(xyz_le[1]), float(xyz_le[2])],
        chord=float(chord),
        twist=float(twist),
        airfoil=airfoil,
    )


def _section_xyz_chord_twist(section: Any, side_sign: float) -> tuple[list[float], float, float, float]:
    x_le = float(section.x_le_m)
    y_abs = abs(float(section.y_m))
    y = float(side_sign * y_abs)
    z = float(section.z_le_m)
    chord = float(section.chord_m)
    twist = float(section.twist_deg)
    if chord <= 0.0 or not math.isfinite(chord):
        raise ValueError(f"Invalid chord at section {getattr(section, 'index', '?')}: {chord}")
    return [x_le, y, z], chord, twist, y_abs


def _airfoil_for_coords(name: str, coords: np.ndarray, *, side_sign: float) -> Any:
    if side_sign < 0.0:
        coords = _mirror_coords_local_y(coords)
    return make_airfoil_from_coords(name=name, coords=coords)


def build_split_mechanical_elevon_airplane(
    *,
    sections: Iterable[Any],
    airfoil_name: str,
    spec: PhysicalDeflectionSpec,
    name: str = "AERIS_BWB_Split_Mechanical_Elevon",
) -> Any:
    """Build fixed-wing plus separate elevon bodies for each side.

    This is the correct topology when the goal is to remove the fake connecting
    wall produced by a single unified abrupt loft.
    """
    import aerosandbox as asb

    main_sections, elevon_sections, split_report = build_split_control_span_sections(sections, spec)
    max_y = float(split_report["max_y_m"])

    base_airfoil_cache: dict[str, Any] = {}

    def base_airfoil(section: Any) -> Any:
        aname = str(getattr(section, "airfoil_name", "") or airfoil_name or "naca4412")
        if aname not in base_airfoil_cache:
            base_airfoil_cache[aname] = asb.Airfoil(aname)
        return base_airfoil_cache[aname]

    wings: list[Any] = []
    side_reports: list[dict[str, Any]] = []

    for side_name, side_sign, side_defl in (
        ("right", +1.0, spec.right_deflection_deg),
        ("left", -1.0, spec.left_deflection_deg),
    ):
        main_xsecs: list[Any] = []
        elevon_xsecs: list[Any] = []
        main_cut_indices: list[int] = []

        for i, s in enumerate(main_sections):
            xyz_le, chord, twist, y_abs = _section_xyz_chord_twist(s, side_sign)
            af = base_airfoil(s)
            in_ctrl = _is_deflected_station(y_abs, max_y, spec)
            if in_ctrl:
                fixed_coords, _ctrl_coords = split_airfoil_at_hinge(
                    af,
                    hinge_point=spec.hinge_point,
                    gap_fraction=spec.hinge_gap_fraction,
                )
                coords = fixed_coords
                main_cut_indices.append(i)
                af_name = f"{af.name}_{side_name}_main_cut_{i:03d}"
            else:
                coords = _airfoil_coords(af)
                af_name = f"{af.name}_{side_name}_main_full_{i:03d}"
            main_xsecs.append(
                _make_xsec(
                    xyz_le=xyz_le,
                    chord=chord,
                    twist=twist,
                    airfoil=_airfoil_for_coords(af_name, coords, side_sign=side_sign),
                )
            )

        for i, s in enumerate(elevon_sections):
            xyz_le, chord, twist, _y_abs = _section_xyz_chord_twist(s, side_sign)
            af = base_airfoil(s)
            _fixed_coords, ctrl_coords = split_airfoil_at_hinge(
                af,
                hinge_point=spec.hinge_point,
                gap_fraction=spec.hinge_gap_fraction,
            )
            if abs(float(side_defl)) > 1.0e-12:
                ctrl_coords = deflect_control_airfoil_coordinates(
                    ctrl_coords,
                    hinge_point=spec.hinge_point,
                    deflection_deg=side_defl,
                    down_positive=spec.down_positive,
                )
            elevon_xsecs.append(
                _make_xsec(
                    xyz_le=xyz_le,
                    chord=chord,
                    twist=twist,
                    airfoil=_airfoil_for_coords(
                        f"{af.name}_{side_name}_elevon_defl_{i:03d}_{side_defl:+.1f}",
                        ctrl_coords,
                        side_sign=side_sign,
                    ),
                )
            )

        wings.append(asb.Wing(name=f"BWB_{side_name}_main_fixed", symmetric=False, xsecs=main_xsecs))
        wings.append(asb.Wing(name=f"BWB_{side_name}_elevon_deflected", symmetric=False, xsecs=elevon_xsecs))
        side_reports.append(
            {
                "side": side_name,
                "deflection_deg": float(side_defl),
                "main_body": {"name": f"BWB_{side_name}_main_fixed", "n_xsecs": len(main_xsecs), "cut_section_indices": main_cut_indices},
                "elevon_body": {"name": f"BWB_{side_name}_elevon_deflected", "n_xsecs": len(elevon_xsecs)},
            }
        )

    airplane = asb.Airplane(name=name, xyz_ref=[0.0, 0.0, 0.0], wings=wings)
    setattr(airplane, "_aeris_physical_deflection_surface_model", "split_mechanical_elevon")
    setattr(airplane, "_aeris_physical_deflection_body_model", "fixed_wing_plus_separate_elevon_per_side")
    setattr(airplane, "_aeris_physical_deflection_boundary_report", split_report)
    setattr(airplane, "_aeris_physical_deflection_side_reports", side_reports)
    return airplane


def build_unified_abrupt_airplane(
    *,
    sections: Iterable[Any],
    airfoil_name: str,
    spec: PhysicalDeflectionSpec,
    name: str = "AERIS_BWB_Unified_Ab abrupt_Physical_Deflected",
) -> Any:
    """Older one-body-per-half-wing topology retained for comparison/debugging."""
    import aerosandbox as asb

    piecewise_sections, boundary_report = build_piecewise_abrupt_sections(sections, spec)
    max_y = float(boundary_report["max_y_m"])
    base_airfoil_cache: dict[str, Any] = {}

    def base_airfoil(section: Any) -> Any:
        aname = str(getattr(section, "airfoil_name", "") or airfoil_name or "naca4412")
        if aname not in base_airfoil_cache:
            base_airfoil_cache[aname] = asb.Airfoil(aname)
        return base_airfoil_cache[aname]

    wings: list[Any] = []
    side_reports: list[dict[str, Any]] = []
    for side_name, side_sign, side_defl in (
        ("right", +1.0, spec.right_deflection_deg),
        ("left", -1.0, spec.left_deflection_deg),
    ):
        xsecs: list[Any] = []
        deflected_indices: list[int] = []
        neutral_indices: list[int] = []
        for i, s in enumerate(piecewise_sections):
            xyz_le, chord, twist, y_abs = _section_xyz_chord_twist(s, side_sign)
            af = base_airfoil(s)
            in_ctrl = _is_deflected_station(y_abs, max_y, spec)
            if in_ctrl and abs(float(side_defl)) > 1.0e-12:
                af_coords = deflect_full_airfoil_coordinates(
                    af,
                    hinge_point=spec.hinge_point,
                    deflection_deg=side_defl,
                    down_positive=spec.down_positive,
                )
                deflected_indices.append(i)
            else:
                af_coords = _airfoil_coords(af)
                neutral_indices.append(i)
            xsecs.append(
                _make_xsec(
                    xyz_le=xyz_le,
                    chord=chord,
                    twist=twist,
                    airfoil=_airfoil_for_coords(
                        f"{af.name}_{side_name}_unified_{i:03d}",
                        af_coords,
                        side_sign=side_sign,
                    ),
                )
            )
        wings.append(asb.Wing(name=f"BWB_{side_name}_unified_abrupt_deflected", symmetric=False, xsecs=xsecs))
        side_reports.append(
            {
                "side": side_name,
                "deflection_deg": float(side_defl),
                "n_xsecs": len(xsecs),
                "deflected_section_indices": deflected_indices,
                "neutral_section_indices": neutral_indices,
            }
        )

    airplane = asb.Airplane(name=name, xyz_ref=[0.0, 0.0, 0.0], wings=wings)
    setattr(airplane, "_aeris_physical_deflection_surface_model", "abrupt_boundary_full_airfoil")
    setattr(airplane, "_aeris_physical_deflection_body_model", "one_continuous_half_wing_per_side")
    setattr(airplane, "_aeris_physical_deflection_boundary_report", boundary_report)
    setattr(airplane, "_aeris_physical_deflection_side_reports", side_reports)
    return airplane


def build_physical_deflected_airplane(
    *,
    sections: Iterable[Any],
    airfoil_name: str,
    spec: PhysicalDeflectionSpec,
    name: str = "AERIS_BWB_Physical_Deflected",
) -> Any:
    if spec.topology == "split-elevon":
        return build_split_mechanical_elevon_airplane(
            sections=sections,
            airfoil_name=airfoil_name,
            spec=spec,
            name=name,
        )
    return build_unified_abrupt_airplane(
        sections=sections,
        airfoil_name=airfoil_name,
        spec=spec,
        name=name,
    )


# ---------------------------------------------------------------------------
# STEP export fallback for arbitrary/full section loops
# ---------------------------------------------------------------------------

def remove_duplicate_last_point(coords: np.ndarray, tol: float = 1e-12) -> np.ndarray:
    coords = np.asarray(coords, dtype=float)
    if len(coords) >= 2 and np.linalg.norm(coords[0] - coords[-1]) < tol:
        return coords[:-1]
    return coords


def make_section_wire_arbitrary(xsec: Any, x_dir: np.ndarray, y_dir: np.ndarray, coords_2d: np.ndarray) -> Any:
    import cadquery as cq

    coords_2d = remove_duplicate_last_point(np.asarray(coords_2d, dtype=float))
    if len(coords_2d) < 3:
        raise ValueError(f"Need at least 3 points for a section wire, got {len(coords_2d)}")

    xy_points = [(float(pt[0] * xsec.chord), float(pt[1] * xsec.chord)) for pt in coords_2d]
    return (
        cq.Workplane(
            inPlane=cq.Plane(
                origin=tuple(float(v) for v in xsec.xyz_le),
                xDir=tuple(float(v) for v in x_dir),
                normal=tuple(float(v) for v in -y_dir),
            )
        )
        .polyline(xy_points)
        .close()
    )


def generate_cadquery_geometry_arbitrary_profiles(airplane: Any) -> Any:
    solids = []
    for wing in airplane.wings:
        xsec_wires = []
        for i, xsec in enumerate(wing.xsecs):
            csys = wing._compute_frame_of_WingXSec(i)
            x_dir = np.asarray(csys[0], dtype=float)
            y_dir = np.asarray(csys[1], dtype=float)
            coords_2d = np.asarray(xsec.airfoil.coordinates, dtype=float)
            xsec_wires.append(make_section_wire_arbitrary(xsec, x_dir, y_dir, coords_2d))

        if len(xsec_wires) < 2:
            raise ValueError(f"Wing {wing.name!r} has fewer than 2 sections; cannot loft.")

        wire_collection = xsec_wires[0]
        for w in xsec_wires[1:]:
            wire_collection.ctx.pendingWires.extend(w.ctx.pendingWires)
        loft = wire_collection.loft(ruled=True, clean=False)
        solids.append(loft)

    if not solids:
        raise ValueError("No wing solids were generated for STEP export.")

    solid = solids[0]
    for s in solids[1:]:
        solid = solid.add(s)
    return solid.clean()


def export_step_arbitrary_profiles(airplane: Any, filename: Path) -> None:
    from cadquery import exporters

    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)
    solid = generate_cadquery_geometry_arbitrary_profiles(airplane)
    solid.objects = [obj.scale(1000) for obj in solid.objects]
    exporters.export(solid, fname=str(filename))


def export_step_physical_deflected_airplane(airplane: Any, filename: Path) -> str:
    """Export STEP. Prefer AERIS arbitrary-profile exporter for split topology."""
    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)
    export_step_arbitrary_profiles(airplane, filename)
    return "aeris_arbitrary_profile_split_mechanical_exporter"


# ---------------------------------------------------------------------------
# AERIS orchestration
# ---------------------------------------------------------------------------

def _extract_control_defaults(config: Any) -> dict[str, float]:
    defaults = {"hinge_point": 0.75, "start_frac": 0.60, "end_frac": 0.95}
    control_cfg = getattr(config, "control_surfaces", None)
    surfaces = tuple(getattr(control_cfg, "surfaces", ()) or ())
    if surfaces:
        chosen = None
        for s in surfaces:
            if str(getattr(s, "name", "")).lower() in {"elevon", "elevon_sym", "elevator"}:
                chosen = s
                break
        chosen = chosen or surfaces[0]
        defaults["hinge_point"] = float(getattr(chosen, "hinge_point", defaults["hinge_point"]))
        spanwise = getattr(chosen, "spanwise", None)
        defaults["start_frac"] = float(getattr(spanwise, "start_frac", defaults["start_frac"]))
        defaults["end_frac"] = float(getattr(spanwise, "end_frac", defaults["end_frac"]))
    return defaults


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def export_bwb_physical_deflected_cad(
    *,
    config_path: str | Path,
    output_dir: str | Path,
    formats: str | Iterable[str] = "vspscript,step",
    delta_e_sym_deg: float = 0.0,
    delta_a_diff_deg: float = 0.0,
    hinge_gap_fraction: float = 0.0,
    boundary_epsilon_fraction: float = 1.0e-6,
    deflection_topology: str = "split-elevon",
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate BWB geometry and export physically deflected CAD artifacts."""
    from aeris.geometry.config_resolver import resolve_generator_and_config
    from aeris.geometry.registry import get_geometry_generator

    config_path = Path(config_path).expanduser().resolve()
    run_root = Path(output_dir).expanduser().resolve()
    cad_dir = run_root / "cad_exports"
    source_dir = cad_dir / "source_geometry"
    cad_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)

    stdout_path = cad_dir / "stdout.txt"
    stderr_path = cad_dir / "stderr.txt"
    _write_text(stdout_path, "")
    _write_text(stderr_path, "")

    requested = _normalise_formats(formats)
    topology = _normalise_topology(deflection_topology)
    manifest: dict[str, Any] = {
        "status": "running",
        "phase": "geometry_export_physical_deflected_cad",
        "created_at_utc": _utc_now(),
        "completed_at_utc": None,
        "config_path": str(config_path),
        "run_root": str(run_root),
        "cad_dir": str(cad_dir),
        "formats_requested": requested,
        "formats_produced": [],
        "platform": platform.system().lower(),
        "python_version": sys.version.split()[0],
        "generator": {},
        "deflection_topology": topology,
        "surface_model": "split_mechanical_elevon" if topology == "split-elevon" else "abrupt_boundary_full_airfoil",
        "body_model": "fixed_wing_plus_separate_elevon_per_side" if topology == "split-elevon" else "one_continuous_half_wing_per_side",
        "physical_controls": {},
        "boundary_report": {},
        "side_deflection_reports": [],
        "step_export": {},
        "artifacts": {
            "vspscript": None,
            "step": None,
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "source_dir": str(source_dir),
        },
        "warnings": [],
        "error": None,
    }
    manifest_path = cad_dir / "physical_deflected_geometry_export_manifest.json"

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        generator_id, typed_config = resolve_generator_and_config(raw)
        if generator_id != "bwb_segmented_v1":
            raise ValueError(
                "Physical deflected CAD export currently supports only "
                f"bwb_segmented_v1, got {generator_id!r}."
            )

        generator = get_geometry_generator(generator_id)
        seed_final = seed if seed is not None else int(getattr(typed_config.generator, "seed", 100))
        sample = generator.sample_one(typed_config, seed=seed_final)
        case = generator.run_full_case(
            sample=sample,
            config=typed_config,
            output_dir=source_dir,
            save_plot=False,
            build_aerosandbox=True,
        )

        defaults = _extract_control_defaults(typed_config)
        spec = PhysicalDeflectionSpec(
            delta_e_sym_deg=float(delta_e_sym_deg),
            delta_a_diff_deg=float(delta_a_diff_deg),
            hinge_point=float(defaults["hinge_point"]),
            start_frac=float(defaults["start_frac"]),
            end_frac=float(defaults["end_frac"]),
            hinge_gap_fraction=float(hinge_gap_fraction),
            boundary_epsilon_fraction=float(boundary_epsilon_fraction),
            deflection_topology=topology,
            down_positive=True,
        )

        airplane = build_physical_deflected_airplane(
            sections=case.section_geometry.sections,
            airfoil_name=str(typed_config.section_bounds.airfoil_name),
            spec=spec,
            name=f"{typed_config.name}_phys_deflected_{topology}_de{spec.delta_e_sym_deg:+.1f}_da{spec.delta_a_diff_deg:+.1f}",
        )

        sample_dict = sample.to_dict() if hasattr(sample, "to_dict") else dict(sample.__dict__)
        manifest["generator"] = {
            "id": generator_id,
            "seed": seed_final,
            "design_sample": sample_dict,
            "n_original_sections": len(case.section_geometry.sections),
        }
        manifest["physical_controls"] = spec.to_dict()
        manifest["surface_model"] = getattr(airplane, "_aeris_physical_deflection_surface_model", manifest["surface_model"])
        manifest["body_model"] = getattr(airplane, "_aeris_physical_deflection_body_model", manifest["body_model"])
        manifest["boundary_report"] = getattr(airplane, "_aeris_physical_deflection_boundary_report", {})
        manifest["side_deflection_reports"] = getattr(airplane, "_aeris_physical_deflection_side_reports", [])
        manifest["airplane"] = {
            "name": airplane.name,
            "wing_count": len(airplane.wings),
            "wings": [
                {"name": w.name, "symmetric": bool(w.symmetric), "n_xsecs": len(w.xsecs)}
                for w in airplane.wings
            ],
        }

        produced: list[str] = []
        if "vspscript" in requested:
            vsp_path = cad_dir / "physical_deflected_geometry.vspscript"
            try:
                airplane.export_OpenVSP_vspscript(filename=vsp_path)
            except TypeError:
                airplane.export_OpenVSP_vspscript(vsp_path)
            manifest["artifacts"]["vspscript"] = str(vsp_path)
            produced.append("vspscript")
            _write_text(stdout_path, stdout_path.read_text(encoding="utf-8") + f"Exported VSP script: {vsp_path}\n")

        if "step" in requested:
            step_path = cad_dir / "physical_deflected_geometry.step"
            try:
                backend = export_step_physical_deflected_airplane(airplane, step_path)
                manifest["artifacts"]["step"] = str(step_path)
                manifest["step_export"] = {"backend": backend, "status": "success"}
                produced.append("step")
                _write_text(stdout_path, stdout_path.read_text(encoding="utf-8") + f"Exported STEP: {step_path} via {backend}\n")
            except Exception as step_exc:
                manifest["step_export"] = {
                    "status": "failed",
                    "error": f"{type(step_exc).__name__}: {step_exc}",
                }
                manifest["warnings"].append("STEP export failed; VSP script may still be usable.")
                _write_text(stderr_path, stderr_path.read_text(encoding="utf-8") + f"STEP export failed: {type(step_exc).__name__}: {step_exc}\n")

        control_report_path = cad_dir / "physical_control_deflection.json"
        control_report_path.write_text(json.dumps(spec.to_dict(), indent=2), encoding="utf-8")
        manifest["artifacts"]["physical_control_deflection"] = str(control_report_path)

        manifest["formats_produced"] = produced
        if set(produced) == set(requested):
            manifest["status"] = "success"
        elif produced:
            manifest["status"] = "partial_success"
        else:
            manifest["status"] = "failed"
            manifest["error"] = "No requested CAD artifacts were produced."
        manifest["completed_at_utc"] = _utc_now()
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        manifest["completed_at_utc"] = _utc_now()
        _write_text(stderr_path, stderr_path.read_text(encoding="utf-8") + f"{type(exc).__name__}: {exc}\n")
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        raise
