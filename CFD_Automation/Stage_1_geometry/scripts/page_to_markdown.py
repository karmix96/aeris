"""A text copy of docs/GEOMETRY_GENERATOR.html for the project docs (figures as "[Figure: ...]" lines, diagrams as
"[Diagram: ...]" lines, captions kept).

    python scripts/page_to_markdown.py     # docs/GEOMETRY_GENERATOR.md (needs pandoc)
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
HEAD = "# Stage_1 — Wing Generator page (text copy, updated 11 Nov 2026)\n\n"


def main() -> None:
    s = (DOCS / "GEOMETRY_GENERATOR.html").read_text()
    for pat in (r"<style>.*?</style>", r"<script.*?</script>", r"<nav.*?</nav>", r"<title>.*?</title>",
                r"<link [^>]*>", r"<meta [^>]*>"):
        s = re.sub(pat, "", s, flags=re.S)
    s = re.sub(r'<img [^>]*?alt="([^"]*)"[^>]*>', lambda m: f"<p><em>[Figure: {m.group(1)}]</em></p>", s)
    s = re.sub(r'<svg[^>]*aria-label="([^"]*)"[^>]*>.*?</svg>', lambda m: f"<p><em>[Diagram: {m.group(1)}]</em></p>",
               s, flags=re.S)
    s = re.sub(r"<svg.*?</svg>", "", s, flags=re.S)
    s = re.sub(r'<span class="ctag">(.*?)</span>', lambda m: f"<strong>{m.group(1).rstrip('.')}.</strong> ", s)
    s = re.sub(r'<span class="howto">(.*?)</span>', r"\1 ", s)
    s = re.sub(r"<span class='do'>(.*?)</span>", r" \1", s)
    tmp = DOCS / "_page_text.html"
    tmp.write_text(s)
    md = subprocess.run(["pandoc", "-f", "html", "-t", "gfm", "--wrap=none", str(tmp)], capture_output=True, text=True,
                        check=True).stdout
    tmp.unlink()
    md = re.sub(r"</?div[^>]*>\n?", "", md)
    md = re.sub(r"</?span[^>]*>", "", md)
    md = re.sub(r"\[([^\]]+)\]\(#[^)]*\)", r"\1", md)                 # links inside the page: plain text
    lines = []
    for line in md.split("\n"):                                       # compact the tables (no column padding)
        if line.startswith("|"):
            line = re.sub(r"\|(\s*:?-{3,}:?\s*)(?=\|)", "| --- ", line) if set(line) <= set("|-: ") else line
            line = re.sub(r" {2,}", " ", line)
        lines.append(line)
    md = "\n".join(lines)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    (DOCS / "GEOMETRY_GENERATOR.md").write_text(HEAD + md)
    print(f"wrote docs/GEOMETRY_GENERATOR.md ({len(md) / 1e3:.0f} kB)")


if __name__ == "__main__":
    main()
