"""Server-rendered SVG charts for the live monitor.

trame-plotly is not installed here, and a residual monitor does not need a
charting library: it needs one polyline per channel, redrawn a few times a
second.  Generating the SVG on the server keeps the payload to a few kilobytes
and puts the axis behaviour under our control - most importantly the log axis,
where a linear autoscale would hide exactly the decade that matters.
"""

from __future__ import annotations

from typing import Iterable

RESIDUAL_COLORS = ("#4da3ff", "#ff8a4c", "#3fcf8e", "#ffd166", "#c792ea", "#ff6b8a")
FORCE_COLORS = ("#4da3ff", "#ff8a4c", "#3fcf8e")


def _nice_bounds(low: float, high: float) -> tuple[float, float]:
    if not (low < high):
        return (low - 1.0, high + 1.0)
    pad = (high - low) * 0.08
    return (low - pad, high + pad)


def _empty(message: str, height: int = 260) -> str:
    return (
        f'<div style="height:{height}px;display:flex;align-items:center;'
        'justify-content:center;color:#7d8590;font:13px system-ui;'
        'border:1px dashed #30363d;border-radius:8px">'
        f"{message}</div>"
    )


def line_chart(
    x: list[float],
    series: list[tuple[str, list[float], str]],
    *,
    title: str = "",
    y_label: str = "",
    height: int = 300,
    gate: float | None = None,
    gate_label: str = "",
) -> str:
    """One SVG with a polyline per series and a shared x axis."""
    series = [(name, values, color) for name, values, color in series if values]
    if not x or not series:
        return _empty(title or "waiting for the first iteration", height)

    width, ml, mr, mt, mb = 720, 62, 118, 14, 34
    pw, ph = width - ml - mr, height - mt - mb

    flat = [v for _, values, _ in series for v in values if v == v]
    if not flat:
        return _empty("no finite values yet", height)
    low, high = _nice_bounds(min(flat), max(flat))
    if gate is not None:
        low, high = _nice_bounds(min(min(flat), gate), max(max(flat), gate))
    x_max = max(x) or 1.0

    def px(value: float) -> float:
        return ml + pw * (value / x_max)

    def py(value: float) -> float:
        return mt + ph * (high - value) / (high - low)

    parts: list[str] = [
        f'<svg viewBox="0 0 {width} {height}" style="width:100%;height:auto;'
        'font-family:ui-monospace,Menlo,monospace" role="img">'
    ]
    for step in range(5):
        value = low + (high - low) * step / 4
        y = py(value)
        parts.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{y:.1f}" y2="{y:.1f}" '
                     'stroke="#30363d" stroke-width="1"/>')
        parts.append(f'<text x="{ml - 8}" y="{y + 4:.1f}" text-anchor="end" '
                     f'font-size="10" fill="#7d8590">{value:.3g}</text>')
    for step in range(5):
        value = x_max * step / 4
        x_pos = px(value)
        parts.append(f'<line x1="{x_pos:.1f}" x2="{x_pos:.1f}" y1="{mt}" y2="{mt + ph}" '
                     'stroke="#21262d" stroke-width="1"/>')
        parts.append(f'<text x="{x_pos:.1f}" y="{mt + ph + 20}" text-anchor="middle" '
                     f'font-size="10" fill="#7d8590">{int(value)}</text>')

    if gate is not None and low < gate < high:
        y = py(gate)
        parts.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{y:.1f}" y2="{y:.1f}" '
                     'stroke="#f85149" stroke-width="1.4" stroke-dasharray="6 4"/>')
        if gate_label:
            parts.append(f'<text x="{ml + 6}" y="{y - 5:.1f}" font-size="10" '
                         f'fill="#f85149">{gate_label}</text>')

    placed: list[float] = []
    for name, values, color in series:
        count = min(len(values), len(x))
        points = " ".join(f"{px(x[i]):.1f},{py(values[i]):.1f}"
                          for i in range(count) if values[i] == values[i])
        if not points:
            continue
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" '
                     'stroke-width="1.8" stroke-linejoin="round"/>')
        y = py(values[count - 1])
        while any(abs(y - other) < 13 for other in placed):
            y += 13
        placed.append(y)
        parts.append(f'<text x="{ml + pw + 9}" y="{y + 4:.1f}" font-size="10.5" '
                     f'fill="{color}">{name} {values[count - 1]:.4g}</text>')

    if y_label:
        parts.append(f'<text transform="translate(13,{mt + ph / 2:.0f}) rotate(-90)" '
                     f'text-anchor="middle" font-size="10" fill="#7d8590">{y_label}</text>')
    parts.append(f'<text x="{ml + pw / 2:.0f}" y="{height - 4}" text-anchor="middle" '
                 'font-size="10" fill="#7d8590">iteration</text>')
    parts.append("</svg>")
    return "".join(parts)


def residual_chart(history: dict[str, list[float]], labels: dict[str, str],
                   *, gate: float | None = None, height: int = 300) -> str:
    x = history.get("iteration") or []
    series = []
    for index, (key, label) in enumerate(labels.items()):
        values = history.get(key)
        if values:
            series.append((label, values, RESIDUAL_COLORS[index % len(RESIDUAL_COLORS)]))
    return line_chart(x, series, title="residuals", y_label="log10 residual",
                      height=height, gate=gate,
                      gate_label=f"gate {gate:g}" if gate is not None else "")


def force_chart(history: dict[str, list[float]], keys: Iterable[str],
                labels: dict[str, str], *, height: int = 240) -> str:
    x = history.get("iteration") or []
    series = []
    for index, key in enumerate(keys):
        values = history.get(key)
        if values:
            series.append((labels.get(key, key), values,
                           FORCE_COLORS[index % len(FORCE_COLORS)]))
    return line_chart(x, series, title="forces", y_label="coefficient", height=height)


def sparkline(values: list[float], *, width: int = 150, height: int = 30,
              color: str = "#4da3ff") -> str:
    if len(values) < 2:
        return ""
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    step = width / (len(values) - 1)
    points = " ".join(f"{i * step:.1f},{height - (v - low) / span * height:.1f}"
                      for i, v in enumerate(values))
    return (f'<svg viewBox="0 0 {width} {height}" style="width:{width}px;height:{height}px">'
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.5"/></svg>')
