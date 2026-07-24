"""Interactive side-by-side 3D viewer: pyGeo vs AeroSandbox (task 3).

For each candidate design it opens an interactive Plotly window with three linked
3D scenes you can rotate/zoom independently:
    [ pyGeo loft ]  [ AeroSandbox ]  [ Overlay (both, to see the difference) ]

Both surfaces are the SAME sampled design realized by the two tools, plus a
metrics banner in the title.

Usage (opens a browser window per candidate):
    # one candidate
    PYTHONPATH=src .venv/bin/python -m standalone.pygeo_asb_comparison.viewer \
        --config configs/geometry/bwb.yaml --seed 5000

    # sweep 50 candidates (opens each in turn; press Enter between)
    PYTHONPATH=src .venv/bin/python -m standalone.pygeo_asb_comparison.viewer \
        --config configs/geometry/bwb.yaml --n 50 --base-seed 5000

    # write self-contained HTML files instead of opening windows
    ... --n 50 --save-html data/runs/pygeo_asb_views
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np

from standalone.pygeo_asb_comparison.build import BothBackends, build_both
from standalone.pygeo_asb_comparison.metrics import asb_metrics, pygeo_metrics, relative_diff

_PYGEO_COLOR = "#2F80ED"
_ASB_COLOR = "#D97706"


def _pygeo_surfaces(build: Any) -> list:
    """pyGeo upper/lower B-spline patches as Plotly surfaces."""
    import plotly.graph_objects as go
    from aeris.generators.bwb_segmented_v1.pygeo_adapter import sample_main_surfaces

    upper, lower = sample_main_surfaces(build, chordwise_points=81, spanwise_points=81)
    traces = []
    for surf, name in ((upper, "pyGeo upper"), (lower, "pyGeo lower")):
        s = np.asarray(surf, dtype=float)
        traces.append(go.Surface(
            x=s[:, :, 0], y=s[:, :, 1], z=s[:, :, 2],
            showscale=False, colorscale=[[0, _PYGEO_COLOR], [1, _PYGEO_COLOR]],
            opacity=0.95, name=name, showlegend=False,
        ))
    return traces


def _asb_mesh(asb_result: Any, *, color: str = _ASB_COLOR, opacity: float = 0.95) -> Any:
    """AeroSandbox wing surface as a Plotly Mesh3d."""
    import plotly.graph_objects as go

    v, f = asb_result.wing.mesh_body(
        method="quad", chordwise_resolution=41, mesh_surface=True,
        mesh_tips=True, mesh_trailing_edge=True, mesh_symmetric=True,
    )
    v = np.asarray(v, dtype=float)
    f = np.asarray(f, dtype=int)
    # quad faces -> two triangles each
    tris = []
    for q in f:
        if len(q) == 4:
            tris.append([q[0], q[1], q[2]])
            tris.append([q[0], q[2], q[3]])
        elif len(q) == 3:
            tris.append(list(q))
    tris = np.asarray(tris, dtype=int)
    return go.Mesh3d(
        x=v[:, 0], y=v[:, 1], z=v[:, 2],
        i=tris[:, 0], j=tris[:, 1], k=tris[:, 2],
        color=color, opacity=opacity, name="AeroSandbox", showlegend=False,
    )


def make_figure(both: BothBackends) -> Any:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    pm = pygeo_metrics(both.extracted)
    am = asb_metrics(both.asb_result)
    rd = relative_diff(pm, am)

    fig = make_subplots(
        rows=1, cols=3,
        specs=[[{"type": "surface"}, {"type": "surface"}, {"type": "surface"}]],
        subplot_titles=("pyGeo loft", "AeroSandbox", "Overlay (both)"),
        horizontal_spacing=0.02,
    )
    for t in _pygeo_surfaces(both.pygeo_build):
        fig.add_trace(t, row=1, col=1)
    fig.add_trace(_asb_mesh(both.asb_result), row=1, col=2)
    # Overlay: pyGeo (semi-transparent) + ASB (semi-transparent), same scene.
    for t in _pygeo_surfaces(both.pygeo_build):
        t.opacity = 0.55
        fig.add_trace(t, row=1, col=3)
    fig.add_trace(_asb_mesh(both.asb_result, opacity=0.45), row=1, col=3)

    banner = (
        f"seed {both.seed}  |  "
        f"span {pm['span_m']:.3f} m ({rd['span_m']*100:+.2f}%)  |  "
        f"area {pm['planform_area_m2']:.3f} m² ({rd['planform_area_m2']*100:+.2f}%)  |  "
        f"AR {pm['aspect_ratio']:.2f} ({rd['aspect_ratio']*100:+.2f}%)  |  "
        f"vol {pm['volume_m3']:.4f} m³ ({rd['volume_m3']*100:+.2f}%)  "
        f"[pyGeo vs ASB]"
    )
    scene = dict(aspectmode="data", xaxis_title="x", yaxis_title="y", zaxis_title="z")
    fig.update_layout(
        title=banner, scene=scene, scene2=scene, scene3=scene,
        margin=dict(l=0, r=0, t=70, b=0), height=650,
    )
    return fig


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--seed", type=int, default=None, help="Single candidate seed.")
    ap.add_argument("--n", type=int, default=1, help="Number of candidates (with --base-seed).")
    ap.add_argument("--base-seed", type=int, default=5000)
    ap.add_argument("--n-sections", type=int, default=25)
    ap.add_argument("--save-html", type=Path, default=None,
                    help="Write HTML files here instead of opening windows.")
    args = ap.parse_args()

    seeds = [args.seed] if args.seed is not None else [args.base_seed + i for i in range(args.n)]
    if args.save_html is not None:
        args.save_html.mkdir(parents=True, exist_ok=True)

    index_rows = []
    for idx, seed in enumerate(seeds):
        both = build_both(args.config, seed=seed, n_sections=args.n_sections)
        fig = make_figure(both)
        if args.save_html is not None:
            out = args.save_html / f"pygeo_vs_asb_seed{seed}.html"
            fig.write_html(out, include_plotlyjs="cdn", full_html=True)
            pm = pygeo_metrics(both.extracted)
            am = asb_metrics(both.asb_result)
            rd = relative_diff(pm, am)
            index_rows.append((seed, out.name, pm, rd))
            print(f"[{idx + 1}/{len(seeds)}] wrote {out.name}")
        else:
            print(f"[{idx + 1}/{len(seeds)}] seed {seed}: opening interactive window…")
            fig.show()
            if idx < len(seeds) - 1:
                try:
                    input("  press Enter for the next candidate (Ctrl-C to stop)… ")
                except (KeyboardInterrupt, EOFError):
                    print("\nstopped.")
                    break

    if args.save_html is not None and index_rows:
        _write_index(args.save_html / "index.html", index_rows)
        print(f"\n[index] open {args.save_html / 'index.html'} to browse all "
              f"{len(index_rows)} candidates")
    return 0


def _write_index(path: Path, rows: list) -> None:
    """A small index page linking every candidate view + its key metrics."""
    cells = []
    for seed, fname, pm, rd in rows:
        cells.append(
            f"<tr><td><a href='{fname}'>seed {seed}</a></td>"
            f"<td>{pm['span_m']:.3f} ({rd['span_m']*100:+.2f}%)</td>"
            f"<td>{pm['planform_area_m2']:.3f} ({rd['planform_area_m2']*100:+.2f}%)</td>"
            f"<td>{pm['aspect_ratio']:.2f} ({rd['aspect_ratio']*100:+.2f}%)</td>"
            f"<td>{pm['taper_ratio']:.3f} ({rd['taper_ratio']*100:+.2f}%)</td>"
            f"<td>{pm['volume_m3']:.4f} ({rd['volume_m3']*100:+.2f}%)</td></tr>"
        )
    html = (
        "<!doctype html><meta charset='utf-8'><title>pyGeo vs ASB — candidates</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;background:#17212b;"
        "color:#e6ecf2}h1{font-size:1.3rem}table{border-collapse:collapse;font-size:.85rem}"
        "td,th{border:1px solid #334252;padding:.4rem .7rem;text-align:right}"
        "td:first-child,th:first-child{text-align:left}a{color:#4a9eff}"
        "th{background:#202b36;position:sticky;top:0}</style>"
        f"<h1>pyGeo vs AeroSandbox — {len(rows)} candidates</h1>"
        "<p>Metric = pyGeo value (pyGeo−ASB relative Δ). Click a seed for the "
        "interactive side-by-side 3D view.</p>"
        "<table><tr><th>candidate</th><th>span m</th><th>area m²</th><th>AR</th>"
        "<th>taper</th><th>volume m³</th></tr>"
        + "".join(cells) + "</table>"
    )
    path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
