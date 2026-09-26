#!/usr/bin/env python3
"""Read BlendedNet++ cases: the blended-wing surface and its pressure field.

BlendedNet++ (arXiv 2512.03280) is 12,490 steady RANS solutions on blended wing
bodies, FUN3D with Spalart-Allmaras, published CC0 on Harvard Dataverse:

    https://doi.org/10.7910/DVN/ICIDK4        26.16 GB in 14 split parts

Each case is a VTK 5.1 binary POLYDATA surface -- around 48,000 points -- with a
`cp` scalar on every point. That makes one file both a GEOMETRY SOURCE and an
ANSWER KEY, which is why it is worth the download.

WHAT IT IS GOOD FOR HERE, and what it is not:

  yes   an independent robustness demonstration. Meshing geometries somebody
        else designed is a far stronger claim than meshing our own sampler's
        output, and these are more extreme than ours: taper 0.075-0.113 against
        our 0.09-0.17, centrebody t/c 18 % against our 15.2 %.
  yes   cross-code, cross-paradigm checking of cp and CL -- our structured O-H
        against their unstructured FUN3D on the same geometry.
  no    drag. Their stated CD mesh-independence error is under 8 %, which is
        +/- 18 counts at the matching subset's median, against the 5-9 counts
        this project cares about.
  no    physics. Both codes run Spalart-Allmaras, so agreement would show that
        two SA solvers agree and nothing more.

One limit worth knowing before planning around it: the dataset varies PLANFORM
only -- nine parameters, fixed aerofoils -- so centrebody t/c is essentially
constant at 18.0-18.1 % across cases. It is a wide planform space, not a wide
shape space.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np

CP_PLAUSIBLE = (-60.0, 3.0)


class TruncatedCase(ValueError):
    """The file does not carry a complete points array and cp field."""


def read_case(path: Path | str) -> tuple[np.ndarray, np.ndarray]:
    """Return (points, cp). Raises rather than returning nonsense.

    Every check here is because the naive version produced garbage silently: a
    case truncated by a range request had no `SCALARS cp` at all, `bytes.find`
    returned -1, and the reader happily decoded from the end of the file and
    reported a cp maximum of 2e300.
    """
    raw = Path(path).read_bytes()
    i = raw.find(b"POINTS")
    if i < 0:
        raise TruncatedCase(f"{path}: no POINTS record")
    j = raw.find(b"\n", i)
    head = raw[i:j].split()
    n = int(head[1])
    need = n * 3 * 4
    if j + 1 + need > len(raw):
        raise TruncatedCase(f"{path}: points array runs past the end of the file")
    pts = np.frombuffer(raw[j + 1:j + 1 + need], dtype=">f4").reshape(-1, 3).astype(float)

    k = raw.find(b"SCALARS cp")
    if k < 0:
        raise TruncatedCase(f"{path}: no cp field")
    m = raw.find(b"LOOKUP_TABLE", k)
    e = raw.find(b"\n", m)
    if e < 0 or e + 1 + n * 8 > len(raw):
        raise TruncatedCase(f"{path}: cp field runs past the end of the file")
    cp = np.frombuffer(raw[e + 1:e + 1 + n * 8], dtype=">f8").astype(float)

    if not np.isfinite(cp).all():
        raise TruncatedCase(f"{path}: cp contains non-finite values")
    if not (CP_PLAUSIBLE[0] < cp.min() and cp.max() < CP_PLAUSIBLE[1]):
        raise TruncatedCase(f"{path}: cp range [{cp.min():.3g}, {cp.max():.3g}] is not physical")
    return pts, cp


def planform(points: np.ndarray, n_stations: int = 25) -> dict:
    """Chord, thickness and leading edge down the right half, tip to centreline.

    These are FULL models, spanning both wings; our mesher wants a half.
    """
    half = points[points[:, 1] >= 0.0]
    b = float(half[:, 1].max())
    out = []
    for f in np.linspace(0.0, 0.97, n_stations):
        s = half[np.abs(half[:, 1] - f * b) < 0.008 * b]
        if len(s) < 20:
            continue
        chord = float(s[:, 0].max() - s[:, 0].min())
        out.append({"eta": round(float(f), 4), "y": round(f * b, 6),
                    "chord": round(chord, 6),
                    "t_over_c_pct": round(float(100 * (s[:, 2].max() - s[:, 2].min()) / chord), 3),
                    "x_le": round(float(s[:, 0].min()), 6),
                    "n_points": int(len(s))})
    return {"semispan": round(b, 6), "stations": out}
