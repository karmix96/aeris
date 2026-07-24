"""Native visualization helpers for pyGeo geometry realizations."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def find_pygeo_plot_path(*, output_dir: Path, pygeo_result: Any) -> Path | None:
    """Resolve the canonical native-pyGeo plot across result schema versions."""

    if pygeo_result is not None:
        artifact = getattr(pygeo_result, "artifacts", {}).get("geometry_3d_plot")
        if artifact:
            candidate = Path(artifact)
            if candidate.exists():
                return candidate
    candidate = Path(output_dir) / "pygeo" / "geometry_3d.png"
    return candidate if candidate.exists() else None


def write_pygeo_interactive_html(pygeo_result: Any, path: Path) -> Path:
    """Write a browser-ready view directly from native pyGeo surface samples.

    This intentionally does not construct or translate through an AeroSandbox
    geometry object. Plotly is imported lazily because it is a GUI dependency,
    not a requirement for ordinary headless geometry generation.
    """

    import numpy as np
    import plotly.graph_objects as go

    upper = np.asarray(pygeo_result.upper_surface, dtype=float)
    lower = np.asarray(pygeo_result.lower_surface, dtype=float)
    if upper.ndim != 3 or lower.shape != upper.shape or upper.shape[2] != 3:
        raise ValueError(
            "pyGeo visualization surfaces must be equal "
            "(n_chord, n_span, 3) grids"
        )

    chord_stride = max(1, int(np.ceil(upper.shape[0] / 100)))
    span_stride = max(1, int(np.ceil(upper.shape[1] / 120)))
    figure = go.Figure()
    for side, sign in (("right", 1.0), ("left", -1.0)):
        for label, surface, color in (
            ("upper", upper, "#2563EB"),
            ("lower", lower, "#14B8A6"),
        ):
            shown = surface[::chord_stride, ::span_stride].copy()
            shown[:, :, 1] *= sign
            figure.add_trace(
                go.Surface(
                    x=shown[:, :, 0],
                    y=shown[:, :, 1],
                    z=shown[:, :, 2],
                    surfacecolor=np.zeros(shown.shape[:2]),
                    colorscale=[[0.0, color], [1.0, color]],
                    showscale=False,
                    name=f"{side} {label}",
                    opacity=0.94,
                    hovertemplate=(
                        f"{side} {label}<br>x=%{{x:.5f}} m"
                        "<br>y=%{y:.5f} m<br>z=%{z:.5f} m<extra></extra>"
                    ),
                )
            )

    geometry_id = getattr(pygeo_result, "geometry_id", "pygeo_geometry")
    figure.update_layout(
        title=f"Aeris native pyGeo loft · {geometry_id}",
        scene={
            "xaxis_title": "x [m]",
            "yaxis_title": "y [m]",
            "zaxis_title": "z [m]",
            "aspectmode": "data",
            "camera": {"eye": {"x": -1.55, "y": -1.8, "z": 0.85}},
        },
        margin={"l": 0, "r": 0, "t": 55, "b": 0},
    )
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(path, include_plotlyjs=True, full_html=True)
    return path
