#!/usr/bin/env python3
"""Auto-generated static pyHyp runner (aeris.cfd) — options come from
pyhyp_options.json next to this script; this file bakes in nothing."""
import json
from pathlib import Path


def main():
    here = Path(__file__).parent
    options = json.loads((here / "pyhyp_options.json").read_text())
    if options.get("BC"):
        # JSON stringifies the 1-based integer block ids pyHyp requires
        options["BC"] = {int(block): edges for block, edges in options["BC"].items()}

    from pyhyp import pyHyp as PyHyp

    hyp = PyHyp(options=options)
    hyp.run()
    hyp.writeCGNS(options["outputFile"])
    print(f"pyHyp done -> {options['outputFile']}", flush=True)


if __name__ == "__main__":
    main()
