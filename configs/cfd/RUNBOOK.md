# CFD Suite — Desktop Runbook (staged, not yet executed)

Everything in this file is built and validated (`--dry-run`, unit tests, or a
cheap real geometry/surface check where noted) but **deliberately not run for
real** in-session, per instruction: heavy/long compute should be launched by
Mike on his own schedule, not automatically inside an agent session. Run
these yourself, in order, whenever convenient. Each entry gives the exact
command, what it produces, an honest runtime/RAM estimate, and how to check
progress.

General rules for all entries below:
- Run one at a time. Nothing here should overlap another ADflow/SU2/pyHyp
  job — this machine has 16 GB RAM and 12 cores; two concurrent solves will
  contend for both.
- Activate the mach-aero conda env first (`conda activate mach-aero`) unless
  a command already gives a full interpreter path.
- Every command writes its own provenance (effective-options manifests,
  `case_manifest.json`/`study_report.json` sha256 chains) — nothing here
  needs to be re-explained after the fact, the artifacts are self-describing.
- If a run OOMs (exit 137 / "Killed"), that is itself a data point — record
  it, don't just retry blindly. The wing-level entries below already flag
  where this is expected to be a real risk (production family member).

## 1. 2D NACA0012 sensitivity studies (cheap: ~7 min per ADflow solve)

All three reuse the validated medium O-grid recipe
(`configs/cfd/validation_naca0012_tmr.yaml`) and the `aeris cfd study`
machinery (`src/aeris/cfd/study/`). Dry-run validated already; not solved.

```bash
# Farfield-distance sensitivity (100c/250c/500c) — tests whether the GCI
# ladder's -1.9% Richardson offset vs NASA TMR is farfield-truncation error.
# 3 solves x ~7 min ~= 20-25 min total.
aeris cfd study run configs/cfd/study_farfield_distance.yaml \
  --workdir data/cfd_cases/naca0012_farfield_study

# Wall-spacing / y+ sensitivity (s0 for y+~2/1/0.4) — shows force
# independence once the viscous sublayer is resolved. Same cost as above.
aeris cfd study run configs/cfd/study_wall_spacing.yaml \
  --workdir data/cfd_cases/naca0012_wall_spacing_study

# Euler-vs-RANS (rubric 8.2) — same grid, inviscid vs viscous. Euler
# iterations are much cheaper per-step than RANS/SA, so the Euler variant
# should finish well under 7 min; RANS variant re-solves the validation
# anchor (~7 min). NOTE (unverified): check ADflow doesn't complain about
# turbulence-model options being present under equationType=Euler before
# trusting the run unattended — see the note in the YAML.
aeris cfd study run configs/cfd/study_euler_vs_rans.yaml \
  --workdir data/cfd_cases/naca0012_euler_vs_rans
```

```bash
# alpha=0 second validation anchor (independent symmetry check, CL should
# ~vanish). Single solve, ~7 min.
aeris cfd run configs/cfd/validation_naca0012_tmr_a0.yaml \
  --stage surface --stage volume --stage solve --stage post
```
CAVEAT: this environment had no live network access to re-verify the exact
NASA TMR alpha=0 CL/CD reference figures against
https://turbmodels.larc.nasa.gov — spot-check the printed CL/CD against the
live TMR table yourself before citing a percent-error number (and it would
be worth re-checking the alpha=10 anchor's 1.0909/0.01231 reference figures
the same way — those were carried over from an earlier session's memory,
not re-verified here either).

After all four finish, fold the results into `data/cfd_cases/README.md`
(there's already a table there to extend) and update
`src/aeris/mesh/DSE_READINESS.md` / the memory project note if the farfield
hypothesis is confirmed or refuted.

## 2. Wing-level mesh family verification (mesh-only, no solve)

DSE_READINESS.md (WP2) flagged that `fine`/`production` family presets were
updated 2026-07-17 but never actually re-marched. Surface generation for all
three already checked clean in this session (cap4 topology, all QC gates
passed at 49/71/97 pts-per-side). What's unverified is the pyHyp **volume**
march at fine/production scale:

```bash
# smoke: already validated (data/meshes/bwb_smoke, 62s march, ~1M cells).
# fine: ~4.7M cells by simple scaling from smoke -- unverified march time,
# expect low tens of minutes at most (meshing, not solving).
aeris cfd run configs/cfd/wing_gci_fine.yaml --stage surface --stage volume

# production: DSE_READINESS.md's own estimate is ~6.7M cells and explicitly
# flags this as "likely needs bigger hardware" than 16 GB. Try mesh-only
# first; if pyHyp itself OOMs or takes excessively long, that's the answer
# and there's no point attempting a solve on this machine.
aeris cfd run configs/cfd/wing_gci_production.yaml --stage surface --stage volume
```

## 3. Wing-level 3-grid GCI study (DSE_READINESS WP3 — the real gap)

This is the 3D counterpart to the 2D NACA0012 GCI ladder, and the highest-
value item left: the 2D case is a strong verification anchor but the
BWB wing is what the DSE campaign actually depends on, and DSE_READINESS.md
has flagged this as unstarted since 2026-07-16.

```bash
# Coarse member — same geometry/flight-condition as the existing
# bwb_smoke_a2_adflow run (CL=0.3980, CD=0.02640); running this AS-IS first
# is also a determinism/regression check against that prior real result.
# ANK-only (useNKSolver=false), 4 ranks. ~27 min based on the earlier run's
# run_meta.json (elapsed_seconds=1598).
aeris cfd run configs/cfd/wing_gci_smoke.yaml \
  --stage surface --stage volume --stage solve --stage post

# Medium member. Cell count ~4.7x smoke -> expect a noticeably longer solve
# (no measured data point yet; do not assume linear scaling, ADflow ANK
# iteration count is not purely a function of cell count). Watch `free -m`
# during the run -- this is the first real test of whether ANK-only fits in
# 16 GB at this size.
aeris cfd run configs/cfd/wing_gci_fine.yaml \
  --stage surface --stage volume --stage solve --stage post

# Fine member. Only attempt this if the mesh-only march in section 2 above
# actually succeeded without excessive time/RAM. Realistic outcome: this may
# simply not fit on this machine, in which case report the 2-point
# (smoke/fine) discretization-error estimate honestly rather than force a
# 3-point GCI number.
aeris cfd run configs/cfd/wing_gci_production.yaml \
  --stage surface --stage volume --stage solve --stage post
```

Once at least the smoke+fine (and ideally +production) solves have real
`solve_report.json` files:

```bash
aeris cfd gci data/cfd_cases/wing_gci_production/solve \
              data/cfd_cases/wing_gci_fine/solve \
              data/cfd_cases/wing_gci_smoke/solve \
  --quantity cl --ratio 1.4
aeris cfd gci ... --quantity cd --ratio 1.4
```
(If production wasn't solved, this needs a 2-point discretization-error
estimate instead of the 3-point Celik/Richardson procedure — `grid_convergence_index`
in `aeris.cfd.post.reports` requires exactly 3 points; report the 2-point
delta directly rather than force-fit 3-point machinery to 2 data points.)

## 4. Wing-level DOE mesh robustness campaign (DSE_READINESS WP4)

**Recommended first step overall** (agreed 2026-07-20): establish which
surface-mesh topology is robust across the design space *before* spending
compute on mesh-independence for one baseline. Two passes:

**Pass A — structured topologies (mid4/split8/cap4), undeflected, mesh-only.**
`--topology`/`--volume-level` overrides added this session (statically
validated: params-resolution logic checked in isolation, no real compute)
but **not smoke-tested with a single real sample** — the first real
invocation, even at `--n 2`, should be run by Mike.

```bash
# Sanity check first, small N, per topology, before committing to 100:
aeris cfd campaign mesh-robustness \
  --config configs/geometry/bwb_explore_wide.yaml \
  --n 2 --seed-start 0 --preset smoke \
  --workdir data/cfd_cases/mesh_robustness_smoketest_cap4
aeris cfd campaign mesh-robustness \
  --config configs/geometry/bwb_explore_wide.yaml \
  --n 2 --seed-start 0 --preset smoke --topology mid4 --volume-level L4 \
  --workdir data/cfd_cases/mesh_robustness_smoketest_mid4
aeris cfd campaign mesh-robustness \
  --config configs/geometry/bwb_explore_wide.yaml \
  --n 2 --seed-start 0 --preset smoke --topology split8 --volume-level L4 \
  --workdir data/cfd_cases/mesh_robustness_smoketest_split8

# The real campaign per topology (DSE_READINESS C1: >=100 geometries, >=98%
# target). Mesh-only, no solve. Based on the smoke preset's ~62s march + a
# few seconds of geometry/surface generation per sample, expect roughly
# 1-2 min/sample -> ~2-3 hours per topology for n=100 (~6-9 hours for all
# three). Run one topology at a time -- nothing else should run
# concurrently (pyHyp subprocess uses real CPU/RAM per sample). split8 is
# already documented in DSE_READINESS.md as a dead end (never marched) --
# running it again is a confirmation, not a discovery; deprioritize it if
# time is short and cap4/mid4 are the real comparison.
aeris cfd campaign mesh-robustness \
  --config configs/geometry/bwb_explore_wide.yaml \
  --n 100 --seed-start 0 --preset smoke \
  --workdir data/cfd_cases/mesh_robustness_campaign_cap4
aeris cfd campaign mesh-robustness \
  --config configs/geometry/bwb_explore_wide.yaml \
  --n 100 --seed-start 0 --preset smoke --topology mid4 --volume-level L4 \
  --workdir data/cfd_cases/mesh_robustness_campaign_mid4
```

Output per run: `campaign_report.json` (schema
`aeris.cfd.mesh_robustness_campaign.v1`) with per-seed status (`ok` /
`geometry_failed` / `surface_mesh_failed` / `volume_mesh_invalid_march` /
`volume_mesh_failed`), success rate, and QC metrics
(`minimum_scaled_jacobian`, march quality) for every sample. Full mesh
artifacts are kept for the first 3 successes and every failure (ParaView
inspection); later successes get their CGNS/VTK pruned, keeping only JSON.

**Pass B — deflected geometry, CAD/Gmsh path (separate from Pass A).**
Control-surface deflection is NOT a sampled variable in
`bwb_explore_wide.yaml` and is NOT compatible with the structured
mid4/split8/cap4 pipeline at all — it goes through
`aeris geometry export-deflected-cad` (produces a STEP file, built
specifically for CFD-meshing clearance) into the `cad_gmsh_tet_v1`
topology instead. This is a different, heavier pathway (CAD export + Gmsh
tet meshing) and is NOT yet wired into the campaign command — needs its own
small extension (loop deflection angles x a smaller geometry sample through
`export-deflected-cad` then `cad_gmsh_tet_v1`) before it can be run at any
scale. Treat as a follow-up after Pass A results are in, not a blocker to
starting.

**Then:** whichever topology (realistically cap4, per DSE_READINESS.md's
existing findings) comes out of Pass A as the robust choice is the one to
carry into section 3's wing-level GCI study.

## 5. Surface-mesh option sweeps -> "surface mesh laws" (rubric 2.1-2.5)

New CLI command this session: `aeris cfd campaign surface-option-sweep`.
Design: 20 geometries drawn via **true Latin Hypercube sampling**
(`aeris.dataset.sampling.samplers.lhs_v1`, space-filling over all 20 BWB
design variables -- NOT independent random seeds, which is what section 4's
`mesh-robustness` command uses) are built **once** and reused for every
level of one surface-mesh option, one option at a time (one-factor-at-a-
time, not a full factorial across all ~9 options -- combinatorially
infeasible and not how this kind of DOE is normally run). Validated this
session: LHS sampling confirmed to space-fill the bounds (20 points,
split_ratio spread 0.352-0.543 against config bounds [0.35,0.55]); a cheap
real 2-geometry x 2-level surface-only check ran correctly (no wiring bugs).
**Not run at the real n=20 scale for any option.**

```bash
# Topology comparison (cap4 known to work; mid4/split8 never validated at
# full LHS-design-space scale). Mesh-only (surface+volume), ~20 geoms x 3
# topologies x ~3 min/mesh (cap4/mid4) -- split8 is a documented dead end
# in DSE_READINESS.md, expect it to fail most/all of these.
aeris cfd campaign surface-option-sweep --config configs/geometry/bwb_explore_wide.yaml \
  --n 20 --lhs-seed 42 --option topology --levels cap4,mid4,split8 \
  --workdir data/cfd_cases/sweep_topology

# Surface split-location study (rubric 2.2)
aeris cfd campaign surface-option-sweep --config configs/geometry/bwb_explore_wide.yaml \
  --n 20 --lhs-seed 42 --option split_x_fore --levels 0.10,0.15,0.20,0.25,0.30,0.35 \
  --workdir data/cfd_cases/sweep_split_x_fore

# Surface (chordwise) resolution study (rubric 2.3)
aeris cfd campaign surface-option-sweep --config configs/geometry/bwb_explore_wide.yaml \
  --n 20 --lhs-seed 42 --option points_per_side --levels 25,33,49,65,97 \
  --workdir data/cfd_cases/sweep_points_per_side

# Spanwise resolution study (rubric 2.4)
aeris cfd campaign surface-option-sweep --config configs/geometry/bwb_explore_wide.yaml \
  --n 20 --lhs-seed 42 --option spanwise_panels --levels 2,4,8,12,16 \
  --workdir data/cfd_cases/sweep_spanwise_panels

# Tip-cap studies (rubric 2.5) -- cap_wrap_x=0.03 and cap_wrap_points=9 are
# KNOWN failures from a single-baseline test (DSE_READINESS.md 2026-07-17);
# this generalizes that finding across 20 LHS geometries instead of one.
aeris cfd campaign surface-option-sweep --config configs/geometry/bwb_explore_wide.yaml \
  --n 20 --lhs-seed 42 --option tip_radial_points --levels 3,9,17 \
  --workdir data/cfd_cases/sweep_tip_radial_points
aeris cfd campaign surface-option-sweep --config configs/geometry/bwb_explore_wide.yaml \
  --n 20 --lhs-seed 42 --option cap_width_frac --levels 0.15,0.3,0.5 \
  --workdir data/cfd_cases/sweep_cap_width_frac
aeris cfd campaign surface-option-sweep --config configs/geometry/bwb_explore_wide.yaml \
  --n 20 --lhs-seed 42 --option cap_wrap_points --levels 9,17,25 \
  --workdir data/cfd_cases/sweep_cap_wrap_points
aeris cfd campaign surface-option-sweep --config configs/geometry/bwb_explore_wide.yaml \
  --n 20 --lhs-seed 42 --option cap_wrap_x --levels 0.015,0.03 \
  --workdir data/cfd_cases/sweep_cap_wrap_x
```
Rough cost: ~20 geometries x (levels per option) x ~2-3 min/mesh (smoke
size) -- e.g. split_x_fore (6 levels) ~ 20x6x2.5min ~ 5 hours. Run ONE
option sweep at a time; this is the biggest remaining compute item in this
document. Each writes `surface_option_sweep_report.json` with per-(level,
geometry) status + real measured QC (`measured_min_scaled_jacobian`,
`measured_max_adjacent_normal_angle_deg` -- not the misleading top-level
gate-threshold fields, see the bugfix note in DSE_READINESS.md/memory).

Once results are in, fold them into `configs/cfd/SURFACE_MESH_LAWS.md` --
the "laws" Mike asked for: safe range per option, backed by
success-rate-vs-level data across a fixed 20-geometry LHS sample, not
single-baseline spot checks.

> **These sweeps are currently ON HOLD.** The baseline cap4 recipe has a
> ~30% background volume-march failure rate whose mechanism is identified
> but not yet fixed, so sweep results would attribute it to whichever
> option is being varied. See `NEXT_STEPS.md` task L1 and the failure-mode
> section of `SURFACE_MESH_LAWS.md`.

## 6. Controlled re-march experiments (volume-side single-variable studies)

`aeris cfd campaign remarch` re-marches *existing* surface meshes under
named pyHyp option variants. Because the surface mesh is copied unchanged
into every variant, any difference in the audited inverted-cell count is
attributable to the varied option alone -- and skipping geometry+surface
generation makes a single-variable study affordable on a laptop (~2 min per
march at smoke size).

```bash
N10=data/cfd_cases/mesh_robustness_n10_cap4
aeris cfd campaign remarch \
  --sample $N10/sample_00001 --sample $N10/sample_00003 --sample $N10/sample_00004 \
  --variant "baseline:" \
  --variant "eps_lo:epsE=3.0,epsI=6.0" \
  --variant "theta:theta=5.0" \
  --variant "nstart:nConstantStart=10" \
  --variant "cmax:cMax=0.25" \
  --workdir data/cfd_cases/remarch_te_inversion
```

A bare `name:` re-marches with unmodified options -- always include one as
the control. Writes `remarch_report.json` with per-(variant, sample)
status, `inverted_cells`, and the audited cluster location.

Every march (here and everywhere else) now also runs
`aeris.cfd.meshing.volume_audit` on the written CGNS: pyHyp exiting 0 does
not mean the mesh is sound, so cell volumes are recomputed from the file
that was actually written and any inversion is classified (`clean` /
`inverted_localized` / `inverted_widespread`) with its block, index range,
layer range and wall bounding box. This lands in `volume_report.json`
under `volume_audit` and on every campaign row.

## Explicitly out of scope (per this session's scope review)

- Exhaustive parameter sweeps (5-point farfield/N-count ladders, every
  pyHyp smoothing parameter, multiple turbulence models) — diagnostic
  padding once the fixed policy passes the checks above; not run, not
  claimed.
- Section 9 of `CFD_PIPELINE_DEFENSE_STUDIES.txt` (BlendNet+++ ML studies:
  baselines, ablation, leakage, uncertainty/OOD) — no such model exists yet
  in AERIS. Revisit once one is built; the CFD-side trust chain
  (`aeris.cfd.post.dataset`, conformal calibration, active learning) it
  would plug into already exists.
