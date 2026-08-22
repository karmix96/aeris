# AERIS Automated Meshing - Strategy Selection, AI Readiness and Validation Runbook (v7)

## Purpose

This document is the implementation plan for Codex and Claude Code.

The current `cap4` method already exists. It is now the control case, not the assumed final answer. The work must first implement, test, and compare six structured-mesh strategies. Only after one strategy wins the complete surface-volume-CFD comparison may its topology, parameters, and global laws be frozen.

The workflow is:

1. Reproduce the NACA0012 TMR anchor, the existing `cap4` result, and the known `epsE` evidence.
2. Freeze a trusted common pyHyp starting configuration.
3. Implement five alternative strategies behind one common interface.
4. Test all strategies fairly on the same geometries.
5. Select the winner using hard gates and worst-case results.
6. Measure the delta of every active design variable on every regional mesh-quality metric.
7. Fit and validate global mesh laws on the full LHS and extreme set.
8. Prove full-volume robustness and CFD usability.
9. Perform a mesh-independence study.
10. Evaluate AI mesh prediction, parameter recommendation and agentic workflow opportunities.
11. Freeze the structured workflow and run production.
12. Repeat the same selection-validation loop for Gmsh/SU2 unstructured meshes.

Do not select a strategy from surface appearance alone. A beautiful surface that produces a failed volume mesh is a failed strategy.

---

## Study workspace - create this first

At repository root, create and use one new folder named:

```text
AERIS_MESH_STUDY/
```

This `RUNBOOK.md` must live inside it. All new study configurations, commands, logs, QC tables, reports, plots, manifests, gate decisions and final results must also live inside this folder. Changes to reusable meshing source code remain in the normal AERIS package directories, but every study output must point back to the exact code/config hash that produced it.

Create this structure during Stage 00:

```text
AERIS_MESH_STUDY/
  RUNBOOK.md
  README.md
  00_governance/
    geometry_topology_contract.json
    design_space_snapshot.yaml
    operating_points.yaml
    gate_registry.yaml
    stage_status.json
    decisions/
  01_references/
  02_tmr/
  03_cap4_epse/
  04_strategy_prototypes/
    S0_cap4/
    S1_tip_first/
    S2_cross_field_tip/
    S3_station_sweep/
    S4_analytic_multiblock/
    S5_frozen_rbf/
  05_tournament/
    round_a_surface/
    round_b_volume/
    round_c_finalists/
  06_variable_deltas/
  07_global_surface_laws/
  08_volume_robustness/
  09_cfd_validation/
  10_mesh_independence/
  11_ai_readiness/
  12_control_deflection/
  13_unstructured_future/
  reports/
  artifacts/
```

Rules:

- Never overwrite a completed stage. New attempts receive a new run ID.
- Keep small evidence files, tables and reports under version control.
- Large CGNS/Plot3D/VTK meshes belong under `artifacts/`; they may be excluded from Git, but their hashes and manifests must remain.
- `00_governance/stage_status.json` is the only workflow-state source. It records the active stage and `AWAITING_USER_APPROVAL` state.
- Every stage writes its report and gate file both in its stage folder and indexes them under `reports/`.
- Do not scatter new results across existing `results/`, `/tmp`, the repository root or personal folders.

---

## 1. Required reading before coding

Read the current AERIS plan first, then the paper assigned to each strategy. Produce a one-page implementation note per strategy containing: algorithm, inputs, outputs, missing details, dependencies, risks, and the smallest feasible prototype.

| Strategy | Required attachment | Sections or ideas to extract | Main warning |
| --- | --- | --- | --- |
| Overall plan and existing `cap4` control | `Επικολλημένο markdown(3).md` | Current topology, QC channels, pyHyp settings, known TE-crown inversions, `epsE` evidence, spacing law, refinement family, production gates | Preserve the current result before changing shared code |
| S1 - Tip-first spanwise sweeping | `Openblademesh_Bachelor_Thesis_Michael_Heider_Abgabe_noBK.pdf` | Sections 1.1.2, 1.1.4, 3.1.4-3.1.7, 3.3, and 4.2; tip construction, transfinite surfaces, tip-to-root point progression, pyHyp interface | The complete blade did not march with pyHyp because of abrupt cell-size transitions |
| S2 - Cross-field tip meshing | `Automatic Multiblock Mesh Generation for 3D-Wing Aerodynamic Analysis.pdf` | Sections 3.2-3.4 and mesh-quality results; tip parameterization, triangular support mesh, cross-field, quad extraction, smoothing, projection, spanwise extrusion | Its surface was good, but minimum volume hex scaled Jacobian was only 0.0539 |
| S3 - Station-to-station sweeping | `Openblademesh_Bachelor_Thesis_Michael_Heider_Abgabe_noBK.pdf`; `Automatic Multiblock Mesh Generation for 3D-Wing Aerodynamic Analysis.pdf`; Wang paper below | Matching section grids, geometric progression, feature-aligned spanwise connection, projection, interpolation between cross-sections | Do not sweep through planform breaks without explicit anchor stations |
| S4 - Geometry-driven analytical multiblock | `applsci-16-07588.pdf` | Sections 2-4; Gordon surface, four types of control vertices and edges, four-level assembly, TFI/volume construction, farfield construction, CFD validation | No drop-in AERIS code is supplied; BWB support and fixed connectivity must be demonstrated |
| S5 - Frozen topology with RBF deformation | `Numerical Meth Engineering - 2026 - Wang - Flow Feature Aligned Structured Mesh Generation via Sweeping Cross-Field.pdf` | Section 4, especially 4.2; main cross-section, RBF mapping, B-spline projection, Poisson mesh generation | Use geometry mapping only in the production DSE; solution-dependent feature alignment remains a separate study |

Also inspect the actual AERIS meshing source, configurations, tests, baseline geometry, CGNS writer, pyHyp runner, and ADflow runner. Do not assume filenames from this document if the repository differs; record the resolved paths in the implementation note.

Locate and read the repository's NACA0012 NASA TMR mesh-generation input, stored reference outputs and comparison tolerances. If no trusted local TMR reference exists, Stage 00 must identify the authoritative reference and create a pinned regression package before Stage 01 begins.

For Stage 11, also inspect the existing AERIS dataset schemas, grouped-split utilities, uncertainty/conformal-calibration code and `AERIS_ML_USER_GUIDE.md` if present. Reuse the trusted ML evidence chain rather than building a disconnected second ML framework. If these items are absent, record that in Stage 00 instead of inventing paths.

---

## 2. Non-negotiable scientific rules

- The mesher must reproduce the prescribed CAD/OML. It must not round, trim, thicken, or smooth the physical wing to make meshing easier.
- A rounded physical tip may be used only if it is deliberately defined in the AERIS geometry generator and used consistently by every analysis method.
- Keep `te_thickness = 0.005` unless a separate geometry decision changes it.
- No case-by-case hand tuning.
- The same inputs must always produce the same mesh, QC results, and failure classification.
- During strategy selection, each method may have its own topology. After selection, the winning block graph and topology policy are frozen.
- The winner must preserve the same connectivity signature across the production design space. If a method changes block count or connectivity between geometries, it does not qualify for the main DSE without an approved topology-class policy.
- Score OML, tip, TE crown, root, planform breaks, and elevon interfaces separately. Whole-mesh averages can hide the actual failure.
- Surface, volume, and CFD stages use the same geometry IDs and immutable manifests.
- Every numerical constant entering a production preset requires an ADR with evidence.
- A failed geometry remains a failure. Do not silently switch solver, topology, or settings to rescue it.

### 2.1 Use the fixed BWB geometry topology explicitly

The AERIS BWB generator is expected to preserve a fixed geometry structure across the design space: the same ordered root-to-tip stations, planform segments, leading/trailing-edge semantics, airfoil-station roles, symmetry definition and control-region meaning. Coordinates and dimensions change, but those semantic entities remain identifiable.

This is not the same as a fixed mesh topology:

- **Fixed geometry topology:** the generator always describes the same kind of segmented BWB using corresponding stations and features.
- **Candidate mesh topology:** each of the six strategies may initially use a different block graph.
- **Frozen production mesh topology:** after the tournament, the winning block-connectivity policy is frozen while node positions, spacing and permitted counts adapt to geometry.

Stage 00 must verify this expectation in the actual generator. Do not merely assume it from old documentation. Write `00_governance/geometry_topology_contract.json` containing:

- Ordered station and segment IDs from root to tip.
- LE, TE, root, tip and symmetry entities.
- Airfoil assignment and interpolation rules.
- Planform-break and elevon/hinge entities.
- Which entities always exist and which are optional.
- Stable IDs exposed to mesh strategies.
- Generator/config source paths and hashes.

Every strategy must consume this contract instead of rediscovering anonymous geometry from raw coordinates where avoidable. In particular:

- Tip-first sweeping uses the fixed tip and ordered spanwise stations.
- Station-to-station sweeping uses the stations and planform breaks directly as anchors.
- Analytical multiblock construction derives control vertices from the same semantic geometry.
- Frozen RBF mapping uses the same stable landmarks and correspondence.
- `cap4` and cross-field candidates must still map their blocks to the contract and prove consistent boundary labels.

This is the geometry-driven part of the meshing system: local chord, thickness, sweep, taper, twist, dihedral, curvature, segment length, TE geometry and control-region geometry drive block coordinates, point counts and spacing laws. The generator's fixed semantic skeleton makes automation possible; it does not preselect `cap4` or any other mesh topology.

### 2.2 Treat the `decisions/` design space as authoritative

Stage 00 must locate the real AERIS decision/bounds files, expected to be under a repository `decisions/` area or referenced from it. Do not copy remembered ranges from this runbook into code.

Create `00_governance/design_space_snapshot.yaml` with, for every active variable:

- Canonical name and semantic meaning.
- Minimum, baseline/nominal and maximum.
- Unit and normalization rule.
- Geometry entity/entities affected.
- Source file, source key and source hash.
- Whether it is active in this mesh study.

Cross-check the decision files against geometry-generator validation, LHS configuration and current baseline. If bounds conflict, a variable is missing, or the expected count of 20 is wrong, stop Stage 00 and request a decision. All sampling, medoid calculations, extremes and variable deltas must use this frozen snapshot.

### 2.3 Gate-definition policy for the small ISR BWB UAV

Do not choose gates because a number looks reasonable. Every gate must be registered in `00_governance/gate_registry.yaml` with: metric definition, region, limit, direction, source, rationale, calibration set, validation set, and freeze stage.

Use four gate classes:

| Gate class | How the limit is chosen | Examples |
| --- | --- | --- |
| Mathematical/format | Non-negotiable correctness | Watertight surface; matching interfaces; valid boundary labels/CGNS; zero inverted or negative-volume cells; minimum signed quality greater than zero |
| Reference/regression | Pinned trusted result and declared numerical tolerance | NACA0012 TMR reproduction; `cap4` reproduction; byte-identical surfaces during the `epsE` causal experiment |
| Mission/solver | Derived from the actual low-Mach, low-Re ISR mission, turbulence model and required aerodynamic resolution | Local first-layer height; y+; Reynolds range; farfield independence; iterative convergence; acceptable CL/CD/Cm numerical uncertainty |
| Diagnostic/data-derived | Learned only from training/calibration cases, then frozen before held-out validation | Adjacent-normal change, spacing-jump warning levels, failure-prediction thresholds and quality tiers |

Current gates and targets:

- **Geometry fidelity:** no physical-geometry modification; provisional Hausdorff limit `<= 0.01%` of local chord, also report the absolute error in millimetres and CAD-kernel tolerance. Stage 00 must confirm that this is meaningful for the UAV's approximately 0.70-1.10 m chord range.
- **Surface validity:** watertight, consistent normals, exact conformal interfaces and no folded/negative surface cells.
- **Volume validity:** zero inverted/negative-volume cells and minimum signed/scaled quality `> 0` everywhere. Scaled Jacobian `>= 0.30` is a quality target and ranking criterion unless solver evidence promotes it to a hard gate.
- **pyHyp behaviour:** grid ratio target `1.0-1.2`; `epsE` is calibrated exactly as declared in this runbook.
- **Boundary layer:** for the intended wall-resolved RANS study, default target `y+ <= 1` at the highest relevant local Reynolds/wall-shear condition. If the selected turbulence/wall treatment requires something else, Stage 00 must change the gate by ADR before CFD.
- **Farfield independence:** test three domain extents. Between the two largest, force/moment changes must be small relative to the final discretization uncertainty or the predeclared engineering tolerance; define the numerical comparison before running the test.
- **Iterative convergence:** residual and force-history tolerances come from the pinned ADflow configuration. Iterative uncertainty must be demonstrably smaller than discretization uncertainty; target `<= 10%` of the mesh-discretization uncertainty where measurable.
- **DSE mesh noise:** the production-to-next-level difference should be less than one fifth of the corresponding variation across the DoE for CD and other decision-driving outputs. Report absolute coefficient differences as well as percentages.
- **Automation:** target `>= 98%` automatic mesh success on the locked production set, with every failure classified and no hand tuning.
- **AI safety:** select classifier thresholds on training/calibration data to prioritise failure recall, freeze them, and require zero observed false-safe predictions on the locked challenge set while reporting the statistical uncertainty caused by limited failures.

Small ISR BWB implications:

- The main flow is low Mach, so shock alignment is not a production gate.
- Reynolds-number and possible transition sensitivity matter; exact Re values must come from the mission atmosphere, speed and local/reference chord.
- Tip-vortex and wake dissipation matter because induced drag is important; evaluate tip/wake regions and CD noise explicitly.
- Control deflection changes geometry and remains the separate pilot defined later.
- Hardware limits determine feasible mesh levels, but memory limits must not be disguised as accuracy gates.

For a diagnostic without an external limit, collect it on the declared calibration set, publish its distribution and relationship to actual failure, then freeze any warning threshold before testing held-out cases. Targets and warnings must never be quietly rewritten as pass/fail gates after results are visible.

---

## 3. Execution protocol for Codex and Claude Code

### 3.1 Autonomy inside a stage

Once a stage is approved, execute all ordinary work inside that stage without asking for routine permission:

- Inspect and edit files inside the current repository.
- Add isolated source modules, configurations, tests and reports.
- Run safe local tests, mesh generators, QC tools and the predeclared limited simulations.
- Re-run failed tests after code corrections within the current stage.
- Create deterministic artifacts and logs.

Do not bypass operating-system, platform or repository security. Do not delete user data, push/publish externally, change credentials, install system-wide software, start an undeclared expensive campaign, or begin the next stage without approval. If any of these is required, stop and report the blocker.

### 3.2 Mandatory stop after every stage

At the end of every stage:

1. Finish all declared tests for that stage.
2. Write `stage_<NN>_report.md` containing work completed, commands/runs, results, failures, artifacts, changed files and recommendation.
3. Write `stage_<NN>_gate.json` with `PASS`, `FAIL` or `BLOCKED`, plus the measured gate values.
4. Present a short GO/NO-GO summary to the user.
5. Set the workflow state to `AWAITING_USER_APPROVAL`.
6. Stop completely. Do not start the next stage until the user explicitly replies `APPROVE STAGE <NN>`.

If a hard gate fails, recommend correction, rejection of a candidate, or redesign. Never lower a threshold after seeing the result merely to obtain a pass.

### 3.3 Master stage sequence

| Stage | Work | Required stop decision |
| --- | --- | --- |
| 00 | Create `AERIS_MESH_STUDY/`; audit papers/repository; verify the fixed BWB geometry-topology contract; snapshot authoritative `decisions/` bounds; register gates and CFD points | Approve workspace, design space, topology contract, gates and operating points |
| 01 | Reproduce NACA0012 TMR, reproduce `cap4`, calibrate the common pyHyp `epsE` starting range, then build common strategy/QC/data interfaces | Approve trusted solver, control and harness |
| 02 | Implement S1-S5 minimum surface prototypes | Approve candidates entering Round A |
| 03 | Round A surface feasibility | Reject failures; approve volume-feasible candidates |
| 04 | Round B volume feasibility | Select and approve two finalists |
| 05 | Round C finalist comparison and winning-strategy ADR | Approve and freeze the winner |
| 06 | Per-variable mesh-quality delta/sensitivity study | Approve influential variables and sampling changes |
| 07 | Full LHS/extreme surface laws and validation | Approve frozen surface policy |
| 08 | Volume laws and full volume-success campaign | Approve frozen volume policy |
| 09 | ADflow CFD validation at declared operating points | Approve CFD-ready workflow |
| 10 | Structured mesh-independence/GCI study | Approve production structured level |
| 11 | AI readiness, model baselines and agentic workflow prototype | Approve/reject each AI use case |
| 12 | Small indicative symmetric-control-deflection CFD pilot | Approve deflection automation as later work or keep manual |
| 13 | Unstructured Gmsh/SU2 strategy loop | Use internal sub-gates equivalent to Stages 02-10 |

Stage 00 starts when this plan is given to the coding agent. Every later stage requires the explicit approval token above.

---

## 4. Common software architecture

### 4.1 Reproduce the NACA0012 TMR anchor

Before refactoring:

- Regenerate the pinned 2D NACA0012 TMR mesh with the same software versions and inputs used by the stored reference.
- Compare topology, dimensions, orientation, boundary labels, mesh quality and relevant pyHyp outputs against the reference tolerances.
- Store environment, dependency versions, commands and comparison results.
- Add the TMR reproduction to continuous/integration testing at an appropriate cost level.
- Treat any unexplained TMR mismatch as a hard stop. Do not continue to `cap4` or the strategy tournament.

Run this anchor again after any pyHyp, CGNS, PETSc, MPI or mesh-export dependency change.

### 4.2 Preserve the `cap4` control and calibrate the common pyHyp start

After TMR passes:

- Run the existing baseline `cap4` case.
- Save geometry, surface mesh, volume mesh, QC, logs, CGNS, and CFD smoke result.
- Add a test-must-reproduce check for all meaningful numerical outputs.
- Record current runtime, memory, cell count, and failure locations.

Then reproduce the existing 10-geometry `epsE` experiment before implementing or judging alternative strategies:

- Use the same 10 locked geometries and byte-identical `cap4` surface meshes.
- Test `epsE = {1.5, 2.0, 3.0}`. Never use the known-bad shipped value `epsE = 6.0` in the tournament.
- Run the complete march on all 10 geometries; an early-layer march is only a preflight.
- Require zero inversions, zero negative-volume cells, zero negative-quality layers and minimum scaled quality greater than zero.
- Record the full layer/block failure locations and pyHyp grid ratio.
- Select the highest `epsE` that passes all 10 as `epsE_common_start` and freeze it in the Stage 01 ADR.
- If none passes all 10, stop and repair the underlying TE-crown/spanwise-spacing mechanism before the tournament.

This common value is the trusted starting point, not necessarily the final value for every surface topology.

### 4.3 Create one strategy interface

All candidates must use a common interface equivalent to:

```text
prepare_geometry(geometry)
build_surface(geometry, level, config)
build_volume(surface, level, config)
export_solver_mesh(mesh, solver)
run_surface_qc(mesh, geometry)
run_volume_qc(mesh)
connectivity_signature(mesh)
write_manifest(run)
```

Register the six strategies by stable IDs:

```text
S0_CAP4
S1_TIP_FIRST_SWEEP
S2_CROSS_FIELD_TIP
S3_STATION_SWEEP
S4_ANALYTIC_MULTIBLOCK
S5_FROZEN_RBF
```

Shared geometry ingestion, QC definitions, manifests, plotting, CGNS validation, and solver launchers must not be duplicated inside strategy modules.

### 4.4 Required artifacts per run

- `manifest.json`: strategy, geometry hash, config hash, code version, seed, level and environment.
- `connectivity.json`: block count, dimensions, interfaces, boundary labels and connectivity hash.
- `surface_qc.json`: geometry error and quality by region.
- `volume_qc.json`: quality by block and layer, negative/inverted-cell counts and failure location.
- `timing.json`: generation time, peak memory and cell count.
- `cfd_summary.json`: solver status, residual history, forces, moments, y+ and runtime.
- Preview files for surface, volume slices and the worst cells.

No result may exist only in terminal text.

---

## 5. Geometry states and CFD design points

### 5.1 Stage 00 must create the authoritative table

Read the AERIS geometry and mission configurations and write `operating_points.yaml`. Do not silently assume that remembered values are current. The expected starting values are below; Stage 00 must calculate and report the exact Reynolds numbers before approval.

Common settings unless explicitly changed:

```text
beta_deg: 0
p_rad_s: 0
q_rad_s: 0
r_rad_s: 0
control_deflection_deg: 0
```

Define Reynolds levels from the actual mission atmosphere and geometry:

- `Re_low`: smallest relevant local/MAC chord at the highest declared altitude and lowest declared speed.
- `Re_nom`: baseline reference chord at the nominal mission point. Initial reference: `V = 28 m/s`, `altitude = 1500 m`.
- `Re_high`: largest relevant chord at the lowest declared altitude and highest declared speed. Initial low-altitude reference: `altitude = 0 m`.

Store density, dynamic viscosity, speed, altitude, reference chord and resulting Reynolds number. Never write only `Re_low` without the physical values used to obtain it.

### 5.2 Conditions used at each stage

| Study | Geometry/control state | CFD points |
| --- | --- | --- |
| Surface feasibility | Neutral CAD, `delta_e = 0` | No AoA or Re is required |
| Volume feasibility | Neutral CAD; first-layer sizing based on the highest relevant Re/wall-shear condition | No CFD except the declared smoke run |
| Strategy-selection smoke | Neutral CAD, `delta_e = 0` | `alpha = 4 deg`, `Re_nom` |
| Winner CFD AoA sweep | Neutral CAD, `delta_e = 0` | `alpha = {-2, 0, 4, 8} deg` at `Re_nom` |
| Winner CFD Re sweep | Neutral CAD, `delta_e = 0` | `Re = {Re_low, Re_nom, Re_high}` at `alpha = 4 deg` |
| Structured mesh independence | Neutral CAD, `delta_e = 0` | Core: `alpha = {-2, 4, 8} deg` at `Re_nom`; additional baseline checks at `alpha = 4 deg`, `Re_low` and `Re_high` |
| Unstructured comparison | Same exact neutral CAD | Same points as the structured study |

The AoA and Re sweeps contain six unique primary points:

```text
(-2 deg, Re_nom)
( 0 deg, Re_nom)
( 4 deg, Re_low)
( 4 deg, Re_nom)
( 4 deg, Re_high)
( 8 deg, Re_nom)
```

This avoids an unnecessary 4 x 3 full factorial while still separating AoA and Reynolds effects. Add the full factorial only if the results show a significant interaction that matters to the conclusions.

### 5.3 Control-deflection pilot

Control deflection changes the physical CFD geometry and may require a separate mesh. It is therefore excluded from strategy selection, global-law fitting, success-rate claims and the primary mesh-independence study.

After the neutral structured workflow passes mesh independence, run a small indicative symmetric-elevon pilot:

- Geometries: baseline and one difficult/extreme geometry.
- Symmetric deflection: `delta_e = {-5, +5} deg`; use existing `delta_e = 0` results as references.
- AoA: `{0, 4, 8} deg`.
- Reynolds number: `Re_nom`.
- Beta and rates: zero.

This requires 12 new deflected CFD cases if both geometries are used. If automated deflected-CAD meshing is not yet robust, generate and inspect these meshes manually, label the study as an indicative pilot, and do not mix its data into the automated neutral-mesh claims. Asymmetric controls are deferred.

---

## 6. Strategies to implement

### S0 - Existing `cap4` control

- Preserve the current method.
- Apply only corrections that are also available to other candidates, such as common QC and exact interface-spacing checks.
- Keep its known weak regions visible; do not hide them through averaging.

### S1 - Tip-first spanwise sweeping

- Mesh the exact physical tip first.
- Build a structured tip pattern with matching upper, lower, LE and TE boundaries.
- Sweep that pattern from tip toward root.
- Determine spanwise point counts from physical segment length and a geometric-progression law.
- Enforce exact cell-size matching at every planform break.
- Report how quality changes with distance from the tip.
- Treat abrupt tip-to-wing spacing changes as the main risk.

### S2 - Cross-field tip meshing

- Triangulate the exact tip surface only as a support mesh.
- Solve the cross-field with LE, TE and tip boundaries as directional constraints.
- Trace the field, extract quad blocks, optimize, and project nodes back to the exact CAD surface.
- Connect the tip blocks to a compatible spanwise surface mesh.
- Record singularity count and block graph. Topology drift across geometries is a production failure.
- Do not automatically copy the paper's rounded NURBS geometry.

### S3 - Station-to-station sweeping

- Place anchor sections at root, every BWB planform/airfoil break, elevon boundaries where required, and tip.
- Build matching structured grids at paired anchor sections.
- Connect one interval at a time instead of performing one uninterrupted root-tip extrusion.
- Use TFI, elliptic, or Poisson smoothing inside each segment.
- Enforce compatible node counts and exact first/last cell-size matching across interfaces.
- This is expected to handle the segmented AERIS planform better than pure tip-to-root sweeping.

### S4 - Geometry-driven analytical multiblock

- Represent the wing with compatible profile and guide curves, following the Gordon-surface principle.
- Construct surface, boundary-layer outer, interior-field, and farfield control vertices analytically from local geometry.
- Assemble edges, domains, faces, and volume blocks in explicit stages.
- Generate the volume directly using TFI/elliptic/Poisson methods; do not require pyHyp for this candidate.
- Adapt the published wing method to the BWB root, multiple planform breaks, blunt TE and elevons.
- This candidate qualifies only if its connectivity rule remains deterministic and comparable across the design space.

### S5 - Frozen topology with RBF deformation

- After S0-S4 baseline prototypes exist, select the strongest baseline block skeleton as the seed. This does not make it the final winner.
- Freeze its block graph, node indexing, landmarks and boundary labels.
- Map it to new sections/geometries using RBF deformation.
- Project boundary nodes back to the exact CAD surface and propagate displacement smoothly to interior nodes.
- Store maximum/RMS projection error, tangent error, Hausdorff distance and RBF conditioning diagnostics.
- Reject folds, block overlap and connectivity changes.

---

## 7. Strategy-selection tournament

Selection is staged to avoid spending months fully implementing a method that fails immediately.

### Round A - Surface feasibility

Run all six strategies on:

- 1 baseline geometry.
- 5 deliberately difficult geometries covering thin/small tip, large sweep, strong taper, maximum twist/dihedral, and the strongest planform-break/elevon combination.

Maximum: `6 strategies x 6 geometries = 36 surface meshes`.

Hard surface gates:

- Exact prescribed geometry; Hausdorff error no greater than 0.01% of local chord.
- Watertight surface, consistent normals and exact block-interface matching.
- No folded or negative surface cells.
- Correct boundary labels and deterministic connectivity signature.
- No manual edits.

Quality metrics, reported by region:

- Shape metric, scaled Jacobian and equiangle skewness.
- Aspect ratio and chordwise/spanwise growth.
- Interface spacing jump.
- Adjacent surface-normal change.
- Geometry projection distance and angle.
- Cell count, time and memory.

Do not invent new pass thresholds for diagnostic metrics. Report their distributions first.

### Round B - Full-volume feasibility

For every strategy passing Round A, generate a low/medium-cost full volume on:

- Baseline.
- The two geometries where that strategy had its worst surface quality.

Maximum if all pass: `6 x 3 = 18 full volumes`.

For every pyHyp candidate:

1. Begin with the Stage 01 `epsE_common_start`, never the shipped value 6.0.
2. On the Round-B baseline and two declared training extremes only, test the same predeclared set `epsE = {1.5, 2.0, 3.0}`.
3. Use a short early-layer march only to reject obvious failures, then complete every surviving march.
4. Select the highest value that passes all three training geometries.
5. Freeze that strategy's `epsE` before Round C. No `epsE` tuning is allowed on the 10 held-out LHS geometries or eight Round-C extremes.

A topology can legitimately require a different stable `epsE`; allowing the same small calibration budget for every pyHyp strategy is fairer than forcing one universal value. Store both `epsE_common_start` and the frozen per-strategy value.

For direct-volume candidates, use the same farfield, boundary-layer intent and outer-boundary labels as closely as possible. Any direct-volume numerical controls receive the same three-geometry calibration budget and must also be frozen before Round C.

Hard volume gates:

- Zero inverted cells and zero negative-volume cells.
- Minimum scaled quality greater than zero everywhere; 0.30 is the quality target, not permission to ignore lower positive cells.
- Valid structured multiblock CGNS readable by ADflow.
- Correct symmetry, wall and farfield boundaries.
- No disconnected blocks, duplicate faces or inconsistent interfaces.
- Complete automatically without per-case changes.

### Round C - Finalists

Take the best two strategies from Round B and run them on the common selection set:

- 1 baseline.
- 8 locked validation extremes not used for per-strategy Round-B calibration.
- 10 fixed-seed LHS geometries.

Total: `2 x 19 = 38 full meshes` plus one ADflow RANS smoke run per mesh at `(alpha = 4 deg, Re_nom, delta_e = 0)`, using the physical values frozen in `operating_points.yaml`.

Selection order:

1. Must pass every hard surface, volume, export and solver gate.
2. Highest automatic success rate and deterministic topology stability.
3. Best worst-case volume quality, not best baseline or best average.
4. Lowest CFD convergence problems and force scatter.
5. Best geometry fidelity.
6. Lowest cell count, runtime, memory and implementation burden.

Issue a signed selection ADR containing all raw results and the reason the winner was chosen. Then freeze the winning topology policy. `cap4` wins only if the evidence says it wins.

---

## 8. Per-variable deltas and development of the winner

Use the complete fixed-seed LHS set (current target `N = 100`), all predeclared extremes, and the baseline. Stage 00 must confirm the authoritative LHS size and seed. The baseline remains a regression reference, but it is not the primary sensitivity anchor because its mesh quality is unusually favourable.

### 8.1 Per-variable mesh-quality delta study

Stage 00 must obtain the authoritative active design-variable list from the geometry configuration. The current expected count is 20; do not silently omit, rename or add variables.

First run the frozen winning strategy at the cheap development level on the complete LHS. Select three actual, valid anchor geometries using a scripted and reproducible rule:

- `A_MEDOID`: the LHS medoid in normalized design-variable space, minimizing total distance to the other LHS points.
- `A_TIP_TE`: the LHS/extreme geometry with the worst tip or TE-crown regional quality/failure state.
- `A_PLANFORM`: a different geometry with the worst planform-break/interface quality or strongest sweep/taper/twist/dihedral transition.

Do not construct an artificial coordinate-wise median geometry. Store every anchor's normalized design variables and its percentile for every regional quality metric. Also report the original baseline's percentiles so its unusually favourable position remains visible.

For every active variable `x_i`, create two local one-at-a-time geometries around `A_MEDOID`:

```text
x_i_minus = x_i_anchor - 0.10 * (upper_i - lower_i)
x_i_plus  = x_i_anchor + 0.10 * (upper_i - lower_i)
```

Clip only when necessary to remain inside the declared bounds and record the actual normalized step. All other variables remain at the anchor. For 20 variables this produces `1 + 2 x 20 = 41` medoid-centred surface meshes with the frozen winning strategy.

For every mesh metric `Q`, region and variable, calculate:

```text
delta_Q_minus = Q(x_i_minus) - Q(anchor)
delta_Q_plus  = Q(x_i_plus)  - Q(anchor)
central_slope = [Q(x_i_plus) - Q(x_i_minus)] / actual_normalized_step
asymmetry     = abs(delta_Q_plus + delta_Q_minus)
```

Do this for:

- Minimum and low-percentile shape metric, scaled Jacobian and skewness.
- Maximum aspect ratio, directional growth and interface-spacing jump.
- Maximum adjacent-normal change and geometry-projection error.
- Surface and volume cell count, runtime and memory.
- Volume minimum quality, failing block/layer, inversion count and march success on the most influential cases.
- ADflow convergence, y+ and CL/CD/Cm deltas only on the reduced cases selected below.

Report deltas separately for OML, tip, TE crown, root, planform breaks and elevon interfaces. A variable can improve one region and damage another; one global number is insufficient.

After all 41 medoid-centred surface runs:

1. Rank variables by worst regional degradation and by failure probability.
2. Select the top 5-8 influential variables, including the strongest positive/negative effects and any nonlinear/asymmetric variable.
3. Repeat both perturbation directions for only those variables around `A_TIP_TE` and `A_PLANFORM`. This adds approximately 20-32 surface meshes, not another complete 82-case OFAT campaign.
4. Identify variables whose sign or ranking changes between anchors; these are likely nonlinear or interacting.
5. Run full volumes for the perturbations that cause the strongest degradation, sign changes or surface failure; do not automatically volume-mesh every OFAT case.
6. Run nominal CFD only for cases that materially change the volume mesh or solver behavior.
7. Compare the local deltas with global effects observed in the LHS using standardized regression, permutation importance and partial-dependence diagnostics.

OFAT measures local main effects and does not establish global causality or interactions. If anchor rankings disagree strongly, or local and global rankings conflict, add a predeclared Morris screening design before fitting global laws. Do not use Sobol indices from an ordinary LHS and call them valid Sobol sensitivity results.

Required outputs:

- `variable_delta_surface.csv`
- `variable_delta_volume.csv`
- `variable_delta_cfd.csv`
- `sensitivity_anchors.json` with selection evidence and regional percentiles.
- Regional delta heatmaps.
- Ranked influential-variable table with signs, anchor dependence and failure directions.
- Stage 06 report and GO/NO-GO gate.

### 8.2 Surface-law development

- Run the winner initially at a cheap development level.
- Collect one row per local mesh region, not one row per whole geometry.
- Vary only exposed, dimensionless controls.
- Fit simple deterministic laws using local chord, thickness, sweep, curvature, spanwise segment length, taper, twist, dihedral and interface geometry.
- Laws must control chordwise counts, spanwise counts, clustering, tip resolution, planform-break transitions and interface growth.
- Prefer monotone, interpretable equations over a black-box predictor.
- Validate laws on held-out LHS geometries and all extremes.

### 8.3 Freeze surface behavior

- Same geometry and level must always return the same counts and connectivity.
- No hidden fallback or manual override.
- Store the law version and inputs in every manifest.
- Require at least 98% automatic surface success across the complete geometry set; classify every failure.

---

## 9. Full-volume robustness and volume laws

### 9.1 Define physical inputs

Derive from the actual AERIS mission/configuration:

- Reynolds-number range using local chord, speed, altitude and viscosity.
- Target wall treatment and y+.
- First-layer height as a function of local chord and local Reynolds number.
- Boundary-layer thickness/march distance.
- Wall-normal growth ratio and layer count.
- Farfield extent.

Do not copy farfield distances or first-layer heights from the papers. Test three farfield sizes and choose the smallest size for which forces stop moving materially.

### 9.2 Volume campaign

- Run full volume generation for baseline + all extremes + full LHS.
- Require zero inversions, zero negative layers and valid solver export.
- Report success rate, worst block, worst layer and failure mechanism.
- Target at least 98% fully automatic success with no hand intervention.
- If failures cluster by geometry, improve the global law and rerun the complete locked validation set.
- Freeze the final volume policy before production CFD.

---

## 10. CFD validation

### 10.1 Solver smoke and envelope

- Run ADflow on every accepted structured mesh at `(alpha = 4 deg, Re_nom, delta_e = 0)`.
- On a representative subset covering baseline, extremes, LHS regions and every failure/quality tier, run the six unique neutral-CAD points declared in Section 5.2.
- Use `operating_points.yaml` as the source of truth. Do not create a new AoA/Re table inside the solver script.
- Verify residual convergence, stable force histories, mass conservation, y+, and physically smooth CL/CD/Cm trends.
- Mesh quality is geometry-dependent; y+ and solver behavior are flow-condition-dependent. Report them separately.

### 10.2 Production CFD gate

Proceed only when:

- Mesh generation and ADflow launch are automatic and deterministic.
- No strategy or parameter changes depend on the CFD answer.
- CFD failures are classified as mesh, setup, physics or solver failures.
- The final configuration, code, geometry, mesh and solver hashes are stored.

---

## 11. Mesh-independence study

- Build at least three systematically refined levels from the frozen winner.
- Refine chordwise, spanwise and wall-normal distributions through one documented family while preserving topology and boundary locations.
- Keep the effective refinement ratio approximately constant and record the actual characteristic cell size.
- Use baseline, the worst-quality extreme, and one representative LHS geometry.
- Use the three core conditions `(-2 deg, Re_nom)`, `(4 deg, Re_nom)` and `(8 deg, Re_nom)` for all selected geometries.
- On the baseline, add `(4 deg, Re_low)` and `(4 deg, Re_high)` to check Reynolds sensitivity.
- Evaluate CL, CD, Cm, L/D, y+, residual behavior and selected Cp distributions.
- Compute observed order and GCI where the solutions are in the asymptotic range.
- If convergence is non-monotonic or the family is not systematic, use an Eca-Hoekstra least-squares uncertainty method and state why.
- Add another level only when the first three do not establish a usable trend.
- Choose the production level from error versus cost, not from cell count alone.

After this gate, freeze the complete structured recipe and run the production DSE.

---

## 12. AI readiness and agentic meshing workflow

AI is not assumed to be useful. It must beat the deterministic global laws on held-out geometries and must never hide unsafe failures.

### 12.1 Build an AI-ready dataset from the beginning

Every structured and later unstructured run must append machine-readable records at three resolutions:

- One row per geometry/strategy/level/run.
- One row per mesh region.
- One row per failed block/layer or solver failure event.

Inputs must include:

- All active geometry design variables and normalized values.
- Derived local geometry: chord, thickness, sweep, taper, twist, dihedral, curvature, TE geometry and planform-break measures.
- Strategy ID, connectivity hash, mesh level and all mesh-control values.
- Operating condition, Reynolds inputs, AoA and control state where applicable.
- Early pyHyp/direct-volume diagnostics, timing and memory.

Targets must include:

- Surface and volume pass/fail.
- Worst quality and low percentiles by region.
- Failure location and failure class.
- Cell count, runtime and memory.
- ADflow convergence, y+, CL/CD/Cm and mesh-level deltas.

Use stable schemas, units, missing-value reasons and provenance hashes. Never infer a missing failure metric as zero.

### 12.2 AI use cases, in recommended order

1. **Mesh evaluator:** predict pass/fail, worst region and expected minimum quality before an expensive full march.
2. **Early-failure predictor:** use the first pyHyp layers or direct-volume iterations to decide whether continuing is worthwhile.
3. **Mesh-parameter recommender:** recommend bounded values for counts, growth, tip resolution, `s0`, march controls and farfield size within the frozen topology.
4. **Quality/cost surrogate:** predict quality, cell count, memory and runtime to expose the Pareto trade-off.
5. **Active-learning selector:** request new geometries or mesh-control experiments only where predictive uncertainty is high.
6. **AI-assisted mesh deformation/generation:** predict RBF/control-point displacements or initial block-node positions inside the already frozen topology, followed by exact CAD projection and normal QC. Never allow an unconstrained model to invent production connectivity.
7. **Mesh-field/GNN research:** predict local quality or deformation on the mesh graph. This is optional and only justified after simpler tabular models fail.
8. **Agentic workflow:** orchestrate geometry, meshing, QC, bounded retries, solver launch, evidence collection and stage reports.

### 12.3 Model-development protocol

- Start with deterministic thresholds, linear/logistic models and interpretable global laws.
- Then compare ExtraTrees/Random Forest and gradient-boosted trees. Use a GNN or neural operator only if the data volume and spatial target justify it.
- Split by `geometry_id`; all levels, regions and strategies belonging to one geometry must stay in the same train/validation/test group.
- Keep all predeclared extreme geometries in an untouched challenge set.
- For classifiers, report failure recall, precision-recall AUC, false-safe rate, calibration and confusion matrix. A model that labels a failing mesh as safe is the dangerous error.
- For regression, report MAE, worst-case error, rank correlation and calibrated prediction intervals by region.
- Compare against the frozen analytical laws and a simple majority/median baseline.
- Use SHAP/permutation importance only as model diagnostics; the physical delta study in Section 8 remains the primary causal sensitivity evidence.
- Accept AI into the workflow only when it improves held-out performance or cost without reducing safety or reproducibility.

### 12.4 Bounded agentic policy

The first agentic workflow must be deterministic around the LLM:

```text
read frozen config
generate geometry
run selected mesh strategy
run QC
classify result
if approved Tier-B condition is met: run one predeclared retry
otherwise stop as pass/fail
launch solver only after mesh pass
write evidence package
stop at the current human gate
```

Rules:

- Maximum retries and allowed parameter changes are predeclared and versioned.
- The agent cannot change CAD, topology, solver, thresholds or design point.
- The agent cannot invent a new rescue setting from free text during production.
- LLM diagnosis may propose a future experiment, but it cannot silently execute it outside the current approved stage.
- Every decision stores the input evidence, rule/model version, confidence and action.

### 12.5 AI decision gate

For every AI use case, choose one outcome:

- `ADOPT`: validated and allowed in the bounded workflow.
- `ADVISORY_ONLY`: useful for diagnosis but cannot control production.
- `REJECT`: does not beat the deterministic approach or is unsafe.
- `DEFER`: insufficient data.

Stage 11 must stop with a separate decision for each use case. Do not bundle all AI ideas into one vague approval.

---

## 13. Indicative control-deflection CFD pilot

- Execute the exact pilot matrix in Section 5.3 only after Stage 10 passes.
- Keep neutral and deflected geometry hashes distinct.
- Regenerate the surface and volume mesh for the physically deflected CAD.
- Inspect hinge, gap/closure, elevon side edges and TE-crown quality separately.
- Compare deflected CL/CD/Cm against the neutral references and check qualitative control trends.
- If automation is difficult, manual generation and inspection are allowed only for this clearly labelled pilot.
- End Stage 12 with a decision: automate deflected meshing next, redesign the control geometry, or retain manual indicative cases.

---

## 14. Unstructured Gmsh/SU2 loop

Begin only after the structured workflow is frozen and documented.

Repeat the same logic using the exact same CAD, geometry IDs, flow conditions and reporting schema:

1. Define at least three Gmsh candidates, for example:
   - Frontal-Delaunay surface + prism boundary layer + tetrahedral farfield.
   - HXT volume + prism boundary layer.
   - Curvature/distance-field controlled surface and volume + prism boundary layer.
2. Run surface feasibility on baseline + difficult extremes.
3. Run full-volume feasibility and SU2 import/smoke tests.
4. Compare finalists on baseline + extremes + the same 10 LHS selection geometries.
5. Choose and freeze one unstructured strategy.
6. Fit its global size, curvature, boundary-layer and farfield laws on the full LHS/extreme set.
7. Prove automatic volume success and SU2 convergence.
8. Perform a three-level unstructured mesh-independence/GCI study.
9. Compare structured ADflow and unstructured SU2 only through uncertainty bands on matched geometries and conditions, not through one mesh from each solver.

Do not use SU2 as a rescue path for structured geometries that fail ADflow meshing. The structured and unstructured campaigns are separate, predeclared methods.

---

## 15. Optional studies outside the production policy

- Flow-feature-aligned tip-vortex or wake blocks may be tested on 2-3 geometries to estimate dissipation error.
- Solution-dependent feature alignment must not enter the main DSE because it gives each design a mesh chosen from its own CFD answer.
- Overset feature blocks are a later research task, not a requirement for selecting the production mesh.

---

## 16. Stop conditions

Stop, record evidence, and ask for a decision if:

- The NACA0012 TMR anchor does not reproduce within its pinned tolerances.
- The current `cap4` control cannot be reproduced.
- No `epsE` in `{1.5, 2.0, 3.0}` passes the locked 10-geometry pre-tournament campaign.
- A candidate requires changing the physical geometry.
- Required cross-field, RBF, CGNS or direct-volume dependencies are unavailable or have incompatible licenses.
- A strategy changes topology unpredictably across the selection set.
- No candidate completes the full-volume feasibility gate.
- The winner needs manual tuning on individual geometries.
- Failures move unpredictably between refinement levels.
- Compute is insufficient for the declared mesh family and no uncertainty fallback has been approved.

---

## 17. Final deliverables

- Pinned NACA0012 TMR regression package and Stage 01 reproduction report.
- Reproduced 10-geometry `epsE` evidence, common-start ADR and frozen per-strategy values.
- Six isolated structured strategy implementations.
- Reproducible strategy-selection dataset and report.
- Selection ADR and frozen structured topology policy.
- Per-variable regional surface, volume and CFD delta tables, anchor-percentile evidence and sensitivity report.
- Surface and volume global laws with held-out validation.
- Full LHS/extreme robustness report.
- ADflow CFD validation report.
- Mesh-independence and uncertainty report.
- AI-ready run/region/failure datasets with documented schemas.
- AI evaluator/recommender baselines and per-use-case adoption decisions.
- Bounded, audited agentic workflow prototype.
- Indicative symmetric-control-deflection CFD report.
- Frozen structured production configuration.
- Equivalent Gmsh/SU2 unstructured selection and validation package.
- Structured-versus-unstructured comparison with uncertainty bands.
