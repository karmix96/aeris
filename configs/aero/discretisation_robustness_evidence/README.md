# Evidence — discretisation robustness across the design space (Task 5)

Backs `studies/discretisation_master_study.md` and
`decision/0010-control-resolution-criterion.md`. Rescued from `data/` (wiped).

| file | what it is |
|---|---|
| `hinge_scout.json` | Hinge sweep 0.652–0.814 × chordwise {8,16,24,32} vs a chordwise-48 reference. The data that killed the "hinge/panel-edge coincidence" hypothesis and established `error ~ N_flap^-1.47` (R² 0.966). |
| `extremes.txt` / `.json` | Nine CONSTRUCTED extreme + simple designs at the production and economy grids vs a 33/4/20 reference. AR 2.25–7.85. Regenerate: `python standalone/lowfi_avl_study/extreme_designs.py` |
| `narrow_elevon_placement.txt` | Same 25-section budget, sections clustered toward the band edges. Shows the narrow-elevon error is misallocation, not insufficiency. Regenerate: `python standalone/lowfi_avl_study/probe_narrow_elevon_placement.py` |
| `grid_trade.txt` | Equal-cost grid trade. **CONFOUNDED — do not cite.** Its reference (25/2/48) shares candidate C's spanwise resolution, so part of the measured error is a spanwise mismatch. Kept for transparency; the question it asked is open. |

## Headline

- **Seven of nine extremes hold at ≤0.5 %** at 25/4/24, including AR 2.25 and 7.85,
  max sweep/twist/dihedral gradients, and both hinge bounds.
- **Both failures are elevon-BAND cases**; narrow band (0.70–0.85) gives 4.34 %.
- The unifying criterion: **N_flap ≥ 6** chordwise, **ramp fraction ≲ 15 %** spanwise.
  corr(ramp fraction, error) = **+0.978**.
- Clustering sections at the band edges recovers ~3.2 % of the 4.34 % **at the same
  section budget** — uniform spacing is misallocated, not insufficient.

## A correction this evidence forced

`hinge_scout.json` **refutes** the hinge/panel-edge-coincidence explanation that
was published in DECISION-0009 §4. Within-chordwise-level correlations between
hinge-to-edge distance and error are +0.611, +0.077, −0.040, −0.163 — inconsistent.
At `nchordwise = 24`, hinge 0.75 has exact edge alignment and 1.32 % error while
hinge 0.652 aligns worse and does better. DECISION-0010 replaces the mechanism.
