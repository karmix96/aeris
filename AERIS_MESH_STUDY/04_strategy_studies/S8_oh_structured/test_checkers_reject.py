#!/usr/bin/env python3
"""The counterexamples, as tests. Run before the cloud batch and after any change.

Every case here is one a checker ONCE accepted. Most came from the external
review of 2026-09-16, which found them by feeding synthetic inputs to the real
functions rather than by reading the code; two were found here on 2026-09-18 by
reproducing its method. A checker that cannot reject these cannot be trusted to
judge runs that cost money.

    python3 test_checkers_reject.py
"""
from __future__ import annotations
import copy, json, math, sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import audit_runs, convergence_gate as G, gci  # noqa: E402

ROWS = HERE / "data/dataset_v2/rows.json"
FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))
    if not condition:
        FAILURES.append(name)


def history(cl, n=600, resid_to=-8.0):
    ncol = max(G.COLUMNS.values()) + 1
    h = np.zeros((n, ncol))
    for key, col in G.COLUMNS.items():
        if key.startswith("res"):
            h[:, col] = np.logspace(0, resid_to, n)
    h[:, G.COLUMNS["cl"]] = cl
    h[:, G.COLUMNS["cd"]] = 0.02
    h[:, G.COLUMNS["cmy"]] = 0.001
    return h


def gate(h):
    return G.gate(h, window=100, min_orders=3.0, cl_pct=0.05, cd_pct=0.05,
                  cmy_abs=1.0e-4, l2_target=1.0e-6)


def test_gate():
    print("\nconvergence gate")
    # Defect 30: a clean residual says nothing about a force still travelling.
    v = gate(history(np.linspace(-0.1, 2.0, 600)))["verdict"]
    check("rejects residual 1e-8 with CL running -0.1 -> 2.0", v == "REJECTED", v)
    # ...but the near-zero-CL runs this fleet actually contains must survive.
    v = gate(history(np.full(600, -0.0087) + np.linspace(0, 1.8e-4, 600)))["verdict"]
    check("accepts CL -0.0087 drifting 1.8e-4 (g65 alpha 0 is real)", v == "ACCEPTED", v)
    v = gate(history(np.full(600, -0.16) + np.linspace(0, -1.7e-4, 600)))["verdict"]
    check("accepts the measured 0.107 % short-tail case", v == "ACCEPTED", v)


def test_gci():
    print("\nGCI")
    # Defect 28: Celik's order formula takes an absolute value, so a runaway
    # family reports a healthy positive order.
    f = [1 + h ** -2 for h in (1.0, 1.3, 1.69)]
    r = gci.gci_triplet(f[0], f[1], f[2], 1.3, 1.3)
    check("refuses f(h) = 1 + h^-2, which has no limit as h -> 0",
          r["condition"].startswith("DIVERGENT"), f"p={r['p_observed']:.3f}")
    check("leaves certified uncertainty empty for it",
          r["certified_uncertainty_percent"] is None)
    # A constructed family whose answer is known exactly.
    f = [0.015 + 0.001 * h ** 2 for h in (1.0, 1.5, 2.25)]
    r = gci.gci_triplet(f[0], f[1], f[2], 1.5, 1.5)
    check("recovers p = 2 and f_ext = 0.015 on a convergent family",
          abs(r["p_observed"] - 2) < 1e-9 and abs(r["f_extrapolated"] - 0.015) < 1e-12,
          f"p={r['p_observed']:.6f} f_ext={r['f_extrapolated']:.8f}")
    check("certifies that one", r["certified_uncertainty_percent"] is not None)


def test_audit():
    print("\narchive audit")
    if not ROWS.exists():
        check("dataset_v2 rows present", False, f"{ROWS} not found")
        return
    rows = json.loads(ROWS.read_text())
    areas = json.loads(audit_runs.AREAS.read_text())["areas"]
    good = rows[0]
    base = audit_runs.checks(good, areas)
    # Defect 29: an absent field must be a finding, never silence.
    for field in ("inverted_cells", "wall_layer_error_m", "velocity_direction_error",
                  "reynolds_mac", "yplus_min_p50_p95_p99_max", "iterations",
                  "CDv", "area_ref", "equation_orders", "gate_verdict"):
        missing = copy.deepcopy(good)
        missing.pop(field, None)
        found = audit_runs.checks(missing, areas)
        check(f"reports a missing {field}",
              any(field in f for f in found) and found != base)
        if isinstance(good.get(field), (int, float)):
            nan = copy.deepcopy(good)
            nan[field] = float("nan")
            check(f"reports a NaN {field}",
                  any(field in f for f in audit_runs.checks(nan, areas)))
    # Only the x component used to be compared.
    off = copy.deepcopy(good)
    off["moment_ref_xyz"] = [0.4, 3, 4]
    check("rejects a moment reference of [0.4, 3, 4]",
          any("moment reference" in f for f in audit_runs.checks(off, areas)))
    check("a real accepted row still yields only the known y+ finding",
          all("y+" in f for f in base), str(base))


def main() -> int:
    test_gate()
    test_gci()
    test_audit()
    print(f"\n{'ALL CHECKERS REJECT WHAT THEY SHOULD' if not FAILURES else 'FAILURES: ' + ', '.join(FAILURES)}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
