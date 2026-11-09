"""A text copy of docs/SURFACE_MESH.html for the project docs (figures as "[Figure: ...]" lines).

    python scripts/page_to_markdown.py     # docs/SURFACE_MESH.md (needs pandoc)
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
HEAD = """# Stage_2 — Surface mesh page (text copy, 2 Nov 2026, updated 9 Nov 2026)

Text copy for chats in this project of `CFD_Automation/Stage_2_surface_mesh/docs/SURFACE_MESH.html` (repo karmix96/aeris,
branch `stage2-surface-mesh`). The figures are in the HTML page and on the artifact; here each one is a *[Figure: ...]*
line with its caption. The page says what was first (built and screened 2–3 Nov) and what the new approach changed
(decided 4–6 Nov, built and screened 7 Nov): the section "What was first, and what changes", and a "What changes" note
in every section it touches. Studies 1–7 are first-approach evidence; Studies 8–13 are new (Study 9: the new screen; Study 12: the family screen; Study 13: what the band costs). Companion files: 'Stage_2 Executive summary', 'Stage_2 Status and
handover' (short), 'Stage_1 Handover to the surface mesh' (the input). If this copy and the repository ever differ,
the repository wins.

"""


def main() -> None:
    s = (DOCS / "SURFACE_MESH.body.html").read_text()
    s = re.sub(r'<figure class="card"><img [^>]*alt="([^"]*)"[^>]*><figcaption class="cap">.*?</figcaption></figure>',
               lambda m: f"<p><em>[Figure: {m.group(1)}]</em></p>", s, flags=re.S)
    s = re.sub(r"<svg.*?</svg>", "<p><em>[Figure: the pipeline: loft → stations → size fields → nose solve → one distribution → rings + cap → 13 checks → files]</em></p>", s, flags=re.S)
    for pat in (r"<style>.*?</style>", r"<nav.*?</nav>", r"<title>.*?</title>", r"<link [^>]*>", r"<meta [^>]*>"):
        s = re.sub(pat, "", s, flags=re.S)
    s = re.sub(r'<span class="k">(.*?)</span>', r"<p><strong>\1</strong></p>", s)
    s = re.sub(r'<div class="big">(.*?)</div>', r"<p><strong>\1</strong></p>", s, flags=re.S)
    s = re.sub(r'<span class="ctag">(.*?)</span>', r"<strong>\1.</strong> ", s)
    tmp = DOCS / "_page_text.html"
    tmp.write_text(s)
    md = subprocess.run(["pandoc", "-f", "html", "-t", "gfm", "--wrap=none", str(tmp)], capture_output=True, text=True, check=True).stdout
    tmp.unlink()
    md = re.sub(r"</?div[^>]*>\n?", "", md)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    (DOCS / "SURFACE_MESH.md").write_text(HEAD + md)
    print(f"wrote docs/SURFACE_MESH.md ({len(md) / 1e3:.0f} kB)")


if __name__ == "__main__":
    main()
