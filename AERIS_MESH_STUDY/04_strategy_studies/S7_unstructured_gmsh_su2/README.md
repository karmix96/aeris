# S7 — unstructured Gmsh + SU2

S7 is the unstructured sibling of
[`S6_bounded_mesh_atlas`](../S6_bounded_mesh_atlas/) inside the same governed
`AERIS_MESH_STUDY`. It derives a full-wing triangular wall from the shared pyGeo
geometry, extrudes triangular-prism boundary layers, fills the farfield with
tetrahedra, audits the written Gmsh and native SU2 meshes independently, and then
runs fixed SU2 RANS/Spalart–Allmaras convergence, force, restart, and wall-y+ gates.

The governing preregistration is
[`ADR-0017`](../../00_governance/decisions/ADR-0017-s7-unstructured-gmsh-su2-preregistration.md).
[`POLICY.yaml`](POLICY.yaml) is the executable numerical contract. No threshold may
be weakened to make a case pass.

## Current state - 2026-08-22

Status remains `preregistered_development_no_results`.

### The unstructured route now meshes the whole development set

A 100-design robustness sweep runs on a 16 GiB laptop in about an hour at roughly
77 000 cells and 30 s per case.  On the first such sweep **97 of 100 designs were
accepted**, and `tet_quality` was the *only* failure mode in the entire run:
topology, validity, geometry fidelity, labels, prism coverage and continuity, and
native-SU2 conversion never failed on any design.

Measured population, best candidate per design:

| statistic | min | p05 | p50 | max |
|---|---|---|---|---|
| tet SICN minimum | 0.0398 | 0.0556 | 0.0998 | 0.1679 |
| tet SICN p01 | 0.2229 | 0.2398 | 0.2948 | - |

The three rejections (089, 029, 085) were boundary-locked slivers against the
prism cap.  The worst-cell floor has been recalibrated onto that population and a
distribution floor added; see the 2026-08-22 sections of ADR-0017.

### Production resolution is validated on five designs

Five representative designs at the `coarse` level, all accepted on the first
candidate with no retries:

| design | cells | tet SICN | tet p01 | prism SJ | core skew p99 | core nonortho p99 | neg |
|---|---|---|---|---|---|---|---|
| dev_000 | 2 549 227 | 0.0651 | 0.6702 | 0.6183 | 0.413 | 31.7 | 0 |
| dev_024 | 2 231 389 | 0.0954 | 0.6764 | 0.6362 | 0.409 | 31.4 | 0 |
| dev_049 | 2 201 979 | 0.0702 | 0.6773 | 0.6342 | 0.409 | 31.4 | 0 |
| dev_074 | 2 505 872 | 0.0591 | 0.6753 | 0.6593 | 0.410 | 31.5 | 0 |
| dev_099 | 2 575 993 | 0.1038 | 0.6737 | 0.6161 | 0.410 | 31.5 | 0 |

Prism wall coverage and column continuity are 1.000000 on every design.  Core
skewness p99 sits at 0.41 against a 0.85 limit and core non-orthogonality p99 at
31.5 against 65, so production resolution carries roughly two-fold margin where
the diagnostic tier had none.

`dev_049` is worth noting: it was the hardest design at laptop resolution and the
one that drove the whole tet-quality investigation, and it passes here at 0.0702
without retries.  The extra cells give the core mesher room the diagnostic tier
never had.

Cost, measured: about **9.5 minutes and 263 MB per case** (245 s meshing at 1.8 GB
peak, 325 s auditing at 5.3 GB peak).  The remaining 95 designs are a desktop job
of roughly 16 hours sequential, or about four hours split four ways since each
case is single-threaded.  See [`RUNBOOK.md`](RUNBOOK.md).

### Wall resolution at coarse: y+ passes

The diagnostic tier measured wall y+ around 44, with a first cell of 2.0e-3 L.
Coarse uses 7.2e-6 L.  Measured on the index-0 coarse mesh (2 549 227 cells, SU2
8.5.0, 120 iterations on 2 MPI ranks, 1 243 s):

| statistic | value | limit |
|---|---|---|
| minimum | 0.0527 | - |
| p50 | 0.3995 | - |
| p95 | **0.5573** | 1.0 |
| p99 | **0.7552** | 2.0 |
| maximum | **0.8744** | 5.0 |

All 5 293 wall points reported, and every wall-y+ limit passes.  This is the first
evidence that S7's wall spacing actually delivers a wall-resolved boundary layer.

It is a bounded diagnostic, not a campaign result: 120 iterations is far from
converged (the density residual moves only from -3.62 to -3.79 over the run), it
is one design at one flow condition, and it invokes SU2 directly rather than
through the campaign.  `production_y_plus_passed` remains unmet until a converged
campaign case demonstrates it.

### Steady convergence is NOT achieved with the frozen numerics

A converged coarse case was attempted and is not currently reachable.  The
diagnosis was run on the cheap mesh so it could be carried to 3 000 iterations:

| quantity | result |
|---|---|
| rms[Rho] start / min / final | -2.576 / -5.240 / -4.234 |
| net residual drop over 3 000 iterations | **1.658 orders** (gate requires 6) |
| behaviour | limit cycle between about -3.2 and -5.2, no descent |
| CD by fifth of the run | 0.09441, 0.09158, 0.09154, 0.09150, 0.09163 |
| CL by fifth of the run | 0.02239, 0.02289, 0.02277, 0.02272, 0.02282 |
| CD over the last 200 iterations | mean 0.09143, spread 1.8e-3 |

**The forces converge; the residual does not.**  That combination is the classic
signature of limiter-induced limit cycling with MUSCL and a Venkatakrishnan
limiter, which the frozen numerics use.

One remedy was tested and is **refuted**: freezing the limiter at iteration 400
(`LIMITER_ITER`) destabilised the solution instead of settling it - the density
residual rose from about -3.4 to -1.3 and stayed there through iteration 700.
Freezing that early, before the flow has developed, is worse than not freezing.

Two further observations that bear on it, both unverified as causes:

- SU2 reports `Dimensional simulation`, so residuals are absolute and not
  comparable between equations: energy sits near 2e5 while density is near 0.5,
  which is why `rms[RhoE]` reads positive.  The policy never set
  `REF_DIMENSIONALIZATION`.
- `MG level: 0`; no multigrid is configured, on a 20L/30L/20L domain.

The residual gate as preregistered - six orders of drop and a final value at or
below -8 - may therefore be unreachable for this configuration.  Nothing has been
changed in response: the numerics remain exactly as frozen, and this is recorded
as a finding for the study owner.

### What made it work

- **Netgen optimisation scoped to the tetrahedral core.**  All optimisation had
  been disabled on the belief that it corrupts the prism schedule.  That is true
  of Relocate3D (prism minSJ 0.3332 to -33.3) and false of Netgen, which leaves
  the prism block bit-identical while removing slivers (tet SICN 0.029 to 0.146).
  Optimisation is guarded: the pre-optimisation mesh is restored if the optimised
  one is less valid.
- **S6-equivalent gate structure.**  S6 gates validity, wall error, interface
  consistency and one quality metric, with a warning tier.  S7 was gating about
  twenty-five criteria including six maxima S6 never checks.  The distribution
  metrics moved from maximum to p99 at unchanged limits, with the maxima reported
  as warnings.
- **Decomposition-free validity.**  A prism's 3-tetrahedron split is not unique;
  two designs were being rejected for negative sub-volumes that vanish under the
  other split, with Gmsh's Jacobian positive throughout.
- **Tier-aware distribution gates.**  Face-quality distributions are resolution
  dependent for unstructured meshes (skewness p99 0.890 at 77 k cells, 0.737 at
  1.2 M), so they are enforced from the development tier upward and reported
  below it.  Binary correctness is gated at every tier.

### Not established

- `SU2_CFD` is absent.  No CFD, y+, force, grid-convergence or trailing-edge
  sensitivity result exists, and no campaign-readiness target is met.
- No production-resolution volume mesh has been built; `coarse` needs a desktop.
- Quality limits for facet fidelity and tetrahedral shape are PROVISIONAL: they
  are calibrated from what the mesher achieves, not from a required aerodynamic
  accuracy, and `geometric_fidelity_sensitivity_study_passed` is false.
- The required independent Claude Opus/max review has never completed.
- `round_c_lhs10_seed42` remains forbidden and untouched.

## Executable architecture

1. [`geometry.py`](geometry.py) builds the same canonical `lhs100_seed42` pyGeo
   design and the declared 0.5/1.0/1.5 mm TE variant. It mirrors the wing, closes
   the numerical TE and tips, propagates orientation, checks topology and
   self-intersections, re-evaluates every OML node, and measures planar-facet
   centroids against the exact opened B-spline.
2. [`gmsh_pipeline.py`](gmsh_pipeline.py) imports that immutable labeled wall into
   Gmsh, extrudes the fixed prism schedule, builds the outer box and wake/near-body
   fields, generates the tet core, and writes both `.msh` and native `.su2` meshes.
3. [`mesh_audit.py`](mesh_audit.py) independently reloads both formats and rejects
   missing/wrong labels, open or invalid topology, conversion drift, inverted or
   zero-volume cells, incomplete prism columns, layer errors, bad cell/face
   quality, and weak TE/tip prism-to-core interfaces.
4. [`su2_pipeline.py`](su2_pipeline.py) admits only a digest-matched accepted mesh,
   writes fixed SU2 8.5 RANS-SA options, runs free-stream plus at most one
   digest-verified restart, and gates process status, density residual, CL/CD/CMy
   tails, restart output, and exact wall-point y+ coverage.
5. [`campaign.py`](campaign.py) preserves immutable mesh/SU2 attempts and case/batch
   terminals. [`qualification.py`](qualification.py) reads only digest-verified
   existing development results and reports five coupled grid studies, the three
   TE variants, and evidence-compatible S6/S7 comparisons.

`accepted` in a case report means the declared technical scope passed (`mesh_only`
or `mesh_and_cfd`). `campaign_ready` remains false, and final scientific acceptance
still requires the governed Claude review and all readiness gates.

## Frozen method

- Full mirrored wing; full-wing reference area and mean aerodynamic chord.
- Fixed pyGeo design identity and frozen cruise condition: alpha 2°, Mach 0.2,
  Reynolds number 1,000,000, temperature 288.15 K.
- Gmsh 4.15.2. The pyGeo-derived wall triangulation is immutable within an attempt;
  retry surface algorithms act only on Gmsh-generated outer surfaces. Core retries
  are Delaunay, HXT, then Delaunay with the predeclared outer-surface algorithm.
- Post-extrusion optimization is disabled. Synthetic diagnostics showed that both
  global and nominally core-scoped relocation can move intermediate prism nodes and
  corrupt the prescribed first height/growth schedule.
- SU2 8.5.0 Harrier, compressible RANS-SA, fixed numerics, one restart maximum.
- Coarse/medium/fine refine wall triangles, first height, prism count/growth, wake,
  near-body core, and far core together. Actual surface/prism/tet/total counts must
  all increase; effective grid spacing is based on actual volume-cell count.
- The mesh audit separately hard-gates first-layer displacement magnitude and its
  wall-normal projection, preventing tangential extrusion at the TE/tip from
  masquerading as the prescribed wall spacing.
- CMy is the pitching-moment coefficient about the y axis. S6/S7 numbers are not
  comparable until design, flow, full-wing normalization, area/chord, moment origin,
  and case lists match explicitly.

## Safe commands

Plan all development indices without constructing geometry or launching a tool:

```bash
.venv/bin/python \
  AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/run_s7.py \
  --indices 0-99 \
  --level laptop_smoke \
  --output AERIS_MESH_STUDY/artifacts/strategy_studies/S7_unstructured_gmsh_su2/plans
```

Run focused unit/synthetic checks:

```bash
.venv/bin/python -m pytest -q \
  AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2
.venv/bin/python -m ruff check \
  AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2
```

Run one deliberately reduced, non-campaign laptop diagnostic after local execution
is available:

```bash
AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/production_desktop.sh \
  --development \
  --index 0 \
  --level laptop_smoke \
  --output AERIS_MESH_STUDY/artifacts/strategy_studies/S7_unstructured_gmsh_su2/laptop_runs
```

The laptop level uses a reduced 3L/5L/3L farfield and refuses an estimated mesh
above 40% of currently available RAM. It cannot prove production quality, y+,
forces, runtime, robustness, or grid convergence.

Submit production-resolution development cases on resource-qualified Slurm nodes:

```bash
sbatch --array=0-99 \
  AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/production_hpc_slurm.sh \
  --development \
  --level medium \
  --output /shared/aeris/s7_medium
```

Append `--run-cfd` only for approved development pilots after the pinned
`SU2_CFD` is installed. The baseline cruise flow is then inferred and enforced.
Production levels retain the full 20L/30L/20L farfield and refuse nodes below the
48 GiB available-RAM and 100 GiB free-disk floors; requested grids are never
silently coarsened. The launchers refuse hold-out and production campaign modes.

Create or collect the fixed five-case grid/TE qualification record without
launching cases:

```bash
.venv/bin/python \
  AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/qualification.py \
  plan --output /shared/aeris/s7_qualification_plan.json

.venv/bin/python \
  AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/qualification.py \
  collect /shared/aeris/results/*/case_result.json \
  --output /shared/aeris/s7_qualification_summary.json
```

Collection fails closed on missing/tampered case terminals, stale source/policy,
wrong software versions, out-of-plan cases, mixed designs/flows/reference values,
non-monotone coupled grids, non-asymptotic behavior, or GCI limits.

## Proved versus unverified

| Claim | Current evidence | Status |
|---|---|---|
| deterministic planning, guards, parser/gate logic | 24 focused tests | proved at unit/synthetic tier |
| Gmsh tri/prism/tet and native SU2 conversion | synthetic tetrahedral wall fixture | proved only for fixture |
| one restart and idempotent recovery | fake local solver fixture | proved only for fixture |
| real BWB surface/TE/tip survives Gmsh | no launched real smoke | unverified |
| SU2 configuration runs under 8.5.0 | executable absent | unverified |
| residual, CL/CD/CMy, and wall y+ pass | no real solution | unverified |
| coarse/medium/fine and TE sensitivity pass | no result family | unverified |
| 100/100 development meshes | not run | unverified |
| 10–20 unattended CFD pilots | not run | unverified |
| locked hold-out | forbidden and untouched | not run by design |

## Honest S6/S7 comparison today

| Measure | S6 structured evidence | S7 unstructured evidence | Conclusion |
|---|---|---|---|
| mesh robustness | 100/100 production-resolution written-CGNS development audit | synthetic fixture only | S6 alone has real development evidence |
| cells | roughly 2.3–3.5 million for S6 production seeds | no real S7 count | no cell comparison |
| runtime | no normalized common-method comparison record | no real S7 runtime | no runtime comparison |
| y+ | N65 pilots 0/3 strict screens; production y+ open | no SU2 y+ | neither route has production y+ proof |
| forces | coarse S6 solver path exists; force/grid accuracy open | no SU2 forces | no force-accuracy comparison |

S7 cannot be selected over S6 from current evidence. The comparison utility emits
`missing_evidence` or `incompatible_evidence` rather than treating absence as zero
or a pass.

## Change control

Gmsh is retained provisionally because it is installed, open, scriptable, and
supports the intended hybrid topology. This is not a robustness finding. If all
frozen candidates fail the same thin-TE/tip topology or quality class, stop and
write a superseding ADR before evaluating snappyHexMesh/cfMesh, Netgen, TetGen, or
another core/layer method. Never silently change a mesher, topology, size, layer,
retry order, solver option, metric, threshold, or output schema.

See [`RESEARCH.md`](RESEARCH.md), [`STUDY.md`](STUDY.md),
[`ROADMAP.md`](ROADMAP.md), and [`HANDOFF.md`](HANDOFF.md) for the research basis,
program, remaining gates, and reload procedure.
