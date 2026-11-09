"""Decision 105: packages of changes that cut the cells, counted (not built) on the 20 reference wings at Re 3e5,
at every level. None is applied: each package changes decided rules, so the choice is Mike's.

    python scripts/cell_packages.py --types bwb flying_wing --tag a     # two halves, one process each
    python scripts/cell_packages.py --types cranked tapered --tag b
    python scripts/cell_packages.py --summary                           # -> data/studies/cell_packages.json

Packages (each builds on the one it names):
    P0  the decided rules (today)
    P1  lighter volume rules: outboard growth 1.30 (no outboard fine zone), 30 cells across the boundary layer at M
        (not VC: 17.8 at VC), the first cell behind the base = the wing's last chordwise cell (not s0)
    P2  P1 + a coarser wake band: 20 cells across the fan at M (not 40), streamwise cell up to 8 x the band cell (not 4)
    P3  P2 + the tip cap not wall-resolved: the last gap at the tip 10 s0 (not 2 s0; Stage 2 law 9/10), which is also
        the first gap past the tip
    P4  P2 + the surface transition band off (Stage 2 option, decision 81)
    P5  P2 + both (P3 and P4)
    P6  P5 + the far field at 40 c (not 80; the Stage 4 ladder would be 20 / 40 / 80) + 30 boundary-layer cells at F
Rows go to data/studies/cell_packages_<tag>.jsonl (one per wing; --resume skips the wings already there).
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import yaml

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent))

from cfdauto.mesh.surface import build_family, wing_from_set     # noqa: E402
from cfdauto.paths import STAGE2                                 # noqa: E402
from cfdauto.volume.laws import CONFIG                           # noqa: E402
from cfdauto.volume.volume import count_volume                   # noqa: E402

TYPES = ("bwb", "flying_wing", "cranked", "tapered")
LEVELS = ("VC", "C", "M", "F")
RE = 3e5
OUT = HERE / "data" / "studies"

LIGHT = {("outboard", "growth", "value"): 1.30, ("wall", "bl_cells", "at"): "M", ("wake", "first_cell"): "te_cell"}
BAND = {("wake", "band", "fan_cells", "value"): 20, ("wake", "band", "max_aspect"): 8.0}
TIP = {("span", "tip_gap_in_s0"): 10.0}
PACKAGES = {
    "P0": {"label": "the decided rules", "volume": {}, "surface": {}, "band": True},
    "P1": {"label": "lighter volume rules", "volume": LIGHT, "surface": {}, "band": True},
    "P2": {"label": "P1 + a coarser wake band", "volume": LIGHT | BAND, "surface": {}, "band": True},
    "P3": {"label": "P2 + the tip cap not wall-resolved (tip gap 10 s0)", "volume": LIGHT | BAND, "surface": TIP,
           "band": True},
    "P4": {"label": "P2 + the surface band off", "volume": LIGHT | BAND, "surface": {}, "band": False},
    "P5": {"label": "P2 + tip gap 10 s0 + the surface band off", "volume": LIGHT | BAND, "surface": TIP, "band": False},
    "P6": {"label": "P5 + far field 40 c + 30 boundary-layer cells at F", "surface": TIP, "band": False,
           "volume": LIGHT | BAND | {("far", "distance_c"): 40.0, ("wall", "bl_cells", "at"): "F"}},
}


def variant(path: Path, changes: dict, folder: Path, name: str) -> Path:
    """A copy of a rules YAML with some keys changed (comments are not kept: it is a scratch file)."""
    raw = yaml.safe_load(Path(path).read_text())
    raw = copy.deepcopy(raw)
    for keys, value in changes.items():
        d = raw
        for k in keys[:-1]:
            d = d[k]
        if keys[-1] not in d and keys != ("wake", "first_cell"):
            raise KeyError(f"{'.'.join(keys)} is not in {path.name}")
        d[keys[-1]] = value
    out = folder / f"{name}.yaml"
    out.write_text(yaml.safe_dump(raw, sort_keys=False))
    return out


def count(a) -> None:
    tmp = Path(tempfile.mkdtemp())
    surface_base = STAGE2 / "configs" / "surface.yaml"
    vcfg = {p: variant(Path(CONFIG), d["volume"], tmp, f"volume_{p}") for p, d in PACKAGES.items()}
    scfg = {False: None, True: variant(surface_base, TIP, tmp, "surface_tip10")}
    out = OUT / f"cell_packages_{a.tag}.jsonl"
    done = set()
    if a.resume and out.exists():
        done = {(r["type"], r["index"]) for r in map(json.loads, out.read_text().splitlines())}
    f = open(out, "a")
    for t in a.types:
        for i in range(5):
            if (t, i) in done:
                continue
            t0 = time.time()
            w = wing_from_set(t, "reference", i)
            fams = {}
            for band in (True, False):
                for tip in (False, True):
                    fams[(band, tip)] = build_family(w.loft, RE, levels=LEVELS, config=scfg[tip], band=band)
            row = {"type": t, "index": i, "hash8": w.input_hash[:8], "re": RE, "packages": {}}
            for p, d in PACKAGES.items():
                fam = fams[(d["band"], bool(d["surface"]))]
                row["packages"][p] = {lev: count_volume(fam[lev], lev, RE, vcfg[p]) for lev in LEVELS}
            row["seconds"] = round(time.time() - t0, 1)
            f.write(json.dumps(row) + "\n")
            f.flush()
            print(t, i, {p: f"{v['F']['cells'] / 1e6:.1f}" for p, v in row["packages"].items()}, row["seconds"], "s",
                  flush=True)
    f.close()


def summary() -> dict:
    rows = [json.loads(l) for p in sorted(OUT.glob("cell_packages_*.jsonl")) for l in p.read_text().splitlines()]
    s = {"wings": len(rows), "re": RE, "packages": {}}
    for p, d in PACKAGES.items():
        e = {"label": d["label"], "band": d["band"], "volume": {".".join(k): v for k, v in d["volume"].items()},
             "surface": {".".join(k): v for k, v in d["surface"].items()}, "levels": {}}
        for lev in LEVELS:
            c = np.array([r["packages"][p][lev]["cells"] for r in rows], float)
            b = np.array([r["packages"]["P0"][lev]["cells"] for r in rows], float)
            e["levels"][lev] = {"median": float(np.median(c)), "min": float(c.min()), "max": float(c.max()),
                                "vs_P0_median": float(np.median(c / b)),
                                "ram_gib_median": 1.51 + 9.46 * float(np.median(c)) / 1e6,
                                "fit_16GB": int(np.sum(c <= 1.2e6)), "fit_52GB": int(np.sum(c <= 5.0e6))}
            for k in ("n_layers", "n_wake", "n_c", "n_span", "n_out"):
                e["levels"][lev][k] = float(np.median([r["packages"][p][lev][k] for r in rows]))
        s["packages"][p] = e
    (OUT / "cell_packages.json").write_text(json.dumps(s, indent=1))
    return s


REOPENS = {"P0": "—", "P1": "law 12 (outboard growth), law 14 anchor (30 cells at M), decision 90 (base y⁺)",
           "P2": "+ decision 87 (the wake band)", "P3": "+ the frozen surface: Stage 2 law 9/10 (tip gap), cap y⁺ ≈ 10 at VC",
           "P4": "+ decision 81 (the surface band on for every run)", "P5": "+ both Stage 2 changes",
           "P6": "+ law 15 (far field) and the 30-cell anchor at F"}


def markdown(s: dict) -> str:
    """The packages as one markdown table (median cells per level; F's largest; F against today; VC's RAM and fit)."""
    n = s["wings"]
    out = ["| Package | Reopens | VC | C | M | F | F largest | F / today | VC: ADflow RAM; fit 16 GB |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for p, e in s["packages"].items():
        L = e["levels"]
        out.append(f"| **{p}** {e['label']} | {REOPENS[p]} | " + " | ".join(f"{L[lev]['median'] / 1e6:.2f} M" for lev in LEVELS)
                   + f" | {L['F']['max'] / 1e6:.1f} M | {L['F']['vs_P0_median']:.2f} | {L['VC']['ram_gib_median']:.0f} GiB; "
                   f"{L['VC']['fit_16GB']} of {n} |")
    out.append("")
    out.append("Counts behind it (median at VC): " + "; ".join(
        f"{p} {e['levels']['VC']['n_layers']:.0f} layers, {e['levels']['VC']['n_wake']:.0f} wake nodes, "
        f"{e['levels']['VC']['n_c']:.0f} C-line nodes, {e['levels']['VC']['n_span']:.0f} + {e['levels']['VC']['n_out']:.0f} stations"
        for p, e in s["packages"].items()) + ".")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--types", nargs="+", default=list(TYPES))
    ap.add_argument("--tag", default="all")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    if a.summary:
        s = summary()
        (OUT / "cell_packages.md").write_text(markdown(s) + "\n")
        for p, e in s["packages"].items():
            print(p, e["label"], {lev: f"{v['median'] / 1e6:.2f} M ({v['vs_P0_median']:.2f})" for lev, v in e["levels"].items()})
        return
    count(a)


if __name__ == "__main__":
    main()
