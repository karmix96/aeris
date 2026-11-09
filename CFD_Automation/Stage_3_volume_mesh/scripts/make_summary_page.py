"""The Stage 3 executive summary as one HTML file with every picture inside: docs/EXECUTIVE_SUMMARY.html.
(A copy of Stage 2's make_summary_page.py with its own boxes.)

    python scripts/make_summary_page.py     # reads docs/EXECUTIVE_SUMMARY.md (needs pandoc)

The markdown is the source (it renders on GitHub with the pictures from docs/page/); the HTML carries the
pictures as data, so it can be uploaded or sent as one file.
"""

from __future__ import annotations

import base64
import html
import re
import subprocess
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
MD = DOCS / "EXECUTIVE_SUMMARY.md"
OUT = DOCS / "EXECUTIVE_SUMMARY.html"

CSS = """
:root { --bg: #F3F6F9; --surface: #FFFFFF; --ink: #142230; --muted: #566573; --line: #D6DEE6; --accent: #0C5EA8;
  --good: #2E8B57; --warn: #B02A20; --amber: #9A6200;
  --display: "Barlow Condensed", "Arial Narrow", sans-serif; --body: "Source Sans 3", "Segoe UI", system-ui, sans-serif;
  --mono: "JetBrains Mono", ui-monospace, Menlo, Consolas, monospace; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg: #0E141A; --surface: #151E27; --ink: #E4ECF3;
  --muted: #98A7B5; --line: #26333F; --accent: #62AEF2; --good: #5FC48F; --warn: #F08A80; --amber: #E7B24F; color-scheme: dark; } }
:root[data-theme="dark"] { --bg: #0E141A; --surface: #151E27; --ink: #E4ECF3; --muted: #98A7B5; --line: #26333F;
  --accent: #62AEF2; --good: #5FC48F; --warn: #F08A80; --amber: #E7B24F; color-scheme: dark; }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 16px; line-height: 1.6; margin: 0;
  padding: 28px max(16px, env(safe-area-inset-right, 0px)) 64px max(16px, env(safe-area-inset-left, 0px)); }
main { max-width: 920px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }
h1 { font-family: var(--display); font-size: clamp(30px, 5vw, 42px); line-height: 1.08; margin: 0 0 4px; text-wrap: balance; }
h2 { font-family: var(--display); font-size: 27px; margin: 30px 0 2px; padding-top: 12px; border-top: 1px solid var(--line); }
p, ul, ol { margin: 0; } ul, ol { padding-left: 22px; } li { margin-bottom: 4px; }
a { color: var(--accent); }
code { font-family: var(--mono); font-size: 13px; overflow-wrap: anywhere; }
blockquote { margin: 0; background: var(--surface); border: 1px solid var(--line); border-left: 4px solid var(--amber); border-radius: 6px; padding: 12px 16px; }
blockquote p + ul { margin-top: 6px; } blockquote ul ul { margin-top: 2px; }
figure.card { margin: 8px 0 0; background: #FFFFFF; border: 1px solid var(--line); border-radius: 6px; padding: 10px; }
figure.card img { display: block; width: 100%; height: auto; }
p.shows { color: var(--muted); font-size: 14.5px; }
.cbox { background: var(--surface); border: 1px solid var(--line); border-left: 4px solid var(--good); border-radius: 6px; padding: 10px 14px; font-size: 15px; }
.cbox .ctag { display: block; font-family: var(--mono); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--good); margin-bottom: 2px; }
.cbox.warn { border-left-color: var(--warn); } .cbox.warn .ctag { color: var(--warn); }
.cbox.old { border-left-color: var(--muted); color: var(--muted); } .cbox.old .ctag { color: var(--muted); }
.cbox.chg { border-left-color: var(--amber); background: color-mix(in srgb, var(--amber) 6%, var(--surface)); } .cbox.chg .ctag { color: var(--amber); }
.tbl { overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 6px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; min-width: 680px; }
th, td { text-align: left; vertical-align: top; padding: 8px 11px; border-bottom: 1px solid var(--line); }
tr:last-child td { border-bottom: 0; }
th { font-family: var(--mono); font-weight: 500; font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
.lede { color: var(--muted); }
"""

BOXES = {"Conclusion.": ("Conclusion", ""), "Weak point.": ("Weak point", "warn"), "To decide.": ("To decide (Mike)", "chg")}


def main() -> None:
    md = MD.read_text()
    body = subprocess.run(["pandoc", "-f", "gfm", "-t", "html5", "--wrap=none"], input=md, capture_output=True,
                          text=True, check=True).stdout

    def figure(m: re.Match) -> str:
        src, alt = m.group(1), html.unescape(m.group(2))
        data = base64.b64encode((DOCS / src).read_bytes()).decode()
        return f'<figure class="card"><img src="data:image/png;base64,{data}" alt="{html.escape(alt)}" loading="lazy"></figure>'

    body, n_fig = re.subn(r'<p><img src="([^"]+)" alt="([^"]*)" ?/?></p>', figure, body)
    body = re.sub(r"<p><em>What it shows\.</em>", '<p class="shows"><em>What it shows.</em>', body)
    for key, (tag, cls) in BOXES.items():
        body = re.sub(rf"<p><strong>{re.escape(key)}</strong> (.*?)</p>",
                      lambda m, t=tag, c=cls: f'<div class="cbox {c}"><span class="ctag">{t}</span>{m.group(1)}</div>', body, flags=re.S)
    body = body.replace("<table>", '<div class="tbl"><table>').replace("</table>", "</table></div>")
    page = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<title>Stage 3 Executive Summary</title>\n'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Source+Sans+3:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap">\n'
            f"<style>{CSS}</style>\n</head>\n<body>\n<main>\n{body}\n</main>\n</body>\n</html>\n")
    OUT.write_text(page)
    print(f"wrote {OUT.name}: {n_fig} figures, {len(page) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
