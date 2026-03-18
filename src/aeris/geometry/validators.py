from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from aeris.geometry.planform import PlanformResult
from aeris.geometry.sections import SectionGeometryResult


@dataclass(frozen=True)
class GeometryAuditResult:
    passed: bool
    errors: list[str]
    warnings: list[str]
    metrics: dict[str, Any]


def _is_strictly_increasing(values: np.ndarray, tol: float = 1e-12) -> bool:
    diffs = np.diff(values)
    return bool(np.all(diffs > tol))


def _finite_fraction(values: np.ndarray) -> float:
    if values.size == 0:
        return 1.0
    return float(np.isfinite(values).sum() / values.size)


def audit_geometry_result(
    *,
    planform: PlanformResult,
    section_geometry: SectionGeometryResult,
    min_chord_tol: float = 1e-10,
) -> GeometryAuditResult:
    errors: list[str] = []
    warnings: list[str] = []

    # -----------------------------
    # Planform arrays
    # -----------------------------
    x_le = np.asarray(planform.x_le, dtype=float)
    y_le = np.asarray(planform.y_le, dtype=float)
    x_te = np.asarray(planform.x_te, dtype=float)
    y_te = np.asarray(planform.y_te, dtype=float)
    chords = np.asarray(planform.chords, dtype=float)

    # -----------------------------
    # Section arrays derived from SectionRecord
    # -----------------------------
    xsec_x = np.asarray([s.x_le_m for s in section_geometry.sections], dtype=float)
    xsec_y = np.asarray([s.y_m for s in section_geometry.sections], dtype=float)
    xsec_z = np.asarray([s.z_le_m for s in section_geometry.sections], dtype=float)
    xsec_chord = np.asarray([s.chord_m for s in section_geometry.sections], dtype=float)
    twist = np.asarray(section_geometry.twist_array_deg, dtype=float)
    dihedral = np.asarray(section_geometry.dihedral_array_deg, dtype=float)

    named_arrays = {
        "planform.x_le": x_le,
        "planform.y_le": y_le,
        "planform.x_te": x_te,
        "planform.y_te": y_te,
        "planform.chords": chords,
        "sections.x_le_m": xsec_x,
        "sections.y_m": xsec_y,
        "sections.z_le_m": xsec_z,
        "sections.chord_m": xsec_chord,
        "sections.twist_array_deg": twist,
        "sections.dihedral_array_deg": dihedral,
    }

    finite_fractions: dict[str, float] = {}
    for name, arr in named_arrays.items():
        ff = _finite_fraction(arr)
        finite_fractions[name] = ff
        if ff < 1.0:
            errors.append(f"{name} contains non-finite values (finite_fraction={ff:.6f})")

    # -----------------------------
    # Shape consistency
    # -----------------------------
    if not (len(x_le) == len(y_le) == len(x_te) == len(y_te) == len(chords)):
        errors.append("Planform arrays have inconsistent lengths")

    if not (
        len(xsec_x)
        == len(xsec_y)
        == len(xsec_z)
        == len(xsec_chord)
        == len(twist)
        == len(dihedral)
    ):
        errors.append("Section arrays have inconsistent lengths")

    # -----------------------------
    # Spanwise monotonicity
    # -----------------------------
    if y_le.size > 1 and not _is_strictly_increasing(y_le):
        errors.append("planform.y_le is not strictly increasing")

    if y_te.size > 1 and not _is_strictly_increasing(y_te):
        errors.append("planform.y_te is not strictly increasing")

    if xsec_y.size > 1 and not _is_strictly_increasing(xsec_y):
        errors.append("sections.y_m is not strictly increasing")

    # -----------------------------
    # Geometry ordering
    # -----------------------------
    if chords.size > 0 and np.min(chords) <= min_chord_tol:
        errors.append(f"Non-positive or near-zero planform chord detected (min={np.min(chords):.6e})")

    if xsec_chord.size > 0 and np.min(xsec_chord) <= min_chord_tol:
        errors.append(
            f"Non-positive or near-zero section chord detected (min={np.min(xsec_chord):.6e})"
        )

    if x_le.size > 0 and x_te.size > 0:
        if np.any((x_te - x_le) <= min_chord_tol):
            errors.append("Trailing edge is not consistently behind leading edge")

    # -----------------------------
    # Scalar consistency
    # -----------------------------
    full_span = float(planform.full_span_m)
    semi_span = float(planform.semi_span_m)
    approx_area = float(planform.approx_area_m2)
    approx_ar = float(planform.approx_aspect_ratio)

    if full_span <= 0.0:
        errors.append("full_span_m <= 0")

    if semi_span <= 0.0:
        errors.append("semi_span_m <= 0")

    if approx_area <= 0.0:
        errors.append("approx_area_m2 <= 0")

    if approx_ar <= 0.0:
        errors.append("approx_aspect_ratio <= 0")

    if abs(full_span - 2.0 * semi_span) > 1e-9:
        errors.append("full_span_m is not equal to 2 * semi_span_m within tolerance")

    # -----------------------------
    # Section consistency
    # -----------------------------
    if len(section_geometry.sections) != planform.num_sections:
        warnings.append(
            f"section count mismatch: len(section_geometry.sections)={len(section_geometry.sections)} "
            f"vs planform.num_sections={planform.num_sections}"
        )

    # -----------------------------
    # Smoothness-ish warnings
    # -----------------------------
    if chords.size > 2:
        chord_diffs = np.diff(chords)
        if np.max(np.abs(chord_diffs)) > 0.5 * max(np.max(chords), 1e-12):
            warnings.append("Large adjacent chord jump detected")

    if twist.size > 1 and np.max(np.abs(np.diff(twist))) > 10.0:
        warnings.append("Large adjacent twist jump detected")

    if dihedral.size > 1 and np.max(np.abs(np.diff(dihedral))) > 10.0:
        warnings.append("Large adjacent dihedral jump detected")

    metrics = {
        "full_span_m": full_span,
        "semi_span_m": semi_span,
        "approx_area_m2": approx_area,
        "approx_aspect_ratio": approx_ar,
        "num_planform_points": int(len(y_le)),
        "num_sections": int(len(section_geometry.sections)),
        "min_planform_chord_m": None if chords.size == 0 else float(np.min(chords)),
        "max_planform_chord_m": None if chords.size == 0 else float(np.max(chords)),
        "min_section_chord_m": None if xsec_chord.size == 0 else float(np.min(xsec_chord)),
        "max_section_chord_m": None if xsec_chord.size == 0 else float(np.max(xsec_chord)),
        "twist_min_deg": None if twist.size == 0 else float(np.min(twist)),
        "twist_max_deg": None if twist.size == 0 else float(np.max(twist)),
        "dihedral_min_deg": None if dihedral.size == 0 else float(np.min(dihedral)),
        "dihedral_max_deg": None if dihedral.size == 0 else float(np.max(dihedral)),
        "finite_fractions": finite_fractions,
    }

    return GeometryAuditResult(
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        metrics=metrics,
    )