# AERIS S7 Unstructured CFD — Master Execution Guide

**Status date:** 31 August 2026
**Execution constraint:** one desktop running WSL2; the same inventoried host as S6, so the memory budget is shared and the two must not run heavy work at once
**Primary pipeline:** pyGeo geometry → independent triangulated wall → marched prism layer → Gmsh tetrahedral core → native SU2 writer → SU2 8.5.0 RANS-SA
**Domain:** half model, `y >= 0`, closed at the root by a `symmetry` plane — the same domain S6 meshes
**Purpose:** carry S7 from "meshes everything, converges nothing at production resolution" to a strategy that independently passes the mesh, y+, convergence and grid gates.

This guide is the S7 counterpart of `AERIS_S6_AUTOMATED_CFD_MASTER_EXECUTION_GUIDE.md`
and follows its structure deliberately. Where the two disagree on a shared fact —
the host inventory, the half-domain convention, the non-destructive covenant — the
S6 guide is authoritative and this one quotes it rather than restating it.

### Non-destructive execution covenant

The S6 covenant applies unchanged and is not repeated here. Two S7-specific
consequences of it are worth naming, because S7 tooling now enforces them:

- Every solver attempt directory is immutable. `solver_tuning.py` reloads a
  directory holding `result.json` and **refuses** a directory without one, on the
  grounds that a part-way attempt is evidence to investigate rather than debris to
  delete. It never calls `rm`.
- Every run root holds a `request.json` identity. Re-running the identical command
  resumes; a different request against the same root is refused rather than mixed.

---

## 0. Executive decision

### Honest status now

- [x] Surface qualified across the design space: **60 / 60**, zero self-intersections, node fidelity exactly 0.0.
- [x] Volume across the whole development set at the diagnostic tier: **100 / 100 in 101 attempts**, 99 first-try, from three frozen candidates and no atlas.
- [x] Half-domain breadth at `laptop_smoke`: **20 / 20**.
- [x] Production-resolution volume, half domain, index 0 at `coarse`: **accepted**, 1 549 111 cells, 146 s meshing, 202 s auditing, 3.6 GB peak.
- [x] SU2 8.5.0 installed, pinned, and the whole chain verified end to end.
- [x] Wall y+ measured at `coarse` and passing: p95 0.5573, p99 0.7552, max 0.8744 over 5 293 wall points.
- [x] The convergence stall is diagnosed: **Newton-Krylov is the discriminating ingredient**, and four configurations carrying it pass both frozen gates at 42 745 cells while agreeing on CL/CD/CMy to 5e-7.
- [ ] **No converged CFD solution exists at production resolution.** This is the single open item that everything downstream waits on.
- [ ] The selected solver configuration is not yet in `POLICY.yaml`'s `su2.numerical_method`; the matrix chose it, the policy does not yet carry it.
- [ ] No production-resolution volume mesh beyond a handful of designs, and none of the 100 in the half domain.
- [ ] No grid-convergence or trailing-edge sensitivity result; the facet and tetrahedral quality limits remain provisional.
- [ ] The required independent Claude Opus/max review has never completed.

### The decisive coarse-resolution consequences

Two measurements taken on 31 August 2026 set the whole budget below. Both were
taken on the index-0 `coarse` half mesh, 1 549 111 cells, two MPI ranks.

**1. Solver cost is now measured, not assumed.** Two bounded probes, 5 and 25
iterations, wall 65 s and 174 s, separate startup from iteration cost:

| quantity | measured |
|---|---|
| per iteration, 2 ranks | **5.45 s** |
| startup: mesh read, partition, preprocessing | **37.8 s** |
| 6 000 iterations, 2 ranks | **9.1 h per variant** |

**2. The residual gate was unsatisfiable at coarse resolution, and is repaired.**
Every `laptop_smoke` history starts between -2.576 and -2.687, so `POLICY.yaml`'s
assumed worst initial residual of -3.0 and the derived solver stop of -9.0 were
safe there. **The coarse mesh starts at -3.6643**, measured identically on two
independent runs. The drop gate asks six orders, so a coarse run must reach
-9.6643; a solver stopping at -9.0 halts having dropped 5.336 orders and is then
rejected on `insufficient_residual_drop`, which reads as a solver that failed to
converge. It is not. It is defect 10 recurring one resolution level up, from the
same cause: a stop derived from an assumption the physics did not honour.

The repair, and what it does **not** change:

- `assumed_worst_initial_residual_log10`: -3.0 → **-4.0**, set below the worst
  measured value with 0.34 of margin rather than below the smoke span.
- `solver_stop_residual_log10`: -9.0 → **-10.0**, which follows from it.
- `su2_pipeline.residual_gate` now checks **each run's own initial residual**
  against the stop and reports `solver_stop_truncates_drop_gate`, so the next
  resolution that starts lower still is diagnosed rather than blamed on the
  solver. The reason cannot fire on a run that would otherwise have passed, and a
  test asserts exactly that.
- **Neither acceptance threshold moved.** `residual_drop_orders_min` is still 6.0
  and `residual_log10_final_max` is still -8.0.

The cost consequence is real and must not be wished away: at smoke resolution the
fastest passing variant needed 5 872 iterations to reach -9.5, and coarse demands
-9.6643 with 36 times the cells. **A 6 000-iteration budget may land short.** That
is a measurement to make, not a threshold to lower.

### What success means

S7 becomes comparable to S6 only when four claims are separately supported. They
are the four the S6 guide §16 requires of S7 before any matched comparison:

1. **Mesh:** every written volume valid and independently re-audited, across the
   development set at production resolution and in the declared half domain.
2. **Wall resolution:** y+ measured on a converged case, not on a bounded probe.
3. **Convergence:** the frozen residual and force-tail gates passed at production
   resolution, by a configuration named in `POLICY.yaml`.
4. **Grid:** coupled grid-convergence and trailing-edge sensitivity results, with
   the provisional quality limits replaced by ones tied to a required accuracy.

Claims 1 and 2 hold at the diagnostic tier today. Claim 3 holds at 42 745 cells
and nowhere else. Claim 4 has not been started.

### Scope discipline, quoted from the S6 guide

S7 remains outside the Paper 1 critical path. After S6 qualification, 3–5
predeclared matched S6/S7 cases may be run **only if S7 independently passes all
four gates above**. S7 is never used only where S6 fails, and the two are never
mixed as one homogeneous fidelity: that would create geometry-correlated method
bias.

---

# Part I — What the pipeline actually does

## 1. Geometry and wall

The pyGeo wall is built independently, triangulated by S7 rather than remeshed by
Gmsh, and held fixed inside every retry. Node fidelity measures exactly 0.0 and is
gated as correctness; facet fidelity is a separate resolution gate, because
grading facets against the node limit produced a bar no preregistered level could
satisfy.

The tip cap is planar Delaunay over the perimeter nodes, with a conformal ladder
as a verified fallback. A centre fan and a rigid ladder were both tried and both
failed; minimum cap angle went 1.516° → 7.209° → 20.649° across the three.

**Open instrumentation gap:** the cap falls back to the ladder without recording
that it did. That single missing field is the blocker on the fixed-topology
exploit, and it is M2 below.

## 2. Prism layer: marched, not extruded

Gmsh offers no way to constrain its extrusion direction, and at the root the wall
does not meet the symmetry plane perpendicularly, so a Gmsh-extruded layer leaves
the domain — measured at 0.705 mm against a 15.449 mm layer. S7 marches the layer
itself in `prism_layer.py`, and the result reproduces Gmsh's extrusion to four
decimals on prism quality for every design.

Three things about it are settled by measurement and must not be re-litigated:

- Vertex normals are **angle-weighted**. Area weighting lets the large flat
  tip-cap faces steer the direction and drops prism quality from 0.3795 to 0.0311,
  below the 0.05 gate.
- **Do not scale the step to mitre corners.** It raises quality and lifts the
  first cell off the wall by up to a factor of two, which is what sets y+: the
  relative first-cell error went from zero to 0.9977 against a 0.05 limit.
- Cell validity uses the isoparametric Jacobian, never a sub-volume
  decomposition, which was decomposition-dependent.

## 3. Core: size field and optimisation, both required

The core needs **both** the background size field and the optimisation passes.
With neither, tet quality was 0.0076 against a 0.025 gate; the field alone gave
0.0117; the passes took it to 0.0774. Optimisation is Netgen, scoped to the core
volume only, with automatic rollback if it increases invalid cells. **Relocate3D
must never be used**: it destroys the prism schedule, minSJ 0.3332 → -33.3.

## 4. Domain and references

S7 meshes `y >= 0`. `REF_AREA` is **halved** for a half mesh, by
`fixed_su2_options` itself, keyed on the presence of the `symmetry` marker. The
reference values describe the whole wing whatever is meshed, so leaving it alone
reports CL and CD at half their true value on a run that looks entirely healthy —
and halving a second time in the caller reports a quarter of it. Callers pass
whole-wing references; `solver_tuning.case_from_directory` reads them from
`geometry_summary.json` for exactly this reason.

`symmetry` is not a wall label. It carries no prisms, and `WALL_LABELS` rather
than `LABELS` is what the audit, the wall mapping and the solver config iterate.

## 5. Solver

Established by byte comparison at 42 745 cells, not by inference:

- **Newton-Krylov is the discriminating ingredient.** Every variant carrying it
  was monotonic and still descending at iteration 5 999 of 6 000; every variant
  without it limit-cycled below 3.02 orders.
- It is **necessary but not sufficient** in budget: alone it reaches 5.954 orders
  and misses the gate by 0.046. It needs either the stronger linear solve or the
  higher CFL, and both together are fastest.
- `QUASI_NEWTON_NUM_SAMPLES` is a **no-op** in SU2 8.5.0: byte-identical history.
- Multigrid is **bypassed** under `NEWTON_KRYLOV`: byte-identical history.
- SU2 **never reports Newton-Krylov activation**; whether it took effect can only
  be established from the residual history.

The four passing variants agree on CL 0.018883, CD 0.087040, CMy -0.006617 to
5e-7 regardless of how the solver reached them. The five failing variants disagree
by a tenth of CMy. The gate discriminates what it was written to discriminate.

---

# Part II — Frozen decision table

| decision | value | status |
|---|---|---|
| domain | half model, `y >= 0`, `symmetry` root plane | frozen |
| wall source | independent pyGeo triangulation, fixed inside retries | frozen |
| tip cap | planar Delaunay, conformal ladder fallback | frozen; fallback unrecorded (M2) |
| prism layer | marched, angle-weighted normals, no mitre scaling | frozen |
| core optimisation | Netgen, core-scoped, rollback on invalidity | frozen |
| cell validity | isoparametric Jacobian | frozen |
| `residual_drop_orders_min` | 6.0 | frozen, unchanged |
| `residual_log10_final_max` | -8.0 | frozen, unchanged |
| `solver_stop_residual_log10` | -10.0 | amended 2026-08-31 |
| `assumed_worst_initial_residual_log10` | -4.0 | amended 2026-08-31 |
| `su2.numerical_method` | conservative baseline, no Newton-Krylov | **not yet adopted** (M1) |
| facet fidelity / tet shape limits | provisional | calibrated from achievement, not accuracy (M5) |
| `round_c_lhs10_seed42` | forbidden | untouched |

---

# Part III — Realistic run budget

All costs measured on the 16 GiB laptop; the desktop is faster but memory-bound
the same way.

## Memory

Each MPI rank reads the whole mesh before partitioning, so peak memory scales with
**ranks × cells**, not with cells. The datum is the OOM that stopped the first
attempt: about 3 GB per rank at 2.5 M cells, and eight ranks killed on 16 GiB.

    GiB per rank ≈ 1.20 × (cells / 1e6)

At the coarse 1 549 111 cells that is **1.86 GiB per rank**. Against the S6
guide's reported desktop budget of about 11.36 GiB available:

| ranks | estimated peak | verdict |
|---|---|---|
| 2 | 3.72 GiB | fits, measured |
| **4** | **7.44 GiB** | **fits — the desktop recommendation** |
| 6 | 11.15 GiB | at the budget; do not |
| 8 | 14.87 GiB | refused; this is the recorded OOM |

`solver_tuning.py` computes this plan, prints it, and **refuses to launch** when it
does not fit, in the spirit of the S6 guide's `RESOURCE_REJECTED`. Overriding it
requires `--allow-overcommit` deliberately.

## Wall time — measured, and the parallelism assumption is dead

M1A ran a clean rank sweep on an idle machine, differencing 5- and 25-iteration
probes at each rank count. The guide previously assumed a 1.8× speedup at 4
ranks. **There is no speedup. More ranks are monotonically slower:**

| ranks | s/iteration | startup | GiB | 6 000 iterations |
|---|---|---|---|---|
| **1** | **4.60** | 12.0 s | **1.86** | **7.7 h** |
| 2 | 5.65 | 39.8 s | 3.72 | 9.4 h |
| 4 | 8.50 | 59.5 s | 7.44 | 14.2 h |

The solve is memory-bandwidth bound: extra ranks buy halo exchange and
partitioning cost for no arithmetic gain, and each holds another full copy of the
mesh. **One rank is simultaneously the fastest and the smallest.** Four ranks is
1.85× slower per iteration than one, and costs four times the memory to be so.

**Rank count does not change the numerics.** The 1-, 2- and 4-rank
25-iteration histories are identical to the byte, sha `9378f811…`. The
decomposition is a pure cost choice; results are reproducible across it, and the
serial laptop matrix and a production run are the same experiment. This was
checked over 25 iterations and should be re-checked at the end of M1B, where
accumulated divergence would show if it exists.

The shortlist is three variants. Run them **sequentially at one rank**: 7.7 h
each, 23 h for all three, in 1.86 GiB. Concurrency is now genuinely tempting —
three single-rank solves fit in 5.6 GiB — but they would contend for the memory
bandwidth that is the actual bottleneck, so the sequential number is the one to
plan against.

---

# Part IV — Milestones and stop/go gates

## M0 — Preserve source and evidence

- [ ] Commit the S7 source, POLICY amendment, tests and this guide before any
      heavy run.
- [ ] Back up the canonical generated JSON and mesh evidence outside the
      gitignored `artifacts/` tree.
- [ ] `pytest -q` on the S7 directory: expect **51 passed**. `ruff check`: clean.

**Stop/go:** do not start M1 with uncommitted source. The whole point of the
confirmation is that its provenance is exact.

## M1 — Confirm Newton-Krylov at coarse resolution

This supersedes "confirm multigrid", which is refuted: multigrid alone ends at
1.082 orders over 6 000 iterations, and is bypassed entirely under
`NEWTON_KRYLOV`.

Run only the shortlist, cheapest first. `J_nk_no_mg` is excluded because its
history is byte-identical to `I_combined`.

| rank | variant | why |
|---|---|---|
| 1 | `G_nk_cfl` | fewest options changed from the frozen block; fastest of the passing set |
| 2 | `I_combined` | deepest drop (6.906) and the most headroom if coarse converges more slowly |
| 3 | `F_nk_linear` | the fallback if the high CFL destabilises at production resolution |

### M1A — Calibrate the rank speedup — **DONE 2026-08-31**

Ran as a clean sweep over 1, 2 and 4 ranks; results in the wall-time table above.
The stop/go fired: the job is memory-bandwidth bound and more ranks do not help,
so **M1B runs at one rank**. Reproduce with:

```bash
cd /home/mike/Desktop/Start_Up/Code/v.0.1_Project
LW=AERIS_MESH_STUDY/artifacts/strategy_studies/S7_unstructured_gmsh_su2/lead_work
S7=AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2
for R in 1 2 4; do for N in 5 25; do
  .venv/bin/python $S7/solver_tuning.py $LW/nk_coarse/case.json \
    --variants G_nk_cfl --ranks $R --iterations $N --timeout 2400 \
    --output $LW/ranksweep_r${R}_n${N}
done; done
```

Run it on an idle machine. The first 4-rank attempt was taken while a test suite
and a geometry build were running and read 6.35 s per iteration against the clean
8.50 — a 25 per cent error, in the direction that would have made 4 ranks look
better than it is.

### M1B — The confirmation runs

One variant at a time, each to its own output root. Sequential is the default at
this cell count and should not be overridden.

```bash
LW=AERIS_MESH_STUDY/artifacts/strategy_studies/S7_unstructured_gmsh_su2/lead_work

# Build the case from the geometry, never by typing reference values.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/solver_tuning.py \
  $LW/nk_coarse/case.json --from-case-dir $LW/half_coarse \
  --variants G_nk_cfl --ranks 1 --iterations 6000 --timeout 43200 \
  --output $LW/nk_coarse_confirm
```

Then, only if the first result warrants it, the same command with
`--variants I_combined` and `--variants F_nk_linear` against **new** output roots.

Resume after any interruption by re-running the identical command: completed
variants reload from `result.json` and only unfinished work runs again.

**Stop/go, in order:**

- A variant reaching **-9.6643 or below** with the force tail inside its limits
  passes both frozen gates at production resolution. That is the result the whole
  strategy is waiting on.
- A variant **still descending monotonically** at iteration 6 000 has not failed;
  it has run out of budget. Extend it rather than rejecting it — that misreading
  is precisely what the multigrid episode was.
- A variant that **turns around and limit-cycles** at coarse when it did not at
  smoke is a genuine resolution-dependent failure. Record it and move to the next
  variant on the shortlist.
- All three limit-cycling at coarse is a **stop**: quarantine the numerical method
  and write a superseding ADR. Do not weaken a threshold.

### M1C — Adopt the winner

Only after M1B, and only from the coarse measurements:

- [ ] Amend ADR-0017 with the coarse numbers.
- [ ] Write the winning options into `POLICY.yaml` `su2.numerical_method`.
- [ ] Re-run the S7 suite; the frozen-config tests must be updated deliberately,
      never silently.

**Do not adopt from the laptop matrix alone.** 42 745 cells is a solver
diagnostic, not a production result.

## M2 — Record the tip-cap fallback — **DONE 2026-08-31**

The Delaunay cap fell back to the conformal ladder without recording that it had,
so a design whose cap connectivity followed its geometry was indistinguishable
from one that took the fallback. `build_surface` now publishes
`metadata["tip_cap"]`:

| field | meaning |
|---|---|
| `by_side[...].construction` | `planar_delaunay` or `chordwise_ladder` |
| `by_side[...].used_fallback` | the flag the fixed-topology question needs |
| `by_side[...].perimeter_nodes`, `.triangles` | cap size |
| `by_side[...].min_angle_deg` | the metric the cap has always been judged by |
| `any_fallback`, `min_angle_deg` | case-level rollup |

Both branches write through one record builder, so they cannot drift apart — a
family comparison is only meaningful if every design reports the same fields, and
a test pins that.

Verified on a real geometry: development index 0 at `laptop_smoke` reports
`planar_delaunay`, no fallback, 33 perimeter nodes, 31 triangles, minimum angle
**18.33°**. For scale, the abandoned centre fan measured 1.516° and the rigid
ladder 7.209°.

**What this does not yet answer:** how many of the 100 designs take the fallback.
That is a census the M3 sweep produces for free now that the field exists, and it
is the input the fixed-topology decision actually needs.

Measured context: freezing the surface grid costs about 1.11× mean surface cells
at `coarse` over six cases, and the wall is already a structured tensor grid, so
index correspondence follows directly.

## M3 — The 100-design coarse sweep in the half domain

About 10 hours sequential, and it **supersedes** the mirrored meshes rather than
adding to them. See `S7_unstructured_gmsh_su2/RUNBOOK.md` for the split-range
form; each part needs its own output root and about 6 GB.

Run this before M1C if the desktop is free, so the adoption decision rests on a
mesh family that will be kept.

**Stop/go:** anything below 100/100 acceptance is a strategy result, not a bug to
patch case by case. A trailing-edge or tip failure common to all three frozen
candidates triggers a stop and a superseding mesher ADR. The specific capability
Gmsh lacks is layer collision handling, which snappyHexMesh and cfMesh provide.

## M4 — A converged coarse case earns the y+ claim

`production_y_plus_passed` is unmet today because the measured y+ came from a
bounded 120-iteration diagnostic. Re-measure it on the M1B converged solution.

**Stop/go:** y+ from an unconverged run is not evidence, however good it looks.

## M5 — Grid and sensitivity — **BLOCKED ON HARDWARE, measured 2026-08-31**

The machinery exists — `qualification.py` already implements unequal-grid
Richardson, GCI, asymptotic-ratio checks and the S6/S7 comparison. M5 is a
*running* problem, not a building one. The problem is that it cannot be run here.

Surfaces were built at all three levels for index 0. Surface triangles and prisms
are exact; the tetrahedral counts come from two independent estimates that agree
to 1.4% at medium and 2.8% at fine:

| level | prisms (exact) | cells | GiB/rank | 6 000 iters | solvable on 11.36 GiB |
|---|---|---|---|---|---|
| coarse | 126 984 | 1 549 111 (measured) | 1.86 | 7.7 h | yes |
| medium | 343 456 | ~4 317 000 | 5.18 | 21.5 h | yes, 1 rank only |
| **fine** | **835 160** | **~12 056 000** | **14.47** | 60 h | **NO** |

**`fine` needs more than the entire host budget for a single rank.** Every rank
holds the whole mesh, so no decomposition rescues it. Without `fine` there is no
three-level family, and without that there is no Richardson extrapolation, no GCI,
and therefore no grid-convergence result. This is the same terminal state S6
reached, `RESOURCE_BLOCKED_16GB`.

Re-run the forecast against the real desktop inventory before accepting this:

```bash
PYTHONPATH=AERIS_MESH_STUDY/04_strategy_studies .venv/bin/python \
  -m S7_unstructured_gmsh_su2.grid_family_forecast \
  --prisms 126984 --tets 1422127 --budget-gib <actual free GiB>
```

At 64 GiB `fine` becomes solvable and M5 proceeds as written. **The desktop's
actual RAM is the single input that decides whether S7 can reach S6-level
readiness on this hardware.** Do not redefine the grid levels to fit the host:
that changes a preregistered definition and hollows out the study it feeds.

### A second M5 problem, independent of memory

The tip cap **degrades monotonically with refinement**: minimum angle 18.33° at
`laptop_smoke`, 12.91° at `coarse`, 9.48° at `medium`, **7.03° at `fine`**. The
rigid ladder rejected earlier in this study measured 7.209°, so the accepted
Delaunay construction at `fine` is more slender than the one thrown out for being
too slender. Refining chordwise on a thin cambered tip section makes cap triangles
thinner, not fatter.

This was invisible until M2 added the instrumentation. It means a `fine` mesh may
fail quality gates for reasons that have nothing to do with memory, and it must be
resolved before the grid family is trusted even on a larger host.

### Still required, once unblocked

- [ ] Five coupled coarse/medium/fine grid studies with Richardson and GCI.
- [ ] The three declared trailing-edge variants.
- [ ] Geometric fidelity sensitivity, which replaces the provisional facet and
      tetrahedral limits with limits tied to a required accuracy. Until this
      lands, no accuracy claim may rest on those limits.

## M6 — Independent review, then freeze, then the hold-out once

- [ ] The independent Claude Opus/max review, which has never completed.
- [ ] Freeze the atlas-free candidate set, mesh resolution, TE policy, solver
      configuration and every acceptance gate.
- [ ] Release `round_c_lhs10_seed42` **once**, about ten cases, and report without
      tuning.

---

# Part V — Per-run discipline

## Preflight

- [ ] The S7 suite passes and `ruff` is clean.
- [ ] `free -g` and `df -h .` clear the declared floors; no S6 heavy job is active.
- [ ] The printed memory plan says `fits: true` without `--allow-overcommit`.
- [ ] The output root is new, or holds the identical `request.json`.
- [ ] The case was built with `--from-case-dir`, so the reference values came from
      the geometry rather than from another design's literals.
- [ ] The mesh carries the `symmetry` marker and `REF_AREA` is the halved value.

## Post-completion classification

- [ ] Process exit 0 and a history of at least the policy row count.
- [ ] `residual_gate` reports no `solver_stop_truncates_drop_gate`. If it does,
      the setup truncated the run and the result says nothing about convergence.
- [ ] Residual drop ≥ 6.0 orders **and** final ≤ -8.0, both from the run's own
      initial residual.
- [ ] CL/CD/CMy tails inside their relative-range limits.
- [ ] y+ read from the surface Paraview file, never the CSV — SU2 8.5 omits every
      PRIMITIVE field from the CSV, and the alias `"Y+"` once collapsed to `"y"`
      and reported the semi-span as wall y+.
- [ ] Every attempt, accepted or not, retained under its immutable directory.

## Failure handling

- Memory plan fails → do not launch; lower ranks. This is `RESOURCE_REJECTED`.
- Part-way attempt directory → investigate it or use a new output root. It is
  never repaired in place and never deleted.
- Solver exits non-zero → one frozen restart if permitted, else record and stop.
- Residual gate fails → check `solver_stop_truncates_drop_gate` **first**. A
  truncated setup is a configuration defect, not a solver failure.
- Still descending at the iteration budget → extend the budget, do not reject.
- Hold-out failure → final evidence. No new tuning round.

---

# Part VI — Permitted claims

**Allowed once M1–M5 pass:** that a deterministic Gmsh triangular-wall /
marched-prism / tetrahedral-core path produces auditable wall-resolved
unstructured meshes over the AERIS development space without geometry-specific
repair, and that a named SU2 8.5 configuration converges them at production
resolution to the frozen gates.

**Prohibited until then:**

- Any accuracy claim resting on the provisional facet or tetrahedral limits.
- Any convergence claim from the 42 745-cell matrix; it selects a configuration
  and establishes nothing about production resolution.
- Any y+ claim from a bounded diagnostic.
- Any S6/S7 comparison before S7 independently passes all four gates.
- Any statement that S7 needs fewer attempts than S6 without stating that S7's
  100/100 was at the **diagnostic tier** and S6's was at production resolution.

---

## Primary technical basis

- `04_strategy_studies/S7_unstructured_gmsh_su2/STUDY.md` — the measured record,
  including every refuted hypothesis.
- `04_strategy_studies/S7_unstructured_gmsh_su2/POLICY.yaml` — the executable
  policy, written before any result.
- `00_governance/decisions/ADR-0017-s7-unstructured-gmsh-su2-preregistration.md`
  and its amendments.
- `AERIS_S6_AUTOMATED_CFD_MASTER_EXECUTION_GUIDE.md` §16 — why S7 sits outside the
  Paper 1 critical path and what it must pass before any matched comparison.
- `04_strategy_studies/VALIDATION_PROGRAMME.md` — the joint S6/S7 sequence.
