#!/usr/bin/env python3
"""Assemble the paper by injecting generated results into the draft.

The draft holds the argument; the experiments hold the numbers. Keeping them in
separate files and joining them here means a number can never drift out of step
with the run that produced it.
"""
from __future__ import annotations

import re
from pathlib import Path

PAPER_DIR = Path(__file__).resolve().parent
RESULTS = PAPER_DIR.parent / "results"

INJECTIONS = {
    "RESULTS:POLICY_TABLE": ("exp03_policy_evaluation.md", "## All 100 geometries"),
    "RESULTS:ROBUSTNESS": ("exp04_robustness.md", None),
}


def _demote(markdown: str) -> str:
    """Push injected headings one level down so they nest under the paper's."""
    return re.sub(r"^(#{2,5}) ", r"#\1 ", markdown, flags=re.MULTILINE)


def section_from(path: Path, start_heading: str | None) -> str:
    if not path.is_file():
        return (
            f"> **Missing.** `{path.name}` has not been generated yet; run the "
            "matching experiment and rebuild.\n"
        )
    text = path.read_text()
    if start_heading is None:
        # Drop the file's own title; the paper supplies its own heading level.
        return _demote("\n".join(text.splitlines()[1:]).strip()) + "\n"
    index = text.find(start_heading)
    body = text[index:] if index != -1 else text
    return _demote(body.strip()) + "\n"


def main() -> None:
    draft = (PAPER_DIR / "PAPER.md").read_text()
    for marker, (filename, heading) in INJECTIONS.items():
        block = section_from(RESULTS / filename, heading)
        draft = draft.replace(f"<!-- {marker} -->", block)

    remaining = re.findall(r"<!-- RESULTS:(\w+) -->", draft)
    output = PAPER_DIR / "PAPER_FULL.md"
    output.write_text(draft)
    print(f"wrote {output.relative_to(PAPER_DIR.parent.parent)}")
    if remaining:
        print(f"  unresolved markers: {remaining}")


if __name__ == "__main__":
    main()
