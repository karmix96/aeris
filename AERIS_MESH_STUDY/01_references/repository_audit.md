# Stage 00 Repository Audit

Created local: 2026-08-11

## Geometry Authority

The active geometry authority is `configs/geometry/bwb.yaml`, parsed through the
actual BWB generator code rather than copied from the runbook. The generator is
`bwb_segmented_v1`; the stable semantic stations are `b0`, `b1`, `b2`, and
`b3`. The fixed semantic entities for every strategy are leading edge, trailing
edge, root/symmetry, physical tip, planform breaks, and the symmetric
trailing-edge elevon region.

The parser reports 20 active design-variable fields. `dihedral_b1_deg` is
included in that schema but pinned at zero by the flat-root-panel invariant.
Perturbation studies must treat it as pinned until an ADR changes the invariant.

The seed-1001 baseline generated from the current parser has:

- semi-span: 0.815964194008996 m
- full span: 1.631928388017992 m
- approximate area: 0.6443883334743863 m2
- approximate aspect ratio: 4.1328964620754745
- realized sections: 17

## Existing Mesh State

The existing mesh code already contains cap4 and related topologies under
`src/aeris/mesh/`. The current registry includes `wing_mid4_v1`,
`wing_split8_v1`, `wing_cap4_v1`, and `wing_cap4_cgrid_face_v1`.

The local mesh-family notes and evidence are important control data:

- `configs/cfd/SURFACE_MESH_LAWS.md`
- `configs/cfd/MESH_FAMILY_V2.md`
- `configs/cfd/evidence/mesh_robustness_n10_cap4_report.json`
- `configs/cfd/evidence/remarch_te_inversion_report.json`

The old cap4 evidence is not production-safe by itself. It reports surface and
volume progress, but it also records trailing-edge crown inversions for some
cases. The Stage 01 control task is therefore to reproduce the existing cap4
evidence, then rerun the `epsE` sweep for `{1.5, 2.0, 3.0}` before judging new
strategies.

## CFD/TMR State

The local TMR material lives under:

- `configs/cfd/validation_naca0012_tmr.yaml`
- `configs/cfd/validation_naca0012_tmr_a0.yaml`
- `configs/cfd/validation_naca0012_tmr_coarse.yaml`
- `configs/cfd/validation_naca0012_tmr_fine.yaml`
- `configs/cfd/evidence/gci_study_naca0012.json`

The alpha-zero TMR config explicitly warns that exact NASA reference values need
a live spot-check before citation. Stage 01 must reproduce the pinned local
topology, orientation, labels, pyHyp volume, and ADflow result before any wing
strategy is scored.

## Tooling

The main project virtual environment has `pygeo`, `pyspline`,
`cgnsutilities`, `gmsh`, `pyhyp`, `aerosandbox`, and common Python numerical
packages. It does not have `adflow` or `idwarp`.

The `mach-aero` conda environment has `pyhyp`, `adflow`, and
`cgnsutilities`; it does not have `pygeo`, `pyspline`, or `idwarp`.

This split means Stage 01 should keep geometry/surface generation in the main
environment unless proven otherwise, and run ADflow validation through
`mach-aero` or a documented solver environment.

## Mission Inputs

No standalone mission YAML was found in the inspected repo paths. The operating
points in `00_governance/operating_points.yaml` are therefore provisional and
come from README/RUNBOOK defaults: 28 m/s, nominal altitude 1500 m, and a
sea-level high-Re case.

This is not a blocker for Stage 00, but it is a governance warning. If a mission
source exists outside the inspected files, Stage 01 or a new ADR must replace
the provisional operating points before solver-ranking work depends on them.

## Claude Audit Correction Addendum - 2026-08-11

The Stage 00 audit found four approval-readiness gaps. They were corrected additively.

The historical cap4 campaign config was restored from the parent of delete commit `0783c30244bcf479daf81b73f2b18575da588dbc` and verified byte-for-byte. The restored SHA-256 is `1c0bfef70f804b111d227fc0abaf55fa235c7463228cab912df1ac43636931d6`. It now lives at `AERIS_MESH_STUDY/00_governance/historical_reference_inputs/bwb_explore_wide.yaml`, not in `configs/geometry/`, so that DECISION-0001's single-live-config rule stays intact.

The old bulk cap4 run directory `data/cfd_cases/mesh_robustness_n10_cap4/` is absent. Stage 01 cannot compare against old deleted surface bytes and must freeze new `surface.fmt` hashes.

## Second Audit Correction - 2026-08-11

The restored historical config is **not** a narrower version of the current design space. It is the pre-rescale airframe that DECISION-0002 replaced:

| Field | Historical | Current |
| --- | --- | --- |
| `c1_m` | 1.2 - 2.0 m | 0.70 - 1.10 m |
| `b_total_m` (semi-span) | 1.2 - 2.0 m (full span 2.4 - 4.0 m) | 0.75 - 1.25 m (full span 1.5 - 2.5 m) |
| sweeps `sw1/sw2/sw3` | 30-55 / 10-45 / 0-30 deg | 20-40 / 15-35 / 5-25 deg |
| airfoils | `naca4412` whole wing, no `station_airfoils` | mh91 / mh91 / e374 / nlf1015 |
| `dihedral_b1_deg` | 0 - 5 deg | pinned 0.0 |
| active design variables | 17 | 20 |

Seed 0 under the historical config gives `c1_m` 1.21 m, semi-span 1.78 m and `dihedral_b1_deg` 3.65 deg - a canted root panel, which contradicts the flat-root-panel invariant frozen in `geometry_topology_contract.json`.

Consequence: the historical config is a qualitative regression input only. `epsE_common_start` is calibrated instead on ten predeclared geometries from the current design space, `00_governance/epse_calibration_lhs10_seed7_samples.csv`, which are disjoint from the Round C hold-out so that RUNBOOK Section 7's no-tuning-on-held-out rule is respected.

Additionally, the July campaign report stores no per-sample design variables, and eight commits touched `params.py`, `sampling.py`, `planform.py` or `sections.py` between the historical config's last version (2026-06-11) and HEAD. Geometry-level reproduction of the July ten therefore cannot be verified. Stage 01 must report the historical check as a mechanism-and-region match, not as numerical reproduction.

The retained CFD documents now in the Stage 00 reference package are `configs/cfd/RESULTS_ARCHIVE.md`, `configs/cfd/RETENTION.md`, `configs/cfd/NEXT_STEPS.md`, `configs/cfd/STATUS.md`, `configs/cfd/SURFACE_MESH_LAWS.md`, `configs/cfd/RUNBOOK.md`, and the evidence JSON files under `configs/cfd/evidence/`.

The old cap4 headline is corrected from 7/10 clean to 6/10 clean under the current policy, because seed 6 had 30 negative-quality layers even though it had been counted as `ok` in the old campaign report.

Raw volume-CGNS byte identity is not a valid determinism check. The retained determinism evidence says `surface.fmt` is byte-identical across reruns, while volume CGNS raw bytes can differ because of non-semantic HDF5 metadata. Volume comparison must use HDF5 dataset contents.

S2 cross-field tip meshing is blocked until a cross-field and quad-extraction dependency or in-house implementation decision is approved. This does not block Stage 01, which is only TMR/cap4/epsE control reproduction.

The LHS authority was made explicit in `00_governance/lhs_authority.yaml`: proposed sampler `lhs_v1`, seed 42, N=100 full LHS, and N=10 Round C LHS, plus seed 7 N=10 for epsE calibration. A set is identified by the quadruple (sampler, seed, n, geometry-config hash) - seed 42 at N=100 and seed 42 at N=10 share zero rows, because Latin hypercube stratification depends on N. All three sets are mutually disjoint and regenerable with `00_governance/make_lhs_sets.py --check`. Stage 00 approval freezes that proposal unless the user changes it before approval.
