# ADR-0010 — Optimise for Marchability, Not Surface Shape Quality

Date: 2026-08-13
Status: Proposed for Stage 02 approval
Supersedes the implicit selection criterion used throughout Stage 02

## The evidence

Two surfaces, same geometry, same pyHyp settings, same code path:

| | min scaled Jacobian | cell-size range | min cell / s0 | march |
| --- | ---: | ---: | ---: | --- |
| cap4 | **+0.0046** | **153x** | **48.7** | **completes**, positive volumes, 54/128 low-quality layers |
| S1 (as built) | **+0.3250** | 3462x | 0.9 | **explodes at layer 2**, coordinates to 1e+24 m |

cap4's cell *shape* is 70x worse than S1's and it marches. S1's shape is
excellent and it cannot be marched at all.

The march log shows the mechanism directly: at layer 2 the linear solver hits
`kspMaxIts = 1500`, produces a small negative volume (-9.4e-09), and diverges by
twelve orders of magnitude per layer thereafter. An implicit hyperbolic solve is
conditioned by the *range* of cell sizes it must couple, not by how well shaped
any individual cell is.

## The mistake

Stage 02 was spent maximising the minimum scaled Jacobian: the tip-fold hunt
(~15 constructions), the camber-split cap, the collar tuning. Every gain came
from **subdividing the tip more finely**. Finer subdivision improves cell shape
and shrinks the smallest cell, and the smallest cell is what breaks the march.

The two objectives are in direct opposition. Measured, holding everything else
fixed:

| configuration | range | min scaled Jacobian |
| --- | ---: | ---: |
| te_base 9, collar 5 | 1068x | +0.3250 |
| te_base 5, collar 3 | 534x | +0.3119 |
| te_base 3, collar 3 | **396x** | +0.1363 |
| cap4 | **153x** | +0.0046 |

Range and shape trade monotonically. No setting reaches cap4's range while
keeping S1's shape, because they are the same knob pulled in opposite
directions. **The stage optimised the metric that does not determine success.**

## Decision

1. **Marchability is the primary surface criterion.** The two metrics that
   predict it, both now measured in `qc_blocks`:
   - `max_cell / min_cell` — the conditioning of the implicit solve
   - `min_cell / s0` — whether the first marching layer fits inside the surface
     cell it is pushed off
   Minimum scaled Jacobian remains a reported quality metric and a tie-break. It
   is **not** the selection criterion.

2. **The tip cap is designed for coarseness**, accepting a worse shape metric.
   Defaults change to `te_base_points = 3`, `collar_points = 3`, which is the
   best measured range at 396x.

3. **The spanwise law is enabled** (`realise_law = True`, target 0.010 m).
   cap4 — the working baseline — refines from 17 native stations to **255** by
   exactly the linear interpolation that was disabled here on fidelity grounds.
   Holding S1 to a standard the working baseline does not meet was inconsistent.
   The fidelity cost is real (measured at 7.4% of chord over two native
   intervals, and NOT an over-estimate) and is inherited from cap4's established
   practice; removing it for both is Stage 03 generator work, not a mesher
   change.

4. **Strategy ranking from Stage 02 is void.** S1 "winning" was measured on the
   wrong criterion. Any ranking must be redone on marchability once a strategy
   marches.

## Consequences

- The Stage 02 gate cannot be claimed on surface shape metrics alone. A strategy
  is not a candidate until it marches.
- Three gates have now been found missing in this stage and added: consistent
  normals, `min_cell` vs `s0`, and cell-size range. All three were caught by
  pyHyp or by measurement, none by the declared gate set.
- The runbook's Round A ("surface feasibility") is weaker than assumed: a surface
  can pass every stated surface gate and be unmarchable. Round A needs the two
  marchability metrics added before Stage 03.

## What this does not claim

It does not claim S1 is fixed. At the time of writing the reduced-range
configuration (396x, min/s0 6.0) has been staged and is marching; whether that is
sufficient is unknown. cap4 sits at 153x and 48.7, so S1 is still several times
worse on both. The decision above stands on the diagnosis regardless of that
run's outcome.
