"""2-D size of the transition effect: XFOIL free transition (e^N, Ncrit 9) vs tripped at the nose.

    python scripts/xfoil_band.py      # needs xfoil on the PATH; writes docs/xfoil_band.json, xfoil_*.png

Why: the planned 3-D CFD (ADflow, SA) is turbulent from the leading edge. Running each suggested
section in XFOIL twice, once with free transition and once tripped at 1 % chord, shows in 2-D how much
that choice changes the drag and where laminar bubbles sit, at each study Re level. It is a proxy for
the model band, not the 3-D answer (no sweep, no crossflow, no 3-D relief).

The Debian xfoil build traps floating-point exceptions; a tiny preload library switches the trap off
(the same arithmetic as an untrapped build).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cfdauto.geometry.sections import load_airfoil  # noqa: E402

DOCS = ROOT / "docs"
SECTIONS = {"naca4415": "NACA 4415 (wings with a tail)", "mh61": "MH 61 (BWB outer wing)",
            "mh60": "MH 60 (flying wing)", "mh104": "MH 104 (BWB centre body)"}
RE = (1e5, 3e5, 1.5e6, 3e6)
ALPHAS = (0, 2, 4, 6, 8)
XTRIP = 0.01


def nofpe(work: Path) -> str:
    so = work / "nofpe.so"
    if not so.exists():
        (work / "nofpe.c").write_text("void _gfortran_set_fpe(int v){(void)v;}\n")
        subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(so), str(work / "nofpe.c")], check=True)
    return str(so)


def run(name: str, re_: float, tripped: bool, work: Path) -> dict:
    a = load_airfoil(name)
    dat = work / f"{name}.dat"
    np.savetxt(dat, a.selig(), header=name, comments="", fmt="%.7f")
    tag = f"{name}_{re_:.0e}_{'trip' if tripped else 'free'}"
    pol, dump = work / f"{tag}.pol", work / f"{tag}.dump"
    for f in (pol, dump):
        f.unlink(missing_ok=True)
    trip = f"VPAR\nXTR {XTRIP} {XTRIP}\n\n" if tripped else ""
    # polar 0..8 deg; then a fresh session marches 0 -> 4 deg for the skin-friction dump (a jump back
    # from 8 deg can leave the tripped solution unconverged)
    cmd = (f"PLOP\nG\n\nLOAD {dat}\n\nPANE\nOPER\nVISC {re_:.0f}\nITER 300\n{trip}PACC\n{pol}\n\n"
           f"ASEQ 0 8 1\nPACC\n\nQUIT\n")
    cmd2 = (f"PLOP\nG\n\nLOAD {dat}\n\nPANE\nOPER\nVISC {re_:.0f}\nITER 300\n{trip}"
            f"ASEQ 0 4 0.5\nDUMP {dump}\n\nQUIT\n")
    env = os.environ | {"LD_PRELOAD": nofpe(work)}
    for c in (cmd, cmd2):
        try:
            subprocess.run(["xfoil"], input=c, text=True, capture_output=True, timeout=120, cwd=work, env=env)
        except subprocess.TimeoutExpired:
            pass
    polar = {}
    if pol.exists():
        for line in pol.read_text().splitlines():
            p = line.split()
            try:
                al = float(p[0]); polar[round(al)] = {"cl": float(p[1]), "cd": float(p[2]), "cdp": float(p[3]),
                                                      "xtr_top": float(p[5]), "xtr_bot": float(p[6])}
            except (ValueError, IndexError):
                continue
    upper = None
    if dump.exists():
        d = np.loadtxt(dump, comments="#", usecols=(1, 2, 6))
        k = int(np.argmin(d[:, 0][: len(a.x) * 3]))      # leading edge: smallest x before the wake
        up = d[: k + 1][::-1]                             # upper surface, LE -> TE
        upper = {"x": up[:, 0].tolist(), "cf": up[:, 2].tolist()}
    return {"polar": {str(k): v for k, v in polar.items() if k in ALPHAS}, "upper_a4": upper}


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="xfoil_"))
    res = {}
    for name in SECTIONS:
        for re_ in RE:
            for tripped in (False, True):
                r = run(name, re_, tripped, work)
                res[f"{name}|{re_:.0e}|{'trip' if tripped else 'free'}"] = r
                cd = {a: round(v['cd'] * 1e4, 1) for a, v in r["polar"].items()}
                print(f"{name:9s} Re {re_:.0e} {'trip' if tripped else 'free'}  CD counts {cd}")
    (DOCS / "xfoil_band.json").write_text(json.dumps({"sections": SECTIONS, "re": RE, "alphas": ALPHAS,
                                                      "xtrip": XTRIP, "ncrit": 9, "runs": res}, indent=1))
    plots(res)


def re_label(x: float) -> str:
    e = int(np.floor(np.log10(x))); m = x / 10 ** e
    sup = str(e).translate(str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹"))
    return (f"{m:g} × 10{sup}" if m != 1 else f"10{sup}")


def plots(res: dict) -> None:
    import logging
    import matplotlib
    matplotlib.use("Agg")
    logging.getLogger("matplotlib").setLevel(logging.ERROR)
    import matplotlib.pyplot as plt
    ink, muted = "#1F2A33", "#6B7785"
    col = {"naca4415": "#0C5EA8", "mh61": "#2E8B57", "mh60": "#B07000", "mh104": "#7A3FA0"}
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": "#B8C0C8"})

    # 1. skin friction on the upper surface, alpha 4: free (solid) vs tripped (dashed)
    fig, axes = plt.subplots(1, 4, figsize=(13.5, 3.7), dpi=110, sharey=True)
    for ax, re_ in zip(axes, RE):
        for name in ("naca4415", "mh61"):
            for mode, ls in (("free", "-"), ("trip", "--")):
                u = res[f"{name}|{re_:.0e}|{mode}"]["upper_a4"]
                if not u:
                    continue
                x, cf = np.array(u["x"]), np.array(u["cf"])
                ax.plot(x, cf * 1e3, ls=ls, color=col[name], lw=1.5 if mode == "free" else 1.1,
                        label=f"{SECTIONS[name].split(' (')[0]}, {'free transition' if mode == 'free' else 'tripped at 1 %'}")
                if mode == "free":
                    neg = cf < 0
                    if neg.any():
                        ax.fill_between(x, cf * 1e3, 0, where=neg, color=col[name], alpha=0.25, lw=0)
                    xt = res[f"{name}|{re_:.0e}|free"]["polar"].get("4", {}).get("xtr_top")
                    if xt is not None:
                        ax.axvline(xt, color=col[name], lw=0.8, ls=":")
        ax.axhline(0, color=muted, lw=0.7)
        ax.set_title(f"Re = {re_label(re_)}", fontsize=10)
        ax.set_xlabel("x / c (upper surface)")
        ax.set_ylim(-1.5, 9)
        ax.grid(alpha=0.25)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0].set_ylabel("skin friction Cf × 1000")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=4, fontsize=8, frameon=False)
    fig.suptitle("Upper surface at 4°: laminar run, bubble (shaded, Cf < 0) and transition (dotted) vs fully turbulent", x=0.01,
                 ha="left", fontsize=10.5, color=ink)
    fig.tight_layout(rect=(0, 0.08, 1, 0.95))
    fig.savefig(DOCS / "xfoil_cf.png")
    plt.close(fig)

    # 2. plain drag comparison: real (free transition) vs fully turbulent, one panel per Re, alpha about 2 deg
    names = list(SECTIONS)
    short = {k: SECTIONS[k].split(" (")[0] for k in names}

    def pick(pol: dict) -> tuple[str, dict] | tuple[None, None]:
        for al in ("2", "0", "4"):
            if al in pol:
                return al, pol[al]
        return None, None

    fig, axes = plt.subplots(1, 4, figsize=(13.5, 3.9), dpi=110, sharey=True)
    for ax, re_ in zip(axes, RE):
        k = f"{re_:.0e}"
        ys = np.arange(len(names))
        for i, name in enumerate(names):
            af, f = pick(res[f"{name}|{k}|free"]["polar"])
            at, t = pick(res[f"{name}|{k}|trip"]["polar"])
            if not f or not t:
                continue
            ax.barh(i + 0.18, f["cd"] * 1e4, height=0.34, color=col[name], alpha=0.45)
            ax.barh(i - 0.18, t["cd"] * 1e4, height=0.34, color=col[name])
            pct = 100 * (t["cd"] / f["cd"] - 1)
            ax.text(t["cd"] * 1e4 + 3, i - 0.18, f"{pct:+.0f} %", va="center", fontsize=8.5, color=ink, fontweight="bold")
        ax.set_yticks(ys)
        ax.set_yticklabels([short[n] for n in names], fontsize=9)
        ax.invert_yaxis()
        ax.set_title(f"Re = {re_label(re_)}", fontsize=10)
        ax.set_xlabel("profile drag [counts]")
        ax.set_xlim(0, 290)
        ax.grid(axis="x", alpha=0.25)
        for s_ in ("top", "right"):
            ax.spines[s_].set_visible(False)
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color="#7A8794", alpha=0.45, label="real air: laminar at the nose, turns turbulent by itself (free transition)"),
                        Patch(color="#7A8794", label="what fully turbulent CFD assumes (turbulent from the nose)")],
               loc="lower center", ncol=2, fontsize=8.5, frameon=False)
    fig.suptitle("Drag of one airfoil section at about 2°: real flow vs fully turbulent CFD. The % is how much too high the CFD would be.",
                 x=0.01, ha="left", fontsize=10.5, color=ink)
    fig.tight_layout(rect=(0, 0.08, 1, 0.94))
    fig.savefig(DOCS / "xfoil_band.png")
    plt.close(fig)

    # 3. where the real flow turns turbulent (upper surface): a strip along the chord per section
    fig, axes = plt.subplots(1, 4, figsize=(13.5, 3.3), dpi=110, sharey=True)
    for ax, re_ in zip(axes, RE):
        for i, name in enumerate(names):
            p = pick(res[f"{name}|{re_:.0e}|free"]["polar"])[1]
            if not p:
                continue
            xt = 100 * p["xtr_top"]
            ax.barh(i, xt, left=0, height=0.55, color=col[name], alpha=0.30)
            ax.barh(i, 100 - xt, left=xt, height=0.55, color=col[name])
            ax.text(xt - 1.5, i, f"{xt:.0f} %", ha="right", va="center", fontsize=8, color=ink)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels([short[n] for n in names], fontsize=9)
        ax.invert_yaxis()
        ax.set_xlim(0, 100)
        ax.set_xlabel("% of chord (nose → trailing edge)")
        ax.set_title(f"Re = {re_label(re_)}", fontsize=10)
        for s_ in ("top", "right", "left"):
            ax.spines[s_].set_visible(False)
    fig.legend(handles=[Patch(color="#7A8794", alpha=0.30, label="laminar (smooth): low friction"),
                        Patch(color="#7A8794", label="turbulent: high friction")],
               loc="lower center", ncol=2, fontsize=8.5, frameon=False)
    fig.suptitle("Upper surface at about 2°: where the real flow turns turbulent. Higher Re → it turns turbulent earlier.",
                 x=0.01, ha="left", fontsize=10.5, color=ink)
    fig.tight_layout(rect=(0, 0.1, 1, 0.93))
    fig.savefig(DOCS / "xfoil_transition.png")
    plt.close(fig)


if __name__ == "__main__":
    if "--plots-only" in sys.argv:
        plots(json.loads((DOCS / "xfoil_band.json").read_text())["runs"])
    else:
        main()
