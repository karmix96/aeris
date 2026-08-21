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

## Current state — 2026-08-21

Status remains `preregistered_development_no_results`.

- The complete software path exists: geometry → mesh → independent mesh audit →
  SU2 → residual/force/y+ gates → method-neutral case report → qualification and
  S6/S7 comparison report.
- The focused laptop-safe suite passes 24/24 tests and Ruff passes. This includes
  a real Gmsh synthetic tri/prism/tet generation-and-conversion test, fail-closed
  mesh gates, a fake-solver one-restart test, digest-linked resume, batch behavior,
  and manufactured unequal-grid Richardson/GCI checks.
- Gmsh 4.15.2 and the pinned Python geometry stack are present. `SU2_CFD` is not
  installed in the current environment.
- A real BWB pyGeo laptop smoke was blocked by the Codex execution sandbox/usage
  approval before the process launched. This is neither a mesh pass nor a Gmsh,
  pyGeo, trailing-edge, or tip failure.
- No real S7 BWB mesh, SU2 solution, force result, wall-y+ result, grid study,
  hold-out case, or campaign result has been accepted.
- The retained `mapping_fix`, `no_optimize_diagnostic`, and
  `core_optimize_diagnostic` artifacts are synthetic development diagnostics under
  older source digests. They are not campaign evidence.
- The first Claude Opus/max audit attempt used the required model and effort but
  ended at a session limit. Its failed record is preserved and is not acceptance.

The locked `round_c_lhs10_seed42` hold-out remains forbidden. The runner has no
unlock or bypass flag.

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
