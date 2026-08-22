# S6 study record

## Hypothesis

A proven S1 volume can be moved to an exact pyGeo wall while preserving its
structured topology and acceptable cell quality. A small set of such volumes can
serve a large campaign more reliably than remarching every exact surface.

## Implemented

- Direct evaluation of both pyGeo B-spline patches.
- S1/Openblademesh six-arc OML and seven-block tip closure.
- Exact pyGeo sampling at every span column.
- Template-specific span dimensions.
- Deterministic maximin atlas selection in the 16 neutral-OML-active dimensions.
- Deterministic quality-aware atlas enrichment before holdout freeze.
- Global chord/span affine map plus bounded column residual deformation.
- CGNS coordinate writer with source hashes.
- Independent cell volume and eight-corner scaled Jacobian audit.
- CLI, pilot harness, policy, and focused tests.

## Measurements

Surface development check, indices 0 through 9:

- 10/10 passed.
- One 13-block connectivity graph.
- Minimum surface scaled Jacobian range: +0.238 to +0.255.
- The original construction-polyline fidelity value was self-referential and is
  withdrawn. The corrected instrument tracks each node's parametric coordinate,
  independently re-evaluates pyGeo, and checks the planar tip cap. Geometry 000
  passes at `1.4081e-5` local chord versus the `1.0e-4` gate.

Same-geometry S1 volume to exact S6 wall, indices 0 through 9:

- 10/10 passed the +0.10 production floor.
- Zero inverted cells in every case.
- Worst minimum volume scaled Jacobian: +0.146067.
- Wall error: at most 1.74e-18 m.

Cross-design test, S1 template 000 to exact target 083:

- 1,621,504 cells.
- Zero inverted cells.
- Minimum volume: 8.72e-12 m3.
- Minimum scaled Jacobian: +0.196745.
- Wall error: 1.74e-18 m.
- Written CGNS independently classified clean.

Preliminary development-atlas preflight, using the provisional first ten S1 seeds:

- 100/100 geometries passed without manual repair.
- 184 template attempts: 100 passed, 81 failed quality, and three incompatible span
  laws were skipped automatically.
- Worst accepted minimum scaled Jacobian: +0.110341.
- This exposed and fixed a non-finite tip-spacing solver bug.
- This result is diagnostic only; those seeds were not selected by the final metric.

Geometry-active maximin smoke atlas:

- All 16 selected seeds marched and passed full volume/interface audit.
- Seed minimum scaled quality range: +0.15081 to +0.21498.
- 100/100 development geometries passed with no manual repair.
- 131 total attempts: 80 first-try routes and no route longer than five attempts.
- Worst accepted quality +0.15184; p05 +0.16950; median +0.20111.
- All 16 templates were selected by at least two targets.
- No quality-aware enrichment seed was needed at smoke resolution.
- This is not a holdout-unlock: production-resolution 100/100 is still required.

Production maximin seed atlas, fixed provisional policy:

- `N=257`, `epsE=1.5`, first-cell fraction `3.6e-6`.
- 16/16 templates passed; zero inverted cells and zero cells below `0.10`.
- Minimum/p05/median/maximum independent quality: `0.10535`, `0.11869`,
  `0.20978`, `0.23471`.
- Only three cells are below `0.15`; they are first-layer tip/trailing-edge cells
  in seeds 002 and 068.
- The campaign-equivalent written-CGNS canary passed targets 000 and 083.
- The complete 100-target production audit is running. No freeze claim yet.

Coarse CFD plumbing pilot, geometry 083:

- ADflow RANS-SA converged by 7.59 residual orders in 159 monitor rows.
- Final coefficients were CL -0.01947, CD +0.03366, and CMy +0.03006.
- It was correctly rejected by the wall gate: y+ p95 2.41 and maximum 7.23.
- This proves the solve and rejection path, not production wall resolution.

Old direct-march diagnostic:

- Direct pyHyp march of exact S6 target 083 failed at layer 2 and the runner
  exited with signal 11.
- It ran before the surface-interface basis correction and is therefore inconclusive.
- The atlas is selected for audited reuse and bounded recovery, not because this stale
  diagnostic proves a corrected direct march impossible.
- The target-specific fallback is S1 march followed by S6 exact-wall deformation.

## Artifacts

- `artifacts/s6_bounded_mesh_atlas/atlas_manifest_v2.json`
- `artifacts/s6_bounded_mesh_atlas/development_pilot/pilot_report.json`
- `artifacts/s6_bounded_mesh_atlas/pilot_000_to_083/deformation_report.json`
- `artifacts/s6_bounded_mesh_atlas/pilot_000_to_083/wing_vol.cgns`
- `artifacts/s6_bounded_mesh_atlas/development_atlas_smoke_all100/`
- `artifacts/s6_bounded_mesh_atlas/development_atlas_maximin16_smoke/`
- `artifacts/s6_bounded_mesh_atlas/atlas_manifest_smoke_enriched_v3.json`
- `artifacts/s6_bounded_mesh_atlas/cfd_pilot_083_n65_lowmem/`
- `artifacts/s6_bounded_mesh_atlas/campaign_preflight_10000/`
- `artifacts/s6_bounded_mesh_atlas/atlas_manifest_production_qualified16_eps15_s0p3p6_v5.json`
- `artifacts/s6_bounded_mesh_atlas/development_atlas_production_written_canary_v2/`
- `AERIS_MESH_STUDY/artifacts/strategy_studies/S6_bounded_mesh_atlas/maximin_v3/calibration_s0_3p6_production/`

## Not yet frozen

- The final atlas is still being validated at production normal resolution.
- The locked holdout has not been opened.
- Production-resolution CFD has not run; the local 16 GB machine is insufficient.
- The TE numerical-geometry aerodynamic sensitivity is still required.
- Grid convergence and turbulence-model uncertainty are not established.
- The 100-case CFD pilot and 500-1,000-case HPC rehearsal have not run.
- Production readiness cannot be claimed until the gates in `ROADMAP.md` pass.
