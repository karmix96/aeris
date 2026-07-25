"""Trailing-edge thickness study for the small BWB ISR UAV.

Question: our station airfoils (mh91/mh91/e374/nlf1015) have SHARP trailing edges,
but a real UAV TE cannot be razor-sharp (manufacturability) and a structured mesh
needs a finite blunt TE (meshability). How much can we blunt the TE before the
aerodynamics change meaningfully — at OUR airfoils and OUR Reynolds numbers?

Method (defensible, aircraft-specific):
  * Open each airfoil's TE to a gap t/c by a linear symmetric opening about the
    chord line (delta = ±(t/2)·x), the standard blunt-TE construction — sharp LE
    preserved, camber preserved, gap = t at x/c=1. This matches how the AERIS
    mesh/CAD open the TE (minimum_te_thickness_fraction).
  * Evaluate with NeuralFoil (XFoil-trained) via get_aero_from_coordinates at the
    operational Reynolds numbers (tip / MAC / root) over an alpha sweep.
  * Report, per airfoil × Re: ΔCd at a fixed operating CL, ΔCL_max, ΔCm0 vs the
    sharp baseline, for TE gaps 0 / 0.25 / 0.5 / 1.0 / 2.0 %c.

Literature anchors (base drag of a blunt TE): Hoerner (Fluid-Dynamic Drag, 1965)
and Standish & van Dam (2003, blunt/flatback airfoils) — base drag grows roughly
linearly with TE thickness; below ~0.5%c the penalty is small and lift/moment are
essentially unaffected. This study quantifies that for our specific case.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

TE_FRACTIONS = [0.0, 0.0025, 0.005, 0.01, 0.02]
_ALPHA = np.linspace(-6.0, 14.0, 21)


def _load_airfoil(name: str) -> np.ndarray:
    import glob
    f = glob.glob(f"data/airfoil_database/{name}.dat")[0]
    pts = []
    for line in open(f):
        p = line.split()
        if len(p) == 2:
            try:
                pts.append((float(p[0]), float(p[1])))
            except ValueError:
                pass
    return np.asarray(pts, dtype=float)


def blunt_te(coords: np.ndarray, te_c: float) -> np.ndarray:
    """Open the TE to gap `te_c` (fraction of chord) by a linear symmetric opening.

    Selig loop: TE(top) -> LE -> TE(bottom). Points on the upper branch move +x·t/2,
    lower branch -x·t/2, so the gap at x/c=1 becomes te_c; LE (x=0) is unchanged.
    """
    if te_c <= 0:
        return coords.copy()
    c = coords.copy()
    le_idx = int(np.argmin(c[:, 0]))
    out = c.copy()
    # upper branch = indices [0..le_idx], lower = [le_idx..end]
    out[: le_idx + 1, 1] += 0.5 * te_c * c[: le_idx + 1, 0]
    out[le_idx:, 1] -= 0.5 * te_c * c[le_idx:, 0]
    return out


def _polar(coords: np.ndarray, re: float, model_size: str = "large") -> dict:
    import neuralfoil as nf
    aero = nf.get_aero_from_coordinates(
        coordinates=coords, alpha=_ALPHA, Re=np.full(len(_ALPHA), re),
        n_crit=9.0, model_size=model_size,
    )
    cl = np.asarray(aero["CL"], float)
    cd = np.asarray(aero["CD"], float)
    cm = np.asarray(aero["CM"], float)
    ok = np.isfinite(cl) & np.isfinite(cd) & (cd > 0)
    return {"alpha": _ALPHA[ok], "cl": cl[ok], "cd": cd[ok], "cm": cm[ok]}


def _cd_at_cl(pol: dict, cl_target: float) -> float:
    cl, cd = pol["cl"], pol["cd"]
    if len(cl) < 3 or cl_target < cl.min() or cl_target > cl.max():
        return float("nan")
    order = np.argsort(cl)
    return float(np.interp(cl_target, cl[order], cd[order]))


def run(airfoils: list[str], res: dict[str, float], cl_op: float) -> dict:
    results = {}
    for name in airfoils:
        base = _load_airfoil(name)
        results[name] = {}
        for re_label, re in res.items():
            base_pol = _polar(blunt_te(base, 0.0), re)
            cd0 = _cd_at_cl(base_pol, cl_op)
            clmax0 = float(np.max(base_pol["cl"])) if len(base_pol["cl"]) else float("nan")
            cm0_0 = float(np.interp(0.0, base_pol["alpha"], base_pol["cm"]))
            rows = []
            for te in TE_FRACTIONS:
                pol = _polar(blunt_te(base, te), re)
                cd = _cd_at_cl(pol, cl_op)
                clmax = float(np.max(pol["cl"])) if len(pol["cl"]) else float("nan")
                cm0 = float(np.interp(0.0, pol["alpha"], pol["cm"]))
                rows.append({
                    "te_pct_c": te * 100,
                    "cd": cd,
                    "d_cd_counts": (cd - cd0) * 1e4 if np.isfinite(cd) and np.isfinite(cd0) else float("nan"),
                    "d_cd_pct": (cd - cd0) / cd0 * 100 if np.isfinite(cd) and cd0 else float("nan"),
                    "cl_max": clmax,
                    "d_cl_max_pct": (clmax - clmax0) / clmax0 * 100 if clmax0 else float("nan"),
                    "cm0": cm0,
                    "d_cm0": cm0 - cm0_0,
                })
            results[name][re_label] = {"re": re, "cd0": cd0, "rows": rows}
    return results


def _fmt_md(d: dict, meta: dict) -> str:
    L = [
        "# Trailing-edge thickness — aerodynamic sensitivity (NeuralFoil)",
        "",
        f"- generated: {meta['generated_utc']}",
        f"- airfoils: {', '.join(meta['airfoils'])}",
        f"- Re: {meta['res']}  ·  operating CL: {meta['cl_op']}  ·  alpha sweep "
        f"{_ALPHA.min():.0f}..{_ALPHA.max():.0f} deg",
        "",
        "ΔCd in **drag counts** (1 count = 1e-4) at the operating CL, vs the sharp "
        "(0%c) TE; ΔCL_max and ΔCm0 vs sharp.",
        "",
    ]
    for name, byre in d.items():
        L.append(f"## {name}")
        L.append("")
        for re_label, blk in byre.items():
            L.append(f"### Re = {blk['re']:.2e} ({re_label})  ·  Cd(sharp) = {blk['cd0']:.5f}")
            L.append("")
            L.append("| TE %c | Cd | ΔCd (counts) | ΔCd % | CL_max | ΔCL_max % | Cm0 | ΔCm0 |")
            L.append("|---|---|---|---|---|---|---|---|")
            for r in blk["rows"]:
                L.append(
                    f"| {r['te_pct_c']:.2f} | {r['cd']:.5f} | {r['d_cd_counts']:+.1f} "
                    f"| {r['d_cd_pct']:+.2f} | {r['cl_max']:.3f} | {r['d_cl_max_pct']:+.2f} "
                    f"| {r['cm0']:+.4f} | {r['d_cm0']:+.4f} |"
                )
            L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--airfoils", default="mh91,e374,nlf1015")
    ap.add_argument("--report-dir", type=Path, default=None)
    args = ap.parse_args()

    airfoils = [a.strip() for a in args.airfoils.split(",") if a.strip()]
    res = {"tip": 1.85e5, "MAC": 7.7e5, "root": 1.8e6}
    cl_op = 0.4
    d = run(airfoils, res, cl_op)
    meta = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "airfoils": airfoils, "res": res, "cl_op": cl_op,
        "te_fractions_pct": [t * 100 for t in TE_FRACTIONS],
    }
    md = _fmt_md(d, meta)
    print(md)
    if args.report_dir is not None:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        (args.report_dir / "te_thickness_aero.json").write_text(
            json.dumps({"meta": meta, "results": d}, indent=2), encoding="utf-8")
        (args.report_dir / "te_thickness_aero.md").write_text(md, encoding="utf-8")
        print(f"\n[written] {args.report_dir}/te_thickness_aero.{{json,md}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
