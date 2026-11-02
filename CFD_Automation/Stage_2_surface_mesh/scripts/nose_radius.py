"""Nose radius of the suggested airfoils: the raw file against the Stage 1 resampled section.

Found while solving the nose spacing (law 1): the resampled section's curvature at the leading edge
differs between the upper and lower side by up to 4-13 x, while the raw points give one nose. Writes
data/studies/nose_radius.json. A Stage 1 (geometry) item; the mesher is made robust to it meanwhile.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cfdauto.geometry import airfoils as A  # noqa: E402
from cfdauto.geometry.sections import load_airfoil  # noqa: E402
from cfdauto.paths import STAGE2  # noqa: E402

AIRFOILS = ("mh104", "mh61", "mh45", "mh60", "e387", "sd7032", "s5010", "la2573a", "naca4415", "naca25118")


def circle_radius(a, b, c) -> float:
    ab, bc, ca = np.linalg.norm(b - a), np.linalg.norm(c - b), np.linalg.norm(a - c)
    s = 0.5 * (ab + bc + ca)
    area = np.sqrt(max(s * (s - ab) * (s - bc) * (s - ca), 1e-300))
    return float(ab * bc * ca / (4 * area))


def raw_nose(name: str) -> dict:
    pts = A.raw_points(name)
    te = 0.5 * (pts[0] + pts[-1])
    i = int(np.argmax(np.linalg.norm(pts - te, axis=1)))
    chord = float(np.linalg.norm(pts[i] - te))
    r = [circle_radius(pts[k - 1], pts[k], pts[k + 1]) / chord for k in range(max(i - 2, 1), min(i + 3, len(pts) - 1))]
    return {"min_R_c_near_le": float(min(r)), "R_c_at_le_point": float(circle_radius(pts[i - 1], pts[i], pts[i + 1]) / chord),
            "points_within_1pct_c": int(np.sum(np.linalg.norm(pts - pts[i], axis=1) < 0.01 * chord))}


def resampled_nose(name: str) -> dict:
    af = load_airfoil(name)
    s = np.sqrt(af.x)
    # y = sqrt(2 R x) near a round nose, so R = (dy/ds)^2 / 2 with s = sqrt(x)
    return {"R_c_upper": float((af.yu[1] / s[1]) ** 2 / 2), "R_c_lower": float((af.yl[1] / s[1]) ** 2 / 2)}


def main() -> None:
    out = {}
    for n in AIRFOILS:
        try:
            out[n] = {"raw": raw_nose(n), "resampled": resampled_nose(n)}
            r, m = out[n]["raw"], out[n]["resampled"]
            print(f"{n:10s} raw R/c at LE {r['R_c_at_le_point']:.4f} (min near {r['min_R_c_near_le']:.4f}); "
                  f"resampled upper {m['R_c_upper']:.4f} lower {m['R_c_lower']:.4f}")
        except Exception as exc:
            out[n] = {"error": f"{type(exc).__name__}: {exc}"}
            print(n, out[n]["error"])
    path = STAGE2 / "data" / "studies" / "nose_radius.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
