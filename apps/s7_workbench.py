#!/usr/bin/env python3
"""AERIS S7 workbench - pyGeo, Gmsh, SU2.

    python3 apps/s7_workbench.py [--port 8770]

Everything runs in the project virtual environment: Gmsh meshes in process and
SU2_CFD is launched as a child, so the whole chain is local to this interpreter.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aeris_workbench.workbench import S7_PROFILE, Workbench  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--no-browser", action="store_true")
    # trame stops a server that no browser has connected to.  That default suits
    # a hosted app; for one a user launches and then opens by hand it just makes
    # the window disappear after a minute, so idle shutdown is off unless asked.
    parser.add_argument("--timeout", type=int, default=0,
                        help="seconds to wait for a client before exiting (0 = never)")
    args = parser.parse_args()

    app = Workbench(S7_PROFILE)
    app.start(port=args.port, host=args.host, timeout=args.timeout,
              open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
