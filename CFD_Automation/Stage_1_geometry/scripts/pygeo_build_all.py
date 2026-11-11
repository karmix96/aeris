"""The one run Mike's machine still owes Stage 1 (open since 8 Nov 2026): build every set wing with pyGeo after the
label fix (decision 79), so that the manifests in git say "pygeo" with the new input hashes.

    source <your AERIS .venv>/bin/activate          # pyGeo 1.17.0, pySpline 1.5.4
    python CFD_Automation/Stage_1_geometry/scripts/pygeo_build_all.py

It runs the Stage 1 tests, builds the 722 set wings (the hold-outs are not built), compares the new manifests with the
ones in git, and prints the three git commands. It commits nothing itself. Never `git add -A` in this folder: 1,622
files show as deleted there (RUN_LOCAL.md).

    --skip-tests     build without running the tests first
    --check-only     only compare the manifests on disk with git (no pyGeo needed)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]                 # CFD_Automation/Stage_1_geometry
sys.path.insert(0, str(HERE.parent))


def compare() -> int:
    """The manifests on disk against HEAD: the same wings, input hashes and pass flags. Returns how many differ."""
    bad = wings = 0
    for f in sorted(str(q.relative_to(HERE)) for q in HERE.glob("data/sets/*/*_manifest.json")):
        new = json.loads((HERE / f).read_text())
        old = json.loads(subprocess.run(["git", "show", f"HEAD:./{f}"], cwd=HERE, capture_output=True, text=True,
                                        check=True).stdout)
        if len(new["wings"]) != len(old["wings"]):
            print("  differs:", f, "the number of wings")
            bad += 1
            continue
        for a, b in zip(old["wings"], new["wings"]):
            wings += 1
            if a["input_hash"] != b["input_hash"] or a.get("passed") != b.get("passed"):
                bad += 1
                print("  differs:", f, "wing", a["index"])
        sealed = all(w.get("built") is False for w in new["wings"])
        print(f"  {f}: {new['loft_backend']}, " + ("hold-outs: not built (sealed)" if sealed else
              f"{sum(bool(w.get('passed')) for w in new['wings'])} of {len(new['wings'])} built"))
    print(f"{wings} wings; input hash or pass flag different from git: {bad} (expected 0)")
    return bad


def main() -> None:
    if "--check-only" not in sys.argv:
        from cfdauto.geometry.loft import pygeo_available
        if not pygeo_available():
            sys.exit("pyGeo is not importable in this Python: activate the AERIS .venv first "
                     "(and `pip install -e CFD_Automation`).")
        if "--skip-tests" not in sys.argv:
            print("== 1 of 3: the Stage 1 tests (with the pyGeo ones) ==", flush=True)
            subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=HERE, check=True)
        print("== 2 of 3: build --all with pyGeo (722 wings) ==", flush=True)
        subprocess.run([sys.executable, "-m", "cfdauto.geometry.build", "--all"], cwd=HERE, check=True)
    print("== 3 of 3: against the manifests in git ==", flush=True)
    bad = compare()
    if bad:
        sys.exit("\nDo not commit: send me the lines that say \"differs\".")
    print("""
Commit only the manifests (from CFD_Automation/Stage_1_geometry):

  git add data/sets/*/*_manifest.json
  git commit -m "Stage 1: build --all with pyGeo after the label fix (decision 79): the manifests"
  git push
""")


if __name__ == "__main__":
    main()
