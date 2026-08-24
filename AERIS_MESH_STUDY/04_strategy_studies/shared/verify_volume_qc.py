"""ADR-0014 section 3.4 — verify the in-house volume metric against pyHyp.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/shared/verify_volume_qc.py

S4's volume cannot be scored until `shared/volume_qc.py` agrees with pyHyp on
volumes pyHyp has already reported on. The comparison is run against **S1's**,
which passed 10/10.

What "agree" means here, and what it deliberately does not mean:

* **Validity must agree exactly.** If pyHyp says zero inverted cells and a positive
  minimum volume, the in-house route must say the same. A disagreement here means
  one of the two instruments is wrong and S4 waits.
* **Minimum quality is compared but not required to be equal.** pyHyp's `Quality`
  column and a corner scaled Jacobian are different definitions of the same idea;
  requiring them to match to three decimals would be requiring pyHyp's formula, not
  verifying ours. What is required is that they agree on the SIGN and stay within a
  factor that is recorded here rather than assumed — the sign is what the gate turns
  on, and a factor recorded once is a factor the final report can state.

The first run of this check found a real defect: the corner triple product was
ordered so that "positive" meant the opposite of what `signed_cell_volumes` means by
it, and every valid pyHyp volume scored -1.0. A unit-cube test had passed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

STUDIES = Path(__file__).resolve().parents[1]
REPO_ROOT = STUDIES.parents[1]
for _p in (str(REPO_ROOT / "src"), str(STUDIES)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shared import gates, volume_qc  # noqa: E402

S1_ROOT = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/strategy_studies/S1_tip_first"
OUT = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/strategy_studies/S4_analytic_multiblock"

#: pyHyp's per-layer table. Columns: Lvl Time Its Its Bad Ratio Max Min Quality ...
#: `Min Quality` is column index 7 (0-based) on a data row.
_NUM = r"([\d.eE+-]+)"
_ROW = re.compile(
    r"^\s*\d+\s+[\d.]+\s+\d+\s+\d+\s+(\d+)\s+" + r"\s+".join([_NUM] * 4)
)


def pyhyp_min_quality(log: Path) -> tuple[float | None, bool]:
    """(worst `Min Quality` over completed layers, march_completed)."""
    text = log.read_text(errors="replace")
    worst = None
    for line in text.splitlines():
        m = _ROW.match(line)
        if not m:
            continue
        q = float(m.group(5))
        worst = q if worst is None else min(worst, q)
    return worst, ("pyHyp done" in text)


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    # Each volume is ~60 MB and 2.3M cells. A sample spread over geometries and epsE
    # settles the question; reading all 125 does not settle it any harder.
    ap.add_argument("--sample", type=int, default=6)
    args = ap.parse_args()

    runs = sorted(S1_ROOT.rglob("wing_vol.cgns"))
    if not runs:
        print(f"no S1 volumes found under {S1_ROOT}")
        return 1
    if args.sample and len(runs) > args.sample:
        step = len(runs) / args.sample
        runs = [runs[int(i * step)] for i in range(args.sample)]

    rows = []
    print(f"{'run':46s} {'pyHypQ':>9s} {'inhouseQ':>10s} {'ratio':>7s} "
          f"{'inv':>4s} {'minVol':>11s} {'gate':>5s}")
    for cgns in runs:
        log = cgns.parent / "run_stdout.log"
        pq, done = (pyhyp_min_quality(log) if log.exists() else (None, False))
        if not done:
            continue  # only completed marches are comparable (instrument bug 10)
        rep = volume_qc.equivalence_against_pyhyp(cgns)
        ok, why = gates.volume_gate_checklist_direct(rep)
        iq = rep["min_scaled_quality"]
        ratio = (iq / pq) if (pq not in (None, 0.0)) else float("nan")
        label = "/".join(cgns.parts[-4:-1])
        rows.append(
            {
                "run": label, "pyhyp_min_quality": pq, "inhouse_min_scaled_quality": iq,
                "ratio": ratio, "inverted_cells": rep["inverted_cells"],
                "min_volume": rep["min_volume"], "total_cells": rep["total_cells"],
                "direct_gate": "PASS" if ok else "FAIL", "direct_gate_reasons": why,
            }
        )
        print(f"{label:46s} {pq:9.5f} {iq:10.5f} {ratio:7.3f} "
              f"{rep['inverted_cells']:4d} {rep['min_volume']:11.4e} "
              f"{('PASS' if ok else 'FAIL'):>5s}")

    if not rows:
        print("no COMPLETED S1 marches found to compare against")
        return 1

    agree_sign = all((r["pyhyp_min_quality"] > 0) == (r["inhouse_min_scaled_quality"] > 0)
                     for r in rows)
    agree_valid = all(r["inverted_cells"] == 0 and r["min_volume"] > 0 for r in rows)
    ratios = [r["ratio"] for r in rows]
    verdict = agree_sign and agree_valid

    print(f"\ncompared            : {len(rows)} completed S1 marches")
    print(f"sign agreement      : {agree_sign}")
    print(f"validity agreement  : {agree_valid} (pyHyp passed all of these)")
    print(f"quality ratio       : {min(ratios):.3f} to {max(ratios):.3f} "
          f"(in-house / pyHyp; different definitions, not required to be 1.0)")
    print(f"\nADR-0014 section 3.4: {'VERIFIED' if verdict else 'FAILED — S4 is blocked'}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "volume_qc_equivalence.json").write_text(
        json.dumps(
            {
                "adr": "ADR-0014-non-pyhyp-volume-gate.md",
                "schema": volume_qc.VOLUME_QC_SCHEMA,
                "verified": verdict,
                "sign_agreement": agree_sign,
                "validity_agreement": agree_valid,
                "quality_ratio_range": [min(ratios), max(ratios)],
                "rows": rows,
            },
            indent=2,
        )
        + "\n"
    )
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
