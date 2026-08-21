# Stage 00 Report - Governance and Reference Freeze

Created local: 2026-08-11
Revised after Claude audit: 2026-08-11
Revised after Claude second audit: 2026-08-11

## Result

Stage 00 is complete after additive audit corrections and is stopped at the required approval gate. No Stage 01 execution has started.

Overall result: PASS

Required next user token: `APPROVE STAGE 00`

## What Changed After Audit

- Restored the historical cap4 campaign config from git history so the old campaign has its missing geometry input again.
- Recorded the retained CFD archive documents and evidence JSONs in `00_governance/reference_package_manifest.yaml`.
- Corrected the old cap4 headline: use 6/10 clean under the current quality policy, not 7/10.
- Recorded that the old bulk `data/cfd_cases/mesh_robustness_n10_cap4/` surfaces are absent, so Stage 01 must regenerate and freeze new `surface.fmt` hashes before the epsE causal experiment.
- Added `00_governance/dependency_audit.yaml`; S2 is blocked before execution until a cross-field and quad-extraction dependency or in-house implementation decision is approved.
- Added `00_governance/geometry_fidelity_gate_resolution.md`; the fidelity gate is now source-aware and does not pretend 5.6 micron tip tolerance is meaningful against looser source representations.
- Added `00_governance/lhs_authority.yaml` plus deterministic LHS CSV tables for N=100 and N=10 using `lhs_v1` seed 42.
- Expanded S0-S5 implementation notes to include algorithm, inputs, outputs, missing details, dependencies, risks, and smallest feasible prototype.

## What Changed After the Second Audit

The second audit accepted the corrections above and found one further blocker: the restored historical config is a **different aircraft**, not a wider version of the current one.

- Root chord 1.2-2.0 m against 0.70-1.10 m; full span 2.4-4.0 m against 1.5-2.5 m.
- `naca4412` across the whole wing instead of mh91 / mh91 / e374 / nlf1015.
- `dihedral_b1_deg` free to 5 deg instead of pinned at zero; seed 0 gives a root panel canted 3.65 deg.
- 17 active design variables instead of 20.

Two of those contradict invariants already frozen in `geometry_topology_contract.json`. Because RUNBOOK Section 4.2 turns the locked-ten epsE result into `epsE_common_start` for every pyHyp strategy, the previous gate would have frozen a production constant calibrated on the wrong airframe.

Corrections applied:

- Moved the historical config to `00_governance/historical_reference_inputs/bwb_explore_wide.yaml`, out of `configs/geometry/`, keeping DECISION-0001's single-live-config rule intact. Byte integrity re-verified after the move.
- Recorded the full divergence table and the usage restriction in `reference_package_manifest.yaml` under `historical_config_divergence`.
- Split the cap4 gate into `cap4_historical_regression` (qualitative, mechanism and region only) and `cap4_current_control_and_epse_common_start` (quantitative, current design space).
- Added `00_governance/epse_calibration_lhs10_seed7_samples.csv`, ten predeclared geometries from the current design space, verified disjoint from the Round C hold-out so RUNBOOK Section 7's no-tuning rule holds.
- Recorded that historical geometry-level reproduction is unverifiable: the July report stores no per-sample design variables and the generator moved eight commits since.
- Declared LHS set identity as the quadruple (sampler, seed, n, geometry-config hash) and added `make_lhs_sets.py` so every locked table is regenerable and checkable.
- Added `ADR-0003-historical-config-scope-and-epse-basis.md`.

## Key Artifacts

- `AERIS_MESH_STUDY/status`
- `AERIS_MESH_STUDY/00_governance/geometry_topology_contract.json`
- `AERIS_MESH_STUDY/00_governance/design_space_snapshot.yaml`
- `AERIS_MESH_STUDY/00_governance/operating_points.yaml`
- `AERIS_MESH_STUDY/00_governance/gate_registry.yaml`
- `AERIS_MESH_STUDY/00_governance/reference_package_manifest.yaml`
- `AERIS_MESH_STUDY/00_governance/dependency_audit.yaml`
- `AERIS_MESH_STUDY/00_governance/lhs_authority.yaml`
- `AERIS_MESH_STUDY/00_governance/lhs100_seed42_samples.csv`
- `AERIS_MESH_STUDY/00_governance/round_c_lhs10_seed42_samples.csv`
- `AERIS_MESH_STUDY/00_governance/epse_calibration_lhs10_seed7_samples.csv`
- `AERIS_MESH_STUDY/00_governance/make_lhs_sets.py`
- `AERIS_MESH_STUDY/00_governance/historical_reference_inputs/bwb_explore_wide.yaml`
- `AERIS_MESH_STUDY/00_governance/geometry_fidelity_gate_resolution.md`
- `AERIS_MESH_STUDY/00_governance/stage_status.json`
- `AERIS_MESH_STUDY/00_governance/stage_00_gate.json`
- `AERIS_MESH_STUDY/00_governance/decisions/ADR-0001-stage00-governance-freeze.md`
- `AERIS_MESH_STUDY/00_governance/decisions/ADR-0002-stage00-audit-corrections.md`
- `AERIS_MESH_STUDY/00_governance/decisions/ADR-0003-historical-config-scope-and-epse-basis.md`
- `AERIS_MESH_STUDY/01_references/paper_inventory.md`
- `AERIS_MESH_STUDY/01_references/repository_audit.md`
- `AERIS_MESH_STUDY/01_references/S0_cap4_implementation_note.md` through `S5_frozen_rbf_implementation_note.md`

## Geometry and Design Space

The authoritative current geometry input remains `configs/geometry/bwb.yaml`, parsed through `bwb_segmented_v1`. The semantic contract freezes stations `b0`, `b1`, `b2`, and `b3`; leading edge; trailing edge; root/symmetry; physical tip; planform breaks; and the symmetric trailing-edge elevon region.

The parser reports 20 active design-variable fields. `dihedral_b1_deg` remains in the schema but is pinned at zero by the flat-root-panel invariant.

## Operating Points

No standalone mission YAML was found in the inspected repo paths. The operating points remain provisional. The low-Re entry is now explicitly a minimum-local-chord Reynolds diagnostic at the declared 28 m/s and nominal altitude, not an independently confirmed low-speed mission point.

## Approval Meaning

Approving Stage 00 means accepting:

- the three locked geometry sets (`lhs_v1` seed 42 N=100, seed 42 N=10 Round C hold-out, seed 7 N=10 epsE calibration);
- the source-aware geometry-fidelity resolution;
- the historical config demoted to qualitative regression use only, with `epsE_common_start` calibrated on the current design space instead;
- the provisional operating points, which stay provisional until a mission authority exists;
- that S2 cannot run until its cross-field dependency decision is resolved.

## Stage 01 First Work

After approval, Stage 01 must run in order:

1. Reproduce the NACA0012 TMR anchor.
2. Historical check: regenerate cap4 surfaces from `00_governance/historical_reference_inputs/bwb_explore_wide.yaml` and confirm the trailing-edge-crown inversion mechanism and region still appear. Report qualitatively; numerical equality is not claimed.
3. Current control: generate the ten geometries in `00_governance/epse_calibration_lhs10_seed7_samples.csv` from `configs/geometry/bwb.yaml` and freeze their `surface.fmt` hashes.
4. Run the epsE sweep for 1.5, 2.0, and 3.0 to completion on those ten, select the highest passing value as `epsE_common_start`, and freeze it in the Stage 01 ADR.
5. Build the regression harness.

Do not begin Stage 01 until the user explicitly replies `APPROVE STAGE 00`.
