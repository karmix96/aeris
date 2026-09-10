"""How much drag does the fully turbulent assumption add?

AUDIT_2026-09-10.md next step 11. ADflow has no transition model, so every S8
run is turbulent from the leading edge. At Re ~1.5e6 a smooth wing in calm air
keeps laminar flow over part of its chord, so the CFD overstates skin-friction
drag by an amount no grid refinement can reveal -- it is the model, not the grid.

This bounds that on the wings' own sections, with NeuralFoil (a model trained on
XFOIL): section drag at matched lift with free transition (n_crit 9, a quiet
wind tunnel or calm air) against transition forced at the leading edge (what the
CFD assumes). Root, mid-span and tip sections of all ten pilot wings, each at
its own chord Reynolds number.

    .venv/bin/python transition_sensitivity.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from cg_limits import PILOT, STUDY, sections

#: mission_authority_v1.yaml: Re 1.53e6 on a 0.9 m reference length
RE, RE_LENGTH = 1.53e6, 0.9
CL_TARGETS = (0.2, 0.4, 0.6)
ALPHAS = np.arange(-4.0, 10.01, 0.25)


def coordinates(path: Path) -> np.ndarray:
    rows = []
    for line in path.read_text().splitlines():
        try:
            x, y = (float(v) for v in line.split()[:2])
        except ValueError:
            continue  # a name line
        rows.append((x, y))
    return np.array(rows)


def polar(nf, coords: np.ndarray, re: float, xtr: float) -> dict:
    aero = nf.get_aero_from_coordinates(coordinates=coords, alpha=ALPHAS, Re=re,
                                        n_crit=9.0, xtr_upper=xtr, xtr_lower=xtr,
                                        model_size="xlarge")
    cl, cd = np.asarray(aero["CL"]), np.asarray(aero["CD"])
    top = int(np.argmax(cl))  # the attached branch only, up to maximum lift
    cl_b, cd_b = cl[: top + 1], cd[: top + 1]
    order = np.argsort(cl_b)
    return {"cd_at_cl": {f"{t:g}": (float(np.interp(t, cl_b[order], cd_b[order]))
                                    if cl_b.min() <= t <= cl_b.max() else None)
                         for t in CL_TARGETS},
            "confidence_mean": float(np.mean(aero["analysis_confidence"]))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=STUDY /
                    "05_s6_cfd_qualification/reports/s8_transition_sensitivity.json")
    args = ap.parse_args()
    import neuralfoil as nf

    report = {"schema": "aeris.s8.transition_sensitivity.v1", "tool": f"neuralfoil {nf.__version__}",
              "free": "n_crit 9, free transition", "turbulent": "transition forced at x/c 0",
              "sections": {}}
    ratios = []
    print(f"{'geom':>5}{'station':>9}{'chord':>7}{'Re':>10}   turbulent / free drag at cl "
          + " ".join(f"{t:g}" for t in CL_TARGETS))
    for gdir in sorted(PILOT.glob("g[0-9]*")):
        index = int(gdir.name[1:])
        sec = [s for s in sections(index) if s["afile"]]
        picks = {"root": sec[0], "mid": sec[len(sec) // 2], "tip": sec[-1]}
        for station, s in picks.items():
            af = Path(s["afile"])
            coords = coordinates(af if af.is_absolute() else gdir / "avl/alpha_0" / af)
            re = RE * s["chord"] / RE_LENGTH
            free, turb = polar(nf, coords, re, 1.0), polar(nf, coords, re, 0.0)
            ratio = {t: (turb["cd_at_cl"][t] / free["cd_at_cl"][t]
                         if turb["cd_at_cl"][t] and free["cd_at_cl"][t] else None)
                     for t in free["cd_at_cl"]}
            ratios += [r for r in ratio.values() if r]
            report["sections"][f"g{index}_{station}"] = {
                "chord_m": s["chord"], "reynolds": re, "free": free, "turbulent": turb,
                "turbulent_over_free": ratio}
            print(f"{index:>5}{station:>9}{s['chord']:>7.3f}{re:>10.3g}   "
                  + " ".join(f"{r:5.2f}" if r else "   - " for r in ratio.values()))
    r = np.array(ratios)
    report["summary"] = {"turbulent_over_free_section_drag": {
        "median": float(np.median(r)), "min": float(r.min()), "max": float(r.max()),
        "n": int(r.size)},
        "reading": ("if the real wing transitions freely, fully turbulent CFD "
                    "overstates its profile drag by this factor; induced drag is "
                    "unaffected")}
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\n  turbulent / free section drag: median {np.median(r):.2f}, "
          f"range {r.min():.2f}-{r.max():.2f}  ({r.size} points)\n  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
