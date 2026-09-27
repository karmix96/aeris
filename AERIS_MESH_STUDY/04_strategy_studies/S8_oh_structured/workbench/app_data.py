"""Trim the harvest bundle down to what the workbench needs, as one JS payload."""
import json, sys
import numpy as np
from pathlib import Path
SP = Path("/tmp/claude-1000/-home-mike-kara-aeris/8b20e11f-275c-43d2-8e3d-34a95e4cbc83/scratchpad")
HERE = Path("/home/mike_kara/aeris/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured")
b = json.loads((SP / "bundle.json").read_text())
R = lambda v, n=6: (None if v is None else round(float(v), n))

# ---- mesh levels ------------------------------------------------------------
levels = {k: {f: (R(v, 8) if isinstance(v, float) else v) for f, v in d.items()}
          for k, d in b["levels"].items()}

# ---- runs -------------------------------------------------------------------
runs = []
for r in b["runs"]:
    runs.append({"p": r["path"].replace("runs/", "").replace("/result.json", ""),
                 "s": r["set"], "lv": r["level"], "fam": r["family"],
                 "g": r["geometry"], "a": R(r["alpha"], 3),
                 "cl": R(r["cl"], 5), "cd": R(r["cd"], 7), "cdp": R(r["cdp"], 7),
                 "cdv": R(r["cdv"], 7), "cmy": R(r["cmy"], 6),
                 "cv": r["converged"], "it": r["iterations"], "rr": R(r["residual"], 10),
                 "nk": r["nk"], "ev": R(r["evir"], 4), "tb": r["turb"],
                 "M": R(r["mach"], 5), "Re": R(r["re"], 1), "n": r["cells"]})

# ---- mesh summaries ---------------------------------------------------------
meshes = [{"n": m["name"], "s": m["set"], "lv": m["level"], "cells": m["cells"],
           "neg": m["negative_cells"], "minv": R(m["min_volume"], 20),
           "orth": R(m["wall_orthogonality_median_deg"], 4),
           "blocks": {k: v["shape"] for k, v in (m["blocks"] or {}).items()},
           "geom": (m["geometry"].get("wing") if isinstance(m.get("geometry"), dict) else m.get("geometry"))}
          for m in b["meshes"] if m["cells"]]

# ---- RIBES experiment -------------------------------------------------------
exp = b["experiment"]["ribes_experiment"]
tests = {}
for tn, t in (exp.get("tests") or {}).items():
    cps = []
    for c in (t.get("cp") or []):
        # cp is [tap][incidence]; alpha_corrected_deg names the incidences
        cps.append({"sec": c["section"], "y": c.get("y_mm"),
                    "alphas": [R(v, 3) for v in (c.get("alpha_corrected_deg") or [])],
                    "x": [R(v, 5) for v in (c.get("x_over_c") or [])],
                    "z": [R(v, 5) for v in (c.get("z_over_c") or [])],
                    "cp": [[R(v, 5) for v in row] for row in (c.get("cp") or [])]})
    sect = t.get("sectional")
    tests[tn] = {"cp": cps,
                 "sectional": sect if isinstance(sect, (list, dict)) else None,
                 **{k: v for k, v in t.items()
                    if k not in ("cp", "sectional") and not isinstance(v, (list, dict))}}
ribes = {"tests": tests,
         "sections_y_mm": exp.get("pressure_sections_y_mm"),
         "model": exp.get("model"), "tunnel": exp.get("tunnel"),
         "test_matrix": exp.get("test_matrix"),
         "meta": {k: v for k, v in exp.items()
                  if not isinstance(v, (list, dict))}}

# ---- scan points, with the interior flag that found the defect --------------
secs = b["experiment"]["ribes_measured_sections"]["sections"]
scan = {}
for k, s in sorted(secs.items(), key=lambda t: int(t[0])):
    x = np.asarray(s["xc"], float); z = np.asarray(s["zc"], float)
    if len(x) < 150:
        continue
    interior = np.zeros(len(x), bool)
    for i in range(len(x)):
        w = np.abs(x - x[i]) < 0.01
        if (z[w] > z[i] + 0.004).any() and (z[w] < z[i] - 0.004).any():
            interior[i] = True
    scan[k] = {"y": s.get("y_mm"), "x": [R(v, 5) for v in x],
               "z": [R(v, 5) for v in z], "i": [int(v) for v in interior]}

# ---- the fitted section, and the old bad one for comparison ----------------
fit = json.loads((HERE / "reports/s8_ribes_section_fit.json").read_text())
d = np.loadtxt(HERE / "external/ribes/ribes_section.dat")
section = {"x": [R(v, 6) for v in d[:, 0]],
           "zu": [R(v, 6) for v in d[:, 1]], "zl": [R(v, 6) for v in d[:, 2]],
           "cst": fit["cst_coefficients"],
           "per_section": {k: {"ifrac": R(v["interior_fraction"], 4),
                               "ru": R(v["cst_residual_upper_pct_chord"], 4),
                               "rl": R(v["cst_residual_lower_pct_chord"], 4)}
                           for k, v in fit["per_section"].items()}}

# ---- the measured findings the workbench should state, not re-derive -------
keep = ["s8_ribes_nonsense_diagnosis", "s8_increment_cancellation", "s8_family2_design",
        "s8_where_meshes_differ", "s8_base_and_near_wake", "s8_base_ladders",
        "s8_family3_result", "s8_geometry_class", "s8_alpha_sweep_to_stall",
        "s8_nk_solver_path", "s8_ribes_status", "s8_ribes_section_fit"]
reports = {k: b["reports"][k] for k in keep if k in b["reports"]}

out = {"fields": b["ohlevel_fields"], "levels": levels, "runs": runs,
       "meshes": meshes, "ribes": ribes, "scan": scan, "section": section,
       "reports": reports}
js = "window.S8=" + json.dumps(out, separators=(",", ":")) + ";"
(SP / "s8data.js").write_text(js)
print(f"levels {len(levels)}  runs {len(runs)}  meshes {len(meshes)}")
print(f"scan sections {len(scan)}  tests {list(tests)}  reports {len(reports)}")
print(f"payload {len(js)/1e6:.3f} MB")
for k, v in out.items():
    print(f"   {k:10s} {len(json.dumps(v))/1e3:>8.1f} kB")
