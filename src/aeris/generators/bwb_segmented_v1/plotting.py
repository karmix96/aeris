"""
Debug plotting utilities for bwb_segmented_v1 geometry cases.

Produces human-readable visual summaries of generated planform and section
distributions for inspection and troubleshooting.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from aeris.generators.bwb_segmented_v1.params import BWBGeneratorConfig
from aeris.generators.bwb_segmented_v1.planform import PlanformResult
from aeris.generators.bwb_segmented_v1.sections import SectionGeometryResult


def save_planform_plot(
    planform: PlanformResult,
    section_geometry: SectionGeometryResult,
    config: BWBGeneratorConfig,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Extract section-wise arrays for quick plotting
    y_sections = np.array([section.y_m for section in section_geometry.sections], dtype=float)
    chord_sections = np.array([section.chord_m for section in section_geometry.sections], dtype=float)
    twist_sections = np.array([section.twist_deg for section in section_geometry.sections], dtype=float)
    dihedral_sections = np.array([section.dihedral_deg for section in section_geometry.sections], dtype=float)

    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(2, 2, height_ratios=[2.2, 1.0], hspace=0.28, wspace=0.22)

    # ------------------------------------------------------------------
    # Top-left: full planform
    # ------------------------------------------------------------------
    ax_planform = fig.add_subplot(gs[0, 0])

    # Control points
    # ax_planform.plot(
    #     planform.x_le,
    #     planform.y_le,
    #     "bo-",
    #     markersize=3,
    #     linewidth=1.0,
    #     label="LE control points",
    # )
    # ax_planform.plot(
    #     planform.x_te,
    #     planform.y_te,
    #     "ro-",
    #     markersize=3,
    #     linewidth=1.0,
    #     label="TE control points",
    # )

    # Chord projection lines at control points
    for i in range(planform.n_points):
        ax_planform.plot(
            [planform.x_le[i], planform.x_te[i]],
            [planform.y_le[i], planform.y_le[i]],
            "k--",
            alpha=0.22,
            linewidth=0.8,
        )

    # Fine curves
    ax_planform.plot(
        planform.front_x_fine,
        planform.front_y_fine,
        "g-",
        linewidth=2.0,
        label="LE spline+linear",
    )
    ax_planform.plot(
        planform.rear_x_fine,
        planform.rear_y_fine,
        "m-",
        linewidth=2.0,
        label="TE spline+linear",
    )

    # Mirrored half
    ax_planform.plot(
        planform.front_x_mirrored,
        planform.front_y_mirrored,
        "g--",
        linewidth=1.5,
        alpha=0.9,
        label="LE mirrored",
    )
    ax_planform.plot(
        planform.rear_x_mirrored,
        planform.rear_y_mirrored,
        "m--",
        linewidth=1.5,
        alpha=0.9,
        label="TE mirrored",
    )

    # Section stations on upper half
    ax_planform.scatter(
        planform.front_x_fine,
        planform.front_y_fine,
        s=10,
        marker="x",
        label="Section stations",
    )

    # Group boundaries
    for yb in planform.group_boundary_y:
        ax_planform.axhline(y=yb, linestyle=":", linewidth=0.8, alpha=0.35)

    ax_planform.set_xlabel("x (m)")
    ax_planform.set_ylabel("y (m)")
    ax_planform.set_title("Planform Geometry")
    ax_planform.grid(True, alpha=0.3)
    ax_planform.axis("equal")
    ax_planform.legend(loc="best", fontsize=8)

    # ------------------------------------------------------------------
    # Top-right: metadata panel
    # ------------------------------------------------------------------
    ax_meta = fig.add_subplot(gs[0, 1])
    ax_meta.axis("off")

    generator_family = config.generator.family
    generator_version = config.generator.version
    seed = config.generator.seed

    info_lines = [
        f"Name: {config.name}",
        f"Generator: {generator_family} {generator_version}",
        f"Seed: {seed}",
        "",
        "Sampled Planform",
        f"  c1 = {planform.c1:.4f} m",
        f"  c2 = {planform.c2:.4f} m",
        f"  c3 = {planform.c3:.4f} m",
        f"  c4 = {planform.c4:.4f} m",
        f"  b_total = {planform.b_total:.4f} m",
        f"  b1 = {planform.b1:.4f} m",
        f"  b2 = {planform.b2:.4f} m",
        f"  b3 = {planform.b3:.4f} m",
        f"  sw1 = {planform.sw1_deg:.3f} deg",
        f"  sw2 = {planform.sw2_deg:.3f} deg",
        f"  sw3 = {planform.sw3_deg:.3f} deg",
        "",
        "Metrics",
        f"  Semi-span = {planform.semi_span_m:.4f} m",
        f"  Full span = {planform.full_span_m:.4f} m",
        f"  Area = {planform.approx_area_m2:.4f} m²",
        f"  AR(planform) = {planform.approx_aspect_ratio:.4f}",
        f"  Num sections = {planform.num_sections}",
        f"  N1 / N2 / N3 = {planform.N1} / {planform.N2} / {planform.N3}",
        "",
        "Section Boundaries",
        f"  Twist: [{section_geometry.twist_b0_deg:.2f}, "
        f"{section_geometry.twist_b1_deg:.2f}, "
        f"{section_geometry.twist_b2_deg:.2f}, "
        f"{section_geometry.twist_b3_deg:.2f}] deg",
        f"  Dihedral: [{section_geometry.dihedral_b0_deg:.2f}, "
        f"{section_geometry.dihedral_b1_deg:.2f}, "
        f"{section_geometry.dihedral_b2_deg:.2f}, "
        f"{section_geometry.dihedral_b3_deg:.2f}] deg",
        f"  Airfoil: {config.section_bounds.airfoil_name}",
    ]

    ax_meta.text(
        0.02,
        0.98,
        "\n".join(info_lines),
        va="top",
        ha="left",
        fontsize=10,
        family="monospace",
    )
    ax_meta.set_title("Run Metadata")

    # ------------------------------------------------------------------
    # Bottom-left: chord distribution
    # ------------------------------------------------------------------
    ax_chord = fig.add_subplot(gs[1, 0])
    ax_chord.plot(y_sections, chord_sections, linewidth=2.0, label="Chord")
    ax_chord.scatter(y_sections, chord_sections, s=12)
    for yb in planform.group_boundary_y:
        ax_chord.axvline(yb, linestyle=":", linewidth=0.8, alpha=0.35)

    ax_chord.set_xlabel("Spanwise station y (m)")
    ax_chord.set_ylabel("Chord (m)")
    ax_chord.set_title("Chord Distribution")
    ax_chord.grid(True, alpha=0.3)
    ax_chord.legend(loc="best", fontsize=8)

    # ------------------------------------------------------------------
    # Bottom-right: twist + dihedral
    # ------------------------------------------------------------------
    ax_angles = fig.add_subplot(gs[1, 1])
    ax_angles.plot(y_sections, twist_sections, linewidth=2.0, label="Twist (deg)")
    ax_angles.plot(y_sections, dihedral_sections, linewidth=2.0, label="Dihedral (deg)")
    ax_angles.scatter(y_sections, twist_sections, s=12)
    ax_angles.scatter(y_sections, dihedral_sections, s=12)

    for yb in planform.group_boundary_y:
        ax_angles.axvline(yb, linestyle=":", linewidth=0.8, alpha=0.35)

    ax_angles.set_xlabel("Spanwise station y (m)")
    ax_angles.set_ylabel("Angle (deg)")
    ax_angles.set_title("Twist and Dihedral Distributions")
    ax_angles.grid(True, alpha=0.3)
    ax_angles.legend(loc="best", fontsize=8)

    fig.suptitle("AERIS Geometry Debug View", fontsize=16)
    plt.tight_layout()
    plt.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)