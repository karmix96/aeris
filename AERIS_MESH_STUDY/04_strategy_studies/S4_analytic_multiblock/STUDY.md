# S4 — geometry-driven analytical multiblock

**Status: COMPLETE.** Surface, tip closure and a directly-constructed boundary-layer
volume, all built and measured across the ten development geometries. S4 **passes
every surface condition that any strategy currently passes** and **fails the volume
gate**, in one place, for a reason that is now understood exactly.

**Strategy ID:** `S4_ANALYTIC_MULTIBLOCK`
**Source:** *Automatic Generation of 3D Parametric Multi-Block Topology and
Structured Mesh for Wings*, Applied Sciences 2026, 16, 7588, §§2.1–2.3.
**Governance:** ADR-0011 (rules), **ADR-0014** (the non-pyHyp volume gate, written
and verified before any S4 volume existed).

---

## 1. What S4 was for

RUNBOOK §6 S4: *"Generate the volume directly using TFI/elliptic/Poisson methods; do
not require pyHyp for this candidate."*

S0, S1 and S3 were all decided by the same mechanism — whether the near-wall march
survives, and whether the spanwise cells match the tip cap at the interface. S4 has
no march: its boundary-layer block has explicitly placed outer vertices, so near-wall
spacing is *constructed*. That made it the last genuinely independent entrant, and
the only one that could have failed for a different reason than the others.

It did fail for a different reason. Not the one the implementation note predicted.

## 2. The primary predicted risk did not materialise

The note names S4's failure mode: *"Bad Type 2 or Type 3 placement can create
self-intersections or nearfield block collapse."* Tested first, on 5 geometries ×
17 stations × 8 vertices = **680 normal advances**: **zero crossings**, minimum Type 2
spacing 0.039–0.045c. The paper's claim that `delta = 0.06 c_local` "maintains a safe
margin against normal-vector intersection" holds on AERIS sections, blunt trailing
edge included.

The averaged TE normal correction (Eq. 5) matters more here than in the paper,
because AERIS has two blunt-base corners rather than one sharp TE; without it the two
corner normals point nearly opposite and their advances cross immediately.

## 3. S4's one structural contribution: the third tip construction

ADR-0013 §2 recorded a result reached three times independently — capping a thin
blunt-TE contour with structured quads needs an O-H ring whose **opposite arcs carry
equal counts**, forcing the nose wrap and the 1.0 mm base to the same size, and
"there are essentially two ways to satisfy it", S0's and S1's.

**There is a third, and the paper states the rule.** §2.3.1: *"A mesh domain is
defined by four boundary edges connected end-to-end, and a single boundary edge may
consist of multiple control edges."* The equality the ring needs is between
**boundary edges**, not individual arcs. Group the eight Type-1 arcs into four
boundary edges and the constraint becomes two equalities between *sums*, so the base
count is chosen on physical grounds and the difference is absorbed by a long
neighbouring arc where four points either way changes nothing.

It works, and it is measurable:

| | S0 | S1 | **S4** |
|---|---:|---:|---:|
| boundary-edge points | — | — | **23 / 22 / 23 / 22** |
| base points | tied to the nose wrap | tied to the nose wrap | **3, chosen** |

## 4. And the price it pays — the finding

Grouping the base into a boundary edge costs a *ring corner*. The section has exactly
**two** sharp corners — the two blunt-TE base corners — and putting a ring corner on
both isolates the base as its own boundary edge, which is the constraint the grouping
exists to escape. So at most one of them can be a ring corner, and the other three
have to be taken from smooth stretches of the contour.

Interior angle at each of the eight Type 1 vertices, **identical on every geometry
measured**:

| v0 | v1 | v2 | v3 | v4 | v5 | v6 | v7 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 114.0° | 179.0° | 178.2° | 176.3° | 176.8° | 179.3° | **180.9°** | 73.2° |

Two consequences, both confirmed by exhaustive search over all admissible rings:

1. **v6 is reflex** (180.9°). Every ring containing it folds exactly one core cell,
   at −0.01523, on every geometry. Every ring without it is positive. This is not a
   tuning effect: `core_shrink` cannot change it, because a similarity preserves
   angles, and 400 Winslow iterations cannot change it, because Winslow does not move
   boundary nodes and a reflex corner in a structured patch always folds its corner
   cell.
2. **The cap's minimum scaled Jacobian is `sin(180° − flattest ring corner)`.** With
   the selected ring `(1, 3, 5, 7)` the flattest corner is v5 at 179.31°, and
   sin(0.69°) = **0.0120**. The measured value is **0.01198**.

So the ceiling is arithmetic, not effort. The best ring that avoids v6 and does not
isolate the base or the nose has a flattest corner of about 1°, and no cap built on
this contour with four corners can beat roughly 0.012–0.018.

**The trade, stated plainly.** S0 and S1 keep the sharp corners — S1 by *creating*
them, with short end edges that cross the section — and pay in cell-size range,
because the base count is then tied to the nose wrap. S4 frees the base count and
pays at the corners. **They are two ends of the same constraint, and this is the
first time the study has been able to write down what the exchange rate is.**

## 5. Selected configuration

| parameter | value | why |
|---|---|---|
| ring corners | `(1, 3, 5, 7)` | exhaustive search over all 4-subsets; avoids the reflex v6, includes v7 (73.2°, the sharpest corner available), balanced edges 23/22/23/22 |
| boundary edges | `(upper_mid, upper_fore) (nose, lower_fore) (lower_mid, lower_aft) (base, upper_aft)` | §2.3.1 grouping; base travels with `upper_aft`, nose with `lower_fore` |
| `core_shrink` | 0.75 | affects the collars only — provably not the core, since a similarity preserves angles |
| `shape_alpha` window | none | a corner window was built and measured; it made the collars worse (−0.017 to −0.021) |
| `corner_pull` | 1.0 | swept 0.50–1.50; changes the answer by < 0.004 in either direction |
| `core_smooth_iters` | 400 | Winslow; converges by ~200 |
| spanwise | uniform target cell, **not** tip-anchored | §6 |
| `delta` | 0.06 c_local | Eq. 2 verbatim |

## 6. The spanwise law, and a fourth confirmation of the study's central result

S1's spanwise law anchors the first cell to the tip cap's radial cell, and that match
is what makes S1 march. S4 does not march, so adopting it would be importing a fix for
a problem S4 does not have; S4 uses a uniform target cell instead, and the question of
whether the interface match still matters becomes a measurement.

**It does not.** S4's OML boundary-layer blocks, built with no tip anchoring at all,
have minimum scaled quality 0.17–0.95 and mean 0.92–0.98 with zero inverted cells.
The tip interface is not a problem for a constructed volume.

That is the fourth independent confirmation of the study's central result, and it
sharpens it: **the tip-interface match is a property of hyperbolic marching, not of
the mesh.** S1 needs it, S3 died without it, and S4 does not need it because nothing
is marching through the interface.

## 7. Results

### 7.1 Surface, ten development geometries, `L2_smoke`

| | S4 | S1, same geometries |
|---|---:|---:|
| blocks | 13 | 13 |
| built | **10 / 10** | 10 / 10 |
| watertight tip | **10 / 10** | 10 / 10 |
| deterministic connectivity | **True**, 1 signature | True |
| dimensions adapt | True, 8 dimension sets | True |
| worst min scaled Jacobian | **+0.01054** | +0.236 |
| cell-size range | 198 – 426 | 114 |
| geometry fidelity (verified columns) | **8.7e-05** of local chord, gate 1.0e-4 | — |

**Surface gate: FAIL on all ten, for the one open cross-cutting item** — fidelity is
unverified for spanwise-refined blocks (COMMON_BRIEF §5). That condition currently
fails for *every* strategy including S1, and where fidelity *is* verified S4 measures
inside the gate. On every condition any strategy passes, S4 passes.

### 7.2 Volume, directly constructed, ADR-0014 route

Boundary layer only: Type 1 → Type 2, `delta = 0.06 c_local`, first cell `s0` matched
to the pyHyp levels so the near-wall spacing is the same physical requirement.

| block group | cells | inverted | min quality | mean quality |
|---|---:|---:|---:|---:|
| 8 OML blocks | ~163k | **0** | **+0.167 … +0.951** | **0.92 … 0.98** |
| 5 tip-cap blocks | ~23k | ~150 | −0.74 | 0.32 … 0.49 |

Across ten geometries: 143k–197k cells, mean scaled quality **0.827–0.895**, **96–98%
of cells at or above 0.30**, and 54–155 inverted cells (375 cells of negative *quality*
on geometry 000) — **all of them in the tip cap**, at the same j-index as the 179.3°
ring corner.

**Volume gate: FAIL 0/10.** The gate is strictly `> 0` and the tip cap is negative.

### 7.2.1 Refinement ladder, geometry 000

| level | blocks | cells | min scaled Jacobian | cell-size range | spanwise |
|---|---:|---:|---:|---:|---:|
| L1_coarse | 13 | 3,668 | 0.01236 | 191 | 58 |
| L2_smoke | 13 | 7,772 | 0.01198 | 295 | 79 |
| L3_medium | 13 | 17,244 | 0.01236 | 434 | 121 |
| L4_fine | 13 | 29,884 | 0.01236 | 587 | 151 |
| L5_production | 13 | 59,383 | 0.01236 | 834 | 200 |

Two things to read here. The minimum scaled Jacobian is **flat at 0.0124 under a 16x
cell-count increase**, which is the §4 result stated a second way: it is set by a
corner *angle*, and refinement does not change angles.

And the cell-size range **grows with refinement**, 191 to 834. That is the cost of
pinning the base at 3–5 points on physical grounds: every other arc gets finer and the
base does not, so the ratio between the largest and smallest surface cell widens. It
is a deliberate consequence of §3's freedom, not a defect, but a production mesh would
have to spend points on the base as it refines.

### 7.3 What that means next to S1

S1's own pyHyp volumes, scored through the *same* in-house instrument (ADR-0014 §3.4,
6 completed marches): min scaled quality **0.170–0.231**. S4's OML blocks reach
**0.167–0.951 with a mean of 0.92–0.98**.

So over the wing itself, a constructed volume is not merely competitive with a marched
one — it is better, and by a wide margin. S4 loses on the tip cap alone.

**Two cautions, both required by ADR-0014 §4.** Cell counts are not comparable: S4
builds the boundary layer, pyHyp marches to a far field. And the in-house metric and
pyHyp's `Quality` column are different definitions — measured at a stable ratio of
**0.585 to 0.660** across the sample — so numbers must never be compared across the
two instruments. Everything above compares in-house to in-house.

## 8. What was tried and rejected

| construction | measured | why it failed |
|---|---:|---|
| centroid-shrunk core, straight inner edges | −0.037 | a straight inner edge under a curved boundary edge shears the collar end to end |
| rectangular core at fixed chord stations | −0.87 | **135-combination sweep, no positive result at all.** On a reflexed section the aft corners landed above the TE ring corner they served, and the collar spokes crossed |
| Eq. 18 similarity core, `alpha` 0.3–1.15 | −0.0099 … −0.985 | best at `alpha = 1`, where Eq. 18 is exact; the fold is at a corner and alpha cannot move it |
| `corner_pull` 0.50–1.50 | −0.0115 … −0.999 | moves the answer by < 0.004; below 0.90 the inner edges self-intersect |
| corner window on the copied deviation | −0.017 … −0.021 | intended to make core corners construction-set rather than inherited; it flattens the collars instead |
| Winslow on the core, 0–1000 iterations | −0.044 → −0.015 | halves the folded cells and then plateaus; cannot move boundary nodes |
| unit-normalised node normals (Eq. 8 read literally) | 174 vs 147 inverted, **and a hard failure** | reverted. Eq. 8 governs the paper's Type 1 control-vertex normals, which `surface_normals` implements faithfully; applying it to the discrete surface-mesh normal field is a different object. On `lhs100_seed42_002` two blocks' unit normals at a shared node cancelled exactly and the field went degenerate — an outcome area weighting cannot produce |
| normal-field smoothing, 0/2/5 passes | 174 / 184 / 198 inverted | the fold is geometric, not a smoothness defect |

## 9. Instrument work this strategy required

ADR-0014 and `shared/volume_qc.py` exist because ADR-0011 §6.1's volume gate is
phrased in terms of pyHyp's report and S4 does not run pyHyp. Two things are worth
recording:

1. **The equivalence check earned its place immediately.** The first version of the
   hexahedral scaled Jacobian ordered its corner triple product so that "positive"
   meant the opposite of what `signed_cell_volumes` means by it. It passed a unit-cube
   test convincingly and scored every valid S1 volume at −1.0. ADR-0014 §3.4 caught it
   before a single S4 number existed.
2. **The 0.585–0.660 ratio is a finding the final report needs.** S1's volumes read
   0.193–0.364 through pyHyp and 0.170–0.231 through the in-house metric. Any table
   mixing the two would misrank the tournament.

## 10. Effort ledger

| metric | value |
|---|---:|
| distinct tip constructions built and measured | 6 |
| parameter combinations swept | 135 (tip) + 22 (rings) + ~40 (alpha/pull/window/shrink) |
| geometries | 10 development, 0 hold-out |
| marches run | **0** — by design |
| instrument defects found and fixed | 2 (Jacobian sign convention; spanwise-axis subdivision) |

## 11. Reproduce

```bash
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/shared/verify_volume_qc.py --sample 6
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S4_analytic_multiblock/run_s4.py surface
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S4_analytic_multiblock/run_s4.py volume
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S4_analytic_multiblock/run_s4.py levels
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S4_analytic_multiblock/search_s4_ring.py
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S4_analytic_multiblock/export_s4_volume.py
```

Artifacts in `artifacts/`; ParaView surfaces alongside the other strategies in
`AERIS_MESH_STUDY/artifacts/paraview_inspection/all_strategies_surface/`, volume in
`.../S4_volume/`.
