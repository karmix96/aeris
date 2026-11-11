"""ADflow's own iteration history, read from its log (the monitor lines), for runs whose result.json lost it
(run_adflow.py's history filter kept no key before the 11 Nov night fix). Judged with read_results.settled, the
plan's rule, imported unchanged.

    python adflow_log_history.py <adflow_log.txt> <out.json>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "solve"))
from read_results import settled                                # noqa: E402

COLS = ["grid", "iter", "itertot", "type", "cfl", "step", "linres", "resrho", "resrhou", "resrhov", "resrhow",
        "resrhoe", "resnuturb", "cl", "cd", "cdp", "cdv", "cmy", "totalres"]
LINE = re.compile(r"^\s+1\s+\d+\s+\d+\s+\S+\s")


def read(log: Path) -> dict:
    rows = []
    for line in log.read_text(errors="replace").splitlines():
        if LINE.match(line):
            f = line.split()
            if len(f) == len(COLS):
                rows.append(f)
    out = {}
    for i, c in enumerate(COLS):
        if c == "type":
            out[c] = [r[i] for r in rows]
        else:
            vals = []
            for r in rows:
                try:
                    vals.append(float(r[i]))
                except ValueError:
                    vals.append(float("nan"))
            out[c] = vals
    return out


def main() -> int:
    h = read(Path(sys.argv[1]))
    n = len(h["iter"])
    cl, cd, tr = np.array(h["cl"]), np.array(h["cd"]), np.array(h["totalres"])
    st = settled(cl[1:], cd[1:])                                # row 0 is the initial residual evaluation
    since = {}
    for start in (50, 80, 100):
        if n > start + 10:
            since[f"from_iter_{start}"] = {"cd_wander_counts": float((cd[start:].max() - cd[start:].min()) * 1e4),
                                           "cl_wander_rel": float((cl[start:].max() - cl[start:].min()) / abs(cl[-1]))}
    rep = {"source": sys.argv[1], "rows": n, "last_iter": int(h["iter"][-1]), "relative_residual_last": float(tr[-1] / tr[0]),
           "settled_rule": st, "force_wander_since": since, "history": h}
    Path(sys.argv[2]).write_text(json.dumps(rep))
    print(json.dumps({k: v for k, v in rep.items() if k != "history"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
