# ADR-0001 - Stage 00 Governance Freeze

Status: Proposed for Stage 00 approval
Date: 2026-08-11

## Decision

Use `AERIS_MESH_STUDY/` as the only study workspace and freeze the Stage 00
governance artifacts as the source of truth for Stage 01:

- geometry contract: `00_governance/geometry_topology_contract.json`
- design space: `00_governance/design_space_snapshot.yaml`
- operating points: `00_governance/operating_points.yaml`
- gates: `00_governance/gate_registry.yaml`
- workflow state: `00_governance/stage_status.json`

The authoritative geometry design space is `configs/geometry/bwb.yaml`. The
current generator reports 20 active design-variable fields; `dihedral_b1_deg`
is pinned at `0.0` by the flat-root-panel invariant and must not be perturbed
unless a later ADR changes the geometry.

## Consequences

Stage 01 may reproduce TMR, cap4, and the locked `epsE` evidence only after the
user approves Stage 00. The strategy tournament must consume the semantic
geometry contract instead of deriving anonymous landmarks independently.

The operating Reynolds values are provisional because no standalone mission YAML
was found. They are still explicit and reproducible: current defaults are
`V=28 m/s`, nominal altitude `1500 m`, and sea-level high-Re case.

## Evidence

The Stage 00 report records the repository paths, paper audit, dependency check,
and commands used to build these artifacts.
