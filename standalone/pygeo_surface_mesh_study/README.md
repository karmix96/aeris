# pyGeo BWB surface-mesh law study

This package prepares and analyzes a pre-registered, geometry-conditioned
surface-mesh campaign for the canonical BWB pyGeo loft.

The current protocol is ready to plan and smoke-test. A production campaign is
intentionally blocked until all enabled metric limits in
configs/cfd/pygeo_surface_mesh_study.yaml are populated.

The detailed statistical and scientific rationale is in METHODOLOGY.md.

## Registered geometry

- one symmetric clean outer mold line;
- canonical configs/geometry/bwb.yaml definition;
- fixed b0-b3 airfoils: MH-91, MH-91, E374, NLF1015;
- flat b0-b1 root panel, so b1 dihedral is fixed at zero;
- elevon dimensions fixed because split physical CAD is outside this study;
- 14 uniformly spaced realised pyGeo source sections for every mesh;
- constant cap4 OML/tip topology and trailing-edge policy.

There are 16 independent clean-OML factors. Aspect ratio, total/panel taper,
curvature, thickness, camber, twist rate, and dihedral rate are calculated from
each realised geometry and stored as descriptors.

Thickness ratio is not independently varied because the airfoils are fixed.
The emitted agent law therefore requires the exact airfoil signature and
rejects extrapolation to other profiles.

## Exact campaign size

The campaign has two registered layers.

Geometry-law layer, with complete L1-L5 ladders:

| Stage | Geometries |
|---|---:|
| Baseline | 1 |
| Eight OFAT deltas for each of 16 factors | 128 |
| Four corners for all 120 factor pairs | 480 |
| Scrambled-Sobol global training | 1,024 |
| Independent IID uniform validation | 512 |
| **Geometry-law total** | **2,145** |

Every geometry-law case is evaluated at all five registered levels, giving
**10,725 surface-mesh builds**. Complete ladders prevent adaptive-stop
censoring from biasing refinement laws.

Mesh-control layer, with one explicit mesh per case:

| Stage | Cases |
|---|---:|
| Joint geometry x mesh-control Sobol training | 2,048 |
| Independent joint geometry x mesh-control validation | 1,024 |
| **Mesh-control total** | **3,072** |

These cases vary the same 16 geometry factors plus four individual numerical
mesh controls: chordwise/block-side points, spanwise panels per section,
cap-wrap points, and tip radial points.

The cap-wrap and tip-radial ranges are intentionally bounded to the verified
nonfolding cap4-tip domain. Higher values fold the thin BWB trailing-edge tip
collar and belong to a separate topology-redesign campaign, not this law fit.

The full registered execution plan is **5,217 cases** and **13,797 mesh
builds**.

If validation fails, the emitted law remains non-deployable. Any enrichment is
registered as a new training campaign with a fresh independent validation set.

## What the analyzer produces

- raw and fitted one-factor deltas;
- physical-unit baseline slopes and curvature;
- all direct pairwise non-additivity residuals;
- per-level, per-metric quadratic Legendre response surfaces;
- geometry-conditioned mesh-control response surfaces over 16 geometry factors
  and four individual mesh knobs;
- ridge hyperparameters selected by training-only cross-validation;
- surrogate-based first, total, and pair Sobol contributions;
- mesh-control action rankings and top geometry-mesh interactions;
- independent holdout errors and conservative false-accept audits;
- level-transition and non-monotonicity summaries;
- exact applicability ranges, fixed fields, airfoils, and topology;
- an agent-facing law that stays non-deployable unless every gate passes.

Important outputs are:

    study_manifest.json
    case_plan.json
    study_report.json
    study_report.csv
    mesh_analysis.json
    candidate_mesh_laws.md
    sensitivity_ranking.csv
    agent_mesh_law.json
    cases/<case_id>/result.json
    cases/<case_id>/geometry.json
    cases/<case_id>/attempts/L1...L5/

## Review metric limits

The acceptance.metrics entries in the registered config are populated with
hard pre-volume surface-quality gates. Review them before publication runs:

    configs/cfd/pygeo_surface_mesh_study.yaml

The rationale for each limit is in METHODOLOGY.md. Set enabled: false only
when a metric is deliberately excluded from acceptance.

## Validate and inspect the plan

    PYTHONPATH=src .venv/bin/python -m \
      standalone.pygeo_surface_mesh_study.run_study validate \
      --config configs/cfd/pygeo_surface_mesh_study.yaml

    PYTHONPATH=src .venv/bin/python -m \
      standalone.pygeo_surface_mesh_study.run_study plan \
      --config configs/cfd/pygeo_surface_mesh_study.yaml \
      --output /tmp/pygeo_surface_case_plan.json

Add --require-limits to validation immediately before a production run.

## Smoke-test one baseline mesh

A smoke run bypasses unset limits and builds only the requested level:

    PYTHONPATH=src .venv/bin/python -m \
      standalone.pygeo_surface_mesh_study.run_study smoke \
      --config configs/cfd/pygeo_surface_mesh_study.yaml \
      --workdir /tmp/pygeo_surface_smoke \
      --level L1

## Run the campaign

Run stages in this order so partial results and resource use remain explicit:

    baseline
    ofat
    pairwise
    global_train
    validation
    mesh_control_train
    mesh_control_validation

For example:

    PYTHONPATH=src .venv/bin/python -m \
      standalone.pygeo_surface_mesh_study.run_study run \
      --config configs/cfd/pygeo_surface_mesh_study.yaml \
      --workdir artifacts/pygeo_surface_mesh_study/paper_run_001 \
      --stage baseline

Use --stage all only when compute and storage budgets have been reviewed.
Completed cases resume only when their case identity and the complete source
fingerprint match.

## Analyze saved results

    PYTHONPATH=src .venv/bin/python -m \
      standalone.pygeo_surface_mesh_study.run_study analyze \
      --config configs/cfd/pygeo_surface_mesh_study.yaml \
      --workdir artifacts/pygeo_surface_mesh_study/paper_run_001

The future meshing agent must use agent_mesh_law.json only when
deployment_ready is true. The law contains both the bundled L1-L5 selection
model and the individual mesh-control retry model. The agent must still
generate the proposed mesh and accept it only from measured QC metrics.
