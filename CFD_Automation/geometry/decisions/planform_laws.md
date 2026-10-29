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


## Aspect ratio as the size input (29 Oct 2026, Mike)

| choice | value | why |
|---|---|---|
| `span_mode: aspect_ratio` for every type | `root_chord_m` and `aspect_ratio` are sampled; semi-span S = AR · c_root · K / 2, K = mean chord / root chord = Σ f_i (r_i + r_i+1) / 2 | Drawing the span in root chords and the taper separately let wings with a tail reach AR 21 (13 % of cranked, 11 % of tapered above 16.5, the highest real value). Drawing AR keeps every wing inside the real range by construction: no refusals, Latin hypercube intact. |
| AR ranges | tailless (bwb, flying_wing) 3–9 (real 2.9–8.6); with a tail (conventional, tapered) 4.5–16.5 (real 4.9–16.0; 16.5 at 630 kg) | from the real wings with a published area (`configs/real_uavs.yaml`) |
| Variables | still 18 names: `semi_span_m` and `aspect_ratio` are both in the vector, one sampled and one derived | one vector shape for every type; `semi_span` and `root_chord_fractions` modes stay for published wings |

Check: the vector gate measures the aspect ratio on the loft and compares it with the vector (0.1 %).

## Flying-wing type (29 Oct 2026, Mike)

`flying_wing`: tailless, `linear_taper` (taper 0.3–0.8) and `sweep_law: one` (10–35°), AR 3–9, root chord
0.25–1.05 m, washout, panel dihedral 0–5°, reflexed sections MH 45 / MH 60. Why: the Lockheed Aquila
(taper 0.58, LE sweep 28°, mean chord 0.78 m) fitted no type, and plain swept flying wings are the most
common small tailless UAVs. Sizes from the real tailless wings; taper, sweep, twist, dihedral and
sections are our choice.

## Shares (29 Oct 2026, Mike)

`mixed` draws the four types with equal shares (1/4 each), split by largest remainder.
