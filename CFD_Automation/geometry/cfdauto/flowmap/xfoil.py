"""XFOIL in batch: one section, one Re, one angle, free or tripped transition. Results are cached.

XFOIL (Drela 1989) solves the 2-D section with a coupled boundary layer and e^N transition
(N_crit 9 = a quiet free stream, as in flight). Tripped = transition forced at 1 % chord on both
surfaces: what a fully turbulent RANS model assumes.

The Debian xfoil build traps floating-point exceptions; a small preload library switches the trap
off (the same arithmetic as an untrapped build).
"""

from __future__ import annotations

import hashlib
import math
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

CACHE = Path(__file__).resolve().parents[2] / "data" / "xfoil_cache"
NCRIT = 9.0
XTRIP = 0.01
TIMEOUT_S = 40


def available() -> bool:
    return shutil.which("xfoil") is not None


def _nofpe(work: Path) -> str:
    so = work / "nofpe.so"
    if not so.exists():
        (work / "nofpe.c").write_text("void _gfortran_set_fpe(int v){(void)v;}\n")
        subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(so), str(work / "nofpe.c")], check=True,
                       capture_output=True)
    return str(so)


def _key(points: np.ndarray, re_: float, alpha: float, tripped: bool) -> str:
    h = hashlib.sha1(np.round(points, 6).tobytes())
    h.update(json.dumps([round(re_, -2), round(alpha, 3), tripped, NCRIT, XTRIP]).encode())
    return h.hexdigest()


def run(points: np.ndarray, re_: float, alpha: float, tripped: bool = False) -> dict | None:
    """points: Selig order (upper TE -> LE -> lower TE), unit chord. Returns cl, cd, cdp, xtr_top,
    xtr_bot and the upper and lower skin friction (x, cf), or None when XFOIL does not converge."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = _key(points, re_, alpha, tripped)
    f = CACHE / f"{key}.json"
    if f.exists():
        d = json.loads(f.read_text())
        return d or None
    work = Path(tempfile.mkdtemp(prefix="xf_", dir="/tmp"))     # XFOIL limits path length
    try:
        dat, pol, dump = work / "a.dat", work / "a.pol", work / "a.dump"
        np.savetxt(dat, points, header="section", comments="", fmt="%.7f")
        trip = f"VPAR\nXTR {XTRIP} {XTRIP}\nN {NCRIT}\n\n" if tripped else f"VPAR\nN {NCRIT}\n\n"
        # march from 0 deg in 0.5 deg steps to just short of alpha, then the exact angle
        step = 0.5 if alpha >= 0 else -0.5
        near = math.trunc(alpha / 0.5) * 0.5
        march = f"ASEQ 0 {near:.3f} {step}\n" if abs(near) > 0 else "ALFA 0\n"
        cmd = (f"PLOP\nG\n\nLOAD {dat}\n\nPANE\nOPER\nVISC {re_:.0f}\nITER 250\n{trip}PACC\n{pol}\n\n"
               f"{march}ALFA {alpha:.4f}\nPACC\nDUMP {dump}\n\nQUIT\n")
        try:
            subprocess.run(["xfoil"], input=cmd, text=True, capture_output=True, timeout=TIMEOUT_S, cwd=work,
                           env=os.environ | {"LD_PRELOAD": _nofpe(work)})
        except subprocess.TimeoutExpired:
            pass
        out = None
        if pol.exists():
            rows = []
            for line in pol.read_text().splitlines():
                p = line.split()
                try:
                    rows.append([float(x) for x in p[:7]])
                except ValueError:
                    continue
            rows = [r for r in rows if len(r) == 7 and abs(r[0] - alpha) < 2e-3]
            if rows and dump.exists():
                al, cl, cd, cdp, cm, xt, xb = rows[-1]
                d = np.loadtxt(dump, comments="#", usecols=(1, 2, 6))
                n = len(points)
                body = d[:n]
                k = int(np.argmin(body[:, 0]))
                up, lo = body[: k + 1][::-1], body[k:]
                out = {"cl": cl, "cd": cd, "cdp": cdp, "cm": cm, "xtr_top": xt, "xtr_bot": xb,
                       "upper": {"x": up[:, 0].round(5).tolist(), "cf": up[:, 2].round(7).tolist()},
                       "lower": {"x": lo[:, 0].round(5).tolist(), "cf": lo[:, 2].round(7).tolist()}}
        f.write_text(json.dumps(out or {}))
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)


def bubbles(side: dict, xtr: float) -> list[tuple[float, float]]:
    """Regions with Cf < 0 (separated flow) on one surface: [(x_start, x_end)], ahead of the TE region."""
    x, cf = np.array(side["x"]), np.array(side["cf"])
    out, start = [], None
    for xi, c in zip(x, cf):
        if c < 0 and start is None:
            start = xi
        elif c >= 0 and start is not None:
            out.append((float(start), float(xi)))
            start = None
    if start is not None:
        out.append((float(start), float(x[-1])))
    return [(a, b) for a, b in out if b - a > 0.005]
