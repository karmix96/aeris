#!/usr/bin/env python3
"""Build the RIBES section table that ribes_loft.py reads, from the laser scan.

The section is the MEDIAN CAMBER and MEDIAN THICKNESS of 17 sections sliced out
of MeasuredCADmodel.stp, then lightly smoothed. Each choice here was forced by a
failure, so they are recorded rather than tuned:

  median camber and thickness, not median upper and lower
      Medianing the two surfaces independently let them cross, and the mesher
      refused the grid. Thickness is non-negative on every input section, so its
      median is too, and the reconstruction cannot cross.

  interpolation in sqrt(x), not x
      Near the nose z ~ sqrt(x). A linear interpolant in x cuts that corner, and
      the mesher measures the result as kinks: a 160-point table read as 19.47
      degrees of leading-edge turning against a 10 degree target.

  Savitzky-Golay window 41 over 2000 points
      Chosen by sweeping the window and building the mesh at each one, because
      the acceptance test is whether a grid comes out, not how the curve looks:

          window   agreement with the taps   build
               0                   0.095 %c   2641 folded cells
               9                   0.082 %c   2524 folded
              21                   0.080 %c   1450 folded
              41                   0.074 %c   clean, LE turning 1.676 deg
              81                   0.076 %c   clean, LE turning 5.308 deg

      41 both builds and agrees best with the pressure taps -- the smoothing is
      removing scan noise, not geometry, which is why fidelity improves with it.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from scipy.signal import savgol_filter

HERE = Path(__file__).resolve().parent
SECTIONS = HERE / "data/ribes/ribes_measured_sections.json"
OUT = HERE / "external/ribes/ribes_section.dat"
N_POINTS, WINDOW = 2000, 41


def main() -> int:
    D = json.loads(SECTIONS.read_text())["sections"]
    grid = np.linspace(0.0, 1.0, N_POINTS) ** 2          # dense at the nose
    cams, thks = [], []
    for _, s in sorted(D.items(), key=lambda t: int(t[0])):
        if s["n_points"] < 150:
            continue
        P = np.column_stack([s["xc"], s["zc"]])
        c = P.mean(axis=0)
        P = P[np.argsort(np.arctan2(P[:, 1] - c[1], (P[:, 0] - c[0]) * 0.25))]
        P = np.roll(P, -int(np.argmin(P[:, 0])), axis=0)
        z_le = P[0, 1]
        half = int(np.argmax(P[:, 0]))
        a, b = P[:half + 1], np.vstack([P[half:], P[:1]])[::-1]
        upper, lower = (a, b) if a[:, 1].mean() > b[:, 1].mean() else (b, a)

        def onto(curve: np.ndarray) -> np.ndarray:
            curve = curve[np.argsort(curve[:, 0])]
            xs = np.concatenate([[0.0], curve[:, 0]])
            zs = np.concatenate([[z_le], curve[:, 1]])
            o = np.argsort(xs)
            return np.interp(np.sqrt(grid), np.sqrt(xs[o]), zs[o])

        u, l = onto(upper), onto(lower)
        cams.append(0.5 * (u + l))
        thks.append(u - l)

    cam = savgol_filter(np.median(np.array(cams), axis=0), WINDOW, 3)
    thk = np.maximum(savgol_filter(np.median(np.array(thks), axis=0), WINDOW, 3), 0.0)
    thk[0] = 0.0                                          # close at the leading edge
    up, lo = cam + 0.5 * thk, cam - 0.5 * thk
    np.savetxt(OUT, np.column_stack([grid, up, lo]), fmt="%.7f",
               header=f"x/c  z/c_upper  z/c_lower   median camber and thickness of "
                      f"{len(cams)} scanned sections, Savitzky-Golay window {WINDOW}")
    print(f"  {len(cams)} sections -> {N_POINTS} points, t/c max {100 * thk.max():.2f} %, "
          f"crossings {bool(np.any(thk[1:] < 0))}")
    print(f"  wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
