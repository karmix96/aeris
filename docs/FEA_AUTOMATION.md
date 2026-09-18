# AERIS open-source FEA automation

The FEA suite turns the same deterministic BWB geometry configurations used by
the aerodynamic pipeline into a closed shell wingbox model. It is intended for
repeatable conceptual-design screening, sensitivity studies, and later
multifidelity dataset generation.

## Open-source stack

- **Gmsh 2.2** is the persistent, inspectable mesh interchange format.
- **CalculiX CrunchiX (`ccx`)** solves the linear-static shell models.
- **OpenAeroStruct 2.12** independently checks global lift behavior and supplies
  a spanwise load shape. It is installed with `pip install -e '.[fea-validation]'`.
- **CalculiX modal, buckling, and NLGEOM procedures** provide advanced physics
  checks. These are separate from the primary linear-static gate.
- Python and NumPy perform deterministic topology construction and quality
  auditing, so input preparation remains available without a solver install.

No Abaqus, NASTRAN, ANSYS, or proprietary file/API dependency is used.

## Model and gates

Each half-wing is idealized as a closed four-surface box with upper/lower skins
and front/rear spar webs. Geometry follows the generated wing's LE, chord,
twist, dihedral, and station spacing. Shell interfaces share nodes. The root is
fully constrained. Reported mass is the full symmetric-aircraft mass.

The governed baseline is exactly `lhs100_seed42[83]`, not a new random draw.
Its design-vector row is read from the locked S8 CSV and checked against every
selected CFD row. Flow values are read from `mission_authority_v1.yaml`; OAS is
run at -2, 0, 4, and 8 degrees. The comparison gates full reference area,
absolute CL error, and lift-curve slope. Viscous RANS drag is recorded but is
not compared to inviscid OAS drag.

Limit loads use the OAS sectional-force distribution as a shape and normalize
it conservatively to half of `mass × g × load factor`. The input manifest gates
that normalization to 1e-10 relative error. The current baseline uses 12.5 kg,
+3.8 g at 8 degrees, and -1.5 g at -2 degrees. The mass is an existing AERIS
mass-model assumption, not an S8 CFD result.

The workflow fails closed on invalid geometry, collapsed elements, aspect ratio,
corner angle, solver failure, missing result fields, yield safety factor,
displacement, and mass. Every stage is hashed in `case_manifest.json`.

The `physics` stage reports modal frequencies, eigenvalue-buckling factors, and
geometrically nonlinear displacement differences. Because CalculiX 2.21 does
not have a qualified nonlinear/buckling treatment for the intersecting rib and
cut-out S4 knot topology, those two checks run on a separately generated clean
closed-box topology and are explicitly labeled in `physics_report.json`; the
rich topology remains the source of the primary static result.

The `qualify` stage checks all structural values against the structural authority
file and runs an analytical cantilever benchmark. It intentionally reports
coupon and representative-wing test evidence as missing rather than inventing
it. The Round C hold-out is sealed unless a separately frozen authority grants
access.

This remains a linear, isotropic smeared wingbox model. OAS validates geometry,
global lift, lift slope, and load shape only. It does **not** validate local
shell stress, buckling, nonlinear response, joints, ribs, cut-outs, control
hinges, or composite ply failure. CalculiX root `RF` is retained as a diagnostic
but is not an acceptance gate for expanded S4 shells.

## Commands

```bash
aeris fea tools
aeris fea run configs/fea/bwb_baseline.yaml --dry-run
aeris fea run configs/fea/bwb_baseline.yaml
aeris fea study run configs/fea/study_skin_thickness.yaml
aeris fea study run configs/fea/study_mesh_convergence.yaml
aeris fea study run configs/fea/study_s8_pilot.yaml
aeris fea study run configs/fea/study_structural_dse.yaml --dry-run
aeris fea visualize data/fea_cases/bwb_baseline --study data/fea_cases/bwb_s8_mesh_convergence
aeris fea calibrate configs/fea/authorities/calibration_evidence_template.yaml
aeris fea promote-holdout --study-report study_report.json \
  --freeze-authority configs/fea/authorities/structural_freeze_v1.yaml \
  --qualification-report qualification_report.json
```

`--dry-run` generates the canonical station artifact, audited `.msh`, CalculiX
mesh include, decks, option manifests, and provenance chain without invoking
`ccx`.

The mesh-convergence study orders levels by actual element count and gates the
medium-to-fine changes in displacement, von Mises stress, and mass. A pass is
mesh-stability evidence; it is not validation of the wingbox idealization.

The `visualize` command creates reproducible PNGs for shell topology, structural
study responses, and the OpenAeroStruct-versus-S8 lift comparison. It also writes
`FEA_VISUAL_REPORT.md`, carrying the evidence status and the next three DSE-
hardening actions. Visualization files are diagnostic and do not bypass numerical
gates. `study_structural_dse.yaml` is the next DSE scaffold: it varies box depth
and skin thickness against the governed baseline and is intentionally dry-run-first
until released structural authorities and validation thresholds are available.

Completed studies now emit deterministic normalized rankings and a Pareto-front
candidate list in `study_report.json`; completed variants are cached by their
existing verification artifact so interrupted DSE campaigns can resume safely.
The calibration command consumes only declared measured records and reports a
blocked/failing result when evidence is absent or outside tolerance. Hold-out
promotion requires a passing study, a `frozen` authority with explicit access,
and a passing detailed-design physical-evidence gate; the supplied development
authority therefore remains blocked by design.

As exercised on 2026-09-17, the 546/1,332/2,392-element sequence passed with
4.93% displacement change, 6.94% peak-stress change, and less than 0.001% mass
change from medium to fine. The governed baseline is the 1,332-element level.
All ten S8 pilot wings also completed both limit cases and every OAS gate. Over
that pilot, the worst absolute CL difference was 0.0711, the worst lift-slope
difference was 4.25%, and the worst reference-area difference was 0.292%.

## Current qualification status and next work

Implemented now: exact S8 geometry/mission identity, OAS-vs-CFD global aero
comparison, conservative limit-load mapping, deterministic shell meshing,
CalculiX execution, mesh-quality gates, three-level convergence automation,
and provenance hashes. This is suitable for governed conceptual screening.

Still required before detailed design or certification use:

1. Replace assumed box depth/spar locations and the 12.5 kg mass with released
   structural and mass authorities.
2. Add ribs, root fittings, elevon hinge/support details, and manufactured
   material allowables.
3. Qualify linear buckling and modal solvers, then nonlinear/post-buckling cases
   where the linear model indicates risk.
4. Validate deflection and strain against a beam coupon and a representative
   wing test; OAS is not that structural experiment.
5. Review the automated ten-wing S8 pilot report, freeze structural thresholds,
   then use the untouched hold-out only after the structural strategy is frozen.

The software implementation now covers the orchestration, provenance, ranking,
calibration ingestion, and promotion gates for all five steps. The remaining
inputs are external engineering authorities and physical test evidence; the
workflow will not synthesize either one.
