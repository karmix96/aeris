"""Independent solver worker for the parallel driver.

Reads a JSON slice spec {sample_keys:[...], cells:[...]} and solves every
(geometry x cell) via common.run_case, populating the on-disk cache. Each worker
is a fully independent process (normal one-time MPI init), which sidesteps the
mpi4py-in-multiprocessing-child deadlock. Coordination is the cache alone.

Samples are rebuilt from their keys (the LHS design and the extreme overrides are
deterministic), so nothing needs pickling across processes.
"""

from __future__ import annotations

import json
import sys

import common as C


def sample_by_key(key: str):
    if key.startswith("extreme:"):
        for k, s in C.extreme_samples():
            if k == key:
                return s
    else:
        for k, s in C.normal_samples():
            if k == key:
                return s
    raise KeyError(f"unknown sample key: {key}")


def main(spec_path: str):
    spec = json.loads(open(spec_path).read())
    keys = spec["sample_keys"]
    cells = spec["cells"]
    for ki, key in enumerate(keys):
        s = sample_by_key(key)
        for cell in cells:
            r = C.run_case(s, sample_key=key, **cell)
            print(f"[worker {spec.get('wid','?')}] {key} "
                  f"c{cell['nchordwise']}s{cell['spanwise']}cs{cell['cspace']} "
                  f"a{cell['alpha_deg']:+.0f} ok={r.get('ok')} hit={r.get('cache_hit')}",
                  flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
