# NEXT_STEPS — shared task board

Hand-maintained (unlike `STATUS.md`, which is auto-generated run telemetry).
Whoever finishes a task edits this file, commits, and pushes; the other
machine pulls before starting.

**Division of labor.** Laptop (Linux, mach-aero) = diagnosis and controlled
single-variable experiments on small samples. Desktop (Windows/WSL2) =
full-scale execution — n=20 LHS x option-level sweeps, 100-geometry DOE,
GCI ladders; anything with real wall-clock cost, and only once the laptop
has validated the approach.

Last updated: 2026-07-22 (laptop).

---

## Clean slate — where things stand

`data/cfd_cases/` and `data/meshes/` were **deleted on 2026-07-22** (1.25 GB)
to restart the campaign against a corrected recipe. Nothing was lost that
matters: findings live in `configs/cfd/` (tracked) —

- `RESULTS_ARCHIVE.md` — the NACA0012 TMR validation, GCI ladder,
  cross-solver comparison and determinism results from the deleted runs.
- `SURFACE_MESH_LAWS.md` — the trailing-edge inversion failure mode and the
  `epsE` dose-response that explained it.
- `evidence/*.json` — the raw reports those two files cite.
- `RETENTION.md` — what is kept versus regenerated, and why it is safe.

Retention is now enforced in code: `aeris cfd prune` (dry-run by default),
`campaign remarch --keep-meshes` off by default, and the existing
`--keep-success-examples` on `campaign mesh-robustness`.

**The headline finding to build on:** the shipped `epsE=6.0` pyHyp default
*causes* localized cell inversion at the blunt-TE crown on cap4 wings.
Lowering it to 3.0 removed the defect on 2 of 3 known-failing geometries
and cut the third from 14 inverted cells to 2. Everything below assumes we
fix that first, because every mesh in the old campaign was marched with the
bad value.

---

## Step 1 — laptop — find the `epsE` floor  (~15 min)

Stage the three known-failing geometries as surfaces only (seconds, no
marching), then sweep `epsE` below 3.0:

```bash
aeris cfd campaign mesh-robustness \
  --config configs/geometry/bwb_explore_wide.yaml \
  --n 5 --seed-start 0 --skip-volume \
  --workdir data/cfd_cases/surfaces_seed0_4

S=data/cfd_cases/surfaces_seed0_4
aeris cfd campaign remarch \
  --sample $S/sample_00001 --sample $S/sample_00003 --sample $S/sample_00004 \
  --variant "eps30:epsE=3.0,epsI=6.0" \
  --variant "eps20:epsE=2.0,epsI=4.0" \
  --variant "eps15:epsE=1.5,epsI=3.0" \
  --workdir data/cfd_cases/remarch_eps_floor
```

Pick the **highest** `epsE` that gives 3/3 clean — `epsE` exists to keep the
marching front smooth, so it cannot be driven to zero for free. Check the
winner's `low_quality_layers` and `min_march_quality` too, not just the
inverted-cell count: trading inversion for severe skew is not a fix.

Then record the law in `SURFACE_MESH_LAWS.md` and set the value as the
curated cap4 default in the preset, so no one has to remember to pass it.

## Step 2 — laptop — confirm on a fresh sample  (~35 min)

```bash
aeris cfd campaign mesh-robustness \
  --config configs/geometry/bwb_explore_wide.yaml --n 10 --seed-start 0 \
  --workdir data/cfd_cases/mesh_robustness_n10_epsfix
```

Success criterion: **10/10 clean**, and `failure_mechanisms` empty. Seeds
0-9 are the same draw as the old campaign, so this is a direct before/after
against the archived 7/10 (which was really 6/10 — seed 6 passed with 30
negative-quality layers). Anything still failing is a *new* mechanism and
gets the same treatment: audit, localize, controlled remarch.

## Step 3 — laptop — re-establish the validation anchor  (~10 min)

The 2D NACA0012 TMR case is the trust chain and its artifacts were deleted.
It uses an airfoil O-grid, not cap4, so the `epsE` finding does not affect
it — this is a straight regeneration to prove the pipeline still reproduces
`CL = 1.0918` vs TMR's 1.0909.

```bash
aeris cfd run configs/cfd/validation_naca0012_tmr.yaml
```

Compare against `configs/cfd/RESULTS_ARCHIVE.md`. If it does not reproduce,
stop — that is a regression in the suite, not a meshing question.

## Step 4 — desktop — the 8 surface-option sweeps  (~20-25 h)

**Blocked until steps 1-3 pass.** Commands in `RUNBOOK.md` section 5, one
option at a time, starting with `topology`. These are the "surface mesh
laws" — safe range per option across a fixed 20-geometry LHS sample.

Group results by `volume_audit_classification` /
`inverted_on_spanwise_edge` / `failure_mechanisms`, not by the coarse
status: the whole point of the audit work is that a failure now names its
own mechanism.

Run `aeris cfd prune data/cfd_cases/sweep_*` after each sweep — 600 marches
at ~42 MB each is ~25 GB if left unpruned.

## Step 5 — desktop — wing-level 3-grid GCI

`RUNBOOK.md` section 3. Independent of the sweeps.

---

## Done 2026-07-22 (laptop)

- Diagnosed the n=10 failure mode from retained artifacts with no new
  compute: localized to the blunt-TE crown at spanwise extremities; ruled
  out surface-QC gates, TE thickness, and pyHyp itself.
- Found meshes were accepted/rejected on the march *log* alone, with
  nothing ever checking the file written. Added
  `aeris.cfd.meshing.volume_audit` (chunked, classifies and localizes
  inversion), wired into every march and campaign row.
- Added `aeris cfd campaign remarch` and proved the `epsE` dose-response.
- Added `aeris cfd prune`, `--skip-volume`, and the retention policy.
