#!/usr/bin/env python3
"""AERIS S6 workbench - pyGeo, pyHyp, ADflow.

    python3 apps/s6_workbench.py [--port 8771]

The interface runs in the project virtual environment, which is the only one
with VTK.  pyHyp and ADflow live in the conda `mach-aero` environment, so both
are launched there as subprocesses; nothing about that is visible in the UI
beyond the log naming the interpreter it used.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aeris_workbench.workbench import S6_PROFILE, Workbench  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8771)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    app = Workbench(S6_PROFILE)
    app.start(port=args.port, host=args.host, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
