"""Plotting helpers for the standalone pyGeo/AVL study."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from standalone.pygeo_avl_study.geometry_bridge import (
    ExtractedSection,
    PyGeoBuild,
    sample_main_surfaces,
)


COLORS = {
    "AeroSandbox intended": "#111827",
    "AeroSandbox production": "#6B7280",
    "pyGeo kSpan=2": "#2563EB",
    "pyGeo kSpan=3": "#DC2626",
    "pyGeo kSpan=4": "#059669",
    "pyGeo global-y": "#9333EA",
}


def _finish(fig, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_geometry_comparison(
    *,
    builds: Mapping[str, PyGeoBuild],
    curves: Mapping[str, Sequence[ExtractedSection]],
    intended_records,
    path: Path,
) -> None:
    """3-D, planform, chord, and twist comparison in one figure."""
    fig = plt.figure(figsize=(15, 11), constrained_layout=True)
    ax3d = fig.add_subplot(2, 2, 1, projection="3d")
    ax_plan = fig.add_subplot(2, 2, 2)
    ax_chord = fig.add_subplot(2, 2, 3)
    ax_twist = fig.add_subplot(2, 2, 4)

    nominal_y = np.asarray([r.y_m for r in intended_records])
    nominal_xle = np.asarray([r.x_le_m for r in intended_records])
    nominal_z = np.asarray([r.z_le_m for r in intended_records])
    nominal_chord = np.asarray([r.chord_m for r in intended_records])
    nominal_twist = np.asarray([r.twist_deg for r in intended_records])
    nominal_frac = (nominal_y - nominal_y[0]) / (nominal_y[-1] - nominal_y[0])

    ax_plan.plot(
        nominal_y,
        nominal_xle,
        "k.-",
        lw=1.2,
        label="AeroSandbox intended LE",
    )
    ax_plan.plot(nominal_y, nominal_xle + nominal_chord, "k.--", lw=1.0, label="ASB TE")

    for label, build in builds.items():
        color = COLORS.get(label)
        upper, _ = sample_main_surfaces(
            build, chordwise_points=51, spanwise_points=81
        )
        ax3d.plot_wireframe(
            upper[:, :, 0],
            upper[:, :, 1],
            upper[:, :, 2],
            rstride=5,
            cstride=8,
            linewidth=0.45,
            alpha=0.55,
            color=color,
            label=label,
        )

    ax3d.plot(nominal_xle, nominal_y, nominal_z, "k.-", lw=1.4)
    ax3d.plot(nominal_xle + nominal_chord, nominal_y, nominal_z, "k.--", lw=1.0)
    ax3d.set_title("Realised right-half outer mould lines")
    ax3d.set_xlabel("x [m]")
    ax3d.set_ylabel("y [m]")
    ax3d.set_zlabel("z [m]")
    ax3d.view_init(elev=25, azim=-125)

    for label, sections in curves.items():
        color = COLORS.get(label)
        frac = np.asarray([s.span_fraction for s in sections])
        y = np.asarray([s.y_m for s in sections])
        xle = np.asarray([s.x_le_m for s in sections])
        chord = np.asarray([s.chord_m for s in sections])
        twist = np.asarray([s.twist_deg for s in sections])
        ax_plan.plot(y, xle, color=color, lw=1.5, label=f"{label} LE")
        ax_plan.plot(y, xle + chord, color=color, lw=1.0, ls="--")
        nominal_c_at = np.interp(frac, nominal_frac, nominal_chord)
        ax_chord.plot(
            frac,
            100.0 * (chord - nominal_c_at) / nominal_c_at,
            color=color,
            label=label,
        )
        ax_twist.plot(frac, twist, color=color, label=label)

    ax_twist.plot(nominal_frac, nominal_twist, "k.--", label="Authored")
    ax_plan.invert_yaxis()
    ax_plan.set_title("Planform (LE solid, TE dashed)")
    ax_plan.set_xlabel("y [m]")
    ax_plan.set_ylabel("x [m]")
    ax_plan.axis("equal")
    ax_plan.legend(fontsize=7, ncol=2)
    ax_chord.axhline(0.0, color="0.6", lw=0.8)
    ax_chord.set_title("Realised chord change from authored stations")
    ax_chord.set_xlabel("semispan fraction")
    ax_chord.set_ylabel("Δchord [%]")
    ax_chord.grid(alpha=0.25)
    ax_chord.legend(fontsize=8)
    ax_twist.set_title("Extracted incidence")
    ax_twist.set_xlabel("semispan fraction")
    ax_twist.set_ylabel("twist [deg]")
    ax_twist.grid(alpha=0.25)
    ax_twist.legend(fontsize=8)
    fig.suptitle("pyGeo lofting versus the AeroSandbox section model", fontsize=15)
    _finish(fig, path)


def plot_section_reconstruction(
    sections: Sequence[ExtractedSection],
    *,
    path: Path,
) -> None:
    choices = [sections[0], sections[len(sections) // 2], sections[-1]]
    fig, axes = plt.subplots(3, 2, figsize=(14, 10), constrained_layout=True)
    for row, section in enumerate(choices):
        x = np.linspace(0.0, 1.0, 501)
        direct_u = np.interp(x, section.x_upper, section.z_upper)
        direct_l = np.interp(x, section.x_lower, section.z_lower)
        cst_u = section.cst.upper(x)
        cst_l = section.cst.lower(x)

        ax = axes[row, 0]
        ax.plot(x, direct_u, "k-", lw=1.6, label="pyGeo slice")
        ax.plot(x, direct_l, "k-", lw=1.6)
        ax.plot(x, cst_u, "r--", lw=1.2, label=f"CST order {section.cst_order}")
        ax.plot(x, cst_l, "r--", lw=1.2)
        ax.axis("equal")
        ax.grid(alpha=0.2)
        ax.set_title(
            f"η={section.span_fraction:.2f}, t/c={section.thickness_ratio:.3f}"
        )
        ax.set_ylabel("z/c")
        if row == 2:
            ax.set_xlabel("x/c")
        if row == 0:
            ax.legend()

        residual = np.concatenate([cst_u - direct_u, cst_l - direct_l])
        axr = axes[row, 1]
        axr.plot(x, 1.0e4 * (cst_u - direct_u), color="#DC2626", label="upper")
        axr.plot(x, 1.0e4 * (cst_l - direct_l), color="#2563EB", label="lower")
        axr.axhline(0.0, color="0.5", lw=0.7)
        axr.grid(alpha=0.2)
        axr.set_title(
            f"RMS={section.cst_rms_chord:.2e} c, "
            f"max={np.max(np.abs(residual)):.2e} c"
        )
        axr.set_ylabel("fit error [×10⁻⁴ c]")
        if row == 2:
            axr.set_xlabel("x/c")
        if row == 0:
            axr.legend()
    fig.suptitle("Realised pyGeo sections and CST reconstruction", fontsize=15)
    _finish(fig, path)


def plot_cst_order_study(frame: pd.DataFrame, path: Path) -> None:
    summary = (
        frame.groupby("cst_order")
        .agg(
            rms_median=("cst_rms_chord", "median"),
            rms_max=("cst_rms_chord", "max"),
            max_error=("cst_max_chord", "max"),
            valid_fraction=("cst_valid", "mean"),
            runtime_s=("runtime_sec", "sum"),
        )
        .reset_index()
    )
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), constrained_layout=True)
    ax = axes[0]
    ax.semilogy(summary.cst_order, summary.rms_median, "o-", label="median RMS")
    ax.semilogy(summary.cst_order, summary.rms_max, "s-", label="worst RMS")
    ax.semilogy(summary.cst_order, summary.max_error, "^-", label="worst point")
    ax.set_xlabel("CST polynomial order")
    ax.set_ylabel("normalised error [chord]")
    ax.grid(alpha=0.25, which="both")
    ax.legend()
    ax.set_title("Geometric reconstruction")

    ax = axes[1]
    ax.plot(summary.cst_order, 100 * summary.valid_fraction, "o-", color="#059669")
    ax.set_ylim(-2, 102)
    ax.set_xlabel("CST polynomial order")
    ax.set_ylabel("sections passing validation [%]")
    ax.grid(alpha=0.25)
    ax2 = ax.twinx()
    ax2.plot(summary.cst_order, summary.runtime_s, "s--", color="#9333EA")
    ax2.set_ylabel("total extraction time [s]")
    ax.set_title("Validity and cost")
    fig.suptitle("CST order sensitivity", fontsize=14)
    _finish(fig, path)


def plot_polar_comparison(frame: pd.DataFrame, path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    for (section, representation, interface), group in frame.groupby(
        ["section_label", "representation", "interface"]
    ):
        style = "--" if representation != "direct" else "-"
        label = f"{section}: {representation}/{interface}"
        axes[0, 0].plot(group.alpha_deg, group.CL, style, lw=1.2, label=label)
        axes[0, 1].plot(group.CL, group.CD, style, lw=1.2, label=label)
        axes[1, 0].plot(group.alpha_deg, group.CD, style, lw=1.2, label=label)
        axes[1, 1].plot(
            group.alpha_deg, group.analysis_confidence, style, lw=1.2, label=label
        )
    axes[0, 0].set(xlabel="α [deg]", ylabel="CL", title="Lift curve")
    axes[0, 1].set(xlabel="CL", ylabel="CD", title="Drag polar")
    axes[1, 0].set(xlabel="α [deg]", ylabel="CD", title="Profile drag")
    axes[1, 1].set(
        xlabel="α [deg]", ylabel="confidence", title="NeuralFoil confidence"
    )
    for ax in axes.flat:
        ax.grid(alpha=0.25)
    axes[0, 0].legend(fontsize=6, ncol=2)
    fig.suptitle("NeuralFoil sensitivity to section extraction and interface", fontsize=14)
    _finish(fig, path)


def plot_avl_comparison(frame: pd.DataFrame, path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    for label, group in frame.sort_values("alpha_deg").groupby("geometry"):
        color = COLORS.get(label)
        axes[0, 0].plot(group.alpha_deg, group.CL, "o-", ms=3, label=label, color=color)
        axes[0, 1].plot(
            group.alpha_deg, group.CD_induced, "o-", ms=3, label=label, color=color
        )
        if group.CD_corrected.notna().any():
            axes[1, 0].plot(
                group.alpha_deg, group.CD_corrected, "o-", ms=3, label=label, color=color
            )
            axes[1, 1].plot(
                group.alpha_deg,
                group.L_over_D_corrected,
                "o-",
                ms=3,
                label=label,
                color=color,
            )
    axes[0, 0].set(xlabel="α [deg]", ylabel="CL", title="AVL lift")
    axes[0, 1].set(xlabel="α [deg]", ylabel="CDi", title="Induced drag")
    axes[1, 0].set(
        xlabel="α [deg]", ylabel="CDi + CDprofile", title="Viscous-corrected drag"
    )
    axes[1, 1].set(
        xlabel="α [deg]", ylabel="CL/CD corrected", title="Corrected efficiency"
    )
    for ax in axes.flat:
        ax.grid(alpha=0.25)
    axes[0, 0].legend(fontsize=7, ncol=2)
    fig.suptitle("AeroSandbox-authored versus pyGeo-derived AVL models", fontsize=14)
    _finish(fig, path)


def plot_convergence(frame: pd.DataFrame, path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), constrained_layout=True)
    for alpha, group in frame.groupby("alpha_deg"):
        label = f"α={alpha:g}°"
        axes[0].plot(group.n_sections, group.CL_error_pct, "o-", label=label)
        axes[1].plot(group.n_sections, group.CDi_error_pct, "o-", label=label)
        axes[2].plot(group.n_sections, group.runtime_sec, "o-", label=label)
    axes[0].set(xlabel="extracted AVL sections", ylabel="CL error [%]", title="Lift")
    axes[1].set(
        xlabel="extracted AVL sections", ylabel="CDi error [%]", title="Induced drag"
    )
    axes[2].set(
        xlabel="extracted AVL sections", ylabel="runtime [s]", title="Runtime"
    )
    for ax in axes:
        ax.grid(alpha=0.25)
        ax.legend()
    fig.suptitle("pyGeo-to-AVL section sampling convergence", fontsize=14)
    _finish(fig, path)


def plot_doe_summary(frame: pd.DataFrame, path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    axes[0, 0].hist(100 * frame.area_delta_k3_pct / 100, bins=12, alpha=0.8)
    axes[0, 0].set(xlabel="kSpan=3 area change [%]", ylabel="count")
    axes[0, 1].hist(1e3 * frame.max_cst_rms_chord, bins=12, alpha=0.8)
    axes[0, 1].set(xlabel="worst CST RMS [×10⁻³ c]", ylabel="count")
    scatter = axes[1, 0].scatter(
        frame.max_abs_twist_deg,
        100 * frame.max_plane_warp_chord,
        c=frame.area_delta_k3_pct,
        cmap="coolwarm",
    )
    axes[1, 0].set(
        xlabel="max |twist| [deg]",
        ylabel="max slice warp [% chord]",
        title="When planar extraction becomes difficult",
    )
    fig.colorbar(scatter, ax=axes[1, 0], label="area change [%]")
    axes[1, 1].scatter(
        frame.min_chord_m,
        frame.geometry_runtime_sec,
        c=frame.failed.astype(int),
        cmap="RdYlGn_r",
    )
    axes[1, 1].set(
        xlabel="minimum chord [m]",
        ylabel="pyGeo + extraction time [s]",
        title="DOE robustness/runtime",
    )
    for ax in axes.flat:
        ax.grid(alpha=0.2)
    fig.suptitle("Wide-bound Paper-1 DOE pyGeo stress study", fontsize=14)
    _finish(fig, path)
