"""Harvest every run, mesh level and measurement into one bundle for the app."""
import dataclasses, glob, json, os, re, sys
from pathlib import Path
sys.path[:0] = ["/home/mike_kara/aeris/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured",
               "/home/mike_kara/aeris", "/home/mike_kara/aeris/src"]
import strategy_s8 as S

HERE = Path("/home/mike_kara/aeris/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured")
os.chdir(HERE)

# ---- mesh levels, straight from the dataclass -------------------------------
fields = [f.name for f in dataclasses.fields(S.OHLevel)]
levels = {}
for name, lv in S.LEVELS.items():
    levels[name] = {f: getattr(lv, f) for f in fields}

def family(name):
    if name.startswith("gci3_"): return "3"
    if name.startswith("gci2_"): return "2"
    if name.startswith("gci"):   return "B/A"
    if name.startswith("m6"):    return "M6"
    if name.startswith(("oh_", "legacy_")): return "legacy"
    return "other"

# ---- every run on disk ------------------------------------------------------
runs = []
for rp in sorted(glob.glob("runs/**/result.json", recursive=True)):
    try:
        r = json.loads(Path(rp).read_text())
    except Exception:
        continue
    fn = {k.split("_")[-1]: v for k, v in (r.get("functions") or {}).items()}
    eff = r.get("solver_options_effective") or {}
    parts = Path(rp).parts
    grid = str(r.get("grid") or r.get("gridFile") or "")
    lvl = next((n for n in sorted(S.LEVELS, key=len, reverse=True)
                if n in grid or n in rp), None)
    geom = ("ribes" if "ribes" in rp.lower() else
            "m6" if "m6" in rp.lower() else "aeris")
    am = re.search(r"/a(-?[\d.]+)", rp)
    runs.append({
        "path": rp,
        "set": parts[1] if len(parts) > 1 else "",
        "level": lvl, "family": family(lvl or ""), "geometry": geom,
        "alpha": float(am.group(1)) if am else r.get("alpha_deg"),
        "cl": fn.get("cl"), "cd": fn.get("cd"), "cdp": fn.get("cdp"),
        "cdv": fn.get("cdv"), "cmy": fn.get("cmy"),
        "converged": r.get("converged"),
        "iterations": r.get("iterations_completed"),
        "residual": r.get("relative_residual"),
        "implausible": r.get("implausible_forces"),
        "nk": eff.get("useNKSolver"), "ank": eff.get("useANKSolver"),
        "turb": eff.get("turbulenceModel"), "evir": eff.get("eddyVisInfRatio"),
        "mach": eff.get("mach"), "re": eff.get("reynolds"),
        "cells": None,
    })

# ---- mesh summaries: cell counts and quality -------------------------------
meshes = {}
for sp in sorted(glob.glob("runs/**/*_summary.json", recursive=True)):
    try:
        d = json.loads(Path(sp).read_text())
    except Exception:
        continue
    blocks = d.get("blocks") or {}
    nm = Path(sp).name.replace("_summary.json", "")
    meshes[sp] = {
        "name": nm, "level": d.get("level") or nm, "set": Path(sp).parts[1],
        "cells": d.get("cells") or sum(b.get("cells", 0) for b in blocks.values()),
        "blocks": {k: {"shape": v.get("shape"), "cells": v.get("cells"),
                       "negative": v.get("negative_cells"),
                       "min_vol": v.get("min_cell_volume_m3"),
                       "max_vol": v.get("max_cell_volume_m3")}
                   for k, v in blocks.items()},
        "negative_cells": d.get("negative_cells_all_blocks"),
        "min_volume": d.get("min_cell_volume_all_blocks_m3"),
        "wall_orthogonality_median_deg": d.get("wall_orthogonality_median_deg"),
        "geometry": d.get("geometry"),
        "outboard": d.get("outboard"),
        "le_turning": d.get("le_turning") or d.get("surface_turning"),
        "wall_spacing": d.get("wall_spacing") or d.get("normal"),
    }
for r in runs:
    for mk, mv in meshes.items():
        if r["level"] and mv["level"] == r["level"] and mv["set"] == r["set"]:
            r["cells"] = mv["cells"]; break

# ---- reports: the measured findings ---------------------------------------
reports = {}
for rp in sorted(glob.glob("reports/*.json")):
    try:
        d = json.loads(Path(rp).read_text())
    except Exception:
        continue
    if len(json.dumps(d)) > 40000:      # per-iteration histories: keep the head only
        if isinstance(d, dict):
            d = {k: (v if len(json.dumps(v)) < 8000 else
                     {"_truncated": True, "_kind": type(v).__name__,
                      "_n": len(v) if hasattr(v, "__len__") else None})
                 for k, v in d.items()}
    reports[Path(rp).stem] = d

# ---- experimental data ----------------------------------------------------
exp = {}
for p in ("data/ribes/ribes_experiment.json", "data/ribes/ribes_measured_sections.json"):
    if Path(p).exists():
        exp[Path(p).stem] = json.loads(Path(p).read_text())

out = {
    "ohlevel_fields": fields,
    "levels": levels,
    "runs": runs,
    "meshes": list(meshes.values()),
    "reports": reports,
    "experiment": exp,
}
dst = Path("/tmp/claude-1000/-home-mike-kara-aeris/8b20e11f-275c-43d2-8e3d-34a95e4cbc83/scratchpad/bundle.json")
dst.write_text(json.dumps(out))
print(f"levels {len(levels)}  runs {len(runs)}  meshes {len(meshes)}  reports {len(reports)}")
print(f"experiment keys: {list(exp)}")
print(f"bundle {dst.stat().st_size/1e6:.2f} MB")
from collections import Counter
print("runs by family :", dict(Counter(r['family'] for r in runs)))
print("runs by geom   :", dict(Counter(r['geometry'] for r in runs)))
print("converged      :", dict(Counter(str(r['converged']) for r in runs)))
print("with cells     :", sum(1 for r in runs if r['cells']))
