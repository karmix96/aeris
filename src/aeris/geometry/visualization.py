"""
Geometry visualization helpers for AERIS.

Purpose:
    Provide a reusable, package-native visualization path for one geometry case,
    so the CLI does not have to call legacy scripts directly.

Responsibilities:
    - Load a geometry config
    - Resolve generator and sample one deterministic design
    - Run one geometry case into a debug output folder
    - Save a plot if requested
    - Optionally display the saved 2D plot
    - Optionally open the AeroSandbox 3D draw window

Notes:
    - This is intentionally debug-oriented, not a production run pipeline.
    - We use the same generator path as the real software, not a separate script-only path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

from aeris.common.config import load_yaml_config
from aeris.generators.bwb_segmented_v1.generator import BwbSegmentedV1Generator


@dataclass(frozen=True)
class GeometryVisualizationResult:
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
    """
    Generate and visualize one geometry from a YAML config.

    Returns:
        GeometryVisualizationResult with output path and visualization status.
    """
    config_path = Path(config_path).expanduser().resolve()
    raw_config = load_yaml_config(config_path)

    cfg_name = _resolve_config_name(raw_config=raw_config, config_path=config_path)
    out_dir = _resolve_output_dir(output_dir=output_dir, config_name=cfg_name)
    out_dir.mkdir(parents=True, exist_ok=True)

    generator = BwbSegmentedV1Generator()
    generator_config = generator.build_config(raw_config)

    case_seed = seed
    if case_seed is None:
        try:
            case_seed = int(generator_config.generator.seed)
        except Exception:
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

    result = generator.run_full_case(
        sample=generator.sample_one(generator_config, seed=case_seed),
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


def _resolve_config_name(*, raw_config: dict[str, Any], config_path: Path) -> str:
    name = raw_config.get("name") or config_path.stem
    return _safe_slug(str(name))


def _resolve_output_dir(*, output_dir: str | Path | None, config_name: str) -> Path:
    if output_dir is not None:
        return Path(output_dir).expanduser().resolve()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _project_root() / "data" / "debug" / "visualization_runs" / f"{ts}_geometry_{config_name}"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


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
    image = plt.imread(plot_path)
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.imshow(image)
    ax.axis("off")
    plt.show()