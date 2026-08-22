# S6 Bounded Mesh Atlas

S6 is the recommended candidate route. It is not production-frozen yet.

It combines:

1. exact pyGeo wall coordinates,
2. proven S1/Openblademesh topology and pyHyp volume seeds,
3. a small parameter-space atlas,
4. bounded volume deformation,
5. independent mesh rejection,
6. ADflow RANS/SA with a frozen solve policy.

The key rule is simple: a case reaches CFD only after the written CGNS passes all
mesh gates. Parameter distance chooses a candidate template; it never certifies it.

## Current evidence

- Exact S6 surfaces: 10/10 development geometries pass surface QC.
- Same-geometry S1-to-S6 deformation: 10/10 pass.
- Worst deformation minimum scaled Jacobian: +0.146.
- Inverted cells: 0 in all ten cases.
- Cross-design deformation 000 to 083: 1,621,504 cells, minimum +0.197, 0 inverted.
- All accepted meshes have 20 conformal internal interfaces below 1.0e-10 m.
- A provisional first-ten-seed preflight passed 100/100 development geometries;
  worst accepted quality was +0.110. It was diagnostic, not the final atlas.
- The geometry-active maximin selection produced 16/16 valid smoke seeds; their
  minimum qualities span +0.151 to +0.215.
- The maximin smoke atlas passed 100/100 geometries in 131 attempts; 80 passed
  first try, no route needed more than five attempts, and worst quality was +0.15184.
- One fixed provisional production policy passed 16/16 maximin seeds at `N=257`:
  `epsE=1.5`, first-cell fraction `3.6e-6`, worst quality +0.10535.
- The campaign-equivalent written-CGNS production canary passed 2/2 targets.
- The qualified 21-template written-CGNS audit passed 100/100 development targets.
- Three governed N65 laptop pilots passed 3/3 solver paths and 0/3 strict coarse
  y+ screens; they do not validate or reject the production wall law.
- A deterministic 10,000-design manifest was generated and checked in about 2 s.
- Production CFD/y+, TE/grid sensitivity, and the locked holdout remain.

## Commands

```bash
# Select candidate atlas points.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/run_s6.py \
  atlas --template-count 16 --trust-radius 0.40 \
  --output artifacts/s6_bounded_mesh_atlas/atlas_manifest_v2.json

# Build and audit the selected development templates.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/build_seeds.py \
  --level smoke \
  --atlas-manifest artifacts/s6_bounded_mesh_atlas/atlas_manifest_v2.json \
  --output AERIS_MESH_STUDY/artifacts/strategy_studies/S6_bounded_mesh_atlas/maximin_v2/smoke

# Validate all 100 development geometries, trying the full atlas when needed.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/development_atlas.py \
  --atlas-manifest artifacts/s6_bounded_mesh_atlas/atlas_manifest_v2.json \
  --template-root AERIS_MESH_STUDY/artifacts/strategy_studies/S6_bounded_mesh_atlas/maximin_v2/smoke \
  --preferred-quality 0.15 \
  --output artifacts/s6_bounded_mesh_atlas/development_atlas_maximin16_smoke

# Add deterministic seeds for weak, slow, or failed development routes.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/run_s6.py \
  enrich-atlas \
  --atlas-manifest artifacts/s6_bounded_mesh_atlas/atlas_manifest_v2.json \
  --development-report artifacts/s6_bounded_mesh_atlas/development_atlas_maximin16_smoke/atlas_validation_report.json \
  --output artifacts/s6_bounded_mesh_atlas/atlas_manifest_smoke_enriched_v3.json

# If seeds were added, build them and repeat validation/enrichment. Then build
# production-normal-resolution seeds; smoke evidence cannot set freeze_ready.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/build_seeds.py \
  --level production \
  --atlas-manifest artifacts/s6_bounded_mesh_atlas/atlas_manifest_smoke_enriched_v3.json \
  --eps-e 1.5 --first-cell-fraction 3.6e-6 \
  --output AERIS_MESH_STUDY/artifacts/strategy_studies/S6_bounded_mesh_atlas/maximin_v3/calibration_s0_3p6_production

# Repeat the 100-case validation at production resolution, then make the final
# enrichment decision. Only this report may set freeze_ready.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/development_atlas.py \
  --atlas-manifest artifacts/s6_bounded_mesh_atlas/atlas_manifest_production_qualified16_eps15_s0p3p6_v5.json \
  --template-root AERIS_MESH_STUDY/artifacts/strategy_studies/S6_bounded_mesh_atlas/maximin_v3/calibration_s0_3p6_production \
  --eps-e 1.5 \
  --preferred-quality 0.15 \
  --output artifacts/s6_bounded_mesh_atlas/development_atlas_maximin16_production_written_v2
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/run_s6.py \
  enrich-atlas \
  --atlas-manifest artifacts/s6_bounded_mesh_atlas/atlas_manifest_production_qualified16_eps15_s0p3p6_v5.json \
  --development-report artifacts/s6_bounded_mesh_atlas/development_atlas_maximin16_production_written_v2/atlas_validation_report.json \
  --output artifacts/s6_bounded_mesh_atlas/atlas_manifest_production_enriched_v6.json

# Build one exact target surface.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/run_s6.py \
  surface --index 83 --level smoke \
  --output artifacts/s6_bounded_mesh_atlas/surfaces

# Deform one proven volume and audit every cell.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/run_s6.py \
  deform --template-cgns TEMPLATE.cgns \
  --template-surface TEMPLATE_surface_blocks.npz \
  --target-surface TARGET_surface_blocks.npz \
  --output-cgns TARGET.cgns --report TARGET_report.json

# Reproduce the ten-case development pilot.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/pilot.py \
  --output artifacts/s6_bounded_mesh_atlas/development_pilot

# Create a deterministic 10,000-design LHS and one-flow manifest.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/campaign.py \
  sample-designs --count 10000 --seed 2026 --output designs_10000.csv
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/campaign.py \
  make-manifest --designs designs_10000.csv \
  --flows AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/examples/flows_single.csv \
  --output campaign_10000.json

# Audit immutable seed files and bind the registry to the atlas hash.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/campaign.py \
  build-registry \
  --atlas-manifest artifacts/s6_bounded_mesh_atlas/atlas_manifest_production_enriched_v6.json \
  --source-root AERIS_MESH_STUDY/artifacts/strategy_studies/S6_bounded_mesh_atlas/maximin_v3/calibration_s0_3p6_production \
  --eps-e 1.5 \
  --output template_registry.json

# Run one design, all its flow points, and prune its accepted transient mesh.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/campaign.py \
  run-design --manifest campaign_10000.json --registry template_registry.json \
  --campaign-root campaign_output --design-index 0 --np 4 --prune-accepted-mesh

# Start with limited Slurm concurrency; raise it only after the HPC rehearsal.
export S6_MANIFEST="$PWD/campaign_10000.json"
export S6_REGISTRY="$PWD/template_registry.json"
export S6_CAMPAIGN_ROOT="$PWD/campaign_output"
sbatch --array=0-9999%50 \
  AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/slurm_run_design_array.sh

# Safe to repeat after jobs finish; accepted cases are hash-cached.
AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/slurm_collect.sh

# Focused tests.
.venv/bin/python -m pytest -q \
  AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/test_s6.py
```

## Production order

For each geometry:

1. Build and validate pyGeo.
2. Build the exact S6 target surface.
3. Try frozen atlas seeds nearest first until quality reaches +0.15; retain the
   best mesh above the +0.10 hard floor.
4. If no atlas mesh reaches +0.15, try target-specific S1 at the epsE and wall law
   recorded in the frozen registry.
5. Deform the fallback to the exact wall and audit it again.
6. Reject and log the case if the fallback fails. Never repair it by hand.
7. Run ADflow only on an accepted written CGNS.
8. Accept CFD only after residual, force-stability, finite-value, and y+ gates pass.
9. Prune accepted transient meshes only after all flow points for that design pass.

Do not freeze the atlas until the 100-case development run passes. Run the locked
holdout only once after that freeze. Production readiness and future Gmsh/SU2 and
AI work are tracked in `ROADMAP.md`.
