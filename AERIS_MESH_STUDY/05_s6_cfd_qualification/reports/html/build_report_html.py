"""Render S8_REPORT_*.md as a navigable HTML report.

The report is ~19k words with a deep section tree, so the whole point of the
rendering is navigation: a sticky contents rail with scroll-spy, and the
addenda treated as what they are -- a dated sequence.
"""
import re, sys, html
from pathlib import Path
from markdown_it import MarkdownIt

SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2])
text = SRC.read_text()

# --- split off the front matter we replace with real page furniture -------
lines = text.split("\n")
title = lines[0].lstrip("# ").strip()
# drop the markdown "## Contents" list: the rail replaces it
body_md = "\n".join(lines[1:])
body_md = re.sub(r"^## Contents\n.*?^---\n", "", body_md, flags=re.S | re.M)

md = MarkdownIt("commonmark").enable(["table", "strikethrough"])
rendered = md.render(body_md)

# --- heading ids + nav tree ----------------------------------------------
def slug(s):
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).lower()
    s = re.sub(r"[^\w\s-]", "", s)
    return re.sub(r"[\s_]+", "-", s).strip("-") or "section"

nav, seen = [], {}
ADD = re.compile(r"^Addendum\s*[—-]\s*(\d{1,2}\s+\w+,\s*\d{1,2}:\d{2}):\s*(.*)$")

def heading(m):
    lvl, inner = int(m.group(1)), m.group(2)
    plain = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
    sid = slug(plain)
    seen[sid] = seen.get(sid, 0) + 1
    if seen[sid] > 1:
        sid = f"{sid}-{seen[sid]}"
    a = ADD.match(plain)
    if a:
        when, what = a.group(1), a.group(2)
        nav.append((2, when, what, sid, True))
        eyebrow = f'<p class="when">{html.escape(when)}</p>'
        return (f'<section class="addendum">{eyebrow}'
                f'<h2 id="{sid}" class="h-add">{html.escape(what)}</h2>')
    nav.append((lvl, None, plain, sid, False))
    return f'<h{lvl} id="{sid}">{inner}</h{lvl}>'

rendered = re.sub(r"<h([23])>(.*?)</h\1>", heading, rendered, flags=re.S)
# close each addendum block before the next top-level heading starts
rendered = re.sub(r'(?<!\A)(?=<section class="addendum">)', "</section>", rendered)
rendered = re.sub(r'(?=<h2 id="[^"]*"(?! class="h-add"))', "</section>", rendered, count=0)
rendered = rendered.replace("</section><h2", "</section>\n<h2")
if '<section class="addendum">' in rendered:
    rendered += "</section>"
# strays: a </section> before the first addendum is wrong
first = rendered.find('<section class="addendum">')
if first != -1:
    head, tail = rendered[:first], rendered[first:]
    rendered = head.replace("</section>", "") + tail

rendered = rendered.replace("<table>", '<div class="tw"><table>').replace("</table>", "</table></div>")
rendered = rendered.replace("<hr />", "")

# --- contents rail --------------------------------------------------------
items, in_add = [], False
for lvl, when, label, sid, is_add in nav:
    if is_add and not in_add:
        items.append('<p class="rail-group">Addenda</p>')
        in_add = True
    if is_add:
        items.append(f'<a class="r2 r-add" href="#{sid}">'
                     f'<span class="rdate">{html.escape(when)}</span>'
                     f'<span>{html.escape(label)}</span></a>')
    else:
        items.append(f'<a class="r{lvl}" href="#{sid}">{html.escape(label)}</a>')
rail = "\n".join(items)

#: Per-document masthead. It used to be hardcoded for the S8 report, which
#: meant the SU2 report published with S8's title, eyebrow, standfirst and
#: "Source" line -- a different document wearing another one's identity.
MASTHEADS = {
    "S8_REPORT_2026-09-15.md": {
        "page": "AERIS S8 Campaign",
        "eyebrow": "Strategy study S8 · structured O-H meshing",
        "stand": ("An automated mesh-and-solve pipeline for the AERIS flying wing: how it "
                  "was built, every setting in force, what each study asked and answered, "
                  "and where the results are still soft."),
        "meta": [("Started", "15 September 2026"), ("Solver", "ADflow RANS-SA · SU2 8.5"),
                 ("Source", "S8_REPORT_2026-09-15.md")],
    },
    "SU2_REPORT_2026-09-18.md": {
        "page": "AERIS SU2 Track",
        "eyebrow": "Second solver · verification, validation and transition",
        "stand": ("Why a second solver exists in this project, every setting in force and the "
                  "reason for it, the ten cases and what each one asks, and what the evidence "
                  "does and does not support."),
        "meta": [("Written", "18 September 2026"), ("Solver", "SU2 v8.5.0 “Harrier”"),
                 ("Source", "SU2_REPORT_2026-09-18.md")],
    },
}
head = MASTHEADS.get(SRC.name, {
    "page": title, "eyebrow": SRC.stem.replace("_", " "), "stand": "",
    "meta": [("Source", SRC.name)]})
meta_html = "".join(f"<span><b>{html.escape(k)}</b> {html.escape(v)}</span>"
                    for k, v in head["meta"])

OUT.write_text(Path(__file__).with_name("shell.html").read_text()
               .replace("{{PAGETITLE}}", html.escape(head["page"]))
               .replace("{{EYEBROW}}", html.escape(head["eyebrow"]))
               .replace("{{STAND}}", html.escape(head["stand"]))
               .replace("{{META}}", meta_html)
               .replace("{{TITLE}}", html.escape(title))
               .replace("{{RAIL}}", rail)
               .replace("{{BODY}}", rendered))
print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB), {len(nav)} headings")
