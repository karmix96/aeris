"""Spanwise geometric information density, and adaptive section placement.

Motivation
----------
The low-fidelity chain hands AVL a *piecewise-linear* wing: between two
extraction sections AVL interpolates leading-edge position, chord, incidence, the
airfoil shape and the control gain linearly. So the discretisation error of the
AVL model is the interpolation error of those spanwise functions — and that error
is not spread evenly. It concentrates wherever the loft *curves*: near planform
breaks, through the airfoil transition, at dihedral and twist gradients.

A uniform section grid therefore spends its budget wrongly: it over-resolves the
straight outboard panel and under-resolves the breaks. The convergence study
(Task 4a) shows the cost — the elevon control derivative oscillates at the ±1.5 %
level between 13 and 33 uniform sections, because what matters is where sections
land relative to features, not how many there are.

Method
------
Classical equidistribution (de Boor 1973). For piecewise-linear interpolation of
a function g the local error over a cell of width h scales as h²·|g''|/8, so the
error is equidistributed when the node spacing satisfies

    h(y) ∝ |g''(y)|^(-1/2)      i.e.      density ρ(y) ∝ |g''(y)|^(1/2)

Nodes are then placed at equal increments of the cumulative density ∫ρ dy.

A wing is not one function, so ``ρ`` is a weighted blend over several
**channels** — the independent spanwise functions AVL interpolates:

    x_le(y)   leading-edge sweep      (ρ picks up sweep BREAKS, not sweep itself)
    z_le(y)   dihedral                (picks up dihedral breaks)
    chord(y)  taper                   (picks up taper breaks)
    twist(y)  incidence distribution
    t/c(y)    thickness / airfoil transition
    camber(y) camber / airfoil transition
    gain(y)   CONTROL-SURFACE GAIN    (see below — usually the dominant channel)

Each channel is scaled by a FIXED physical reference before differentiating —
lengths by the root chord, twist by 10°, thickness/camber by 0.1 — so the blend
is dimensionless *and* a channel that barely varies contributes proportionally
little.

**This is a correction.** The first implementation normalised each channel to its
own range and then to unit integral. That made channels comparable but destroyed
the magnitude information: a sweep break of 1.05 and a wiggle of 0.0002 both
integrated to exactly 1.0, so the metric could not tell a sharply-kinked wing
from a smooth one — the judgement it exists to make. Fixed reference scales keep
"how much this varies" alongside "where it varies".

The control channel
-------------------
DECISION-0010 established that the binding discretisation error in the low-fi
chain is resolution of the **control surface**, not of the wing: AVL ramps the
control gain from 1 to 0 over the interval just outside each band edge, and the
error scales with that ramp width as a fraction of the band width (r = +0.978).

The control gain is *itself* a spanwise function AVL interpolates linearly —
a boxcar, 1 inside the band and 0 outside. So it is not a special case needing
bespoke handling: it is simply the channel with the sharpest features. Its second
derivative is a pair of delta functions at the band edges, so the same de Boor
monitor automatically concentrates sections there, and a narrow elevon
automatically attracts a larger share of the budget.

The boxcar is smoothed over a small span fraction before differentiating, because
a true delta would take the entire budget. The smoothing width sets how tightly
sections cluster at the edges, and is the one genuinely tunable knob here.

Note what this measures: a constant-sweep panel has x_le'' = 0 and contributes
NO information density — correctly, since AVL represents it exactly with two
sections. Information lives at *changes* of gradient. This is why the metric
finds planform breaks and airfoil transitions without being told where they are.

Cost
----
``spanwise_information_profile`` probes the loft on a dense v-grid using a small
chordwise sample per station (no CST fitting), so it is orders of magnitude
cheaper than extracting sections. It runs *before* the section budget is spent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

__all__ = [
    "CONTROL_EDGE_SMOOTHING",
    "ramp_fraction",
    "InformationChannel",
    "InformationProfile",
    "DEFAULT_CHANNEL_WEIGHTS",
    "probe_spanwise_geometry",
    "spanwise_information_profile",
    "adaptive_span_fractions",
]

# Equal weight on every channel is the neutral default: it asserts only that all
# six spanwise functions matter, without a tuned prior on which. Sensitivity to
# this choice is reported in the study rather than hidden.
DEFAULT_CHANNEL_WEIGHTS: dict[str, float] = {
    "x_le": 1.0,
    "z_le": 1.0,
    "chord": 1.0,
    "twist": 1.0,
    "thickness": 1.0,
    "camber": 1.0,
    # Weighted above the geometric channels because DECISION-0010 measured the
    # control surface, not the wing, as the binding error. Not a free parameter:
    # 3.0 is the smallest weight that drives the ramp fraction of the worst case
    # (a 0.15-wide band) under the 15% criterion at a 25-section budget.
    "control_gain": 3.0,
}

# Fixed physical scales each channel is divided by before differentiating.
# Lengths are in units of the ROOT CHORD; twist in units of 10 degrees;
# thickness and camber in units of 0.1 (10% of chord). These make a unit of one
# channel roughly as aerodynamically significant as a unit of another, WITHOUT
# erasing how much each actually varies on a given wing.
CHANNEL_REFERENCE_SCALES: dict[str, str | float] = {
    "x_le": "root_chord", "z_le": "root_chord", "chord": "root_chord",
    "twist": 10.0, "thickness": 0.1, "camber": 0.1, "control_gain": 1.0,
}

# Half-width, in span fractions, over which the control-gain boxcar is smoothed
# before differentiating. A true step would put a delta at each band edge and
# consume the whole budget; this sets how tightly sections cluster there.
CONTROL_EDGE_SMOOTHING = 0.02

_EPS = 1e-12


@dataclass
class InformationChannel:
    """One spanwise geometry function and its information density."""

    name: str
    values: np.ndarray          # g(y), raw physical units
    normalised: np.ndarray      # g(y) scaled to unit range
    density: np.ndarray         # rho_k(y) = |g''|^(1/2), unit integral
    weight: float
    total_variation: float      # range of the raw values, for reporting


@dataclass
class InformationProfile:
    """Blended spanwise information density and its cumulative distribution."""

    span_fraction: np.ndarray          # the probe grid, in [0, 1]
    y_m: np.ndarray                    # physical spanwise station of each probe
    density: np.ndarray                # blended rho(y), unit integral
    cumulative: np.ndarray             # normalised cumulative, 0 -> 1
    channels: dict[str, InformationChannel] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def channel_shares(self) -> dict[str, float]:
        """Fraction of the blended density each channel ACTUALLY contributes.

        Integrates weight x density per channel, so a near-flat channel reports a
        small share. (The first implementation returned the weights themselves,
        because per-channel normalisation had already erased the magnitudes.)
        """
        x = np.asarray(self.span_fraction, dtype=float)
        parts = {name: c.weight * float(np.trapezoid(c.density, x))
                 for name, c in self.channels.items()}
        total = sum(parts.values()) or 1.0
        return {name: v / total for name, v in parts.items()}

    def concentration(self) -> float:
        """How non-uniform the density is: 1.0 = uniform, higher = peaked.

        The ratio of the L2 norm to the L1 norm of the density, scaled so a
        constant density gives exactly 1. A wing whose information is
        concentrated in a few breaks scores well above 1, and is exactly the case
        where adaptive placement pays.
        """
        d = np.asarray(self.density, dtype=float)
        x = np.asarray(self.span_fraction, dtype=float)
        l1 = float(np.trapezoid(np.abs(d), x))
        l2 = math.sqrt(float(np.trapezoid(d * d, x)))
        if l1 <= _EPS:
            return 1.0
        return l2 / l1


def probe_spanwise_geometry(
    build: Any,
    *,
    n_probe: int = 401,
    chordwise_probe: int = 25,
) -> dict[str, np.ndarray]:
    """Sample the loft's spanwise geometry functions cheaply.

    Returns arrays over a uniform *span-fraction* grid: ``span_fraction``,
    ``y_m``, ``x_le``, ``z_le``, ``chord``, ``twist_deg``, ``thickness``
    (max t/c) and ``camber`` (max camber / chord).

    No CST fitting and no section planarisation — just ``chordwise_probe``
    surface evaluations per station, which is what makes this affordable before
    the section budget is chosen.
    """
    from aeris.generators.bwb_segmented_v1.pygeo_adapter import (
        _section_endpoints_at_v,
        span_parameters_for_fractions,
    )

    fractions = np.linspace(0.0, 1.0, int(n_probe))
    v_params = span_parameters_for_fractions(build, fractions)

    top, bottom = build.geometry.surfs[0], build.geometry.surfs[1]
    u = 0.5 * (1.0 - np.cos(np.linspace(0.0, math.pi, int(chordwise_probe))))

    n = len(fractions)
    y_m = np.empty(n)
    x_le = np.empty(n)
    z_le = np.empty(n)
    chord = np.empty(n)
    twist = np.empty(n)
    thickness = np.empty(n)
    camber = np.empty(n)

    for i, v in enumerate(v_params):
        le, te = _section_endpoints_at_v(build, float(v))
        y_m[i] = le[1]
        x_le[i] = le[0]
        z_le[i] = le[2]
        dx, dz = te[0] - le[0], te[2] - le[2]
        c = math.hypot(dx, dz)
        chord[i] = c
        # Incidence of the LE->TE line in the x-z plane; nose-up positive.
        twist[i] = math.degrees(math.atan2(-dz, dx)) if c > _EPS else 0.0

        vv = np.full_like(u, float(v))
        pt = np.asarray(top(u, vv), dtype=float)
        pb = np.asarray(bottom(u, vv), dtype=float)
        if c > _EPS:
            # Project onto the local chord line to get a t/c and camber measure
            # without a full planarisation.
            ex = np.array([dx, dz]) / c
            en = np.array([-ex[1], ex[0]])
            rel_t = np.stack([pt[:, 0] - le[0], pt[:, 2] - le[2]], axis=1)
            rel_b = np.stack([pb[:, 0] - le[0], pb[:, 2] - le[2]], axis=1)
            nt = rel_t @ en
            nb = rel_b @ en
            thickness[i] = float(np.max(np.abs(nt - nb))) / c
            camber[i] = float(np.max(np.abs(0.5 * (nt + nb)))) / c
        else:
            thickness[i] = 0.0
            camber[i] = 0.0

    return {
        "span_fraction": fractions, "y_m": y_m, "x_le": x_le, "z_le": z_le,
        "chord": chord, "twist_deg": twist, "thickness": thickness,
        "camber": camber,
    }


def _channel_density(values: np.ndarray, y: np.ndarray, smooth: int,
                     scale: float) -> tuple[np.ndarray, np.ndarray, float]:
    """(scaled values, density, total variation) for one channel.

    density = |g''|^(1/2), the de Boor monitor for piecewise-LINEAR
    interpolation, which is what AVL does between sections.

    ``scale`` is a FIXED physical reference (see CHANNEL_REFERENCE_SCALES), not
    the channel's own range. The density is deliberately NOT normalised to unit
    integral: its magnitude must survive so that a channel with a sharp break
    outweighs one that is nearly flat.
    """
    v = np.asarray(values, dtype=float)
    span = float(np.max(v) - np.min(v))
    if span <= _EPS or scale <= _EPS:
        return np.zeros_like(v), np.zeros_like(v), 0.0
    vn = (v - float(np.min(v))) / float(scale)

    d1 = np.gradient(vn, y, edge_order=2)
    d2 = np.gradient(d1, y, edge_order=2)
    monitor = np.sqrt(np.abs(d2))

    if smooth and smooth > 1:
        # The loft's curvature is spread over a finite width by the B-spline; a
        # short moving average suppresses probe-grid noise in the second
        # derivative without moving the features.
        k = int(smooth) | 1
        kernel = np.ones(k) / k
        monitor = np.convolve(np.pad(monitor, k // 2, mode="edge"), kernel, mode="valid")

    return vn, monitor, span


def _control_gain_channel(
    span_fraction: np.ndarray,
    band: "tuple[float, float]",
    *,
    smoothing: float = CONTROL_EDGE_SMOOTHING,
) -> np.ndarray:
    """The control-gain boxcar, smoothed so its curvature is finite.

    AVL interpolates this exactly like chord or twist, so it belongs in the same
    monitor. Smoothed with a tanh so d2/dy2 peaks sharply at each band edge
    instead of being a delta.
    """
    lo, hi = float(band[0]), float(band[1])
    w = max(float(smoothing), 1e-4)
    return 0.5 * (np.tanh((span_fraction - lo) / w)
                  - np.tanh((span_fraction - hi) / w))


def spanwise_information_profile(
    build: Any,
    *,
    n_probe: int = 401,
    chordwise_probe: int = 25,
    weights: dict[str, float] | None = None,
    smooth: int = 9,
    floor: float = 0.50,
    probe: dict[str, np.ndarray] | None = None,
    control_band: "tuple[float, float] | None" = None,
    control_edge_smoothing: float = CONTROL_EDGE_SMOOTHING,
) -> InformationProfile:
    """Blended spanwise geometric information density of a pyGeo loft.

    ``control_band`` is the (start_frac, end_frac) of the control surface. Pass it
    whenever the design has one — it is normally the dominant channel, and
    omitting it reproduces the uniform-spacing failure mode on narrow bands.

    ``floor`` mixes a uniform density back in:
        rho = (1 - floor) * rho_geometric + floor * uniform
    Without it a region of exactly zero curvature (a straight outboard panel)
    would receive *no* sections, and the aerodynamics — which is not purely a
    geometry interpolation problem — still needs resolution there.

    **floor = 0.50 is a measured value, not a taste.** At the theoretically
    "pure" floor = 0.15, equidistribution concentrated so hard on the sharp
    features that it left a maximum section gap 4.4x larger than uniform, starving
    the inboard region, and the resulting placement was WORSE than uniform on
    every case tested (DECISION-0011). Raising the floor is this module's form of
    the gradation control that mesh adaptation requires: at 0.50 the max gap ratio
    drops to 1.5-2.0x and adaptive placement becomes 2.78x better than uniform on
    a narrow control band, while staying neutral on benign geometry.
    """
    weights = dict(DEFAULT_CHANNEL_WEIGHTS if weights is None else weights)
    p = probe if probe is not None else probe_spanwise_geometry(
        build, n_probe=n_probe, chordwise_probe=chordwise_probe
    )

    y = np.asarray(p["y_m"], dtype=float)
    channel_sources = {
        "x_le": p["x_le"], "z_le": p["z_le"], "chord": p["chord"],
        "twist": p["twist_deg"], "thickness": p["thickness"],
        "camber": p["camber"],
    }
    if control_band is not None:
        channel_sources["control_gain"] = _control_gain_channel(
            np.asarray(p["span_fraction"], dtype=float), control_band,
            smoothing=control_edge_smoothing,
        )

    root_chord = float(np.asarray(p["chord"], dtype=float)[0]) or 1.0
    channels: dict[str, InformationChannel] = {}
    blended = np.zeros_like(y)
    for name, values in channel_sources.items():
        w = float(weights.get(name, 0.0))
        ref = CHANNEL_REFERENCE_SCALES.get(name, 1.0)
        scale = root_chord if ref == "root_chord" else float(ref)
        vn, density, tv = _channel_density(values, y, smooth, scale)
        channels[name] = InformationChannel(
            name=name, values=np.asarray(values, dtype=float), normalised=vn,
            density=density, weight=w, total_variation=tv,
        )
        if w > 0.0:
            # NOT re-normalised per channel: magnitude must survive the blend.
            blended = blended + w * density
    area = float(np.trapezoid(blended, y))
    span_len = float(y[-1] - y[0])
    if area <= _EPS or span_len <= _EPS:
        blended = np.ones_like(y) / max(span_len, _EPS)
    else:
        blended = blended / area

    uniform = np.ones_like(y) / span_len
    density = (1.0 - float(floor)) * blended + float(floor) * uniform
    density = density / float(np.trapezoid(density, y))

    cumulative = np.concatenate([[0.0], np.cumsum(
        0.5 * (density[1:] + density[:-1]) * np.diff(y)
    )])
    if cumulative[-1] > _EPS:
        cumulative = cumulative / cumulative[-1]

    return InformationProfile(
        span_fraction=np.asarray(p["span_fraction"], dtype=float),
        y_m=y, density=density, cumulative=cumulative, channels=channels,
        metadata={
            "n_probe": len(y), "chordwise_probe": int(chordwise_probe),
            "smooth": int(smooth), "floor": float(floor),
            "weights": weights, "control_band": control_band,
            "control_edge_smoothing": float(control_edge_smoothing),
            "channel_total_variation": {
                name: c.total_variation for name, c in channels.items()
            },
        },
    )


def adaptive_span_fractions(
    profile: InformationProfile,
    n_sections: int,
    *,
    must_include: Sequence[float] = (),
    min_spacing_frac: float = 1e-3,
) -> np.ndarray:
    """Place ``n_sections`` span fractions by equidistributing the density.

    Sections land at equal increments of the cumulative information, so cells
    carry equal interpolation error rather than equal width. Both span ends are
    always included.

    ``must_include`` pins extra fractions — used for the elevon band edges, where
    AVL's control-gain ramp makes an exact section mandatory (DECISION-0005).
    Pinned fractions replace their nearest interior neighbour rather than being
    added, so the budget is respected exactly.
    """
    n = int(n_sections)
    if n < 2:
        raise ValueError("n_sections must be at least 2")

    targets = np.linspace(0.0, 1.0, n)
    fractions = np.interp(targets, profile.cumulative, profile.span_fraction)
    fractions[0], fractions[-1] = 0.0, 1.0

    for edge in sorted(float(e) for e in must_include):
        if not (0.0 < edge < 1.0):
            continue
        interior = np.arange(1, len(fractions) - 1)
        if interior.size == 0:
            break
        nearest = int(interior[np.argmin(np.abs(fractions[interior] - edge))])
        fractions[nearest] = edge

    fractions = np.unique(np.clip(fractions, 0.0, 1.0))
    # Enforce strict monotonic separation (extract_sections requires it).
    keep = [fractions[0]]
    for f in fractions[1:]:
        if f - keep[-1] >= float(min_spacing_frac):
            keep.append(f)
        elif f == fractions[-1]:
            keep[-1] = f
    return np.asarray(keep, dtype=float)


def ramp_fraction(span_fractions: "Sequence[float]", band: "tuple[float, float]") -> float:
    """The quantity DECISION-0010 identified as governing control-surface error.

    (total width of the gain-ramp intervals just outside the band edges) /
    (band width). AVL ramps the control gain to zero across those intervals, so
    they are the part of the control it smears. Measured r = +0.978 against
    CL_delta error. Target <~ 0.15.
    """
    f = np.unique(np.asarray(list(span_fractions), dtype=float))
    lo, hi = float(band[0]), float(band[1])
    width = hi - lo
    if width <= _EPS:
        return float("inf")
    below = f[f < lo - 1e-9]
    above = f[f > hi + 1e-9]
    ramp = ((lo - below[-1]) if below.size else 0.0) + \
           ((above[0] - hi) if above.size else 0.0)
    return float(ramp / width)
