# 04 — Six independent strategy studies

Authority: **ADR-0011**, `00_governance/decisions/ADR-0011-independent-strategy-studies.md`.
Prior knowledge for all six: **`COMMON_BRIEF.md`** — read it before implementing.

## The objective

One structured meshing method that runs unattended, robustly, across the production
design space. Not a well-documented catalogue of failures. If a strategy is close to
passing, finish it.

**Success:** a strategy that passes every hard gate on all ten geometries of
`round_c_lhs10_seed42` at its own calibrated settings, with laws that extend it to
the full DSE.

## Why this replaced `04_strategy_prototypes/`

Stage 02 ran the six strategies as variants of a shared implementation. The tip
closure was built once and inherited by all of them, so S3, S4 and S5 converged on
S1's cap and scored identically — S4 was bit-identical to S1 to `0.000e+00` on all
ten geometries. **The tournament compared one topology wearing four labels.**

Here, each strategy is implemented from scratch in its own folder, developed to the
best state it can reach, and only then compared on metrics frozen in advance.

`04_strategy_prototypes/` is retained **unchanged as the archived Stage 02 record**.
Nothing here imports from it.

## Layout

```
COMMON_BRIEF.md            Stage 02 lessons, given to all six up front
migrate_from_stage02.py    provenance record of the ADR-0011 section 4.1 migration
shared/                    the experimental control — see shared/__init__.py
  ingestion.py             section reading, 2D->3D mapping   (no chordwise defaults)
  qc.py                    QC metric DEFINITIONS, orientation, artifacts
  gates.py                 thresholds and the frozen checklists
  geometry_sets.py         locked sets; the hold-out is guarded
  pyhyp_runner.py          the pyHyp invocation; prepare / collect
  verify.py                the verifier, with all six instrument bugs fixed
  export_paraview.py       VTK with per-cell quality
S0_cap4/  S1_tip_first/  S2_cross_field/
S3_station_sweep/  S4_analytic_multiblock/  S5_frozen_rbf/
    <implementation>       written from scratch, per strategy
    STUDY.md               the log: paper-vs-invented, attempts, results, ledger
    artifacts/             this strategy's outputs
```

## The independence line, in one sentence

Geometry is generated the same way for every strategy; **how each turns it into
blocks is the experiment.** Blocking, tip closure, spanwise and chordwise laws,
smoothing and staging are per-strategy. Ingestion, QC definitions, thresholds, the
pyHyp invocation, the geometry sets and the verifier are shared.

If a strategy genuinely cannot work within that line, record it as a finding and
raise it. Do not resolve it by copying code across the line.

## Order and pace

**S0, S1, S2, S3, S4, S5** — declared in advance so it cannot be reordered after
seeing results. S2's feasibility question is resolved early, in parallel with S0.

**The user decides when a strategy is done.** No budget is declared in advance;
Claude Code reports state and waits. No strategy is started and none is frozen
without an explicit user signal. Because effort is not capped, it is **measured** —
each `STUDY.md` carries an effort ledger, mirrored into `status`, and reported
alongside results in every comparison table.

## Geometry sets

| set | role |
|---|---|
| `lhs100_seed42` | development and refinement — baseline, then a subset, then widen |
| `round_c_lhs10_seed42` | **HOLD-OUT. Untouched. No tuning, ever.** Run once, after freeze. |
| `epse_calibration_lhs10_seed7` | Stage 01/02 evidence basis; permitted only for a declared like-for-like comparison |

Robustness is ranked on the hold-out, never on the refinement set — otherwise the
top-ranked criterion becomes a proxy for effort.

## Usage

```python
import sys
from pathlib import Path
STUDIES = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDIES.parents[1] / "src"))
sys.path.insert(0, str(STUDIES))

from shared import geometry_sets, gates, pyhyp_runner, verify
from shared.ingestion import section_loop_2d, feature_split_sides
from shared.qc import qc_blocks, orient_blocks_consistently
```

Heavy compute is prepared, never launched in-session: `pyhyp_runner.prepare` writes
the run inputs and returns the commands; the user launches them;
`pyhyp_runner.collect` reads them back and applies the frozen checklist.
