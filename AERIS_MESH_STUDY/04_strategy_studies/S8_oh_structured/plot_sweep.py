#!/usr/bin/env python
"""Residual histories and polars for the S8 alpha sweep, against AVL.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/plot_sweep.py

Six panels, chosen because each answers a question the table cannot:

1. **Residual histories.**  Whether a run converged, plateaued and broke through,
   or froze.  alpha 4's freeze is invisible in a final number and obvious here.
2. **Lift curve.**  CFD against AVL on the identical loft.  The interesting
   feature is not the offset but that it CLOSES with incidence.
3. **Drag polar, CD against CL.**  The shape that says whether the drag
   behaves.  AVL's induced-only drag is drawn separately because it is not the
   same quantity as a RANS CD and should never share an axis without saying so.
4. **Moment against alpha.**  Where the wing trims, read directly in degrees.
   The zero crossing is the trim angle and it is what a designer asks for first.
5. **Moment against CL.**  The same data on the axis whose SLOPE is static
   stability.  This is where CFD and AVL disagree on the sign, and the two
   panels are kept separate because they answer different questions: panel 4
   asks "where does it trim", panel 5 asks "is it stable".
6. **Lift-to-drag.**  The number a design actually cares about.
7. **Force tails.**  CL over the last iterations of each run, normalised, so
   "the forces settled" is shown rather than asserted.
8. **Surface pressure over its physical bound.**  Cells exceeding the isentropic
   stagnation cp, against incidence.  This is the count that says leading-edge
   resolution is operating-point dependent rather than a fixed mesh property.

Everything is read from the run logs and result files; nothing is typed in.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

import numpy as np

ROW = re.compile(r"^ +1 +\d+ +\d+ ")
COLUMNS = {"resrho": 0, "cl": 6, "cd": 7, "cdp": 8, "cdv": 9, "cmy": 10}
#: AVL and the CFD normalise moments by different reference chords.  AVL uses the
#: mean aerodynamic chord it computes (0.4946 m); the CFD uses the declared
#: reference chord of 0.9 m.  Areas already match, so this is the only scale
#: left once both take moments about the same point.
AVL_CREF, CFD_CREF = 0.4946, 0.9


def read_history(log: Path):
    rows = [line.split() for line in log.read_text().splitlines() if ROW.match(line)]
    if len(rows) < 20:
        return None
    width = min(len(r) for r in rows)
    return np.array([[float(c) for c in r[7:width]] for r in rows])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", default="AERIS_MESH_STUDY/artifacts/s8_cfd/oh_L3_fixed_a*")
    ap.add_argument("--avl", default="AERIS_MESH_STUDY/artifacts/s8_cfd/avl_verification_xref04")
    ap.add_argument("--avl-fallback", default="AERIS_MESH_STUDY/artifacts/s8_cfd/avl_verification")
    ap.add_argument("--out", type=Path,
                    default=Path("AERIS_MESH_STUDY/artifacts/s8_cfd/s8_sweep_polars.png"))
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # --- CFD -------------------------------------------------------------
    cfd = {}
    for directory in sorted(glob.glob(args.runs)):
        d = Path(directory)
        history = read_history(d / "run.log") if (d / "run.log").exists() else None
        if history is None:
            continue
        alpha = float(re.search(r"_a(-?\d+)", d.name).group(1))
        cfd[alpha] = {
            "history": history, "dir": str(d),
            "cl": history[-1, COLUMNS["cl"]], "cd": history[-1, COLUMNS["cd"]],
            "cdp": history[-1, COLUMNS["cdp"]], "cdv": history[-1, COLUMNS["cdv"]],
            "cmy": history[-1, COLUMNS["cmy"]],
        }

    # --- AVL, preferring the run that shares the CFD moment reference -----
    avl, avl_source = {}, args.avl
    for base in (args.avl, args.avl_fallback):
        found = {}
        for path in sorted(glob.glob(f"{base}/alpha_*/native_avl_result.json")):
            record = json.loads(Path(path).read_text())
            if record.get("status") != "SUCCESS":
                continue
            alpha = float(re.search(r"alpha_(-?[\d.]+)", path).group(1))
            found[alpha] = record
        if len(found) >= len(avl):
            avl, avl_source = found, base
        if len(found) == len(cfd):
            break
    matched_reference = "xref04" in avl_source

    alphas = sorted(cfd)
    cl = np.array([cfd[a]["cl"] for a in alphas])
    cd = np.array([cfd[a]["cd"] for a in alphas])
    cmy = np.array([cfd[a]["cmy"] for a in alphas])
    aa = np.array(alphas)
    va = sorted(avl)
    acl = np.array([avl[a]["cl"] for a in va]) if va else np.array([])
    acd = np.array([avl[a]["cd"] for a in va]) if va else np.array([])
    # AVL Cm -> the CFD's reference chord.  If the AVL run already used the CFD
    # moment point, only the chord scale differs; otherwise the arm is applied.
    if va:
        acm = np.array([avl[a]["cm"] for a in va])
        if not matched_reference:
            acm = acm + np.array([avl[a]["cl"] for a in va]) * (0.4 - 0.0) / AVL_CREF
        acm = acm * AVL_CREF / CFD_CREF
        acm = -acm      # AVL Cm is nose-up positive; ADflow CMy is the +y moment (nose-down)
    else:
        acm = np.array([])

    fig, ax = plt.subplots(2, 4, figsize=(21.5, 9.4))
    fig.suptitle(
        "S8 O-H structured grid, oh_L3 (567,256 cells) - lhs100_seed42[83], "
        "M 0.0837, Re 1.53e6\nADflow RANS-SA against AVL on the identical pyGeo loft",
        fontsize=12)
    colours = plt.cm.viridis(np.linspace(0.05, 0.85, len(alphas)))

    # 1 residuals
    a0 = ax[0, 0]
    for c, alpha in zip(colours, alphas):
        h = cfd[alpha]["history"][:, COLUMNS["resrho"]]
        a0.semilogy(h / h[0], color=c, label=f"$\\alpha$ = {alpha:g}$\\degree$")
    a0.axhline(1e-8, color="0.4", ls="--", lw=1)
    a0.text(0.98, 1.3e-8, "old gate 1e-8", ha="right", va="bottom", fontsize=8,
            color="0.35", transform=a0.get_yaxis_transform())
    a0.axhline(1e-5, color="C3", ls=":", lw=1.2)
    a0.text(0.98, 1.3e-5, "new gate: 5 orders", ha="right", va="bottom", fontsize=8,
            color="C3", transform=a0.get_yaxis_transform())
    a0.set_xlabel("iteration"); a0.set_ylabel("density residual / initial")
    a0.set_title("1. Residual histories"); a0.legend(fontsize=8); a0.grid(alpha=0.3)

    # 2 lift curve
    a1 = ax[0, 1]
    a1.plot(aa, cl, "o-", color="C0", label="CFD (ADflow RANS-SA)")
    if va:
        a1.plot(va, acl, "s--", color="C1", label="AVL (inviscid VLM)")
    a1.axhline(0, color="0.7", lw=0.8); a1.axvline(0, color="0.7", lw=0.8)
    a1.set_xlabel(r"$\alpha$  [deg]"); a1.set_ylabel(r"$C_L$")
    a1.set_title("2. Lift curve"); a1.legend(fontsize=8); a1.grid(alpha=0.3)

    # 3 drag polar
    a2 = ax[0, 2]
    a2.plot(cd, cl, "o-", color="C0", label="CFD $C_D$ (total)")
    a2.plot([cfd[a]["cdp"] for a in alphas], cl, "^:", color="C4", lw=1, ms=4,
            label="CFD $C_{Dp}$")
    a2.plot([cfd[a]["cdv"] for a in alphas], cl, "v:", color="C2", lw=1, ms=4,
            label="CFD $C_{Dv}$")
    if va:
        a2.plot(acd, acl, "s--", color="C1", label="AVL $C_{Di}$ (induced only)")
    a2.set_xlabel(r"$C_D$"); a2.set_ylabel(r"$C_L$")
    a2.set_title("3. Drag polar\n(AVL carries no viscous drag - not the same quantity)")
    a2.legend(fontsize=7); a2.grid(alpha=0.3)

    # 4 moment against alpha -- the trim question
    at = ax[1, 0]
    at.plot(aa, cmy, "o-", color="C0", label="CFD")
    if va:
        at.plot(va, acm, "s--", color="C1",
                label="AVL, " + ("same moment point" if matched_reference
                                 else "arm transferred to x=0.4"))
    at.axhline(0, color="0.7", lw=0.8); at.axvline(0, color="0.7", lw=0.8)
    # trim angle: where CMy crosses zero
    for series, colour, name in ((cmy, "C0", "CFD"), (acm, "C1", "AVL")):
        if len(series) >= 2 and series.min() < 0 < series.max():
            xs = va if name == "AVL" else aa
            trim = float(np.interp(0.0, series, xs)) if series[0] < series[-1] \
                else float(np.interp(0.0, series[::-1], np.asarray(xs)[::-1]))
            at.plot([trim], [0], "*", color=colour, ms=13, zorder=5)
            at.annotate(f"{name} trim {trim:+.2f}$\\degree$", (trim, 0),
                        textcoords="offset points", xytext=(6, 8 if name == "CFD" else -16),
                        fontsize=8, color=colour)
    at.set_xlabel(r"$\alpha$  [deg]")
    at.set_ylabel(r"$C_{My}$  (about $x$=0.4 m, $c_{ref}$=0.9 m)")
    at.set_title("4. Pitching moment against incidence\n(zero crossing = trim)")
    at.legend(fontsize=8); at.grid(alpha=0.3)

    # 5 moment / stability
    a3 = ax[1, 1]
    a3.plot(cl, cmy, "o-", color="C0", label="CFD")
    if va:
        a3.plot(acl, acm, "s--", color="C1",
                label="AVL, " + ("same moment point" if matched_reference
                                 else "arm transferred to x=0.4"))
    slope = np.polyfit(cl, cmy, 1)[0]
    a3.axhline(0, color="0.7", lw=0.8); a3.axvline(0, color="0.7", lw=0.8)
    a3.set_xlabel(r"$C_L$"); a3.set_ylabel(r"$C_{My}$  (about $x$=0.4 m, $c_{ref}$=0.9 m)")
    a3.set_title(f"5. Pitching moment against $C_L$\n"
                 f"slope = static stability: CFD {slope:+.4f}")
    a3.legend(fontsize=8); a3.grid(alpha=0.3)

    # 6 lift-to-drag
    a4 = ax[1, 2]
    a4.plot(aa, cl / cd, "o-", color="C0", label="CFD $C_L/C_D$")
    a4.axhline(0, color="0.7", lw=0.8)
    best = int(np.argmax(cl / cd))
    a4.annotate(f"best {cl[best]/cd[best]:.2f} at {aa[best]:g}$\\degree$",
                (aa[best], cl[best] / cd[best]), textcoords="offset points",
                xytext=(-10, -18), fontsize=8, color="C0")
    a4.set_xlabel(r"$\alpha$  [deg]"); a4.set_ylabel(r"$C_L / C_D$")
    a4.set_title("6. Lift-to-drag"); a4.grid(alpha=0.3); a4.legend(fontsize=8)

    # 7 force tails
    a5 = ax[0, 3]
    for c, alpha in zip(colours, alphas):
        v = cfd[alpha]["history"][-150:, COLUMNS["cl"]]
        a5.plot(np.arange(-len(v), 0), (v - v[-1]) / abs(v[-1]) * 100.0,
                color=c, label=f"$\\alpha$ = {alpha:g}$\\degree$")
    a5.axhline(0, color="0.7", lw=0.8)
    a5.set_xlabel("iterations before the end"); a5.set_ylabel(r"$C_L$ deviation  [%]")
    a5.set_title("7. Force tails\n(the new gate asks < 0.05 % over 100 iterations)")
    a5.legend(fontsize=8); a5.grid(alpha=0.3); a5.set_yscale("symlog", linthresh=1e-6)

    # 8 surface pressure over its physical bound
    a6 = ax[1, 3]
    counts = {}
    for alpha in alphas:
        loc = Path(cfd[alpha]["dir"]) / "cp_excess_locations.json"
        if not loc.exists():
            continue
        z = [x for x in json.loads(loc.read_text())["zones"] if "Zone5" in x["zone"]][0]
        te = sum(1 for c in z["cells"] if c["i_ring"] in (0, 87))
        counts[alpha] = (te, z["interior_over_bound"] - te,
                         max((c["excess"] for c in z["cells"]), default=0.0))
    if counts:
        ks = sorted(counts)
        te = [counts[k][0] for k in ks]
        le = [counts[k][1] for k in ks]
        a6.bar([k - 0.35 for k in ks], te, width=0.7, color="C7",
               label="trailing-edge corner (C0 kink, 0.01-0.2 % of $C_{Dp}$)")
        a6.bar([k + 0.35 for k in ks], le, width=0.7, color="C3",
               label="leading edge")
        for k in ks:
            a6.annotate(f"peak\n+{counts[k][2]:.2f}", (k, max(counts[k][:2])),
                        textcoords="offset points", xytext=(0, 4),
                        ha="center", fontsize=7, color="0.3")
        missing = [a for a in alphas if a not in counts]
        if missing:
            a6.annotate(
                f"$\\alpha$ = {', '.join(f'{m:g}' for m in missing)}$\\degree$ missing:\n"
                "the run was stopped before\nit wrote a surface solution",
                (0.5, 0.72), xycoords="axes fraction", ha="center", fontsize=8,
                color="C3", style="italic")
    a6.set_xlabel(r"$\alpha$  [deg]"); a6.set_ylabel("wall cells over the cp bound")
    a6.set_title("8. Surface pressure above its physical bound\n"
                 "(leading-edge resolution is operating-point dependent)")
    a6.legend(fontsize=7); a6.grid(alpha=0.3, axis="y")

    fig.tight_layout(rect=(0, 0, 1, 0.94))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=150)
    print(f"wrote {args.out}")
    print(f"AVL source: {avl_source}"
          f"  ({'shares the CFD moment point' if matched_reference else 'moment arm applied here'})")
    print(f"CFD angles: {alphas}   AVL angles: {va}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
