# S8 — complete desktop plan: grid convergence, ten geometries, TMR validation

**Written 2026-09-06; execution status refreshed 2026-09-07.** This file remains the
self-contained campaign plan. The status block below is authoritative where it conflicts
with older prose later in the document.

## Execution status — 2026-09-07

- **Far-field/domain sensitivity is complete.** The tracked 40→60 chord test at α=0 gives
  ΔCL = −2.49e−5 and ΔCD = +6.92e−5.
- **ONERA M6 solver validation is complete on the tracked delivered-grid comparison.**
  The tracked report gives mean shock-position error 0.01496 x/c, mean suction-peak
  relative error 1.025%, and mean RMS ΔCp 0.3239 across the seven stations. This validates
  the solver configuration against external experiment; it does not validate the S8 mesher.
- **The S8 coarse and medium four-angle sweeps are complete and accepted.**
  `gci_C` and `gci_M` both have α = −2, 0, 4, 8 accepted by the current gate.
- **The S8 study is still two-level only.** All current `s8_gci_a*.json` reports correctly say
  `TREND_NOT_GCI`. The missing publication-critical step is `gci_F` at the same four α.
- **Fine-grid robustness is 61/61 clean so far at `gci_F`.** Finish the remaining 39.
- **Immediate order:** finish the `gci_F` robustness screen → run four `gci_F` CFD points
  → compute real three-level GCI → select/freeze the production level → run the ten-geometry
  pilot → freeze policy → unlock the untouched holdout.
- The tracked ONERA comparison report is a delivered-grid result. No tracked three-level
  ONERA GCI report exists; do not imply one unless those additional artifacts are committed.


**Everything runs on 6 MPI ranks.**

---

## 0. What this project has already learned. Read this first.

Not general advice. Each cost real time here, and each has a number.

### 0.1 A metric that passes is not the metric that matters

Defect 21: the span-normal marching plane moved the wing surface by
**1.194e-03 m**, the same order as the 1.0 mm blunt trailing edge. Wall
orthogonality (1.083 vs 1.085 deg), first-cell height, scaled Jacobian, inverted
cells, cell count — **every metric being checked was unchanged.** They measure
cell *shape*. Nothing measured cell *position*.

> **Rule.** After any structural change run `compare_meshes.py`, which computes
> 37 metrics grouped by the question each answers: geometry, validity, quality,
> resolution, topology. Never hand-pick a subset after the fact.

### 0.2 Never mutate code while a measurement is running

Twice. A memory probe launched over a live rank sweep summed both processes and
read 11.86 GiB for something that was not. The wall-guard's negative test, which
deliberately breaks `march_o.py`, ran during the 100-design screen; index 3 was
built inside that ~40 s window and reported a false failure.

> **Rule.** One measurement at a time, on an otherwise idle machine.

### 0.3 Exit code 0 does not mean success

S7 defect 12: ADflow handles SIGTERM cleanly, so a run killed at iteration 1853
of 8000 wrote `"exit": 0`. S8 defect 19: `build_volume` wrote a mesh with **645
folded cells** and exited 0, because the fold check was in-plane per section and
the folds were between sections.

> **Rule.** Check the thing itself. Both are now guarded; the pattern will recur
> somewhere new.

### 0.4 A quantity the acceptance metric cannot see will drift

Defect 15: leading-edge spacing stepped **2.6x between adjacent stations** while
`worst_le_turn_per_cell_deg` reported success, because every station individually
met 10 degrees. The number that would have shown it was computed and discarded.

### 0.5 Solver defaults are not neutral

Defect 14: `solve_s8.py` omitted `liftIndex`, took ADflow's default of 2, and
**applied angle of attack as sideslip** on a span-+y mesh. Every result void,
nothing errored. Now verified before the solve, fail-closed.

ADflow's defaults are `NKSubspaceSize` 60 and `NKPCILUFill` 2; this project uses
**20** and **1**, roughly 3x leaner on Krylov memory. Do not "restore defaults"
to fix convergence without re-measuring memory.

### 0.6 Forces settling is not convergence

`alpha 4` froze its residual at **5.2371905e-05 to eight significant figures**,
NK step length 0.00, linear residual 1.000 — the Krylov solve had stopped
reducing. Its forces were stable to **9.2e-09**, five orders inside the limit,
*because nothing was happening.*

> **Rule.** `ACCEPTED_SOLVER_FROZEN` is reported separately from `ACCEPTED`, and
> **`gci.py` refuses frozen runs**: a stalled solver bounds no iterative error,
> and a GCI is meaningless unless iterative error is far below discretization
> error.

### 0.7 When a sign or a reference is in doubt, integrate the field

Defect 17: a reported CFD-vs-AVL stability disagreement was two sign errors
compounding. Hours of reconciling conventions; the convention-free check —
integrate `-cp n dA` and `r x dF`, take `x_np = -d(M_y)/d(F_z)` — settled it in
minutes and agreed with both codes.

### 0.8 Refinement does not fix everything, and can make it worse

The fold defect grew with refinement: index 65 went **645 → 1438 → 3253** folds
up the ladder. "Refine until it goes away" would have burned compute backwards.

### 0.9 Cheap and expensive are not where you think

Meshing is **12 s** per design; a four-angle polar is **~2 hours**. Meshing is
0.2 % of a campaign, so mesher choice is not a throughput decision. **100 designs
is ~8 days of solving; 1000 is ~80.** That arithmetic shapes the campaign, not
the mesher.

### 0.10 Use the right formula for unequal refinement ratios

The first draft of this plan gave `p = ln|(f3-f2)/(f2-f1)| / ln(r21)`, valid only
for equal ratios. This family's differ by ~0.6 %. On a manufactured second-order
solution that formula returns **p = 1.852 against a true 2.000** — a 7.4 % error
in the observed order, and a correspondingly wrong extrapolation and uncertainty
band, after hours of solver time. `gci.py` solves the generalised ASME relation
numerically and was verified to recover p = 1, 2 and 3 to within 1e-10.

---

## 1. State on 2026-09-06

| | |
|---|---|
| design-space meshing | **100/100 build, 100/100 valid**; determinism gate passes |
| wall position | 2.22e-16 m from the exact loft, guarded at 1e-9 |
| frame mode | `span_normal` default; `svd` selectable; pre-fix tagged `s8-svd-frame-baseline` |
| CFD | 4 angles on index 83, **on meshes that no longer exist** |
| grid convergence | not started — this plan |

**Nothing from the previous CFD sweep may be quoted.** Regression reference only
(§3.2).

---

## 2. The grid family

Memory is `1.51 GiB + 9.46 GB per million cells`, from two clean measurements
with NK engaged. Verified builds on index 83:

| level | cells | inverted | wall error | memory |
|---|---|---|---|---|
| `gci_C` | 567,256 | 0 | 2.2e-16 m | 6.9 GiB |
| `gci_M` | 1,111,152 | 0 | 2.2e-16 m | 12.0 GiB |
| `gci_F` | 2,217,680 | 0 | 2.2e-16 m | **22.5 GiB** |

A 299k level was generated and **rejected**: too coarse to be credibly asymptotic
for a wall-resolved BWB, and a GCI anchored on a non-asymptotic coarse grid is
worse than none.

### 2.1 Pick the third level from ACTUAL available RAM, not installed RAM

`gci_M` at 12.0 GiB leaves little room on a nominal 16 GB machine once the OS,
MPI runtime, Python and filesystem cache are counted.

```bash
free -g | awk '/^Mem:/ {printf "total %s GiB, AVAILABLE %s GiB\n", $2, $7}'
```

Then:

- **available ≥ 26 GiB** → use `gci_C / gci_M / gci_F`. Best family; r ≈ 1.251,
  1.259.
- **available 14–26 GiB** → `gci_F` will not fit. Generate an intermediate:

  ```python
  # in strategy_s8.py, alongside the other gci_* entries
  LEVELS["gci_MF"] = refined_level(LEVELS["oh_L3"], GCI_RATIO ** 1.5, name="gci_MF")
  ```

  giving ~1.6 M cells at ~16.6 GiB, and use `gci_C / gci_M / gci_MF`. Note r then
  falls to about 1.13 between the top two, which **weakens the GCI** — a small r
  makes the observed order noisy. Prefer finding a bigger machine.
- **available < 14 GiB** → two levels only. That is a trend, not a GCI. Say so.

Whatever is chosen, verify each level builds with `0 folded hexes` and
`wall_layer_error_m` near 2e-16 before solving on it.

### 2.2 The refinement ratio is NOT 1.300 — and the family is not uniform

`o_wing` refines at 1.30 in all three directions; `o_out` and `cap_out` do **not**
refine spanwise (47, 48, 49, 50 — a far-field growth law). `o_out` is 49 % of
cells at the coarse level and less at the fine, and that shifting fraction is the
whole 1.30-vs-1.25 gap.

> Describe this honestly as **systematic near-body refinement with weak
> far-field refinement**, not as a globally uniform family. Using the smaller
> global r usually widens the GCI band, but that does not make the whole
> procedure provably conservative. A single far-field sensitivity run — same
> grid, `farfield_chords` 40 → 60 — would make it much easier to defend, and is
> cheap. Do it once, at `gci_C`, α = 0.

`gci.py` takes the ratios from the cell counts; do not pass 1.300.

---

## 3. Grid convergence on index 83

### 3.1 Build and write CGNS

```bash
cd <repo>
R=$(pwd)
LEVELS="gci_C gci_M gci_F"      # or gci_MF per §2.1

for L in $LEVELS; do
  .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/build_volume.py \
    --level $L --index 83 --out $R/AERIS_MESH_STUDY/artifacts/s8_gci83
  /home/mike/miniconda3/envs/mach-aero/bin/python \
    AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/write_cgns.py \
    --blocks $R/AERIS_MESH_STUDY/artifacts/s8_gci83/${L}_blocks.npz
done
```

### 3.2 The regression run, ALONE, before anything else

The frame change moved every cell. This checks the whole chain.

```bash
/home/mike/miniconda3/envs/mach-aero/bin/mpirun -np 6 \
  /home/mike/miniconda3/envs/mach-aero/bin/python \
  AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/solve_s8.py \
  --grid $R/AERIS_MESH_STUDY/artifacts/s8_gci83/gci_C_volume.cgns \
  --alpha 0.0 --out $R/AERIS_MESH_STUDY/artifacts/s8_cfd/gci_C_a0 \
  --i-have-authorization
```

| | pre-fix `oh_L3` | acceptable |
|---|---|---|
| CL | −0.159963 | 3rd–4th decimal shift is the mesh |
| CD | 0.020838 | **2nd-decimal shift is a problem — stop** |
| CDp | 0.011841 | |
| CDv | 0.008996 | |
| CMy | +0.001280 | |

Confirm `result.json` carries `flow_directions` with `lift_index_realised: 3`
and `velocity_direction_error: 0.0`.

### 3.3 The sweep: four angles on every level

**α ∈ {−2, 0, 4, 8}** on all three levels — twelve runs.

Four angles rather than two because the outputs that matter here are
`dCMy/dCL` and `x_np`, and two points define a line by construction. Four give a
slope with residual, at every grid level, so the *stability derivative* gets a
convergence study rather than just the pointwise coefficients.

**α = 4 is expected to be the difficult one** — it is the point that froze
before. Run it, record what happens, and let `gci.py` refuse it if the gate says
`ACCEPTED_SOLVER_FROZEN`. Whether the stall recurs on the rebuilt meshes and at
other levels is itself a result.

```bash
for L in $LEVELS; do
  for A in -2 0 4 8; do
    [ "$L" = "gci_C" ] && [ "$A" = "0" ] && continue     # done in 3.2
    /home/mike/miniconda3/envs/mach-aero/bin/mpirun -np 6 \
      /home/mike/miniconda3/envs/mach-aero/bin/python \
      AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/solve_s8.py \
      --grid $R/AERIS_MESH_STUDY/artifacts/s8_gci83/${L}_volume.cgns \
      --alpha $A --out $R/AERIS_MESH_STUDY/artifacts/s8_cfd/${L}_a${A} \
      --i-have-authorization
  done
done
```

Sequentially (§0.2). Roughly 8–14 hours depending on the third level.

### 3.4 Gate, extrapolate, cross-check

```bash
.venv/bin/python .../convergence_gate.py \
  --runs 'AERIS_MESH_STUDY/artifacts/s8_cfd/gci_*_a*' \
  --out AERIS_MESH_STUDY/05_s6_cfd_qualification/reports/s8_gci_gate.json

for A in -2 0 4 8; do
  .venv/bin/python .../gci.py \
    --runs "AERIS_MESH_STUDY/artifacts/s8_cfd/gci_*_a${A}" \
    --cells '{"gci_C":567256,"gci_M":1111152,"gci_F":2217680}' \
    --gate AERIS_MESH_STUDY/05_s6_cfd_qualification/reports/s8_gci_gate.json \
    --out AERIS_MESH_STUDY/05_s6_cfd_qualification/reports/s8_gci_a${A}.json
done

.venv/bin/python .../verify_against_avl.py --index 83 --alphas -2.0 0.0 4.0 8.0 \
  --out AERIS_MESH_STUDY/artifacts/s8_cfd/avl_83
.venv/bin/python .../locate_cp_excess.py \
  --surface AERIS_MESH_STUDY/artifacts/s8_cfd/gci_F_a8/s8_a8_000_surf.cgns --le-index 74
```

**Reading the result.**

- `gci.py` reports the observed order `p`, the extrapolated value and the GCI
  band per function, and states the condition when the triplet is not usable.
- **Do not expect `p ≈ 2`.** RANS on stretched grids frequently gives observed
  orders below the nominal spatial order. **A positive, stable, monotonic trend
  matters more than `p` landing near 2.** `gci.py` flags `p` outside 0.5–4 and
  flags oscillatory (`e32/e21 < 0`) triplets; report those conditions rather
  than quoting a band.
- **`gci_C/M/F` is provisional until asymptotic behaviour is demonstrated.** If
  the triplet misbehaves, the answer is a finer family on a bigger machine, not
  a forced number.
- **Also extract `dCMy/dCL` and `x_np` per level** from the four angles, and
  report how they converge. That is the stability-relevant result.
- **Record over-bound cp counts at α=8 across levels.** 36 at `gci_C` before. If
  they fall with refinement the leading-edge excess is discretization; if flat,
  structural.

### 3.5 Choose the campaign level

Pick the coarsest level whose GCI band is acceptable for a surrogate-training
dataset (not certification). Record the choice and its justification.

**Expect CD and CMy to need a finer level than CL.** CDp moved 5.2 % and CMy 18 %
from a single respacing; CL is far less sensitive. Running the campaign at a
level converged for lift while carrying a stated uncertainty on drag and moment
is legitimate — provided it is stated.

---

## 4. Ten geometries

### 4.1 The ten, chosen by maximin over normalised design variables

```
12, 13, 16, 23, 65      former folders — the fix exists for these, never CFD'd
83                      reference, continuity with all prior work
29, 36, 47, 81          maximin space-filling over the 20 normalised DVs
```

Coverage — worst distance from any of the 100 designs to its nearest chosen one,
lower is better:

| set | coverage |
|---|---|
| **these ten** | **1.6918** |
| random ten, median of 200 | 1.7768 |
| first ten (0–9) | 1.8294 |
| the old S6/S7 representative five | 1.8664 |

Reproduce with the snippet in `AUDIT_2026-09-05.md`, or re-run maximin if the
seed set changes.

### 4.2 Run

At the level chosen in §3.5, α ∈ {−2, 0, 4, 8}, plus AVL per geometry.

```bash
LEVEL=<CHOSEN>
for i in 12 13 16 23 29 36 47 65 81 83; do
  D=$R/AERIS_MESH_STUDY/artifacts/s8_pilot/g$i
  .venv/bin/python .../build_volume.py --level $LEVEL --index $i --out $D
  /home/mike/miniconda3/envs/mach-aero/bin/python .../write_cgns.py \
    --blocks $D/${LEVEL}_blocks.npz
  for A in -2 0 4 8; do
    /home/mike/miniconda3/envs/mach-aero/bin/mpirun -np 6 \
      /home/mike/miniconda3/envs/mach-aero/bin/python .../solve_s8.py \
      --grid $D/${LEVEL}_volume.cgns --alpha $A --out $D/a$A --i-have-authorization
  done
  .venv/bin/python .../verify_against_avl.py --index $i \
    --alphas -2.0 0.0 4.0 8.0 --out $D/avl
  .venv/bin/python .../convergence_gate.py --runs "$D/a*"
done
```

Check the gate after each geometry, not at the end.

### 4.3 What the pilot actually tests

1. **Does the solver converge across geometries**, or does the α=4 stall recur?
   Undiagnosed, and the biggest unknown here.
2. **Does the CFD–AVL relationship hold across the design space?** On index 83
   the gap closed monotonically with incidence to 1.9 % at α=8. If that holds on
   ten designs, the multifidelity correction is viable. **If it varies wildly by
   geometry, the surrogate strategy needs rethinking** — far cheaper to learn now
   than after 100 designs.
3. **Does y+ stay in band as planform varies?** 0.56 at p95 on index 83; nothing
   guarantees that on a very different chord distribution.

### 4.4 Dataset schema — fix before the first pilot case

Retrofitting provenance is far harder than recording it. Scalars are not enough:
the eventual goal is **AI field prediction**, which needs the fields and their
identity.

```
# identity and provenance
geometry_set, geometry_index, geometry_hash, design_vector,
mesher, frame_mode, grid_level, cells, mesh_hash,
git_commit, adflow_version, turbulence_model, solver_options_hash

# operating point and references
alpha_deg, beta_deg, mach, reynolds, temperature_K,
area_ref, chord_ref, moment_ref_xyz

# results
CL, CD, CDp, CDv, CMy, CMx, CMz

# convergence, all of it
gate_verdict, relative_residual, orders_dropped, iterations,
cl_pct, cd_pct, cmy_abs,           # force-tail spreads
lift_index_realised, velocity_direction_error

# mesh state
wall_layer_error_m, inverted_cells, worst_le_turn_deg,
min_cell_over_s0, scaled_jacobian_min_p001_p01

# physics checks
yplus_min_p50_p95_p99_max, cp_cells_over_bound, cp_peak_excess

# fields, for the AI work
surface_field_path, volume_field_path,
node_ordering, connectivity_hash

# low fidelity
avl_cl, avl_cd, avl_cm, avl_status
```

---

## 5. Validation against TMR experimental data

Cross-method agreement with AVL is **not validation**. S8 currently has none.

**Validate the solver configuration, not the mesher.** The two are separable and
should be separated: S8's mesher only builds AERIS BWB lofts, so it cannot mesh a
wind-tunnel wing, but the ADflow setup this project uses — RANS-SA, `liftIndex 3`,
ANK→NK, `NKSubspaceSize 20`, `NKPCILUFill 1`, the convergence gate — can be run
on a published case with published grids.

**Recommended case: ONERA M6 wing** (NASA Turbulence Modeling Resource). Standard
3-D transonic validation case, experimental surface pressures at seven spanwise
stations (Schmitt & Charpin 1979), and TMR publishes structured grid families.

```
M = 0.8395,  alpha = 3.06 deg,  Re = 11.72e6 based on mean chord
```

Steps:

1. Download the TMR ONERA M6 structured grid family.
2. Run this project's `solve_s8.py` option set unchanged, on 6 ranks, at three
   grid levels.
3. Compare surface `cp` against the experimental stations, and CL/CD against the
   TMR reference solutions.
4. Run `gci.py` on the three levels — it validates the GCI machinery on a case
   with a known answer.

**What this does and does not establish.** It establishes that the *solver
configuration and the convergence gate* produce results consistent with published
data and other codes. It does **not** validate the S8 mesher, which no public
experimental case can, because no public case is an AERIS BWB. Say both.

A second, cheaper check worth doing: the operating point here is M 0.0837, far
from M 0.84, so if a low-speed TMR case is available it is a better match for
Reynolds and compressibility regime. Note the discrepancy explicitly if only the
transonic case is run.

---

## 6. Authorization

`POLICY.yaml` blocks heavy work. `run-s8-corrected-sweep` covers **`oh_L3` only**
and is consumed. This plan needs a new signed entry covering: grid convergence on
index 83 at three levels, the ten-geometry pilot, and the TMR validation runs. It
does **not** authorize a hold-out unlock, a family freeze, or a paper claim.

`round_c_lhs10_seed42` stays locked.

---

## 7. Known-open problems — refreshed 2026-09-07

1. **The third S8 grid is still missing from the solved family.** `gci_C` and `gci_M`
   are a refinement trend only. `gci_F` at α = −2, 0, 4, 8 is the immediate
   publication-critical numerical-verification step.
2. **Pressure drag is still strongly grid-sensitive.** At α=0 the C→M change is
   about 15.8% in CD and 30.3% in CDp. The third level decides whether the family is
   entering a usable asymptotic regime and which level can support the campaign.
3. **Leading-edge resolution remains operating-point dependent.** Re-evaluate the
   over-bound Cp-cell count at α=8 on `gci_F`; the trend across C/M/F determines
   whether the excess is principally discretization-driven.
4. **The blunt trailing-edge corner remains a known C0 feature.** Prior sensitivity
   showed negligible practical influence relative to the main pressure-drag issue;
   leave it unchanged unless new evidence contradicts that conclusion.
5. **Far-field/domain sensitivity is closed.** The 40→60 chord test moved CL by
   −2.49e−5 and CD by +6.92e−5 at α=0.
6. **ONERA M6 external validation is closed for the tracked delivered-grid solver
   comparison.** Keep the limitation explicit: it validates the solver configuration,
   not the S8 mesher, and it is transonic whereas the AERIS campaign is low-speed.
   The repository does not currently contain a three-level ONERA GCI report.

---

## 8. Files

| | |
|---|---|
| this plan | `PLAN_desktop_campaign.md` |
| technical audit | `AUDIT_2026-09-05.md` |
| current state | `STATUS_AND_NEXT_STEPS.md` |
| **GCI, unequal ratios** | **`gci.py`** — verified to 1e-10 on manufactured p = 1, 2, 3 |
| mesh comparison, 37 metrics | `compare_meshes.py` |
| memory measurement | `measure_memory.py` |
| convergence gate | `convergence_gate.py` |
| cp bound locator | `locate_cp_excess.py` |
| AVL cross-check | `verify_against_avl.py` |
| robustness screen | `robustness_screen.py` |
| plots | `plot_sweep.py` |
| pre-fix baseline | git tag `s8-svd-frame-baseline` |

**`artifacts/` is gitignored and gets wiped.** Keep results in
`05_s6_cfd_qualification/`; images need `git add -f`.
