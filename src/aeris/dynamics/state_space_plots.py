"""State-space plotting utilities for saved AERIS state-space reports.

D5.2 scope:
    - read an existing state_space_result.json
    - write static PNG evidence plots
    - do not recompute dynamics or change solver physics
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from aeris.dynamics.state_space_run import find_state_space_result, read_state_space_result

STATE_SPACE_PLOT_MANIFEST_SCHEMA_VERSION = "state_space_plot_manifest_v0.1"
VALID_STATE_SPACE_PLOTS = {"all", "eigenvalues", "mode-summary"}


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) or math.isinf(out) else out


def _safe_slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_")


def _load_result_from_run_dir(run_dir: str | Path) -> tuple[Path, dict[str, Any]]:
    path = find_state_space_result(run_dir)
    if path is None:
        raise FileNotFoundError(
            f"Could not find state_space_result.json under {Path(run_dir)}. "
            "Run 'aeris dynamics state-space' first."
        )
    return path, read_state_space_result(path)


def _collect_eigenvalue_points(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    section_labels = [
        ("longitudinal", "Longitudinal"),
        ("lateral_directional", "Lateral-directional"),
    ]
    for section_key, section_label in section_labels:
        section = result.get(section_key, {}) or {}
        for idx, eig in enumerate(section.get("all_eigenvalues", []) or [], start=1):
            if not isinstance(eig, dict):
                continue
            real = _as_float(eig.get("real"))
            imag = _as_float(eig.get("imag"))
            if real is None or imag is None:
                continue
            rows.append(
                {
                    "section": section_key,
                    "section_label": section_label,
                    "name": f"{section_label} λ{idx}",
                    "real": real,
                    "imag": imag,
                    "stable": real < 0.0,
                }
            )
    return rows


def _collect_named_modes(result: dict[str, Any]) -> list[dict[str, Any]]:
    mode_specs = [
        ("longitudinal", "short_period", "Short period"),
        ("longitudinal", "phugoid", "Phugoid"),
        ("lateral_directional", "roll_subsidence", "Roll subsidence"),
        ("lateral_directional", "spiral", "Spiral"),
        ("lateral_directional", "dutch_roll", "Dutch roll"),
    ]
    rows: list[dict[str, Any]] = []
    for section_key, mode_key, label in mode_specs:
        mode = (result.get(section_key, {}) or {}).get(mode_key, {}) or {}
        if not isinstance(mode, dict):
            continue
        real = _as_float(mode.get("eigenvalue_real"))
        imag = _as_float(mode.get("eigenvalue_imag")) or 0.0
        if real is None:
            continue
        rows.append(
            {
                "section": section_key,
                "mode": mode_key,
                "label": label,
                "real": real,
                "imag": imag,
                "stability_margin": -real,
                "stable": real < 0.0,
                "zeta": _as_float(mode.get("zeta")),
                "omega_n": _as_float(mode.get("omega_n")),
                "time_to_double_s": _as_float(mode.get("time_to_double_s")),
            }
        )
    return rows


def _import_matplotlib():
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    return plt


def plot_state_space_eigenvalues(
    *,
    result: dict[str, Any],
    output_path: str | Path,
    dpi: int = 180,
) -> Path:
    """Write an eigenvalue map PNG from a state-space result."""
    points = _collect_eigenvalue_points(result)
    if not points:
        raise ValueError("No eigenvalues found in state_space_result.json.")

    plt = _import_matplotlib()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(9.5, 6.5))

    section_markers = {
        "longitudinal": "o",
        "lateral_directional": "s",
    }
    for section_key, label in [("longitudinal", "Longitudinal"), ("lateral_directional", "Lateral-directional")]:
        subset = [p for p in points if p["section"] == section_key]
        if not subset:
            continue
        ax.scatter(
            [p["real"] for p in subset],
            [p["imag"] for p in subset],
            marker=section_markers[section_key],
            label=label,
            s=58,
        )
        for p in subset:
            ax.annotate(
                p["name"].replace("Longitudinal ", "L").replace("Lateral-directional ", "D"),
                (p["real"], p["imag"]),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=8,
            )

    ax.axvline(0.0, linewidth=1.5, linestyle="--", label="Stability boundary")
    ax.axhline(0.0, linewidth=0.8)
    ax.set_title("AERIS state-space eigenvalue map")
    ax.set_xlabel("Real part σ [1/s]")
    ax.set_ylabel("Imaginary part ωd [rad/s]")
    ax.grid(True, alpha=0.35)
    ax.legend(loc="best")

    stability = result.get("linear_stability_summary", {}) or {}
    if stability:
        text = (
            f"overall stable: {stability.get('overall_linear_stable')}\n"
            f"unstable eigenvalues: {stability.get('total_unstable_eigenvalue_count')}\n"
            f"max real: {stability.get('max_real_eigenvalue')}"
        )
        ax.text(
            0.99,
            0.02,
            text,
            transform=ax.transAxes,
            ha="right",
            va="bottom",
            fontsize=8,
            bbox={"boxstyle": "round", "alpha": 0.12},
        )

    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return output_path


def plot_state_space_mode_summary(
    *,
    result: dict[str, Any],
    output_path: str | Path,
    dpi: int = 180,
) -> Path:
    """Write a named-mode stability-margin PNG from a state-space result.

    The plotted value is -real(eigenvalue). Positive bars are locally stable;
    negative bars are locally unstable. This keeps the chart honest and avoids
    mixing damping ratios, time constants, and frequencies on one axis.
    """
    modes = _collect_named_modes(result)
    if not modes:
        raise ValueError("No named modes found in state_space_result.json.")

    plt = _import_matplotlib()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    labels = [m["label"] for m in modes]
    values = [m["stability_margin"] for m in modes]

    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    y_positions = list(range(len(labels)))
    ax.barh(y_positions, values)
    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels)
    ax.axvline(0.0, linewidth=1.5, linestyle="--")
    ax.set_xlabel("Stability margin = -real(λ) [1/s]")
    ax.set_title("AERIS named-mode stability summary")
    ax.grid(True, axis="x", alpha=0.35)

    for y, mode, value in zip(y_positions, modes, values):
        status = "stable" if mode["stable"] else "unstable"
        ax.text(
            value,
            y,
            f" {status} | real={mode['real']:.4g}",
            va="center",
            fontsize=8,
        )

    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return output_path


def render_state_space_plots(
    *,
    run_dir: str | Path,
    plot: str = "all",
    output_dir: str | Path | None = None,
    dpi: int = 180,
) -> dict[str, Any]:
    """Render requested state-space plots and write a manifest."""
    plot = plot.strip().lower()
    if plot not in VALID_STATE_SPACE_PLOTS:
        raise ValueError(
            f"Invalid plot '{plot}'. Expected one of: {', '.join(sorted(VALID_STATE_SPACE_PLOTS))}."
        )

    run_dir = Path(run_dir)
    result_path, result = _load_result_from_run_dir(run_dir)
    output_dir = Path(output_dir) if output_dir is not None else run_dir / "dynamics" / "plots"
    output_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, str | None] = {
        "eigenvalues_png": None,
        "mode_summary_png": None,
    }

    if plot in {"all", "eigenvalues"}:
        artifacts["eigenvalues_png"] = str(
            plot_state_space_eigenvalues(
                result=result,
                output_path=output_dir / "state_space_eigenvalues.png",
                dpi=dpi,
            )
        )

    if plot in {"all", "mode-summary"}:
        artifacts["mode_summary_png"] = str(
            plot_state_space_mode_summary(
                result=result,
                output_path=output_dir / "state_space_mode_summary.png",
                dpi=dpi,
            )
        )

    manifest = {
        "schema_version": STATE_SPACE_PLOT_MANIFEST_SCHEMA_VERSION,
        "source_run_dir": str(run_dir),
        "source_state_space_result": str(result_path),
        "requested_plot": plot,
        "dpi": dpi,
        "plot_count": sum(1 for value in artifacts.values() if value),
        "artifacts": artifacts,
        "linear_stability_summary": result.get("linear_stability_summary"),
        "limitations": [
            "Static PNG evidence plots generated from state_space_result.json.",
            "Does not recompute dynamics or change state-space physics.",
            "Eigenvalue map is a local linear diagnostic around one operating point.",
        ],
    }
    manifest_path = output_dir / "state_space_plot_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest
