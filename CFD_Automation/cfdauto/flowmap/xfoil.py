"""XFOIL in batch: one section, one Re, one Mach, a sweep of angles, free or tripped transition.

XFOIL (Drela 1989) solves the 2-D section with a coupled boundary layer and e^N transition
(N_crit 9 = a quiet free stream, as in flight; Mach by the Karman-Tsien correction). Tripped =
transition forced at 1 % chord on both surfaces: what a fully turbulent RANS model assumes.

Robust sweeps. The Debian xfoil build traps floating-point exceptions; a small preload library
switches the trap off. Untrapped, a failing point can then loop on NaN forever (seen in TRCHEK2 with a
forced trip near the stagnation point at higher angles). So each session is watched: on a NaN, or no
output for a few seconds, the process is killed, the failing angle is skipped, and a new session
continues with the next angle. Only converged points (those XFOIL writes to its polar) are kept.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
from ..paths import STAGE1

CACHE = STAGE1 / "data" / "xfoil_cache"
NCRIT = 9.0
XTRIP = 0.01
POINT_IDLE_S = 6.0      # kill a session that prints nothing for this long
SESSION_MAX_S = 120.0
TE_REGION = 0.95        # Cf < 0 reaching beyond this x/c = trailing-edge separation, not a bubble


def available() -> bool:
    return shutil.which("xfoil") is not None


def _nofpe(work: Path) -> str:
    so = work / "nofpe.so"
    if not so.exists():
        (work / "nofpe.c").write_text("void _gfortran_set_fpe(int v){(void)v;}\n")
        subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(so), str(work / "nofpe.c")], check=True,
                       capture_output=True)
    return str(so)


# --------------------------------------------------------------------------------------------- parsing
def _read_polar(path: Path) -> dict[float, list[float]]:
    out = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        p = line.split()
        if len(p) < 7:
            continue
        try:
            v = [float(x) for x in p[:7]]
        except ValueError:
            continue
        out[round(v[0], 3)] = v
    return out


def _read_dump(path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    """Upper (LE -> TE) and lower (LE -> TE) surface rows (x, cf) from an XFOIL BL dump.
    Airfoil rows have 12 or more columns; wake rows have 8."""
    if not path.exists():
        return None
    rows = []
    for line in path.read_text().splitlines():
        if line.startswith("#"):
            continue
        p = line.split()
        if len(p) >= 12:
            try:
                rows.append((float(p[1]), float(p[6])))
            except ValueError:
                return None
    if len(rows) < 20:
        return None
    a = np.array(rows)
    k = int(np.argmin(a[:, 0]))
    return a[: k + 1][::-1], a[k:]


def _intervals(side: np.ndarray) -> list[tuple[float, float]]:
    x, cf = side[:, 0], side[:, 1]
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


def features(upper: np.ndarray, lower: np.ndarray) -> dict:
    """Bubbles (largest Cf < 0 region ahead of x/c 0.95) and trailing-edge separation per surface."""
    out = {}
    for name, side in (("u", upper), ("l", lower)):
        iv = _intervals(side)
        bub = [(a, b) for a, b in iv if b < TE_REGION]
        sep = [(a, b) for a, b in iv if b >= TE_REGION]
        if bub:
            a, b = max(bub, key=lambda t: t[1] - t[0])
            out |= {f"bub_{name}": 1.0, f"bub_{name}_s": a, f"bub_{name}_e": b}
        else:
            out |= {f"bub_{name}": 0.0, f"bub_{name}_s": np.nan, f"bub_{name}_e": np.nan}
        out |= {f"sep_{name}": 1.0 if sep else 0.0, f"sep_{name}_x": (min(a for a, _ in sep) if sep else np.nan)}
    return out


# --------------------------------------------------------------------------------------------- sweeps
def _watch(proc: subprocess.Popen) -> bool:
    """Read the process output; kill it on NaN, idleness or overall time. True when killed."""
    q: queue.Queue = queue.Queue()

    def reader():
        for chunk in iter(lambda: proc.stdout.read(512), ""):
            q.put(chunk)
        q.put(None)

    threading.Thread(target=reader, daemon=True).start()
    t0 = last = time.time()
    tail = ""
    while True:
        try:
            chunk = q.get(timeout=0.25)
        except queue.Empty:
            chunk = ""
        now = time.time()
        if chunk is None:
            proc.wait()
            return False
        if chunk:
            last = now
            tail = (tail + chunk)[-2000:]
            if "NaN" in tail:
                proc.kill(); proc.wait()
                return True
        if now - last > POINT_IDLE_S or now - t0 > SESSION_MAX_S:
            proc.kill(); proc.wait()
            return True


def sweep(points: np.ndarray, re_: float, alphas: list[float], tripped: bool = False, mach: float = 0.0,
          ncrit: float = NCRIT, keep_cf_at: float | None = None) -> dict[float, dict]:
    """Converged results at each angle of `alphas` (ordered, marched in that order).
    Each: cl, cd, cdp, cm, xtr_top, xtr_bot and the bubble / separation features."""
    work = Path(tempfile.mkdtemp(prefix="xs_", dir="/tmp"))     # XFOIL limits path length
    try:
        so = _nofpe(work)
        dat = work / "a.dat"
        np.savetxt(dat, points, header="section", comments="", fmt="%.7f")
        vpar = f"VPAR\nN {ncrit:g}\n" + (f"XTR {XTRIP} {XTRIP}\n" if tripped else "") + "\n"
        head = (f"PLOP\nG\n\nLOAD {dat}\n\nPANE\nOPER\nVISC {re_:.0f}\n" + (f"MACH {mach:.4f}\n" if mach > 0 else "")
                + f"ITER 150\n{vpar}")
        pending = [round(float(a), 3) for a in alphas]
        results: dict[float, dict] = {}
        n = 0
        while pending:
            n += 1
            pol = work / f"p{n}.pol"
            cmd = head + f"PACC\n{pol}\n\n"
            for i, a in enumerate(pending):
                cmd += f"ALFA {a:.3f}\nDUMP {work}/d{n}_{i}.txt\n"
            cmd += "PACC\n\nQUIT\n"
            proc = subprocess.Popen(["xfoil"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, cwd=work, env=os.environ | {"LD_PRELOAD": so})
            try:
                proc.stdin.write(cmd); proc.stdin.close()
            except BrokenPipeError:
                pass
            killed = _watch(proc)
            conv = _read_polar(pol)
            done = -1
            for i, a in enumerate(pending):
                f = work / f"d{n}_{i}.txt"
                if not f.exists():
                    break
                done = i
                if a in conv:
                    sides = _read_dump(f)
                    if sides is None:
                        continue
                    al, cl, cd, cdp, cm, xt, xb = conv[a]
                    r = {"cl": cl, "cd": cd, "cdp": cdp, "cm": cm, "xtr_top": xt, "xtr_bot": xb} | features(*sides)
                    if keep_cf_at is not None and abs(a - keep_cf_at) < 1e-3:
                        r["upper"] = {"x": sides[0][:, 0].round(5).tolist(), "cf": sides[0][:, 1].round(7).tolist()}
                        r["lower"] = {"x": sides[1][:, 0].round(5).tolist(), "cf": sides[1][:, 1].round(7).tolist()}
                    results[a] = r
            if not killed:
                break
            pending = pending[done + 2:]          # skip the angle that failed, continue after it
        return results
    finally:
        shutil.rmtree(work, ignore_errors=True)


def march(alpha: float, step: float = 0.5) -> list[float]:
    """Angles from 0 toward alpha in `step`, ending exactly at alpha."""
    n = int(math.floor(abs(alpha) / step + 1e-9))
    s = step if alpha >= 0 else -step
    seq = [round(k * s, 3) for k in range(n + 1)]
    if abs(seq[-1] - alpha) > 1e-6:
        seq.append(round(alpha, 4))
    return seq


def _key(points: np.ndarray, re_: float, alpha: float, tripped: bool, mach: float, ncrit: float) -> str:
    h = hashlib.sha1(np.round(points, 6).tobytes())
    h.update(json.dumps([round(re_, -2), round(alpha, 3), tripped, round(mach, 4), ncrit, XTRIP, 2]).encode())
    return h.hexdigest()


def run(points: np.ndarray, re_: float, alpha: float, tripped: bool = False, mach: float = 0.0,
        ncrit: float = NCRIT) -> dict | None:
    """One angle (marched from 0 deg), cached. Includes the skin friction for plotting."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{_key(points, re_, alpha, tripped, mach, ncrit)}.json"
    if f.exists():
        d = json.loads(f.read_text())
        return d or None
    res = sweep(points, re_, march(alpha), tripped, mach, ncrit, keep_cf_at=round(alpha, 3))
    out = res.get(round(alpha, 3)) or res.get(round(alpha, 4))
    f.write_text(json.dumps(out or {}, default=float))
    return out


def bubbles(side: dict, xtr: float | None = None) -> list[tuple[float, float]]:
    """Separated regions (Cf < 0) on one surface ahead of the trailing-edge region: [(x_start, x_end)]."""
    a = np.column_stack([side["x"], side["cf"]])
    return [(s, e) for s, e in _intervals(a) if e < TE_REGION]
