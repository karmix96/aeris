"""Each design's neutral point, and the centre-of-gravity range it allows.

AUDIT_2026-09-10.md next step 12. Every S8 run takes moments about x = 0.40 m,
the CG in configs/mass/baseline_uav.yaml -- the project's only mass model, one
CG for every design. So each "stable / unstable" verdict the campaign printed is
a verdict for a design whose CG sits at 0.40 m, and a design with a different
planform has no reason to put it there.

No per-design mass model exists, and this does not invent one. It reports what
the aerodynamics settles on its own: the neutral point, and the aft-most CG at
which each design keeps a 5 % and a 10 % static margin. A mass model settles
stability later by comparing its CG against those limits.

    python cg_limits.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
ROWS = HERE / "data/dataset/rows.json"
PILOT = HERE / "runs/s8_pilot"
#: the CFD moment reference and chordRef, identical for every design
X_REF, C_REF = 0.40, 0.9
MARGINS = (0.05, 0.10)


def avl_lines(index: int) -> list[str]:
    path = PILOT / f"g{index}/avl/alpha_0/airplane.avl"
    return [line.split("!")[0].strip() for line in path.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith(("#", "!"))]


def sections(index: int) -> list[dict]:
    """SECTION rows of the AVL geometry, with their AFILE, sorted root to tip."""
    lines, out = avl_lines(index), []
    for i, line in enumerate(lines):
        key = line.upper()
        if key.startswith("SECTION"):
            values = [float(v) for v in lines[i + 1].split()[:5]]
            xle, yle, zle, chord = values[:4]
            out.append({"x_le": xle, "y_le": yle, "z_le": zle, "chord": chord,
                        # incidence, which carries the twist
                        "ainc": values[4] if len(values) > 4 else 0.0,
                        "afile": None})
        elif key.startswith("AFIL") and out:  # AVL accepts AFIL and AFILE
            out[-1]["afile"] = lines[i + 1]
    return sorted(out, key=lambda s: s["y_le"])


def planform(index: int) -> dict:
    """Reference quantities and MAC from the AVL geometry -- the loft the mesh uses."""
    s_ref, c_ref, b_ref = (float(v) for v in avl_lines(index)[3].split()[:3])
    sec = sections(index)
    y, x, c = (np.array([s[k] for s in sec]) for k in ("y_le", "x_le", "chord"))
    dy = np.diff(y)
    c1, c2, x1, x2 = c[:-1], c[1:], x[:-1], x[1:]
    area = np.sum(dy * (c1 + c2) / 2)
    # exact for chord and leading edge linear between sections
    c_sq = np.sum(dy * (c1 ** 2 + c1 * c2 + c2 ** 2) / 3)
    c_x = np.sum(dy * (2 * c1 * x1 + c1 * x2 + c2 * x1 + 2 * c2 * x2) / 6)
    return {"avl_s_ref_m2": s_ref, "avl_c_ref_m": c_ref, "avl_b_ref_m": b_ref,
            "half_area_from_sections_m2": float(area),
            "mac_m": float(c_sq / area), "x_mac_le_m": float(c_x / area),
            "n_sections": int(len(y))}


def load_rows() -> list[dict]:
    rows = json.loads(ROWS.read_text())
    return rows if isinstance(rows, list) else rows["rows"]


def cfd_neutral_points(rows: list[dict]) -> dict:
    """x_np = x_ref - (dCMy/dCL) c_ref, per geometry and grid level.

    The slope is unchanged by the defect-23 rescale, which multiplies CL and CMy
    by the same factor.
    """
    groups: dict = {}
    for r in rows:
        if r.get("gate_verdict") != "ACCEPTED" or r.get("CMy") is None:
            continue
        if list(r.get("moment_ref_xyz", [X_REF]))[0] != X_REF or r.get("chord_ref") != C_REF:
            raise SystemExit(f"{r['run_name']}: moment reference or chord is not "
                             f"{X_REF} m / {C_REF} m; the formula below would be wrong")
        groups.setdefault((r["geometry_index"], r["grid_level"]), []).append(r)
    out: dict = {}
    for (index, level), rs in sorted(groups.items()):
        if len(rs) < 3:
            continue
        cl = np.array([r["CL"] for r in rs])
        cm = np.array([r["CMy"] for r in rs])
        slope, intercept = np.polyfit(cl, cm, 1)
        resid = cm - (slope * cl + intercept)
        out.setdefault(index, {})[level] = {
            "x_np_m": float(X_REF - slope * C_REF), "dcmy_dcl": float(slope),
            "alphas": sorted(r["alpha_deg"] for r in rs),
            "fit_rms_cmy": float(np.sqrt(np.mean(resid ** 2)))}
    return out


def avl_neutral_point(index: int) -> dict:
    sweep = json.loads((PILOT / f"g{index}/avl/avl_sweep.json").read_text())
    x = [p["raw"]["x_np"] for p in sweep if p.get("raw", {}).get("x_np") is not None]
    return {"x_np_m": float(np.mean(x)), "spread_over_alpha_m": float(np.ptp(x)),
            "n_alphas": len(x)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path,
                    default=HERE / "reports/s8_cg_limits.json")
    args = ap.parse_args()

    nps = cfd_neutral_points(load_rows())
    designs = {}
    print(f"{'geom':>5}{'MAC m':>8}{'x_np CFD':>10}{'x_np AVL':>10}{'np %MAC':>9}"
          f"{'SM@0.40':>9}{'aft CG 5%':>11}{'aft CG 10%':>11}")
    for index, by_level in sorted(nps.items()):
        pf = planform(index)
        level = "gci_M" if "gci_M" in by_level else "gci_C"
        x_np = by_level[level]["x_np_m"]
        mac, x_le = pf["mac_m"], pf["x_mac_le_m"]
        avl = avl_neutral_point(index)
        entry = {"planform": pf, "cfd_neutral_point": by_level,
                 "neutral_point_level_used": level, "x_np_m": x_np,
                 "neutral_point_pct_mac": 100 * (x_np - x_le) / mac,
                 "avl_neutral_point": avl, "x_np_cfd_minus_avl_m": x_np - avl["x_np_m"],
                 "static_margin_if_cg_at_0p40_pct_mac": 100 * (x_np - X_REF) / mac,
                 "verdict_if_cg_at_0p40": "stable" if x_np > X_REF else "unstable",
                 "aft_cg_limit_m": {f"static_margin_{int(100 * m)}pct":
                                    x_np - m * mac for m in MARGINS}}
        designs[str(index)] = entry
        lim = entry["aft_cg_limit_m"]
        print(f"{index:>5}{mac:>8.4f}{x_np:>10.4f}{avl['x_np_m']:>10.4f}"
              f"{entry['neutral_point_pct_mac']:>8.1f}%"
              f"{entry['static_margin_if_cg_at_0p40_pct_mac']:>8.1f}%"
              f"{lim['static_margin_5pct']:>11.4f}{lim['static_margin_10pct']:>11.4f}")

    unstable = sorted(int(k) for k, v in designs.items()
                      if v["verdict_if_cg_at_0p40"] == "unstable")
    offsets = [v["x_np_cfd_minus_avl_m"] for v in designs.values()]
    report = {
        "schema": "aeris.s8.cg_limits.v1",
        "question": "AUDIT_2026-09-10 next step 12: stability needs each design's CG",
        "finding": ("the project has one mass model (configs/mass/baseline_uav.yaml, "
                    "x_cg 0.40 m for every design); no per-design CG exists, so "
                    "stability is reported as a CG limit per design, not a verdict"),
        "formula": "x_np = x_ref - (dCMy/dCL) * c_ref;  aft CG = x_np - SM * MAC",
        "moment_reference_m": X_REF, "cfd_chord_ref_m": C_REF,
        "designs": designs,
        "summary": {
            "unstable_if_cg_at_0p40": unstable,
            "x_np_range_m": [min(v["x_np_m"] for v in designs.values()),
                             max(v["x_np_m"] for v in designs.values())],
            "cfd_minus_avl_neutral_point_m": {"mean": float(np.mean(offsets)),
                                              "min": float(np.min(offsets)),
                                              "max": float(np.max(offsets))},
        },
    }
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\n  unstable if the CG were at 0.40 m: {unstable or 'none'}")
    print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
