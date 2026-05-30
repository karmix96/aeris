"""
Geometry visualization helpers for AERIS.

Purpose:
    Provide a reusable, package-native visualization path for one geometry
    case, so the CLI does not call legacy scripts directly.

Responsibilities:
    - Load a geometry config (via aeris.common.config)
    - Resolve generator via the registry (no hardcoded generator)
    - Sample one deterministic design
    - Run one geometry case into a debug output folder
    - Save a plot if requested
    - Optionally display the saved 2D plot
    - Optionally open the AeroSandbox 3D draw window

Notes:
    - This module is intentionally debug-oriented, not a production pipeline.
    - It uses the same generator chain as production code (registry-based),
      so any registered generator works without code changes here.
    - Output folders go under {data_dir}/debug/visualization_runs/ where
      data_dir is resolved by aeris.common.paths (editable install, packaged
      install, cluster scratch, and cloud worker all work transparently).
    - Matplotlib is imported lazily, so simply importing this module stays
      fast (relevant for CLI --help latency).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aeris.common.config import load_yaml_config
from aeris.common.paths import get_data_dir
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator


@dataclass(frozen=True)
class GeometryVisualizationResult:
    """Result of a one-shot geometry visualization."""

    output_dir: Path
    plot_path: Path | None
    has_aerosandbox_airplane: bool


def visualize_geometry_from_config(
    config_path: str | Path,
    *,
    seed: int | None = None,
    save_plot: bool | None = None,
    build_aerosandbox: bool | None = None,
    output_dir: str | Path | None = None,
    show_plot: bool = False,
    draw_3d: bool = True,
) -> GeometryVisualizationResult:
    """Generate and visualize one geometry from a YAML config.

    Returns:
        GeometryVisualizationResult with output path and visualization status.

    Raises:
        ValueError: if the config is malformed (propagated from the resolver).
        KeyError: if the resolved generator ID is not registered.
        RuntimeError: if 3D draw is requested but no AeroSandbox airplane is
            available.
    """
    config_path = Path(config_path).expanduser().resolve()
    raw_config = load_yaml_config(config_path)

    generator_id, generator_config = resolve_generator_and_config(raw_config)
    generator = get_geometry_generator(generator_id)

    cfg_name = _resolve_config_name(raw_config=raw_config, config_path=config_path)
    out_dir = _resolve_output_dir(output_dir=output_dir, config_name=cfg_name)
    out_dir.mkdir(parents=True, exist_ok=True)

    case_seed = seed
    if case_seed is None:
        # Many generator configs expose a generator-level seed. Treat it as
        # a best-effort default. Generators without such a field fall through
        # to None and the sampler picks its own.
        try:
            case_seed = int(generator_config.generator.seed)
        except (AttributeError, TypeError, ValueError):
            case_seed = None

    save_plot_final = _resolve_bool_override(
        override=save_plot,
        raw_config=raw_config,
        path=("geometry", "outputs", "save_plot"),
        default=True,
    )
    build_aerosandbox_final = _resolve_bool_override(
        override=build_aerosandbox,
        raw_config=raw_config,
        path=("geometry", "outputs", "build_aerosandbox"),
        default=True,
    )

    sample = generator.sample_one(generator_config, seed=case_seed)

    # NOTE: save_plot and build_aerosandbox are BWB-specific kwargs not in
    # the abstract base contract. Tracker item D15 covers moving these into
    # the config object during the Layer 2 (BWB) review.
    result = generator.run_full_case(
        sample=sample,
        config=generator_config,
        output_dir=out_dir,
        save_plot=save_plot_final,
        build_aerosandbox=build_aerosandbox_final,
    )

    plot_path = _find_plot_path(out_dir)

    if show_plot and plot_path is not None and plot_path.exists():
        _show_saved_plot(plot_path)

    has_airplane = (
        getattr(result, "aerosandbox_result", None) is not None
        and getattr(result.aerosandbox_result, "airplane", None) is not None
    )

    if draw_3d:
        if not has_airplane:
            raise RuntimeError(
                "3D draw requested, but AeroSandbox airplane is not available. "
                "Enable build_aerosandbox in config or via --build-aerosandbox."
            )
        airplane = result.aerosandbox_result.airplane
        airplane.draw()

    return GeometryVisualizationResult(
        output_dir=out_dir,
        plot_path=plot_path,
        has_aerosandbox_airplane=has_airplane,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_config_name(*, raw_config: dict[str, Any], config_path: Path) -> str:
    name = raw_config.get("name") or config_path.stem
    return _safe_slug(str(name))


def _resolve_output_dir(
    *,
    output_dir: str | Path | None,
    config_name: str,
) -> Path:
    if output_dir is not None:
        return Path(output_dir).expanduser().resolve()

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return (
        get_data_dir()
        / "debug"
        / "visualization_runs"
        / f"{ts}_geometry_{config_name}"
    )


def _safe_slug(text: str) -> str:
    cleaned = []
    for ch in text.strip():
        if ch.isalnum() or ch in {"-", "_"}:
            cleaned.append(ch)
        else:
            cleaned.append("_")
    return "".join(cleaned).strip("_") or "geometry"


def _resolve_bool_override(
    *,
    override: bool | None,
    raw_config: dict[str, Any],
    path: tuple[str, ...],
    default: bool,
) -> bool:
    if override is not None:
        return override

    node: Any = raw_config
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]

    return bool(node)


def _find_plot_path(output_dir: Path) -> Path | None:
    candidates = [
        output_dir / "planform.png",
        output_dir / "artifacts" / "planform.png",
        output_dir / "geometry" / "planform.png",
        output_dir / "geometry" / "artifacts" / "planform.png",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _show_saved_plot(plot_path: Path) -> None:
    # Lazy import: matplotlib is heavy (~50 MB, ~0.4–0.8 s startup). Importing
    # it only when actually displaying keeps CLI help and import time fast.
    import matplotlib.pyplot as plt

    image = plt.imread(plot_path)
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.imshow(image)
    ax.axis("off")
    plt.show()