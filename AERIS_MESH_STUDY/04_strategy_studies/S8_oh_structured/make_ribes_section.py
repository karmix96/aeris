#!/usr/bin/env python
"""Build external/ribes/ribes_section.dat from the RIBES laser scan.

THE DEFECT THIS FIXES
---------------------
19.5% of the scan points are not on the wetted surface.  The RIBES model is an
aeroelastic article with a load-bearing structure, and the scan captured its
spar web: 15 of 17 sections carry a vertical column of points at x/c 0.19-0.21,
and section 1100 is 66.8% interior.  Sorting the raw cloud by polar angle
interleaves those interior points into the surface ring, and any fit through
them rattles.  The old smoothing spline still agreed with the 30 pressure taps
to 0.074% of chord, because the rattle lives *between* the taps -- so tap
agreement alone could not detect this.  The rattle then tripped separation over
the whole wing (C_L -0.153 against a measured +0.264).

Two measurements decide this file:
  * interior rejection: per-section CST residual 0.85% -> 0.032% of chord (26x).
  * CST rather than a smoothing spline: the nose is structural (the sqrt(x)
    class function), not fitted, so smoothness does not trade against fit.
Both metrics improve together, which is why this is a fix and not a taste call.
"""
import json
import numpy as np
from math import comb
from pathlib import Path

HERE = Path(__file__).resolve().parent
SECTIONS = HERE / "data/ribes/ribes_measured_sections.json"
OUT = HERE / "external/ribes/ribes_section.dat"

N_CST = 8          # 8 coefficients reach 0.03%c; more only refits scan noise
X_WIN = 0.01       # half-width of the x-neighbourhood used to test interiority
Z_TOL = 0.004      # a point needs material above AND below to count as interior
N_OUT = 400        # output points per surface, cosine-clustered


def reject_interior(x, z):
    """Drop points that have scan material both above and below them nearby.

    The wetted surface is the z-envelope of the cloud.  A spar-web point sits
    strictly inside it; a surface point cannot.
    """
    keep = np.ones(len(x), bool)
    for i in range(len(x)):
        near = np.abs(x - x[i]) < X_WIN
        if (z[near] > z[i] + Z_TOL).any() and (z[near] < z[i] - Z_TOL).any():
            keep[i] = False
    return x[keep], z[keep]


def split_surfaces(x, z):
    """Assign cleaned points to upper/lower against the local mid-line."""
    order = np.argsort(x)
    x, z = x[order], z[order]
    probe = np.linspace(0.0, 1.0, 60)
    mids = []
    for xx in probe:
        near = np.abs(x - xx) < 0.02
        mids.append(0.5 * (z[near].max() + z[near].min()) if near.any() else 0.0)
    mid = np.interp(x, probe, mids)
    return (x[z >= mid], z[z >= mid]), (x[z < mid], z[z < mid])


def cst_fit(x, z, n=N_CST):
    """Kulfan CST: z = x^0.5 (1-x) * sum A_i B_i(x) + x*z_te, linear in A_i."""
    z_te = z[x > 0.995].mean() if (x > 0.995).any() else 0.0
    cls = np.sqrt(np.clip(x, 0.0, 1.0)) * (1.0 - x)
    basis = np.column_stack(
        [cls * comb(n, i) * x**i * (1.0 - x) ** (n - i) for i in range(n + 1)])
    coeff, *_ = np.linalg.lstsq(basis, z - x * z_te, rcond=None)
    resid = float(np.sqrt(np.mean((basis @ coeff - (z - x * z_te)) ** 2)))

    def evaluate(g):
        cls_g = np.sqrt(np.clip(g, 0.0, 1.0)) * (1.0 - g)
        bg = np.column_stack(
            [cls_g * comb(n, i) * g**i * (1.0 - g) ** (n - i) for i in range(n + 1)])
        return bg @ coeff + g * z_te

    return evaluate, resid, coeff


def main():
    sections = json.loads(SECTIONS.read_text())["sections"]
    up_x, up_z, lo_x, lo_z = [], [], [], []
    per_section = {}
    for key, sec in sorted(sections.items(), key=lambda t: int(t[0])):
        x = np.asarray(sec["xc"], float)
        z = np.asarray(sec["zc"], float)
        if len(x) < 150:
            continue
        n_raw = len(x)
        x, z = reject_interior(x, z)
        (ux, uz), (lx, lz) = split_surfaces(x, z)
        _, r_up, _ = cst_fit(ux, uz)
        _, r_lo, _ = cst_fit(lx, lz)
        per_section[key] = {"n_raw": n_raw, "n_surface": int(len(x)),
                            "interior_fraction": 1.0 - len(x) / n_raw,
                            "cst_residual_upper_pct_chord": 100 * r_up,
                            "cst_residual_lower_pct_chord": 100 * r_lo}
        up_x.extend(ux); up_z.extend(uz)
        lo_x.extend(lx); lo_z.extend(lz)

    f_up, r_up, c_up = cst_fit(np.asarray(up_x), np.asarray(up_z))
    f_lo, r_lo, c_lo = cst_fit(np.asarray(lo_x), np.asarray(lo_z))

    # cosine clustering: dense at both edges, which is where curvature lives
    grid = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, N_OUT)))
    zu, zl = f_up(grid), f_lo(grid)
    zle = 0.5 * (zu[0] + zl[0])
    zu[0] = zl[0] = zle

    if np.any((zu - zl)[1:-1] <= 0.0):
        raise SystemExit("upper and lower surfaces cross -- refusing to write")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # three columns on a shared x/c grid: this is what ribes_loft reads
    with OUT.open("w") as fh:
        fh.write("# RIBES wing section, from the laser scan, interior points rejected\n")
        fh.write(f"# CST n={N_CST}; pooled residual upper {100*r_up:.3f}%c "
                 f"lower {100*r_lo:.3f}%c\n")
        fh.write("# x/c   z/c upper   z/c lower\n")
        for xx, zzu, zzl in zip(grid, zu, zl):
            fh.write(f"{xx:.8f} {zzu:.8f} {zzl:.8f}\n")

    thick, camber = zu - zl, 0.5 * (zu + zl)
    report = {
        "source": "RIBES laser scan, 17 sections",
        "method": f"interior rejection then CST n={N_CST} per surface",
        "pooled_residual_pct_chord": {"upper": 100 * r_up, "lower": 100 * r_lo},
        "thickness_max_pct_chord": 100 * float(thick.max()),
        "thickness_max_at_xc": float(grid[thick.argmax()]),
        "camber_max_pct_chord": 100 * float(camber.max()),
        "camber_max_at_xc": float(grid[camber.argmax()]),
        "trailing_edge_thickness_pct_chord": 100 * float(thick[-1]),
        "cst_coefficients": {"upper": c_up.tolist(), "lower": c_lo.tolist()},
        "per_section": per_section,
    }
    out_json = HERE / "reports/s8_ribes_section_fit.json"
    out_json.write_text(json.dumps(report, indent=2))

    print(f"wrote {OUT}  ({N_OUT} stations, 3 columns)")
    print(f"  pooled CST residual  upper {100*r_up:.3f} %c   lower {100*r_lo:.3f} %c")
    print(f"  interior rejected    {100*np.mean([v['interior_fraction'] for v in per_section.values()]):.1f} % of scan points")
    print(f"  t/c max {100*thick.max():.2f} % at x/c {grid[thick.argmax()]:.3f}"
          f"   camber max {100*camber.max():+.2f} % at x/c {grid[camber.argmax()]:.3f}")
    print(f"  TE thickness {100*thick[-1]:.3f} %c")
    print(f"  wrote {out_json}")


if __name__ == "__main__":
    main()
