"""The values of the Stage 3 flowchart (docs/MESH_FLOWCHART.html): the rules per level, the cells and the outcomes,
written into the page's `const V = {...}` from the rule files and the rule-set-2 study files.

    python scripts/make_flowchart_values.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent))

from cfdauto.volume.laws import rules      # noqa: E402

LEVELS = ("VC", "C", "M", "F")
STUDIES = HERE / "data" / "studies"


def load(name: str) -> dict:
    p = STUDIES / name
    return json.loads(p.read_text()) if p.exists() else {}


def main() -> None:
    v4, v6 = load("r2_v4.json"), load("r2_v6.json")
    cells = v4.get("cells", {})
    built = v4.get("outcomes_built", {})
    od = v6.get("outcomes_with_decision_101", v6.get("outcomes", {}))
    nice = lambda r: f"{r['type']} {r['set']} {r['index']}".replace("training_full", "full-space").replace("flying_wing", "flying wing").replace("bwb", "BWB")
    refused = (f"V6: {od.get('refused', 0)} of {v6['meshes']} refused" + (" (" + "; ".join(f"{nice(r)}, cell quality {r['values'].get('cell_quality', 0):.3f}" for r in v6.get("refused", [])) + ")" if od.get("refused") else "")) if v6 else "V6: running"
    V = {}
    for lev in LEVELS:
        r = rules(lev)
        c = cells.get(lev, {})
        med, mx = c.get("median", 0) / 1e6, c.get("max", 0) / 1e6
        b = built.get(lev, {})
        nb = sum(b.values())
        txt = (f"built on {nb}: {b.get('passed', 0)} pass" if nb else "counted, not built")
        if lev == "VC" and v6:
            txt += f"; all sets: {od.get('passed', 0)} of {v6['meshes']}"
        V[lev] = {"lv": lev, "yp": f"{r.yplus:.2f}", "gw": f"{r.wall_growth:.3f}", "bl": f"{r.bl_cells:.3g}",
                  "gfc": f"{r.far_growth:.3f}", "gfb": f"{r.far_growth_built:.3f}",
                  "band": f"{100 * r.band['spacing_c']:.3g} % c", "fan": f"{r.band['fan_cells']:.3g}",
                  "og": f"{r.outboard_growth:.3f}", "base": str({"VC": 8, "C": 10, "M": 14, "F": 18}[lev]),
                  "cells": f"{med:.2f} M" if med < 10 else f"{med:.1f} M", "cmax": f"{mx:.2f} M" if mx < 10 else f"{mx:.1f} M",
                  "ram": f"{2.69 + 7.23 * med:.0f}–{1.51 + 9.46 * med:.0f} GiB", "built": txt, "refused": refused}
    p = HERE / "docs" / "MESH_FLOWCHART.html"
    s = p.read_text()
    s, n = re.subn(r"const V = \{.*?\};\n", lambda m: "const V = " + json.dumps(V, ensure_ascii=False) + ";\n", s, count=1, flags=re.S)
    assert n == 1
    # the text in the page itself (shown before the script runs, and read by the text copy): the VC values
    s = re.sub(r'(<(span|strong)\b[^>]*\bdata-k="(\w+)"[^>]*>)(.*?)(</\2>)',
               lambda m: m.group(1) + (V["VC"].get(m.group(3), m.group(4))) + m.group(5), s, flags=re.S)
    p.write_text(s)
    md = text_copy(s, V)
    (HERE / "docs" / "MESH_FLOWCHART.md").write_text(md)
    print(json.dumps(V["VC"], ensure_ascii=False))


LABELS = (("yp", "y⁺"), ("gw", "wall growth"), ("bl", "cells across the boundary layer"), ("gfb", "far growth, built"),
          ("gfc", "far growth, checked"), ("band", "band cell at the trailing edge"), ("fan", "cells across the −5° to +10° fan"),
          ("og", "outboard growth"), ("base", "base cells"), ("cells", "cells, median (20 reference wings, Re 3e5)"),
          ("cmax", "cells, largest"), ("ram", "ADflow RAM, median (S8's two laws)"), ("built", "built here"))


def text_copy(page: str, V: dict) -> str:
    """The flowchart as text for the project docs: the values per level, then the steps (needs pandoc)."""
    import subprocess
    main = page[page.index("<main>"):page.index("</main>") + 7]
    main = re.sub(r'<div class="bar">.*?<div class="flow">', '<div class="flow">', main, flags=re.S)
    main = re.sub(r'<span class="num">(\d+)</span>', r"<p><strong>Step \1</strong></p>", main)
    main = re.sub(r'<span class="chip (law|dec|chk)"><b>(.*?)</b><span>(.*?)</span></span>', r"[\2: \3] ", main)
    main = re.sub(r'<span class="tag">(.*?)</span>', r"<p><em>\1</em></p>", main)
    main = re.sub(r'<span class="eyebrow">(.*?)</span>', r"<p>\1</p>", main)
    body = subprocess.run(["pandoc", "-f", "html", "-t", "gfm", "--wrap=none"], input=main, capture_output=True, text=True,
                          check=True).stdout
    body = re.sub(r"</?(div|span|main|header|footer|strong)[^>]*>", "", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    rows = ["| value | " + " | ".join(LEVELS) + " |", "| --- | " + " | ".join("---" for _ in LEVELS) + " |"]
    rows += ["| " + lab + " | " + " | ".join(V[l][k] for l in LEVELS) + " |" for k, lab in LABELS]
    head = ("# Stage_3 — Mesh flowchart (text copy, 10 Nov 2026)\n\nText copy of `CFD_Automation/Stage_3_volume_mesh/docs/MESH_FLOWCHART.html` "
            "(the artifact *Volume Mesh Flowchart*). Rule set 2 as it stands (decisions 107–111). On the page the values change with "
            "the level picked; here they are a table, and the steps show the VC values.\n\n## The values per level\n\n")
    return head + "\n".join(rows) + "\n\n## The steps\n\n" + body + "\n"


if __name__ == "__main__":
    main()
