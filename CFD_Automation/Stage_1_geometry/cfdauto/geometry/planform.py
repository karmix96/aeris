"""Exact panels: straight leading and trailing edges through the four stations."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .params import TypeSpec, chord_ratios, panel_mean_chord, resolve


@dataclass(frozen=True)
class Planform:
    y: np.ndarray           # station span positions b0..b3 [m]
    x_le: np.ndarray        # station leading-edge x [m]
    chord: np.ndarray       # station chords [m]
    sweep_le_deg: np.ndarray  # panel leading-edge sweeps (signed, + aft)
    twist_deg: np.ndarray | None = None  # station twists (for the exact ruled-panel area)

    @property
    def semi_span(self) -> float:
        return float(self.y[-1])

    @property
    def panel_span(self) -> np.ndarray:
        return np.diff(self.y)

    def at(self, y: np.ndarray | float) -> tuple[np.ndarray, np.ndarray]:
        """Leading-edge x and chord at span positions (linear inside each panel)."""
        y = np.asarray(y, dtype=float)
        return np.interp(y, self.y, self.x_le), np.interp(y, self.y, self.chord)

    def area(self) -> float:
        """Full-wing area (both halves) = 2 x integral of the true chord over y, exact for straight
        (ruled) panels, including the small chord loss where the twist changes along a panel."""
        tw = np.radians(self.twist_deg) if self.twist_deg is not None else np.zeros_like(self.chord)
        return float(2.0 * sum(h * panel_mean_chord(a, b, ta, tb) for a, b, ta, tb, h in
                               zip(self.chord[:-1], self.chord[1:], tw[:-1], tw[1:], self.panel_span)))


def semi_span_m(spec: TypeSpec, vec: dict[str, float]) -> float:
    """Semi-span in metres of a resolved vector."""
    if spec.span_mode == "root_chord_fractions":
        return vec["semi_span_m"] * vec["root_chord_m"]
    return vec["semi_span_m"]


def build_planform(spec: TypeSpec, vec: dict[str, float]) -> Planform:
    vec = resolve(spec, vec)
    s = semi_span_m(spec, vec)
    p3 = vec["b3_ratio"] * s
    rest = s - p3
    p1 = vec["split_ratio"] * rest
    p2 = rest - p1
    spans = np.array([p1, p2, p3])
    if s <= 0 or np.any(spans <= 0):
        raise ValueError(f"every panel needs a positive span, got {spans.tolist()}")

    c0 = vec["root_chord_m"]
    chord = c0 * np.array(chord_ratios(spec.chord_law, vec))
    if np.any(chord <= 0):
        raise ValueError(f"every chord must be positive, got {chord.tolist()}")

    sweep = np.array([vec["sweep1_deg"], vec["sweep2_deg"], vec["sweep3_deg"]])
    if np.any(np.abs(sweep) >= 89.0):
        raise ValueError("sweep must be within +/-89 deg")
    y = np.concatenate([[0.0], np.cumsum(spans)])
    x_le = np.concatenate([[0.0], np.cumsum(spans * np.tan(np.radians(sweep)))])
    twist = np.array([vec[f"twist{i}_deg"] for i in range(4)])
    return Planform(y=y, x_le=x_le, chord=chord, sweep_le_deg=sweep, twist_deg=twist)


def panel_sweep_deg(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Sweep of the straight lines between consecutive points (+ aft)."""
    return np.degrees(np.arctan2(np.diff(x), np.diff(y)))


def mean_aero_chord(planform: Planform) -> float:
    """MAC = integral c^2 dy / integral c dy, exact for linear chord per panel."""
    num = 0.0
    den = 0.0
    for a, b, h in zip(planform.chord[:-1], planform.chord[1:], planform.panel_span):
        num += h * (a * a + a * b + b * b) / 3.0
        den += h * (a + b) / 2.0
    return num / den


def aspect_ratio(planform: Planform) -> float:
    return (2.0 * planform.semi_span) ** 2 / planform.area()
