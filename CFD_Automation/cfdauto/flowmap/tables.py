"""Section tables: XFOIL results on a grid of Re x Mach x angle, for every section the flow maps use.

    python -m cfdauto.flowmap.tables --build        # needs xfoil; about 2,400 sweeps, resumable
    python -m cfdauto.flowmap.tables --status

Why tables. A flow map needs XFOIL at every strip of every wing, angle and speed. Strip sections are the
station sections (or their ruled blends), so the same 2-D answers repeat. The tables hold them once:
any wing is then evaluated in milliseconds, without XFOIL, by interpolation:
  - trilinear in (log Re, Mach, angle), NaN-aware (a value needs at least half the interpolation weight
    on converged grid points, else it is NaN = not converged / beyond 2-D stall);
  - a strip between two different station sections takes the blend of the two parents' results
    (checked against direct XFOIL runs of 50/50 blends, see the analysis).

Grid: 10 sections, Re 1.5e4 - 6e6 (14 levels, about x1.6), Mach 0 / 0.1 / 0.2, angle -10 to 14 deg
in 0.5 deg; free transition (N_crit 9) and tripped at 1 % chord. Extra: free transition at N_crit 5 and
11 (Mach 0.1), and three 50/50 blends (Mach 0.1) for the checks.
"""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..geometry.params import GEOMETRY_ROOT
from ..geometry.sections import load_airfoil
from . import xfoil

SECTIONS = ("mh104", "mh61", "mh60", "mh45", "s5010", "naca4415", "naca4412", "sd7032", "la2573a", "e387")
BLENDS = (("mh104", "mh61"), ("naca4415", "naca4412"), ("mh60", "mh45"))
RE = np.array([1.5e4, 2.5e4, 4e4, 6e4, 1e5, 1.5e5, 2.5e5, 4e5, 6e5, 1e6, 1.5e6, 2.5e6, 4e6, 6e6])
MACH = np.array([0.0, 0.1, 0.2])
ALPHA = np.round(np.arange(-10.0, 14.0001, 0.5), 3)
UP = [a for a in ALPHA if a >= 0]
DOWN = [a for a in ALPHA[::-1] if a < 0]
NCRIT_VARIANTS = (5.0, 11.0)
FIELDS = ("cl", "cd", "cdp", "cm", "xtr_top", "xtr_bot", "bub_u", "bub_u_s", "bub_u_e", "bub_l", "bub_l_s",
          "bub_l_e", "sep_u", "sep_u_x", "sep_l", "sep_l_x")
TABLE_DIR = GEOMETRY_ROOT / "data" / "section_tables"
SWEEP_CACHE = GEOMETRY_ROOT / "data" / "section_cache"


def blend_name(a: str, b: str) -> str:
    return f"{a}+{b}@0.5"


def section_points(name: str) -> np.ndarray:
    if "+" in name:
        a, rest = name.split("+")
        b = rest.split("@")[0]
        return load_airfoil(a).blend(load_airfoil(b), 0.5).selig()
    return load_airfoil(name).selig()


def variants() -> list[tuple[str, str, float, tuple[float, ...]]]:
    """(section, mode, ncrit, machs) for every table."""
    out = [(s, m, 9.0, tuple(MACH)) for s in SECTIONS for m in ("free", "trip")]
    out += [(s, "free", n, (0.1,)) for s in SECTIONS for n in NCRIT_VARIANTS]
    out += [(blend_name(a, b), m, 9.0, (0.1,)) for a, b in BLENDS for m in ("free", "trip")]
    return out


def table_id(section: str, mode: str, ncrit: float) -> str:
    return f"{section}__{mode}__n{ncrit:g}"


def _job_file(section, mode, ncrit, mach, re_, direction) -> Path:
    return SWEEP_CACHE / f"{table_id(section, mode, ncrit)}__M{mach:g}__Re{re_:.3g}__{direction}.json"


def jobs() -> list[tuple]:
    return [(s, m, n, M, r, d) for s, m, n, machs in variants() for M in machs for r in RE for d in ("up", "down")]


def _run_job(job) -> int:
    s, mode, n, M, r, d = job
    f = _job_file(*job)
    if f.exists():
        return 0
    res = xfoil.sweep(section_points(s), float(r), UP if d == "up" else DOWN, tripped=(mode == "trip"), mach=float(M),
                      ncrit=n)
    f.write_text(json.dumps({str(k): v for k, v in res.items()}, default=float))
    return 1


def build(workers: int = 2) -> None:
    SWEEP_CACHE.mkdir(parents=True, exist_ok=True)
    todo = [j for j in jobs() if not _job_file(*j).exists()]
    print(f"{len(todo)} of {len(jobs())} sweeps to run")
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for k in ex.map(_run_job, todo):
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(todo)}", flush=True)
    assemble()


def assemble() -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    for s, mode, n, machs in variants():
        arr = {f: np.full((len(RE), len(machs), len(ALPHA)), np.nan) for f in FIELDS}
        missing = 0
        for j, M in enumerate(machs):
            for i, r in enumerate(RE):
                for d in ("up", "down"):
                    f = _job_file(s, mode, n, M, r, d)
                    if not f.exists():
                        missing += 1
                        continue
                    for a, v in json.loads(f.read_text()).items():
                        k = int(np.argmin(np.abs(ALPHA - float(a))))
                        if abs(ALPHA[k] - float(a)) > 1e-6:
                            continue
                        for fld in FIELDS:
                            x = v.get(fld)
                            arr[fld][i, j, k] = np.nan if x is None else float(x)
        if missing:
            print(f"  {table_id(s, mode, n)}: {missing} sweeps missing")
        filled = fill_single_gaps(arr)
        if filled:
            print(f"  {table_id(s, mode, n)}: {filled} single-angle gaps filled")
        np.savez_compressed(TABLE_DIR / f"{table_id(s, mode, n)}.npz", re=RE, mach=np.array(machs), alpha=ALPHA,
                            **{f: arr[f] for f in FIELDS})


FLAGS = ("bub_u", "bub_l", "sep_u", "sep_l")      # 0/1 fields: never averaged into 0.5


def fill_single_gaps(arr: dict) -> int:
    """Fill isolated one-angle XFOIL failures by linear interpolation between the two neighbouring
    angles (both converged). They are numerical: with a forced trip, XFOIL can fail at the one angle
    where the stagnation point crosses the trip. Two or more failures in a row stay NaN (no 2-D answer).
    A 0/1 flag (bubble, separation) is filled only where both neighbours agree; else it stays NaN."""
    cd = arr["cd"]
    hole = ~np.isfinite(cd[..., 1:-1]) & np.isfinite(cd[..., :-2]) & np.isfinite(cd[..., 2:])
    if not hole.any():
        return 0
    for f, v in arr.items():
        lo, hi = v[..., :-2], v[..., 2:]
        mid = np.where(lo == hi, lo, np.nan) if f in FLAGS else 0.5 * (lo + hi)
        inner = v[..., 1:-1]
        inner[hole] = mid[hole]
    return int(hole.sum())


# --------------------------------------------------------------------------------------------- lookup
@dataclass
class Table:
    name: str
    log_re: np.ndarray
    mach: np.ndarray
    alpha: np.ndarray
    data: dict

    def coverage(self) -> float:
        return float(np.mean(np.isfinite(self.data["cd"])))


_LOADED: dict[str, Table] = {}


def load(section: str, mode: str = "free", ncrit: float = 9.0) -> Table:
    key = table_id(section, mode, ncrit)
    if key not in _LOADED:
        f = TABLE_DIR / f"{key}.npz"
        if not f.exists():
            raise FileNotFoundError(f"no section table {f.name}: run python -m cfdauto.flowmap.tables --build")
        z = np.load(f)
        _LOADED[key] = Table(key, np.log10(z["re"]), z["mach"], z["alpha"], {k: z[k] for k in FIELDS})
    return _LOADED[key]


def has(section: str, mode: str = "free", ncrit: float = 9.0) -> bool:
    return (TABLE_DIR / f"{table_id(section, mode, ncrit)}.npz").exists()


def _axis(grid: np.ndarray, x: np.ndarray, clamp: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Lower index, upper weight, inside-flag for each x on a sorted grid."""
    if len(grid) == 1:
        z = np.zeros(x.shape, dtype=int)
        return z, np.zeros(x.shape), np.ones(x.shape, dtype=bool)
    inside = (x >= grid[0] - 1e-9) & (x <= grid[-1] + 1e-9)
    xc = np.clip(x, grid[0], grid[-1]) if clamp else x
    i = np.clip(np.searchsorted(grid, xc, side="right") - 1, 0, len(grid) - 2)
    w = (xc - grid[i]) / (grid[i + 1] - grid[i])
    return i, np.clip(w, 0.0, 1.0), inside


def interp(t: Table, re_: np.ndarray, mach: np.ndarray, alpha: np.ndarray, fields=FIELDS) -> dict:
    """NaN-aware trilinear lookup. Re and Mach are clamped to the grid (flags returned); angles outside
    the grid give NaN. A value needs >= half of the interpolation weight on converged points."""
    re_, mach, alpha = np.broadcast_arrays(np.asarray(re_, float), np.asarray(mach, float), np.asarray(alpha, float))
    ir, wr, in_r = _axis(t.log_re, np.log10(np.maximum(re_, 1.0)), True)
    im, wm, _ = _axis(t.mach, mach, True)
    ia, wa, in_a = _axis(t.alpha, alpha, False)
    out = {}
    nm = len(t.mach)
    for f in fields:
        v = t.data[f]
        num = np.zeros(re_.shape); den = np.zeros(re_.shape)
        for dr, fr in ((0, 1 - wr), (1, wr)):
            for dm, fm in (((0, 1 - wm), (1, wm)) if nm > 1 else ((0, np.ones(re_.shape)),)):
                for da, fa in ((0, 1 - wa), (1, wa)):
                    w = fr * fm * fa
                    val = v[np.minimum(ir + dr, len(t.log_re) - 1), np.minimum(im + dm, nm - 1),
                            np.minimum(ia + da, len(t.alpha) - 1)]
                    ok = np.isfinite(val) & (w > 0)
                    num += np.where(ok, w * np.nan_to_num(val), 0.0)
                    den += np.where(ok, w, 0.0)
        r = np.where(den >= 0.5 - 1e-9, num / np.maximum(den, 1e-12), np.nan)
        out[f] = np.where(in_a, r, np.nan)
    out["re_clamped"] = ~in_r
    return out


def lookup(sec_a: str, sec_b: str | None, s: np.ndarray, re_, mach, alpha, mode="free", ncrit=9.0, fields=FIELDS) -> dict:
    """A strip whose section is the ruled blend (1 - s) a + s b: the same blend of the two parents'
    results (NaN-aware, half-weight rule as in interp)."""
    ra = interp(load(sec_a, mode, ncrit), re_, mach, alpha, fields)
    if sec_b is None or sec_b == sec_a:
        return ra
    rb = interp(load(sec_b, mode, ncrit), re_, mach, alpha, fields)
    s = np.broadcast_to(np.asarray(s, float), ra[fields[0]].shape)
    out = {}
    for f in fields:
        a, b = ra[f], rb[f]
        wa, wb = np.where(np.isfinite(a), 1 - s, 0.0), np.where(np.isfinite(b), s, 0.0)
        den = wa + wb
        out[f] = np.where(den >= 0.5 - 1e-9, (wa * np.nan_to_num(a) + wb * np.nan_to_num(b)) / np.maximum(den, 1e-12), np.nan)
    out["re_clamped"] = ra["re_clamped"] | rb["re_clamped"]
    return out


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Build or inspect the section tables.")
    p.add_argument("--build", action="store_true")
    p.add_argument("--assemble", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2)))
    a = p.parse_args(argv)
    if a.build:
        build(a.workers)
    elif a.assemble:
        assemble()
    if a.status or not (a.build or a.assemble):
        n = sum(_job_file(*j).exists() for j in jobs())
        print(f"sweeps cached: {n} of {len(jobs())}")
        for s, mode, nc, _ in variants():
            if has(s, mode, nc):
                t = load(s, mode, nc)
                print(f"  {t.name:32s} converged {100 * t.coverage():.0f} % of the grid")


if __name__ == "__main__":
    main()
