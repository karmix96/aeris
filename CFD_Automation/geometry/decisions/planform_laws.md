# Planform laws: cranked and tapered wings

Decided 29 Oct 2026 (Mike): the generator must make tapered wings.

| choice | value | why |
|---|---|---|
| Three wing types | `bwb`, `conventional` (cranked: chord and sweep may change at b1 and b2), `tapered` (straight edges root to tip) | With chords and sweeps drawn freely, a straight taper has zero chance: 100 of 100 conventional training wings came out cranked, none tapered. Rectangular and plain tapered wings are the most common real wings. |
| `tapered` | `chord_law: linear_taper` (c4 = tip/root, c2 and c3 follow) and `sweep_law: one` (sweep2 = sweep3 = sweep1) | Linear chord and one leading-edge sweep give straight leading and trailing edges. Taper 1 gives a rectangular wing. Stations b1 and b2 stay, because twist and dihedral may still change there. |
| `conventional` (cranked) | `chord_law: per_panel`: c2 = c(b1)/c(b0), c3 = c(b2)/c(b1), c4 = c(b3)/c(b2), each 0.5-1 | Before, 46 of 100 wings got wider toward the tip on at least one panel (c2, c3, c4 drawn as independent fractions of the root chord). With each panel's own taper at most 1, no chord grows outboard, and the Latin hypercube stays intact (no rejection, no clipping). |
| Same 18 variables | unchanged; a law marks what it computes (`derived`), and those variables need no range | One vector shape for all types. |
| BWB | unchanged (`chord_law: stations`, `sweep_law: panels`) | Its ranges already never grow outboard. |

Check: `tests/geometry/test_planform.py` (no chord grows outboard on 500 cranked wings; leading and
trailing edges straight on 200 tapered wings; resolve is idempotent).

Open: the mixed shares (BWB 0.5, cranked 0.25, tapered 0.25) are our choice.
